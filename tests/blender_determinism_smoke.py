"""Headless determinism check (Phase 1, last item).

    blender -b --factory-startup --python tests/blender_determinism_smoke.py

Heavy rain, no colliders, frames 1..16, two twin emitters with identical
settings in one scene. Probes on Blender 5.2.1 showed that a modifier-input
change alone does not dirty the live simulation cache, so the walk order
matters: the Seed change is only picked up when followed by a cache delete.

1. The twins must match each other bit-for-bit every frame on the first
   walk (same Seed = same rain, per object; positions are read in emitter
   space so different world placements cannot mask a difference).
2. Scrubbing back and re-walking without any change must replay exactly,
   and forcing the modifiers to re-evaluate (node group reassign) must
   re-run the same sim bit-for-bit again.
3. Changing only emitter A's Seed (then dropping the cache, the order the
   probes proved necessary) must change its rain, while the untouched twin
   B still matches walk 1: seeds matter, nothing leaks between modifiers.
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

FRAMES = 16


def twin_world():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.fps = 24
    sc.frame_start, sc.frame_end = 1, FRAMES
    objs = []
    for loc in ((0.0, 0.0, 8.0), (4.0, 3.0, 8.0)):
        ob = em.create_emitter(sc, "heavy_rain")
        ob.location = loc
        em.apply_preset(ob, sc, "heavy_rain", quality=0.25, box=(10.0, 10.0, 8.0))
        mod = em.find_modifier(ob)
        assert compat.set_modifier_input(mod, "Output Mode", 1)
        assert compat.set_modifier_input(mod, "Viewport Density", 1.0)
        objs.append(ob)
    return sc, objs


def walk(sc, objs):
    """Sequential frame walk; per-frame position snapshot per emitter."""
    snaps = []
    for f in range(1, FRAMES + 1):
        sc.frame_set(f)
        snaps.append([T.read_state(o)["pos"].astype(np.float64).copy() for o in objs])
    return snaps


def reset_cache(objs):
    bpy.context.view_layer.objects.active = objs[0]
    for ob in objs:
        ob.select_set(True)
    with bpy.context.temp_override(selected_objects=list(objs)):
        bpy.ops.object.simulation_nodes_cache_delete()


def force_regroup(objs):
    """Reassign each modifier's node group so the sim restarts from frame 1."""
    for ob in objs:
        mod = em.find_modifier(ob)
        ng = mod.node_group
        mod.node_group = None
        mod.node_group = ng


def maxdiff(a, b):
    if a.shape != b.shape:
        return float("inf")
    if a.size == 0:
        return 0.0
    return float(np.abs(a - b).max())


def identical(snap_a, snap_b, label):
    """Frame-parallel snapshots: equal counts and bitwise-equal positions."""
    for f, (a, b) in enumerate(zip(snap_a, snap_b), start=1):
        d = maxdiff(a, b)
        assert d == 0.0, f"{label} frame {f}: shapes {a.shape} vs {b.shape}, maxdiff {d:.3e}"


def walk_eq(w1, w2, label):
    for f in range(FRAMES):
        identical([w1[f][0]], [w2[f][0]], f"{label} A")
        identical([w1[f][1]], [w2[f][1]], f"{label} B")


def main():
    sc, objs = twin_world()

    w1 = walk(sc, objs)
    n_min = min(s[0].shape[0] for s in w1)
    assert n_min > 100, f"anti-vacuous: too few primaries ({n_min})"

    scrub = walk(sc, objs)
    walk_eq(w1, scrub, "cache replay")

    force_regroup(objs)
    w2 = walk(sc, objs)
    walk_eq(w1, w2, "re-sim after group reassign")

    compat.set_modifier_input(em.find_modifier(objs[0]), "Seed", 7)
    reset_cache(objs)
    w3 = walk(sc, objs)

    changed = 0.0
    for f in range(FRAMES):
        identical([w1[f][1]], [w3[f][1]], "seeded twin control B")
        changed = max(changed, maxdiff(w1[f][0], w3[f][0]))
    assert changed > 0.5, f"seed 7 changed nothing (maxdiff {changed:.3e})"

    print("[Twin walks] %d frames, min primaries %d, fresh twins bit-identical" % (FRAMES, n_min))
    print("[Replay]     scrub-back walk identical; forced re-sim (group reassign) identical too")
    print("[Seeds]      seed 7 moved emitter A (max diff %.2f m), untouched twin B identical" % changed)
    print("PASS determinism (same seed = same rain, replay + re-sim exact, seeds matter)")


if __name__ == "__main__":
    main()
