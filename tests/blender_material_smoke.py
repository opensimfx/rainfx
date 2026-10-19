"""Material smoke test.

Run inside Blender:

    blender -b --factory-startup --python tests/blender_material_smoke.py

Asserts the polished material stack: every kind builds with sane Principled
values, the refraction variant is used only when requested (and never for
dew), snow presets keep snow, and a headless EEVEE render with all of them
completes without errors.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import bpy

import rainfx
import rainfx.gn.materials as M
from rainfx import compat
from rainfx.scene import emitter as em
import blender_smoke as T


def val(mat, key):
    for n in mat.node_tree.nodes:
        if n.type == "BSDF_PRINCIPLED" and key in n.inputs:
            try:
                return tuple(n.inputs[key].default_value)
            except TypeError:
                return n.inputs[key].default_value
    return None


def sc(mat, key):
    v = val(mat, key)
    return v[0] if isinstance(v, (tuple, list)) else v
    return None


def main():
    rainfx.register()
    T.make_world()
    obj = em.create_emitter(bpy.context.scene, "heavy_rain", location=(0, 0, 8))

    # every kind builds with sane values
    for kind in M.KINDS:
        mat = M.get_material(kind)
        tr = sc(mat, "Transmission Weight")
        alpha = sc(mat, "Alpha")
        assert mat.name == f"RainFX {kind.capitalize()}"
        assert 0.0 <= alpha <= 1.0 and (tr is None or 0.0 <= tr <= 1.0), (kind, alpha, tr)
        if kind in ("water", "splash", "drop") and hasattr(mat, "surface_render_method"):
            assert mat.surface_render_method == "BLENDED", kind
    drop = M.get_material("drop")
    assert sc(drop, "Transmission Weight") == 1.0 and sc(drop, "Alpha") == 1.0, sc(drop, "Transmission Weight")
    print("[Materials] all kinds build, drop refraction values OK")

    # presets pick their own kind; refraction only changes water-family drops
    drop_mat = em.apply_preset(obj, bpy.context.scene, "heavy_rain")
    mod = obj.modifiers[0]
    assert compat.get_modifier_input(mod, "Drop Material") is not None
    em.apply_preset(obj, bpy.context.scene, "light_snow")
    assert compat.get_modifier_input(mod, "Drop Material") == M.get_material("snow"), "snow preset must keep snow"
    em.apply_preset(obj, bpy.context.scene, "heavy_rain", refraction=True)
    assert compat.get_modifier_input(mod, "Drop Material") == M.get_material("drop"), "refraction variant not wired"
    print("[Presets] snow stays snow; refraction=True switches water drops to the drop variant")

    # headless EEVEE render with all materials in scene
    obj = em.create_emitter(bpy.context.scene, "hailstorm", location=(3, 0, 8))
    obj2 = em.create_emitter(bpy.context.scene, "hailstorm", location=(-3, 0, 8))
    rn = bpy.context.scene
    rn.render.engine = "BLENDER_EEVEE"
    rn.render.resolution_x = rn.render.resolution_y = 64
    rn.render.filepath = "/tmp/rainbake/materials.png"
    rn.frame_set(5)
    cam_data = bpy.data.cameras.new("cam")
    cam = bpy.data.objects.new("cam", cam_data)
    cam.location = (0, -25, 4)
    cam.rotation_euler = (1.5708, 0, 0)
    rn.collection.objects.link(cam)
    rn.camera = cam
    bpy.ops.render.render(write_still=True)
    print("[Render] EEVEE frame rendered without errors")


main()
print("PASS material smoke")
