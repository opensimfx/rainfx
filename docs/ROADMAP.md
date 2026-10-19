# Roadmap

Each phase ends with a Blender 5.2.1 acceptance pass (`TESTING.md` section 5). Scope is ordered by value to rendered output.

## Phase 0 - v0.1 (this repository)

Done and tested on Blender 5.0.1: precipitation simulation with raycast collision, 14 presets, dew, fog, sky and sun
scaling, lightning, compositor glow, particle-engine alternative, compatibility layer, tests, documentation.

Exit criteria: acceptance checklist passes on 5.2.1; extension validator passes; one rendered test frame per engine reviewed.

## Phase 1 - Production hardening (next)

| Item | Notes |
|---|---|
| Follow Object input | **Done (0.2.0)**: world-space volume follows the camera or a target via the Follow Object / Follow Offset controls — wrap is world-anchored, no parenting needed (`tests/blender_follow_smoke.py`) |
| Collider velocity transfer | **Done (0.2.0)**: the realised collider set rides inside the sim state as a snapshot; per-vertex velocity matched step-over-step with Geometry Proximity and sampled at the hit; Collider Push slider (`tests/blender_motion_smoke.py`) |
| Seeded-inside-collider cleanup | **Done (0.2.0)**: init +Z/-Z ray parity rejects start points inside enclosed colliders (`tests/blender_inside_smoke.py`); open-top shapes and respawned points stay untested |
| Stable bake workflow | **Done (0.2.0)**: dialog Bake with the scene frame range pre-filled, disk or *Packed cache* target, Delete clears both; playback over the baked range verified identical to live (`tests/blender_bake_smoke.py`) |
| Material polish | Tuned streak, splash, hail and snow shaders for EEVEE and Cycles; refraction-friendly drop variant for close-ups | **Done (0.2.0)** |
| Extension validation | **Done (0.2.0)**: manifest maintainer/website/copyright filled in (github.com/opensimfx/rainfx), permissions reviewed (user preset file read/write), zip passes `extension validate` |
| Determinism tests | **Done (0.2.0)**: twin emitters with the same seed are bit-identical every frame; scrub-back replay and forced re-sim match exactly; a changed Seed moves only the changed twin (`tests/blender_determinism_smoke.py`) |

## Phase 2 - Surfaces and atmosphere

| Item | Notes |
|---|---|
| Wetness | Per-collider wetness attribute from impact positions; Principled roughness / darkening node group; optional Dynamic Paint wet map — **Done (0.2.0)** (Dynamic Paint skipped: can't read GN instances; hidden impact-carrier approach instead) |
| Puddles and ripples | **Done (0.2.0)** — pool attribute in the wetness zone + ripple bump/noise shader with frame driver; verified via blender_wetness_smoke.py |
| Snow cover | **Done (0.2.0)** — per-vertex "rainfx_snow" accumulation + post-sim normal lift driven by landed flakes (split "RainFX Snow Impacts" carrier; Snow Rate / Snow Depth); rain worlds stay snow-inert |
| Distant rain | **Done (0.2.0)** — static GN "RainFX Distant" far layer: translucent streaks scatter into a 3x reach / 2x height shelf and wrap at the preset's own fall speed and wind; no sim zone, no cache, pure frame function (replay/bake safe); separates the emitter so impact scans stay untouched |
| Lens interaction | **Done (0.2.0)** — compositor droplet-displacement stage on the RainFX post chain (two drifting, procedurally generated signed drop maps via frame drivers; foreign compositing trees are never touched) |
| Sound-ready events | **Done (0.2.0)** — "Export Impact Events" button replays the frame range and writes impact-event JSON (frame, position, intensity = drop diameter in mm, type impact/snow) for audio sync |

## Phase 3 - Hero physics

| Item | Notes |
|---|---|
| Rigid Body hail | Convert the largest stones to rigid bodies (Rigid Body World, convex hull or sphere shapes) for tumbling and stacking |
| Mantaflow splashes | Feed Flow objects at impact positions for fluid-grade crowns and puddle interaction in close-ups |
| Cloth and hair response | Evaluate the 5.2 experimental Geometry Nodes physics (hair and cloth with Collider effector) as a target for rain-loaded cloth, once it stabilises |
| Particle-particle effects | Coalescence and breakup statistics |

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Blender API churn (5.x) | Breakage on minor releases | All version branches in `compat.py`; CI job running the Blender scripts on each supported release |
| Collider triangle count | Slow raycast | Proxy mesh guidance; optional decimated collider cache |
| Visual realism needs per-shot tuning | Disappointing out-of-the-box renders | Presets are data; tuning guide; phase 1 material polish |
| Sim-zone semantics change | Different results between versions | Version string on the node group; rebuild on mismatch; regression tests on recorded statistics |
| Experimental 5.2 physics replaces parts of this | Duplicate effort | Keep the engine boundary thin (`scene/` vs `gn/`) |
