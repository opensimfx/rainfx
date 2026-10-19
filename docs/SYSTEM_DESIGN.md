# System Design

Status: implemented for v0.1 unless a section says "planned". Every behavioural claim below is covered by a test in
`tests/` or marked as unverified.

## 1. Goals and non-goals

Goals

1. Physically grounded precipitation: drop size, fall speed, wind coupling and impact follow published relations.
2. Real collisions with arbitrary scene meshes, including thin surfaces, without per-object setup beyond membership in a collection.
3. One-click presets for the weather types in `PRESETS.md`, fully editable afterwards.
4. Uses Blender's built-in systems (Geometry Nodes simulation, Collision modifier, force fields, compositor, volumes) instead of private solvers.
5. Renders in EEVEE and Cycles; deterministic and bakeable.
6. Survives Blender API churn (4.2 to 5.2 changed the modifier input API, compositor, EEVEE ids, actions).

Non-goals (v0.1)

- Particle-particle collisions, drop coalescence, drag-based drop deformation.
- Real puddle geometry and expanding-ring ripples (shipped 0.2.0 as shading cues: pool mask, dark gloss + ripple bump; see ROADMAP.md phase 2 for the physical successors).
- Volumetric rain curtains for distant rain (phase 2).
- Fluid-grade splashes (Mantaflow hero mode, phase 3).

## 2. Architecture

```mermaid
flowchart TB
  subgraph UI[ui/ - Blender types only]
    P[props.py PropertyGroup] --> O[ops.py operators]
    O --> PN[panels.py]
  end
  subgraph SC[scene/ - bpy datablock logic, no UI]
    EM[emitter.py] --- AT[atmosphere.py]
    EM --- LI[lighting.py]
    EM --- CO[compositor.py]
    EM --- LG[legacy_particles.py]
  end
  subgraph GN[gn/ - node group builders]
    PR[precip.py] --- DW[dew.py]
    DS[dsl.py] --> PR
    DS --> DW
    MT[materials.py]
  end
  subgraph CORE[core/ - pure Python]
    PH[physics.py]
    PS[presets.py] --> PH
  end
  CP[compat.py - version differences]
  UI --> SC
  SC --> GN
  SC --> CORE
  SC --> CP
  GN --> CP
  PS -.->|reads| JS[(data/presets.json + user *.json)]
```

Dependency rule: arrows only point downward. `core/` never imports `bpy`; this is what makes the physics and preset
logic testable with plain `pytest` (`tests/test_physics.py`, 11 tests) and keeps `rainfx/__init__.py` import-safe outside Blender.

### Component responsibilities

| Component | Responsibility |
|---|---|
| `core/physics.py` | Terminal velocity (rain, hail, snow), Marshall-Palmer slope and density, truncated-exponential sampler, relaxation time, wind vector, streak length |
| `core/presets.py` | `Preset` dataclass, validation, `derive()` (preset + volume + quality -> simulation inputs), JSON loading with user overrides |
| `gn/dsl.py` | Builder over `bpy` node trees. Looks sockets up by name among enabled sockets, never by identifier |
| `gn/precip.py` | Builds the `RainFX Precipitation` group: init, simulation zone, rendering instances |
| `gn/dew.py` | Builds the `RainFX Dew` group: beads on up-facing collider faces with a hard count cap |
| `gn/materials.py` | Water, splash, ice, snow, dew materials, created on demand; `wire_wetness()` links the wet look into a collider's material |
| `gn/wetness.py` | Builds the `RainFX Wetness` helper group: per-collider accumulation of `rainfx_wet` per face, `rainfx_pool` standing water mask, per-vertex `rainfx_snow` + post-sim normal lift |
| `gn/distant.py` | Builds the static `RainFX Distant` far layer group: seeded scatter, per-frame deterministic wrap drift, align-to-fall streak instancing (see 4.8) |
| `scene/distant.py` | Creates/updates/removes the background layer object, pushes preset-derived wind/fall speed, parents it to the Follow Object like the fog |
| `scene/wetness.py` | Attaches/removes the helper per collider and refreshes the hidden `RainFX Impacts` / `RainFX Snow Impacts` carriers each frame (see 4.6/4.7) |
| `scene/emitter.py` | Creates emitters, applies presets to modifiers, stores the applied wind on `rainfx_wind` for far-layer sync; `create_demo` seeds the demo ground plane + Suzanne colliders on the add operator (idempotent by name) |
| `scene/atmosphere.py` | Fog volume, reversible sky and sun scaling |
| `scene/lighting.py` | Seeded lightning schedule as constant-interpolated keyframes |
| `scene/compositor.py` | Glare chain if the scene has no compositor tree (never touches foreign trees); Lens Drops stage: two procedurally generated signed droplet maps drifted through a Displacement stage by frame drivers (see 4.9) |
| `scene/legacy_particles.py` | Alternative engine on Blender's emitter particle system |
| `scene/events.py` | Sound-ready export: replays the frame range, reads the impact sink ('imp' verts) each frame, writes JSON event log (see 4.10) |
| `compat.py` | All version-dependent API access |
| `ui/*` | Properties, operators, panels, preferences. No simulation logic |

