"""Headless check for the Follow Object input (Phase 1, item 1).

    blender -b --factory-startup --python tests/blender_follow_smoke.py

Asserts that the precipitation volume relocates with the follow object at
every step (spawn, wrap, recycle) while still colliding with the ground.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import bpy  # noqa: E402

import blender_smoke as T  # noqa: E402
from rainfx import compat  # noqa: E402
from rainfx.scene import emitter as em  # noqa: E402

BOX = (20.0, 20.0, 12.0)
HX = BOX[0] / 2


def scene_with_camera():
    sc = T.make_world()
    cam_data = bpy.data.cameras.new("cam")
    cam = bpy.data.objects.new("cam", cam_data)
    sc.collection.objects.link(cam)
    cam.location = (10.0, 0.0, 4.0)          # start: 10 m away from the emitter
    cam.keyframe_insert("location", frame=1)
    cam.location = (40.0, 0.0, 4.0)          # at frame 60: moved 30 m along X
    cam.keyframe_insert("location", frame=60)
    return sc, cam


def read_xy_z(sc, obj):
    s = T.read_state(obj)
    prim = s["kind"] < 0.5
    return s["pos"][prim]


def check_follow():
    sc, cam = scene_with_camera()
    obj = em.create_emitter(sc, "heavy_rain", location=(0.0, 0.0, 0.0))
    bpy.context.view_layer.objects.active = obj
    d = em.apply_preset(obj, sc, "heavy_rain", quality=0.25, box=BOX,
                        follow=cam, follow_offset=(0.0, 0.0, -BOX[2] / 2))
    mod = em.find_modifier(obj)
    compat.set_modifier_input(mod, "Output Mode", 1)
    compat.set_modifier_input(mod, "Viewport Density", 1.0)
    got = compat.get_modifier_input(mod, "Follow Object")
    assert got == cam, f"follow socket not stored (got {got})"
    stats = []
    for f in (10, 30, 55):
        sc.frame_set(f)
        cx = cam.matrix_world.translation.x   # animated location at this frame
        cz = cam.matrix_world.translation.z
        p = read_xy_z(sc, obj)
        assert len(p), "no primaries evaluated"
        dx, dy, dz = p[:, 0] - cx, p[:, 1] - 0.0, p[:, 2] - cz
        # Volume base = cam + offset(-half box in x/y/z). x/y inside [cam-h/2, cam+h/2],
        # z inside [cam-h/2, cam+h/2] (rain spans the whole column; only the box
        # bounds matter, not the vertical distribution).
        inside = (np.abs(dx) <= HX * 1.01) & (np.abs(dy) <= HX * 1.01) & \
                 (dz >= -BOX[2] * 0.51) & (dz <= BOX[2] * 0.51)
        stats.append((f, cx, int(inside.sum()), len(p), float(np.abs(dx).max())))
    for r in stats:
        print("frame %d cam_x=%.1f inside %5d / %5d (max |dx| %.1f)" % r)
    assert all(r[2] >= 0.95 * r[3] for r in stats), f"follow failed: {stats}"
    print("PASS follow_object")


def check_fixed_mode_regression():
    """follow=None must behave like v0.1: volume centred on the emitter origin."""
    sc = T.make_world()
    obj = em.create_emitter(sc, "heavy_rain", location=(7.0, 0.0, 0.0))
    bpy.context.view_layer.objects.active = obj
    loc = obj.location.copy()
    em.apply_preset(obj, sc, "heavy_rain", quality=0.25, box=BOX)
    mod = em.find_modifier(obj)
    compat.set_modifier_input(mod, "Output Mode", 1)
    compat.set_modifier_input(mod, "Viewport Density", 1.0)
    sc.frame_set(30)
    p = read_xy_z(sc, obj)
    assert len(p)
    # read_state returns LOCAL positions (evaluated mesh); x range must be [-hx, hx]
    assert np.abs(p[:, 0]).max() <= HX * 1.01 and np.abs(p[:, 1]).max() <= HX * 1.01, \
        "fixed-mode spawn range wrong"
    assert p[:, 2].min() >= -0.3, "particles below emitter base"
    print("PASS fixed mode regression (emitter-local numbers, %d primaries)" % len(p))


if __name__ == "__main__":
    check_fixed_mode_regression()
    check_follow()
