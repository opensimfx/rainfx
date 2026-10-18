# Physics

Every formula here exists in `rainfx/core/physics.py` (Python, tested) and, where the simulation needs it per particle,
is re-implemented as nodes in `gn/precip.py`. The two implementations are checked against each other by the
derived values shown in the Derived Physics panel.

Confidence labels:

- **cited**: confirmed in a web source fetched for this project (`RESEARCH_SOURCES.md`).
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

True drop width (0.5-5 mm) is sub-pixel at normal distances, so width is multiplied by `Visual Scale` (3-5 in presets).
True concentration is two orders of magnitude above what can be simulated interactively (`SYSTEM_DESIGN.md` section 5).
Lower `Visual Scale` and raise `Quality` for close-up hero shots; raise `Visual Scale` for wide shots.

## 6. Rain categories (cited, WMO-style scheme)

WMO-style thresholds used to place presets: light up to 2.5 mm/h, moderate 2.5-7.5, heavy 7.6-50, violent above 50.
Agencies disagree on exact limits; these are starting points. Drizzle: drops under about 0.5 mm.

## 7. What is not modelled

Drop oscillation and deformation, coalescence and breakup, collision between particles, evaporation, electrical
effects of lightning on drop motion, temperature dependence of air density and viscosity (fixed at 15 C), altitude.