## 3. Data flow

```mermaid
sequenceDiagram
  participant U as User
  participant UI as ui/ops
  participant E as scene/emitter
  participant C as core/presets
  participant M as GN modifier
  U->>UI: pick preset, click Add Emitter
  UI->>E: create_emitter(preset)
  E->>C: derive(preset, box, quality)
  C-->>E: count, lambda, wind vector, tau, ...
  E->>M: compat.set_modifier_input(name, value) for each socket
  U->>M: play timeline (frame N)
  M->>M: simulation zone step (dt = 1/fps)
  M-->>U: instances (streaks / spheres) or vertices
```

The preset to inputs mapping lives in exactly one function (`emitter.apply_preset`), so UI, tests and scripts cannot drift.

## 4. The simulation (Geometry Nodes)

### 4.1 State

All state is stored as named attributes on the point cloud inside the simulation zone. Anonymous attributes would be
dropped at the zone boundary (documented behaviour of simulation zones).

| Attribute | Type | Meaning |
|---|---|---|
| `position` | vector | metres; stored as world-space numbers inside the sim (base of the volume = Follow Object location + Follow Offset), converted back to emitter-local just before output |
| `velocity` | vector | m/s |
| `diameter` | float | mm (splash droplets store their own, smaller value) |
| `vt` | float | terminal fall speed, m/s |
| `tau` | float | relaxation time, s |
| `kind` | float | 0 primary particle, 1 splash droplet, 2 collider snapshot (rides in the state as a mesh component) |
| `bounces` | float | impacts survived (hail, pellets) |
| `age`, `life` | float | splash droplet age and lifetime, s |

### 4.2 Initialisation (frame 1, evaluated once)

