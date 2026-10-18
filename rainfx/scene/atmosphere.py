"""Fog volume + sky/sun dimming. Everything reversible: original values are
stored as custom properties on the datablocks that were modified."""
from __future__ import annotations

import bpy

from .. import compat
from . import emitter as em

FOG_NAME = "RainFX Fog"
_KEY = "rainfx_orig"


def _fog_material() -> bpy.types.Material:
    mat = bpy.data.materials.get(FOG_NAME)
    if mat is not None:
        return mat
    mat = compat.new_material(FOG_NAME)
    nt = mat.node_tree
    for n in list(nt.nodes):
        if n.type == "BSDF_PRINCIPLED":
            nt.nodes.remove(n)
    out = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"), None) or nt.nodes.new("ShaderNodeOutputMaterial")
    vol = nt.nodes.new("ShaderNodeVolumeScatter")
    nt.links.new(vol.outputs["Volume"], out.inputs["Volume"])
    return mat


def create_fog(scene: bpy.types.Scene, box=(16.0, 16.0, 10.0), density: float = 0.01,
               anisotropy: float = 0.3, location=(0.0, 0.0, 0.0)) -> bpy.types.Object:
    obj = bpy.data.objects.get(FOG_NAME)
    if obj is None:
        mesh = bpy.data.meshes.new(FOG_NAME)
        h = 0.5
        v = [(x, y, z) for x in (-h, h) for y in (-h, h) for z in (0.0, 1.0)]
        f = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
        mesh.from_pydata(v, [], f)
        mesh.validate()
        obj = bpy.data.objects.new(FOG_NAME, mesh)
        em.ensure_collection(scene, em.ROOT_NAME).objects.link(obj)
        obj.display_type = "BOUNDS"
        obj.visible_shadow = False
        obj.data.materials.append(_fog_material())
    obj.location = location
    obj.scale = tuple(box)
    set_fog(obj, density, anisotropy)
    return obj


def set_fog(obj: bpy.types.Object, density: float, anisotropy: float = 0.3) -> None:
    mat = obj.data.materials[0] if obj.data.materials else _fog_material()
    for n in mat.node_tree.nodes:
        if n.type == "VOLUME_SCATTER":
            n.inputs["Density"].default_value = density
            n.inputs["Anisotropy"].default_value = anisotropy


def _background_nodes(scene):
    w = scene.world
    if w is None or w.node_tree is None:
        return []
    return [n for n in w.node_tree.nodes if n.type == "BACKGROUND"]


def apply_lighting(scene: bpy.types.Scene, sky_mult: float, sun_mult: float) -> None:
    """Scale world background strength and every SUN light (idempotent: scales
    from the stored original, not from the current value)."""
    for n in _background_nodes(scene):
        sock = n.inputs["Strength"]
        if _KEY not in n:
            n[_KEY] = sock.default_value
        sock.default_value = n[_KEY] * sky_mult
    for ob in scene.objects:
        if ob.type == "LIGHT" and ob.data.type == "SUN":
            if _KEY not in ob.data:
                ob.data[_KEY] = ob.data.energy
            ob.data.energy = ob.data[_KEY] * sun_mult


def revert_lighting(scene: bpy.types.Scene) -> None:
    for n in _background_nodes(scene):
        if _KEY in n:
            n.inputs["Strength"].default_value = n[_KEY]
            del n[_KEY]
    for ob in scene.objects:
        if ob.type == "LIGHT" and _KEY in ob.data:
            ob.data.energy = ob.data[_KEY]
            del ob.data[_KEY]
