# Development and Testing

How to run, test and release RainFX. Architecture is in [SYSTEM_DESIGN.md](SYSTEM_DESIGN.md); contribution rules in
[CONTRIBUTING.md](../CONTRIBUTING.md).

## Testing

### 1. Layers

| Layer | Files | Needs Blender | What it proves |
|---|---|---|---|
| Unit | `tests/test_physics.py`, `tests/test_presets.py` | no | Formulas match reference values; presets validate; derived numbers are physical; user presets override and broken files are skipped |
| Simulation behaviour | `tests/blender_smoke.py` | yes (`bpy`) | The Geometry Nodes simulation obeys physics: no particle ends below the floor, none inside a collider, hail bounces, rain splashes, speeds plausible |
| Follow Object | `tests/blender_follow_smoke.py` | yes (`bpy`) | The volume relocates with the follow target during movement (spawn, wrap, recycle stay inside the moving box), fixed mode keeps emitter-local output |
| Moving colliders | `tests/blender_motion_smoke.py` | yes (`bpy`) | Splashes from a moving cube carry the cube's velocity (both run share and mean speed checked); push-off control run stays slow |
| Sheltered starts | `tests/blender_inside_smoke.py` | yes (`bpy`) | Start points no drop could reach (a ray back along the fall direction meets a collider) are rejected at init: ~7.5% of the volume around a closed room, zero primaries inside the cavity from the first frame |
| Bake workflow | `tests/blender_bake_smoke.py` | yes (`bpy`) | Disk bake (scene range) and packed bake replay covered frames exactly; delete clears disk blobs and restores live playback |
| Background bake | `tests/blender_bake_bg_smoke.py` | yes (`bpy`) | `baker.launch` spawns a second headless Blender on a copy of the scene as it is now; the parent polls the per-frame `.blob` files written since the launch (monotonic); double-launch is refused; the child bakes the chosen emitter (a decoy emitter stays unbaked) and includes a change made after the last save (+6 m/s wind: +0.30 m x drift by frame 5); after save and reopen, playback comes from the child's cache (a Seed change moves nothing); `finish` reaps the process, removes the snapshot and clears the module state; `bake_delete` resets. Facts: the child is `bpy.app.binary_path` (`sys.executable` is the bundled Python), the child script is a real file, paths and names are pasted as `repr()` literals, and blob layout is `<bake_dir>/<record-id>/blobs/{frame:05d}_00000.blob`. The parent's live preview keeps its old cache after an input change, so it is not a reference |
| Wetness | `tests/blender_wetness_smoke.py` | yes (`bpy`) | Helpers attach to every collider (the scene settings are not registered here, so there is no preset and no ambient wetness: this test covers the impact path; ambient wetness and sheltering are in Hardening); dry before rain, hit faces saturate >0.3, far faces stay <=0.05; pools fill on flat up-facing faces (ground/cube top) while vertical walls stay near-zero; toggle-off removes helpers; wet+pool+snow material wiring idempotent with ripple bump and frame driver (hidden "RainFX Impacts" carrier feeds helpers; carrier refresh runs inside frame_change_post). Snow sub-scene: light_snow world (compact 4x4x3 box for flake flux; Snow Rate 1.0 pushed on both helpers; walk limited to scene frame_end because sim zones stop stepping past it) — cube top accumulates rainfx_snow >0.2 and lifts z 2.0 -> 2.0156, rain worlds stay snow-inert (zmax 2.0) |
| Distant rain | `tests/blender_distant_smoke.py` | yes (`bpy`) | The far layer builds with preset-synced inputs (Box/Count/Wind/Fall Speed/Seed/Material); streaks realize into real verts and stay inside the inflated far shelf across a full fall cycle (frames 1/60/120); same-frame re-eval is bit-identical (pure frame function, no cache); the emitter's eval mesh (impact scan) is unchanged with the layer on vs off over a 124-frame walk; follow parenting tracks a mover; toggle-off is idempotent; headless EEVEE frame renders. (Headless emitter inspection needs the `Viewport Density` / `Output Mode` pushes, mirroring blender_smoke.py) |
| Lens interaction | `tests/blender_lens_smoke.py` | yes (`bpy`) | apply_lens builds the marked droplet stage (6 nodes, both Transform drivers evaluate when the frame is set); second call adds nothing; a foreign unmarked compositing tree is returned untouched; strength rebake bakes mapped values idempotently; remove_lens restores the bare chain and drops the maps; headless EEVEE 64px A/B render (compositing on vs off) shows a visible warp (mean diff ≫ noise floor) and frames 10 vs 26 differ (drift is live). Generated maps must be `float_buffer=True` — byte images saturate the signed displacement to a no-op; map size stays at 128px because ≥256px generated images sample black in the 5.2 compositor |
| Materials | `tests/blender_material_smoke.py` | yes (`bpy`) | Every material builds with sane alpha/transmission; *Refraction Drops* swaps only water presets to the drop variant; headless EEVEE frame renders |
| Look | `tests/blender_look_smoke.py` | desktop Blender 5.2.3 | Streak materials are translucent + Fresnel gloss (no emission, no Principled diffuse) with per-streak alpha jitter + Fresnel rim; a 0.3 material is upgraded in place; fog density and compositor glow follow the preset rain rate; wet shading keeps a textured Base Color and a normal map, darkens porous stone by 0.8 and metal not at all, flattens normals in puddles; the backlight sits behind the rain, shines back toward the camera (20 deg off the camera line), is hidden from camera rays and is never duplicated; EEVEE frame renders |
| Detail | `tests/blender_detail_smoke.py` | desktop Blender 5.2.3 | Splashes are decided per drop by K = We Oh^-2/5: a threshold above every K gives none, drizzle gives none even at Splash Amount 6, splashing drops are bigger than the average landing; crowns are static, sit on up-facing faces, live at most 0.1 s and switch off; puddle ripple weight rises light < heavy < downpour; spray mist only from heavy rain at the derived density; the foreground layer follows the camera, hides streaks in the clear zone and is removed for snow; EEVEE frame renders |
| Sound-ready events | `tests/blender_events_smoke.py` | yes (`bpy`) | export_events replays a heavy_rain world for 24 frames and writes a JSON with sane metadata and thousands of events (frames in range, positions on the ground/cube top, intensities = drop diameters > 0, types impact/snow); no frame ever exceeds the per-frame cap of 256 (odd strides ceil–rounded); a pushed Viewport Density value is restored after the walk; light_snow exports strictly snow-typed events (97-frame world); a collider-less drizzle world exports a valid empty log. (Headless emitters need the `Viewport Density` push, which the exporter does itself and restores) |
| Determinism | `tests/blender_determinism_smoke.py` | yes (`bpy`) | Twin emitters with the same seed are bit-identical every frame; scrub replay and forced re-sim match exactly; a changed Seed moves only the changed emitter (input changes need a cache delete to dirty the sim) |
| Scene helpers | `tests/blender_scene_smoke.py` | yes | Fog and lighting scale and revert, lightning keyframes fire, compositor is not overwritten, dew is capped, the particle engine collides and kills, the 5.2 input-path branch logic |
| UI | `tests/blender_ui_smoke.py` | yes | Register / unregister, operators, live preset switching, diagnostics; the [Demo] block asserts add_emitter seeds the demo plane + Suzanne into the collider set (idempotent on re-run), and the icon-enum guard scans every `icon="..."` literal in `rainfx/ui/*.py` against the real `UILayout` enum (regression for the MOD_SMOKE icon removed in 5.2) |
| Hardening | `tests/blender_hardening_smoke.py` | yes (`bpy`) | Wetness keeps accumulating after save and reopen (persistent handler); a moved, rotated and scaled cube gets wet where the rain lands (control with the old transform space: 0.00-0.06); two emitters both feed the carrier; rebuilding a stale group keeps every user; ground under a roof stays dry in still air while open ground is 100% wet; unregister removes the handler and the bake timer |
| Upgrade | `tests/blender_upgrade_smoke.py` | yes (`bpy`) | `tests/fixtures/scene_0_3_0.blend` (made by `tests/fixtures/make_scene_0_3_0.py` with the released 0.3.0) plays as saved; changing the preset rebuilds every group without a crash and leaves no modifier without a group; rain and wetness continue on the face-corner domain; the lens stage is rebuilt with its 9 nodes |
| Drips | `tests/blender_drips_smoke.py` | yes (`bpy`) | Drip points line a roof's edge only (none on a covered ledge, a curb or the ground's border), fall heights match the air below, drops stay between roof and ground and are a pure function of time, heavier rain drips faster, snow and the toggle remove the layer |
| Render farm | `tests/blender_farm_smoke.py` | yes (`bpy`) | A baked scene opened in a fresh Blender without RainFX (factory settings, as a farm node) and jumped straight to the last frame shows the rain, the cube's wetness from simulated hits and the drips, for a packed in-process bake and a disk background bake; unbaked, the same jump shows no wetness |

