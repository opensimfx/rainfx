from __future__ import annotations

import bpy

from ..scene import baker, emitter as em


class RAINFX_PT_main(bpy.types.Panel):
    bl_label = "RainFX"
    bl_idname = "RAINFX_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "RainFX"

    def draw(self, context):
        lo = self.layout
        s = context.scene.rainfx
        lo.use_property_split = True
        lo.use_property_decorate = False
        lo.prop(s, "preset")
        p = em.all_presets().get(s.preset)
        if p:
            box = lo.box()
            box.label(text=p.description, icon="INFO")
        col = lo.column(align=True)
        col.prop(s, "intensity")
        col.prop(s, "quality")
        col.prop(s, "wind_mult")
        col.prop(s, "box")
        col.prop(s, "seed")
        col.prop(s, "refraction_drops")
        lo.prop(s, "follow_object")
        if s.follow_object:
            col = lo.column(align=True)
            col.prop(s, "follow_offset")
            lo.label(text="Volume follows %s in world space" % s.follow_object.name, icon="TRACKING")
        lo.prop(s, "distant_rain", icon="MOD_PARTICLES")
        if s.distant_rain:
            lo.prop(s, "distant_density")
        lo.prop(s, "lens_drops", icon="MOD_DISPLACE")
        if s.lens_drops:
            lo.prop(s, "lens_strength")
        lo.prop(s, "live_update")
        row = lo.row(align=True)
        row.prop(s, "with_atmosphere", toggle=True)
        row.prop(s, "with_lightning", toggle=True)
        lo.operator("rainfx.add_emitter", icon="OUTLINER_OB_FORCE_FIELD")
        lo.operator("rainfx.apply_preset", icon="FILE_REFRESH")


class RAINFX_PT_collision(bpy.types.Panel):
    bl_label = "Collisions"
    bl_idname = "RAINFX_PT_collision"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "RainFX"
    bl_parent_id = "RAINFX_PT_main"

    def draw(self, context):
        lo = self.layout
        col = bpy.data.collections.get(em.COLLIDERS_NAME)
        n = len(col.objects) if col else 0
        lo.label(text=f"{n} collider object(s)", icon="MOD_PHYSICS")
        row = lo.row(align=True)
        row.operator("rainfx.colliders_add", icon="ADD")
        row.operator("rainfx.colliders_remove", icon="REMOVE")
        s = context.scene.rainfx
        lo.prop(s, "wetness", icon="MOD_FLUID")  # MOD_SMOKE was removed in 5.2; wetness needs an emitter in the scene
        if s.wetness:
            lo.prop(s, "wet_radius")
            lo.prop(s, "wet_strength")
            lo.prop(s, "wet_dry_rate")
        lo.label(text="Rain is raycast against these meshes.")
        lo.operator("rainfx.export_events", icon="SOUND", text="Export Impact Events")


class RAINFX_PT_derived(bpy.types.Panel):
    bl_label = "Derived Physics"
    bl_idname = "RAINFX_PT_derived"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "RainFX"
    bl_parent_id = "RAINFX_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return em.is_emitter(context.object)

    def draw(self, context):
        d = context.object.get("rainfx_derived") or {}
        lo = self.layout
        fmt = (("count", "Particles", "{:,.0f}"), ("d_mean_mm", "Mean diameter", "{:.2f} mm"),
               ("vt_mean_ms", "Terminal speed", "{:.2f} m/s"), ("tau_s", "Relaxation time", "{:.2f} s"),
               ("tilt_deg", "Streak tilt", "{:.0f} deg"), ("streak_len_m", "Streak length", "{:.2f} m"),
               ("physical_count", "Physical drops in volume", "{:,.0f}"),
               ("density_ratio", "Simulated / physical", "{:.2%}"))
        for key, label, f in fmt:
            if key in d:
                r = lo.split(factor=0.55)
                r.label(text=label)
                r.label(text=f.format(d[key]))


class RAINFX_PT_scene(bpy.types.Panel):
    bl_label = "Scene Integration"
    bl_idname = "RAINFX_PT_scene"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "RainFX"
    bl_parent_id = "RAINFX_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        lo = self.layout
        lo.operator("rainfx.lightning", icon="LIGHT_AREA")
        lo.operator("rainfx.revert_lighting", icon="LOOP_BACK")
        lo.operator("rainfx.post", icon="NODE_COMPOSITING")


class RAINFX_PT_engines(bpy.types.Panel):
    bl_label = "Simulation"
    bl_idname = "RAINFX_PT_engines"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "RainFX"
    bl_parent_id = "RAINFX_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        lo = self.layout
        lo.operator("rainfx.bake", icon="PHYSICS")
        lo.operator("rainfx.bake_delete", icon="TRASH")
        handle = baker.active()
        if handle is not None:
            running, done = baker.progress(handle)
            pct = round(100.0 * done / max(handle["expected"], 1))
            if running:
                lo.label(text=f"Background bake: {done}/{handle['expected']} frames ({pct}%)",
                         icon="PHYSICS")
            else:
                lo.label(text=f"Background bake complete: {done}/{handle['expected']}",
                         icon="PHYSICS")
        lo.operator("rainfx.legacy_emitter", icon="PARTICLES")
        lo.operator("rainfx.diagnose", icon="CONSOLE")
        if not bpy.data.filepath:
            lo.label(text="Save the file to enable disk baking", icon="ERROR")


class RainFXPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__.rpartition(".")[0] or __package__

    def draw(self, context):
        from .. import compat
        lo = self.layout
        lo.label(text=f"User presets folder: {compat.user_dir()}")
        lo.label(text="Drop *.json files there; entries override built-ins by id.")


CLASSES = (RAINFX_PT_main, RAINFX_PT_collision, RAINFX_PT_derived, RAINFX_PT_scene, RAINFX_PT_engines,
           RainFXPreferences)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
