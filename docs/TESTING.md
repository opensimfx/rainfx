# Testing

## 1. Layers

| Layer | Files | Needs Blender | What it proves |
|---|---|---|---|
| Unit | `tests/test_physics.py`, `tests/test_presets.py` | no | Formulas match reference values; presets validate; derived numbers are physical; user presets override and broken files are skipped |
| Simulation behaviour | `tests/blender_smoke.py` | yes (`bpy`) | The Geometry Nodes simulation obeys physics: no particle ends below the floor, none inside a collider, hail bounces, rain splashes, speeds plausible |
| Follow Object | `tests/blender_follow_smoke.py` | yes (`bpy`) | The volume relocates with the follow target during movement (spawn, wrap, recycle stay inside the moving box), fixed mode keeps emitter-local output |
| Moving colliders | `tests/blender_motion_smoke.py` | yes (`bpy`) | Splashes from a moving cube carry the cube's velocity (both run share and mean speed checked); push-off control run stays slow |
| Inside-collider starts | `tests/blender_inside_smoke.py` | yes (`bpy`) | Start points inside a closed room are rejected at init (~5% of the volume rejected, zero primaries inside the cavity from the first frame) |
| Bake workflow | `tests/blender_bake_smoke.py` | yes (`bpy`) | Disk bake (scene range) and packed bake replay covered frames exactly; delete clears disk blobs and restores live playback |
| Background bake | `tests/blender_bake_bg_smoke.py` | yes (`bpy`) | `baker.launch` spawns a second headless Blender on the saved .blend that bakes the disk cache itself; the parent polls the per-frame `.blob` files (progress = blobs written vs expected, monotonic); double-launch is refused while one runs; parent playback after the child bake matches the live sim exactly (max delta 0); `finish` reaps the process and clears the module state; `bake_delete` resets. Facts: child must be spawned with `sys.argv[0]` (Blender binary — `sys.executable` is the bundled python), the child script is a real file (`--python-expr` can't take multiline code), `$BAKE_DIR` substitution must be quoted, and blob layout is `<bake_dir>/<record-id>/blobs/{frame:05d}_00000.blob` |
| Wetness | `tests/blender_wetness_smoke.py` | yes (`bpy`) | Helpers attach to every collider; dry before rain, hit faces saturate >0.3, far faces stay <=0.05; pools fill on flat up-facing faces (ground/cube top) while vertical walls stay near-zero; toggle-off removes helpers; wet+pool+snow material wiring idempotent with ripple bump and frame driver (hidden "RainFX Impacts" carrier feeds helpers; carrier refresh runs inside frame_change_post). Snow sub-scene: light_snow world (compact 4x4x3 box for flake flux; Snow Rate 1.0 pushed on both helpers; walk limited to scene frame_end because sim zones stop stepping past it) — cube top accumulates rainfx_snow >0.2 and lifts z 2.0 -> 2.0156, rain worlds stay snow-inert (zmax 2.0) |
| Distant rain | `tests/blender_distant_smoke.py` | yes (`bpy`) | The far layer builds with preset-synced inputs (Box/Count/Wind/Fall Speed/Seed/Material); streaks realize into real verts and stay inside the inflated far shelf across a full fall cycle (frames 1/60/120); same-frame re-eval is bit-identical (pure frame function, no cache); the emitter's eval mesh (impact scan) is unchanged with the layer on vs off over a 124-frame walk; follow parenting tracks a mover; toggle-off is idempotent; headless EEVEE frame renders. (Headless emitter inspection needs the `Viewport Density` / `Output Mode` pushes, mirroring blender_smoke.py) |
| Lens interaction | `tests/blender_lens_smoke.py` | yes (`bpy`) | apply_lens builds the marked droplet stage (6 nodes, both Transform drivers evaluate when the frame is set); second call adds nothing; a foreign unmarked compositing tree is returned untouched; strength rebake bakes mapped values idempotently; remove_lens restores the bare chain and drops the maps; headless EEVEE 64px A/B render (compositing on vs off) shows a visible warp (mean diff ≫ noise floor) and frames 10 vs 26 differ (drift is live). Generated maps must be `float_buffer=True` — byte images saturate the signed displacement to a no-op; map size stays at 128px because ≥256px generated images sample black in the 5.2 compositor |
| Materials | `tests/blender_material_smoke.py` | yes (`bpy`) | Every material builds with sane alpha/transmission; *Refraction Drops* swaps only water presets to the drop variant; headless EEVEE frame renders |
| Sound-ready events | `tests/blender_events_smoke.py` | yes (`bpy`) | export_events replays a heavy_rain world for 24 frames and writes a JSON with sane metadata and thousands of events (frames in range, positions on the ground/cube top, intensities = drop diameters > 0, types impact/snow); no frame ever exceeds the per-frame cap of 256 (odd strides ceil–rounded); a pushed Viewport Density value is restored after the walk; light_snow exports strictly snow-typed events (97-frame world); a collider-less drizzle world exports a valid empty log. (Headless emitters need the `Viewport Density` push, which the exporter does itself and restores) |
| Determinism | `tests/blender_determinism_smoke.py` | yes (`bpy`) | Twin emitters with the same seed are bit-identical every frame; scrub replay and forced re-sim match exactly; a changed Seed moves only the changed emitter (input changes need a cache delete to dirty the sim) |
| Scene helpers | `tests/blender_scene_smoke.py` | yes | Fog and lighting scale and revert, lightning keyframes fire, compositor is not overwritten, dew is capped, the particle engine collides and kills, the 5.2 input-path branch logic |
| UI | `tests/blender_ui_smoke.py` | yes | Register / unregister, operators, live preset switching, diagnostics; the [Demo] block asserts add_emitter seeds the demo plane + Suzanne into the collider set (idempotent on re-run), and the icon-enum guard scans every `icon="..."` literal in `rainfx/ui/*.py` against the real `UILayout` enum (regression for the MOD_SMOKE icon removed in 5.2) |

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
| UI smoke | passed: register, add emitter, live switch thunderstorm to hailstorm to dew to heavy snow, diagnostics, legacy emitter, compositor, revert lighting; **[Demo]**: the add op seeds a 4-vert *RainFX Surface* plane + a Suzanne (>100 verts in 5.2.1) into the colliders collection at the origin and is idempotent on re-run; **icon guard**: every `icon="..."` literal in `rainfx/ui/*.py` is asserted against the real `UILayout` enum (regression for MOD_SMOKE, removed in Blender 5.2) |
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
