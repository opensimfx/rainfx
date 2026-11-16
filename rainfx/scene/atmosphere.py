"""Fog volume + sky/sun dimming. Everything reversible: original values are
stored as custom properties on the datablocks that were modified."""
from __future__ import annotations

import bpy

from .. import compat
from ..core import physics as P
from . import emitter as em

FOG_NAME = "RainFX Fog"
_KEY = "rainfx_orig"


FOG_VERSION = 2       # 2 (1.0): reaches 3x the rain volume, soft edges, base below the ground
FOG_REACH = 3.0       # fog box footprint over the rain volume's: its edge stays out of shot
FOG_HEIGHT = 1.5      # ... and over its height
FOG_EDGE = 0.12       # share of the half-width over which density fades out at the sides
GROUND_SKIRT = 0.05   # box bottoms sit this far below the ground (relative): a face coplanar
                      # with the ground confuses Cycles about which side is inside the volume


def _box_mesh(name: str, z0: float) -> bpy.types.Mesh:
    mesh = bpy.data.meshes.new(name)
    h = 0.5
    v = [(x, y, z) for x in (-h, h) for y in (-h, h) for z in (z0, 1.0)]
    f = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    mesh.from_pydata(v, [], f)
    mesh.validate()
    return mesh


def _edge_fade(nt, sep, top: bool):
    """Shader nodes: smoothstep fade toward the box sides (and top) in object space."""
    def m(op, a, b=None):
        n = nt.nodes.new("ShaderNodeMath")
        n.operation = op
        for i, v in enumerate((a, b)):
            if v is None:
                continue
            if isinstance(v, (int, float)):
                n.inputs[i].default_value = v
            else:
                nt.links.new(v, n.inputs[i])
        return n.outputs[0]

    def smooth(v, lo, hi):
        r = nt.nodes.new("ShaderNodeMapRange")
        r.interpolation_type = "SMOOTHSTEP"
        nt.links.new(v, r.inputs["Value"])
        r.inputs["From Min"].default_value = lo
        r.inputs["From Max"].default_value = hi
        return r.outputs["Result"]

    edge = m("MINIMUM", m("SUBTRACT", 0.5, m("ABSOLUTE", sep.outputs["X"])),
             m("SUBTRACT", 0.5, m("ABSOLUTE", sep.outputs["Y"])))
    fade = smooth(edge, 0.0, 0.5 * FOG_EDGE)
    if top:
        fade = m("MULTIPLY", fade, smooth(sep.outputs["Z"], 1.0, 0.7))
    return fade


def _fog_material() -> bpy.types.Material:
    """Volume Scatter: density x soft fade toward the box sides and top.

    Object coordinates span x, y in [-0.5, 0.5] and z in [0, 1]; the fade is
    smoothstep over the outer FOG_EDGE of each half-width and the top 30 %,
    so the box never shows as a wall of haze.
    """
    mat = bpy.data.materials.get(FOG_NAME)
    if mat is not None and mat.get("rainfx_fog_version") == FOG_VERSION:
        return mat
    if mat is None:
        mat = compat.new_material(FOG_NAME)
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])

    fade = _edge_fade(nt, sep, top=True)
    d0 = nt.nodes.new("ShaderNodeValue")
    d0.label = "Density"
    d0["rainfx_fog_density"] = True
    vol = nt.nodes.new("ShaderNodeVolumeScatter")
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    nt.links.new(fade, mul.inputs[0])
    nt.links.new(d0.outputs[0], mul.inputs[1])
    nt.links.new(mul.outputs[0], vol.inputs["Density"])
    nt.links.new(vol.outputs["Volume"], out.inputs["Volume"])
    mat["rainfx_fog_version"] = FOG_VERSION
    return mat


def fog_density(obj: bpy.types.Object) -> float:
    """Density (1/m) at the centre of a RainFX fog box."""
    for n in obj.data.materials[0].node_tree.nodes:
        if n.get("rainfx_fog_density"):
            return n.outputs[0].default_value
    return 0.0


def create_fog(scene: bpy.types.Scene, box=(16.0, 16.0, 10.0), density: float = 0.01,
               anisotropy: float = 0.3, location=(0.0, 0.0, 0.0)) -> bpy.types.Object:
    obj = bpy.data.objects.get(FOG_NAME)
    if obj is not None and obj.data.get("rainfx_fog_version") != FOG_VERSION:
        old = obj.data                       # 0.3 box: bottom on the ground, no fade
        obj.data = _box_mesh(FOG_NAME, -GROUND_SKIRT)
        obj.data["rainfx_fog_version"] = FOG_VERSION
        obj.data.materials.append(_fog_material())
        if old.users == 0:
            bpy.data.meshes.remove(old)
    if obj is None:
        mesh = _box_mesh(FOG_NAME, -GROUND_SKIRT)
        mesh["rainfx_fog_version"] = FOG_VERSION
        obj = bpy.data.objects.new(FOG_NAME, mesh)
        em.ensure_collection(scene, em.ROOT_NAME).objects.link(obj)
        obj.display_type = "BOUNDS"
        obj.visible_shadow = False
        obj.data.materials.append(_fog_material())
    obj.location = location
    obj.scale = (box[0] * FOG_REACH, box[1] * FOG_REACH, box[2] * FOG_HEIGHT)
    set_fog(obj, density, anisotropy)
    return obj


