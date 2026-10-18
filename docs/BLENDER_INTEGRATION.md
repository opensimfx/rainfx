# Blender Integration

How RainFX uses Blender's built-in systems, which ones it deliberately does not use yet, and what changed in the
Blender 5.x Python API. "Checked" means exercised by a test in headless Blender 5.0.1; "documented" means taken from the
Blender manual or release notes only.

## 1. Geometry Nodes (the main engine)

### Simulation zone

Manual points that shaped the design (documented):

- State inside a zone must be stored as named attributes; anonymous attributes are not propagated across steps.
- Values linked into a zone from outside are re-evaluated every step, while values connected through the Simulation Input
  node are evaluated once at the start. RainFX links parameters (wind, gust, colliders) from outside so they can be animated.
- `Delta Time` comes from the Simulation Input node; RainFX uses an exact exponential integrator so it is stable for any value.
- Caching: the standard bake workflow. Operators present in 5.0.1 (checked): `object.simulation_nodes_cache_bake`,
  `simulation_nodes_cache_calculate_to_frame`, `simulation_nodes_cache_delete`, `geometry_node_bake_single`.

### Nodes used

| Node | Use |
|---|---|
| Simulation Input / Output (paired by `pair_with_output`) | The solver loop (checked) |
| Raycast | Collision against the realized colliders mesh, along each particle step (checked) |
| Collection Info (transform space Relative) + Realize Instances | Collider geometry in the emitter's local space, so moving the emitter moves the volume correctly |
| Capture Attribute (`capture_items.new`) | Freezes all fields before any mutation (see SYSTEM_DESIGN D5) |
| Separate Geometry, Duplicate Elements, Delete Geometry, Join Geometry | Primary / splash split, splash spawn, splash end of life |
| Noise Texture, Random Value, Math, Vector Math (incl. Wrap), Compare, Boolean Math, Mix | Gusts, sampling, integrator, impact logic |
| Instance on Points, Align Rotation to Vector, Set Material, Switch | Streak / sphere rendering with velocity-aligned instances |
| Points to Vertices | Debug and custom instancing output (`Output Mode = 1`) |
| Is Viewport | Viewport density reduction |
| Distribute Points on Faces, Input Normal, Mesh Face Area, Attribute Statistic, Translate Instances | Dew beads with an area-based cap |

### Using the output in your own node trees

Set `Output Mode` to 1: the modifier then outputs the simulation state as mesh vertices carrying `velocity`, `diameter`,
`kind`, `bounces` named attributes. Add a second Geometry Nodes modifier after it to instance your own meshes, drive
materials from `velocity`, or compute wetness from where `kind == 1` splashes occur.

## 2. Physics systems

| System | Status | How |
|---|---|---|
| Collision (modifier) | Used by the legacy engine (checked) | `scene/legacy_particles.py` adds a Collision modifier to every collider and sets `permeability`, `stickiness`, `damping`, `friction_factor`, `use_particle_kill` from the preset. The manual lists these settings for particle collisions |
| Particle system (emitter, Newtonian) | Used by the legacy engine (checked) | Count, frame range, lifetime, face emission, Newtonian physics, initial velocity along object axes, `drag_factor`, `brownian_factor`, gravity weight, `use_die_on_collision`, `collision_collection`. The Newtonian page documents drag, Brownian, damping, size, mass and integrator options |
| Force fields (Wind, Turbulence, Drag) | Not used automatically | Observed: a horizontal Wind field removes the vertical fall velocity (it behaves as drag toward the wind vector), so it needs per-scene tuning. `legacy_particles.create_wind` is available for users who add gusts manually |
| Rigid Body | Planned (phase 3) | "Hero hail": a few large hailstones as rigid bodies converted from the point output, with a Rigid Body World collision shape |
| Fluid (Mantaflow) | Planned (phase 3) | Hero splashes / puddles by feeding a Flow object from impact points. Out of scope for the interactive simulation |
| Dynamic Paint | Planned (phase 2) | Wet maps and ripples on surfaces from splash positions |
| Soft Body / Cloth | Not applicable | |
| New experimental physics (5.2) | Not used | The 5.2 release notes introduce a Geometry Nodes based physics system focused on hair and cloth, with a Collider effector for closed meshes, and allow Geometry Nodes modifiers on empties (documented). It does not cover precipitation; revisit when it matures |

## 3. Rendering

- **Engine ids.** In 5.0 the EEVEE engine id is `BLENDER_EEVEE` (the `_NEXT` suffix is gone; checked: the only EEVEE id in 5.0.1). `compat.eevee_engine_id()` returns the right one.
- **EEVEE / Cycles.** The materials are plain Principled BSDF graphs and work in both. Water and splash materials use `surface_render_method = 'BLENDED'` for alpha streaks.
- **Fog.** A cube with a Volume Scatter material (Density from the preset, Anisotropy 0.3). Renders as a volume in both engines. In EEVEE, volumetric resolution and the clip distance must cover the cube.
- **Lightning.** An area light keyframed with constant interpolation. Increase `Energy` for large scenes; the value is in watts and depends on distance.
- **Motion blur.** Streaks already include the shutter blur. Turn renderer motion blur off or expect double blur (documented in PHYSICS.md section 5).
- **Not render-tested.** No image was rendered while building v0.1; tune the materials in your scene.