1. Count = `Count x (Viewport Density if in viewport else 1)`.
2. Positions: uniform random in the box (X, Y centred, Z from 0 to height), then offset by the volume origin; a
   +Z/-Z ray-parity test against the colliders deletes any start point inside an enclosed volume (respawned
   points are not re-checked)
   (Follow Object's world location + Follow Offset; the emitter itself when no object is set).
3. Diameter: inverse-CDF sample of an exponential truncated to [D Min, D Max] with slope Lambda.
   `D = Dmin - ln(1 - u (1 - exp(-L (Dmax - Dmin)))) / L`. For rain, Lambda = 4.1 R^-0.21 (Marshall-Palmer).
4. Terminal speed by mode: rain (Stokes bridge below 0.5 mm, Atlas fit above), hail `0.85 x 9 (D/10)^0.8`, snow `v0 (0.85 + 0.03 D)`.
5. `tau = max(vt / g, 0.02) x Inertia`. Initial velocity = wind + (0, 0, -vt).

### 4.3 Per step

Collider velocities: the realised collider set itself rides inside the simulation state as a mesh
component (marked `kind = 2`). Each step it is matched against the previous copy with *Geometry
Proximity* (nearest point, independent of vertex order) and stores
`rainfx_velocity = (position - nearest previous) / dt` on itself — static geometry keeps exactly 0.
A raycast with a `FLOAT_VECTOR` attribute input then samples `rainfx_velocity` at the hit; that value
is `cvel`, scaled by the *Collider Push* socket (default 1). Bake-safe: no Python handlers, the
mechanism lives entirely inside the zone.

```text
split by kind -> primaries P0, splash S0

primaries (fields evaluated on P0, then frozen):
  gust     = (noise(pos / L + drift * t) - 0.5) * 2 * (1, 1, 0.6) * strength
  target   = wind + gust + (0, 0, -vt)
  v_new    = target + (v - target) * exp(-dt / tau)            # exact for any dt
  ray      = Raycast(collider snapshot, from pos, dir v_new, length |v_new| dt + radius)
  if hit:
      can_bounce = restitution > 0 and bounces < max_bounces
      bounce  -> pos = hit + n * 3 mm ; v = 0.85 v_rel_tangent - restitution v_rel_normal + cvel  (collider frame)
      else    -> recycle (+ splash spawn for rain)
  below floor without hit -> recycle
  recycle  -> new random position in the top 8 % of the box, v = wind + (0, 0, -vt)
  pos wraps horizontally inside the box (world-anchored around the Follow Object's position)

capture all results (Capture Attribute) -> Set Position / Store velocity / bounces
world->local: the final Set Position subtracts the emitter's world location, so the
output is emitter-local again (emitter rotation/scale must stay identity).

splash spawn: duplicate hit rain particles (Splash Amount copies)
  direction = normalize(0.6..1.4 n + tangential random), speed = Splash Speed x (0.4..1.6) x size factor + cvel
  life = random(min, max), diameter = parent x Splash Size x (0.4..1.2)

splash update: v += g dt ; pos += v dt ; age += dt ; delete where age > life
```

### 4.4 Output

Primaries become instances: cylinder (6 vertices) aligned to velocity and stretched to `|v| x Shutter`, or an ico
sphere when `Shutter = 0`. Width is `D x Visual Scale`. Splash droplets are ico spheres. `Output Mode = 1` outputs the raw
state as mesh vertices instead (used by the tests and useful for custom instancing). Primary drops that land this frame
also form an invisible vertex mesh inside the output (named `imp` flag = 1, zero area, renders nothing).

### 4.5 Why these choices (decision records)

| # | Decision | Alternatives rejected | Reason |
|---|---|---|---|
| D1 | Geometry Nodes simulation zone as main engine | Legacy particle system | Scales to 10^5 particles with BVH raycasts, bakeable, scriptable, drop-size distribution per particle. The legacy system is kept as a second engine |
| D2 | Raycast along each step | Collision modifier, proximity or distance checks | Exact for thin geometry at any speed (no tunnelling). Proximity checks miss fast particles |
| D3 | Recycle instead of spawn and delete | Emission rate with lifetime | Constant memory and cost, no emission bookkeeping, steady-state from frame 1 |
| D4 | Exponential velocity integrator | Explicit drag force | Unconditionally stable for any frame rate or sub-step; reproduces terminal velocity exactly |
| D5 | Capture Attribute before mutation | Set Position then re-read fields | Fields are lazy: after `Set Position` a field using `Position` returns the *new* position. Found while building; the freeze is mandatory |
| D6 | Wind as input vector plus noise | Blender Wind force field | The force field acts as a drag coupling toward the wind vector and removes vertical fall speed for horizontal wind (observed in `legacy_particles` testing). Not usable as drop-in wind |
| D7 | Presets as JSON, derived values computed in Python | Hard-coded node values | One source of truth for UI, docs (table is generated) and tests; users can add presets |
| D8 | `compat.py` is the only place that branches on version | Version checks scattered | The modifier input API changed in 5.2 and the compositor in 5.0 |
| D9 | Sockets looked up by name among enabled sockets | Identifier or index lookup | Compare and Random Value identifiers are type-suffixed and changed in 5.2 |
| D10 | Visual scale and streaks over physical drop size | True 0.5-5 mm drops | A 2 mm drop is sub-pixel at normal camera distances; streaks of length speed x shutter reproduce what a real camera records |
| D11 | Wetness via a hidden impact-carrier object | Helpers reading the emitter directly (pure GN), Dynamic Paint | ObjectInfo back to the emitter closes a dependency cycle the depsgraph breaks by serving empty geometry once two or more helpers read it (verified headless). DP cannot read GN instance geometry. The carrier costs one tiny frame_change handler; wet state stays in bake-safe helper sim zones |

### 4.6 Wetness (`RainFX Wetness` helper)

Each wet-enabled collider gets a `RainFX Wetness` node modifier at the top of its stack. It runs its own
simulation zone that accumulates a per-face `rainfx_wet` float: each step it finds how close the face
centre is to any current impact vertex, adds `Strength x exp(-distance / Wet Radius)`, and decays the
value by `Dry Rate x dt` (saturating at 1). The same step accumulates a per-face `rainfx_pool`
standing-water mask: the increment is footprinted on up-facing faces (`max(0, normal_z)`) and weighted
by a height mask over the object's own bounding box (low spots pool up to 65% stronger; the mask is a
weight, not a gate, so raised tops still pool at the 35% floor). Pools fill instantly inside the
footprint and dry 4x slower (`Dry Rate x dt x 0.25`), reading as lingering standing water.
`materials.wire_wetness()` links both attributes into the surface: Base Color pulled toward a dark
pool colour and roughness scaled by `1 - 0.85 x max(wet, pool)` — glossier, darker where wet (5.2's
Principled has no Wet Amount socket, so the cue is colour + roughness). Where `rainfx_pool` rises, the
material also gets a procedural ripple bump: noise texture over Object coordinates drifted along X by
a frame-driven time value (5.2's noise W socket is disabled), bump strength proportional to the pool
mask.

The impacts are not read from the emitter directly (D11): a hidden `RainFX Impacts` mesh object is
refreshed every frame by a `frame_change_post` handler that copies the emitter's evaluated impact
vertices; the helpers read that carrier via ObjectInfo. Wet *state* lives only in each helper's sim
zone, so baking is unaffected — the handler is just the input feed.

### 4.7 Snow cover (same helper, second carrier)

Snow lands come from a second hidden carrier: the emitter stores a named `snow` flag on landings
(pure arithmetic `1 - min(|mode - 2|, 1)` — Compare nodes evaluated stale inside this field
context in 5.2.1, verified by probe; group version forces a rebuild), and the handler routes
landings with the flag into `RainFX Snow Impacts` while plain rain hits keep going to
`RainFX Impacts`. The helper accumulates snow per vertex: per step it footprints flake proximity
by the same radius decay, gates on the *up-facing* factor `max(0, vertex normal_z)` (cube corners
keep a 0.577 share of the vertical normal) and adds `Snow Rate x dt` inside the footprint to
`saturated 1`. After the sim zone, a fresh Set Position lifts vertices along their normals by
`rainfx_snow x Snow Depth` — recomputed from the accumulated attribute every evaluation so the
sim state itself never receives displacement (no feedback, bake-safe).
`materials.wire_wetness()` stacks the snow look after the water cues: Base Color mixes toward
snow white by `rainfx_snow`, and roughness lifts by `+0.5 x snow` (clamped at 1) over the
wet-darkened value. Snow Rate and Snow Depth stay untouched by refresh (user tunables persist).
Note flake flux: light snow falls ~1 m/s, so a tall/sparse box takes a while before enough flakes
cross a raised face — the group version registry is precip 8 / wetness 3.

### 4.8 Distant rain (`RainFX Distant` far layer)

The near field is deliberately sparse (density ratio ~1%), so the far view needs filling. A
standalone `RainFX Distant` object carries a second, deliberately independent GN group — never
touching the emitter's eval mesh that the impact handler scans (`ObjectInfo`-back emitter still
owns its own object). The group is static: no simulation zone, no cache, no point state. The
`GeometryNodePoints` node's own position field freezes one seeded random spot per streak; the
motion is `(wind.xy, -vt) x scene seconds` wrapped through the box by a per-axis FRACTION of the
box span (FRACTION maps negatives upward, XY recentred afterwards), so every frame is a pure
function of frame time — replay, bake and live-edit safe by construction. Streaks align their Z
to the fall vector and lengthen with `vt x 0.12 x Streak Scale` like a time exposure (slow snow
presets read as short dots automatically). Instances are realized into the output so the
evaluated geometry equals what renders.