def set_fog(obj: bpy.types.Object, density: float, anisotropy: float = 0.3) -> None:
    mat = _fog_material()
    if not obj.data.materials:
        obj.data.materials.append(mat)
    elif obj.data.materials[0] is not mat:
        obj.data.materials[0] = mat
    for n in mat.node_tree.nodes:
        if n.get("rainfx_fog_density"):
            n.outputs[0].default_value = density
        elif n.type == "VOLUME_SCATTER":
            n.inputs["Anisotropy"].default_value = anisotropy


SPRAY_NAME = "RainFX Spray"


def _spray_material() -> bpy.types.Material:
    """Volume Scatter whose density falls as exp(-height / 0.1 m) above the ground.

    Splash droplets thrown by heavy rain hang in a thin white layer: their
    number density decays exponentially with height and few rise above
    0.33-0.45 m (JFM study of raindrops hitting water). The box spans
    0..SPRAY_TOP_M; object Z (0..1) is mapped to metres before the decay.
    """
    mat = bpy.data.materials.get(SPRAY_NAME)
    if mat is not None and mat.get("rainfx_fog_version") == FOG_VERSION:
        return mat
    if mat is None:
        mat = compat.new_material(SPRAY_NAME)
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    k = nt.nodes.new("ShaderNodeMath")
    k.operation = "MULTIPLY"
    k.inputs[1].default_value = -P.SPRAY_TOP_M / P.SPRAY_SCALE_HEIGHT_M
    nt.links.new(sep.outputs["Z"], k.inputs[0])
    ex = nt.nodes.new("ShaderNodeMath")
    ex.operation = "EXPONENT"
    nt.links.new(k.outputs[0], ex.inputs[0])
    d0 = nt.nodes.new("ShaderNodeValue")
    d0.label = "Ground density"
    d0["rainfx_spray_density"] = True
    m = nt.nodes.new("ShaderNodeMath")
    m.operation = "MULTIPLY"
    nt.links.new(ex.outputs[0], m.inputs[0])
    nt.links.new(d0.outputs[0], m.inputs[1])
    mf = nt.nodes.new("ShaderNodeMath")
    mf.operation = "MULTIPLY"
    nt.links.new(m.outputs[0], mf.inputs[0])
    nt.links.new(_edge_fade(nt, sep, top=False), mf.inputs[1])
    vol = nt.nodes.new("ShaderNodeVolumeScatter")
    nt.links.new(mf.outputs[0], vol.inputs["Density"])
    mat["rainfx_fog_version"] = FOG_VERSION
    nt.links.new(vol.outputs["Volume"], out.inputs["Volume"])
    for i, n in enumerate((tc, sep, k, ex, d0, m, vol)):
        n.location = (-1200 + 170 * i, 0 if n is not d0 else -200)
    return mat


def create_spray(scene: bpy.types.Scene, box=(16.0, 16.0, 10.0), density: float = 0.05,
                 anisotropy: float = 0.3, location=(0.0, 0.0, 0.0)) -> bpy.types.Object:
    """Low splash-spray mist over the ground of the rain volume (heavy rain only)."""
    obj = bpy.data.objects.get(SPRAY_NAME)
    if obj is None:
        mesh = _box_mesh(SPRAY_NAME, -0.2)     # 10 cm below the ground: never coplanar with it
        obj = bpy.data.objects.new(SPRAY_NAME, mesh)
        em.ensure_collection(scene, em.ROOT_NAME).objects.link(obj)
        obj.display_type = "BOUNDS"
        obj.visible_shadow = False
        obj.data.materials.append(_spray_material())
    obj.location = location
    obj.scale = (box[0], box[1], P.SPRAY_TOP_M)
    mat = _spray_material()
    if obj.data.materials[0] is not mat:
        obj.data.materials[0] = mat
    for n in mat.node_tree.nodes:
        if n.get("rainfx_spray_density"):
            n.outputs[0].default_value = density
        elif n.type == "VOLUME_SCATTER":
            n.inputs["Anisotropy"].default_value = anisotropy
    return obj


def remove_spray() -> bool:
    obj = bpy.data.objects.get(SPRAY_NAME)
    if obj is None:
        return False
    me = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if me is not None and me.users == 0:
        bpy.data.meshes.remove(me)
    return True


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
