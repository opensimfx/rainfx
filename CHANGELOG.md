# Changelog

## 0.2.0 (unreleased)

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

## 0.1.0

- Geometry Nodes precipitation simulation: rain, hail, snow with raycast collision, bounce, splash, wind and gusts.
- 14 presets, user preset JSON files.
- Dew bead scattering with density cap.
- Fog volume, reversible sky and sun dimming, seeded lightning keyframes, optional compositor glow.
- Alternative engine on Blender emitter particle system with Collision modifiers.
- Compatibility layer for Blender 5.0 and 5.2 API changes.
