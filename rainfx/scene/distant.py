"""'RainFX Distant' background layer: object lifecycle + preset wiring.

The GN group itself is static and cache-free, so everything here is plain
object work: one renderable box object carrying the modifier, placed at the
emitter and optionally parented to the Follow Object exactly like the fog.
Motion feeds off the emitter's stored derived values, so the far layer moves
with the simulation for free — and re-syncs on every Apply because refresh
re-reads the emitter's vt/wind.
"""
from __future__ import annotations

import bpy

from .. import compat
from . import emitter as em

DISTANT_NAME = "RainFX Distant"
SNOW_COUNT = 1.5           # far flakes per far streak (slow snow lingers in view)
SNOW_STREAK_SCALE = 0.15   # with SNOW_WIDTH_SCALE: ~2 cm flakes, length ~ width at 1-1.5 m/s
SNOW_WIDTH_SCALE = 16.0


def _emitter(scene: bpy.types.Scene):
    for o in scene.objects:
        if em.is_emitter(o):
            return o
    return None


def _find_mod(obj) -> bpy.types.NodesModifier | None:
    for m in obj.modifiers:
        if m.type == "NODES" and m.name == DISTANT_NAME:
            return m
    return None


def refresh(scene: bpy.types.Scene, enabled: bool, ob=None, box=None, density: float = 0.35,
            follow=None, seed: int = 0) -> int:
    """Create/update or remove the background layer; 1 while it exists."""
    if not enabled:
        return remove()
    et = ob if ob is not None else _emitter(scene)
    if et is None:
        return 0
    preset = em.all_presets().get(et.get("rainfx_preset", ""), None)
    if preset is not None and preset.mode == "dew":
        return remove()                 # dew does not fall: no background precipitation
    obj = bpy.data.objects.get(DISTANT_NAME)
    if obj is None:
        # display-only unit box (XY centred, Z 0..1); the modifier output replaces it
        mesh = bpy.data.meshes.new(DISTANT_NAME)
        h = 0.5
        v = [(x, y, z) for x in (-h, h) for y in (-h, h) for z in (0.0, 1.0)]
        f = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6),
             (0, 2, 6, 4), (1, 5, 7, 3)]
        mesh.from_pydata(v, [], f)
        mesh.validate()
        obj = bpy.data.objects.new(DISTANT_NAME, mesh)
        em.ensure_collection(scene, em.ROOT_NAME).objects.link(obj)
        obj.display_type = "BOUNDS"
        obj.visible_shadow = False
    group = _group()
    mod = _find_mod(obj)
    if mod is None:
        mod = obj.modifiers.new(DISTANT_NAME, "NODES")
        obj.modifiers.move(len(obj.modifiers) - 1, 0)
    if mod.node_group != group:
        mod.node_group = group

    near = tuple(box) if box is not None else (16.0, 16.0, 10.0)
    far = (near[0] * 3.0, near[1] * 3.0, max(near[2] * 2.0, 20.0))
    from ..gn import materials
    d = et.get("rainfx_derived") or {}
    obj.location = tuple(et.location)
    # unit scale: the node group already spans Box Size in object space (0.3 also
    # scaled the object by the box, which blew the layer up to ~1 km and widened
    # every far streak 48x); the display box shows the evaluated bounds anyway
    obj.scale = (1.0, 1.0, 1.0)
    S = lambda k, v: compat.set_modifier_input(mod, k, v)  # noqa: E731
    snow = int(d.get("mode_index", 0)) == 2
    S("Box Size", far)
    # snow: slow flakes, so more of them stay in view, drawn as ~2 cm round
    # flakes in the snow material instead of rain streaks
    S("Count", max(0, int(far[0] * far[1] * far[2] * 0.5 * density * (SNOW_COUNT if snow else 1.0))))
    S("Wind", tuple(et.get("rainfx_wind", (0.0, 0.0, 0.0))))
    S("Fall Speed", float(d.get("vt_mean_ms", 9.0)))
    S("Seed", int(seed) + 511)
    S("Streak Scale", SNOW_STREAK_SCALE if snow else 1.0)
    S("Width Scale", SNOW_WIDTH_SCALE if snow else 1.0)
    S("Distant Material", materials.get_material("snow" if snow else "distant"))
    if follow is not None:  # rides along with the follow target, like the fog
        obj.parent = follow
        obj.matrix_parent_inverse = follow.matrix_world.inverted()
    return 1


def _group():
    from ..gn import distant as gn
    return gn.ensure_group()


def remove() -> int:
    obj = bpy.data.objects.get(DISTANT_NAME)
    if obj is None:
        return 0
    me = obj.data
    bpy.data.objects.remove(obj)
    if me is not None and me.users == 0:
        bpy.data.meshes.remove(me)
    return 1
