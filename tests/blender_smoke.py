"""Headless Blender integration test.

Run with a Python that has the ``bpy`` wheel (3.11 for bpy 5.0.x):

    python tests/blender_smoke.py [preset_id ...]

or inside Blender:

    blender -b --python tests/blender_smoke.py -- hailstorm

Asserts physical behaviour of the Geometry Nodes simulation, not just that it
runs: nothing may pass through colliders, hail must bounce, rain must splash.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bpy  # noqa: E402

from rainfx import compat  # noqa: E402
from rainfx.scene import emitter as em  # noqa: E402


def make_world():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.fps = 24
    sc.frame_start, sc.frame_end = 1, 200
    # ground plane (z = 0) and a 2 m cube in the middle of the rain volume
    me = bpy.data.meshes.new("ground")
    s = 60.0
    me.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
    ground = bpy.data.objects.new("ground", me)
    sc.collection.objects.link(ground)
    cm = bpy.data.meshes.new("cube")
    v = [(x, y, z) for x in (-1, 1) for y in (-1, 1) for z in (0, 2)]
    f = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    cm.from_pydata(v, [], f)
    cm.validate()
    cube = bpy.data.objects.new("cube", cm)
    sc.collection.objects.link(cube)
    em.add_colliders(sc, [ground, cube])
    return sc


def read_state(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    eo = obj.evaluated_get(dg)
    me = eo.to_mesh()
    n = len(me.vertices)
    pos = np.zeros(n * 3, dtype=np.float32)
    me.vertices.foreach_get("co", pos)
    pos = pos.reshape(-1, 3)

    def a(name, dim=1):
        arr = np.zeros(n * dim, dtype=np.float32)
        me.attributes[name].data.foreach_get("value" if dim == 1 else "vector", arr)
        return arr.reshape(-1, dim) if dim > 1 else arr

    out = dict(pos=pos, kind=a("kind"), vel=a("velocity", 3), bounces=a("bounces"), d=a("diameter"))
    eo.to_mesh_clear()
    return out


def run(preset_id: str, frames=90, quality=0.25, control=False):
    sc = make_world()
    obj = em.create_emitter(sc, preset_id)
    bpy.context.view_layer.objects.active = obj
    d = em.apply_preset(obj, sc, preset_id, quality=quality)
    mod = em.find_modifier(obj)
    compat.set_modifier_input(mod, "Output Mode", 1)          # raw vertices for inspection
    compat.set_modifier_input(mod, "Viewport Density", 1.0)   # headless evaluation counts as viewport
    if control:                                               # sensitivity check: no colliders
        compat.set_modifier_input(mod, "Colliders", None)
    sc.frame_set(1)
    stats = []
    for f in range(2, frames + 1):
        sc.frame_set(f)
        if f in (30, 60, frames):
            s = read_state(obj)
            prim = s["kind"] < 0.5
            p = s["pos"][prim]
            inside = (np.abs(p[:, 0]) < 0.95) & (np.abs(p[:, 1]) < 0.95) & (p[:, 2] > 0.05) & (p[:, 2] < 1.95)
            below = p[:, 2] < -0.02
            sp = int((~prim).sum())
            speed = np.linalg.norm(s["vel"][prim], axis=1)
            stats.append((f, int(prim.sum()), sp, int(inside.sum()), int(below.sum()),
                          float(speed.mean()), int((s["bounces"][prim] > 0).sum()), float(s["d"][prim].mean())))
    print(f"\n== {preset_id}  derived count={d.get('count')} vt_mean={d.get('vt_mean_ms'):.2f} m/s")
    print("frame  primaries splash  inside_cube  below_floor  mean_speed  bounced  mean_D_mm")
    for r in stats:
        print("%5d %9d %6d %11d %12d %11.2f %8d %10.2f" % r)
    return stats, d


def check(preset_id: str):
    stats, d = run(preset_id)
    last = stats[-1]
    f, prim, sp, inside, below, spd, bounced, dm = last
    assert prim > 0, "no primaries"
    assert below == 0, f"{below} particles fell through the floor"
    assert inside <= max(2, 0.001 * prim), f"{inside} particles inside the cube"
    p = em.all_presets()[preset_id]
    if p.mode == "rain" and p.splash_amount > 0:
        assert sp > 0, "rain produced no splashes"
    if p.mode == "hail":
        assert max(r[6] for r in stats) > 0, "hail never bounced"
    assert 0.2 < spd < 60, f"implausible mean speed {spd}"
    print("PASS", preset_id)


def control_check(preset_id: str = "heavy_rain"):
    """Without colliders the same scene MUST show particles inside the cube,
    otherwise the main test could pass vacuously."""
    stats, _ = run(preset_id, control=True)
    assert stats[-1][3] > 0, "control run found nothing inside the cube: test is not sensitive"
    print("PASS control (test detects missing collision)")


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    if "--control" in args:
        args.remove("--control")
        control_check()
    for pid in (args or ["heavy_rain"]):
        check(pid)
