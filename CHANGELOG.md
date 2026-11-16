# Changelog

## 1.0.0 (2026-11-16)

First stable release. Scenes made with 0.3 open and play as saved; the first change you make (or *Apply*)
upgrades their node groups, materials, fog and lens stage in place. Wetness built by 0.3 starts again.

### Rain that looks filmed (research in `docs/PHYSICS.md`, *Look*)

- Streaks are lit from behind, like real drops: a raindrop shows a wide view of what lies behind it (Garg &
  Nayar), so the streak shader is now translucent with a weak Fresnel gloss instead of a Principled BSDF with
  10 % white diffuse. Rain blazes in front of a lamp, reads against dark walls by day and vanishes against the
  sky, instead of glowing evenly everywhere. No constant emission; per-streak alpha jitter and a Fresnel rim.
- Drops near the camera are drawn at their true size: *Visual Scale* now fades in with distance (full width
  past 2 x scale metres), so drops passing the lens are no longer finger-thick sticks. Splashes and crowns
  follow the same rule, which keeps crowns small in close-ups.
- New *Add Rain Backlight* (Scene Integration): a hard spot beyond the rain aimed back at the camera, hidden
  from camera rays; *Street Lamp*, *Moonlight* or *Neutral*.
- Fog follows the rain rate (preset field `fog_mist` x measured rain extinction) and now reaches 3 x the rain
  volume with soft edges, so its box no longer shows as a wall of haze in wide shots. The compositor glow
  around lights grows with the rain rate. Rain presets from 8 mm/h add a low spray mist over the ground.
- Splashes are decided per drop: K = We Oh^-2/5 from each drop's own size and impact speed, against the new
  *Splash Threshold*; drizzle never splashes, big drops throw more and faster droplets. *Splash Amount* now
  means the droplets of a 2 mm drop at terminal speed (rain presets raised to 2-6).
- Crowns: a splashing drop on an up-facing surface leaves a short open ring (0.1 s) growing as sqrt(t);
  *Crowns* on the modifier turns them off.
- New *Drips*: drops falling from the edges of roofs, sills and lamp heads the rain reaches, with a growing
  bead at each drip point; faster in heavier rain. Found on the colliders; pure function of time (no cache).
- New *Foreground Rain*: big, soft streaks 0.6-4 m around the active camera, the near layer of filmed rain.
- Lens drops blur what is seen through them; the faster layer has sliding drops with wet trails.

### Wet surfaces

- Every surface the rain can reach is wet, not only where simulated drops landed: a ray test toward where the
  rain comes from (five rays from straight up to the full wind tilt) finds what is exposed, so open ground and windward
  walls are wet, ground under a roof stays dry and a street canyon gets a soft rain shadow on its upwind side.
  New *Already Wet* (on: wet from the first frame; off: wets up over 10-120 s, faster in heavier rain) and
  *Puddles* (standing water on exposed flat ground, scaled by the rain rate). Simulated hits add detail on top.
- Wet shading after Lagarde: albedo darkens by porosity and keeps its hue, metal does not darken, roughness
  tends to a water film's (0.18) so lights streak on wet asphalt, puddles are near mirrors with ring ripples
  (more rings in heavier rain) and flatten the material's normal map. Textured inputs stay connected.
- No more tiles: wet and pool are stored per face corner, blending across faces but never bleeding down a
  wall; puddles fill the low spots of a noise height map, giving organic edges at any mesh resolution.
- Impact footprints are Gaussian (were exponential), so repeated rain no longer creeps under roofs.
- Fix: moved, rotated or scaled colliders got wet in the wrong place (impacts were compared in the wrong
  space).
- Fix: wetness stopped after reopening a file and in command-line renders (its frame handler was dropped on
  load); it also read only the first emitter. All emitters now feed it.
- The Collisions panel lists colliders too coarse for wetness detail (edges over 4 x *Wet Radius*). The demo
  ground is a 64 x 64 grid instead of one quad.
- Moving, editing, adding or removing a collider refreshes the sheltering and the drip points by itself after
  half a second (not during playback, rendering or Edit Mode; keyframed colliders keep the pose of the last
  refresh).

### Snow, hail and dew

- Snow settles: exposed up-facing surfaces carry a snow cover from the first frame (*Already Snowy*, the same
  switch as *Already Wet*) or build it up, from about 0.57 x *Snow Depth* in light snow to full in heavy snow
  and blizzards; ground under shelter and in the lee of buildings stays bare, with soft edges. Flake landings
  still add on top.
- Snowflakes are 35 % translucent, so they glow in front of lamps and a bright sky instead of reading as grey
  specks; snow presets have about twice the flakes (light 18, heavy 55, blizzard 75 per m^3) and Visual Scale 4.
