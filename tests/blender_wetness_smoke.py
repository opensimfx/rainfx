"""Wetness smoke: impacts wet the collider faces through the helper modifier.

World: 30 m subdivided ground plane + solid 2 m cube. Rain above the cube
stamps wetness onto BOTH objects' faces near the hit points; faces far from
any impact stay dry.

Checks (headless, Blender 5.2.1):
  1. helper group builds, two helpers attach, Emitter socket wired;
  2. before any rain the attribute is all zero;
  3. after 24 frames some faces carry rainfx_wet above 0.3 while other faces
     of the ground stay below 0.05;
  4. pools: rainfx_pool fills on flat up-facing faces (ground + cube top)
     but the cube's vertical sides stay un-pooled (flatness gate);
  5. toggling wetness off removes every RainFX Wetness modifier;
  6. material wiring: wet + pool + snow attribute links, ripple bump nodes
     and the frame driver wired exactly once;
  7. a light_snow world accumulates rainfx_snow on up-facing verts and the
     post-sim Set Position lifts cube tops by Snow Depth x snow.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

import bpy  # noqa: E402

from rainfx import compat  # noqa: E402
from rainfx.gn import materials  # noqa: E402
from rainfx.scene import emitter as em  # noqa: E402
from rainfx.scene import wetness as wet  # noqa: E402

GROUND = "Ground"
CUBE = "Cube"
N = 12  # ground grid resolution (N x N quads, ~2.5 m each on +/-30 m span)


def make_world(preset: str = "heavy_rain", box=None, quality=None):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = 24
    scene.frame_start, scene.frame_end = 1, 24
    verts, faces = [], []
    k = N + 1
    for j in range(k):
        for i in range(k):
            verts.append((-30.0 + 60.0 * i / N, -30.0 + 60.0 * j / N, 0.0))
    for j in range(N):
        for i in range(N):
            a = j * k + i
            faces.append((a, a + 1, a + k + 1, a + k))
    me = bpy.data.meshes.new(GROUND)
    me.from_pydata(verts, [], faces)
    ground = bpy.data.objects.new(GROUND, me)
    scene.collection.objects.link(ground)
    cm = bpy.data.meshes.new(CUBE)
    cm.from_pydata(((-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0),
                    (-1, -1, 2), (1, -1, 2), (1, 1, 2), (-1, 1, 2)),
                   [], [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5),
                        (2, 3, 7, 6), (3, 0, 4, 7)])
    cube = bpy.data.objects.new(CUBE, cm)
    scene.collection.objects.link(cube)
    em.add_colliders(scene, [ground, cube])
    mat = bpy.data.materials.new("Matte")
    mat.use_nodes = True
    for ob in (ground, cube):
        ob.data.materials.append(mat)
    kw = {}
    if box is not None:
        kw["box"] = box
    if quality is not None:
        kw["quality"] = quality
    emitter = em.create_emitter(scene, preset, **kw)
    return scene, ground, cube, emitter


def wet_values(ob) -> list[float]:
    dg = bpy.context.evaluated_depsgraph_get()
    me = ob.evaluated_get(dg).to_mesh()
    attr = me.attributes.get("rainfx_wet")
    vals = [d.value for d in attr.data] if attr is not None else []
    ob.evaluated_get(dg).to_mesh_clear()
    return vals


def pool_splits(ob):
    """Return (pool values on up faces, pool values on non-up faces)."""
    dg = bpy.context.evaluated_depsgraph_get()
    me = ob.evaluated_get(dg).to_mesh()
    attr = me.attributes.get("rainfx_pool")
    pools = [d.value for d in attr.data] if attr is not None else []
    ups, downs = [], []
    for i, poly in enumerate(me.polygons):
        (ups if poly.normal.z > 0.5 else downs).append(pools[i])
    ob.evaluated_get(dg).to_mesh_clear()
    return ups, downs


def zmax(ob) -> float:
    """Highest evaluated vertex z (original factory z was 2.0 for cube tops)."""
    dg = bpy.context.evaluated_depsgraph_get()
    me = ob.evaluated_get(dg).to_mesh()
    zs = [v.co.z for v in me.vertices]
    ob.evaluated_get(dg).to_mesh_clear()
    return max(zs) if zs else float("nan")


def snow_values(ob) -> list[float]:
    dg = bpy.context.evaluated_depsgraph_get()
    me = ob.evaluated_get(dg).to_mesh()
    attr = me.attributes.get("rainfx_snow")
    vals = [d.value for d in attr.data] if attr is not None else []
    ob.evaluated_get(dg).to_mesh_clear()
    return vals


def main() -> None:
    scene, ground, cube, emitter = make_world()

    # [Build] helper modifiers attached by the toggle path
    n = wet.refresh(scene, True, radius=1.0, strength=0.9, dry_rate=0.0)
    wmod_ground = wet._find_wet_mod(ground)
    wmod_cube = wet._find_wet_mod(cube)
    assert n == 2 and wmod_ground is not None and wmod_cube is not None, \
        f"helpers not attached (n={n})"
    assert compat.get_modifier_input(wmod_ground, "Emitter") == bpy.data.objects.get("RainFX Impacts"), \
        "helper Emitter socket should hold the RainFX Impacts carrier"
    print(f"[Build] {n} helpers attached, Emitter wired OK")

    # [Control] before any rain: attribute must be all zero (or absent)
    bpy.context.view_layer.update()
    v0 = wet_values(ground)
    assert v0 and all(abs(a) < 1e-4 for a in v0), \
        f"ground faces wet before rain (max {max(v0, default=-1):.4f})"
    print(f"[Control] dry baseline OK ({len(v0)} faces)")

    # [Wet] walk 24 frames; hit areas get wet, the ground's far side stays dry
    for f in range(1, 25):
        scene.frame_set(f)
    gvals = wet_values(ground)
    cvals = wet_values(cube)
    gw = max(gvals) if gvals else -1.0
    cw = max(cvals) if cvals else -1.0
    assert gw > 0.3, f"ground never got wet (max {gw:.4f})"
    assert cw > 0.3, f"cube never got wet (max {cw:.4f})"
    far = [a for a in gvals if a < 0.05]
    assert len(far) >= max(1, len(gvals) // 3), \
        f"whole ground uniformly wet (only {len(far)}/{len(gvals)} dry faces)"
    print(f"[Wet] ground max {gw:.3f}, cube max {cw:.3f}, "
          f"far faces {len(far)}/{len(gvals)} <= 0.05")

    # [Puddles] pool fills on flat up-facing spots, not on vertical walls
    gu, _gd = pool_splits(ground)
    cu, cs = pool_splits(cube)
    gpu = max(gu) if gu else -1.0
    cpu = max(cu) if cu else -1.0
    cside = max(cs) if cs else -1.0
    assert gpu > 0.3, f"ground never pooled (max {gpu:.4f})"
    # 0.303 pre-splash-imp-leak was splash-inflated; honest pool tops out ~0.285
    assert cpu > 0.25, f"cube top never pooled (max {cpu:.4f})"
    assert cside < 0.05, f"cube walls pooled (max {cside:.4f})"
    print(f"[Puddles] ground max {gpu:.3f}, cube top {cpu:.3f}, "
          f"cube walls max {cside:.3f} (flat/up gating OK)")

    # [Rain inert] no snow mode: snow attr stays 0, no lift on cube tops
    ct = zmax(cube)
    assert abs(ct - 2.0) < 5e-3, f"rain world displaced cube tops (z {ct:.4f})"
    print(f"[Rain inert] cube top z {ct:.4f} (no snow lift in rain mode)")

    # [Toggle off] removes every helper
    n = wet.refresh(scene, False)
    assert n == 2 and wet._find_wet_mod(ground) is None and \
        wet._find_wet_mod(cube) is None, "toggle-off left helpers"
    print(f"[Toggle] removed {n} helpers")

    # [Material] wet wiring idempotent (fresh mat; slot mats got wired in [Build])
    mat = bpy.data.materials.new("FreshMat")
    mat.use_nodes = True
    first = materials.wire_wetness(mat)
    second = materials.wire_wetness(mat)
    assert first is True and second is False, \
        f"wet wiring not idempotent ({first}, {second})"
    types = [n.type for n in mat.node_tree.nodes]
    assert types.count("ATTRIBUTE") >= 3, "wet+pool+snow Attribute nodes missing"
    assert types.count("TEX_NOISE") >= 1 and types.count("BUMP") >= 1, \
        "ripple bump chain missing"
    ad = mat.node_tree.animation_data
    dj = [(fc.data_path, fc.driver.expression) for fc in (ad.drivers if ad else [])]
    assert any("frame" in expr for _p, expr in dj), \
        f"ripple time driver missing ({dj})"
    print("[Material] wet links wired once, ripple bump + frame driver present")

    # [Snow] a light_snow world accumulates flakes and lifts up-facing verts
    # compact box: the top is 4/16 of the footprint and flakes fall from just
    # ~1 m above it, so top strikes are frequent (a big box starves the top:
    # 4 m^2 of 144 m^2 footprint at ~1 m/s fall speed - dbg_census fact)
    scene2, ground2, cube2, _em2 = make_world("light_snow", box=(4, 4, 3), quality=1.0)
    n = wet.refresh(scene2, True, radius=1.0, strength=0.9, dry_rate=0.0)
    assert n == 2, f"snow world helpers missing (n={n})"
    compat.set_modifier_input(wet._find_wet_mod(ground2), "Snow Rate", 1.0)
    compat.set_modifier_input(wet._find_wet_mod(cube2), "Snow Rate", 1.0)
    # GN sim zones stop stepping past the scene range (frames beyond frame_end
    # replay the last cached state), so the walk length must fit frame_end
    scene2.frame_start, scene2.frame_end = 1, 97
    # light_snow falls ~1 m/s: the 2 m cube top needs >2 s of falling before
    # the first flake lands on it, so walk 4 s here (the rain sections use 1 s)
    for f in range(1, 97):
        scene2.frame_set(f)
    gs = snow_values(ground2)
    cs = snow_values(cube2)
    gsw = max(gs) if gs else -1.0
    csw = max(cs) if cs else 0.0
    assert gsw > 0.2, f"ground snow never accumulated (max {gsw:.4f})"
    assert csw > 0.2, f"cube top snow never accumulated (max {csw:.4f})"
    ct2 = zmax(cube2)
    assert ct2 > 2.005, f"cube top not lifted by snow (z {ct2:.4f})"
    print(f"[Snow] ground {gsw:.3f}, cube top {csw:.3f}, cube top z {ct2:.4f} (lifted)")

    print("PASS wetness smoke")


if __name__ == "__main__":
    main()