The scene side (`scene/distant.py`) mirrors the fog lifecycle: a display-bounds box object in
the RainFX collection, scaled to a 3x reach / max(2x height, 20 m) shelf, positioned at the
emitter and parented to the Follow Object exactly like `atmosphere.create_fog`. Inputs come
from the emitter's stored derived values — `wind` now persists as `obj["rainfx_wind"]` (the
mult-scaled wind tuple, previously lost to the scalar-only `rainfx_derived` store) and
`vt_mean_ms` from `rainfx_derived` — so far motion matches the simulation and re-syncs on every
Apply. `Count = 0.5 x Distant Density x far volume`. The `distant` material kind is a flat
translucent BLENDED streak with no transmission, keeping EEVEE cheap at thousands of instances.
Group version registry: precip 8 / wetness 3 / distant 1.

### 4.9 Lens interaction (compositor droplets)

The far layer fills the world; this item fills the glass. When Lens Drops is on, the RainFX
post tree (built by `create_post` if the scene has none — foreign trees are still never
touched) gets a Displacement stage inserted between Render Layers and Glare: two 128px
`float_buffer` RGBA maps generated at runtime carry droplets — mostly round beads, a quarter
stretched into drip streaks — encoded as signed displacement (`R` = dx, `G` = dy, amplitude
`4 x Lens Strength`, smooth `alpha` falloff) in an AlphaOver stack. Two Transform nodes drift
the maps downward (`frame x -0.35` and `frame x -0.85` frame drivers, `REPEAT` extension) so
streaks keep running down the glass in a non-repeating mix. Every inserted node is marked
`['rainfx_lens']`, so `remove_lens` can strip the stage and relink the bare chain; strengths
re-bake the maps in place (only when they change by more than 0.02) — drivers move pixels,
no per-frame Python.

