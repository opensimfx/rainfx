# Validation

What was measured, what is not verified, and the acceptance checklist for Blender 5.2.1. How to run the
checks is in [DEVELOPMENT.md](DEVELOPMENT.md).

## Results recorded while building (Blender 5.0.1 headless, 1 CPU)

| Test | Result |
|---|---|
| Plain pytest | 21 passed |
| Simulation, all 13 simulated presets (drizzle, light, moderate, heavy, downpour, wind-driven, thunderstorm, freezing rain, sleet, hailstorm, light snow, heavy snow, blizzard) | passed: 0 below floor, 0 inside the cube at frame 90, splashes for splashing presets, hail and sleet bounced |
| Control run (no colliders) | passed: found 32-47 particles inside the cube |
| Scene helpers (7 tests) | passed; dew limited to 199,723 beads by the cap; particle engine: 192 born, 74 alive at frame 100 (the rest killed by colliders), none below the floor |
| UI smoke | passed: register, add emitter, live switch thunderstorm to hailstorm to dew to heavy snow, diagnostics, legacy emitter, compositor, revert lighting; **[Demo]**: the add op seeds a 4-vert *RainFX Surface* plane + a Suzanne (>100 verts in 5.2.1) into the colliders collection at the origin and is idempotent on re-run; **icon guard**: every `icon="..."` literal in `rainfx/ui/*.py` is asserted against the real `UILayout` enum (regression for MOD_SMOKE, removed in Blender 5.2) |
| Bake operator | returns FINISHED on a saved file; the resulting cache contents were not independently inspected |
| Performance | 19,200 particles 33 ms/frame, 76,800 116 ms, 122,880 189 ms |

Mean speeds measured (heavy rain 5.5 m/s = sqrt(3.85^2 + 4^2) as predicted by terminal speed plus wind) match the derived values.

## Not verified

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

## Acceptance checklist for Blender 5.2.1

1. Install the zip (`python tools/build_extension.py`), enable it, confirm the RainFX tab appears.
2. Run the three scripts above inside 5.2.1; all must print PASS.
3. Open a scene with a ground plane and a roof; add both as colliders; add Heavy Rain; play from frame 1; confirm nothing falls through the roof and that the space under it stays dry.
4. Click *Run Diagnostics*; it must report "GN modifier API: properties.inputs (5.2+)" and "Group sockets OK".
5. Switch through Hailstorm (bounces), Light Snow, Dew, Thunderstorm (flashes) with Live Update on.
6. Render frame 60 with EEVEE and with Cycles at low samples; check streak visibility with a back light.
7. Save, bake, reopen, scrub the timeline; compare frame 60 before and after reopening.
8. Disable and remove the extension; purge orphans; confirm no errors in the console.