#### Anti-vacuous-pass design

A collision test that passes because nothing ever reaches the collider proves nothing. `blender_smoke.py --control` runs the
same scene with the colliders removed and requires the *same* check to fail (particles found inside the cube). Measured:
32-47 particles inside the 2 m cube without colliders, 0 with colliders.

### 2. Running

Plain tests (Python 3.11+):

```bash
python -m pytest            # 45 tests
```

Inside an installed Blender (Blender bundles numpy). Pass `--` so a script does not read Blender's own options:

```bash
BLENDER=/Applications/Blender.app/Contents/MacOS/Blender
$BLENDER -b --factory-startup --python-exit-code 1 --python tests/blender_smoke.py -- --control heavy_rain hailstorm light_snow
for t in tests/blender_*_smoke.py; do $BLENDER -b --factory-startup --python-exit-code 1 --python "$t" -- || echo "FAILED $t"; done
```

With the PyPI `bpy` wheel (Python 3.11 for bpy 5.0.x, 3.13 for 5.2.x) the non-rendering scripts run as
`python tests/blender_smoke.py`; the rendering ones (look, material, distant, detail, lens) need EEVEE and a desktop
Blender.

CI (`.github/workflows/ci.yml`) runs the plain tests on Linux, Windows and macOS (Python 3.11 and 3.13), checks
that `rainfx/data/presets.json` and `docs/PRESETS.md` match their generators, and on Linux builds and validates
the zip, runs every Blender script that does not render with EEVEE in Blender 5.2.3 and 5.2.4 and renders the
street bench in Cycles; a Windows job runs the simulation, bake, background-bake, farm, wetness, hardening,
upgrade, drips and UI scripts in Blender 5.2.3 and renders the bench in Cycles.

