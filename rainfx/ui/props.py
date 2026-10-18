from __future__ import annotations

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty, PointerProperty

from ..scene import emitter as em

_items_cache: list[tuple] = []


def preset_items(self, context):
    """Dynamic enum. The returned list must stay referenced (Blender keeps raw
    pointers to the strings), hence the module-level cache."""
    global _items_cache
    cat_order = {"rain": 0, "frozen": 1, "surface": 2}
    ps = sorted(em.all_presets().values(), key=lambda p: (cat_order.get(p.category, 9), p.rate_mm_h, p.name))
    _items_cache = [(p.id, p.name, p.description) for p in ps]
    return _items_cache


def _on_change(self, context):
    """Live update: re-apply the preset to the active emitter."""
    ob = context.object
    if ob is not None and em.is_emitter(ob) and self.live_update:
        em.apply_preset(ob, context.scene, self.preset, quality=self.quality, box=tuple(self.box),
                        intensity=self.intensity, wind_mult=self.wind_mult, seed=self.seed,
                        follow=self.follow_object, follow_offset=tuple(self.follow_offset))


class RainFXSettings(bpy.types.PropertyGroup):
    preset: EnumProperty(name="Preset", items=preset_items, update=_on_change)
    quality: FloatProperty(name="Quality", description="Particle budget multiplier (1.0 = preset density)",
                           default=1.0, min=0.02, max=4.0, update=_on_change)
    intensity: FloatProperty(name="Intensity", description="Scales particle density",
                             default=1.0, min=0.1, max=3.0, update=_on_change)
    wind_mult: FloatProperty(name="Wind", description="Scales preset wind and gusts",
                             default=1.0, min=0.0, max=3.0, update=_on_change)
    box: FloatVectorProperty(name="Volume", description="Simulation box in metres (X, Y, height)",
                             default=(16.0, 16.0, 10.0), min=1.0, max=500.0, size=3, subtype="XYZ_LENGTH",
                             update=_on_change)
    seed: IntProperty(name="Seed", default=0, update=_on_change)
    follow_object: PointerProperty(name="Follow Object", type=bpy.types.Object,
                                   description="Precipitation volume follows this object's location in world "
                                               "space (pick the camera for camera-following rain)")
    follow_offset: FloatVectorProperty(name="Follow Offset", size=3, default=(0.0, 0.0, 0.0), subtype="XYZ_LENGTH",
                                       description="Volume base offset from the follow point; for a camera try "
                                                   "Z = -half of the volume height", update=_on_change)
    live_update: BoolProperty(name="Live Update", default=True,
                              description="Re-apply the preset to the active emitter when settings change")
    with_atmosphere: BoolProperty(name="Fog + Sky", default=True,
                                  description="Also create fog and dim sky/sun when applying a preset")
    with_lightning: BoolProperty(name="Lightning", default=True,
                                 description="Also create lightning if the preset defines it")


CLASSES = (RainFXSettings,)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Scene.rainfx = PointerProperty(type=RainFXSettings)


def unregister():
    del bpy.types.Scene.rainfx
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
