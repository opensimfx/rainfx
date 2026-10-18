"""Second engine: Blender's built-in emitter particle system.

Use when you want the stock tools (Collision modifier, Force Fields, Rigid
Body hand-off, Particle Edit, Mantaflow particle coupling). Drops start with
the preset's mean *target velocity* (wind + terminal fall speed) as initial
velocity with gravity weight 0, so they fly straight at the same slant as the
Geometry Nodes engine. Collisions come from the Collision modifier on every
collider (permeability / stickiness / damping / friction / kill).

Blender's Wind force field is NOT used automatically: it behaves as a drag
coupling toward the wind vector (it removes the vertical fall velocity when the
wind is horizontal), so it needs per-scene tuning. ``create_wind`` exists for
users who want to add gusts on top.

It is a statistical approximation (one mean drop size). The Geometry Nodes
engine is the physically richer one.
"""
from __future__ import annotations

import bpy

from ..core import presets as presets_mod
from . import emitter as em

NAME = "RainFX Legacy Emitter"
WIND_NAME = "RainFX Wind"


def setup_colliders(scene, preset: presets_mod.Preset) -> int:
    """Add / update a Collision modifier on every object in the colliders collection."""
    n = 0
    for ob in em.colliders_collection(scene).objects:
        if ob.type != "MESH":
            continue
        if not any(m.type == "COLLISION" for m in ob.modifiers):
            ob.modifiers.new("RainFX Collision", "COLLISION")
        c = ob.collision
        c.permeability = preset.col_permeability
        c.stickiness = preset.col_stickiness
        c.damping = preset.col_damping
        c.friction_factor = preset.col_friction
        c.use_particle_kill = preset.mode in ("rain", "snow") and preset.restitution == 0.0
        n += 1
    return n


def create_wind(scene, preset: presets_mod.Preset, location=(0.0, 0.0, 0.0)):
    ob = bpy.data.objects.get(WIND_NAME)
    if ob is None:
        view = bpy.context.view_layer
        with bpy.context.temp_override(scene=scene, view_layer=view):
            bpy.ops.object.effector_add(type="WIND", location=location)
        ob = bpy.context.view_layer.objects.active
        ob.name = WIND_NAME
    from mathutils import Vector
    from ..core import physics as P
    wx, wy, _ = P.wind_vector(1.0, preset.wind_dir_deg)
    direction = Vector((wx, wy, 0.0)) if (wx or wy) else Vector((0.0, 1.0, 0.0))
    ob.rotation_euler = Vector((0.0, 0.0, 1.0)).rotation_difference(direction).to_euler()   # force acts along local +Z
    ob.field.strength = preset.wind_ms
    ob.field.noise = min(preset.gust_strength / max(preset.wind_ms, 0.1), 1.0)
    return ob


def create_legacy_emitter(scene, preset_id: str, size=(16.0, 16.0), height=10.0,
                          quality: float = 0.1, frame_end: int = 250):
    p = em.all_presets()[preset_id]
    if p.mode == "dew":
        raise ValueError("Dew has no particle representation")
    d = presets_mod.derive(p, (size[0], size[1], height), quality=quality)
    old = bpy.data.objects.get(NAME)
    if old is not None:
        bpy.data.objects.remove(old, do_unlink=True)
    h = 0.5
    mesh = bpy.data.meshes.new(NAME)
    mesh.from_pydata([(-h * size[0], -h * size[1], height), (h * size[0], -h * size[1], height),
                      (h * size[0], h * size[1], height), (-h * size[0], h * size[1], height)],
                     [], [(0, 1, 2, 3)])
    ob = bpy.data.objects.new(NAME, mesh)
    em.ensure_collection(scene, em.ROOT_NAME).objects.link(ob)
    ob.modifiers.new("RainFX Particles", "PARTICLE_SYSTEM")
    st = ob.particle_systems[-1].settings
    st.name = "RainFX Particles"
    st.count = d["count"]
    st.frame_start, st.frame_end = 1, frame_end
    st.lifetime = frame_end + 1
    st.emit_from = "FACE"
    st.physics_type = "NEWTON"
    st.normal_factor = 0.0
    wx, wy, _ = d["wind_vec"]
    st.object_align_factor = (wx, wy, -d["vt_mean_ms"])           # object local axes; emitter has no rotation
    st.mass = 1.0
    st.drag_factor = p.legacy_drag
    st.brownian_factor = min(p.gust_strength * 0.1, 2.0)
    st.damping = 0.0
    st.render_type = "NONE"                                    # users pick Object / Collection instancing
    st.effector_weights.gravity = 0.0                          # already at terminal velocity
    st.use_die_on_collision = p.mode in ("rain", "snow")
    st.collision_collection = em.colliders_collection(scene)
    st.timestep = 0.04
    st.subframes = 1 if d["vt_mean_ms"] < 3 else 2
    setup_colliders(scene, p)
    ob["rainfx_legacy_preset"] = preset_id
    return ob
