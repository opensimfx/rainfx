from __future__ import annotations

import bpy

from .. import compat
from ..scene import atmosphere, compositor, emitter as em, legacy_particles, lighting


def _active_emitter(context):
    ob = context.object
    if em.is_emitter(ob):
        return ob
    for o in context.scene.objects:
        if em.is_emitter(o):
            return o
    return None


def apply_all(context, ob):
    """Apply settings + optional atmosphere/lightning for the emitter's preset."""
    s = context.scene.rainfx
    sc = context.scene
    d = em.apply_preset(ob, sc, s.preset, quality=s.quality, box=tuple(s.box), intensity=s.intensity,
                        wind_mult=s.wind_mult, seed=s.seed, follow=s.follow_object,
                        follow_offset=tuple(s.follow_offset))
    p = em.all_presets()[s.preset]
    if s.with_atmosphere:
        fog = atmosphere.create_fog(sc, box=tuple(s.box), density=p.fog_density, anisotropy=p.fog_anisotropy,
                                    location=tuple(ob.location))
        atmosphere.set_fog(fog, p.fog_density, p.fog_anisotropy)
        if s.follow_object is not None:  # fog rides along with the follow target
            fog.parent = s.follow_object
            fog.matrix_parent_inverse = s.follow_object.matrix_world.inverted()
        atmosphere.apply_lighting(sc, p.sky_mult, p.sun_mult)
    if s.with_lightning and p.lightning_per_min > 0:
        lighting.create_lightning(sc, p.lightning_per_min, p.lightning_energy, seed=s.seed + 1)
    return d


class RAINFX_OT_add_emitter(bpy.types.Operator):
    bl_idname = "rainfx.add_emitter"
    bl_label = "Add Weather Emitter"
    bl_description = "Create a RainFX emitter at the 3D cursor using the selected preset"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = context.scene.rainfx
        ob = em.create_emitter(context.scene, s.preset, location=tuple(context.scene.cursor.location))
        for o in context.selected_objects:
            o.select_set(False)
        ob.select_set(True)
        context.view_layer.objects.active = ob
        apply_all(context, ob)
        self.report({"INFO"}, f"Added '{ob.name}' ({s.preset}). Play from frame {context.scene.frame_start}.")
        return {"FINISHED"}


class RAINFX_OT_apply(bpy.types.Operator):
    bl_idname = "rainfx.apply_preset"
    bl_label = "Apply Preset"
    bl_description = "Apply the preset (and fog / sky / lightning if enabled) to the active emitter"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _active_emitter(context) is not None

    def execute(self, context):
        apply_all(context, _active_emitter(context))
        return {"FINISHED"}


class RAINFX_OT_colliders_add(bpy.types.Operator):
    bl_idname = "rainfx.colliders_add"
    bl_label = "Add Selected as Colliders"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        n = em.add_colliders(context.scene, context.selected_objects)
        self.report({"INFO"}, f"{n} object(s) added to '{em.COLLIDERS_NAME}'")
        return {"FINISHED"}


class RAINFX_OT_colliders_remove(bpy.types.Operator):
    bl_idname = "rainfx.colliders_remove"
    bl_label = "Remove Selected"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        n = em.remove_colliders(context.scene, context.selected_objects)
        self.report({"INFO"}, f"{n} object(s) removed")
        return {"FINISHED"}


class RAINFX_OT_revert_lighting(bpy.types.Operator):
    bl_idname = "rainfx.revert_lighting"
    bl_label = "Restore Sky / Sun"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        atmosphere.revert_lighting(context.scene)
        return {"FINISHED"}


class RAINFX_OT_lightning(bpy.types.Operator):
    bl_idname = "rainfx.lightning"
    bl_label = "Add Lightning"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = context.scene.rainfx
        p = em.all_presets()[s.preset]
        per_min = p.lightning_per_min or 4.0
        energy = p.lightning_energy or 200000.0
        lighting.create_lightning(context.scene, per_min, energy, seed=s.seed + 1)
        return {"FINISHED"}


class RAINFX_OT_post(bpy.types.Operator):
    bl_idname = "rainfx.post"
    bl_label = "Create Compositor Post"
    bl_description = "Create a soft-glow compositor chain (only if the scene has no compositor nodes yet)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        if compositor.create_post(context.scene) is None:
            self.report({"WARNING"}, "Scene already has compositor nodes; left untouched")
            return {"CANCELLED"}
        return {"FINISHED"}


class RAINFX_OT_legacy(bpy.types.Operator):
    bl_idname = "rainfx.legacy_emitter"
    bl_label = "Add Particle-System Emitter"
    bl_description = "Alternative engine: Blender emitter particles + Collision modifiers on all colliders"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = context.scene.rainfx
        try:
            legacy_particles.create_legacy_emitter(context.scene, s.preset, size=(s.box[0], s.box[1]),
                                                   height=s.box[2], quality=min(s.quality, 0.2) * 0.1,
                                                   frame_end=context.scene.frame_end)
        except ValueError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


class RAINFX_OT_bake(bpy.types.Operator):
    bl_idname = "rainfx.bake"
    bl_label = "Bake Simulation"
    bl_description = "Bake all Geometry Nodes simulations of the active emitter (save the .blend first)"

    @classmethod
    def poll(cls, context):
        return _active_emitter(context) is not None and bool(bpy.data.filepath)

    def execute(self, context):
        ob = _active_emitter(context)
        with context.temp_override(object=ob, active_object=ob, selected_objects=[ob]):
            bpy.ops.object.simulation_nodes_cache_bake(selected=True)
        return {"FINISHED"}


class RAINFX_OT_diagnose(bpy.types.Operator):
    bl_idname = "rainfx.diagnose"
    bl_label = "Run Diagnostics"
    bl_description = "Report Blender version, API paths in use and node group health"

    def execute(self, context):
        lines = [f"Blender {bpy.app.version_string}",
                 f"GN modifier API: {'properties.inputs (5.2+)' if compat.IS_5_2_PLUS else 'custom properties (<=5.1)'}",
                 f"Compositor API: {'compositing_node_group' if compat.IS_5_0_PLUS else 'node_tree'}",
                 f"Presets loaded: {len(em.all_presets())}"]
        ob = _active_emitter(context)
        if ob:
            mod = em.find_modifier(ob)
            ng = mod.node_group if mod else None
            lines.append(f"Emitter '{ob.name}': group={ng.name if ng else None}")
            if ng:
                missing = [k for k in ("Colliders", "Count", "Wind") if compat.socket_identifier(ng, k) is None]
                lines.append("Group sockets OK" if not missing else f"Missing sockets: {missing}")
                lines.append(f"Count input reads back: {compat.get_modifier_input(mod, 'Count')}")
        for ln in lines:
            self.report({"INFO"}, ln)
            print("[RainFX]", ln)
        return {"FINISHED"}


CLASSES = (RAINFX_OT_add_emitter, RAINFX_OT_apply, RAINFX_OT_colliders_add, RAINFX_OT_colliders_remove,
           RAINFX_OT_revert_lighting, RAINFX_OT_lightning, RAINFX_OT_post, RAINFX_OT_legacy,
           RAINFX_OT_bake, RAINFX_OT_diagnose)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
