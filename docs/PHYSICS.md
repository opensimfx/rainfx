# Physics

Every formula here exists in `rainfx/core/physics.py` (Python, tested) and, where the simulation needs it per particle,
is re-implemented as nodes in `gn/precip.py`. The two implementations are checked against each other by the
derived values shown in the Derived Physics panel.

Confidence labels:

- **cited**: confirmed in a web source fetched for this project (listed in [REFERENCES.md](REFERENCES.md)).
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

- **Rain: whether a drop splashes** (cited: Yarin, *Drop Impact Dynamics*, Annu. Rev. Fluid Mech. 2006). Each
  landing computes its own splashing parameter K = We Oh^-2/5, with We = rho D V^2 / sigma and
  Oh = mu / sqrt(rho sigma D) for water (rho 1000 kg/m^3, sigma 0.072 N/m, mu 0.001 Pa s), D its diameter and V its
  speed relative to the collider. It splashes only when K is above the threshold K_S = 2100 + 5880 H^1.44
  (H = film depth / D); the *Splash Threshold* input defaults to the thin-film value 2100. At terminal speed a
  0.3 mm drizzle drop gives K of about 35 (never splashes), 1 mm about 2,100 (borderline), 2 mm about 12,800 and
  4 mm about 52,000, so light rain barely splashes and heavy rain splashes hard.
- **Rain: how much** (modelled). Mean droplets per impact = `Splash Amount` x clamp(ln(K / K_S) / ln(K_ref / 2100), 0, 2),
  where K_ref is the 2 mm reference drop: `Splash Amount` is what a 2 mm drop at terminal speed throws, bigger
  drops up to twice that. The count is rounded stochastically per impact so the mean holds. Droplets are ejected
  around the surface normal at `Splash Speed x (0.4..1.6) x clamp((K / K_ref)^1/4, 0.5, 2)`; lifetime 0.15-0.4 s;
  ballistic under gravity. Rain presets raised `splash_amount` in 0.4 (moderate 4, heavy and downpour 6) because
  small drops no longer splash at all.
- **Crown** (cited growth law, modelled look). Every splashing drop on an up-facing face (normal z > 0.5) also
  leaves a crown: an open ring standing on the surface whose radius grows with the square root of time,
  R = D/2 sqrt(V t / D) (about 11 mm 40 ms after a 2 mm drop lands), with height 0.57 R (crown height grows at
  dh/dr of about 0.57). It lives 0.1 s, about the time to the Worthington jet (116 ms). Its size is enlarged by
  sqrt(`Visual Scale`) so it reads at the scale of the enlarged streaks. *Crowns* switches it off.
- **Spray mist** (cited profile, modelled amount). Raindrops on water throw small droplets whose number density
  falls exponentially with height; few rise above 0.33-0.45 m (JFM study of raindrops hitting water). Rain
  presets from 8 mm/h (none) to 40 mm/h (full) add a 0.5 m high volume over the ground of the rain box, density
  3 x the rain fog at the ground and exp(-height / 0.1 m) above it.
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
The factor fades in with distance from the active camera (modelled): width = D x min(max(d / 2 m, 1), Visual
Scale). Within 2 m drops keep their true width (a 3 mm drop half a metre from the lens is about 8 px at 1280 px
and 35 mm), and from there on a streak keeps roughly the same on-screen width. Splashes and crowns use the same
factor (crowns its square root).

### Look (cited optics, modelled shading)

