"""Per-collider wetness accumulation helper.

Rain impacts are recorded by the emitter as an invisible mesh of real vertices
at the hit positions (the "impact sink" in rainfx/gn/precip.py). This group is
added as a Geometry Nodes modifier on collider objects that opted into wetness:

  SIM  per step (own Simulation Zone, state = the collider mesh carrying
       FLOAT attributes "rainfx_wet" / "rainfx_pool" on the FACE CORNER domain,
       starting at 0). Corners are evaluated at their vertex position with
       their face's normal: coplanar neighbours share a value at a shared
       vertex, so the shader interpolates smoothly across them (no per-face
       tiles), while a hard edge (a cube's top vs its side) keeps two values
       and puddles never bleed down walls:
         1. impacts = Mesh component of the Emitter's evaluated geometry
            (ObjectInfo RELATIVE: the carrier holds world-space hits, brought
            into this collider's local space, so moved, rotated or scaled
            colliders get wet where the rain lands)
         2. streak/splash streams are Instances and drop out at
            SeparateComponents, so the remaining Mesh IS the impact events
         3. increment = Strength * exp(-(distance(corner, nearest impact) / radius)^2)
         4. wet <- min(1, wet * (1 - Dry Rate * dt) + inc * (1 - wet))
         5. pool <- max(pool * (1 - Dry Rate * dt * 0.25), inc * flat * low)
            ("rainfx_pool") - fills instantly inside the footprint on flat
            up-facing low spots and lingers ~4x longer than surface wetness.
         6. snow <- min(snow + Snow Rate * dt * exp(-(dist(v, flake) / radius)^2)
            * up, 1) ("rainfx_snow", per-vertex, accumulated per second like
            the dry rate) - flakes arrive via a SECOND
            carrier ("RainFX Snow Impacts") split off by the handler; there
            is no melt, so snow persists after the storm.

   POST-SIM  Set Position lifts every vertex along its normal by
             rainfx_snow * Snow Depth (metres). The offset is recomputed
             fresh from the accumulated attribute each evaluation, so the
             sim state never feeds displacement back into itself.

With no Emitter assigned the increment is 0 and wet stays 0 forever, so the
group passes the collider through unchanged - inert by default.

The impact stream is the hidden "RainFX Impacts" carrier object whose verts
are copied from the emitter by a frame_change_post handler (see
scene/wetness.py); a direct ObjectInfo(emitter) wiring forms a depsgraph
cycle that kills every helper once two or more objects carry one.

Bake-safe: pure node logic; the only Python is the persistent handler that fills the carriers. The helper's sim cache is
independent of the rain cache (bake it the same way if you farm-render).
"""
from __future__ import annotations

import bpy

from .dsl import B, ensure_versioned

GROUP_NAME = "RainFX Wetness"
EXPOSURE_TILTS = (0.0, 0.25, 0.5, 0.75, 1.0)   # share of the wind tilt per exposure ray
GROUP_VERSION = 5   # 5 (1.0): impacts read RELATIVE, Gaussian footprint, ambient wetness and snow cover from exposure; 4 (0.4): wet/pool on the FACE CORNER domain (smooth, no per-face tiles)


def ensure_group() -> bpy.types.NodeTree:
    ng = bpy.data.node_groups.get(GROUP_NAME)
    if ng is not None and ng.get("rainfx_version") == GROUP_VERSION:
        return ng
    return ensure_versioned(ng, GROUP_NAME, build)


