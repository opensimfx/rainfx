"""'RainFX Distant': background drizzle layer far beyond the simulation box.

Roadmap: "Volumetric or screen-space far layer so the near-field simulation
can stay sparse" — this is the cheap geometry answer. The group is STATIC:
no simulation zone, no cache, no point state. The base scatter is generated
once inside the Points node's own position field, and the motion is a
uniform drift wrapped through the box by a per-axis FRACTION of Scene Time
seconds, so every frame's result is a pure function of that frame — replay
and bake safe by construction. Instances are realized into the output so
the evaluated geometry can be read back exactly as it renders, and the
'distant' material kind is a flat translucent streak without transmission,
keeping EEVEE cheap.
"""
from __future__ import annotations

import bpy

GROUP_NAME = "RainFX Distant"
GROUP_VERSION = 1


def ensure_group() -> bpy.types.NodeTree:
    ng = bpy.data.node_groups.get(GROUP_NAME)
    if ng is not None and ng.get("rainfx_version") == GROUP_VERSION:
        return ng
    if ng is not None:
        bpy.data.node_groups.remove(ng)
    return build()


def build() -> bpy.types.NodeTree:
    from .dsl import B

    ng = bpy.data.node_groups.new(GROUP_NAME, "GeometryNodeTree")
    ng["rainfx_version"] = GROUP_VERSION
    b = B(ng)
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

    # ---------------------------------------------------------------- INIT
    p = b.panel("Distant")
    b.add_input("Box Size", "NodeSocketVector", (48.0, 48.0, 20.0), parent=p,
                desc="Wrapping volume of the layer (local: XY centred, Z from 0)")
    b.add_input("Count", "NodeSocketInt", 8000, lo=0, hi=1000000, parent=p,
                desc="Streak count for the whole layer")
    b.add_input("Wind", "NodeSocketVector", (0.0, 0.0, 0.0), parent=p,
                desc="Lateral drift shared with the near simulation")
    b.add_input("Fall Speed", "NodeSocketFloat", 9.0, lo=0.1, hi=30.0, parent=p,
                desc="Vertical fall speed of the far drizzle (m/s)")
    b.add_input("Seed", "NodeSocketInt", 0, parent=p, desc="Scatter seed")
    b.add_input("Streak Scale", "NodeSocketFloat", 1.0, lo=0.05, hi=4.0, parent=p,
                desc="Overall size multiplier of the far streaks")
    b.add_input("Distant Material", "NodeSocketMaterial", parent=p,
                desc="Flat translucent streak material, wired automatically")

    gi = b.node("NodeGroupInput")
    go = b.node("NodeGroupOutput")

    def GI(name):
        return gi.outputs[name]

    box = GI("Box Size")
    rec = b.vm("MULTIPLY", box, (0.5, 0.5, 0.0))

    # static scatter: the Points node's position field freezes one random
    # spot per streak (XY over the wrapped box, Z over its full height), so
    # nothing exists to cache or replay.
    pts = b.node("GeometryNodePoints")
    b.put(pts.inputs["Count"], GI("Count"))
    base = b.vm("SUBTRACT",
                b.vm("MULTIPLY", b.rand((-0.5, -0.5, 0.0), (0.5, 0.5, 1.0),
                                        b.fm("ADD", GI("Seed"), 511), "FLOAT_VECTOR"), box), rec)
    b.put(pts.inputs["Position"], base)

    # -------------------------------------------------------- fall + wrap
    # velocity = (wind.xy, -fall); displacement over scene seconds, wrapped
    # by per-axis FRACTION. FRACTION maps negatives upward, X/Y re-centre
    # after the multiply and Z already spans 0..box — one wrap covers all.
    t = b.node("GeometryNodeInputSceneTime").outputs["Seconds"]
    vel = b.vm("ADD", b.vm("MULTIPLY", GI("Wind"), (1.0, 1.0, 0.0)),
               b.xyz(0.0, 0.0, b.fm("MULTIPLY", GI("Fall Speed"), -1.0)))
    shifted = b.vm("ADD", b.node("GeometryNodeInputPosition").outputs[0],
                   b.vm("MULTIPLY", vel, t))
    wrapped = b.vm("FRACTION", b.vm("DIVIDE", shifted, box))
    pos = b.vm("SUBTRACT", b.vm("MULTIPLY", wrapped, box), rec)
    loc = b.set_position(pts.outputs["Points"], position=pos)

    # ------------------------------------------------------------- LOOK
    # far streaks: fixed 4 mm-class columns, length bound by the fall speed
    # like a time exposure (snow presets fall slow and read as short dots)
    width = b.fm("MULTIPLY", GI("Streak Scale"), 0.008)
    length = b.fm("MAXIMUM", b.fm("MULTIPLY", GI("Fall Speed"),
                                  b.fm("MULTIPLY", GI("Streak Scale"), 0.12)), width)
    align = b.node("FunctionNodeAlignRotationToVector", axis="Z")
    b.put(b.sin(align, "Vector"), vel)

    cyl = b.node("GeometryNodeMeshCylinder")
    b.put(cyl.inputs["Vertices"], 6)
    b.put(cyl.inputs["Radius"], 0.5)
    b.put(cyl.inputs["Depth"], 1.0)
    setmat = b.node("GeometryNodeSetMaterial")
    b.links.new(cyl.outputs["Mesh"], setmat.inputs["Geometry"])
    b.put(setmat.inputs["Material"], GI("Distant Material"))
    inst = b.node("GeometryNodeInstanceOnPoints")
    b.links.new(loc, inst.inputs["Points"])
    b.put(inst.inputs["Instance"], setmat.outputs["Geometry"])
    b.put(inst.inputs["Rotation"], b.sout(align, "Rotation"))
    b.put(inst.inputs["Scale"], b.xyz(width, width, length))
    # realize: the far buffer is small and to_mesh/render should agree
    real = b.node("GeometryNodeRealizeInstances")
    b.links.new(inst.outputs["Instances"], real.inputs["Geometry"])
    b.links.new(real.outputs["Geometry"], go.inputs["Geometry"])
    return ng
