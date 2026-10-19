"""Per-collider wetness: add/remove the "RainFX Wetness" helper modifier.

The helper GN group (rainfx/gn/wetness.py) accumulates per-face
"rainfx_wet"/"rainfx_pool" and per-vertex "rainfx_snow" attributes driven by
impact streams. The streams are not the emitter itself but hidden "RainFX
Impacts" / "RainFX Snow Impacts" carrier objects refreshed by a
frame_change_post handler (snowflakes land in the second one); ObjectInfo
back to the emitter closes a dependency cycle the depsgraph breaks by
serving empty geometry once two or more helpers read it. Wet state lives in
each helper's sim zone and stays bake-safe; the handler only feeds the
input.
"""
from __future__ import annotations

import bpy

from .. import compat
from ..gn import wetness
from . import emitter as em

WET_MOD_NAME = "RainFX Wetness"
IMPACTS_NAME = "RainFX Impacts"
SNOW_IMPACTS_NAME = "RainFX Snow Impacts"


def _on_frame(scene) -> None:
    """frame_change_post: copy the emitter's impact verts into the carriers.

    The helpers read the carriers via ObjectInfo instead of the emitter
    itself: an ObjectInfo pointing back at the emitter closes a dependency
    cycle the depsgraph breaks by serving empty geometry (two or more
    helpers => every helper gets nothing). Impacts are split by the named
    'snow' flag into the rain carrier (wet/pool) and the snow carrier
    (flake accumulation).
    """
    ob = bpy.data.objects.get(IMPACTS_NAME)
    sob = bpy.data.objects.get(SNOW_IMPACTS_NAME)
    et = _emitter(scene)
    if ob is None and sob is None:
        return
    if et is None:
        return
    dg = bpy.context.evaluated_depsgraph_get()
    me = et.evaluated_get(dg).to_mesh()
    try:
        imp = me.attributes.get("imp") if me else None
        snow = me.attributes.get("snow") if me else None
        rain_pts, flake_pts = [], []
        if imp is not None:
            sv = snow.data if snow is not None else None
            for i, (v, d) in enumerate(zip(me.vertices, imp.data)):
                if d.value > 0.5:
                    if sv is not None and sv[i].value > 0.5:
                        flake_pts.append(v.co[:])
                    else:
                        rain_pts.append(v.co[:])
    finally:
        et.evaluated_get(dg).to_mesh_clear()
    for tgt, pts in ((ob, rain_pts), (sob, flake_pts)):
        if tgt is None:
            continue
        cd = tgt.data
        cd.clear_geometry()
        if pts:
            cd.from_pydata(pts, [], [])
        cd.update()
        tgt.matrix_world = et.matrix_world


def _ensure_handler(on: bool) -> None:
    hs = bpy.app.handlers.frame_change_post
    if on and _on_frame not in hs:
        hs.append(_on_frame)
    elif not on and _on_frame in hs:
        hs.remove(_on_frame)


def ensure_carriers(scene: bpy.types.Scene):
    """Hidden plain-mesh objects the helpers read their impacts from.

    Returns (rain_carrier, snow_carrier) — both always created together so
    the handler can fill either one.
    """
    out = []
    for name in (IMPACTS_NAME, SNOW_IMPACTS_NAME):
        ob = bpy.data.objects.get(name)
        if ob is None:
            me = bpy.data.meshes.new(name)
            ob = bpy.data.objects.new(name, me)
            ob.hide_viewport = True
            ob.hide_render = True
            scene.collection.objects.link(ob)
        out.append(ob)
    return tuple(out)


def ensure_carrier(scene: bpy.types.Scene):  # legacy single name kept for back-compat
    """Deprecated alias: the helpers now read two carriers."""
    carrier, snow = ensure_carriers(scene)
    return carrier


def _collider_objects(scene: bpy.types.Scene) -> list[bpy.types.Object]:
    col = bpy.data.collections.get(em.COLLIDERS_NAME)
    if col is None:
        return []
    return [o for o in col.objects if o.type == "MESH"]


def _emitter(scene: bpy.types.Scene):
    for o in scene.objects:
        if em.is_emitter(o):
            return o
    return None


def _find_wet_mod(obj) -> bpy.types.NodesModifier | None:
    for m in obj.modifiers:
        if m.type == "NODES" and m.name == WET_MOD_NAME:
            return m
    return None


def refresh(scene: bpy.types.Scene, enabled: bool, radius: float = 0.2,
            strength: float = 0.5, dry_rate: float = 0.02) -> int:
    """Enable or remove the helper on every collider; returns touched count."""
    if not enabled:
        return remove(scene)
    group = wetness.ensure_group()
    src = _emitter(scene)
    carrier, snowcarrier = ensure_carriers(scene) if src is not None else (None, None)
    _ensure_handler(src is not None)
    if carrier is not None:
        _on_frame(scene)  # seed the carriers so frame 1 already sees impacts
    n = 0
    for o in _collider_objects(scene):
        mod = _find_wet_mod(o)
        if mod is None:
            mod = o.modifiers.new(WET_MOD_NAME, "NODES")
            o.modifiers.move(len(o.modifiers) - 1, 0)  # before user modifiers
        if mod.node_group != group:
            mod.node_group = group
        S = lambda k, v: compat.set_modifier_input(mod, k, v)  # noqa: E731
        # NOTE: the group's single "Geometry" input stays unlinked on purpose;
        # a modifier feeds its own object's mesh into the first geometry input.
        S("Emitter", carrier if carrier is not None else src)
        S("Snow Impacts", snowcarrier if snowcarrier is not None else src)
        S("Wet Radius", radius)
        S("Strength", strength)
        S("Dry Rate", dry_rate)
        for slot in o.material_slots:
            if slot.material is not None:
                from ..gn import materials
                materials.wire_wetness(slot.material)
        n += 1
    return n


def remove(scene: bpy.types.Scene) -> int:
    n = 0
    for o in _collider_objects(scene):
        for m in list(o.modifiers):
            if m.type == "NODES" and m.name == WET_MOD_NAME:
                o.modifiers.remove(m)
                n += 1
    if n:
        _ensure_handler(False)
        me_del = []
        for name in (IMPACTS_NAME, SNOW_IMPACTS_NAME):
            ob = bpy.data.objects.get(name)
            if ob is not None:
                me_del.append(ob.data)
                bpy.data.objects.remove(ob)
        for me in me_del:
            bpy.data.meshes.remove(me)
    return n
