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

#### Anti-vacuous-pass design

A collision test that passes because nothing ever reaches the collider proves nothing. `blender_smoke.py --control` runs the
same scene with the colliders removed and requires the *same* check to fail (particles found inside the cube). Measured:
32-47 particles inside the 2 m cube without colliders, 0 with colliders.

### 2. Running

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

Measured results, what is not verified, and the Blender 5.2.1 acceptance checklist are in
[VALIDATION.md](VALIDATION.md).

### 3. Adding tests

- Anything in `core/` gets a plain pytest test with a reference value and a source in the docstring.
- Anything touching `bpy` goes into one of the three Blender scripts. Prefer asserting physical outcomes (positions, counts, speeds) over "ran without error".
- When a check could pass vacuously, add a control run that must fail.

## Build and release

```bash
python tools/gen_presets.py          # only after editing the preset table
python tools/gen_preset_docs.py      # regenerates docs/PRESETS.md
python -m pytest tests               # plain tests
python tests/blender_smoke.py        # with a bpy-capable interpreter, see Testing
python tools/build_extension.py      # dist/rainfx-<version>.zip
blender --command extension validate dist/rainfx-<version>.zip
```

Version bump: edit `version` in `rainfx/blender_manifest.toml`, add a `CHANGELOG.md` entry, rebuild. Bump
`GROUP_VERSION` in `gn/precip.py` or `gn/dew.py` whenever the node graph changes so existing files rebuild the group.

## Adding things

| Task | Where |
|---|---|
| New preset | Add to the table in `tools/gen_presets.py`, run both generators |
| New weather mode | `core/presets.py` (`MODES`, `derive`), `gn/precip.py` (Mode switch), tests |
| New node group input | `gn/precip.py` interface + graph, `emitter.apply_preset`, bump `GROUP_VERSION`, update the table above |
| New Blender-version workaround | `compat.py` only, with a comment naming the release note |
