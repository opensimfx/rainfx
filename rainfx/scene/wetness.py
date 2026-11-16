"""Per-collider wetness: add/remove the "RainFX Wetness" helper modifier.

The helper GN group (rainfx/gn/wetness.py) accumulates face-corner
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
SHELTER_NAME = "RainFX Shelter"


def _point_mask(me, name):
    """Boolean per-vertex mask of a POINT attribute (> 0.5), or None."""
    import numpy as np
    a = me.attributes.get(name)
    if a is None or a.domain != "POINT":
        return None
    n = len(me.vertices)
    if a.data_type == "BOOLEAN":
        arr = np.zeros(n, dtype=bool)
        a.data.foreach_get("value", arr)
        return arr
    if a.data_type in ("FLOAT", "INT", "INT8"):
        arr = np.zeros(n, dtype=np.float32 if a.data_type == "FLOAT" else np.int32)
        a.data.foreach_get("value", arr)
        return arr > 0.5
    return None


def _impact_points(scene, depsgraph=None):
    """World-space (rain, snow) impact positions of every emitter in ``scene``.

    Uses the depsgraph the handler was given (the render's during a render, so
    full render density, not the viewport's reduced Viewport Density).
    """
    import numpy as np
    dg = depsgraph if depsgraph is not None else bpy.context.evaluated_depsgraph_get()
    rain, snow = [], []
    for et in _emitters(scene):
        ev = et.evaluated_get(dg)
        me = ev.to_mesh()
        try:
            if me is None or not len(me.vertices):
                continue
            imp = _point_mask(me, "imp")
            if imp is None or not imp.any():
                continue
            co = np.zeros(len(me.vertices) * 3, dtype=np.float32)
            me.vertices.foreach_get("co", co)
            co = co.reshape(-1, 3)
            m = np.array(et.matrix_world, dtype=np.float32)
            world = co @ m[:3, :3].T + m[:3, 3]
            flake = _point_mask(me, "snow")
            is_snow = imp & flake if flake is not None else np.zeros_like(imp)
            rain.append(world[imp & ~is_snow])
            snow.append(world[is_snow])
        finally:
            ev.to_mesh_clear()
    cat = lambda parts: np.concatenate(parts) if parts else np.zeros((0, 3), np.float32)  # noqa: E731
    return cat(rain), cat(snow)


def _fill(carrier, pts) -> None:
    from mathutils import Matrix
    me = carrier.data
    me.clear_geometry()
    if len(pts):
        me.vertices.add(len(pts))
        me.vertices.foreach_set("co", pts.ravel())
    me.update()
    if carrier.matrix_world != Matrix.Identity(4):
        carrier.matrix_world = Matrix.Identity(4)


@bpy.app.handlers.persistent
def _on_frame(scene, depsgraph=None) -> None:
    """frame_change_post: copy every emitter's impact points into the carriers.

    The helpers read the carriers via ObjectInfo instead of the emitter
    itself: an ObjectInfo pointing back at the emitter closes a dependency
    cycle the depsgraph breaks by serving empty geometry (two or more
    helpers => every helper gets nothing). Impacts are split by the named
    'snow' flag into the rain carrier (wet/pool) and the snow carrier
    (flake accumulation). Points are stored in world space, so several
    emitters (and follow-mounted ones) feed the same carriers.

    Persistent and registered with the add-on, so wetness keeps
    accumulating after a file is reopened and in command-line renders.
    """
    ob = bpy.data.objects.get(IMPACTS_NAME)
    sob = bpy.data.objects.get(SNOW_IMPACTS_NAME)
    if ob is None and sob is None:
        return
    rain, snow = _impact_points(scene, depsgraph)
    for tgt, pts in ((ob, rain), (sob, snow)):
        if tgt is not None:
            _fill(tgt, pts)


def _ensure_handler(on: bool) -> None:
    hs = bpy.app.handlers.frame_change_post
    if on and _on_frame not in hs:
        hs.append(_on_frame)
    elif not on and _on_frame in hs:
        hs.remove(_on_frame)


def register() -> None:
    """Attach the impact-carrier handler for the add-on's lifetime."""
    _ensure_handler(True)


def unregister() -> None:
    # remove by name too: a reloaded module leaves the old function object behind
    hs = bpy.app.handlers.frame_change_post
    for h in list(hs):
        if getattr(h, "__module__", "") == __name__ and getattr(h, "__name__", "") == "_on_frame":
            hs.remove(h)


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


def _emitters(scene: bpy.types.Scene) -> list:
    return [o for o in scene.objects if em.is_emitter(o)]


def _emitter(scene: bpy.types.Scene):
    found = _emitters(scene)
    return found[0] if found else None


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
    _ensure_handler(True)
    if carrier is not None:
        _on_frame(scene)  # seed the carriers so frame 1 already sees impacts
    build_shelter(scene)
    amb = ambient_inputs(scene)
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
        from mathutils import Vector
        to_local = o.matrix_world.inverted().to_3x3()   # the shelter is read RELATIVE
        for k, v in amb.items():
            if k == "Rain Direction":
                v = tuple((to_local @ Vector(v)).normalized())
            S(k, v)
        if amb:
            S("Sky Direction", tuple((to_local @ Vector((0.0, 0.0, 1.0))).normalized()))
        for slot in o.material_slots:
            if slot.material is not None:
                from ..gn import materials
                materials.wire_wetness(slot.material)
        n += 1
    scene[COARSE_KEY] = coarse_colliders(scene, radius)   # shown as a hint in the Collisions panel
    from ..core import presets as presets_mod
    p = em.all_presets().get(getattr(getattr(scene, "rainfx", None), "preset", ""), None)
    if p is not None:
        from ..gn import materials
        materials.set_ripple_weight(presets_mod.ripple_weight_for(p))
    return n


def build_shelter(scene: bpy.types.Scene):
    """(Re)build the hidden world-space copy of every collider (exposure target).

    A plain mesh object outside the colliders collection, so the wetness
    helpers can raycast against all colliders without depending on any of
    them. Rebuilt on every wetness refresh; move a collider, then refresh
    (any wetness setting, or Apply) to update the sheltering.
    """
    import bmesh
    try:
        bpy.context.view_layer.update()   # world matrices are current only after an update
    except (AttributeError, RuntimeError):
        pass
    ob = bpy.data.objects.get(SHELTER_NAME)
    if ob is None:
        me = bpy.data.meshes.new(SHELTER_NAME)
        ob = bpy.data.objects.new(SHELTER_NAME, me)
        ob.hide_viewport = True
        ob.hide_render = True
        scene.collection.objects.link(ob)
    bm = bmesh.new()
    for o in _collider_objects(scene):
        tmp = o.data.copy()
        tmp.transform(o.matrix_world)
        bm.from_mesh(tmp)
        bpy.data.meshes.remove(tmp)
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()
    ob.matrix_world.identity()
    return ob


def ambient_inputs(scene: bpy.types.Scene) -> dict:
    """Ambient-wetness modifier inputs from the scene preset and the panel.

    Every surface the rain can reach is wet (Ambient Wet, by preset), exposed
    flat ground holds standing water that the shader floods into puddles
    (Ambient Pool x the Puddles slider), and with *Already Wet* off the
    exposed surfaces wet up over Wet Up Time instead of starting wet.
    """
    from ..core import presets as presets_mod
    s = getattr(scene, "rainfx", None)
    p = em.all_presets().get(getattr(s, "preset", ""), None)
    if p is None:
        return {}
    return {
        "Shelter": bpy.data.objects.get(SHELTER_NAME),
        "Rain Direction": presets_mod.rain_direction_for(p, float(getattr(s, "wind_mult", 1.0))),
        "Ambient Wet": presets_mod.ambient_wet_for(p),
        "Ambient Pool": min(1.0, presets_mod.ambient_pool_for(p) * float(getattr(s, "puddles", 1.0))),
        "Wet Up Time": 0.0 if getattr(s, "wet_start", True) else presets_mod.wet_up_time_for(p),
        "Ambient Snow": presets_mod.ambient_snow_for(p),
    }


def helpers(scene: bpy.types.Scene) -> list:
    """(object, modifier) for every collider carrying a wetness helper."""
    out = []
    for o in _collider_objects(scene):
        m = _find_wet_mod(o)
        if m is not None:
            out.append((o, m))
    return out


def helper_bake_dir(base: str, obj) -> str:
    """Per-object cache folder under the emitter's bake folder (bake ids are per node, not unique across objects)."""
    import os
    return os.path.join(base, "wetness", bpy.path.clean_name(obj.name))


def prepare_bake(mod, target: str, directory: str | None, frame_start: int, frame_end: int) -> None:
    """Point a wetness helper's simulation bake at the same range and target as the emitter's."""
    mod.bake_target = target
    if directory:
        mod.bake_directory = directory
    for b in mod.bakes:
        b.use_custom_simulation_frame_range = True
        b.frame_start, b.frame_end = int(frame_start), int(frame_end)


COARSE_KEY = "rainfx_coarse_colliders"
COARSE_FACTOR = 4.0   # an edge longer than 4 x Wet Radius cannot show a footprint


def coarse_colliders(scene: bpy.types.Scene, radius: float) -> list[str]:
    """Colliders whose longest edge (world scale) is over COARSE_FACTOR x ``radius``.

    Wetness is stored on the mesh (per face corner), so a surface needs
    vertices about every Wet Radius to show where rain lands and where it is
    sheltered; a single big quad only gets one value per corner.
    """
    out = []
    lim = COARSE_FACTOR * max(radius, 1e-4)
    for o in _collider_objects(scene):
        me = o.data
        if not me.edges:
            continue
        sx, sy, sz = (abs(c) for c in o.matrix_world.to_scale())
        longest = 0.0
        for e in me.edges:
            a, b = me.vertices[e.vertices[0]].co, me.vertices[e.vertices[1]].co
            d = ((sx * (a.x - b.x)) ** 2 + (sy * (a.y - b.y)) ** 2 + (sz * (a.z - b.z)) ** 2) ** 0.5
            if d > longest:
                longest = d
                if longest > lim:
                    break
        if longest > lim:
            out.append(o.name)
    return out


def remove(scene: bpy.types.Scene) -> int:
    n = 0
    for o in _collider_objects(scene):
        for m in list(o.modifiers):
            if m.type == "NODES" and m.name == WET_MOD_NAME:
                o.modifiers.remove(m)
                n += 1
    if COARSE_KEY in scene:
        del scene[COARSE_KEY]
    if n:
        me_del = []
        for name in (IMPACTS_NAME, SNOW_IMPACTS_NAME, SHELTER_NAME):
            ob = bpy.data.objects.get(name)
            if ob is not None:
                me_del.append(ob.data)
                bpy.data.objects.remove(ob)
        for me in me_del:
            bpy.data.meshes.remove(me)
    return n
