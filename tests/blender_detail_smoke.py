"""Physics-driven detail smoke test (0.4 P2 items).

Run inside Blender:

    blender -b --factory-startup --python-exit-code 1 --python tests/blender_detail_smoke.py

Asserts: splashes are decided per drop by K = We Oh^-2/5 (a threshold above
every drop's K gives none, drizzle gives none however many droplets are asked
for, splashing parents are bigger than the average landing drop); crowns sit
still on up-facing surfaces and live 0.1 s, and can be switched off; puddle
ring ripples follow the rain rate; the low spray mist exists only in heavy
rain; the foreground layer rides the camera, stays out of the clear zone and
is rain-only; an EEVEE frame with all of it renders.
"""
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import bpy

import rainfx
import rainfx.gn.materials as M
from rainfx import compat
from rainfx.core import physics as P
from rainfx.core import presets as PR
from rainfx.scene import atmosphere, emitter as em, foreground as fg
import blender_smoke as T


def state(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    eo = obj.evaluated_get(dg)
    me = eo.to_mesh()
    n = len(me.vertices)
    out = {"pos": np.zeros((n, 3), np.float32)}
    me.vertices.foreach_get("co", out["pos"].ravel())
    for name, dim in (("kind", 1), ("crown", 1), ("imp", 1), ("diameter", 1), ("age", 1), ("velocity", 3)):
        at = me.attributes.get(name)
        arr = np.zeros(n * dim, np.float32)
        if at is not None:
            at.data.foreach_get("value" if dim == 1 else "vector", arr)
        out[name] = arr.reshape(-1, dim) if dim > 1 else arr
    eo.to_mesh_clear()
    return out


def run(pid, frames=40, **inputs):
    sc = T.make_world()
    ob = em.create_emitter(sc, pid)
    em.apply_preset(ob, sc, pid, quality=0.25)
    mod = em.find_modifier(ob)
    compat.set_modifier_input(mod, "Output Mode", 1)
    compat.set_modifier_input(mod, "Viewport Density", 1.0)
    for k, v in inputs.items():
        compat.set_modifier_input(mod, k.replace("_", " "), v)
    for f in range(1, frames + 1):
        sc.frame_set(f)
    return state(ob)


def split(s):
    land = s["imp"] > 0.5
    crowns = s["crown"] > 0.5
    drops = (s["kind"] > 0.5) & ~crowns
    return land, drops, crowns


def check_splash_threshold():
    s = run("heavy_rain")
    land, drops, crowns = split(s)
    assert land.sum() > 50 and drops.sum() > 50 and crowns.sum() > 10, (land.sum(), drops.sum(), crowns.sum())
    # splashing parents are the big drops: droplet D = parent D x Splash Size x U(0.4, 1.2)
    size = em.all_presets()["heavy_rain"].splash_size
    parent_d = s["diameter"][drops].mean() / (size * 0.8)
    land_d = s["diameter"][land].mean()
    assert parent_d > 1.2 * land_d, f"splashers not bigger than the average drop ({parent_d:.2f} vs {land_d:.2f})"
    # crowns: static, on the ground (z ~ 0.001) or the cube top (z ~ 2.001), at most 0.1 s old
    cz = s["pos"][crowns][:, 2]
    on_top = (np.abs(cz - 0.001) < 0.01) | (np.abs(cz - 2.001) < 0.01)
    assert on_top.all(), f"crowns off the up-facing surfaces: {cz[~on_top][:5]}"
    assert np.abs(s["velocity"][crowns]).max() == 0.0, "crowns move"
    assert s["age"][crowns].max() <= P.CROWN_LIFE_S + 1e-6
    print(f"[Splash] heavy: {drops.sum()} droplets, {crowns.sum()} crowns from {land.sum()} landings; "
          f"splashing drops average {parent_d:.2f} mm vs {land_d:.2f} mm landing")

    s = run("heavy_rain", Splash_Threshold=1.0e5)
    land, drops, crowns = split(s)
    assert land.sum() > 50 and drops.sum() == 0 and crowns.sum() == 0, (land.sum(), drops.sum(), crowns.sum())
    s = run("heavy_rain", Crowns=False)
    land, drops, crowns = split(s)
    assert drops.sum() > 50 and crowns.sum() == 0
    s = run("drizzle", Splash_Amount=6)
    land, drops, crowns = split(s)
    assert land.sum() > 20 and drops.sum() == 0 and crowns.sum() == 0, "drizzle must not splash"
    print("[Splash] threshold above every K -> none; Crowns off -> none; drizzle at amount 6 -> none")


def ripple_weight():
    ng = bpy.data.node_groups[M.RIPPLES_NAME]
    return next(n for n in ng.nodes if n.get("rainfx_ripple_weight")).outputs[0].default_value


def check_ripples_spray_foreground():
    rainfx.register()
    sc = T.make_world()
    from rainfx.ui import ops
    s = sc.rainfx
    s.with_atmosphere = True
    ob = em.create_emitter(sc, "light_rain")
    mat = compat.new_material("Puddle")
    M.wire_wetness(mat)
    rip = [n for n in mat.node_tree.nodes if n.type == "GROUP" and n.node_tree.name == M.RIPPLES_NAME]
    assert rip, "ring ripples not wired"
    w = {}
    for pid in ("light_rain", "heavy_rain", "downpour"):
        s.preset = pid
        ops.apply_all(bpy.context, ob)
        w[pid] = ripple_weight()
        spray = bpy.data.objects.get(atmosphere.SPRAY_NAME)
        want = PR.spray_density_for(em.all_presets()[pid])
        if want == 0:
            assert spray is None, f"{pid}: spray mist in light rain"
        else:
            d0 = next(n for n in spray.data.materials[0].node_tree.nodes if n.get("rainfx_spray_density"))
            assert math.isclose(d0.outputs[0].default_value, want, rel_tol=1e-5)
            assert math.isclose(spray.scale.z, P.SPRAY_TOP_M, rel_tol=1e-4)   # unit-high box
    assert w["light_rain"] < w["heavy_rain"] < w["downpour"] == 1.0, w
    print(f"[Ripples] weight light {w['light_rain']:.2f} < heavy {w['heavy_rain']:.2f} < downpour {w['downpour']:.2f}")
    print("[Spray] none in light rain; heavy and downpour get the low mist at the derived density")

    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.location = (1.0, -12.0, 1.7)
    cam.rotation_euler = (math.radians(80), 0.0, math.radians(15))
    sc.collection.objects.link(cam)
    sc.camera = cam
    s.foreground_rain = True
    lay = bpy.data.objects.get(fg.FOREGROUND_NAME)
    assert lay is not None, "foreground layer not created"
    sc.frame_set(12)
    dg = bpy.context.evaluated_depsgraph_get()
    le = lay.evaluated_get(dg)
    me = le.to_mesh()
    pts = np.array([(le.matrix_world @ v.co)[:] for v in me.vertices], np.float32)
    le.to_mesh_clear()
    assert len(pts) > 100
    rel = pts - np.array(cam.location[:], np.float32)
    assert (np.abs(rel[:, 0]) <= 0.5 * fg.BOX[0] + 0.3).all() and (np.abs(rel[:, 2]) <= 0.5 * fg.BOX[2] + 0.3).all()
    inst = rel.reshape(-1, 12, 3)                      # 6-sided cylinder = 12 verts per streak
    centre = inst.mean(axis=1)
    extent = np.ptp(inst, axis=1).max(axis=1)
    near = np.linalg.norm(centre, axis=1) < fg.CLEAR_RADIUS - 0.05
    assert (extent[near] < 1e-6).all(), "streaks inside the clear zone around the lens"
    visible = extent > 0
    print(f"[Foreground] {visible.sum()} streaks around the camera, {near.sum()} hidden in the clear zone")
    cam.location.x += 5.0
    bpy.context.view_layer.update()
    assert math.isclose(lay.matrix_world.translation.x, cam.location.x, abs_tol=1e-4), "layer does not follow"
    s.preset = "light_snow"
    ops.apply_all(bpy.context, ob)
    assert bpy.data.objects.get(fg.FOREGROUND_NAME) is None, "foreground layer must be rain-only"
    s.preset = "heavy_rain"
    ops.apply_all(bpy.context, ob)
    assert bpy.data.objects.get(fg.FOREGROUND_NAME) is not None
    print("[Foreground] follows the camera; removed for snow, back for rain")

    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x = sc.render.resolution_y = 64
    sc.render.filepath = "/tmp/rainbake/detail.png"
    sc.frame_set(20)
    bpy.ops.render.render(write_still=True)
    print("[Render] EEVEE frame with crowns, spray mist, ripples and foreground rain rendered")


check_splash_threshold()
check_ripples_spray_foreground()
print("PASS detail smoke")
