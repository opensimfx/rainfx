# Testing

## 1. Layers

| Layer | Files | Needs Blender | What it proves |
|---|---|---|---|
| Unit | `tests/test_physics.py`, `tests/test_presets.py` | no | Formulas match reference values; presets validate; derived numbers are physical; user presets override and broken files are skipped |
| Simulation behaviour | `tests/blender_smoke.py` | yes (`bpy`) | The Geometry Nodes simulation obeys physics: no particle ends below the floor, none inside a collider, hail bounces, rain splashes, speeds plausible |
| Follow Object | `tests/blender_follow_smoke.py` | yes (`bpy`) | The volume relocates with the follow target during movement (spawn, wrap, recycle stay inside the moving box), fixed mode keeps emitter-local output |
| Moving colliders | `tests/blender_motion_smoke.py` | yes (`bpy`) | Splashes from a moving cube carry the cube's velocity (both run share and mean speed checked); push-off control run stays slow |
| Scene helpers | `tests/blender_scene_smoke.py` | yes | Fog and lighting scale and revert, lightning keyframes fire, compositor is not overwritten, dew is capped, the particle engine collides and kills, the 5.2 input-path branch logic |
| UI | `tests/blender_ui_smoke.py` | yes | Register / unregister, operators, live preset switching, diagnostics |

### Anti-vacuous-pass design

A collision test that passes because nothing ever reaches the collider proves nothing. `blender_smoke.py --control` runs the
same scene with the colliders removed and requires the *same* check to fail (particles found inside the cube). Measured:
32-47 particles inside the 2 m cube without colliders, 0 with colliders.

## 2. Running

Plain tests (any Python 3.10+):

```bash
python -m pytest            # 21 tests
```

Blender tests with the PyPI `bpy` wheel (Python 3.11 for bpy 5.0.x; 5.2 wheels need the Python version that release specifies):

```bash
python tests/blender_smoke.py --control heavy_rain hailstorm light_snow
python tests/blender_scene_smoke.py
python tests/blender_ui_smoke.py
```

Inside an installed Blender (recommended for 5.2.1; Blender bundles numpy):

```bash
blender -b --factory-startup --python tests/blender_smoke.py -- --control heavy_rain hailstorm
blender -b --factory-startup --python tests/blender_scene_smoke.py
blender -b --factory-startup --python tests/blender_ui_smoke.py
```

## 3. Results recorded while building (Blender 5.0.1 headless, 1 CPU)

| Test | Result |
|---|---|
| Plain pytest | 21 passed |
| Simulation, all 13 simulated presets (drizzle, light, moderate, heavy, downpour, wind-driven, thunderstorm, freezing rain, sleet, hailstorm, light snow, heavy snow, blizzard) | passed: 0 below floor, 0 inside the cube at frame 90, splashes for splashing presets, hail and sleet bounced |
| Control run (no colliders) | passed: found 32-47 particles inside the cube |
| Scene helpers (7 tests) | passed; dew limited to 199,723 beads by the cap; particle engine: 192 born, 74 alive at frame 100 (the rest killed by colliders), none below the floor |
| UI smoke | passed: register, add emitter, live switch thunderstorm to hailstorm to dew to heavy snow, diagnostics, legacy emitter, compositor, revert lighting |
| Bake operator | returns FINISHED on a saved file; the resulting cache contents were not independently inspected |
| Performance | 19,200 particles 33 ms/frame, 76,800 116 ms, 122,880 189 ms |

Mean speeds measured (heavy rain 5.5 m/s = sqrt(3.85^2 + 4^2) as predicted by terminal speed plus wind) match the derived values.

## 4. Not verified

| Item | Why | How to close |
|---|---|---|
| Blender 5.2.1 runtime | No 5.2 build or wheel was available. Everything above ran on 5.0.1 | Run the three Blender test scripts in 5.2.1 (section 5) |
| 5.2 modifier input path | Only logic-tested with a stand-in object | `blender_ui_smoke.py` exercises it for real in 5.2; `Run Diagnostics` shows which path is active |
| Rendered appearance | No render was performed; EEVEE and Cycles materials are untuned | Render a test frame (section 5, step 6) |
| Extension manifest | Blender's validator was not available | `blender --command extension validate dist/rainfx-0.1.0.zip` |
| Cache contents after Bake | Operator run only | Bake, save, reopen, scrub |
| Animated colliders, determinism across sessions | Not covered | Add tests before relying on them |
| Gunn-Kinzer reference values in `test_physics.py` | Entered from memory of the published table (4.03, 6.49, 8.06, 8.83, 9.09 m/s) and not re-read from a fetched source | Compare with the original table |
| Interactive UI (drawing, redraw, undo) | Headless cannot draw panels | Open the sidebar and click through |
| Multiple emitters, huge colliders | Not tested | Manual |

## 5. Acceptance checklist for Blender 5.2.1

1. Install the zip (`python tools/build_extension.py`), enable it, confirm the RainFX tab appears.
2. Run the three scripts above inside 5.2.1; all must print PASS.
3. Open a scene with a ground plane and a roof; add both as colliders; add Heavy Rain; play from frame 1; confirm nothing falls through the roof and that the space under it stays dry.
4. Click *Run Diagnostics*; it must report "GN modifier API: properties.inputs (5.2+)" and "Group sockets OK".
5. Switch through Hailstorm (bounces), Light Snow, Dew, Thunderstorm (flashes) with Live Update on.
6. Render frame 60 with EEVEE and with Cycles at low samples; check streak visibility with a back light.
7. Save, bake, reopen, scrub the timeline; compare frame 60 before and after reopening.
8. Disable and remove the extension; purge orphans; confirm no errors in the console.

## 6. Adding tests

- Anything in `core/` gets a plain pytest test with a reference value and a source in the docstring.
- Anything touching `bpy` goes into one of the three Blender scripts. Prefer asserting physical outcomes (positions, counts, speeds) over "ran without error".
- When a check could pass vacuously, add a control run that must fail.
