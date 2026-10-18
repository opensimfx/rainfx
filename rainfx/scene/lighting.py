"""Lightning flashes as keyframed light energy.

Uses ``keyframe_insert`` + the user preference for new-key interpolation so it
works with the slotted-action API of 5.x (``action.fcurves`` no longer exists).
"""
from __future__ import annotations

import random

import bpy

from . import emitter as em

LIGHT_NAME = "RainFX Lightning"


def flash_schedule(per_min: float, fps: float, frame_start: int, frame_end: int, seed: int = 1):
    """Pure function: list of (frame, energy_fraction). Each strike is a short
    flicker train (2-4 pulses) with a return stroke brighter than the rest."""
    rng = random.Random(seed)
    keys = [(frame_start, 0.0)]
    if per_min <= 0:
        return keys
    mean_gap = 60.0 * fps / per_min
    f = frame_start + rng.uniform(0.3, 1.0) * mean_gap
    while f < frame_end - 8:
        pulses = rng.randint(2, 4)
        cur = int(f)
        for i in range(pulses):
            level = rng.uniform(0.6, 1.0) if i == 0 else rng.uniform(0.2, 0.7)
            on = rng.randint(1, 2)
            keys.append((cur, level))
            keys.append((cur + on, 0.0))
            cur += on + rng.randint(1, 3)
        f += rng.uniform(0.5, 1.5) * mean_gap
    return keys


def create_lightning(scene: bpy.types.Scene, per_min: float, energy: float, seed: int = 1,
                     height: float = 40.0, size: float = 60.0) -> bpy.types.Object:
    old = bpy.data.objects.get(LIGHT_NAME)
    if old is not None:
        bpy.data.objects.remove(old, do_unlink=True)
    ld = bpy.data.lights.get(LIGHT_NAME) or bpy.data.lights.new(LIGHT_NAME, "AREA")
    ld.type = "AREA"
    ld.shape = "DISK"
    ld.size = size
    ld.color = (0.72, 0.8, 1.0)
    ld.energy = 0.0
    if ld.animation_data:
        ld.animation_data_clear()
    obj = bpy.data.objects.new(LIGHT_NAME, ld)
    obj.location = (0.0, 0.0, height)             # area lights face -Z by default
    em.ensure_collection(scene, em.ROOT_NAME).objects.link(obj)

    prefs = bpy.context.preferences.edit
    prev = prefs.keyframe_new_interpolation_type
    prefs.keyframe_new_interpolation_type = "CONSTANT"
    try:
        for frame, frac in flash_schedule(per_min, scene.render.fps, scene.frame_start,
                                          scene.frame_end, seed):
            ld.energy = energy * frac
            ld.keyframe_insert("energy", frame=frame)
    finally:
        prefs.keyframe_new_interpolation_type = prev
    return obj
