# Validation

What was measured for the 1.0 release, what is not verified, and the manual acceptance checklist. How to run the
checks is in [DEVELOPMENT.md](DEVELOPMENT.md).

## Test runs for 1.0 (2026-11-16)

Desktop Blender 5.2.3 LTS, macOS arm64 (Apple M4, CPU), `-b --factory-startup`:

| Suite | Result |
|---|---|
| Pure tests (`python -m pytest`) | 45 passed |
| Blender test scripts (`tests/blender_*.py`, 20) | all pass |
| Cycles on the GPU (Metal, Apple M4 10-core) | the night street bench renders the same image as on the CPU |

The `bpy` 5.0.1 wheel (Python 3.11) runs the non-rendering scripts: simulation (`blender_smoke`), wetness,
hardening, drips, inside, upgrade, scene and UI pass. `blender_determinism_smoke` fails there at its
cache-delete step in the same way with the released 0.3.0 code: after `simulation_nodes_cache_delete`
mid-timeline, Blender 5.0 serves an empty mesh until the start frame. It passes on 5.2.

CI (`.github/workflows/ci.yml`): pure tests on Linux, Windows and macOS with Python 3.11 and 3.13. On Linux the zip
is built and validated, every Blender script that does not render with EEVEE runs in Blender 5.2.3 and 5.2.4, and
the street bench renders in Cycles (CPU; the frame is checked and kept as an artifact). On Windows, Blender 5.2.3
runs the simulation, UI, bake, background-bake (Windows paths), wetness, hardening, upgrade, drips and farm
scripts and renders the bench in Cycles. The EEVEE scripts (look, material, distant, detail, lens) need a GPU and
run on a desktop machine.

## Measurements

Each check below also has a control: the same scene with the fix removed, which must fail.

| Check | Result | Control |
|---|---|---|
| Collision (`blender_smoke`, 13 presets) | 0 particles below the floor, 0 inside the 2 m cube | no colliders: particles inside the cube |
| Sheltered start points (roof at 3 m, still air) | ground under the roof max wetness 0.000 after 24 frames; open ground 100 % wet | before 1.0: wet 1.0 under the roof (drops started there) |
| Wetness on a moved, rotated, scaled cube (rain only over it) | cube top wet 0.93-0.98 | impacts compared in the wrong space: 0.00-0.06 |
| Wetness after save and reopen | handler survives; cube wet 1.00 after 24 frames | before 1.0: the handler was dropped on load |
| Two emitters, one wetness carrier | impacts from both (88 left, 87 right) | before 1.0: first emitter only |
| Upgrade from a 0.3.0 scene (`tests/fixtures/scene_0_3_0.blend`) | plays as saved; first change rebuilds every group, lens gets its 9 nodes | before 1.0: Blender crashed on the first change |
| Background bake of an unsaved change (+6 m/s wind) | reopened playback drifts +0.30 m further in x by frame 5; a Seed change moves nothing (cache read) | test before 1.0 compared against the parent's own live preview and could not tell |
| Drips (4 x 4 m roof at 3 m, ledge under it, 15 cm curb) | 55 points, all on the roof edge, fall 2.99 m; heavy rain period 0.60 s vs light 2.19 s | |
| Ambient wetness, night street (`tools/render_look.py`) | road wet mean 0.70 (median 0.67), upwind pavement 0.39, downwind 0.91 | single wind-tilted ray: road median 0.00 |
| Splash rule (`blender_detail_smoke`) | drizzle 0 splashes at Splash Amount 6; heavy rain splashing drops larger than the mean landing | threshold above every K: none |
| Determinism | twin emitters bit-identical, replay and re-simulation exact, a Seed change moves only its emitter | |
| Render farm (`blender_farm_smoke`): baked file opened in a Blender without RainFX, jumping straight to frame 24 | packed bake: cube wet 1.00, 29,222 rain instances, 57 drip instances; background bake: cube wet 1.00 | unbaked: cube wet 0.000 |
| Lens maps after save and reopen | identical (max 1.2641, sum 3191.3 before and after) | before 1.0: reset to a blank generated image |
| Collider watcher: roof moved up 1 m | drip points 3.00 -> 4.00 m and shelter top 4.00 m after the queued refresh; the refresh does not re-trigger itself | |
| Scale: ground grid + N boxes, heavy rain, wetness and drips | 201 colliders: refresh 0.16 s (wetness) + 0.08 s (drips), 0.03 s per frame; 1001: 0.38 + 0.57 s, 0.15 s/frame; 2001: 0.90 + 1.97 s, 0.37 s/frame (drip points capped at 5000) | |

