"""Keep wetness sheltering and drip points in step with the colliders.

Exposure (ambient wetness) and drip points are computed from the colliders'
geometry. A persistent depsgraph handler notices when a collider is moved,
its mesh edited, or the collider set changed, and refreshes both after a
short pause (debounced with a timer), so a user never has to remember to.

Not during playback or rendering, not in Edit Mode (the timer waits), and
not for keyframed colliders: they change every frame, and the simulation only
reads its exposure at its start frame anyway.
"""
from __future__ import annotations

import bpy

from . import emitter as em

DELAY_S = 0.5
_pending: set[str] = set()
_refreshing = False   # our own refresh updates the depsgraph too: never re-trigger on it


def _animated(ob) -> bool:
    ad = ob.animation_data
    return bool(ad and (ad.action or ad.drivers))


def _busy() -> bool:
    screen = getattr(bpy.context, "screen", None)
    if screen is not None and screen.is_animation_playing:
        return True
    try:
        return bpy.app.is_job_running("RENDER")
    except (AttributeError, TypeError):
        return False


def collider_changes(scene, depsgraph) -> bool:
    """True when this depsgraph update moved, edited or re-listed a collider."""
    col = bpy.data.collections.get(em.COLLIDERS_NAME)
    if col is None:
        return False
    obs = {o.name: o for o in col.objects if o.type == "MESH"}
    meshes = {o.data.name for o in obs.values()}
    for u in depsgraph.updates:
        idb = getattr(u.id, "original", u.id)
        if isinstance(idb, bpy.types.Collection) and idb.name == em.COLLIDERS_NAME:
            return True
        if isinstance(idb, bpy.types.Object) and idb.name in obs and u.is_updated_transform:
            if not _animated(idb):
                return True
        if isinstance(idb, bpy.types.Mesh) and idb.name in meshes and u.is_updated_geometry:
            return True
    return False


def _refresh():
    """Timer callback: refresh what depends on the colliders, once things are idle."""
    if _busy() or getattr(bpy.context, "mode", "OBJECT") != "OBJECT":
        return DELAY_S                       # try again shortly
    global _refreshing
    names = set(_pending)
    _pending.clear()
    _refreshing = True
    try:
        _refresh_scenes(names)
    finally:
        _refreshing = False
    return None


def _refresh_scenes(names: set[str]) -> None:
    for scene in bpy.data.scenes:
        if scene.name not in names:
            continue
        s = getattr(scene, "rainfx", None)
        if s is None:
            continue
        if s.wetness:
            from . import wetness
            wetness.refresh(scene, True, radius=s.wet_radius, strength=s.wet_strength, dry_rate=s.wet_dry_rate)
        if s.drips:
            from . import drips
            drips.refresh(scene, True, density=s.drip_density, seed=s.seed)


@bpy.app.handlers.persistent
def _on_depsgraph(scene, depsgraph):
    if _refreshing or _busy():
        return
    s = getattr(scene, "rainfx", None)
    if s is None or not (s.wetness or s.drips):
        return
    if not collider_changes(scene, depsgraph):
        return
    _pending.add(scene.name)
    if not bpy.app.timers.is_registered(_refresh):
        bpy.app.timers.register(_refresh, first_interval=DELAY_S)


def register() -> None:
    hs = bpy.app.handlers.depsgraph_update_post
    if _on_depsgraph not in hs:
        hs.append(_on_depsgraph)


def unregister() -> None:
    hs = bpy.app.handlers.depsgraph_update_post
    for h in list(hs):
        if getattr(h, "__module__", "") == __name__ and getattr(h, "__name__", "") == "_on_depsgraph":
            hs.remove(h)
    if bpy.app.timers.is_registered(_refresh):
        bpy.app.timers.unregister(_refresh)
    _pending.clear()
