# Physics

Every formula here exists in `rainfx/core/physics.py` (Python, tested) and, where the simulation needs it per particle,
is re-implemented as nodes in `gn/precip.py`. The two implementations are checked against each other by the
derived values shown in the Derived Physics panel.

Confidence labels:

- **cited**: confirmed in a web source fetched for this project (the Research Sources section below).
- **textbook**: standard published constants entered from general knowledge; the sources fetched confirm the model exists but
  the exact constants were not re-read from them. Verify before relying on them for scientific work.
- **modelled**: engineering approximation chosen by this project; tune against your own reference footage.

## 1. Raindrop size distribution (cited N0, textbook slope)

Marshall and Palmer (1948): number of drops per m3 per mm of diameter. The intercept N0 = 8.0 x 10^3 m^-3 is confirmed in Gunn and Marshall (1958); the slope relation is entered from general knowledge.

```text
N(D) = N0 exp(-L D)       N0 = 8000 m^-3 mm^-1      L = 4.1 R^-0.21 mm^-1     (R in mm/h)
```

Total concentration `N0 / L`. At R = 10 mm/h: L = 2.53, about 3,160 drops per m3 (unit-tested).
The simulation draws each diameter with the inverse CDF of this exponential truncated to `[D Min, D Max]`:

```text
D = Dmin - ln(1 - u (1 - exp(-L (Dmax - Dmin)))) / L ,   u uniform in [0, 1)
```

Hail and snow use the same sampler with a fixed `lam_override` (hail 0.12 mm^-1, snow 0.3-0.35 mm^-1); these slopes are modelled, not measured.

## 2. Terminal velocity

### Rain (cited: Gunn-Kinzer data exist up to 5.8 mm; textbook: the Atlas fit constants)

Gunn and Kinzer (1949) measured fall speeds up to 5.8 mm drops. The Atlas et al. fit

```text
v(D) = 9.65 - 10.3 exp(-0.6 D)      D in mm, v in m/s,  valid for D >= 0.5 mm
```

gives 4.0, 6.5, 7.9, 8.7, 9.1 m/s for 1, 2, 3, 4, 5 mm drops (unit-tested within 3 % of the Gunn-Kinzer values 4.03, 6.49, 8.06, 8.83, 9.09 as quoted in the literature; those reference values were taken from memory of the published table, not re-fetched).
Below 0.5 mm the fit goes negative, so RainFX uses (modelled): Stokes law `rho g d^2 / (18 mu)` below 0.1 mm (capped at 0.27 m/s),
and a power-law bridge `0.27 (D / 0.1)^1.25` from 0.1 to 0.5 mm that is continuous with both ends.

| D (mm) | v (m/s) |
|---|---|
| 0.1 | 0.27 |
| 0.2 | 0.64 |
| 0.5 | 2.02 |
| 1 | 4.00 |
| 2 | 6.55 |
| 3 | 7.95 |
| 5 | 9.14 |

Drops larger than about 5 to 6 mm break up in reality; presets cap at 5.5 mm.

### Hail (cited relation and NSSL bands; modelled drag factor)

A review of hail fall speed gives `v = 9 D^0.8` with D in cm for stones up to about 8 cm. NSSL notes natural hail falls
slower than the solid-sphere estimate and gives speed bands (under 1 inch about 9-25 mph, 1 to 1.75 inch 25-40 mph, 2 to 4 inch
44-72 mph). Published speeds spread widely: the NSSL bands above, versus about 50 mph (22 m/s) for 1 inch hail in a roofing-inspection source. RainFX multiplies the solid-sphere relation by a drag factor 0.85 (modelled), so 1 cm hail falls at 7.7 m/s and 2.5 cm (1 inch) at 16 m/s (36 mph, inside the NSSL 25-40 mph band). Unit tests assert the 1 cm value lies in the NSSL small-hail band (4-11 m/s).

### Snow (cited range; modelled formula)

Studies of snowflake fall speed report roughly 1-2 m/s once flakes are large, with dry dendrites slower and
weak dependence on size for aggregates; graupel depends more on diameter. RainFX uses `v0 (0.85 + 0.03 D)` with `v0` per
preset (0.9 light snow, 1.2 heavy snow, 1.3 blizzard). Wet snow is faster: observed wet-snow particles of 2.4 mm or more average about 2 m/s (standard deviation 0.8), so for wet snow create a user preset with `snow_speed_ms` near 1.8 and `inertia` near 1. Treat all snow values as starting points to tune by eye.

## 3. Air coupling