Implementation guards learned the hard way in 5.2.1: generated images MUST be
`float_buffer=True` (byte images saturate the signed values >1 to 1.0 and clamp negatives to
0, which renders the stage as an exact no-op for many seeds), map size stays at 128px because
256px+ generated images sample black in the compositor, and `Image.update()` must never be
called on a generated buffer (it resets it). Transform units are pixels per frame; the drift
rates are feel-calibrated, not derived from wind (the stage is screen-space, deliberately
decoupled from world physics). Strength is capped at 3.0 so the stage reads as refraction,
not a broken image.

(The GN group-version registry does not change: precip 8 / wetness 3 / distant 1 — no
Geometry Nodes in this stage.)

### 4.10 Sound-ready impact events

`scene/events.py::export_events` turns the sim into a replayed event log for audio
middleware. It reuses the impact sink that already rides the emitter output — every landed
drop each frame exists as a real vertex flagged `imp > 0.5` in the emitter's evaluated mesh
(the same stream the wetness handler reads) — so there is no new node group and no cache:
for each frame in the range, the depsgraph is stepped, the sink verts are read
(`imp` → presence, `snow` → 'snow' vs 'impact' type, `diameter` → intensity in mm; up to
256 per frame via even-stride sampling) and the frame's events joined below. Positions are
emitter-local (consumers multiply by the emitter's `matrix_world` when the layer is
follow-mounted). The operator `rainfx.export_events` (Collision panel button, *Export
Impact Events*) applies this to the active emitter and writes
`{"version": 1, "fps", "frame_start", "frame_end", "preset", "vt_mean_ms", "sample_stride",
"events": [...]}` — default path `<user presets>/rainfx_impact_events.json`, with a *File
Path* property for a custom target. Headless emitters reset their spawn points at the
viewport residence multiplier, so the exporter pushes `Viewport Density` to 1.0 for the
walk and restores the user's value afterwards; the stride is `ceil(hits / cap)` to
guarantee the cap. The replay is the deterministic per-frame sim stepping, so an export
matches bake playback and every rerun. Rain/snow landings stay separated so middleware can
map flake impacts to softer sound layers.

(Registry unchanged — no Geometry Nodes; the push/restore on `Viewport Density` is the
only socket traffic.)

## 5. Rain density: physical vs simulated

Marshall-Palmer gives about 3,000 drops per m3 at 10 mm/h, so a 16 x 16 x 10 m volume would hold roughly 8 million drops.
v0.1 simulates 0.3-1.3 % of that and compensates with streak length and `Visual Scale`. The Derived Physics panel shows the ratio.
A multi-layer approach (dense near field, screen-space or volumetric far field) is phase 2.

## 6. Performance

