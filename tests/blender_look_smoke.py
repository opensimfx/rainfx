"""Cinematic look smoke test (0.4 P1 items).

Run inside Blender:

    blender -b --factory-startup --python-exit-code 1 --python tests/blender_look_smoke.py

Asserts: rain materials carry no constant emission and get per-streak alpha
jitter; materials made by an older RainFX are upgraded in place; fog and the
compositor glow follow the preset's rain rate; wet shading keeps textures,
darkens only porous dielectrics and flattens normal maps in puddles; the
backlight sits behind the rain, aims back at the camera and is hidden from
camera rays; an EEVEE frame with all of it renders.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import bpy
from mathutils import Vector

import rainfx
import rainfx.gn.materials as M
from rainfx import compat
from rainfx.core import physics as P
from rainfx.core import presets as PR
from rainfx.scene import atmosphere, backlight, compositor, emitter as em
import blender_smoke as T


def principled(mat):
    return next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")


def upstream_types(socket, depth=8):
    """Node types reachable upstream of a socket."""
    out, todo = set(), [socket]
    for _ in range(depth):
        nxt = []
        for s in todo:
            for l in s.links:
                out.add(l.from_node.bl_idname)
                nxt.extend(l.from_node.inputs)
        todo = nxt
    return out


def check_materials():
    # an old (0.3) material: emission on, no version tag -> upgraded on next use
    old = compat.new_material("RainFX Water")
    principled(old).inputs["Emission Strength"].default_value = 0.03
    mat = M.get_material("water")
    assert mat is old and mat["rainfx_mat_version"] == M.MATERIAL_VERSION
    assert not any(n.type == "BSDF_PRINCIPLED" for n in mat.node_tree.nodes), "0.3 streak not rebuilt"
    for kind in ("water", "splash", "distant", "near"):
        m = M.get_material(kind)
        types = {n.bl_idname for n in m.node_tree.nodes}
        assert "ShaderNodeEmission" not in types and "ShaderNodeBsdfPrincipled" not in types, kind
        assert {"ShaderNodeBsdfTranslucent", "ShaderNodeBsdfTransparent"} <= types, kind
        # Glossy BSDF reports as ShaderNodeBsdfAnisotropic in Blender 5.x
        assert types & {"ShaderNodeBsdfGlossy", "ShaderNodeBsdfAnisotropic"}, kind
        mix = next(n for n in m.node_tree.nodes if n.get("rainfx_streak_mix"))
        assert mix.inputs[0].is_linked, f"{kind}: alpha jitter not wired"
        assert "ShaderNodeObjectInfo" in upstream_types(mix.inputs[0]), kind
        assert "ShaderNodeFresnel" in upstream_types(mix.inputs[0]), kind
    n_before = len(mat.node_tree.nodes)
    M._apply_kind(mat, "water")                    # idempotent
    assert len(mat.node_tree.nodes) == n_before
    print("[Materials] streaks lit from behind (translucent + Fresnel gloss), no emission; alpha jitter + rim; 0.3 material upgraded in place")


def check_fog_and_glare(scene, ob):
    s = scene.rainfx
    s.with_atmosphere = True
    compositor.create_post(scene)
    from rainfx.ui import ops
    for pid in ("light_rain", "downpour"):
        s.preset = pid
        ops.apply_all(bpy.context, ob)
        p = em.all_presets()[pid]
        fog = bpy.data.objects[atmosphere.FOG_NAME]
        assert math.isclose(atmosphere.fog_density(fog), PR.fog_density_for(p), rel_tol=1e-5), pid
        tree = compat.get_compositing_tree(scene, create=False)
        glare = next(n for n in tree.nodes if n.bl_idname == "CompositorNodeGlare")
        assert math.isclose(glare.inputs["Strength"].default_value, PR.glare_strength_for(p), rel_tol=1e-5), pid
    print("[Atmosphere] fog density and glow strength follow the rain rate")


def check_wetness():
    # textured rough dielectric with a normal map
    stone = compat.new_material("Stone")
    nt = stone.node_tree
    b = principled(stone)
    b.inputs["Roughness"].default_value = 0.9
    tex = nt.nodes.new("ShaderNodeTexChecker")
    nt.links.new(tex.outputs["Color"], b.inputs["Base Color"])
    nmap = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(nmap.outputs["Normal"], b.inputs["Normal"])
    assert M.wire_wetness(stone) is True and M.wire_wetness(stone) is False
    assert stone["rainfx_wet"] == M.WET_VERSION
    ups = upstream_types(b.inputs["Base Color"], depth=10)
    assert "ShaderNodeTexChecker" in ups, "texture lost from Base Color"
    assert "ShaderNodeNormalMap" in upstream_types(b.inputs["Normal"], depth=10), "normal map lost"
    assert "ShaderNodeNewGeometry" in upstream_types(b.inputs["Normal"], depth=10), "puddle flattening missing"
    # the darkening amount: rough dielectric darkens by 0.8 at full wet, metal not at all
    darken = [n for n in nt.nodes if n.bl_idname == "ShaderNodeMath" and n.operation == "MULTIPLY"
              and math.isclose(n.inputs[1].default_value, 0.8, abs_tol=1e-6)]
    assert darken, "porous darkening factor (0.8) not found"
    metal = compat.new_material("Metal")
    mb = principled(metal)
    mb.inputs["Metallic"].default_value = 1.0
    mb.inputs["Roughness"].default_value = 0.9
    M.wire_wetness(metal)
    assert P.wet_porosity(0.9, 1.0) == 0.0
    assert not any(n.bl_idname == "ShaderNodeMath" and n.operation == "MULTIPLY"
                   and math.isclose(n.inputs[1].default_value, 0.8, abs_tol=1e-6) for n in metal.node_tree.nodes)
    # hue kept: base colour is multiplied, not mixed toward a fixed pool colour
    mixes = [n for n in nt.nodes if n.bl_idname == "ShaderNodeMix" and n.data_type == "RGBA"]
    assert any(n.blend_type == "MULTIPLY" for n in mixes), "wet albedo must multiply"
    print("[Wetness] textures kept; porous stone darkens x0.2, metal doesn't; puddles flatten normal maps")


def check_backlight(scene, ob):
    cam_data = bpy.data.cameras.new("cam")
    cam = bpy.data.objects.new("cam", cam_data)
    cam.location = (0.0, -20.0, 1.7)
    cam.rotation_euler = (math.radians(88), 0.0, 0.0)      # looking along +Y
    scene.collection.objects.link(cam)
    scene.camera = cam
    bpy.context.view_layer.update()
    assert bpy.ops.rainfx.add_backlight() == {"FINISHED"}
    light = bpy.data.objects[backlight.LIGHT_NAME]
    assert light.type == "LIGHT" and light.data.type == "SPOT"
    bpy.context.view_layer.update()
    loc = light.matrix_world.translation
    beam = (light.matrix_world.to_quaternion() @ Vector((0, 0, -1))).normalized()
    assert loc.y > ob.location.y - 1.0, f"backlight not behind the rain (y {loc.y:.1f})"
    assert loc.z > cam.location.z
    to_cam = (cam.location - loc).normalized()
    ang = math.degrees(beam.angle(to_cam))
    assert ang < 50, f"backlight does not shine back toward the camera ({ang:.0f} deg)"
    if hasattr(light, "visible_camera"):
        assert light.visible_camera is False
    assert bpy.ops.rainfx.add_backlight() == {"FINISHED"}          # re-run moves, never duplicates
    assert sum(1 for o in bpy.data.objects if o.name.startswith(backlight.LIGHT_NAME)) == 1
    print(f"[Backlight] behind the rain at y={loc.y:.1f}, beam {ang:.0f} deg off the camera line, hidden from camera")
    return cam


def main():
    rainfx.register()
    T.make_world()
    scene = bpy.context.scene
    check_materials()
    ob = em.create_emitter(scene, "heavy_rain", location=(0, 0, 0))
    check_fog_and_glare(scene, ob)
    check_wetness()
    check_backlight(scene, ob)
    assert bpy.ops.rainfx.remove_backlight() == {"FINISHED"}
    assert bpy.data.objects.get(backlight.LIGHT_NAME) is None
    assert bpy.ops.rainfx.add_backlight() == {"FINISHED"}
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = scene.render.resolution_y = 64
    scene.render.filepath = "/tmp/rainbake/look.png"
    scene.frame_set(20)
    bpy.ops.render.render(write_still=True)
    print("[Render] EEVEE frame with backlight, fog, glow rendered")


main()
print("PASS look smoke")
