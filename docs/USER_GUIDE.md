# User Guide

## 1. First rain in five steps

1. **Colliders.** Select every object rain must hit (ground, roofs, cars, umbrellas) and click *Add Selected as Colliders*.
   Only mesh objects count. Use simple proxy meshes for dense geometry; the raycast cost grows with triangle count.
2. **Preset.** Pick one in the RainFX tab. The box under the dropdown describes it.
3. **Volume.** Set X, Y and height so the volume covers everything the camera sees plus a margin; wind pushes drops sideways and they wrap around the box.
4. **Add Weather Emitter** (placed at the 3D cursor). Fog, sky dimming and lightning are created too if their toggles are on. A demo ground plane (RainFX Surface) and a Suzanne (RainFX Suzanne) are also seeded and joined to the collision set the first time, so rain lands visibly right away — swap in your own meshes later via the Collision panel (select them, Add Colliders) or just delete the demo objects.
5. **Play from the start frame.** The simulation needs a short warm-up; for a render, start the timeline 2 s before the shot or bake.

The emitter's origin is the centre of the *bottom* of the volume. Put it on the ground.

## 2. Controls

| Control | Effect | Typical use |
|---|---|---|
| Intensity | Scales particle density | 0.5 for lighter, 1.5 for denser look without changing physics |
| Quality | Particle budget multiplier | 0.25 while blocking, 1.0 final; higher for hero close-ups |
| Wind | Scales preset wind and gusts | 0 for still air, 2 for stormy |
| Volume | Simulation box (X, Y, height in m) | Match the camera frustum |
| Seed | Random seed | Different but equivalent weather |
| Live Update | Re-applies the preset on change | Turn off for slow scenes |
| Follow Object | The volume base follows this object's world location (emitter itself if empty) | Pick the camera for camera-following rain |
| Follow Offset | World offset of the volume base from the follow point | For a camera set Z = -half volume height so the camera sits mid-column |
| Refraction Drops | Rain drops use a clear refraction material instead of translucent streaks | Close-up shots; set *Shutter* 0 so drops render as spheres |
| Wetness (Collision sub-panel) | Surfaces darken and gloss where drops actually land, low spots pool as lingering wet puddle shading with a shimmering ripple bump — a hidden "RainFX Impacts" carrier feeds each collider's helper modifier | On for ground shots in rain; tune Wet Radius / Strength, raise Dry Rate for quick-drying surfaces |
| Snow accumulation (Wetness sub-panel) | Under snow presets, up-facing surfaces gain a per-vertex snow cover that lifts vertices along their normals (*Snow Depth*; metres) and brightens/roughens the surface; tune with *Snow Rate* (snow units per second inside a flake footprint) directly on the helper modifier | On automatically with the Wetness toggle in snow presets; plateaus at Snow Depth on fully covered spots |
| Distant Rain | A cheap background drizzle layer fills the far view so the near-field simulation can stay sparse; translucent far streaks fall at the preset's own wind and speed around a 3x reach shelf, and the layer follows the Follow Object like fog | On for wide establishing shots; far streaks are open-world filler and never collide; tune *Distant Density* (0.02-3.0) for the look |
| Lens Drops | A compositing droplet stage smears the rendered frame like water on the camera glass: round beads plus stretched drip streaks keep falling down the lens via frame-driven drifting maps; constant cost, no animation work | On for camera-attached shots through rain; scale with *Lens Strength* (0.1-3.0); only builds on the RainFX post chain — a scene with its own compositing nodes is left untouched |
| Export Impact Events | A one-click JSON log (Collision panel) for audio middleware: frame, emitter-local position (multiply by the emitter's matrix_world when follow-mounted), intensity = landing drop diameter in mm and type impact/snow, plus fps, preset and mean terminal velocity in the header | Run after the rain is built and the frame range is final; the export replays the sim (deterministic, matches bakes); split impact/snow entries so flake landings can map to softer sound layers |
| Fog + Sky / Lightning | Extras created with the preset | Turn off if you light the scene yourself |

Derived Physics (sub-panel) shows what the preset produced: particle count, mean diameter, terminal speed, relaxation time, streak tilt, streak length and the ratio to physical drop density.

## 3. Weather presets in practice

| Want | Preset | Notes |
|---|---|---|
| Morning macro shots | Dew | Beads on up-facing surfaces of colliders; density per m2 with a hard cap of 200,000 beads. Collide only the object you are photographing |
| Fine mist-like rain | Drizzle | Many tiny, slow drops, no splash |
| Standard rain | Light / Moderate / Heavy | Splash count and fog grow with intensity |
| Cloudburst | Downpour | Reduce Quality for the viewport; the fog density is high |
| Storm | Thunderstorm, Wind-Driven Rain | Gusts are noise-based; lightning flashes are keyframed |
| Ice | Freezing Rain, Sleet, Hailstorm | Sleet and hail bounce off colliders (restitution, max bounces) |
| Snow | Light Snow, Heavy Snow, Blizzard | Flakes stick and recycle; up-facing surfaces accumulate a snow cover (Wetness toggle + helper *Snow Rate* / *Snow Depth*) |

## 4. Viewport vs render

- `Viewport Density` (default 0.3) draws 30 % of the particles in the viewport only. Rendering uses 100 %.
- The viewport shows streaks and spheres as real instances; keep Quality low for responsive playback.
- Changing Count, Volume or Seed mid-timeline changes the initial state: return to the start frame (or re-bake).

## 5. Baking

Save the .blend and pick the emitter, then *Simulation → Bake* (RainFX panel). The dialog pre-fills the scene
frame range; *Packed cache* stores the result inside the .blend, otherwise the bake files go under
`<emitter>_rainfx_bake` next to the saved file. Bake the range you render, starting at the scene start frame —
replay is exact over the baked range, and a partial bake that stops early should be re-run (or the file reloaded)
if your render range extends past it. *Delete* frees disk files and packed data; playback then re-simulates live.
Tick *Background bake* (disk bakes only) to bake in a second Blender process and keep working: live progress
shows in the panel while the bake runs.
A baked simulation is the only reliable way to get identical frames across render nodes.

## 6. Rendering tips

| Topic | Advice |
|---|---|
| Motion blur | Streak length already represents the shutter. Renderer motion blur cannot paint real trails — sim zones step whole frames, so every shutter sample sees identical geometry; best off to avoid double blur on colliders |
| Visual Scale | Increase for wide shots (drops are sub-pixel), reduce for close-ups |
| Fog | The fog cube must enclose the camera view; in EEVEE check volumetric resolution and end distance |
| Lights | Rain is nearly invisible without a light behind it. Rim or back lights and bright backgrounds reveal streaks. Street lamps in a dark scene are the classic setup |
| Materials | `RainFX Water`, `RainFX Splash`, `RainFX Ice`, `RainFX Snow`, `RainFX Dew` are normal Principled materials; edit them freely |
| Lightning | The `RainFX Lightning` light is an area light high above the volume. Change Energy and position to taste |
| Compositor | *Create Compositor Post* adds a glow chain only if the scene has no compositor nodes |

## 7. Advanced

### Custom presets

Place JSON files in the user presets folder (shown in the add-on preferences). Format in `PRESETS.md`. Restart Blender after editing.

### Editing the node group

Open the emitter's Geometry Nodes modifier: the group `RainFX Precipitation` exposes all inputs grouped in panels (Setup, Population, Air, Impact, Look).
Do not edit nodes inside the group in a file you want to keep upgrading: the add-on rebuilds the group when its internal version changes. Duplicate the group (and rename it) if you want to modify the internals.

### Raw simulation output

Set `Output Mode` to 1 to output vertices with `velocity`, `diameter`, `kind` (0 drop, 1 splash) and `bounces` attributes, then instance your own geometry in a second modifier.

### Second engine (particle system)

*Add Particle-System Emitter* creates Blender's own emitter particle system with Newtonian physics and adds Collision
modifiers to all colliders using the preset's permeability, stickiness, damping and friction. Use it if you need Blender tools that only
act on legacy particles. It uses one mean drop size and straight paths at the mean target velocity; it does not replace the Geometry Nodes engine for realism.

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| No rain visible | Playhead is not at/after the start frame, or Quality is too low, or lighting hides streaks | Go to the start frame, press play, add a back light |
| Rain frozen or in the wrong place after moving the emitter | Parenting the emitter to a moving object | Leave the emitter unparented; set *Follow Object* (plus a Z *Follow Offset*) to the moving object or camera |
| Moving colliders don't push splashes | *Collider Push* (Impact panel) reduced to 0, or colliders changed mid-simulation | Raise *Collider Push*; changing the collider collection mid-sim costs one step of velocity accuracy |
| Rain passes through an object | Object is not in `RainFX Colliders`, or it is not a mesh | Add Selected as Colliders; convert curves and text to mesh |
| Rain inside buildings at frame 1 | Particles are seeded inside colliders | Start the timeline earlier; they recycle within about 2 s |
| Viewport slow | Too many particles or dense colliders | Lower Quality or Viewport Density, use proxy colliders |
| *Bake* errors | Unsaved file (disk bake) or no active emitter | Save the .blend and select an emitter; *Packed cache* also works on unsaved scenes |
| Dew looks too sparse or too dense | Density is per m2 and capped at 200,000 total | Edit `Density` / `Max Beads` in the modifier |
| Lighting looks wrong after switching presets | Sky and sun were scaled | *Restore Sky / Sun* resets to the stored originals |
| Presets list shorter than expected | A user preset file failed to parse | Check the console for `[RainFX] skipped user preset file` |
| Operators report missing sockets | Old node group in the file | Click *Apply Preset*; the group is rebuilt when versions differ. Use *Run Diagnostics* |

## 9. Uninstall and cleanup

Disable and remove the extension, then in Outliner > Blender File purge orphan data. Datablocks created by RainFX
are prefixed `RainFX ` (node groups, materials, collections, objects) so they are easy to find.


---

## Blender Integration


How RainFX uses Blender's built-in systems, which ones it deliberately does not use yet, and what changed in the
Blender 5.x Python API. "Checked" means exercised by a test in headless Blender 5.0.1; "documented" means taken from the
Blender manual or release notes only.

### 1. Geometry Nodes (the main engine)

#### Simulation zone

Manual points that shaped the design (documented):

- State inside a zone must be stored as named attributes; anonymous attributes are not propagated across steps.
- Values linked into a zone from outside are re-evaluated every step, while values connected through the Simulation Input
  node are evaluated once at the start. RainFX links parameters (wind, gust, colliders) from outside so they can be animated.
- `Delta Time` comes from the Simulation Input node; RainFX uses an exact exponential integrator so it is stable for any value.
- Caching: the standard bake workflow. Operators present in 5.0.1 (checked): `object.simulation_nodes_cache_bake`,
  `simulation_nodes_cache_calculate_to_frame`, `simulation_nodes_cache_delete`, `geometry_node_bake_single`.

#### Nodes used

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

#### Using the output in your own node trees

Set `Output Mode` to 1: the modifier then outputs the simulation state as mesh vertices carrying `velocity`, `diameter`,
`kind`, `bounces` named attributes. Add a second Geometry Nodes modifier after it to instance your own meshes, drive
materials from `velocity`, or compute wetness from where `kind == 1` splashes occur.

### 2. Physics systems

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

### 3. Rendering

- **Engine ids.** In 5.0 the EEVEE engine id is `BLENDER_EEVEE` (the `_NEXT` suffix is gone; checked: the only EEVEE id in 5.0.1). `compat.eevee_engine_id()` returns the right one.
- **EEVEE / Cycles.** The materials are plain Principled BSDF graphs and work in both. Water and splash materials use `surface_render_method = 'BLENDED'` for alpha streaks.
- **Fog.** A cube with a Volume Scatter material (Density from the preset, Anisotropy 0.3). Renders as a volume in both engines. In EEVEE, volumetric resolution and the clip distance must cover the cube.
- **Lightning.** An area light keyframed with constant interpolation. Increase `Energy` for large scenes; the value is in watts and depends on distance.
- **Motion blur.** Streaks already include the shutter blur, and renderer motion blur cannot add real trails: simulation zones step whole frames, so shutter samples see identical geometry (verified in Blender 5.2.1 — identical renders with blur on/off in both Cycles and EEVEE; noted in PHYSICS.md section 5).
- **Not render-tested.** No image was rendered while building v0.1; tune the materials in your scene.

### 4. Compositor

5.0 moved the compositor to node groups (see section 6). `scene/compositor.py`:

- creates `RainFX Post` only when the scene has no compositor nodes (checked: a second call returns `None` and leaves the tree alone),
- 5.0+: Render Layers -> Glare -> Group Output with an `Image` output socket; <5.0: Composite node (checked on 5.0.1 only),
- setting the Glare type and strength is attempted through both the old property and the new socket and silently falls back to defaults if neither is accepted. Check the result in your 5.2.1 compositor.

### 5. Extension packaging

`rainfx/blender_manifest.toml` follows schema `1.0.0` (documented in the Blender manual, "Getting Started" for extensions):
required `id`, `version`, `name`, `tagline`, `maintainer`, `type = "add-on"`, `blender_version_min`, `license` (an SPDX
GPL identifier), plus optional `tags`, `website`, `copyright` and `[permissions]`.

- The tagline must be short, without trailing punctuation. Permission reasons must be short.
- `[permissions] files` is declared because user preset JSON files are read from the user extension folder (`bpy.utils.extension_path_user`).
- Build: `blender --command extension build --source-dir rainfx --output-dir dist`; validate: `blender --command extension validate <zip>`.
  `tools/build_extension.py` produces an equivalent zip without Blender (manifest at the zip root). **Not validated** with Blender's validator.
- `AddonPreferences.bl_idname` is derived from `__package__` (extensions are loaded under `bl_ext.<repo>.<id>`), never hard-coded.
- Update the maintainer, website and copyright fields before publishing; they contain placeholders.

### 6. Python API changes handled (4.2 to 5.2)

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

### 7. Integration recipes

- **Trying the rain quickly** (0.2.0): press *Add Weather Emitter* — a demo ground plane (RainFX Surface) and a Suzanne
  (RainFX Suzanne) are seeded and joined to the collision set, so rain lands on real geometry the moment you press Play.
  Both are idempotent by name; replace them with your own meshes via the Collision panel (select and use *Add Colliders*)
  or just delete them.
- **Rain only on part of a scene**: put just those objects in `RainFX Colliders`; everything else is ignored by the raycast.
- **Roofs and umbrellas**: add the roof as a collider; drops that would hit it splash on top and the space below stays dry.
- **Several weather volumes**: add several emitters; they share the colliders collection and node group but have separate modifier inputs and caches.
- **Baking without downtime** (0.2.0): for long bakes on heavy scenes tick *Background bake* in the bake dialog —
  the bake runs in a second headless Blender on the saved file (save first!) while you keep editing, and the panel
  shows live per-frame progress. Packed bakes (cache inside the .blend) always bake in-process.
- Camera-following rain: do not parent the emitter to the camera. Since 0.2.0, set the *Follow Object* field to the camera (and a Z *Follow Offset*, e.g. half the volume height, so the camera sits mid-column). Do not parent the emitter itself to a moving object; the legacy particle-system engine ignores Follow Object.
- **Refraction close-ups**: enable *Refraction Drops* on the main panel for shots where the camera sits inside the
  rain column. Drops get a fully refractive material (transmission 1.0, alpha 1.0) instead of translucent streaks;
  pair it with *Shutter* 0 (Look panel) so drops render as spheres, and Higher *Quality* for the denser hero look.
- **Moving colliders (vehicles, doors)**: animated colliders push splashes automatically since 0.2.0 — tune with the *Collider Push* slider on the Impact panel (0 restores the old static behaviour). The transfer is translation-only and bake-safe (it lives in the node group); changing the collider collection mid-simulation costs one step of velocity accuracy.
- **Wet surfaces**: toggle *Wetness* in the Collision sub-panel (0.2.0). Colliders darken and gloss where drops actually land,
  and low spots pool as lingering wet-puddle shading with a shimmering ripple bump animating across standing water
  (fill is instant inside impact footprints, drying runs at a quarter of the Dry Rate) —
  tune *Wet Radius* (footprint of one hit), *Strength*, and *Dry Rate* (0 keeps puddle-dark surfaces, higher dries between
  bursts). A hidden "RainFX Impacts" helper object is refreshed per frame from the emitter; leave it hidden. The wet state
  itself is bakeable (each collider's helper keeps its own simulation cache).
- **Snow cover** (0.2.0): with the Wetness toggle on, snow presets accumulate flakes on up-facing surfaces — the
  post-sim Set Position lifts verts along their normals by snow x *Snow Depth* (metres) and the surface brightens to snow white.
  *Snow Rate* (snow units per second inside a flake footprint) lives on the helper modifier next to the wet controls; the hidden
  "RainFX Snow Impacts" carrier pairs with the rain one. Snow is accumulation only — no melt, and lift follows vertex normals,
  so subdividing the snowed faces gives the smoothest drifts.
- **Wide establishing shots** (0.2.0): enable *Distant Rain* on the main panel — a static "RainFX Distant" layer fills the
  far view with translucent streaks falling at the preset's own wind and terminal speed (wrapper at 3x reach / 2x height
  around the emitter; counts = 0.5 x *Distant Density* x shelf volume). It re-applies with Apply like the fog, rides the
  Follow Object, costs none of the sim budget, and its material is transmission-free so EEVEE stays cheap. Frees the real
  simulation to stay sparse: drop *Quality* to ~0.3 and let the far layer carry the depth of the shot.
- **Camera-through-the-rain hero shots** (0.2.0): enable *Lens Drops* on the main panel — the compositor gets a
  droplet displacement stage (two procedurally generated drop maps with beads and drip streaks, drifted downward by
  frame drivers and wrapped so the smear never repeats). Scale *Lens Strength* (0.1-3.0) with focal length; the stage
  only ever attaches to the RainFX-built post chain, so scenes with their own compositing nodes stay untouched, and
  *Post Processing* must stay enabled in the render settings for the effect to reach the frame.
- **Audio-ready impact log** (0.2.0): press *Export Impact Events* in the Collision panel — the
  addon replays the emitter's frame range and writes `rainfx_impact_events.json` (frame,
  position, intensity = landing drop diameter in mm, type impact/snow, fps, preset and mean
  terminal velocity in the header). Sound designers map events to impact layers (size →
  loudness, snow → softer splat) directly in middleware; per frame at most 256 events are
  kept via even stride sampling, and the replay matches bakes because it is the same
  deterministic sim stepping frame by frame.
- **Baking for farm renders**: Simulation → *Bake* with the scene frame range; *Packed cache* travels inside the
  .blend (no sidecar folders to ship). Playback of baked frames equals the live simulation frame for frame, so
  renders run without per-frame re-simulation.
- **Cycles + volumes**: the fog cube is a bounded volume; for world-wide haze add a World Volume Scatter yourself.
