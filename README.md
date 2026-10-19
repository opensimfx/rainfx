# RainFX

Physically based weather for Blender: dew, drizzle through downpour, wind-driven rain, thunderstorm, freezing rain,
sleet, hail and snow. Particles are simulated with Geometry Nodes simulation zones and collide with your scene
geometry through raycasts. Target: Blender 5.2.1 (supports 5.0+; see compatibility).

## What it does

| Capability | How |
|---|---|
| 14 presets (dew, drizzle, light / moderate / heavy rain, downpour, wind-driven rain, thunderstorm, freezing rain, sleet, hailstorm, light / heavy snow, blizzard) | `rainfx/data/presets.json`, extensible with user JSON files |
| Real drop physics | Marshall-Palmer size distribution, Gunn-Kinzer terminal velocity, drag relaxation toward wind, hail and snow models (`docs/PHYSICS.md`) |
| Collision with any mesh | Raycast along every particle step against the `RainFX Colliders` collection. No tunnelling through thin geometry |
| Impact behaviour | Rain splashes (spawned droplets, ballistic, aged), hail and sleet bounce with restitution, snow sticks and recycles |
| Wind | Mean wind plus noise gusts in space and time; particles lag the air with relaxation time tau = v_t / g |
| Atmosphere | Fog volume (Volume Scatter), sky and sun dimming (reversible), seeded lightning flashes |
| Compositor | Optional glow chain; never overwrites an existing compositor setup |
| Second engine | Blender emitter particle system with Collision modifiers on all colliders, for users of the stock tools |
| Output | Instances (streaks or spheres) or raw vertices for custom instancing |

## Install

1. `python tools/build_extension.py` produces `dist/rainfx-0.1.0.zip`.
2. Blender: Edit > Preferences > Get Extensions > top-right menu > Install from Disk, choose the zip.
3. 3D Viewport sidebar (N) > RainFX tab.

For development, run Blender with the package folder symlinked into your extension repository, or use
`blender --command extension build --source-dir rainfx`.

## 60-second workflow

1. Model or open your scene (ground, buildings, props).
2. Select the objects that should stop rain, click **Add Selected as Colliders**.
3. Pick a preset, click **Add Weather Emitter** at the 3D cursor. Set the Volume (X, Y, height) to cover the camera view.
4. Start playback from the scene start frame. Rain needs roughly 2 s to fill the volume; start the timeline early or bake (RainFX panel → *Simulation → Bake*).
5. Render with EEVEE or Cycles. Streaks are already motion-blurred; disable renderer motion blur for the drops.

Full guide: `docs/USER_GUIDE.md`.

## Documentation map

| Document | Content |
|---|---|
| `docs/SYSTEM_DESIGN.md` | Architecture, data flow, simulation algorithm, decisions and trade-offs; project structure; testing strategy |
| `docs/PHYSICS.md` | Models, equations, sources, how real values become simulation inputs; research sources and reference analysis |
| `docs/USER_GUIDE.md` | Workflow, render settings, baking, troubleshooting; Blender integration notes (Geometry Nodes, compositor, render engines, 5.x API changes) |
| `docs/PRESETS.md` | Preset table (generated), schema, user presets |
| `docs/ROADMAP.md` | Phased plan |

## Verification status (read this)

Verified in headless Blender 5.0.1 (`bpy` wheel): the simulation passes physical assertions (no particle crosses the
floor or a 2 m test cube, hail bounces, rain splashes, a control run without colliders fails the same check), every
preset runs, operators and live preset switching work, fog, lightning keyframes, compositor and the particle-engine
collision path work.

**Not verified:** runtime behaviour in Blender 5.2.1 itself (no 5.2 build was available). The 5.2 modifier input path
(`modifier.properties.inputs.<id>.value`) follows the official release notes and is covered by a logic test with a
stand-in object, not by Blender. Also not verified: rendered image quality (no GPU render was run) and Blender's
extension validator. Run `tests/blender_smoke.py` and `tests/blender_scene_smoke.py` inside your 5.2.1 install first
(`docs/SYSTEM_DESIGN.md`, Testing).

## License

GPL-3.0-or-later (required for Blender extensions) — full text in [`LICENSE`](LICENSE).
