from __future__ import annotations

import bpy

from ..scene import baker, emitter as em


# Layout follows the shared OpenSimFX UI conventions (docs/UI_STYLE.md, identical in every OpenSimFX add-on).
class _Base:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "RainFX"


class _Sub(_Base):
    bl_parent_id = "RAINFX_PT_main"
    bl_options = {"DEFAULT_CLOSED"}


def _split(layout):
    layout.use_property_split = True
    layout.use_property_decorate = False
    return layout


class RAINFX_PT_main(_Base, bpy.types.Panel):
    bl_label = "RainFX"
    bl_idname = "RAINFX_PT_main"

    def draw(self, context):
        lo = _split(self.layout)
        s = context.scene.rainfx
        lo.prop(s, "preset")
        p = em.all_presets().get(s.preset)
        if p:
            import textwrap
            col = lo.column(align=True)
            for i, line in enumerate(textwrap.wrap(p.description, 38) or [""]):
                col.label(text=line, icon="INFO" if i == 0 else "BLANK1")
        col = lo.column()
        col.scale_y = 1.4
        col.operator("rainfx.add_emitter", icon="OUTLINER_OB_FORCE_FIELD")
        lo.operator("rainfx.apply_preset", icon="FILE_REFRESH")


class RAINFX_PT_rain(_Base, bpy.types.Panel):
    bl_label = "Rain"
    bl_idname = "RAINFX_PT_rain"
    bl_parent_id = "RAINFX_PT_main"

    def draw(self, context):
        lo = _split(self.layout)
        s = context.scene.rainfx
        col = lo.column(align=True)
        col.prop(s, "intensity")
        col.prop(s, "quality")
        col.prop(s, "wind_mult")
        col.prop(s, "box")
        col.prop(s, "seed")
        lo.prop(s, "follow_object")
        if s.follow_object:
            lo.prop(s, "follow_offset")
            lo.label(text="Volume follows %s in world space" % s.follow_object.name, icon="TRACKING")
        col = lo.column(heading="Extras", align=True)
        col.prop(s, "refraction_drops")
        col.prop(s, "distant_rain")
        if s.distant_rain:
            col.prop(s, "distant_density")
        col.prop(s, "foreground_rain")
        if s.foreground_rain:
            col.prop(s, "foreground_density")
            if context.scene.camera is None:
                col.label(text="Needs an active camera", icon="INFO")
        col.prop(s, "drips")
        if s.drips:
            col.prop(s, "drip_density")
        col.prop(s, "lens_drops")
        if s.lens_drops:
            col.prop(s, "lens_strength")
        col = lo.column(heading="With", align=True)
        col.prop(s, "with_atmosphere")
        col.prop(s, "with_lightning")
        lo.prop(s, "live_update")


class RAINFX_PT_collision(_Base, bpy.types.Panel):
    bl_label = "Collisions"
    bl_idname = "RAINFX_PT_collision"
    bl_parent_id = "RAINFX_PT_main"

    def draw(self, context):
        lo = _split(self.layout)
        col = bpy.data.collections.get(em.COLLIDERS_NAME)
        n = len(col.objects) if col else 0
        col = lo.column(align=True)
        col.label(text=f"{n} collider object(s)", icon="MOD_PHYSICS")
        col.label(text="Rain is raycast against them.", icon="BLANK1")
        col = lo.column(align=True)
        col.operator("rainfx.colliders_add", icon="ADD")
        col.operator("rainfx.colliders_remove", icon="REMOVE")
        s = context.scene.rainfx
        lo.prop(s, "wetness")  # wetness needs an emitter in the scene
        if s.wetness:
            coarse = list(context.scene.get("rainfx_coarse_colliders", []))
            if coarse:
                box = lo.box().column(align=True)
                box.label(text="Too coarse for wetness detail:", icon="ERROR")
                for name in coarse[:4]:
                    box.label(text=name, icon="MESH_DATA")
                if len(coarse) > 4:
                    box.label(text=f"... and {len(coarse) - 4} more")
                box.label(text="Subdivide them (vertices about every Wet Radius)")
            col = lo.column(align=True)
            p = em.all_presets().get(s.preset)
            col.prop(s, "wet_start", text="Already Snowy" if p is not None and p.mode == "snow" else "Already Wet")
            col.prop(s, "puddles")
            col = lo.column(align=True)
            col.prop(s, "wet_radius")
            col.prop(s, "wet_strength")
            col.prop(s, "wet_dry_rate")
        lo.operator("rainfx.export_events", icon="SOUND", text="Export Impact Events")


