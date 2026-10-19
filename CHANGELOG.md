# Changelog

## 0.2.0 (unreleased)

- Background baking: *Bake* in the Engines panel gains a *Background bake* option that runs the
  disk bake in a second headless Blender process while you keep working, with live progress
  ("6/10 frames (60%)") drawn in the panel from the per-frame cache files; the cache is written
  where the in-process bake would put it, so playback consumes it unchanged. Packed bakes and
  the classic blocking bake behave exactly as before (packed stays in-process).
- Splash-impact fix: splash children (spawned on landing) no longer inherit the landed
  drop's `imp` flag, so invisible impact stamps no longer appear below surfaces (splash
  is ballistic and pierces the ground). Precip group bumped to version 8 so existing
  .blend files rebuild; the impact sink and event exports are cleaner (a heavy-rain
  24-frame export drops from 5848 to 5443 honest events); wetness and puddle thresholds
  re-checked against the de-polluted signal.
- Demo seeding on **Add Weather Emitter**: a 20 m demo ground plane (RainFX Surface) and a
  Suzanne (RainFX Suzanne) are generated and joined to the collision set the first time the
  operator runs, so rain lands visibly on real geometry right away. Idempotent by name;
  replace them with your own meshes any time via the Collision panel (Add Colliders) or
  delete them. Also fixes a live 0.1.0 crash: the MOD_SMOKE icon (removed in Blender 5.2)
  broke the panel draw — the ui smoke now asserts every icon literal against the real enum.
- Sound-ready events: the Collision panel gains "Export Impact Events" — replays the
  emitter's frame range and writes a JSON log (frame, position, intensity = landing drop
  diameter in mm, type impact/snow, fps, preset and mean terminal velocity) for audio
  middleware. Per frame at most 256 events are kept (even stride over the impact sink
  verts); no cache and no new geometry nodes: the export replays the deterministic sim
  run. Verified via tests/blender_events_smoke.py.
- Lens interaction: a compositor droplet stage ("Drops on the camera lens" — Lens Drops toggle)
  that warps the rendered frame like water stuck to the glass. When applied, the addon builds
  its own glare chain (or attaches to it) and inserts a Displacement stage driven by two
  procedurally generated droplet maps (round beads plus stretched drip streaks, 128px signed
  RGBA fields); two Transform nodes drift the maps downward at different speeds with frame
  drivers and REPEAT wrapping, so drops keep falling forever while the smear never repeats the
  same pattern. Strength scales the blob amplitude; re-toggling or changing strength re-bakes
  the maps in place (no per-frame Python). Stages only ever touch trees created by RainFX — a
  scene with foreign compositing nodes is left untouched. Verified via new blender_lens_smoke.py
  (chain build + idempotency + foreign-tree protection + strength rebake + removal/restoration +
  headless EEVEE A/B render diff + drift diff between frames).
- Distant rain: a cheap far-field drizzle layer ("RainFX Distant", Distant Rain toggle) so the
  near-field simulation can stay sparse. A static Geometry Nodes group scatters translucent
  streaks (from 0.02 up to 3.0 Distant Density of the simulation volume) into a 3x reach /
  double-height shelf around the emitter and wraps them through the box at the preset's own
  wind and terminal speed — no sim zone, no cache: every frame is a pure function of frame
  time, so replay and bake are safe, and streaks align with the fall vector and lengthen with
  speed like a time exposure. The layer object parents to the Follow Object exactly like the
  fog. Verified via new blender_distant_smoke.py (wrap containment over a full fall cycle,
  same-frame determinism, emitter-impact-attribute scan untouched with the layer on, follow
  tracking, EEVEE render).
- Snow cover: up-facing surfaces accumulate "rainfx_snow" under snow presets — the wetness helper
  counts flake landings (Snow Rate slider) into a per-vertex attribute and the post-sim Set
  Position lifts vertices along their normals by snow x *Snow Depth*, so roofs, tops and ledges
  get a soft white fade while the sim state itself stays undisplaced and bake-safe. Snowed faces
  brighten toward snow white and roughen. The impact carrier is now split: "RainFX Impacts" keeps
  rain wetting, "RainFX Snow Impacts" carries flakes only. Verified via the extended
  blender_wetness_smoke.py (ground 0.849 / cube top 0.539 / cube top lifted to z 2.0156 over
  97 frames; rain worlds stay snow-inert).