The look is checked by eye in a street scene: `tools/render_look.py -- <shot> <preset> <out.png> [samples] [frame]`
with shots `street_night`, `street_day`, `puddle`, `wide` and `macro` (dew) (environment: `RAINFX_W`/`RAINFX_H` resolution,
`RAINFX_WET_START=0` to start dry, `RAINFX_DRIPS=0`, `RAINFX_LENS=1`, `RAINFX_HOOK=<script>` run before the render).
The README images are these shots at 1280 x 720, 128 samples, frame 48.

Measured results, what is not verified, and the acceptance checklist are in [VALIDATION.md](VALIDATION.md).

### 3. Adding tests

- Anything in `core/` gets a plain pytest test with a reference value and a source in the docstring.
- Anything touching `bpy` goes into a `tests/blender_*_smoke.py` script (add it to the CI list unless it renders). Prefer asserting physical outcomes (positions, counts, speeds) over "ran without error".
- When a check could pass vacuously, add a control run that must fail.

## Build and release

```bash
python tools/gen_presets.py          # only after editing the preset table
python tools/gen_preset_docs.py      # regenerates docs/PRESETS.md
python -m pytest tests               # plain tests
# every Blender script, see Testing
python tools/build_extension.py      # dist/rainfx-<version>.zip
blender --command extension validate dist/rainfx-<version>.zip
```

Version bump: edit `version` in `rainfx/blender_manifest.toml`, add a `CHANGELOG.md` entry, rebuild. Bump
`GROUP_VERSION` in the `gn/` module whenever a node graph changes, `MATERIAL_VERSION` / `WET_VERSION` in
`gn/materials.py` for shaders and `FOG_VERSION` in `scene/atmosphere.py` for the fog, so existing files rebuild
them (`tests/blender_upgrade_smoke.py` opens a 0.3.0 scene).

## Adding things

| Task | Where |
|---|---|
| New preset | Add to the table in `tools/gen_presets.py`, run both generators |
| New weather mode | `core/presets.py` (`MODES`, `derive`), `gn/precip.py` (Mode switch), tests |
| New node group input | `gn/precip.py` interface + graph, `emitter.apply_preset`, bump `GROUP_VERSION`, update the table above |
| New Blender-version workaround | `compat.py` only, with a comment naming the release note |