class RAINFX_PT_scene(_Sub, bpy.types.Panel):
    bl_label = "Scene Integration"
    bl_idname = "RAINFX_PT_scene"

    def draw(self, context):
        lo = self.layout
        s = context.scene.rainfx
        col = lo.column(align=True)
        col.prop(s, "backlight_style")
        col.prop(s, "backlight_strength", text="Strength")
        row = col.row(align=True)
        row.operator("rainfx.add_backlight", icon="LIGHT_SPOT")
        row.operator("rainfx.remove_backlight", icon="X", text="")
        if context.scene.camera is None:
            col.label(text="Needs an active camera", icon="INFO")
        lo.separator()
        lo.operator("rainfx.lightning", icon="LIGHT_AREA")
        lo.operator("rainfx.post", icon="NODE_COMPOSITING")
        lo.separator()
        lo.operator("rainfx.revert_lighting", icon="LOOP_BACK")


class RAINFX_PT_engines(_Sub, bpy.types.Panel):
    bl_label = "Cache and Bake"
    bl_idname = "RAINFX_PT_engines"

    def draw(self, context):
        lo = self.layout
        if not bpy.data.filepath:
            box = lo.box()
            box.alert = True
            box.label(text="Save the file to enable disk baking", icon="ERROR")
        handle = baker.active()
        if handle is not None:
            running, done = baker.progress(handle)
            factor = done / max(handle["expected"], 1)
            lo.progress(factor=factor, text=f"{'Baking' if running else 'Baked'} {done}/{handle['expected']} frames")
        col = lo.column()
        col.scale_y = 1.2
        col.operator("rainfx.bake", icon="REC")
        lo.operator("rainfx.legacy_emitter", icon="PARTICLES")
        lo.separator()
        lo.operator("rainfx.bake_delete", icon="TRASH")


class RAINFX_PT_derived(_Sub, bpy.types.Panel):
    bl_label = "Readout"
    bl_idname = "RAINFX_PT_derived"

    @classmethod
    def poll(cls, context):
        return em.is_emitter(context.object)

    def draw(self, context):
        d = context.object.get("rainfx_derived") or {}
        lo = self.layout
        fmt = (("count", "Particles", "{:,.0f}"), ("d_mean_mm", "Mean diameter", "{:.2f} mm"),
               ("vt_mean_ms", "Terminal speed", "{:.2f} m/s"), ("tau_s", "Relaxation time", "{:.2f} s"),
               ("tilt_deg", "Streak tilt", "{:.0f} deg"), ("streak_len_m", "Streak length", "{:.2f} m"),
               ("physical_count", "Drops in volume", "{:,.0f}"),
               ("density_ratio", "Simulated / physical", "{:.2%}"))
        col = lo.column(align=True)
        for key, label, f in fmt:
            if key in d:
                r = col.split(factor=0.5)
                r.label(text=label)
                r.label(text=f.format(d[key]))


class RAINFX_PT_diagnostics(_Sub, bpy.types.Panel):
    bl_label = "Diagnostics"
    bl_idname = "RAINFX_PT_diagnostics"

    def draw(self, context):
        self.layout.operator("rainfx.diagnose", icon="CONSOLE")


class RainFXPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__.rpartition(".")[0] or __package__

    def draw(self, context):
        from .. import compat
        lo = self.layout
        lo.label(text=f"User presets folder: {compat.user_dir()}")
        lo.label(text="Drop *.json files there; entries override built-ins by id.")


CLASSES = (RAINFX_PT_main, RAINFX_PT_rain, RAINFX_PT_collision, RAINFX_PT_scene, RAINFX_PT_engines,
           RAINFX_PT_derived, RAINFX_PT_diagnostics, RainFXPreferences)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
