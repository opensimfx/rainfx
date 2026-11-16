"""Hardening smoke: what has to hold for a stable release.

Checks (desktop Blender 5.2.3):
  1. [Reopen] wetness keeps accumulating after save + reopen: the impact
     handler is persistent, so a reopened file (or a command-line render)
     still feeds the helpers;
  2. [Transform] a moved, rotated and scaled collider gets wet where the
     rain lands (impacts are compared in the collider's own space);
  3. [Multi] two emitters both feed the impact carriers (world space);
  4. [Remap] rebuilding a stale node group keeps every user: two emitters
     on an old precipitation group both end up on the fresh one;
  5. [Shelter] ground under a roof stays dry while open ground beside it
     gets wet;
  6. [Watch] moving a collider queues a refresh: the shelter mesh and the
     drip points follow it (the timer is run by hand: no event loop here);
  7. [Unregister] disabling the add-on removes its handlers and timers.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

import bpy  # noqa: E402

import rainfx  # noqa: E402
from rainfx import compat  # noqa: E402
from rainfx.gn import precip  # noqa: E402
from rainfx.scene import emitter as em  # noqa: E402
from rainfx.scene import wetness as wet  # noqa: E402

import blender_wetness_smoke as W  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="rainfx_hard_"))


def walk(scene, frames):
    for f in range(scene.frame_start, scene.frame_start + frames):
        scene.frame_set(f)


def handler_on() -> bool:
    return any(getattr(h, "__name__", "") == "_on_frame" and "rainfx" in getattr(h, "__module__", "")
               for h in bpy.app.handlers.frame_change_post)


def carrier_count() -> int:
    ob = bpy.data.objects.get(wet.IMPACTS_NAME)
    return len(ob.data.vertices) if ob else -1


def max_wet(ob) -> float:
    vals = W.wet_values(ob)
    return max(vals) if vals else 0.0


def main() -> None:
    # ---------------------------------------------------------- 1. reopen
    scene, ground, cube, emitter = W.make_world()
    rainfx.register()
    wet.refresh(scene, True, radius=1.0, strength=0.9, dry_rate=0.0)
    scene.frame_set(1)
    path = TMP / "reopen.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(path))
    bpy.ops.wm.open_mainfile(filepath=str(path))
    assert handler_on(), "impact handler dropped when the file was reopened"
    scene = bpy.context.scene
    walk(scene, 24)
    n = carrier_count()
    w = max_wet(bpy.data.objects[W.CUBE])
    assert n > 0, "carrier stayed empty after reopening"
    assert w > 0.3, f"cube did not get wet after reopening (max {w:.3f})"
    print(f"[Reopen] handler survives load; {n} impacts on the last frame, cube wet {w:.2f}")

    # ------------------------------------------------------- 2. transform
    scene, ground, cube, emitter = W.make_world(box=(3, 3, 6))
    # the cube's own mesh sits at +/-1 m; the object is moved, turned and
    # scaled so local and world positions differ everywhere, and it only
    # rains over the moved cube: hits compared in the wrong space land ~5 m
    # from every cube vertex and wet nothing
    cube.location = (4.0, -3.0, 0.0)
    cube.rotation_euler = (0.0, 0.0, 0.6)
    cube.scale = (1.5, 1.5, 1.0)
    emitter.location = (4.0, -3.0, 0.0)
    wet.refresh(scene, True, radius=0.4, strength=0.9, dry_rate=0.0)
    walk(scene, 24)
    dg = bpy.context.evaluated_depsgraph_get()
    me = cube.evaluated_get(dg).to_mesh()
    attr = me.attributes["rainfx_wet"]
    top = [attr.data[li].value for poly in me.polygons if poly.normal.z > 0.5 for li in poly.loop_indices]
    cube.evaluated_get(dg).to_mesh_clear()
    assert top and min(top) > 0.3, f"transformed cube top not wet: {top}"
    print(f"[Transform] moved/rotated/scaled cube top wet {min(top):.2f}-{max(top):.2f}")

    # ----------------------------------------------------------- 3. multi
    scene, ground, cube, emitter = W.make_world(box=(8, 8, 6))
    emitter.location = (-12.0, 0.0, 0.0)
    e2 = em.create_emitter(scene, "heavy_rain", box=(8, 8, 6))
    e2.location = (12.0, 0.0, 0.0)
    wet.refresh(scene, True, radius=1.0, strength=0.9, dry_rate=0.0)
    walk(scene, 24)
    ob = bpy.data.objects[wet.IMPACTS_NAME]
    xs = [ob.matrix_world @ v.co for v in ob.data.vertices]
    left = sum(1 for v in xs if v.x < -6)
    right = sum(1 for v in xs if v.x > 6)
    assert left > 0 and right > 0, f"impacts from one emitter only (left {left}, right {right})"
    print(f"[Multi] carrier holds impacts from both emitters ({left} left, {right} right)")

    # ----------------------------------------------------------- 4. remap
    ng = bpy.data.node_groups[precip.GROUP_NAME]
    ng["rainfx_version"] = -1
    fresh = precip.ensure_group()
    users = [em.find_modifier(o).node_group for o in (emitter, e2)]
    assert all(g == fresh for g in users), f"stale rebuild dropped users: {users}"
    assert precip.GROUP_NAME in bpy.data.node_groups and fresh.name == precip.GROUP_NAME
    assert not any("(stale)" in g.name for g in bpy.data.node_groups), "stale group left behind"
    em.apply_preset(emitter, scene, "heavy_rain", box=(8, 8, 6))
    print("[Remap] both emitters moved onto the rebuilt group")

    # --------------------------------------------------------- 5. shelter
    scene, ground, cube, emitter = W.make_world(box=(12, 12, 8))
    bpy.data.objects.remove(cube)
    rm = bpy.data.meshes.new("Roof")
    rm.from_pydata([(-4, -4, 3), (4, -4, 3), (4, 4, 3), (-4, 4, 3)], [], [(0, 1, 2, 3)])
    roof = bpy.data.objects.new("Roof", rm)
    scene.collection.objects.link(roof)
    em.add_colliders(scene, [roof])
    # a fine ground so footprints resolve (vertices every 0.5 m over +/-6 m)
    gm = bpy.data.meshes.new("Fine")
    k = 25
    gm.from_pydata([(-6 + 12 * i / (k - 1), -6 + 12 * j / (k - 1), 0) for j in range(k) for i in range(k)], [],
                   [(j * k + i, j * k + i + 1, (j + 1) * k + i + 1, (j + 1) * k + i)
                    for j in range(k - 1) for i in range(k - 1)])
    fine = bpy.data.objects.new("Fine", gm)
    scene.collection.objects.link(fine)
    em.add_colliders(scene, [fine])
    bpy.data.objects.remove(ground)
    # still air: with wind, small slow drops really are blown under a roof edge.
    # The panel's Wind multiplier stills both the simulation and the ambient
    # wetness's rain direction.
    scene.rainfx.live_update = False
    scene.rainfx.wind_mult = 0.0
    em.apply_preset(emitter, scene, "heavy_rain", box=(12, 12, 8), wind_mult=0.0)
    compat.set_modifier_input(em.find_modifier(emitter), "Gust Strength", 0.0)
    wet.refresh(scene, True, radius=0.4, strength=0.9, dry_rate=0.0)
    walk(scene, 24)
    dg = bpy.context.evaluated_depsgraph_get()
    me = fine.evaluated_get(dg).to_mesh()
    a = me.attributes["rainfx_wet"]
    under, open_ = [], []
    for poly in me.polygons:
        c = poly.center
        v = max(a.data[li].value for li in poly.loop_indices)
        if abs(c.x) < 2.5 and abs(c.y) < 2.5:
            under.append(v)       # well inside the roof's 4 m half-width
        elif abs(c.x) > 4.5 or abs(c.y) > 4.5:
            open_.append(v)
    fine.evaluated_get(dg).to_mesh_clear()
    wet_open = sum(1 for v in open_ if v > 0.3) / len(open_)
    assert max(under) < 0.05, f"ground under the roof got wet (max {max(under):.3f})"
    assert wet_open > 0.5, f"open ground stayed dry ({wet_open:.0%} wet)"
    print(f"[Shelter] under the roof max wet {max(under):.3f}; open ground {wet_open:.0%} wet")

    # ----------------------------------------------------------- 6. watch
    from rainfx.scene import drips, watch
    scene.rainfx.preset = "heavy_rain"
    scene.rainfx.wetness = True
    scene.rainfx.drips = True
    dr = bpy.data.objects[drips.DRIPS_NAME]
    before = max(v.co.z for v in dr.data.vertices)
    roof.location.z += 1.0
    bpy.context.view_layer.update()            # fires depsgraph_update_post like an edit would
    assert scene.name in watch._pending and bpy.app.timers.is_registered(watch._refresh), \
        "moving a collider did not queue a refresh"
    bpy.app.timers.unregister(watch._refresh)
    watch._refresh()
    after = max(v.co.z for v in bpy.data.objects[drips.DRIPS_NAME].data.vertices)
    shelter_top = max(v.co.z for v in bpy.data.objects[wet.SHELTER_NAME].data.vertices)
    assert abs(after - before - 1.0) < 0.02 and abs(shelter_top - 4.0) < 1e-4, (before, after, shelter_top)
    bpy.context.view_layer.update()
    assert not watch._pending, "the refresh re-triggered itself"
    print(f"[Watch] roof moved up 1 m: drips {before:.2f} -> {after:.2f} m, shelter top {shelter_top:.2f} m, "
          "no self-trigger")

    # ------------------------------------------------------ 7. unregister
    rainfx.unregister()
    assert not handler_on(), "frame handler left behind after unregister"
    from rainfx.ui import ops
    assert not bpy.app.timers.is_registered(ops._bg_tick), "bake timer left behind"
    assert not any(getattr(h, "__name__", "") == "_on_depsgraph" for h in bpy.app.handlers.depsgraph_update_post), \
        "collider watcher left behind"
    print("[Unregister] handlers and timers removed")
    print("PASS hardening smoke")


main()