- **Streak shading** (cited: Garg and Nayar). A drop works as a 165 degree wide-angle lens: about 94 % of what
  it shows is refracted surroundings, 6 % is reflection at its rim. Each streak changes a pixel only faintly
  (at most about 4 % of the background, beta < 0.039). The streak, splash, distant and near materials are
  therefore Translucent (light from the hemisphere behind the streak, standing in for the wide refracted view)
  mixed with a Glossy term by Fresnel (IOR 1.33), then with Transparent by alpha (modelled). No emission and
  no diffuse: rain blazes in front of a lamp or a bright background, reads against dark walls by day (it passes
  on the bright sky behind and above it) and vanishes against the sky. The 0.4 Principled version had 10 %
  white diffuse, which lit every streak from every side; straight-through refraction (IOR 1.0, rough) made rain
  all but invisible. Alpha varies per streak (x 0.6-1.4, modelled, for drop size and oscillation phase) and rises
  toward the rim (Fresnel, x 0.75-1.5).
- **Backlight** (cited practice: "front-light snow, back-light rain"). *Add Rain Backlight* places a spot beyond
  the rain, shining back toward the camera at 20-25 degrees to the side and 30-40 degrees from above
  (`core.physics.backlight_placement`). Its power is set for about 3 W/m^2 at the aim point at any distance
  (modelled starting value).
- **Fog box** (modelled). The fog reaches 3 x the rain volume horizontally and 1.5 x its height, and its density
  fades out by smoothstep over the outer 12 % of each half-width and the top 30 %, so its edge is never seen as
  a wall of haze. Its base sits below the ground: a volume face coplanar with a surface makes Cycles light the
  surface as if it were inside the volume.
- **Fog from rain rate** (cited). Rain extinction beta = 0.312 R^0.67 per km (R in mm/h; Halder et al., after
  Marshall-Palmer rain). 10 mm/h gives about 1.5 per km, a visibility near 2 km, matching the 1-3 km observed
  (Gultepe et al.). Rain presets set fog = `fog_mist` x beta with `fog_mist` = 6 (modelled: mist and spray
  that come with rain, and a fog box only tens of metres deep), so heavier rain is more veiled in the measured
  proportion. Drizzle, frozen and dew presets keep a hand-set `fog_density`.
- **Halo around lights** (modelled). The compositor Fog Glow strength follows the rain rate,
  0.15 + 0.12 ln(1 + R/2), capped at 0.6 (about 0.22 at 1.5 mm/h, 0.44 at 20 mm/h).
- **Where it is wet** (modelled). The simulation carries a thinned-out sample of the drops, and only inside its
  volume, so in a real scene its hits alone leave most surfaces dry. Every face corner of a collider therefore
  gets an exposure: five rays from just off its face toward where the rain comes from (from straight up to the
  full wind tilt in quarter steps, tilt = atan(wind / v_t)) against a world-space copy of all colliders, exposure = share of clear
  rays x smoothstep(0, 0.5, facing). Gusts swing real rain about, so averaging the three gives a soft rain shadow
  on the upwind side of a street canyon instead of a hard dry band, while real cover (a roof) blocks all five.
  Exposed corners take the preset's ambient wetness, 0.6 + 0.4 sqrt(R / 10) capped at 1 (drizzle about 0.7, 10
  mm/h soaked), and flat exposed ground (normal z above 0.94-0.99) the ambient pool level 0.25 log2(1 + R / 2.5)
  capped at 0.7 (x the *Puddles* slider), which the shader's flood level turns into puddles. With *Already Wet*
  off they rise toward these levels with time constant 120 / sqrt(R) s (10-120 s). Snow presets cover exposed
  vertices facing up (normal z smoothstep 0.5-0.9) with 0.35 + 0.012 x flake density (light snow 0.57, heavy
  and blizzard 1) x *Snow Depth* (modelled; snow presets carry no snowfall rate). Simulated hits add wetness on
  top with a Gaussian footprint, Strength x exp(-(d / Wet Radius)^2) per step: an exponential tail (0.4) added
  about 2 % per step four radii away, which crept under roofs over a shot.