- Puddles and ripples: besides surface wetness, the wetness helper now accumulates a per-face
  "rainfx_pool" standing-water mask — flat up-facing spots pool instantly inside the impact
  footprint (low areas weight up to 65% stronger) and linger about 4x longer than wetness.
  Pooled faces get the full ripple shader: dark water colour, mirror gloss and a procedural
  noise-bump ripple pattern that drifts with a frame-driven time value. Same Wetness toggle,
  no new controls. Verified via the extended blender_wetness_smoke.py (ground 0.885 / cube
  top 0.285 / vertical walls 0.000 across 24 frames).
- Wetness: per-collider "rainfx_wet" attribute accumulates where drops actually land — wet faces sink
  to a dark pool colour and gloss up (roughness drops). Toggle *Wetness* in the Collision sub-panel with
  Wet Radius / Strength / Dry Rate. The hidden "RainFX Impacts" carrier feeds the helpers each frame
  (a frame_change_post handler copies the emitter's impact verts, keeping the depsgraph cycle-free);
  wet state lives in helper sim zones and stays bake-safe. Verified headless in Blender 5.2.1
  ("`tests/blender_wetness_smoke.py`").

- Determinism tests: twin emitters with the same seed render bit-identical rain every frame; playback
  replay and forced re-simulation reproduce it exactly, and a changed Seed moves only the changed
  emitter ("tests/blender_determinism_smoke.py").

- Material polish: restyled streak, splash, ice and snow shaders ("EEVEE and Cycles") — glassier thinner
  streaks (alpha 0.18 + faint self-shading emission), brighter splash, milkier ice, softer snow with
  subsurface scatter. New *Refraction Drops* toggle and 'drop' material kind: fully refractive spheres
  ("Transmission 1.0, alpha 1.0, IOR 1.33") for close-up shots ("tests/blender_material_smoke.py").

- Follow Object: the precipitation volume tracks any object's world location (usually the camera)
  through the new Follow Object / Follow Offset controls; moving emitters no longer freeze the rain.
  Verified headless in Blender 5.2.1 ("`tests/blender_follow_smoke.py`").
- Extension metadata: maintainer, website and copyright filled in (github.com/opensimfx/rainfx).
- Inside-collider cleanup: init rejects start points inside enclosed colliders with a +Z/-Z
  ray-parity test (both directions hit a surface only inside an enclosed volume), removing the
  ~2 s warm-up where seeded-in drops fell to a collider's inner faces. Open-top shapes and
  respawned points are not covered. Verified headless in Blender 5.2.1 ("`tests/blender_inside_smoke.py`").
- Collider velocity transfer: moving colliders (vehicles) push splashes and steer bounces. The node
  group snapshots the realised colliders inside the simulation state each step, matches vertices with
  Geometry Proximity and hands the sampled velocity at the hit to the impact physics (new *Collider
  Push* slider, default 1). Verified headless in Blender 5.2.1 ("`tests/blender_motion_smoke.py`").
- Bake workflow: *Bake* opens a dialog with the scene frame range pre-filled and a *Packed cache* option; a
  *Delete* button clears disk and packed caches. Playback over the baked range is identical to the live
  simulation ("`tests/blender_bake_smoke.py`). Bake the range you render, starting at the scene start frame.

## 0.1.0

- Geometry Nodes precipitation simulation: rain, hail, snow with raycast collision, bounce, splash, wind and gusts.
- 14 presets, user preset JSON files.
- Dew bead scattering with density cap.
- Fog volume, reversible sky and sun dimming, seeded lightning keyframes, optional compositor glow.
- Alternative engine on Blender emitter particle system with Collision modifiers.
- Compatibility layer for Blender 5.0 and 5.2 API changes.