## Look

`tools/render_look.py` renders a street (asphalt on a 0.25 m grid, curbs, pavements, building fronts with lit
windows, lamp posts) at night, on an overcast day, from a puddle and from above. At 960 x 540 and 64 samples a
frame renders in about 40 s on the M4 CPU (two or three in parallel: about 110 s each). What the renders were
used to settle:

| Question | Finding |
|---|---|
| Why did streaks look like an overlay? | 10 % white diffuse in the Principled streak lit every streak from every side. A translucent + Fresnel gloss shader (light from behind) makes rain bright in front of lamps and invisible against the sky. Pure IOR-1 refraction makes rain all but disappear; a 25/75 mix was too faint |
| Why were near drops sticks? | Visual Scale x 4 applied at every distance; now true size within 2 m of the camera |
| Why was the street dry? | Only simulated hits wetted it, and only inside the volume; the ambient exposure layer fixes it |
| Why was the day road milky white? | The fog box's bottom face was coplanar with the road; Cycles treated the road as inside the volume. Boxes now extend below the ground |
| Why did the fog show a wall? | The box was the rain volume's size; it now reaches 3 x with soft edges |
| Why did snow look broken? | Bare ground (cover only from simulated flakes), sparse opaque flakes reading as grey specks, rain streaks in the distant layer. Ambient snow cover, 35 % translucent flakes, about twice the flakes and round distant flakes fix it; a snow shadow behind buildings comes from the same exposure as the rain shadow (five rays smooth its edge) |
| Why not a hail layer? | A 30 % snow cover for hail only whitened the whole ground and hid the wet sheen; a layer of stones would need persistent stones, so hail leaves wet ground |
| Why did dew show rain? | The distant layer did not check the mode; it is removed for dew |
| Is dew visible? | `render_look.py macro dew` (100 mm, 0.6 m, f/4, the pavement as the only collider): beads of 0.4-2.2 mm show across the focus plane with glints toward a low sun. At the old 350 beads/m^2 one bead was in frame, so the preset is now 3000/m^2 (real dew is denser still; Max Beads caps the total, so collide only what you photograph) |

## Not verified

| Item | Why | How to close |
|---|---|---|
| Interactive Windows and Linux sessions, NVIDIA/AMD GPUs | CI covers headless Blender and Cycles CPU on Windows and Linux; the GPU check ran on Metal | Install the zip there and run the acceptance checklist |
| Real render-farm software | The farm test opens the baked file in a Blender without RainFX, which is what a farm node does; no farm manager was used | Submit a baked scene to the farm |

The Gunn-Kinzer reference speeds in `test_physics.py` (4.03, 6.49, 8.06, 8.83, 9.09 m/s at 1-5 mm) were checked
against the published table as reproduced in two rainfall-simulator papers and Hinkle (1987); see REFERENCES.md.

## Acceptance checklist (manual, before a release)

1. Install the zip (`python tools/build_extension.py`) in a clean profile, enable it, confirm the RainFX tab.
2. Run the Blender test scripts; all must pass.
3. Open a scene with a ground and a roof; add both as colliders; add Heavy Rain; turn on Wetness. Play from the
   start frame: nothing falls through the roof, the ground under it stays dry, the open ground is wet.
4. *Run Diagnostics*: "GN modifier API" and "Group sockets OK".
5. Switch through Hailstorm (bounces), Light Snow, Dew and Thunderstorm (flashes) with Live Update on.
6. Render frame 48 with EEVEE and with Cycles: rain bright in front of lights, puddles reflect, no fog wall.
7. Save, bake in the background, reopen, scrub: the baked frames play. Open the file with RainFX disabled and
   render the last frame: rain, wetness and drips are all there.
8. Open `tests/fixtures/scene_0_3_0.blend`, change the preset: no crash, rain and wetness continue.
9. Disable and remove the extension; purge orphans; no errors in the console.
