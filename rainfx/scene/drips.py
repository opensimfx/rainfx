"""'RainFX Drips': find the edges rain drips from and set up the Drips layer.

A drip point sits on a roughly horizontal collider edge where an up-facing
face (which collects rain) meets a side or underside face, or the mesh ends:
roof and parapet edges, window sills, lamp heads, awnings, car roofs. It must
be open to the sky above that face, and have at least DRIP_MIN_FALL_M of open
air below it (a curb edge 15 cm above the road does not visibly drip). The
points are written to the hidden "RainFX Drips" mesh with their fall height,
period and phase; the "RainFX Drips" node group (gn/drips.py) animates the
drops as a pure function of time.

Drip points are found when the layer is refreshed (toggle, density, Apply):
after moving or editing colliders, refresh to move the drips with them.
"""
from __future__ import annotations

import random

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from .. import compat
from ..core import physics as P
from . import emitter as em

DRIPS_NAME = "RainFX Drips"
MAX_POINTS = 5000
UP_NZ = 0.7       # a face with normal z above this collects rain
SIDE_NZ = 0.3     # ... and one below this is a side or underside the water runs over
FLAT_EDGE = 0.2   # edges steeper than this (dz / length) are not drip edges


def _update_matrices() -> None:
    """World matrices are only current after a depsgraph update (a script may have just moved things)."""
    try:
        bpy.context.view_layer.update()
    except (AttributeError, RuntimeError):
        pass


def _colliders(scene) -> list:
    col = bpy.data.collections.get(em.COLLIDERS_NAME)
    return [o for o in col.objects if o.type == "MESH"] if col is not None else []


def _world_bmesh(obj):
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.transform(obj.matrix_world)
    bm.normal_update()
    return bm


def _bvh(colliders) -> BVHTree | None:
    verts, polys = [], []
    for o in colliders:
        mw = o.matrix_world
        base = len(verts)
        verts.extend(mw @ v.co for v in o.data.vertices)
        polys.extend([base + i for i in p.vertices] for p in o.data.polygons)
    return BVHTree.FromPolygons(verts, polys) if polys else None


def find_points(scene, rate_mm_h: float, density: float = 1.0, seed: int = 0,
                max_points: int = MAX_POINTS) -> list[tuple]:
    """[(position, fall, period, phase)] for every drip point of the colliders."""
    _update_matrices()
    colliders = _colliders(scene)
    tree = _bvh(colliders)
    if tree is None or density <= 0:
        return []
    rng = random.Random(seed * 7919 + 17)
    base_period = P.drip_period_s(rate_mm_h)
    spacing = P.DRIP_SPACING_M / density
    up = Vector((0.0, 0.0, 1.0))
    out = []
    for o in colliders:
        bm = _world_bmesh(o)
        try:
            for e in bm.edges:
                faces = list(e.link_faces)
                tops = [f for f in faces if f.normal.z > UP_NZ]
                if not tops:
                    continue
                sides = [f for f in faces if f.normal.z < SIDE_NZ]
                if not sides and len(faces) != 1:
                    continue
                a, b = e.verts[0].co.copy(), e.verts[1].co.copy()
                d = b - a
                length = d.length
                if length < 1e-4 or abs(d.z) > FLAT_EDGE * length:
                    continue
                top = tops[0]
                # outward: the side face's horizontal normal, else away from the top face
                if sides:
                    away = Vector((sides[0].normal.x, sides[0].normal.y, 0.0))
                else:
                    away = (a + b) * 0.5 - top.calc_center_median()
                    away.z = 0.0
                if away.length < 1e-6:
                    continue
                away.normalize()
                n = int(length / spacing + rng.random())
                for _ in range(n):
                    pt = a + d * rng.random()
                    # rain must reach the face this edge drains
                    on_top = pt - away * 0.03 + up * 0.01
                    if tree.ray_cast(on_top, up, 1000.0)[0] is not None:
                        continue
                    spot = pt + away * 0.004 - up * 0.004
                    hit = tree.ray_cast(spot - up * 0.002, -up, 1000.0)
                    if hit[0] is None or hit[3] < P.DRIP_MIN_FALL_M:
                        continue
                    out.append((tuple(spot), hit[3], base_period * rng.uniform(0.6, 1.6), rng.random()))
        finally:
            bm.free()
    if len(out) > max_points:
        out = rng.sample(out, max_points)
    return out


def _find_mod(obj):
    for m in obj.modifiers:
        if m.type == "NODES" and m.name == DRIPS_NAME:
            return m
    return None


def refresh(scene, enabled: bool, density: float = 1.0, seed: int = 0) -> int:
    """Create/update (rain presets) or remove the Drips layer; returns the drip-point count."""
    s = getattr(scene, "rainfx", None)
    p = em.all_presets().get(getattr(s, "preset", ""), None)
    if not enabled or p is None or p.mode != "rain":
        remove()
        return 0
    from ..gn import drips as gdrips
    from ..gn import materials
    pts = find_points(scene, p.rate_mm_h, density=density, seed=seed)
    obj = bpy.data.objects.get(DRIPS_NAME)
    if obj is None:
        obj = bpy.data.objects.new(DRIPS_NAME, bpy.data.meshes.new(DRIPS_NAME))
        em.ensure_collection(scene, em.ROOT_NAME).objects.link(obj)
        obj.visible_shadow = False
    me = obj.data
    me.clear_geometry()
    if pts:
        me.from_pydata([q[0] for q in pts], [], [])
    for name, i in (("fall", 1), ("period", 2), ("phase", 3)):
        attr = me.attributes.get(name) or me.attributes.new(name, "FLOAT", "POINT")
        if pts:
            attr.data.foreach_set("value", [q[i] for q in pts])
    me.update()
    obj.matrix_world.identity()
    mod = _find_mod(obj) or obj.modifiers.new(DRIPS_NAME, "NODES")
    mod.node_group = gdrips.ensure_group()
    S = lambda k, v: compat.set_modifier_input(mod, k, v)  # noqa: E731
    S("Drop Diameter", P.DRIP_D_MM)
    S("Terminal Speed", P.rain_terminal_velocity(P.DRIP_D_MM))
    S("Shutter", p.shutter_s)
    S("Visual Scale", p.visual_scale)
    S("Drip Material", materials.get_material("splash"))
    return len(pts)


def remove() -> bool:
    obj = bpy.data.objects.get(DRIPS_NAME)
    if obj is None:
        return False
    me = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if me is not None and me.users == 0:
        bpy.data.meshes.remove(me)
    return True