Measured in a 1-CPU sandbox with Blender 5.0.1 headless (instancing included, single sphere/cylinder instance per point):

| Particles | ms per frame |
|---|---|
| 19,200 | 33 |
| 76,800 | 116 |
| 122,880 | 189 |

Cost is close to linear in particle count (about 1.5 microseconds per particle-step on that machine, raycast included for a
two-object collider set). Expect much better numbers on multi-core hardware, but collider triangle count raises raycast cost
(BVH built each step from `Collection Info` + `Realize Instances`). Mitigations: keep colliders to proxy meshes, use
`Viewport Density` (default 0.3), bake before rendering.

## 7. Caching and determinism

- Simulation caches follow Blender's standard bake workflow; the RainFX panel exposes *Bake* (scene frame range,
  disk or packed target) and *Delete* (`rainfx.bake` / `bake_delete` wrap `simulation_nodes_cache_bake/delete`).
- Baked frames replay exactly when the bake starts at the scene start frame (verified: disk and packed, partial
  ranges covered-exactly); continuing past the baked end is not identity-stable in Blender 5.2.1, so re-bake when
  the render range grows.
- *Background bake* (0.2.0): bpy is main-thread-only and the stock bake op is one blocking call, so a true
  "different thread" is a second headless Blender process (`rainfx/scene/baker.py`) opened on the saved .blend.
  The parent pre-sets the bake metadata (range, `bake_target='DISK'`, `bake_directory`), which persists through
  the save, and the child re-applies it and runs the stock bake op. Progress is the number of per-frame cache
  files (`<bake_dir>/<record-id>/blobs/*.blob`) against the expected count — polled by a 0.5 s `bpy.app.timers`
  tick that also sets a WAIT cursor. Packed bakes keep the legacy in-process path bit-for-bit.
- Random streams are seeded from `Seed` and the scene frame, so the same file is expected to give the same weather (not covered by a test yet).
- Changing Count, box size or most inputs requires a re-bake or playing again from the start frame, as with any simulation zone.

## 8. Error handling and robustness

- `compat.set_modifier_input` returns `False` instead of raising when a socket does not exist, so presets with extra keys never break an older node group.
- Node groups carry `rainfx_version`; `ensure_group()` rebuilds a stale group rather than editing it.
- A broken user preset file is skipped with a console message.
- The compositor is untouched when the scene already has nodes; lighting changes store the original values and can be reverted.
- Dew has a hard bead cap (`Max Beads`) derived from collider area. Without it a 120 m ground plane produced 5 million beads in testing.

## 9. Known limitations (v0.2)

1. Collider velocities are translation-only: matched step-over-step by nearest point, so rotating or deforming colliders get approximate velocities, and changing the collider set mid-simulation costs one inaccurate step.
2. Only init positions get the inside-collider test; a recycled (respawned) drop can still start inside a collider for one follow-up scan of the box. Open-topped shapes (cups) are not detected by the ray parity.
3. One impact per particle per step; with default 24 fps and speeds under 15 m/s this is not visible.
4. Puddles are an amber cue (colour + roughness + ripple bump), not real water: no geometry, no refraction, no growing ring waves.
5. Snow lift is per vertex on the receiving face's own normals, so low-res meshes lift as plates and seams can open where normals differ; there is no melt or settling physics.
6. The distant layer is a wrapping open-world filler: it never collides, splashes or gates on camera distance, and its shelf edge is visible if a wide shot puts the camera outside it (turn the layer off or enlarge the Volume).
7. The lens stage is screen-space: droplet drift is calibrated by feel (pixels per frame, decoupled from wind), and a droplet warps whatever the camera sees — it has no notion of what is behind the glass, so very bright highlights can smear unrealistically. The stage also assumes an unclipped camera framing.
8. Impact-event exports sample the impact sink with a per-frame cap of 256 (even stride), so dense storms are a statistical sample, not a lossless record; 'intensity' is only the landing drop's diameter (no per-event velocity), and positions are emitter-local — consumers multiply by the emitter's `matrix_world` when the layer is follow-mounted. The export replays the whole frame range sequentially, so cost grows linearly with range and collision complexity.
9. Blender 5.2.1 runtime behaviour is unverified (see `TESTING.md`).