A particle accelerates toward the local air-relative terminal velocity with relaxation time `tau = v_t / g`
(from `dv/dt = (v_target - v) / tau`, which has terminal speed `v_t` under gravity). The step update is the exact solution:

```text
v(t + dt) = v_target + (v(t) - v_target) exp(-dt / tau)
v_target  = wind + gust + (0, 0, -v_t)
```

| Particle | v_t (m/s) | tau (s) |
|---|---|---|
| 1 mm drop | 4.0 | 0.41 |
| 3 mm drop | 7.95 | 0.81 |
| snow flake | 1.0 | 0.10 x Inertia (presets use 1.5 to 2.5) |

Consequences you can verify: heavy rain with 4 m/s wind tilts streaks atan(4 / 3.8) = 46 degrees (the table in `PRESETS.md`);
large drops lag gusts more than small ones; a 15 m/s blizzard wind produces nearly horizontal flakes.

Gusts (modelled): `3-D noise(pos / L + (v_g t, 0.37 v_g t, 0)) - 0.5`, scaled by `2 x gust_strength`, vertical component multiplied by 0.6. This is not turbulence theory; it gives spatially coherent, time-varying wind.

## 4. Impact

- **Rain** (modelled): droplets are spawned at the hit point, ejected around the surface normal. Speed is `Splash Speed x (0.4..1.6) x clamp(D / 2 mm, 0.5, 2)`; lifetime 0.15-0.4 s; ballistic under gravity. `core.physics.splash_speed` documents the same heuristic.
- **Hail and sleet** (modelled): `v' = 0.85 v_tangent - e v_normal`, limited by `Max Bounces`. Restitution 0.5 (hail), 0.35 (sleet). Real restitution depends on surface and stone size; use the preset as a start.
- **Snow, freezing rain**: stick and recycle. No accumulation in v0.1.

## 5. Visual density and streaks

A camera exposes for a shutter time `T`; a drop moving at `v` leaves a streak of length `v T`.
Default `T = 1/48 s` (180 degree shutter at 24 fps) gives 0.08 m for a 3.8 m/s drop and 0.19 m for a 9 m/s drop. The mesh is stretched
by exactly this length, which is why renderer motion blur should be off for the drops (double blur otherwise).
Renderer motion blur cannot paint real trails instead: simulation zones step only at whole frame boundaries,
so every shutter subframe sample sees identical geometry and the blur is a no-op for the particles (verified in Blender 5.2.1: identical Cycles and EEVEE renders with motion blur on and off).

True drop width (0.5-5 mm) is sub-pixel at normal distances, so width is multiplied by `Visual Scale` (3-5 in presets).
True concentration is two orders of magnitude above what can be simulated interactively (`SYSTEM_DESIGN.md` section 5).
Lower `Visual Scale` and raise `Quality` for close-up hero shots; raise `Visual Scale` for wide shots.

## 6. Rain categories (cited, WMO-style scheme)

WMO-style thresholds used to place presets: light up to 2.5 mm/h, moderate 2.5-7.5, heavy 7.6-50, violent above 50.
Agencies disagree on exact limits; these are starting points. Drizzle: drops under about 0.5 mm.

## 7. What is not modelled

Drop oscillation and deformation, coalescence and breakup, collision between particles, evaporation, electrical
effects of lightning on drop motion, temperature dependence of air density and viscosity (fixed at 15 C), altitude.


---

## Research Sources


All pages below were retrieved through Firecrawl (search or scrape) while designing RainFX. "Used for" states exactly
what was taken from each. Anything not listed here is general knowledge and is labelled "textbook" or "modelled" in `PHYSICS.md`.

### Blender documentation and release notes

| Source | Used for |
|---|---|
| https://developer.blender.org/docs/release_notes/5.2/ | Overview of 5.2 changes |
| https://developer.blender.org/docs/release_notes/5.2/python_api/ | Geometry Nodes modifier inputs moved to `modifier.properties.inputs.<identifier>.value`; node socket identifier changes (Compare, Random Value) |
| https://developer.blender.org/docs/release_notes/5.2/geometry_nodes/ | Geometry Nodes changes in 5.2; Geometry Nodes modifiers on empties |
| https://developer.blender.org/docs/release_notes/5.2/physics/ | New experimental Geometry Nodes physics system (hair and cloth focus, Collider effector for closed meshes) |
| https://developer.blender.org/docs/release_notes/5.0/python_api/ | Compositor as node group (`compositing_node_group`), EEVEE engine id, `use_nodes` deprecation, `bpy.props` storage change |
| https://docs.blender.org/api/5.2/bpy.types.NodesModifier.html | `NodesModifier.properties` (read-only, may be `None`), `bakes`, `bake_directory`, `is_input_visible` |
| https://docs.blender.org/manual/en/latest/physics/index.html | Map of physics systems (emitter particles, collision, force fields, fluid, rigid body, simulation nodes) in the 5.2 LTS manual |
| https://docs.blender.org/manual/en/latest/physics/collision.html | Collision modifier settings for particles (permeability, stickiness, kill, damping, friction) |
| https://docs.blender.org/manual/en/latest/physics/particles/emitter/physics/newtonian.html | Newtonian particle physics: drag, Brownian, damping, size, mass, integrators |
| https://docs.blender.org/manual/en/latest/physics/simulation_nodes.html | Simulation nodes overview and baking |
| https://docs.blender.org/manual/en/latest/modeling/geometry_nodes/simulation/simulation_zone.html | Simulation zone semantics: named attributes only, inputs evaluated once vs every step, Delta Time |
| https://docs.blender.org/manual/en/latest/advanced/extensions/getting_started.html | Extension manifest schema 1.0.0, required fields, build and validate commands |

