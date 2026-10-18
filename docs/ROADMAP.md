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
| Seeded-inside-collider cleanup | Reject initial points inside colliders (ray parity test) to remove warm-up |
| Stable bake workflow | Bake panel with frame range, progress, delete, packed vs disk cache choice |
| Material polish | Tuned streak, splash, hail and snow shaders for EEVEE and Cycles; refraction-friendly drop variant for close-ups |
| Extension validation | **Done (0.2.0)**: manifest maintainer/website/copyright filled in (github.com/opensimfx/rainfx), permissions reviewed (user preset file read/write), zip passes `extension validate` |
| Determinism tests | Same seed gives identical frames across sessions; animated collider test |

## Phase 2 - Surfaces and atmosphere

| Item | Notes |
|---|---|
| Wetness | Per-collider wetness attribute from impact positions; Principled roughness / darkening node group; optional Dynamic Paint wet map |
| Puddles and ripples | Procedural ripple shader driven by impact density; height-based puddle mask |
| Snow cover | Accumulation displacement on up-facing faces driven by landed flake counts |
| Distant rain | Volumetric or screen-space far layer so the near-field simulation can stay sparse |
| Lens interaction | Drop-on-lens compositor/shader effect for camera shots |
| Sound-ready events | Export impact events (frame, position, intensity) for audio sync |

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
