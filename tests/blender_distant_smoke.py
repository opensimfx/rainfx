"""Distant rain smoke: a static far layer that wraps and stays out of the way.

World: bare emitter + the helper world's ground/cube (the layer interacts
with nothing itself).

Checks (headless, Blender 5.2.1):
  1. refresh creates 'RainFX Distant' carrying the static group and
     preset-derived inputs (Box Size, Count, Wind, Fall Speed, Seed,
     Material);
  2. the modifier evaluates: instances realize into a real vertex cloud
     tagged with the far material;
  3. every realized vertex stays inside the inflated far box at frames
     1 / 60 / 120 — the wrap survives more than a full fall cycle;
  4. re-evaluating the same frame rebuilds identical geometry (pure frame
     function: no cache, no state);
  5. the layer never enters the emitter's eval mesh (wetness 'imp' scan
     safety): same vertex count and materials with the layer on vs off;
  6. follow parenting: the layer tracks its parent's moves like the fog;
  7. toggling off removes the object again, idempotently;
  8. a headless EEVEE render with the far layer completes without errors.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import bpy

import blender_smoke as T
import rainfx
from rainfx import compat
from rainfx.gn import materials as M
from rainfx.scene import distant as dist
from rainfx.scene import emitter as em

FAR = (48.0, 48.0, 20.0)


def eval_cloud(ob):
    """(vertex coords list, material names) of a realized modifier output."""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    try:
        pts = [tuple(v.co) for v in me.vertices]
        mats = [m.name for m in me.materials if m is not None]
    finally:
        ev.to_mesh_clear()
    return pts, mats


def eval_counts(ob):
    """Realized vertex count + material names (cheap for big meshes)."""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    try:
        n = len(me.vertices)
        mats = [m.name for m in me.materials if m is not None]
    finally:
        ev.to_mesh_clear()
    return n, mats


def main():
    rainfx.register()
    scene = T.make_world()
    scene.frame_end = 140
    et = em.create_emitter(scene, "heavy_rain", location=(0, 0, 8), quality=0.3)
    em.apply_preset(et, scene, "heavy_rain", quality=0.3)
    compat.set_modifier_input(et.modifiers[0], "Viewport Density", 1.0)  # headless eval counts as viewport
    compat.set_modifier_input(et.modifiers[0], "Output Mode", 1)         # raw vertices for inspection

    # [Build] refresh creates the layer with preset-derived inputs
    n = dist.refresh(scene, True, ob=et, box=(16.0, 16.0, 10.0), density=0.02, seed=3)
    obj = bpy.data.objects.get("RainFX Distant")
    assert obj is not None and n == 1, f"layer object missing (n={n})"
    mod = dist._find_mod(obj)
    assert mod is not None and mod.type == "NODES" and \
        mod.node_group.name == "RainFX Distant", "layer modifier missing"
    got = compat.get_modifier_input(mod, "Box Size")
    assert tuple(float(c) for c in got) == FAR, f"far box wrong ({got})"
    count = int(compat.get_modifier_input(mod, "Count"))
    assert count == int(48 * 48 * 20 * 0.5 * 0.02), f"count formula off ({count})"
    vt = float((et.get("rainfx_derived") or {}).get("vt_mean_ms", 0.0))
    assert abs(float(compat.get_modifier_input(mod, "Fall Speed")) - vt) < 1e-4, \
        "fall speed not synced to preset"
    wexp = tuple(et.get("rainfx_wind", ()))
    assert len(wexp) == 3, f"emitter did not store rainfx_wind ({wexp})"
    wgot = tuple(float(c) for c in compat.get_modifier_input(mod, "Wind"))
    assert all(abs(a - b) < 1e-4 for a, b in zip(wexp, wgot)), \
        f"wind not synced ({wexp} vs {wgot})"
    assert int(compat.get_modifier_input(mod, "Seed")) == 514, "seed offset wrong"
    assert compat.get_modifier_input(mod, "Distant Material") == M.get_material("distant"), \
        "material not wired"
    print(f"[Build] layer up: {count} streaks, far box {FAR}, fall {vt:.2f} m/s")

    # [Eval] instances realize into real vertices tagged with the far material
    scene.frame_set(1)
    pts, mats = eval_cloud(obj)
    assert len(pts) > 4 * count, f"instances did not realize ({len(pts)} verts)"
    assert "RainFX Distant" in mats, f"far material not on realized mesh ({mats})"
    print(f"[Eval] {len(pts)} verts realized, far material present")

    # [Wrap] every realized vertex stays inside the inflated far box
    margin = 1.5  # streak half-length + wind-tilt slack
    for f in (1, 60, 120):
        scene.frame_set(f)
        pts, _ = eval_cloud(obj)
        for pos in pts:
            x, y, z = pos
            assert -24.0 - margin < x < 24.0 + margin and \
                -24.0 - margin < y < 24.0 + margin and \
                -margin < z < 20.0 + margin, f"streak escaped the box at frame {f}: {pos}"
    print("[Wrap] cloud stays inside the far box at frames 1/60/120")

    # [Determin] re-evaluating the same frame rebuilds identical geometry
    scene.frame_set(130)
    a, _ = eval_cloud(obj)
    scene.frame_set(129)
    scene.frame_set(130)
    b, _ = eval_cloud(obj)
    assert len(a) == len(b), "realized vertex count drifts between evals"
    worst = max(max(abs(p1[j] - p2[j]) for j in range(3)) for p1, p2 in zip(a, b))
    assert worst < 1e-4, f"layer is not a pure frame function (delta {worst:.2e})"
    print("[Determin] same-frame re-eval identical")

    # [Safety] the emitter's eval mesh is untouched by the far layer
    # (walk past ~frame 50 so impact verts exist; heavy_rain vt 3.85 m/s
    # from z=8 lands its first drop around frame 50)
    for f in range(1, 125):
        scene.frame_set(f)
    n_on, m_on = eval_counts(et)
    dist.refresh(scene, False)
    for f in range(1, 125):
        scene.frame_set(f)
    n_off, m_off = eval_counts(et)
    assert n_on == n_off and n_on > 0 and m_on == m_off and "RainFX Distant" not in m_on, \
        f"far layer leaks into the emitter mesh ({n_on}/{n_off}, {m_on} vs {m_off})"
    print(f"[Safety] emitter mesh unchanged ({n_on} verts, {len(m_on)} mats)")

    # [Follow] the layer rides its parent like the fog does
    fake = bpy.data.objects.new("FollowPoint", None)
    scene.collection.objects.link(fake)
    n = dist.refresh(scene, True, ob=et, box=(16, 16, 10), density=0.02, follow=fake, seed=3)
    obj = bpy.data.objects.get("RainFX Distant")
    bpy.context.view_layer.update()  # matrix readback after a fresh parent link
    assert obj is not None and obj.parent is fake, "layer not parented to follow target"
    orig = obj.matrix_world.translation.copy()
    fake.location = (6.0, 0.0, 0.0)
    bpy.context.view_layer.update()
    moved = (obj.matrix_world.translation - orig).length
    assert abs(moved - 6.0) < 1e-3, f"layer does not follow (delta {moved:.4f})"
    print(f"[Follow] tracks parent (delta {moved:.3f} for a 6.0 m shift)")

    # [Toggle] off removes the object again, idempotently
    n1 = dist.refresh(scene, False)
    n2 = dist.refresh(scene, False)
    assert n1 == 1 and n2 == 0, f"toggle-off not idempotent ({n1}, {n2})"
    assert bpy.data.objects.get("RainFX Distant") is None, "layer object remains"
    print("[Toggle] layer removed cleanly (x2 idempotent)")

    # [Render] headless EEVEE frame with the far layer in scene
    dist.refresh(scene, True, ob=et, box=(16, 16, 10), density=0.35, seed=1)
    obj = bpy.data.objects.get("RainFX Distant")
    assert obj is not None, "layer vanished before render"
    rn = scene.render
    rn.engine = "BLENDER_EEVEE"
    rn.resolution_x = rn.resolution_y = 64
    rn.filepath = "/tmp/rainbake/distant.png"
    cam_data = bpy.data.cameras.new("cam")
    cam = bpy.data.objects.new("cam", cam_data)
    cam.location = (0, -25, 12)
    cam.rotation_euler = (1.3508, 0, 0)
    scene.collection.objects.link(cam)
    scene.camera = cam
    scene.frame_set(40)
    bpy.ops.render.render(write_still=True)
    print("[Render] EEVEE frame with the far layer rendered")

    print("PASS distant smoke")


main()
print("PASS distant rain smoke")
