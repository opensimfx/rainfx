from __future__ import annotations

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty, PointerProperty

from ..scene import compositor, emitter as em

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
                        follow=self.follow_object, follow_offset=tuple(self.follow_offset),
                        refraction=self.refraction_drops)
        if self.wetness:
            from ..scene import wetness as wet
            wet.refresh(context.scene, True, radius=self.wet_radius, strength=self.wet_strength,
                        dry_rate=self.wet_dry_rate)
        if self.distant_rain:
            from ..scene import distant as dist
            dist.refresh(context.scene, True, box=tuple(self.box), density=self.distant_density,
                         follow=self.follow_object, seed=self.seed)
        if self.lens_drops:
            compositor.apply_lens(context.scene, self.lens_strength)


def _on_lens(self, context):
    """Lens Drops toggle/strength: rebuild or strip the compositor droplet stage."""
    if self.lens_drops:
        compositor.apply_lens(context.scene, self.lens_strength)
    else:
        compositor.remove_lens(context.scene)


def _on_distant(self, context):
    """Distant rain toggle/density: create or remove the background layer."""
    from ..scene import distant as dist
    dist.refresh(context.scene, self.distant_rain, box=tuple(self.box),
                 density=self.distant_density, follow=self.follow_object, seed=self.seed)


def _on_wetness(self, context):
    """Wetness toggle: add/remove the wetness helper modifiers on colliders."""
    from ..scene import wetness as wet
    wet.refresh(context.scene, self.wetness, radius=self.wet_radius,
                strength=self.wet_strength, dry_rate=self.wet_dry_rate)


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
    refraction_drops: BoolProperty(name="Refraction Drops", default=False,
                                   description="Rain drops use a clear refraction material instead of streaks "
                                               "(for close-up shots; drops render ball-shaped when Shutter is 0)",
                                   update=_on_change)
    wetness: BoolProperty(name="Wetness", default=False,
                          description="Accumulate a wetness attribute on collider faces at rain impact points "
                                      "(adds a RainFX Wetness modifier to each collider)",
                          update=_on_wetness)
    wet_radius: FloatProperty(name="Wet Radius", default=0.2, min=0.001, max=5.0, unit="LENGTH",
                              description="Spread of one impact's wet patch in metres", update=_on_wetness)
    wet_strength: FloatProperty(name="Wet Strength", default=0.5, min=0.0, max=2.0,
                                description="How quickly impacts soak a face toward full wetness", update=_on_wetness)
    wet_dry_rate: FloatProperty(name="Dry Rate", default=0.02, min=0.0, max=1.0,
                                description="Wetness decay per second; 0 keeps surfaces soaked", update=_on_wetness)
    distant_rain: BoolProperty(name="Distant Rain", default=False,
                               description="Add a cheap background drizzle layer so the near-field "
                                           "simulation can stay sparse",
                               update=_on_distant)
    distant_density: FloatProperty(name="Distant Density", default=0.35, min=0.0, max=3.0,
                                   description="Streak density of the background layer (scaled from "
                                               "the simulation volume)",
                                   update=_on_distant)
    lens_drops: BoolProperty(name="Lens Drops", default=False,
                             description="Add a compositing droplet-displacement stage that mimics drops "
                                         "and streaks stuck to the camera lens",
                             update=_on_lens)
    lens_strength: FloatProperty(name="Lens Strength", default=1.0, min=0.1, max=3.0,
                                 description="Bigger droplets and stronger refraction on the lens",
                                 update=_on_lens)
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
