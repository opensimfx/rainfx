# User Guide

## 1. First rain in five steps

1. **Colliders.** Select every object rain must hit (ground, roofs, cars, umbrellas) and click *Add Selected as Colliders*.
   Only mesh objects count. Use simple proxy meshes for dense geometry; the raycast cost grows with triangle count.
2. **Preset.** Pick one in the RainFX tab. The box under the dropdown describes it.
3. **Volume.** Set X, Y and height so the volume covers everything the camera sees plus a margin; wind pushes drops sideways and they wrap around the box.
4. **Add Weather Emitter** (placed at the 3D cursor). Fog, sky dimming and lightning are created too if their toggles are on.
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
| Snow | Light Snow, Heavy Snow, Blizzard | Flakes stick and recycle; no accumulation yet |

## 4. Viewport vs render

- `Viewport Density` (default 0.3) draws 30 % of the particles in the viewport only. Rendering uses 100 %.
- The viewport shows streaks and spheres as real instances; keep Quality low for responsive playback.
- Changing Count, Volume or Seed mid-timeline changes the initial state: return to the start frame (or re-bake).

## 5. Baking

Save the .blend, select the emitter, click *Bake Simulation*. The bake covers the scene frame range. Delete the bake from the
Physics tab or the modifier panel to re-simulate. A baked simulation is the only reliable way to get identical frames
across render nodes.

## 6. Rendering tips

| Topic | Advice |
|---|---|
| Motion blur | Streak length already represents the shutter. Turn renderer motion blur off or accept double blur |
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
| *Bake Simulation* is grayed out | The file has not been saved | Save the .blend |
| Dew looks too sparse or too dense | Density is per m2 and capped at 200,000 total | Edit `Density` / `Max Beads` in the modifier |
| Lighting looks wrong after switching presets | Sky and sun were scaled | *Restore Sky / Sun* resets to the stored originals |
| Presets list shorter than expected | A user preset file failed to parse | Check the console for `[RainFX] skipped user preset file` |
| Operators report missing sockets | Old node group in the file | Click *Apply Preset*; the group is rebuilt when versions differ. Use *Run Diagnostics* |

## 9. Uninstall and cleanup

Disable and remove the extension, then in Outliner > Blender File purge orphan data. Datablocks created by RainFX
are prefixed `RainFX ` (node groups, materials, collections, objects) so they are easy to find.
