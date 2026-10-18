"""Blender 5.2 smoke test: start points inside enclosed colliders are rejected.

A closed room (4 walls + roof on a ground plane) overlaps the rain volume. The
init +-Z ray-parity cleanup must leave zero primaries inside the room cavity
from the first evaluated frame on; before the cleanup existed, seeded-in
points fell to the collider's inner faces over ~2 s of warm-up.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))         # sibling tests
sys.path.insert(0, str(Path(__file__).parent.parent))  # repo root → rainfx

import numpy as np

import bpy  # noqa: E402
from rainfx import compat  # noqa: E402
from rainfx.scene import emitter as em  # noqa: E402
from blender_smoke import read_state  # noqa: E402  (sibling test helpers)

FRAMES = 14
CUT = 4.5   # |x|,|y| inside test radius (wall inner face at 4.75)
CUTZ = 7.5  # z below the roof inner face (7.75)


def slab(name, cx, cy, cz, sx, sy, sz, sc):
    """Box mesh from (0,0,0) bottom centre at (cx, cy, cz), given full sizes."""
    hx, hy, hz = sx / 2.0, sy / 2.0, sz / 2.0
    v = [(cx + x * hx, cy + y * hy, cz + z * sz) for x in (-1, 1) for y in (-1, 1) for z in (0.0, 1.0)]
    f = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 6, 2), (0, 2, 3, 1), (1, 3, 7, 5), (2, 6, 7, 3), (4, 5, 7, 6)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(v, [], f)
    me.validate()
    ob = bpy.data.objects.new(name, me)
    sc.collection.objects.link(ob)
    return ob


def make_room_world():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.fps = 24
    sc.frame_start, sc.frame_end = 1, 60
    s = 60.0
    me = bpy.data.meshes.new("ground")
    me.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
    ground = bpy.data.objects.new("ground", me)
    sc.collection.objects.link(ground)

    wt = 0.25  # wall thickness
    parts = [
        slab("wall_n", 0.0, 5.0 - wt / 2.0, 0.0, 10.0, wt, 8.0, sc),
        slab("wall_s", 0.0, -(5.0 - wt / 2.0), 0.0, 10.0, wt, 8.0, sc),
        slab("wall_e", 5.0 - wt / 2.0, 0.0, 0.0, wt, 10.0, 8.0, sc),
        slab("wall_w", -(5.0 - wt / 2.0), 0.0, 0.0, wt, 10.0, 8.0, sc),
        slab("roof", 0.0, 0.0, 8.0 - wt, 10.6, 10.6, wt, sc),
    ]
    em.add_colliders(sc, [ground, *parts])
    return sc


def run():
    sc = make_room_world()
    obj = em.create_emitter(sc, "heavy_rain")
    obj.location = (0, 0, 0)
    bpy.context.view_layer.objects.active = obj
    d = em.apply_preset(obj, sc, "heavy_rain", quality=0.3, box=(30, 30, 20))
    mod = em.find_modifier(obj)
    compat.set_modifier_input(mod, "Output Mode", 1)
    compat.set_modifier_input(mod, "Viewport Density", 1.0)

    counts, inside_per_frame = None, []
    for f in range(1, FRAMES + 1):
        sc.frame_set(f)
        s = read_state(obj)
        prim = s["kind"] < 0.5
        p = s["pos"][prim]
        if f == 1:
            counts = int(prim.sum())
        ins = int(((np.abs(p[:, 0]) < CUT) & (np.abs(p[:, 1]) < CUT) & (p[:, 2] < CUTZ)).sum())
        inside_per_frame.append(ins)
        if f in (1, 2, FRAMES):
            print(f"   frame {f}: primaries={int(prim.sum())} inside_room={ins}")
    return int(d["count"]), counts, inside_per_frame


def main():
    intended, n1, inside = run()
    assert n1 > 1000, f"frame 1 has only {n1} primaries (anti-vacuous fail)"
    frac = (intended - n1) / intended
    assert 0.005 < frac < 0.15, (
        f"clean-up removed {frac:.2%} of {intended} points; expected the room "
        f"cavity (~3.75% of the volume) and nothing else"
    )
    assert max(inside) == 0, f"points inside the room: {max(inside)} (frames {inside})"
    print(f"PASS inside-collider cleanup (rejected {frac:.2%} = {intended - n1} of "
          f"{intended} as inside-room starts, 0 inside across {len(inside)} frames)")


if __name__ == "__main__":
    main()