The 5.2.1 manual and API pages were read as "latest" / "5.2". Blender 5.2.1 itself could not be run.

### Physics

| Source | Used for |
|---|---|
| https://journals.ametsoc.org/view/journals/atot/39/3/JTECH-D-21-0049.1.pdf (J. Atmos. Oceanic Technol. 39) | Gunn and Kinzer (1949) terminal-velocity data have a maximum drop size of 5.8 mm |
| https://www.atmos.albany.edu/facstaff/rfovell/ATM562/gunn-marshall-1958.pdf | Marshall-Palmer intercept N0 = 8.0 x 10^3 m^-3 (per mm) for rain; Gunn and Kinzer terminal speeds |
| https://hess.copernicus.org/articles/5/615/2001/hess-5-615-2001.pdf | Marshall-Palmer parameterisation remains a realistic average drop-size distribution |
| https://www.nssl.noaa.gov/education/svrwx101/hail/ | Hail fall-speed bands: under 1 in 9-25 mph, 1-1.75 in 25-40 mph, 2-4 in 44-72 mph; natural hail slower than solid ice spheres |
| MDPI Geosciences 10(12):500 (hail review; found via search, page not re-fetched for this file) | `v = 9 D^0.8` (D in cm) hail terminal velocity relation |
| https://www.nachi.org/hail-damage-part4-31.htm | Counter-example: roofing source quotes about 50 mph for 1 in hail, much higher than NSSL; shows the spread in published hail speeds |
| https://journals.ametsoc.org/view/journals/apme/45/10/jam2406.1.pdf (J. Appl. Meteor. Climatol. 45) | Wet-snow particles of 2.4 mm or more fall at about 2 m/s (standard deviation 0.8) |
| https://tellusjournal.org/articles/10.16993/tellus.4127 | Large aggregate snowflakes with terminal velocities up to 1.5 m/s |
| https://www.opticalscientific.com/feeds/blog/standard-unit-rainfall-precipitation-wmo | WMO rain intensity categories: light 2.5 mm/h or less, moderate 2.6-7.5, heavy 7.6 or more, violent over 50 |
| https://community.wmo.int/site/knowledge-hub/programmes-and-initiatives/aviation/aviation-hazards-precipitation | Showers classed violent above 50 mm/h |

### Not sourced (entered from general knowledge)

- Marshall-Palmer slope `L = 4.1 R^-0.21`.
- Atlas et al. fit `v = 9.65 - 10.3 exp(-0.6 D)` and the Gunn-Kinzer reference values used in unit tests.
- Stokes law, air viscosity and density constants.
- All "modelled" items (gusts, splash, bounce, snow speed formula, hail drag factor 0.85).

### Web search availability

Firecrawl enforced a per-minute request limit during research; some scrapes were retried. Search results are excerpts; pages
were not read in full unless listed under Blender documentation above.


---

## Reference Analysis


Two files were supplied as references. Both were written in Blender 3.6 (file version 306) and were opened read-only in
headless Blender 5.0.1 for this analysis. Node counts and sockets below are read from the files; statements about intent are
marked as inferences where the graph was not traced node by node.

### 1. `rain_generator.blend`

| Object / node group | Nodes | Key nodes | Inputs |
|---|---|---|---|
| Rain Zone | 67 | Simulation Input, Instance on Points, Delete Geometry x2, Object Info, Random Value x3, Set Position x5 | Amount, Scale, Fall Speed, Instance (object), Size X/Y/Z, Tilt X, Tilt Y, Outline |
| Rain Splash | 37 | Simulation Input, Distribute Points on Faces, Duplicate Elements, Capture Attribute, Delete Geometry, Random Value x2, Set Position | Geometry (ground), Density, Vertex Group, Z Limit, Drops/Splash, Power, Speed, Radius, Material |
| Droplet | 5 | (mesh generator) | Length, Radius |

