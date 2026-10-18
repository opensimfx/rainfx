"""Headless check for collider velocity transfer (Phase 1, item 2).

    blender -b --factory-startup --python tests/blender_motion_smoke.py

A 2 m cube sweeps 12 m through the rain between frames 1 and 40 (bezier keys:
average 7.4 m/s, mid-sweep up to ~11 m/s). Splashes spawned on its surface
must inherit that velocity. Metric: the share of splashes moving with the
cube (vx > 5 m/s) and their mean vx; the same scene with "Collider Push" = 0
is the control (anti-vacuous: it must still spawn splashes, just almost none
carry the cube's speed, and no splash velocity field may blow up).
"""
import sys
from pathlib import Path

import numpy as np

FAST = 5.0   # m/s: above the fastest static splash (ground hits, wind only)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import bpy  # noqa: E402

import blender_smoke as T  # noqa: E402
from rainfx import compat  # noqa: E402
from rainfx.scene import emitter as em  # noqa: E402

SPEED = 12.0 / (39.0 / 24.0)   # average cube speed 7.4 m/s (bezier: peak ~11)


def make_world():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.fps = 24
    sc.frame_start, sc.frame_end = 1, 60
    me = bpy.data.meshes.new("ground")
    s = 60.0
    me.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
    ground = bpy.data.objects.new("ground", me)
    sc.collection.objects.link(ground)
    # moving 2 m cube, base at z = 0, sweeps through the emitter's box centre
    cm = bpy.data.meshes.new("mover")
    v = [(x, y, z) for x in (-1, 1) for y in (-1, 1) for z in (0, 2)]
    f = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    cm.from_pydata(v, [], f)
    cm.validate()
    mover = bpy.data.objects.new("mover", cm)
    sc.collection.objects.link(mover)
    mover.location = (-6.0, 0.0, 0.0)
    mover.keyframe_insert("location", frame=1)
    mover.location = (6.0, 0.0, 0.0)
    mover.keyframe_insert("location", frame=40)
    em.add_colliders(sc, [ground, mover])
    return sc


def run(push):
    sc = make_world()
    obj = em.create_emitter(sc, "heavy_rain")
    bpy.context.view_layer.objects.active = obj
    em.apply_preset(obj, sc, "heavy_rain", quality=0.25, box=(10.0, 10.0, 8.0))
    mod = em.find_modifier(obj)
    compat.set_modifier_input(mod, "Output Mode", 1)
    compat.set_modifier_input(mod, "Viewport Density", 1.0)
    if push == 0.0:
        assert compat.set_modifier_input(mod, "Collider Push", 0.0), "Collider Push socket missing"
    for f in range(1, 31):
        sc.frame_set(f)
    s = T.read_state(obj)
    spl = s["kind"] > 0.5
    n = int(spl.sum())
    v = s["vel"][spl]
    fast = v[:, 0] > FAST
    frac = float(fast.mean()) if n else 0.0
    mean_fast = float(v[fast, 0].mean()) if fast.any() else 0.0
    mean_abs = float(np.linalg.norm(v, axis=1).mean())
    print("   push=%.1f  splashes=%d  fast(vx>%s)=%d (%.1f%%)  mean fast vx=%.2f  mean |v|=%.2f"
          % (push, n, FAST, int(fast.sum()), frac * 100, mean_fast, mean_abs))
    return n, frac, mean_fast, mean_abs


def main():
    n_on, frac_on, fast_on, abs_on = run(1.0)
    n_off, frac_off, fast_off, abs_off = run(0.0)
    assert n_on > 50 and n_off > 50, f"splashes missing ({n_on}, {n_off})"
    assert abs_on < 5.0, f"garbage velocity field: mean|v|={abs_on:.2f}"
    assert frac_off < 0.005, f"no-push control already fast: frac={frac_off:.3f} (max vx {fast_off:.1f})"
    assert frac_on > 0.05, f"cube-hit splashes not carrying push: frac={frac_on:.3f}"
    assert fast_on > 7.0, \
        f"push share too weak: fast mean vx={fast_on:.2f} (cube up to ~11 m/s)"
    print("PASS collider velocity transfer "
          "(%.1f%% of splashes move with the cube at %.1f m/s vs %.2f%% without push)"
          % (frac_on * 100, fast_on, frac_off * 100))


if __name__ == "__main__":
    main()
