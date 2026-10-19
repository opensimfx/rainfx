"""Per-collider wetness accumulation helper.

Rain impacts are recorded by the emitter as an invisible mesh of real vertices
at the hit positions (the "impact sink" in rainfx/gn/precip.py). This group is
added as a Geometry Nodes modifier on collider objects that opted into wetness:

  SIM  per step (own Simulation Zone, state = the collider mesh carrying a
       per-face FLOAT attribute "rainfx_wet", starting at 0):
         1. impacts = Mesh component of the Emitter's evaluated geometry
            (ObjectInfo ORIGINAL; the carrier matches the emitter transform,
            so hit positions land on this collider's world-space geometry)
         2. streak/splash streams are Instances and drop out at
            SeparateComponents, so the remaining Mesh IS the impact events
         3. increment = Strength * exp(-distance(face, nearest impact) / radius)
         4. wet <- min(1, wet * (1 - Dry Rate * dt) + inc * (1 - wet))
         5. pool <- max(pool * (1 - Dry Rate * dt * 0.25), inc * flat * low)
            ("rainfx_pool") - fills instantly inside the footprint on flat
            up-facing low spots and lingers ~4x longer than surface wetness.
         6. snow <- min(snow + Snow Rate * dt * exp(-dist(v, flake) / radius)
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

Bake-safe: pure node logic, no Python handlers. The helper's sim cache is
independent of the rain cache (bake it the same way if you farm-render).
"""
from __future__ import annotations

import bpy

from .dsl import B

GROUP_NAME = "RainFX Wetness"
GROUP_VERSION = 3


def ensure_group() -> bpy.types.NodeTree:
    ng = bpy.data.node_groups.get(GROUP_NAME)
    if ng is not None and ng.get("rainfx_version") == GROUP_VERSION:
        return ng
    if ng is not None:
        bpy.data.node_groups.remove(ng)
    return build()


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

    def GI(name):
        return gi.outputs[name]

    gi = b.node("NodeGroupInput")
    go = b.node("NodeGroupOutput")

    # ------------------------------------------------------------- sim zone
    sim_in = b.node("GeometryNodeSimulationInput")
    sim_out = b.node("GeometryNodeSimulationOutput")
    sim_in.pair_with_output(sim_out)
    wet0 = b.store(GI("Geometry"), "rainfx_wet", 0.0, "FLOAT", domain="FACE")
    snow0 = b.store(wet0, "rainfx_snow", 0.0, "FLOAT", domain="POINT")
    b.links.new(snow0, sim_in.inputs["Geometry"])
    S0, dt = sim_in.outputs["Geometry"], sim_in.outputs["Delta Time"]

    # ------------------------------------------------- impacts from the emitter
    obj = b.node("GeometryNodeObjectInfo", transform_space="ORIGINAL")
    b.put(obj.inputs["Object"], GI("Emitter"))
    obj_comp = b.node("GeometryNodeSeparateComponents")
    b.links.new(obj.outputs["Geometry"], obj_comp.inputs["Geometry"])
    impacts = obj_comp.outputs["Mesh"]  # emitter-local hit vertices

    # ------------------------------------------------------- wetness update
    fpos = b.node("GeometryNodeInputPosition").outputs[0]  # face centre in this context
    prox = b.node("GeometryNodeProximity", target_element="POINTS")
    b.links.new(impacts, prox.inputs["Geometry"])
    b.put(prox.inputs["Sample Position"], fpos)
    rad = b.fm("MAXIMUM", GI("Wet Radius"), 0.001)
    footprint = b.fm("EXPONENT", b.fm("MULTIPLY", b.fm("DIVIDE", prox.outputs["Distance"], rad), -1.0))
    inc = b.fm("MULTIPLY", GI("Strength"), footprint)

    wet = b.attr("rainfx_wet")
    valid = prox.outputs["Is Valid"]  # empty impact stream must wet nothing
    decay = b.fm("SUBTRACT", 1.0, b.fm("MINIMUM", b.fm("MULTIPLY", GI("Dry Rate"), dt), 1.0))
    grown = b.fm("ADD", b.fm("MULTIPLY", wet, decay),
                 b.fm("MULTIPLY", b.fm("MULTIPLY", inc, valid), b.fm("SUBTRACT", 1.0, wet)))
    wet1 = b.store(S0, "rainfx_wet", b.fm("MINIMUM", grown, 1.0), "FLOAT", domain="FACE")

    # --------------------------------------- puddle pool (flat, low, up-facing)
    # height-based mask: normalized height over the object's own bbox; thin
    # flat colliders (range ~ 0) count as all-low so water collects everywhere
    nrm = b.node("GeometryNodeInputNormal").outputs[0]
    flat = b.fm("MAXIMUM", b.vdot(nrm, b.xyz(0.0, 0.0, 1.0)), 0.0)
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
    pool1 = b.store(wet1, "rainfx_pool", grown_p, "FLOAT", domain="FACE")

    # ------------------------------------------- snow accumulation (per-vertex)
    # flakes need their own ObjectInfo: a mesh input is not switchable per point,
    # and Is Valid on the snow stream is what keeps rain-only worlds inert
    sobj = b.node("GeometryNodeObjectInfo", transform_space="ORIGINAL")
    b.put(sobj.inputs["Object"], GI("Snow Impacts"))
    sobj_comp = b.node("GeometryNodeSeparateComponents")
    b.links.new(sobj.outputs["Geometry"], sobj_comp.inputs["Geometry"])
    flakes = sobj_comp.outputs["Mesh"]

    sprox = b.node("GeometryNodeProximity", target_element="POINTS")
    b.links.new(flakes, sprox.inputs["Geometry"])
    sfoot = b.fm("EXPONENT", b.fm("MULTIPLY", b.fm("DIVIDE", sprox.outputs["Distance"], rad), -1.0))
    # per-vertex: InputNormal is the vertex normal in point context, which is
    # exactly what Set Position needs afterwards
    sup = b.fm("MAXIMUM", b.vdot(nrm, b.xyz(0.0, 0.0, 1.0)), 0.0)
    sinc = b.fm("MULTIPLY", GI("Snow Rate"),
                b.fm("MULTIPLY", b.fm("MULTIPLY", sfoot, sup), sprox.outputs["Is Valid"]))
    snow = b.attr("rainfx_snow")
    grown_s = b.fm("MINIMUM", b.fm("ADD", snow, b.fm("MULTIPLY", sinc, dt)), 1.0)
    snow1 = b.store(pool1, "rainfx_snow", grown_s, "FLOAT", domain="POINT")
    b.links.new(snow1, sim_out.inputs["Geometry"])

    # ----------------------------------------- post-sim displacement (fresh)
    # every evaluation recomputes offset = normal * snow * depth from the state
    # attribute; the state itself never received displacement, so no feedback
    disp = b.vscale(nrm, b.fm("MULTIPLY", b.attr("rainfx_snow"), GI("Snow Depth")))
    lifted = b.set_position(sim_out.outputs["Geometry"], offset=disp)
    b.links.new(lifted, go.inputs["Geometry"])
    return ng
