"""'RainFX Drips': drops falling from the edges of roofs, sills and lamp heads.

The modifier sits on the hidden "RainFX Drips" object, whose vertices are the
drip points found by scene/drips.py (one per DRIP_SPACING_M of dripping edge)
with three point attributes: "fall" (metres of open air below the point),
"period" (seconds between drops) and "phase" (0-1, desynchronises the points).

Everything is a pure function of Scene Time, like the distant layer: nothing
is simulated or cached, so scrubbing, baking and farm rendering agree.

Per point, k = t / period + phase. Six copies j = 0..5 stand for the drop
released j periods ago (tau = (fract(k) + j) * period), so a drop is still
falling while the next one forms. Each falls from rest to terminal speed
(core.physics.drip_fall: s = g tau^2 / 2 up to vt, then vt tau) and is
deleted once it has fallen "fall" metres. Falling drops are streaks
(length = speed x Shutter, like the rain); a bead hangs at the point and
grows from 35 % to full size until it lets go.
"""
from __future__ import annotations

import bpy

from ..core import physics as PH
from .dsl import B, ensure_versioned

GROUP_NAME = "RainFX Drips"
GROUP_VERSION = 1
COPIES = 6


def ensure_group() -> bpy.types.NodeTree:
    ng = bpy.data.node_groups.get(GROUP_NAME)
    if ng is not None and ng.get("rainfx_version") == GROUP_VERSION:
        return ng
    return ensure_versioned(ng, GROUP_NAME, build)


def build() -> bpy.types.NodeTree:
    ng = bpy.data.node_groups.new(GROUP_NAME, "GeometryNodeTree")
    ng["rainfx_version"] = GROUP_VERSION
    b = B(ng)
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    p = b.panel("Drips")
    b.add_input("Geometry", "NodeSocketGeometry", desc="Drip points (wired automatically)")
    b.add_input("Drop Diameter", "NodeSocketFloat", PH.DRIP_D_MM, 0.5, 20.0, p, "Detaching drop size (mm)")
    b.add_input("Terminal Speed", "NodeSocketFloat", 9.0, 0.5, 20.0, p, "Fall speed limit (m/s)")
    b.add_input("Shutter", "NodeSocketFloat", 1.0 / 48.0, 0.0, 1.0, p, "Streak length = speed x shutter (s)")
    b.add_input("Visual Scale", "NodeSocketFloat", 4.0, 0.1, 50.0, p,
                "Width exaggeration far from the camera (true size within 2 m)")
    b.add_input("Drip Material", "NodeSocketMaterial", parent=p, desc="Wired automatically")

    gi = b.node("NodeGroupInput")
    go = b.node("NodeGroupOutput")

    def GI(name):
        return gi.outputs[name]

    g = PH.G
    t = b.node("GeometryNodeInputSceneTime").outputs["Seconds"]
    period = b.fm("MAXIMUM", b.attr("period"), 0.05)
    k = b.fm("ADD", b.fm("DIVIDE", t, period), b.attr("phase"))
    cycle = b.fm("FRACT", k)
    diam = b.fm("MULTIPLY", GI("Drop Diameter"), 0.001)

    # size on screen: true size near the camera, Visual Scale far away (as precip.py)
    cam_oi = b.node("GeometryNodeObjectInfo", transform_space="RELATIVE")
    b.links.new(b.node("GeometryNodeInputActiveCamera").outputs[0], cam_oi.inputs["Object"])
    cam_d = b.vlen(b.vm("SUBTRACT", b.node("GeometryNodeInputPosition").outputs[0], cam_oi.outputs["Location"]))
    vis = b.fm("MINIMUM", b.fm("MAXIMUM", b.fm("DIVIDE", cam_d, PH.VISUAL_SCALE_NEAR_M), 1.0), GI("Visual Scale"))

    # ------------------------------------------------------------ falling drops
    dup = b.node("GeometryNodeDuplicateElements", domain="POINT")
    b.links.new(GI("Geometry"), dup.inputs["Geometry"])
    b.put(dup.inputs["Amount"], COPIES)
    tau = b.fm("MULTIPLY", b.fm("ADD", cycle, dup.outputs["Duplicate Index"]), period)
    vt = b.fm("MAXIMUM", GI("Terminal Speed"), 0.1)
    t_v = b.fm("DIVIDE", vt, g)
    s_free = b.fm("MULTIPLY", 0.5 * g, b.fm("MULTIPLY", tau, tau))
    s_term = b.fm("ADD", b.fm("MULTIPLY", b.fm("MULTIPLY", 0.5, vt), t_v),
                  b.fm("MULTIPLY", vt, b.fm("SUBTRACT", tau, t_v)))
    early = b.fm("LESS_THAN", tau, t_v)
    dist = b.fm("ADD", b.fm("MULTIPLY", early, s_free), b.fm("MULTIPLY", b.fm("SUBTRACT", 1.0, early), s_term))
    speed = b.fm("MINIMUM", b.fm("MULTIPLY", g, tau), vt)
    gone = b.fm("GREATER_THAN", dist, b.fm("SUBTRACT", b.attr("fall"), 0.02))
    falling = b.set_position(dup.outputs["Geometry"], offset=b.xyz(0.0, 0.0, b.fm("MULTIPLY", dist, -1.0)))
    falling = b.delete(falling, gone)

    width = b.fm("MULTIPLY", diam, vis)
    length = b.fm("MAXIMUM", b.fm("MULTIPLY", speed, GI("Shutter")), width)
    cyl = b.node("GeometryNodeMeshCylinder")
    b.put(cyl.inputs["Vertices"], 6)
    b.put(cyl.inputs["Radius"], 0.5)
    b.put(cyl.inputs["Depth"], 1.0)
    mat1 = b.node("GeometryNodeSetMaterial")
    b.links.new(cyl.outputs["Mesh"], mat1.inputs["Geometry"])
    b.put(mat1.inputs["Material"], GI("Drip Material"))
    inst = b.node("GeometryNodeInstanceOnPoints")
    b.links.new(falling, inst.inputs["Points"])
    b.put(inst.inputs["Instance"], mat1.outputs["Geometry"])
    b.put(inst.inputs["Scale"], b.xyz(width, width, length))

    # ------------------------------------------------------------ hanging beads
    bead_r = b.fm("MULTIPLY", b.fm("MULTIPLY", diam, vis), b.fm("MULTIPLY_ADD", cycle, 0.65, 0.35))
    beads = b.set_position(GI("Geometry"), offset=b.xyz(0.0, 0.0, b.fm("MULTIPLY", bead_r, -0.5)))
    ico = b.node("GeometryNodeMeshIcoSphere")
    b.put(ico.inputs["Radius"], 0.5)
    b.put(ico.inputs["Subdivisions"], 2)
    mat2 = b.node("GeometryNodeSetMaterial")
    b.links.new(ico.outputs["Mesh"], mat2.inputs["Geometry"])
    b.put(mat2.inputs["Material"], GI("Drip Material"))
    inst2 = b.node("GeometryNodeInstanceOnPoints")
    b.links.new(beads, inst2.inputs["Points"])
    b.put(inst2.inputs["Instance"], mat2.outputs["Geometry"])
    b.put(inst2.inputs["Scale"], b.xyz(bead_r, bead_r, b.fm("MULTIPLY", bead_r, 1.25)))

    b.links.new(b.join(inst.outputs["Instances"], inst2.outputs["Instances"]), go.inputs["Geometry"])
    return ng
