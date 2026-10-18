"""Procedural precipitation: rain, hail, snow in one Geometry Nodes group.

Pipeline (see docs/SYSTEM_DESIGN.md):

  INIT   Points in a box -> diameter (truncated exponential / Marshall-Palmer),
         terminal speed vt(D, mode), relaxation time tau, initial velocity.
         +-Z ray-parity against the colliders removes start points inside
         enclosed volumes.
  SIM    per step (Simulation Zone, dt from Delta Time):
           1. split primaries / splash droplets
           2. primaries: v <- v_target + (v - v_target) exp(-dt / tau)
                         v_target = wind + gust(noise) + (0, 0, -vt)
           3. Raycast along the step against a velocity-annotated copy of the
              Colliders collection, sampling "rainfx_velocity" at the hit
              hit -> bounce (hail) | land+recycle (rain, snow) [+ splash spawn]
           4. wrap horizontally in the box, recycle below the floor
           5. splash droplets: ballistic, aged, deleted at end of life
  OUTPUT instances aligned to velocity, stretched by shutter time (streaks),
         or raw vertices for debugging / custom instancing.

  All positions are world-space numbers inside the graph; the sim box base
  sits at the Follow Object's location (or the emitter if no object is set).
  One world->local Set Position on the sim state (subtracting the emitter's
  world location) runs just before the OUTPUT stage, so Blender's object
  transform of the emitter cannot move the rain at render time.

  Collider motion is derived inside the graph: each step joins the realized
  collider mesh back into the sim state (kind = 2 marker) and computes its
  per-vertex velocity against the previous step's copy by nearest-point
  match (Geometry Proximity), v = (pos - nearest_prev) / dt. Robust to
  vertex order and topology changes; per-frame world motion, translation
  dominant for rigid moves.

Fields are always evaluated on the *unmodified* geometry and frozen with a
Capture Attribute node before positions or velocities are changed. Reading a
field after Set Position would silently use the new position.
"""
from __future__ import annotations

import bpy

from .dsl import B