## 4. Compositor

5.0 moved the compositor to node groups (see section 6). `scene/compositor.py`:

- creates `RainFX Post` only when the scene has no compositor nodes (checked: a second call returns `None` and leaves the tree alone),
- 5.0+: Render Layers -> Glare -> Group Output with an `Image` output socket; <5.0: Composite node (checked on 5.0.1 only),
- setting the Glare type and strength is attempted through both the old property and the new socket and silently falls back to defaults if neither is accepted. Check the result in your 5.2.1 compositor.

## 5. Extension packaging

`rainfx/blender_manifest.toml` follows schema `1.0.0` (documented in the Blender manual, "Getting Started" for extensions):
required `id`, `version`, `name`, `tagline`, `maintainer`, `type = "add-on"`, `blender_version_min`, `license` (an SPDX
GPL identifier), plus optional `tags`, `website`, `copyright` and `[permissions]`.

- The tagline must be short, without trailing punctuation. Permission reasons must be short.
- `[permissions] files` is declared because user preset JSON files are read from the user extension folder (`bpy.utils.extension_path_user`).
- Build: `blender --command extension build --source-dir rainfx --output-dir dist`; validate: `blender --command extension validate <zip>`.
  `tools/build_extension.py` produces an equivalent zip without Blender (manifest at the zip root). **Not validated** with Blender's validator.
- `AddonPreferences.bl_idname` is derived from `__package__` (extensions are loaded under `bl_ext.<repo>.<id>`), never hard-coded.
- Update the maintainer, website and copyright fields before publishing; they contain placeholders.

## 6. Python API changes handled (4.2 to 5.2)

| Change | Release | Where handled | Status |
|---|---|---|---|
| Geometry Nodes modifier inputs: `modifier["Socket_2"]` replaced by `modifier.properties.inputs.<identifier>.value` | 5.2 (5.2 Python API notes; `NodesModifier.properties` is read-only and may be `None`) | `compat.set_modifier_input` / `get_modifier_input` | 5.2 branch: logic-tested with a stand-in; legacy branch: checked on 5.0.1 |
| Compare and Random Value socket identifiers changed (type-suffixed) | 5.2 notes | `gn/dsl.py` looks up sockets by name among enabled sockets | Name lookup checked on 5.0.1 |
| `scene.node_tree` removed; compositor is `scene.compositing_node_group` | 5.0 | `compat.get_compositing_tree` | Checked (`scene.node_tree` absent in 5.0.1) |
| `Material.use_nodes` deprecated, removal expected in 6.0 | 5.0 | `compat.new_material` only sets it before 5.0 | Checked (deprecation warning in 5.0.1) |
| `BLENDER_EEVEE_NEXT` id removed | 5.0 | `compat.eevee_engine_id` | Checked |
| `action.fcurves` removed (slotted actions) | 5.0 | `scene/lighting.py` uses `keyframe_insert` + the interpolation preference | Checked (`hasattr(action, "fcurves")` is False in 5.0.1) |
| `CompositorNodeComposite` replaced by Group Output | 5.0 | `scene/compositor.py` | Checked |
| Glare node settings became sockets | 5.0 | try/except setters | Checked that it does not fail |
| `bpy.props` storage no longer dict-accessible (`obj["prop"]` for registered properties) | 5.0 notes | RainFX stores plain custom properties (`rainfx_emitter`, `rainfx_preset`) and registered properties only through attribute access | Not specifically tested |

Rule for contributors: any new API call that is not present identically in 5.0 and 5.2 goes through `compat.py` with a
comment naming the release note.

## 7. Integration recipes

- **Rain only on part of a scene**: put just those objects in `RainFX Colliders`; everything else is ignored by the raycast.
- **Roofs and umbrellas**: add the roof as a collider; drops that would hit it splash on top and the space below stays dry.
- **Several weather volumes**: add several emitters; they share the colliders collection and node group but have separate modifier inputs and caches.
- **Camera-following rain**: do not parent the emitter to the camera. Since 0.2.0, set the *Follow Object* field to the camera (and a Z *Follow Offset*, e.g. half the volume height, so the camera sits mid-column). Do not parent the emitter itself to a moving object; the legacy particle-system engine ignores Follow Object.
- **Moving colliders (vehicles, doors)**: animated colliders push splashes automatically since 0.2.0 — tune with the *Collider Push* slider on the Impact panel (0 restores the old static behaviour). The transfer is translation-only and bake-safe (it lives in the node group); changing the collider collection mid-simulation costs one step of velocity accuracy.
- **Cycles + volumes**: the fog cube is a bounded volume; for world-wide haze add a World Volume Scatter yourself.
