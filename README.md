# RainFX

**Physically based weather for Blender** — part of [OpenSimFX](https://github.com/opensimfx),
alongside BlastFX, FlowFX and AtmosFX.

RainFX brings physically based weather to Blender — dew, drizzle through downpour, wind-driven rain, thunderstorm, freezing rain, sleet, hail and snow. Drops are simulated with Geometry Nodes simulation zones and collide with your scene geometry through raycasts.

## Features

- **14 weather presets** — Dew through blizzard from `rainfx/data/presets.json` — extensible with your own user JSON files.
- **Real drop physics** — Marshall-Palmer size distribution, Gunn-Kinzer terminal velocity and drag relaxation toward the wind; hail and snow follow their own models.
- **Raycast collision** — Every particle step raycasts against the RainFX Colliders collection — no tunnelling through thin geometry.
- **Impact behaviour** — Splashes spawn ballistic droplets, hail and sleet bounce with restitution, snow sticks and recycles.
- **Wind with gusts** — Mean wind plus noise gusts in space and time; particles lag the air with relaxation time tau = v_t / g.
- **Atmosphere controls** — Fog volume (Volume Scatter), reversible sky and sun dimming, seeded lightning flashes; optional compositor glow chain never overwrites an existing setup.
- **Two engines, open output** — Geometry Nodes simulation zones plus a stock emitter engine with Collision modifiers; output as streaks, spheres or raw vertices for custom instancing.

## Install

Requires Blender **5.2.1** (target; supports Blender 5.0+).

```bash
python tools/build_extension.py        # -> dist/rainfx-0.2.0.zip
```

In Blender: *Edit > Preferences > Get Extensions > Install from Disk…*, pick the zip. The panel appears in the 3D Viewport sidebar (**N**) under **RainFX**.

For development, run Blender with the package folder symlinked into your extension repository, or use `blender --command extension build --source-dir rainfx`.

## Quick start

1. Model or open your scene (ground, buildings, props).
2. Select the objects that should stop rain, click **Add Selected as Colliders**.
3. Pick a preset, click **Add Weather Emitter** at the 3D cursor. Set the Volume (X, Y, height) to cover the camera view.
4. Start playback from the scene start frame. Rain needs roughly 2 s to fill the volume; start the timeline early or bake (RainFX panel → *Simulation → Bake*).
5. Render with EEVEE or Cycles. Streaks are already motion-blurred; disable renderer motion blur for the drops.

Full guide: `docs/USER_GUIDE.md`.

## Verification status (read this)

Verified in **headless Blender 5.0.1 (`bpy` wheel)**:

- Simulation passes physical assertions: no particle crosses the floor or a 2 m test cube, hail bounces, rain splashes, a control run without colliders fails the same check.
- Every preset runs, operators and live preset switching work.
- Fog, lightning keyframes, compositor and the particle-engine collision path work.

**Not verified** — treat as unknown:

- Runtime behaviour in Blender 5.2.1 itself (no 5.2 build was available at time of verification). The 5.2 modifier input path (`modifier.properties.inputs.<id>.value`) follows the official release notes and is covered by a logic test with a stand-in object, not by Blender.
- Rendered image quality (no GPU render was run).
- Blender's extension validator.
- Blender versions other than 5.0.1 and 5.2.1; Windows; GPU Cycles; EEVEE on CI or a machine without a GPU/display.

Run `tests/blender_smoke.py` and `tests/blender_scene_smoke.py` inside your 5.2.1 install first (`docs/SYSTEM_DESIGN.md`, Testing).

## Repository layout

```
rainfx/                 the add-on (what gets zipped)
  core/                 pure Python: physics, presets, schema, wind, collision
  nodes/                node-group builders (emitters, splash, fog, lightning)
  scene/                world, domain objects, render settings, orchestration
  ui/                   properties, operators, panels, preset conversion
  data/presets.json     the shipped preset library (generated)
  engine_particles/     stock particle-system engine (fallback)
tests/                  pytest suites + headless Blender checks
tools/                  build_extension, gen_presets
docs/                   SYSTEM_DESIGN, PHYSICS, USER_GUIDE, PRESETS, ROADMAP, TESTING
```

## Develop

```bash
# Pure tests (no Blender)
python -m pytest

# Headless Blender checks (needs bpy 5.0.1)
python tests/blender_smoke.py             # 23 checks, ~20 s
ATMOSFX_RENDER_TESTS=1 python tests/blender_smoke.py   # + render checks (if bpy supports)

# Build the extension zip
python tools/build_extension.py
```

See `docs/SYSTEM_DESIGN.md` for architecture, data flow, simulation algorithm, decisions and trade-offs; project structure; testing strategy.

## Documentation

[User Guide](docs/USER_GUIDE.md) · [Physics](docs/PHYSICS.md) · [System Design](docs/SYSTEM_DESIGN.md) · [Presets](docs/PRESETS.md) · [Roadmap](docs/ROADMAP.md)

## License

GPL-3.0-or-later (required for Blender extensions) — full text in [`LICENSE`](LICENSE).