GROUP_NAME = "RainFX Precipitation"
GROUP_VERSION = 4
E = 2.718281828459045


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

    # ------------------------------------------------------------ interface
    p = b.panel("Setup")
    b.add_input("Colliders", "NodeSocketCollection", parent=p,
                desc="Objects the precipitation collides with (raycast)")
    b.add_input("Mode", "NodeSocketInt", 0, 0, 2, p, "0 rain, 1 hail, 2 snow")
    b.add_input("Seed", "NodeSocketInt", 0, -100000, 100000, p)
    b.add_input("Box Size", "NodeSocketVector", (16.0, 16.0, 10.0), parent=p,
                desc="Simulation volume in metres; wraps horizontally")
    b.add_input("Follow Object", "NodeSocketObject", parent=p,
                desc="Volume base follows this object's world location (the emitter itself when empty)")
    b.add_input("Origin Offset", "NodeSocketVector", (0.0, 0.0, 0.0), parent=p,
                desc="World offset of the volume base from the follow point; for a camera try Z = -half height")
    b.add_input("Count", "NodeSocketInt", 20000, 0, 2000000, p)
    b.add_input("Viewport Density", "NodeSocketFloat", 0.3, 0.0, 1.0, p,
                "Fraction of particles drawn in the viewport")
    b.add_input("Output Mode", "NodeSocketInt", 0, 0, 1, p, "0 instances, 1 raw vertices")

    p = b.panel("Population")
    b.add_input("D Min", "NodeSocketFloat", 0.3, 0.01, 100.0, p, "Smallest diameter (mm)")
    b.add_input("D Max", "NodeSocketFloat", 4.0, 0.01, 100.0, p, "Largest diameter (mm)")
    b.add_input("Lambda", "NodeSocketFloat", 2.5, 0.01, 20.0, p,
                "Exponential slope (1/mm); Marshall-Palmer for rain")
    b.add_input("Speed Scale", "NodeSocketFloat", 1.0, 0.0, 5.0, p)
    b.add_input("Snow Speed", "NodeSocketFloat", 1.0, 0.1, 5.0, p, "Base snow fall speed (m/s)")

    p = b.panel("Air")
    b.add_input("Wind", "NodeSocketVector", (0.0, 0.0, 0.0), parent=p, desc="m/s")
    b.add_input("Gust Strength", "NodeSocketFloat", 0.0, 0.0, 50.0, p)
    b.add_input("Gust Scale", "NodeSocketFloat", 6.0, 0.1, 100.0, p)
    b.add_input("Gust Speed", "NodeSocketFloat", 2.0, 0.0, 50.0, p)
    b.add_input("Inertia", "NodeSocketFloat", 1.0, 0.05, 10.0, p, "Multiplies relaxation time vt/g")

    p = b.panel("Impact")
    b.add_input("Restitution", "NodeSocketFloat", 0.0, 0.0, 1.0, p, ">0 bounces (hail)")
    b.add_input("Max Bounces", "NodeSocketInt", 0, 0, 20, p)
    b.add_input("Collider Push", "NodeSocketFloat", 1.0, 0.0, 2.0, p,
                "Share of the collider's motion (rainfx_velocity attribute) that moving colliders give to splashes and bounces")
    b.add_input("Splash Amount", "NodeSocketInt", 2, 0, 12, p)
    b.add_input("Splash Speed", "NodeSocketFloat", 1.2, 0.0, 20.0, p)
    b.add_input("Splash Life Min", "NodeSocketFloat", 0.15, 0.01, 5.0, p)
    b.add_input("Splash Life Max", "NodeSocketFloat", 0.4, 0.01, 5.0, p)
    b.add_input("Splash Size", "NodeSocketFloat", 0.35, 0.01, 2.0, p)
    b.add_input("Gravity", "NodeSocketFloat", 9.80665, 0.0, 50.0, p)

    p = b.panel("Look")
    b.add_input("Shutter", "NodeSocketFloat", 1 / 48, 0.0, 1.0, p, "Streak length = speed x shutter; 0 = spheres")
    b.add_input("Visual Scale", "NodeSocketFloat", 4.0, 0.1, 50.0, p, "Exaggerates sub-pixel drops")
    b.add_input("Drop Material", "NodeSocketMaterial", parent=p)
    b.add_input("Splash Material", "NodeSocketMaterial", parent=p)

    gi = b.node("NodeGroupInput")
    go = b.node("NodeGroupOutput")

    def GI(n):
        return gi.outputs[n]

    box, wind, seed = GI("Box Size"), GI("Wind"), GI("Seed")
    g = GI("Gravity")
    hx, hy, hz = b.sep(b.vscale(box, 0.5))

    # -------------------------------------------------------- volume origin
    self_obj = b.node("GeometryNodeSelfObject")
    oi_self = b.node("GeometryNodeObjectInfo", transform_space="ORIGINAL")
    b.put(oi_self.inputs["Object"], self_obj.outputs[0])
    follow_oi = b.node("GeometryNodeObjectInfo", transform_space="ORIGINAL")
    b.put(follow_oi.inputs["Object"], GI("Follow Object"))
    origin = b.vm("ADD", follow_oi.outputs["Location"], GI("Origin Offset"))
    ox, oy, oz = b.sep(origin)

    # ------------------------------------------------------------- colliders
    ci = b.node("GeometryNodeCollectionInfo", transform_space="ORIGINAL")
    b.put(ci.inputs["Collection"], GI("Colliders"))
    colliders = b.node("GeometryNodeRealizeInstances")
    b.links.new(ci.outputs["Instances"], colliders.inputs["Geometry"])
    collider_geo = colliders.outputs["Geometry"]

    # ----------------------------------------------------------------- INIT
    vp = b.node("GeometryNodeIsViewport").outputs[0]
    vp_factor = b.fm("MULTIPLY_ADD", vp, b.fm("SUBTRACT", GI("Viewport Density"), 1.0), 1.0)
    count = b.fm("MULTIPLY", GI("Count"), vp_factor)
    pts = b.node("GeometryNodePoints")
    b.put(pts.inputs["Count"], count)
    pmin = b.vm("MULTIPLY", box, (-0.5, -0.5, 0.0))
    pmax = b.vm("MULTIPLY", box, (0.5, 0.5, 1.0))
    b.put(pts.inputs["Position"], b.vm("ADD", b.rand(pmin, pmax, b.fm("ADD", seed, 1), "FLOAT_VECTOR"), origin))

    lam = b.fm("MAXIMUM", GI("Lambda"), 0.01)
    dmin, dmax = GI("D Min"), GI("D Max")
    u = b.rand(0.0, 1.0, b.fm("ADD", seed, 11))
    span = b.fm("SUBTRACT", 1.0, b.fm("EXPONENT", b.fm("MULTIPLY", lam, b.fm("SUBTRACT", dmin, dmax))))
    arg = b.fm("MAXIMUM", b.fm("SUBTRACT", 1.0, b.fm("MULTIPLY", u, span)), 1e-6)
    diam = b.fm("SUBTRACT", dmin, b.fm("DIVIDE", b.fm("LOGARITHM", arg, E), lam))

    mode = GI("Mode")
    m0, m1, m2 = (b.fm("COMPARE", mode, float(i), 0.5) for i in range(3))
    v_atlas = b.fm("SUBTRACT", 9.65, b.fm("MULTIPLY", 10.3, b.fm(
        "EXPONENT", b.fm("MULTIPLY", -0.6, b.fm("MINIMUM", diam, 8.0)))))
    v_small = b.fm("MULTIPLY", 0.27, b.fm("POWER", b.fm("DIVIDE", diam, 0.1), 1.25))
    w_small = b.fm("LESS_THAN", diam, 0.5)
    vt_rain = b.fm("ADD", b.fm("MULTIPLY", w_small, v_small),
                   b.fm("MULTIPLY", b.fm("SUBTRACT", 1.0, w_small), v_atlas))
    vt_hail = b.fm("MULTIPLY", 0.85 * 9.0, b.fm(
        "POWER", b.fm("DIVIDE", b.fm("MINIMUM", diam, 80.0), 10.0), 0.8))
    vt_snow = b.fm("MULTIPLY", GI("Snow Speed"), b.fm(
        "ADD", 0.85, b.fm("MULTIPLY", 0.03, b.fm("MINIMUM", diam, 10.0))))
    vt = b.fm("MAXIMUM", b.fm("MULTIPLY", GI("Speed Scale"), b.fm(
        "ADD", b.fm("MULTIPLY", m0, vt_rain), b.fm("ADD", b.fm("MULTIPLY", m1, vt_hail),
                                                   b.fm("MULTIPLY", m2, vt_snow)))), 0.05)
    tau = b.fm("MULTIPLY", b.fm("MAXIMUM", b.fm("DIVIDE", vt, g), 0.02), GI("Inertia"))
    vel0 = b.vm("ADD", wind, b.xyz(0.0, 0.0, b.fm("MULTIPLY", vt, -1.0)))

    geo = pts.outputs["Points"]
    for name, val, dt in (("diameter", diam, "FLOAT"), ("vt", vt, "FLOAT"), ("tau", tau, "FLOAT"),
                          ("velocity", vel0, "FLOAT_VECTOR"), ("kind", 0.0, "FLOAT"),
                          ("age", 0.0, "FLOAT"), ("life", 0.0, "FLOAT"), ("bounces", 0.0, "FLOAT")):
        geo = b.store(geo, name, val, dt)

    # reject start points inside a collider: a +-Z ray-parity test - a point
    # in an enclosed volume gets Is Hit in both directions (open-top shapes
    # like cups stay undetected; respawned points are never re-checked)
    in_pos = b.node("GeometryNodeInputPosition").outputs[0]
    up_hit = down_hit = None
    for direction in ((0.0, 0.0, 1.0), (0.0, 0.0, -1.0)):
        rc = b.node("GeometryNodeRaycast", data_type="FLOAT")
        b.put(rc.inputs["Target Geometry"], collider_geo)
        b.put(rc.inputs["Source Position"], in_pos)
        b.put(rc.inputs["Ray Direction"], direction)
        b.put(rc.inputs["Ray Length"], 100.0)
        is_hit = rc.outputs["Is Hit"]
        if up_hit is None:
            up_hit = is_hit
        else:
            down_hit = is_hit
    inside = b.node("FunctionNodeBooleanMath", operation="AND")
    b.put(inside.inputs[0], up_hit)
    b.put(inside.inputs[1], down_hit)
    geo = b.delete(geo, inside.outputs["Boolean"])

    # ------------------------------------------------------------------ SIM
    sim_in = b.node("GeometryNodeSimulationInput")
    sim_out = b.node("GeometryNodeSimulationOutput")
    sim_in.pair_with_output(sim_out)
    # a copy of the realized colliders rides inside the sim state as a mesh
    # component (kind = 2) so per-step collider velocities can be derived
    # in-graph and survive bakes; zeroed velocity makes step 1 yield exactly 0
    snap0 = b.store(collider_geo, "kind", 2.0, "FLOAT")
    snap0 = b.store(snap0, "rainfx_velocity", (0.0, 0.0, 0.0), "FLOAT_VECTOR")
    b.links.new(b.join(geo, snap0), sim_in.inputs["Geometry"])
    G0, dt = sim_in.outputs["Geometry"], sim_in.outputs["Delta Time"]

    kind = b.attr("kind")
    g0_comp = b.node("GeometryNodeSeparateComponents")
    b.links.new(G0, g0_comp.inputs["Geometry"])
    prev_snap = g0_comp.outputs["Mesh"]
    G0_pts = g0_comp.outputs["Point Cloud"]
    P0, S0 = b.separate(G0_pts, b.cmp("LESS_THAN", kind, 0.5))

    # --- fields on primaries --------------------------------------------
    pos = b.node("GeometryNodeInputPosition").outputs[0]
    vel, vtA, tauA = b.attr("velocity", "FLOAT_VECTOR"), b.attr("vt"), b.attr("tau")
    D, nb = b.attr("diameter"), b.attr("bounces")
    stime = b.node("GeometryNodeInputSceneTime")
    t_sec, frame = stime.outputs["Seconds"], stime.outputs["Frame"]

    gscale = b.fm("MAXIMUM", GI("Gust Scale"), 0.1)
    drift = b.xyz(b.fm("MULTIPLY", t_sec, GI("Gust Speed")),
                  b.fm("MULTIPLY", t_sec, b.fm("MULTIPLY", GI("Gust Speed"), 0.37)), 0.0)
    noise = b.node("ShaderNodeTexNoise", noise_dimensions="3D")
    b.put(noise.inputs["Vector"], b.vm("ADD", b.vscale(pos, b.fm("DIVIDE", 1.0, gscale)), drift))
    b.put(noise.inputs["Scale"], 1.0)
    b.put(noise.inputs["Detail"], 1.0)
    gust = b.vscale(b.vm("MULTIPLY", b.vm("SUBTRACT", noise.outputs["Color"], (0.5, 0.5, 0.5)),
                         (2.0, 2.0, 0.6)), GI("Gust Strength"))

    target = b.vm("ADD", b.vm("ADD", wind, gust), b.xyz(0.0, 0.0, b.fm("MULTIPLY", vtA, -1.0)))
    decay = b.fm("EXPONENT", b.fm("MULTIPLY", -1.0, b.fm("DIVIDE", dt, tauA)))
    vnew = b.vm("ADD", target, b.vscale(b.vm("SUBTRACT", vel, target), decay))
    speed = b.vlen(vnew)
    ray_len = b.fm("ADD", b.fm("MULTIPLY", speed, dt), b.fm("MULTIPLY", D, 0.0005))

    # collider velocity from the state snapshot: v = (pos - nearest prev pos)
    # / dt matched by Geometry Proximity (independent of vertex order, so
    # deformed or reordered colliders still work)
    samp_pos = b.node("GeometryNodeInputPosition").outputs[0]
    prox = b.node("GeometryNodeProximity", target_element="POINTS")
    b.links.new(prev_snap, prox.inputs["Geometry"])
    b.put(prox.inputs["Sample Position"], samp_pos)
    dt_safe = b.fm("MAXIMUM", dt, 0.001)
    collider_vel = b.store(collider_geo, "rainfx_velocity",
                           b.vscale(b.vm("SUBTRACT", samp_pos, prox.outputs["Position"]),
                                    b.fm("DIVIDE", 1.0, dt_safe)), "FLOAT_VECTOR")
    collider_vel = b.store(collider_vel, "kind", 2.0, "FLOAT")

    ray = b.node("GeometryNodeRaycast", data_type="FLOAT_VECTOR")
    b.put(ray.inputs["Target Geometry"], collider_vel)
    b.put(ray.inputs["Source Position"], pos)
    b.put(ray.inputs["Ray Direction"], b.vm("NORMALIZE", vnew))
    b.put(ray.inputs["Ray Length"], ray_len)
    # collider motion sampled on the target at the hit point (0 when the
    # attribute is missing -> static colliders behave exactly as before)
    push = GI("Collider Push")
    col_vel = b.vscale(b.attr("rainfx_velocity", "FLOAT_VECTOR"), push)
    b.put(ray.inputs["Attribute"], col_vel)
    is_hit, hit_pos, hit_n = ray.outputs["Is Hit"], ray.outputs["Hit Position"], ray.outputs["Hit Normal"]
    cvel = ray.outputs["Attribute"]

    rest, maxb = GI("Restitution"), GI("Max Bounces")
    can_bounce = b.bool("AND", b.cmp("GREATER_THAN", rest, 0.0), b.cmp("LESS_THAN", nb, maxb))
    do_bounce = b.bool("AND", is_hit, can_bounce)
    do_land = b.bool("AND", is_hit, b.bool("NOT", can_bounce))
    free_pos = b.vm("ADD", pos, b.vscale(vnew, dt))
    below = b.cmp("LESS_THAN", b.sep(free_pos)[2], oz)
    recycle = b.bool("OR", do_land, b.bool("AND", below, b.bool("NOT", is_hit)))

    # reflect off the collider in ITS frame (v - collider velocity), then shift
    # the result back to world space; equals the old formula when cvel = 0
    v_rel = b.vm("SUBTRACT", vnew, cvel)
    vn_rel = b.vscale(hit_n, b.vdot(v_rel, hit_n))
    v_bounce = b.vm("ADD",
                    b.vm("SUBTRACT", b.vscale(b.vm("SUBTRACT", v_rel, vn_rel), 0.85), b.vscale(vn_rel, rest)),
                    cvel)
    bounce_pos = b.vm("ADD", hit_pos, b.vscale(hit_n, 0.003))

    rseed = b.fm("ADD", b.fm("MULTIPLY", frame, 3.0), seed)
    rmin = b.vm("MULTIPLY", box, (-0.5, -0.5, 0.92))
    rmax = b.vm("MULTIPLY", box, (0.5, 0.5, 1.0))
    respawn_pos = b.vm("ADD", b.rand(rmin, rmax, b.fm("ADD", rseed, 101), "FLOAT_VECTOR"), origin)
    respawn_vel = b.vm("ADD", wind, b.xyz(0.0, 0.0, b.fm("MULTIPLY", vtA, -1.0)))

    pos_a = b.mix(do_bounce, free_pos, bounce_pos)
    pos_f = b.mix(recycle, pos_a, respawn_pos)
    vel_a = b.mix(do_bounce, vnew, v_bounce)
    vel_f = b.mix(recycle, vel_a, respawn_vel)
    wrapped = b.vm("WRAP", pos_f, b.vm("ADD", b.xyz(hx, hy, 1.0e6), origin),
                   b.vm("ADD", b.xyz(b.fm("MULTIPLY", hx, -1.0), b.fm("MULTIPLY", hy, -1.0), -1.0e6), origin))
    nb_new = b.fm("MULTIPLY", b.fm("SUBTRACT", 1.0, recycle), b.fm("ADD", nb, do_bounce))
    spawn = b.bool("AND", do_land, b.bool("AND", b.cmp("EQUAL", mode, 0, "INT"),
                                          b.cmp("GREATER_THAN", GI("Splash Amount"), 0, "INT")))

    # --- freeze every field before touching the geometry ---------------------
    cap = b.node("GeometryNodeCaptureAttribute")
    items = (("n_pos", "VECTOR", wrapped), ("n_vel", "VECTOR", vel_f), ("n_b", "FLOAT", nb_new),
             ("hp", "VECTOR", hit_pos), ("hn", "VECTOR", hit_n), ("v_in", "VECTOR", vnew),
             ("cv", "VECTOR", cvel), ("spawn", "BOOLEAN", spawn))
    for name, st, val in items:
        cap.capture_items.new(st, name)
        b.put(b.sin(cap, name), val)
    b.links.new(P0, cap.inputs["Geometry"])
    Pc = cap.outputs["Geometry"]
    C = {name: b.sout(cap, name) for name, _, _ in items}

    P1 = b.set_position(Pc, position=C["n_pos"])
    P1 = b.store(P1, "velocity", C["n_vel"], "FLOAT_VECTOR")
    P1 = b.store(P1, "bounces", C["n_b"], "FLOAT")

    # --- splash spawn --------------------------------------------------------
    src, _ = b.separate(Pc, C["spawn"])
    dup = b.node("GeometryNodeDuplicateElements", domain="POINT")
    b.links.new(src, dup.inputs["Geometry"])
    b.put(dup.inputs["Amount"], GI("Splash Amount"))
    SP = dup.outputs["Geometry"]

    r1 = b.rand(0.0, 1.0, b.fm("ADD", rseed, 201))
    r2 = b.rand(0.0, 1.0, b.fm("ADD", rseed, 202))
    r3 = b.rand(0.0, 1.0, b.fm("ADD", rseed, 203))
    rv = b.rand((-1.0, -1.0, -1.0), (1.0, 1.0, 1.0), b.fm("ADD", rseed, 301), "FLOAT_VECTOR")
    n_ = C["hn"]
    r_tan = b.vm("SUBTRACT", rv, b.vscale(n_, b.vdot(rv, n_)))
    d_out = b.vm("NORMALIZE", b.vm("ADD", b.vscale(n_, b.fm("MULTIPLY_ADD", r1, 0.8, 0.6)), r_tan))
    sp_speed = b.fm("MULTIPLY", b.fm("MULTIPLY", GI("Splash Speed"), b.fm("MULTIPLY_ADD", r2, 1.2, 0.4)),
                    b.fm("MINIMUM", b.fm("MAXIMUM", b.fm("DIVIDE", D, 2.0), 0.5), 2.0))
    sp_vel = b.vm("ADD", b.vscale(d_out, sp_speed),
                  b.vm("ADD", b.vscale(wind, 0.2), C["cv"]))
    life = b.rand(GI("Splash Life Min"), GI("Splash Life Max"), b.fm("ADD", rseed, 401))
    sp_d = b.fm("MULTIPLY", b.fm("MULTIPLY", D, GI("Splash Size")), b.fm("MULTIPLY_ADD", r3, 0.8, 0.4))

    SP = b.set_position(SP, position=b.vm("ADD", C["hp"], b.vscale(n_, 0.004)))
    SP = b.store(SP, "velocity", sp_vel, "FLOAT_VECTOR")
    SP = b.store(SP, "life", life)
    SP = b.store(SP, "diameter", sp_d)
    SP = b.store(SP, "kind", 1.0)
    SP = b.store(SP, "age", 0.0)

    # --- splash update (ballistic) --------------------------------------------
    SJ = b.join(S0, SP)
    sv = b.attr("velocity", "FLOAT_VECTOR")
    sv_new = b.vm("ADD", sv, b.xyz(0.0, 0.0, b.fm("MULTIPLY", g, b.fm("MULTIPLY", dt, -1.0))))
    spos = b.node("GeometryNodeInputPosition").outputs[0]
    SJ = b.set_position(SJ, position=b.vm("ADD", spos, b.vscale(sv_new, dt)))
    SJ = b.store(SJ, "velocity", sv_new, "FLOAT_VECTOR")
    age = b.attr("age")
    SJ = b.store(SJ, "age", b.fm("ADD", age, dt))
    SJ = b.delete(SJ, b.cmp("GREATER_THAN", b.attr("age"), b.attr("life")))

    b.links.new(b.join(P1, SJ, collider_vel), sim_out.inputs["Geometry"])
    state = sim_out.outputs["Geometry"]

    # drop the collider snapshot mesh component, then world -> emitter-local:
    # the sim carried world-space position numbers, the object renders in its
    # own space (emitter is a single-vertex point, identity rotation/scale).
    state_comp = b.node("GeometryNodeSeparateComponents")
    b.links.new(state, state_comp.inputs["Geometry"])
    local_pos = b.node("GeometryNodeInputPosition").outputs[0]
    state_pts = b.set_position(state_comp.outputs["Point Cloud"],
                               position=b.vm("SUBTRACT", local_pos, oi_self.outputs["Location"]))

    # --------------------------------------------------------------- OUTPUT
    prim, spl = b.separate(state_pts, b.cmp("LESS_THAN", b.attr("kind"), 0.5))
    pv = b.attr("velocity", "FLOAT_VECTOR")
    pd = b.attr("diameter")
    width = b.fm("MULTIPLY", b.fm("MULTIPLY", pd, 0.001), GI("Visual Scale"))
    length = b.fm("MAXIMUM", b.fm("MULTIPLY", b.vlen(pv), GI("Shutter")), width)
    align = b.node("FunctionNodeAlignRotationToVector", axis="Z")
    b.put(b.sin(align, "Vector"), pv)

    cyl = b.node("GeometryNodeMeshCylinder")
    b.put(cyl.inputs["Vertices"], 6)
    b.put(cyl.inputs["Radius"], 0.5)
    b.put(cyl.inputs["Depth"], 1.0)
    ico = b.node("GeometryNodeMeshIcoSphere")
    b.put(ico.inputs["Radius"], 0.5)
    b.put(ico.inputs["Subdivisions"], 1)
    shape = b.switch_geo(b.cmp("GREATER_THAN", GI("Shutter"), 0.0001), ico.outputs["Mesh"], cyl.outputs["Mesh"])
    drop_mat = b.node("GeometryNodeSetMaterial")
    b.links.new(shape, drop_mat.inputs["Geometry"])
    b.put(drop_mat.inputs["Material"], GI("Drop Material"))
    inst = b.node("GeometryNodeInstanceOnPoints")
    b.links.new(prim, inst.inputs["Points"])
    b.put(inst.inputs["Instance"], drop_mat.outputs["Geometry"])
    b.put(inst.inputs["Rotation"], b.sout(align, "Rotation"))
    b.put(inst.inputs["Scale"], b.xyz(width, width, length))

    sw = b.fm("MULTIPLY", b.fm("MULTIPLY", b.attr("diameter"), 0.001), GI("Visual Scale"))
    ico2 = b.node("GeometryNodeMeshIcoSphere")
    b.put(ico2.inputs["Radius"], 0.5)
    b.put(ico2.inputs["Subdivisions"], 1)
    spl_mat = b.node("GeometryNodeSetMaterial")
    b.links.new(ico2.outputs["Mesh"], spl_mat.inputs["Geometry"])
    b.put(spl_mat.inputs["Material"], GI("Splash Material"))
    inst2 = b.node("GeometryNodeInstanceOnPoints")
    b.links.new(spl, inst2.inputs["Points"])
    b.put(inst2.inputs["Instance"], spl_mat.outputs["Geometry"])
    b.put(inst2.inputs["Scale"], b.xyz(sw, sw, sw))

    rendered = b.join(inst.outputs["Instances"], inst2.outputs["Instances"])
    pv1 = b.node("GeometryNodePointsToVertices")
    b.links.new(prim, pv1.inputs["Points"])
    pv2 = b.node("GeometryNodePointsToVertices")
    b.links.new(spl, pv2.inputs["Points"])
    verts = b.join(pv1.outputs["Mesh"], pv2.outputs["Mesh"])
    final = b.switch_geo(b.cmp("EQUAL", GI("Output Mode"), 0, "INT"), verts, rendered)
    b.links.new(final, go.inputs["Geometry"])
    return ng
