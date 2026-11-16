"""'RainFX Foreground': big, soft rain streaks right around the camera.

VFX rain is built in layers (far, mid, near); the near layer is a handful of
large streaks between the lens and the subject that read as out of focus.
This reuses the static, cache-free "RainFX Distant" group in a small box that
travels with the camera (Copy Location, world rotation kept so rain still
falls straight down when the camera tilts). Streaks are widened as if
defocused, kept out of a clear zone around the lens, and use the softer
'near' material; in Cycles with camera depth of field they also blur for real.
Rain presets only; the motion matches the emitter (mean fall speed, wind).
"""
from __future__ import annotations

import bpy

from .. import compat
from . import emitter as em

FOREGROUND_NAME = "RainFX Foreground"
BOX = (6.0, 6.0, 4.0)       # around the camera; streaks 0.6-4 m from the lens
CLEAR_RADIUS = 0.6          # nothing closer than this (the lens and its clip range)
WIDTH_SCALE = 2.5           # defocused near drops look wider than they are


def _find_mod(obj):
    for m in obj.modifiers:
        if m.type == "NODES" and m.name == FOREGROUND_NAME:
            return m
    return None


def refresh(scene: bpy.types.Scene, enabled: bool, ob=None, camera=None, density: float = 1.0,
            seed: int = 0) -> int:
    """Create/update the camera foreground layer, or remove it; 1 while it exists.

    Needs a rain emitter and a camera (``camera`` or the scene camera).
    """
    if not enabled:
        return remove()
    et = ob
    if et is None:
        et = next((o for o in scene.objects if em.is_emitter(o)), None)
    cam = camera or scene.camera
    if et is None or cam is None:
        return 0
    p = em.all_presets().get(et.get("rainfx_preset", ""), None)
    if p is None or p.mode != "rain":
        return remove()
    obj = bpy.data.objects.get(FOREGROUND_NAME)
    if obj is None:
        mesh = bpy.data.meshes.new(FOREGROUND_NAME)
        mesh.from_pydata([(0.0, 0.0, 0.0)], [], [])
        obj = bpy.data.objects.new(FOREGROUND_NAME, mesh)
        em.ensure_collection(scene, em.ROOT_NAME).objects.link(obj)
        obj.display_type = "BOUNDS"
        obj.visible_shadow = False
    from ..gn import distant as gn
    from ..gn import materials
    mod = _find_mod(obj) or obj.modifiers.new(FOREGROUND_NAME, "NODES")
    group = gn.ensure_group()
    if mod.node_group != group:
        mod.node_group = group
    # box base half a box below the camera, rotation stays world-aligned
    con = next((c for c in obj.constraints if c.type == "COPY_LOCATION"), None) \
        or obj.constraints.new("COPY_LOCATION")
    con.target = cam
    con.use_offset = True
    obj.location = (0.0, 0.0, -0.5 * BOX[2])
    obj.rotation_euler = (0.0, 0.0, 0.0)
    obj.scale = (1.0, 1.0, 1.0)

    d = et.get("rainfx_derived") or {}
    fall = float(d.get("vt_mean_ms", 6.0))
    shutter = p.shutter_s if p.shutter_s > 0 else 1.0 / 48.0
    S = lambda k, v: compat.set_modifier_input(mod, k, v)  # noqa: E731
    S("Box Size", BOX)
    S("Count", max(0, int(BOX[0] * BOX[1] * BOX[2] * p.visual_density * density)))
    S("Wind", tuple(et.get("rainfx_wind", (0.0, 0.0, 0.0))))
    S("Fall Speed", fall)
    S("Seed", int(seed) + 977)
    S("Streak Scale", shutter / 0.12)          # length = fall speed x shutter (group: fall x 0.12 x scale)
    S("Width Scale", WIDTH_SCALE)
    S("Clear Radius", CLEAR_RADIUS)
    S("Clear Center", (0.0, 0.0, 0.5 * BOX[2]))
    S("Distant Material", materials.get_material("near"))
    return 1


def remove() -> int:
    obj = bpy.data.objects.get(FOREGROUND_NAME)
    if obj is None:
        return 0
    me = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if me is not None and me.users == 0:
        bpy.data.meshes.remove(me)
    return 1