- **Wet surfaces** (cited: Lagarde). Wet albedo = albedo x lerp(1, 0.2, porosity); porosity from roughness,
  zero for smooth or metallic surfaces, so the hue is kept and metal does not darken. Roughness tends to a water
  film's, lerp(r, min(r, 0.18), wet) (modelled 0.18), then x (1 - 0.95 pool): the film fills the surface texture,
  which is what smears street lamps into long streaks on wet asphalt. Standing water also flattens the
  material's normal map. Water F0 0.02 comes from the Principled IOR.
  Puddle shape follows Lagarde's flood level against a height map (modelled: world-space noise, features ~2 m):
  puddle = clamp((1.2 pool - h) / 0.15), so low spots fill first and edges are organic; wetness = clamp(1.3 wet -
  0.3 h), so high spots dry first (observed: convex dries before concave).
- **Puddle ripples** (cited method: Lagarde, *Water drop 2b*). Standing water (the pool attribute) gets rain
  rings instead of a drifting noise bump: four layers of Voronoi cells (0.25 m) in world space, each cell a ring
  with its own random start; per layer, drop = fract(phase + 1.6 t m_i) (m_i = 1, 0.85, 0.93, 1.13), height =
  clamp(0.2 + 0.8 W - drop) x x x sin(clamp((drop - 1 + x) x 9, 0, 3) pi), x = 1 - distance / half a cell, so 1.5
  waves run outward and fade. Layer i shows only when 4 W > i. W = sqrt(R / 50) (modelled), so light rain has one
  sparse layer and 50 mm/h all four. The rings are procedural, not placed at the simulated impact points: a shader
  cannot read the impact list, and colliders rarely have the mesh resolution to carry rings as attributes.
- **Foreground layer** (cited practice: separate far, mid and near rain layers with real depth of field;
  befores & afters on comping CG rain). *Foreground Rain* adds streaks 0.6-4 m around the camera, 2.5 x wider and
  fainter as if out of focus (modelled), streak length = fall speed x shutter.
- **Drips** (cited: capillary length; modelled rates). Water collected on a roof, sill or lamp head runs to its
  edge and leaves it as pendant drops, which detach at about two capillary lengths (water: l_c = sqrt(sigma /
  rho g) = 2.7 mm), so drips are 5 mm across, bigger than most raindrops. A drip point sits on a near-horizontal
  edge where an up-facing face meets a side face or the mesh ends, open to the sky above that face and with at
  least 0.3 m of air below; one per 0.3 m of edge (x *Drip Density*). Period between drops 1.2 s x sqrt(5 / R)
  (0.25-4 s, modelled), x 0.6-1.6 per point. A drop falls from rest, s = g t^2 / 2, until it reaches its terminal
  speed (9.1 m/s for 5 mm), then at that speed, and is gone when it has fallen the open air below its point.
- **Lens drops** (modelled after rain-on-glass shaders). A drop on the front element is far out of focus, so
  what is seen through it is refracted and blurred while the frame around it stays sharp: the compositor mixes a
  blurred copy (0.4 % of the frame width) in under the drop mask. The faster layer has sliding drops, taller
  than wide with a flatter bottom, half of them dragging a tapering wet trail.

## 6. Rain categories (cited, WMO-style scheme)

WMO-style thresholds used to place presets: light up to 2.5 mm/h, moderate 2.5-7.5, heavy 7.6-50, violent above 50.
Agencies disagree on exact limits; these are starting points. Drizzle: drops under about 0.5 mm.

Start points of the simulation are removed when a ray from them back along their fall direction (up and into
the wind) meets a collider: a drop could not have reached a point under a roof or inside a closed shape. Small,
slow drops in a strong wind still reach under roof edges, as they do in real rain.

## 7. What is not modelled

Drop oscillation and deformation (only as per-streak alpha variation), water running down walls and gutters (drips appear at edges without a flow model), coalescence and breakup, collision between particles, evaporation, electrical
effects of lightning on drop motion, temperature dependence of air density and viscosity (fixed at 15 C), altitude.


---

Sources for every value above are in [REFERENCES.md](REFERENCES.md).
