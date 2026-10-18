"""Dew: static condensation beads on upward facing surfaces of the collider
collection. No simulation; density is per square metre of collider area."""
from __future__ import annotations

import bpy

from .dsl import B

GROUP_NAME = "RainFX Dew"
GROUP_VERSION = 1


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
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    b.add_input("Colliders", "NodeSocketCollection", desc="Surfaces that collect dew")
    b.add_input("Density", "NodeSocketFloat", 350.0, 0.0, 100000.0, desc="Beads per m2")
    b.add_input("D Min", "NodeSocketFloat", 0.4, 0.01, 20.0, desc="mm")
    b.add_input("D Max", "NodeSocketFloat", 2.2, 0.01, 20.0, desc="mm")
    b.add_input("Min Normal Z", "NodeSocketFloat", 0.35, -1.0, 1.0, desc="Only faces facing up")
    b.add_input("Flatten", "NodeSocketFloat", 0.65, 0.1, 1.0, desc="Bead height / width")
    b.add_input("Max Beads", "NodeSocketInt", 200000, 0, 5000000,
                desc="Safety cap: density is reduced so the total never exceeds this")
    b.add_input("Seed", "NodeSocketInt", 0, -100000, 100000)
    b.add_input("Bead Material", "NodeSocketMaterial")

    gi, go = b.node("NodeGroupInput"), b.node("NodeGroupOutput")
    GI = lambda n: gi.outputs[n]  # noqa: E731

    ci = b.node("GeometryNodeCollectionInfo", transform_space="RELATIVE")
    b.put(ci.inputs["Collection"], GI("Colliders"))
    real = b.node("GeometryNodeRealizeInstances")
    b.links.new(ci.outputs["Instances"], real.inputs["Geometry"])

    nz = b.sep(b.node("GeometryNodeInputNormal").outputs["Normal"])[2]
    dist = b.node("GeometryNodeDistributePointsOnFaces", distribute_method="RANDOM")
    b.links.new(real.outputs["Geometry"], dist.inputs["Mesh"])
    b.put(dist.inputs["Selection"], b.cmp("GREATER_EQUAL", nz, GI("Min Normal Z")))
    area = b.node("GeometryNodeInputMeshFaceArea").outputs["Area"]
    stat = b.node("GeometryNodeAttributeStatistic", data_type="FLOAT", domain="FACE")
    b.links.new(real.outputs["Geometry"], stat.inputs["Geometry"])
    b.put(b.sin(stat, "Attribute"), area)
    total_area = b.fm("MAXIMUM", stat.outputs["Sum"], 1e-4)
    b.put(dist.inputs["Density"], b.fm("MINIMUM", GI("Density"), b.fm("DIVIDE", GI("Max Beads"), total_area)))
    b.put(dist.inputs["Seed"], GI("Seed"))

    d = b.fm("MULTIPLY", b.rand(GI("D Min"), GI("D Max"), b.fm("ADD", GI("Seed"), 7)), 0.001)
    ico = b.node("GeometryNodeMeshIcoSphere")
    b.put(ico.inputs["Radius"], 0.5)
    b.put(ico.inputs["Subdivisions"], 2)
    mat = b.node("GeometryNodeSetMaterial")
    b.links.new(ico.outputs["Mesh"], mat.inputs["Geometry"])
    b.put(mat.inputs["Material"], GI("Bead Material"))
    inst = b.node("GeometryNodeInstanceOnPoints")
    b.links.new(dist.outputs["Points"], inst.inputs["Points"])
    b.put(inst.inputs["Instance"], mat.outputs["Geometry"])
    b.put(inst.inputs["Rotation"], dist.outputs["Rotation"])
    b.put(inst.inputs["Scale"], b.xyz(d, d, b.fm("MULTIPLY", d, GI("Flatten"))))
    lift = b.node("GeometryNodeTranslateInstances")
    b.links.new(inst.outputs["Instances"], lift.inputs["Instances"])
    b.put(lift.inputs["Translation"], b.xyz(0.0, 0.0, b.fm("MULTIPLY", b.fm("MULTIPLY", d, GI("Flatten")), 0.3)))
    b.put(lift.inputs["Local Space"], True)
    b.links.new(lift.outputs["Instances"], go.inputs["Geometry"])
    return ng
