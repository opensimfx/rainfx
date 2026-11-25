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
| `gn/wetness.py` | Builds the `RainFX Wetness` helper group: per-collider accumulation of `rainfx_wet` and the `rainfx_pool` standing water mask per face corner, per-vertex `rainfx_snow` + post-sim normal lift |
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
2. Positions: uniform random in the box (X, Y centred, Z from 0 to height), then offset by the volume origin
   (Follow Object's world location + Follow Offset; the emitter itself when no object is set). A ray from each
   point back along its fall direction (-normalize(initial velocity): up and into the wind) that meets a
   collider deletes the point (1.0): no drop could have reached it, under a roof or inside a closed shape.
   Respawned points start at the top of the box and are not re-checked.
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

splash decision per landing rain drop: K = We Oh^-2/5 from its diameter and |v - cvel|
  n = floor(Splash Amount x clamp(ln(K / Splash Threshold) / ln(K_ref / 2100), 0, 2) + random)
splash spawn: duplicate hit rain particles (n copies each; none when K <= threshold)
  direction = normalize(0.6..1.4 n + tangential random), speed = Splash Speed x (0.4..1.6) x clamp((K / K_ref)^1/4, 0.5, 2) + cvel
  life = random(min, max), diameter = parent x Splash Size x (0.4..1.2)
crown spawn (Crowns on, K above threshold, hit normal z > 0.5): one static point per landing,
  crown = 1, velocity 0, life 0.1 s, keeps parent diameter, hit normal (nrm) and impact speed (vimp)

splash update: droplets v += g dt ; pos += v dt ; crowns stay put ; age += dt ; delete where age > life
```

### 4.4 Output

Primaries become instances: cylinder (6 vertices) aligned to velocity and stretched to `|v| x Shutter`, or an ico
sphere when `Shutter = 0`. Width is `D x min(max(d / 2 m, 1), Visual Scale)`, d = distance to the active
camera (Active Camera node; true size near the lens, 1.0). Splash droplets are ico spheres. Crowns are open 16-sided flared cones (base half the rim) aligned to the hit
normal, rim radius `0.5 sqrt(D V age) x sqrt(effective Visual Scale)` and height 0.57 x radius, with the splash material. `Output Mode = 1` outputs the raw
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
simulation zone that accumulates a `rainfx_wet` float on the face-corner domain: each step it finds how
close the corner's vertex is to any current impact vertex, adds `Strength x exp(-(distance / Wet Radius)^2)`
(Gaussian, 1.0), and decays the value by `Dry Rate x dt` (saturating at 1). Before the zone, an exposure
per corner is computed once (1.0): five rays from 2 cm off the face toward where the rain comes from (Sky
Direction blended toward Rain Direction in quarter steps, both set per object in its own space) against the hidden
`RainFX Shelter` mesh, a world-space copy of every collider rebuilt by `wetness.build_shelter()` on each
refresh and read RELATIVE. Exposed corners take the *Ambient Wet* level (and flat ones *Ambient Pool*); with
*Wet Up Time* > 0 a `rainfx_amb` state rises toward it, else it starts there. Wet and pool never drop below
the ambient level while the rain lasts. Snow presets set *Ambient Snow*: the corner exposure averaged onto
each vertex and gated by its normal sets a `rainfx_snow` floor the same way. `scene/watch.py` rebuilds the
shelter and the drip points after collider edits, and *Bake* bakes the helpers with the emitter. Reading the collider collection directly would make every collider
depend on every other one, itself included (a dependency cycle that hung evaluation). Corners rather than faces (0.4): coplanar faces
meeting at a vertex get the same value there, so the shader interpolates smoothly across them instead of
showing one flat value per face, while faces meeting at a hard edge keep separate values. The same step
accumulates a `rainfx_pool` standing-water mask on the corners: the increment is footprinted on up-facing
faces (`max(0, face normal z)`, the face normal evaluated per corner so puddles never bleed down walls) and
weighted by a height mask over the object's own bounding box (low spots pool up to 65% stronger; the mask
is a weight, not a gate, so raised tops still pool at the 35% floor). Pools fill instantly inside the
footprint and dry 4x slower (`Dry Rate x dt x 0.25`), reading as lingering standing water.
`materials.wire_wetness()` links both attributes into the surface (Lagarde's wet-surface model, see
PHYSICS.md *Look*): a world-space noise height map shapes them, so standing water fills the low spots
first (puddle = (1.2 pool - h) / 0.15, organic edges at any mesh resolution) and high spots dry first;
albedo darkens by porosity, roughness drops with the water film and to a near mirror in puddles, and
puddles get the "RainFX Ripples" ring bump and flatten the material's normal map. The mesh still sets
the spatial detail of where rain landed: `wetness.coarse_colliders` lists colliders with edges over
4 x Wet Radius, shown as a hint in the Collisions panel.

The impacts are not read from the emitter directly (D11): a hidden `RainFX Impacts` mesh object is
refreshed every frame by a `frame_change_post` handler that copies every emitter's evaluated impact
vertices in world space (numpy, `foreach_get`); the helpers read that carrier via ObjectInfo RELATIVE, so
moved, rotated or scaled colliders compare hits in their own space. The handler is `@persistent` and
registered with the add-on (1.0), so it survives file loads and runs in command-line renders; it returns
at once when no carrier exists. Wet *state* lives only in each helper's sim zone, so baking is unaffected —
the handler is just the input feed (a render farm needs RainFX installed for it).

### 4.6b Drips (`RainFX Drips` layer)

`scene/drips.py` finds drip points on the colliders when the layer is refreshed: near-horizontal edges where
an up-facing face (normal z > 0.7) meets a side face (normal z < 0.3) or the mesh ends, open to the sky above
that face, with at least 0.3 m of air below (BVH ray casts over a world-space copy of the colliders). One point
per 0.3 m / *Drip Density*, capped at 5000. The points go into the hidden `RainFX Drips` mesh with `fall`,
`period` and `phase` attributes. The `RainFX Drips` node group (`gn/drips.py`) is a pure function of Scene
Time like the distant layer: per point k = t / period + phase, six duplicates stand for the drops released
0-5 periods ago, each falls from rest to terminal speed (`physics.drip_fall`) and is deleted past its fall
height; a bead hangs at the point and grows from 35 % to full size until release. No cache.

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
  "different thread" is a second headless Blender process (`rainfx/scene/baker.py`). The parent saves a copy of
  the scene as it is now next to the .blend (1.0; the saved file could be stale), sets its own modifier to the
  same disk target and range so it reads what the child writes, and the child bakes the named emitter and
  modifier (1.0; was the first emitter in the file). Paths and names reach the child script as `repr()`
  literals (Windows backslashes). Progress is the number of per-frame cache
  files (`<bake_dir>/<record-id>/blobs/*.blob`) against the expected count — polled by a 0.5 s `bpy.app.timers`
  tick that also sets a WAIT cursor. Packed bakes keep the legacy in-process path bit-for-bit.
- Random streams are seeded from `Seed` and the scene frame, so the same file gives the same weather (`blender_determinism_smoke.py`).
- Changing Count, box size or most inputs requires a re-bake or playing again from the start frame, as with any simulation zone.

## 8. Error handling and robustness

- `compat.set_modifier_input` returns `False` instead of raising when a socket does not exist, so presets with extra keys never break an older node group.
- Node groups carry `rainfx_version`; `ensure_group()` rebuilds a stale group rather than editing it
  (`dsl.ensure_versioned`): every modifier using the old group is detached (which clears its simulation state;
  `ID.user_remap` kept it and crashed Blender), the group rebuilt and the modifiers re-attached, so a second
  emitter or the other colliders keep working. Materials (`rainfx_mat_version`, `rainfx_wet`), the fog and
  spray (`rainfx_fog_version`) and the lens stage (no blur node = 0.3) are upgraded in place the same way.
- `unregister()` stops a running background bake, its progress timer and the frame handler.
- A broken user preset file is skipped with a console message.
- The compositor is untouched when the scene already has nodes; lighting changes store the original values and can be reverted.
- Dew has a hard bead cap (`Max Beads`) derived from collider area. Without it a 120 m ground plane produced 5 million beads in testing.

## 9. Known limitations (1.0)

1. Collider velocities are translation-only: matched step-over-step by nearest point, so rotating or deforming colliders get approximate velocities, and changing the collider set mid-simulation costs one inaccurate step.
2. Only init positions get the shelter test; a recycled (respawned) drop starts at the top of the box and is never re-checked, so a collider reaching above the volume top can hold drops inside it for one fall.
3. One impact per particle per step; with default 24 fps and speeds under 15 m/s this is not visible.
4. Puddles are a shading effect (colour, roughness, flood-level mask, ring-ripple bump), not water geometry: no refraction depth and no rings at the simulated impact points.
5. Snow lift is per vertex on the receiving face's own normals, so low-res meshes lift as plates and seams can open where normals differ; there is no melt or settling physics.
6. The distant layer is a wrapping open-world filler: it never collides, splashes or gates on camera distance, and its shelf edge is visible if a wide shot puts the camera outside it (turn the layer off or enlarge the Volume).
7. The lens stage is screen-space: droplet drift is calibrated by feel (pixels per frame, decoupled from wind), and a droplet warps whatever the camera sees — it has no notion of what is behind the glass, so very bright highlights can smear unrealistically. The stage also assumes an unclipped camera framing.
8. Impact-event exports sample the impact sink with a per-frame cap of 256 (even stride), so dense storms are a statistical sample, not a lossless record; 'intensity' is only the landing drop's diameter (no per-event velocity), and positions are emitter-local — consumers multiply by the emitter's `matrix_world` when the layer is follow-mounted. The export replays the whole frame range sequentially, so cost grows linearly with range and collision complexity.
9. Exposure (ambient wetness and snow cover) and drip points are computed from the colliders when they are refreshed, not every frame. `scene/watch.py` refreshes them by itself half a second after a collider is moved, edited, added or removed (not during playback, rendering or Edit Mode). Keyframed colliders keep the exposure of the last refresh, and a simulation reads its exposure at its start frame only.
10. Unbaked wetness needs RainFX in the Blender that plays or renders the scene (a frame handler feeds the helpers). *Bake* bakes the helpers with the rain, so baked scenes render anywhere (`blender_farm_smoke.py`); drips, materials and drivers never need the add-on.
11. Drips fall from edges without a flow model: no water running down walls or along gutters, and drip rate follows the rain rate, not the area that drains to the edge.
12. Hail leaves wet ground, not a layer of stones (stones recycle after their bounces); snow cover is a per-vertex amount and lift, not drifts.

---

## Testing

Moved to [DEVELOPMENT.md](DEVELOPMENT.md): test layers, how to run them, recorded results, the
acceptance checklist, and how to add tests.


---

## Project Structure


```text
rainfx_project/
├── README.md
├── LICENSE                         GPL-3.0-or-later
├── CHANGELOG.md
├── pyproject.toml                  project metadata, pytest configuration
├── .github/logo.png                add-on icon (README heading)
├── docs/
│   ├── SYSTEM_DESIGN.md            architecture, algorithm, decisions
│   ├── PHYSICS.md                  models and sources
│   ├── PRESETS.md                  GENERATED table + schema
│   ├── USER_GUIDE.md
│   ├── DEVELOPMENT.md              testing, build and release
│   ├── ROADMAP.md
│   ├── UI_STYLE.md                 shared OpenSimFX panel conventions
│   └── img/                        README renders
├── rainfx/                         the extension (this folder is what gets zipped)
│   ├── blender_manifest.toml       extension metadata (schema 1.0.0)
│   ├── __init__.py                 register() / unregister(); no top-level bpy import
│   ├── compat.py                   ALL version-dependent API access
│   ├── core/                       pure Python, never imports bpy
│   │   ├── physics.py
│   │   └── presets.py
│   ├── gn/                         node group builders
│   │   ├── dsl.py
│   │   ├── precip.py               rain, hail, snow simulation group
│   │   ├── dew.py
│   │   └── materials.py
│   ├── scene/                      datablock logic, no UI
│   │   ├── emitter.py              emitters, colliders, preset application
│   │   ├── atmosphere.py
│   │   ├── lighting.py
│   │   ├── compositor.py
│   │   └── legacy_particles.py
│   ├── ui/
│   │   ├── props.py
│   │   ├── ops.py
│   │   └── panels.py               also AddonPreferences
│   └── data/
│       └── presets.json            GENERATED by tools/gen_presets.py
├── tests/
│   ├── test_physics.py             plain pytest (no Blender)
│   ├── test_presets.py             plain pytest (no Blender)
│   ├── blender_smoke.py            simulation behaviour (needs bpy)
│   ├── blender_scene_smoke.py      scene helpers (needs bpy)
│   └── blender_ui_smoke.py         registration and operators (needs bpy)
└── tools/
    ├── gen_presets.py              preset table -> data/presets.json
    ├── gen_preset_docs.py          presets + physics -> docs/PRESETS.md
    └── build_extension.py          rainfx/ -> dist/rainfx-<version>.zip
```

### Dependency rules

| Layer | May import | Must not import |
|---|---|---|
| `core` | stdlib | `bpy`, anything above |
| `compat` | `bpy` | `core`, `scene`, `ui` |
| `gn` | `bpy`, `compat`, `core` | `scene`, `ui` |
| `scene` | `bpy`, `gn`, `core`, `compat` | `ui` |
| `ui` | everything | none |

`rainfx/__init__.py` must stay free of top-level `bpy` imports so `tests/test_physics.py` and the generator tools run in a plain interpreter. This was broken once during development (the package init imported `compat`) and is now guarded by the plain-pytest run.

### Naming conventions

- Operators: `rainfx.<verb>` ids, classes `RAINFX_OT_*`; panels `RAINFX_PT_*`.
- Node groups: `RainFX <Name>`; custom property `rainfx_version` on the group.
- Datablocks created by the add-on start with `RainFX ` so users can find and purge them.
- Emitter objects carry the custom property `rainfx_emitter = True` plus `rainfx_preset` and `rainfx_derived`.
- Collections: `RainFX` (everything created) and `RainFX Colliders` (what rain hits).

### Node group interface (precipitation)

Panels and sockets in `gn/precip.py`. The Python side addresses sockets by name through `compat.set_modifier_input`, so
renaming a socket requires updating `emitter.apply_preset` and `docs/PRESETS.md`.

| Panel | Sockets |
|---|---|
| Setup | Colliders, Mode, Seed, Box Size, Count, Viewport Density, Output Mode |
| Population | D Min, D Max, Lambda, Speed Scale, Snow Speed |
| Air | Wind, Gust Strength, Gust Scale, Gust Speed, Inertia |
| Impact | Restitution, Max Bounces, Collider Push, Splash Amount, Splash Threshold, Crowns, Splash Speed, Splash Life Min, Splash Life Max, Splash Size, Gravity |
| Look | Shutter, Visual Scale, Drop Material, Splash Material |

### Build and release

See [DEVELOPMENT.md](DEVELOPMENT.md#build-and-release).
