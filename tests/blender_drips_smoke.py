"""Drips smoke: drops fall from exposed edges with open air below them.

World: 20 m ground grid, a floating 4 x 4 m roof slab (top at 3 m), a ledge
tucked under the roof (top at 2 m) and a 15 cm curb out in the open.

Checks (desktop Blender 5.2.3):
  1. drip points line the roof's edge only: none on the covered ledge (no
     rain reaches it), none on the curb (too little open air below) and none
     on the ground grid's border (nothing below it);
  2. each point's fall height is the open air down to the ground (~3 m);
  3. falling drops stay between the roof edge and the ground, and the layer
     is a pure function of time (same frame -> same drops);
  4. heavier rain drips faster (shorter periods);
  5. a snow preset and the toggle both remove the layer.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

import bpy  # noqa: E402

import rainfx  # noqa: E402
from rainfx.scene import drips  # noqa: E402
from rainfx.scene import emitter as em  # noqa: E402


def box(name, size, loc):
    me = bpy.data.meshes.new(name)
    sx, sy, sz = (s / 2 for s in size)
    v = [(x, y, z) for x in (-sx, sx) for y in (-sy, sy) for z in (-sz, sz)]
    f = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    me.from_pydata(v, [], f)
    ob = bpy.data.objects.new(name, me)
    ob.location = loc
    bpy.context.scene.collection.objects.link(ob)
    return ob


def grid(name, size, n):
    me = bpy.data.meshes.new(name)
    k = n + 1
    me.from_pydata([(-size / 2 + size * i / n, -size / 2 + size * j / n, 0.0) for j in range(k) for i in range(k)],
                   [], [(j * k + i, j * k + i + 1, (j + 1) * k + i + 1, (j + 1) * k + i)
                        for j in range(n) for i in range(n)])
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def drops(sc):
    dg = bpy.context.evaluated_depsgraph_get()
    obj = bpy.data.objects[drips.DRIPS_NAME]
    out = []
    for inst in dg.object_instances:
        if inst.is_instance and inst.parent and inst.parent.original == obj:
            out.append(tuple(round(c, 5) for c in inst.matrix_world.translation))
    return sorted(out)


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    rainfx.register()
    sc = bpy.context.scene
    sc.render.fps = 24
    ground = grid("Ground", 20.0, 20)
    roof = box("Roof", (4.0, 4.0, 0.2), (0.0, 0.0, 2.9))
    ledge = box("Ledge", (1.0, 1.0, 0.1), (0.5, 0.5, 1.95))
    curb = box("Curb", (6.0, 0.2, 0.15), (0.0, 7.0, 0.075))
    em.add_colliders(sc, [ground, roof, ledge, curb])
    sc.rainfx.preset = "heavy_rain"
    em.create_emitter(sc, "heavy_rain")
    sc.rainfx.drips = True

    obj = bpy.data.objects.get(drips.DRIPS_NAME)
    assert obj is not None, "drips layer not created"
    pts = [v.co.copy() for v in obj.data.vertices]
    falls = [d.value for d in obj.data.attributes["fall"].data]
    assert len(pts) >= 30, f"too few drip points on a 16 m roof edge: {len(pts)}"
    for p in pts:
        on_edge = abs(abs(p.x) - 2.0) < 0.02 or abs(abs(p.y) - 2.0) < 0.02
        assert on_edge and 2.95 < p.z < 3.0, f"drip point off the roof edge: {tuple(p)}"
    assert all(2.9 < f < 3.0 for f in falls), f"fall heights {min(falls):.2f}-{max(falls):.2f}"
    print(f"[Points] {len(pts)} drip points, all on the roof edge (ledge, curb, ground border: none); "
          f"fall {min(falls):.2f}-{max(falls):.2f} m")

    sc.frame_set(37)
    a = drops(sc)
    sc.frame_set(12)
    sc.frame_set(37)
    b = drops(sc)
    assert a and a == b, "drips differ on the same frame (must be a pure function of time)"
    zs = [p[2] for p in a]
    assert min(zs) > 0.0 and max(zs) < 3.0, f"drops outside roof..ground: {min(zs):.2f}-{max(zs):.2f}"
    print(f"[Fall] {len(a)} drops and beads between {min(zs):.2f} and {max(zs):.2f} m; same frame, same drops")

    heavy = sum(d.value for d in obj.data.attributes["period"].data) / len(pts)
    sc.rainfx.preset = "light_rain"
    drips.refresh(sc, True, seed=0)
    light = sum(d.value for d in obj.data.attributes["period"].data) / len(obj.data.vertices)
    assert heavy < light, (heavy, light)
    print(f"[Rate] mean period heavy {heavy:.2f} s < light {light:.2f} s")

    sc.rainfx.preset = "light_snow"
    drips.refresh(sc, True)
    assert bpy.data.objects.get(drips.DRIPS_NAME) is None, "snow preset kept the drips"
    sc.rainfx.preset = "heavy_rain"
    drips.refresh(sc, True)
    sc.rainfx.drips = False
    assert bpy.data.objects.get(drips.DRIPS_NAME) is None, "toggle off kept the drips"
    print("[Remove] snow and the toggle remove the layer")
    print("PASS drips smoke")


main()