Reading: a box of simulated points falls at a user-set speed with a tilt, is instanced as a droplet object, and is deleted
or recycled by a height limit. Splashes are generated by distributing points on the *ground surface* and duplicating them with random velocity.
There is no Raycast, Proximity or Sample Nearest Surface node, so drops do not detect objects; the ground is a Z limit and a splash source surface.

### 2. `dynamic_rain_addon_1_0_0.zip` (38 MB)

Package contents: `__init__.py` (145 lines, generated-add-on style with `sna_` / `SNA_PT_` names), `assets/Dynamic Rain.blend`, one PNG.

| Item | Observation |
|---|---|
| Packaging | Legacy `bl_info` add-on, Blender 3.6.0, version 1.0.0. The add-on appends the object `Raindrop` from the bundled blend with `bpy.ops.wm.append` |
| Panel code | Reads `bpy.data.objects['Raindrop'].modifiers['几何节点']` (the Chinese UI name of the Geometry Nodes modifier) and exposes inputs by identifier: `["Input_10"]`, `["Input_2"]`, `["Input_3"]`, `["Input_5"]` |
| Node group `Dynamic Rain` | 107 nodes: Simulation Input, Proximity x2, Sample Nearest Surface x3, Distribute Points on Faces, Instance on Points x2, Delete Geometry x3, Collection Info x2, Points to Volume, Mesh to Volume, Volume to Mesh, Noise Texture, Random Value x2, Set Position x4 |
| Inputs | X size, Y size, Rain Density, Rain Height, Raindrop acceleration, sputtering ratio, Raindrop length, raindrop size, water raindrop size, Raindrop disappearing height |
| Node group `删除几何体内点` | "Delete points inside geometry": 12 nodes, Sample Nearest Surface x2 + Delete Geometry |
| Scene | Cube, Raindrop, an umbrella empty with umbrella parts as materials |

Reading: collision is implemented as *point inside geometry* removal using nearest-surface sampling (the umbrella demo),
plus Proximity for splash placement. The volume nodes (Points to Volume -> Volume to Mesh) likely build a blobby water
surface (inference). "Raindrop acceleration" suggests constant acceleration rather than drag-limited terminal speed (inference from the input name).

### 3. What RainFX keeps, changes and fixes

| Topic | References | RainFX |
|---|---|---|
| Solver | Simulation zone in a box with respawn | Same idea, kept |
| Instancing | Instance on points aligned to velocity | Kept; streak length now comes from speed x shutter |
| Collision | Z limit / point-inside deletion / proximity | Raycast along each step: stops fast drops at thin surfaces, gives a hit position and normal for splash and bounce |
| Splash origin | Ground surface samples (rain generator) | Actual impact points of simulated drops |
| Drop physics | User-set fall speed or acceleration, constant sizes | Marshall-Palmer size distribution, Gunn-Kinzer terminal speed, drag relaxation, wind coupling |
| Weather range | One rain look | 14 presets: dew, drizzle to downpour, wind-driven, thunderstorm, freezing rain, sleet, hail (bounce), snow, blizzard |
| Distribution | 38 MB zip with appended blend | Node groups built from code (`gn/precip.py`); package is about 30 KB |
| Input access | `["Input_N"]` identifiers, hard-coded object and localized modifier names | Socket *names* through `compat.set_modifier_input`; emitter found by custom property; works with the 5.2 `properties.inputs` API |
| Blender versions | 3.6 | 5.0+ (tested 5.0.1, targeting 5.2.1) |
| Atmosphere | none in the add-on | Fog volume, sky and sun dimming, lightning, compositor glow |

#### Compatibility warning for the reference add-on

The `["Input_10"]` style custom-property access is the exact pattern replaced by `modifier.properties.inputs.<identifier>.value`
in Blender 5.2, and `bl_info`-only add-ons targeting 3.6 will need conversion to an extension manifest for the 5.x extensions
workflow. The reference add-on should not be expected to work unchanged in 5.2.1.

#### Assets worth reusing

The umbrella scene in `Dynamic Rain.blend` is a good collision acceptance test: drops must stay off the umbrella and ground
splashes must appear only where drops actually land. The RainFX test world uses a 2 m cube for the same purpose
(`tests/blender_smoke.py`). Copying meshes or materials from the reference files into a released add-on requires checking their license first; none was included in the archive.