def build() -> bpy.types.NodeTree:
    ng = bpy.data.node_groups.new(GROUP_NAME, "GeometryNodeTree")
    ng["rainfx_version"] = GROUP_VERSION
    b = B(ng)
    it = ng.interface
    it.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

    p = b.panel("Wetness")
    b.add_input("Geometry", "NodeSocketGeometry",
                desc="Collider geometry (wired automatically; carries the wet attribute)")
    wet_panel = b.panel("Wetness")
    b.add_input("Emitter", "NodeSocketObject", parent=wet_panel,
                desc="RainFX emitter whose evaluated geometry carries the impact events")
    b.add_input("Wet Radius", "NodeSocketFloat", 0.2, 0.001, 5.0, wet_panel,
                "Spread of the wet footprint around each hit (metres)")
    b.add_input("Strength", "NodeSocketFloat", 0.5, 0.0, 2.0, wet_panel,
                "How wet each hit makes the surface per step")
    b.add_input("Dry Rate", "NodeSocketFloat", 0.02, 0.0, 1.0, wet_panel,
                "Share of existing wetness lost per second")
    b.add_input("Snow Impacts", "NodeSocketObject", parent=wet_panel,
                desc="Hidden carrier carrying snowflake landings (wired automatically)")
    b.add_input("Snow Rate", "NodeSocketFloat", 0.02, 0.0, 1.0, wet_panel,
                "Snow units added per second inside a flake footprint")
    b.add_input("Snow Depth", "NodeSocketFloat", 0.05, 0.0, 1.0, wet_panel,
                "Metres of lift on fully snowed up-facing verts")
    amb_panel = b.panel("Ambient")
    b.add_input("Shelter", "NodeSocketObject", parent=amb_panel,
                desc="Hidden world-space copy of every collider, for the exposure test (wired automatically)")
    b.add_input("Rain Direction", "NodeSocketVector", (0.0, 0.0, 1.0), parent=amb_panel,
                desc="Direction the rain comes from (up and into the wind), in this object's space")
    b.add_input("Sky Direction", "NodeSocketVector", (0.0, 0.0, 1.0), parent=amb_panel,
                desc="World up in this object's space")
    b.add_input("Ambient Wet", "NodeSocketFloat", 0.0, 0.0, 1.0, amb_panel,
                "Wetness of every surface the rain can reach, beyond the simulated hits")
    b.add_input("Ambient Pool", "NodeSocketFloat", 0.0, 0.0, 1.0, amb_panel,
                "Standing-water level on exposed flat ground (the shader floods its low spots)")
    b.add_input("Wet Up Time", "NodeSocketFloat", 0.0, 0.0, 600.0, amb_panel,
                "Seconds for exposed surfaces to wet up; 0 = already wet on the first frame")
    b.add_input("Ambient Snow", "NodeSocketFloat", 0.0, 0.0, 1.0, amb_panel,
                "Snow cover (0-1, x Snow Depth) on exposed up-facing surfaces while snow falls")

    def GI(name):
        return gi.outputs[name]

    gi = b.node("NodeGroupInput")
    go = b.node("NodeGroupOutput")

    # ------------------------------------------------------------- sim zone
    sim_in = b.node("GeometryNodeSimulationInput")
    sim_out = b.node("GeometryNodeSimulationOutput")
    sim_in.pair_with_output(sim_out)
    # --------------------------------------------- exposure (once, at the start)
    # A corner is exposed when a ray from just off its face, toward where the
    # rain comes from, meets no collider: open ground and windward walls are,
    # ground under a roof and leeward walls are not. The target is the hidden
    # "RainFX Shelter" mesh (a world-space copy of all colliders made by
    # scene/wetness.py): reading the collider collection itself would make
    # every collider depend on every other one, itself included.
    e_fn = b.node("GeometryNodeFieldOnDomain", domain="FACE", data_type="FLOAT_VECTOR")
    b.put(b.sin(e_fn, "Value"), b.node("GeometryNodeInputNormal").outputs[0])
    face_n = b.sout(e_fn, "Value")
    up_l = b.vm("NORMALIZE", GI("Rain Direction"))
    shelter = b.node("GeometryNodeObjectInfo", transform_space="RELATIVE")
    b.put(shelter.inputs["Object"], GI("Shelter"))
    # five rays (straight up to full wind tilt), averaged: gusts swing
    # the rain about, so a street canyon gets a soft rain shadow on its upwind
    # side instead of a hard dry band, and only real cover stays fully dry
    sky = b.vm("NORMALIZE", GI("Sky Direction"))
    src = b.vm("ADD", b.node("GeometryNodeInputPosition").outputs[0], b.vscale(face_n, 0.02))
    open_sum = None
    tilts = []
    for f in EXPOSURE_TILTS:               # straight up ... full wind tilt
        tilts.append(b.vm("NORMALIZE", b.vm("ADD", b.vscale(sky, 1.0 - f), b.vscale(up_l, f))))
    for d in tilts:
        r = b.node("GeometryNodeRaycast", data_type="FLOAT")
        b.links.new(shelter.outputs["Geometry"], r.inputs["Target Geometry"])
        b.put(r.inputs["Source Position"], src)
        b.put(r.inputs["Ray Direction"], d)
        b.put(r.inputs["Ray Length"], 1000.0)
        clear = b.fm("SUBTRACT", 1.0, r.outputs["Is Hit"])
        open_sum = clear if open_sum is None else b.fm("ADD", open_sum, clear)
    open_frac = b.fm("DIVIDE", open_sum, float(len(EXPOSURE_TILTS)))
    facing = b.vdot(face_n, b.vm("NORMALIZE", b.vm("ADD", sky, up_l)))
    face_w = b.node("ShaderNodeMapRange", interpolation_type="SMOOTHSTEP")
    b.put(face_w.inputs["Value"], facing)
    b.put(face_w.inputs["From Min"], 0.0)
    b.put(face_w.inputs["From Max"], 0.5)
    exposed = b.fm("MULTIPLY", open_frac, face_w.outputs["Result"])
    flat_w = b.node("ShaderNodeMapRange", interpolation_type="SMOOTHSTEP")
    b.put(flat_w.inputs["Value"], b.sep(face_n)[2])
    b.put(flat_w.inputs["From Min"], 0.94)
    b.put(flat_w.inputs["From Max"], 0.99)
    pool_exp = b.fm("MULTIPLY", exposed, flat_w.outputs["Result"])
    start_wet = b.fm("LESS_THAN", GI("Wet Up Time"), 0.001)   # 1 = already wet
    amb_start = b.fm("MULTIPLY", b.fm("MULTIPLY", GI("Ambient Wet"), exposed), start_wet)
    pool_start = b.fm("MULTIPLY", b.fm("MULTIPLY", GI("Ambient Pool"), pool_exp), start_wet)
    g0 = b.store(GI("Geometry"), "rainfx_exposed", exposed, "FLOAT", domain="CORNER")
    g0 = b.store(g0, "rainfx_pool_exposed", pool_exp, "FLOAT", domain="CORNER")
    g0 = b.store(g0, "rainfx_amb", amb_start, "FLOAT", domain="CORNER")
    g0 = b.store(g0, "rainfx_pool", pool_start, "FLOAT", domain="CORNER")
    wet0 = b.store(g0, "rainfx_wet", amb_start, "FLOAT", domain="CORNER")
    # snow settles on what faces up and is exposed: the corner exposure,
    # averaged onto the vertex, gated by the vertex normal
    v_up = b.node("ShaderNodeMapRange", interpolation_type="SMOOTHSTEP")
    b.put(v_up.inputs["Value"], b.sep(b.node("GeometryNodeInputNormal").outputs[0])[2])
    b.put(v_up.inputs["From Min"], 0.5)
    b.put(v_up.inputs["From Max"], 0.9)
    g1 = b.store(wet0, "rainfx_snow_exp", b.fm("MULTIPLY", b.attr("rainfx_exposed"), v_up.outputs["Result"]),
                 "FLOAT", domain="POINT")
    snow_start = b.fm("MULTIPLY", b.fm("MULTIPLY", GI("Ambient Snow"), b.attr("rainfx_snow_exp")), start_wet)
    g1 = b.store(g1, "rainfx_amb_snow", snow_start, "FLOAT", domain="POINT")
    snow0 = b.store(g1, "rainfx_snow", snow_start, "FLOAT", domain="POINT")
    b.links.new(snow0, sim_in.inputs["Geometry"])
    S0, dt = sim_in.outputs["Geometry"], sim_in.outputs["Delta Time"]

    # ------------------------------------------------- impacts from the emitter
    obj = b.node("GeometryNodeObjectInfo", transform_space="RELATIVE")
    b.put(obj.inputs["Object"], GI("Emitter"))
    obj_comp = b.node("GeometryNodeSeparateComponents")
    b.links.new(obj.outputs["Geometry"], obj_comp.inputs["Geometry"])
    impacts = obj_comp.outputs["Mesh"]  # hit vertices in this collider's space

    # ------------------------------------------------------- wetness update
    fpos = b.node("GeometryNodeInputPosition").outputs[0]  # the corner's vertex position
    prox = b.node("GeometryNodeProximity", target_element="POINTS")
    b.links.new(impacts, prox.inputs["Geometry"])
    b.put(prox.inputs["Sample Position"], fpos)
    rad = b.fm("MAXIMUM", GI("Wet Radius"), 0.001)
    # Gaussian footprint: as strong as before near the hit, but negligible past
    # ~2 radii, so repeated rain does not creep under roofs and overhangs
    # (exp(-d/r) gave 2% per step at 4 radii, which adds up over a shot)
    _q = b.fm("DIVIDE", prox.outputs["Distance"], rad)
    footprint = b.fm("EXPONENT", b.fm("MULTIPLY", b.fm("MULTIPLY", _q, _q), -1.0))
    inc = b.fm("MULTIPLY", GI("Strength"), footprint)

    wet = b.attr("rainfx_wet")
    valid = prox.outputs["Is Valid"]  # empty impact stream must wet nothing
    decay = b.fm("SUBTRACT", 1.0, b.fm("MINIMUM", b.fm("MULTIPLY", GI("Dry Rate"), dt), 1.0))
    grown = b.fm("ADD", b.fm("MULTIPLY", wet, decay),
                 b.fm("MULTIPLY", b.fm("MULTIPLY", inc, valid), b.fm("SUBTRACT", 1.0, wet)))
    amb = b.attr("rainfx_amb")
    amb_target = b.fm("MULTIPLY", GI("Ambient Wet"), b.attr("rainfx_exposed"))
    k_up = b.fm("MINIMUM", b.fm("DIVIDE", dt, b.fm("MAXIMUM", GI("Wet Up Time"), 0.001)), 1.0)
    amb1 = b.fm("ADD", amb, b.fm("MULTIPLY", b.fm("SUBTRACT", amb_target, amb), k_up))
    S1 = b.store(S0, "rainfx_amb", amb1, "FLOAT", domain="CORNER")
    wet1 = b.store(S1, "rainfx_wet", b.fm("MAXIMUM", b.fm("MINIMUM", grown, 1.0), amb1), "FLOAT", domain="CORNER")

    # --------------------------------------- puddle pool (flat, low, up-facing)
    # height-based mask: normalized height over the object's own bbox; thin
    # flat colliders (range ~ 0) count as all-low so water collects everywhere
    nrm = b.node("GeometryNodeInputNormal").outputs[0]
    # the FACE normal at each corner (a smooth-shaded mesh would otherwise hand
    # corners its vertex normal, tilting cube-top corners toward the walls)
    fnorm = b.node("GeometryNodeFieldOnDomain", domain="FACE", data_type="FLOAT_VECTOR")
    b.put(b.sin(fnorm, "Value"), nrm)
    flat = b.fm("MAXIMUM", b.vdot(b.sout(fnorm, "Value"), b.xyz(0.0, 0.0, 1.0)), 0.0)
    bbox = b.node("GeometryNodeBoundBox")
    b.links.new(S0, bbox.inputs["Geometry"])
    mx, my, mz = b.sep(bbox.outputs["Min"])
    XX, YX, ZX = b.sep(bbox.outputs["Max"])
    hnorm = b.fm("DIVIDE", b.fm("SUBTRACT", b.sep(fpos)[2], mz), b.fm("MAXIMUM", b.fm("SUBTRACT", ZX, mz), 0.01))
    low = b.fm("SUBTRACT", 1.0, b.fm("MINIMUM", hnorm, 1.0))
    # height-weighted puddle mask: low spots pool up to 65% stronger; a hard
    # gate would stop elevated tops (hnorm = 1) from holding any rain at all
    pinc0 = b.fm("MULTIPLY", inc, b.fm("MULTIPLY", flat,
                                       b.fm("ADD", b.fm("MULTIPLY", low, 0.65), 0.35)))
    pinc = b.fm("MULTIPLY", pinc0, valid)
    pool = b.attr("rainfx_pool")
    pd = b.fm("MINIMUM", b.fm("MULTIPLY", GI("Dry Rate"), b.fm("MULTIPLY", dt, 0.25)), 1.0)
    grown_p = b.fm("MAXIMUM", b.fm("MULTIPLY", pool, b.fm("SUBTRACT", 1.0, pd)), b.fm("MINIMUM", pinc, 1.0))
    amb_frac = b.fm("DIVIDE", amb1, b.fm("MAXIMUM", GI("Ambient Wet"), 0.001))
    pool_amb = b.fm("MULTIPLY", b.fm("MULTIPLY", GI("Ambient Pool"), b.attr("rainfx_pool_exposed")), amb_frac)
    pool1 = b.store(wet1, "rainfx_pool", b.fm("MAXIMUM", grown_p, pool_amb), "FLOAT", domain="CORNER")

    # ------------------------------------------- snow accumulation (per-vertex)
    # flakes need their own ObjectInfo: a mesh input is not switchable per point,
    # and Is Valid on the snow stream is what keeps rain-only worlds inert
    sobj = b.node("GeometryNodeObjectInfo", transform_space="RELATIVE")
    b.put(sobj.inputs["Object"], GI("Snow Impacts"))
    sobj_comp = b.node("GeometryNodeSeparateComponents")
    b.links.new(sobj.outputs["Geometry"], sobj_comp.inputs["Geometry"])
    flakes = sobj_comp.outputs["Mesh"]

    sprox = b.node("GeometryNodeProximity", target_element="POINTS")
    b.links.new(flakes, sprox.inputs["Geometry"])
    _sq = b.fm("DIVIDE", sprox.outputs["Distance"], rad)
    sfoot = b.fm("EXPONENT", b.fm("MULTIPLY", b.fm("MULTIPLY", _sq, _sq), -1.0))
    # per-vertex: InputNormal is the vertex normal in point context, which is
    # exactly what Set Position needs afterwards
    sup = b.fm("MAXIMUM", b.vdot(nrm, b.xyz(0.0, 0.0, 1.0)), 0.0)
    sinc = b.fm("MULTIPLY", GI("Snow Rate"),
                b.fm("MULTIPLY", b.fm("MULTIPLY", sfoot, sup), sprox.outputs["Is Valid"]))
    snow = b.attr("rainfx_snow")
    grown_s = b.fm("MINIMUM", b.fm("ADD", snow, b.fm("MULTIPLY", sinc, dt)), 1.0)
    amb_s = b.attr("rainfx_amb_snow")
    amb_s1 = b.fm("ADD", amb_s, b.fm("MULTIPLY", b.fm("SUBTRACT", b.fm("MULTIPLY", GI("Ambient Snow"),
                                                                     b.attr("rainfx_snow_exp")), amb_s), k_up))
    S2 = b.store(pool1, "rainfx_amb_snow", amb_s1, "FLOAT", domain="POINT")
    snow1 = b.store(S2, "rainfx_snow", b.fm("MAXIMUM", grown_s, amb_s1), "FLOAT", domain="POINT")
    b.links.new(snow1, sim_out.inputs["Geometry"])

    # ----------------------------------------- post-sim displacement (fresh)
    # every evaluation recomputes offset = normal * snow * depth from the state
    # attribute; the state itself never received displacement, so no feedback
    disp = b.vscale(nrm, b.fm("MULTIPLY", b.attr("rainfx_snow"), GI("Snow Depth")))
    lifted = b.set_position(sim_out.outputs["Geometry"], offset=disp)
    b.links.new(lifted, go.inputs["Geometry"])
    return ng