- *Distant Rain* draws snow presets as round ~2 cm flakes in the snow material (1.5 x the count) instead of rain
  streaks.
- Fix: *Distant Rain* added falling rain streaks to the Dew preset; it is removed for dew.
- Dew is denser: 3000 beads per m^2 (was 350, which left one bead in a macro frame); collide only the object you
  photograph, since *Max Beads* caps the total over all colliders.

### Reliability

- Baked scenes render anywhere: *Bake* (in this Blender or in the background) now bakes the wetness on every
  collider together with the rain, with the impact feed running while Blender steps the frames, so a render
  farm without RainFX renders the same rain, wetness and drips as your machine (`blender_farm_smoke.py` opens
  the baked file in a Blender without the add-on). *Delete* clears both.
- Fix: lens-drop maps were lost when the file was saved and reopened (generated images keep no pixels); they
  are now packed into the .blend as float EXR, exactly.
- Rain no longer starts under shelters: start points that a drop could not have reached (a ray back along its
  fall direction meets a collider) are removed, so ground under a roof is dry from the first frame.
- Background bake: bakes the scene as it is now (a temporary copy), not as last saved; bakes the chosen
  emitter, not the first one in the file; works with any path on Windows (the cache path was pasted into a
  Python string, so backslashes broke it); shows progress only for this bake's files.
- Disabling or updating RainFX during a background bake stops the child Blender and the progress timer, and
  the frame handler is removed.
- Fix: changing a setting in a scene from an older version crashed Blender (a rebuilt node group kept the old
  group's simulation state); rebuilt groups also no longer drop other emitters or colliders that used them.
- Fix: a 0.3 lens stage is rebuilt with the blur when the lens is applied again.
- Fix: the fog and spray boxes no longer share a face with the ground (Cycles lit the ground inside them).
- Fix: the *Distant Rain* layer was scaled twice and spread over ~2.3 km; it spans its 48 m box.
- Continuous integration: pure tests on Linux, Windows and macOS (Python 3.11 and 3.13); Linux jobs build and
  validate the zip, run every non-EEVEE Blender test in Blender 5.2.3 and 5.2.4 and render the street bench in
  Cycles; a Windows job runs the simulation, wetness, bake (including the background bake), farm, upgrade and UI
  tests in Blender 5.2.3 and renders the bench in Cycles.
- New tests: `blender_hardening_smoke.py` (reopen, transformed colliders, several emitters, group rebuild,
  shelter, collider watcher, unregister), `blender_farm_smoke.py` (baked scene without RainFX), `blender_upgrade_smoke.py` (a scene saved by 0.3.0), `blender_drips_smoke.py`,
  `blender_detail_smoke.py`, `blender_look_smoke.py`; the background-bake test now proves the reopened scene
  plays from the child's cache. New `tools/render_look.py` renders the street scene used for the README.

## 0.3.0-beta.1 (2026-11-16)

Everything since 0.1.0; the 0.2.0 public betas (up to `v-0.2.0-beta3`) were cut from this work.

- `docs/REFERENCES.md` keeps the scientific and Blender sources; working research notes are no longer published.
- Repository layout shared by the four OpenSimFX add-ons (CONTRIBUTING.md, Repository conventions): new
  `CONTRIBUTING.md` and `docs/DEVELOPMENT.md` (testing, build and release, moved out of `docs/SYSTEM_DESIGN.md`),
  README renders in `docs/img/` (new renders), project metadata in `pyproject.toml`, add-on icon in the README.
  The same nine docs as every add-on: measured results, unverified items and the 5.2.1 checklist moved to the new
  `docs/VALIDATION.md`; research sources and the reference-add-on analysis to the new `docs/REFERENCES.md`.
- Fix: `tools/render_preview.py` placed its camera from the emitter's evaluated geometry, which is empty before
  the simulation runs, and outside the rain volume; it now stands inside the volume at eye height (from the
  Volume setting) and looks across it. Its ground no longer gets an empty material slot.
- UI follows the shared OpenSimFX conventions (`docs/UI_STYLE.md`, identical in all four add-ons):
  the main panel holds the preset (with a wrapped description) and a large *Add Weather Emitter*;
  rain controls move to a *Rain* sub-panel; the bake controls formerly under *Simulation* /
  *Engines* are now *Cache and Bake* (progress bar, *Delete Sim Cache* separated at the bottom);
  *Derived Physics* is now *Readout*; *Run Diagnostics* has its own *Diagnostics* panel. Every
  panel uses Blender's label-left property layout. No properties or operators changed.

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
