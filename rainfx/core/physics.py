"""Hydrometeor physics used to derive simulation parameters.

Pure functions, no ``bpy`` import, unit-tested in ``tests/test_physics.py``.
Units: metres, seconds, millimetres for particle diameters (``d_mm``),
mm/h for rainfall rate.

Sources (full list in docs/PHYSICS.md):
* Gunn & Kinzer (1949) terminal-velocity measurements, largest drop 5.8 mm.
* Atlas et al. (1973) fit  v = 9.65 - 10.3 exp(-0.6 D).
* Marshall & Palmer (1948) drop-size distribution  N(D) = N0 exp(-L D).
* Hail  v = 9 D^0.8  (D in cm, valid to about 8 cm), reviewed in
  MDPI Geosciences 10(12):500; NSSL notes natural hail falls slower than
  solid ice spheres.
"""
from __future__ import annotations

import math

G = 9.80665                 # m/s^2
MP_N0 = 8000.0              # m^-3 mm^-1, Marshall-Palmer intercept
RHO_WATER = 1000.0          # kg/m^3
MU_AIR = 1.81e-5            # Pa s, dynamic viscosity of air near 15 C


def mp_lambda(rate_mm_h: float) -> float:
    """Marshall-Palmer slope parameter (mm^-1) for a rain rate in mm/h."""
    if rate_mm_h <= 0:
        raise ValueError("rain rate must be > 0")
    return 4.1 * rate_mm_h ** -0.21


def stokes_velocity(d_mm: float) -> float:
    """Stokes-regime fall speed (m/s); valid only below about 0.1 mm."""
    d = d_mm * 1e-3
    return RHO_WATER * G * d * d / (18.0 * MU_AIR)


def rain_terminal_velocity(d_mm: float) -> float:
    """Terminal velocity (m/s) of a raindrop of diameter ``d_mm`` in still air.

    Piecewise: Stokes (<0.1 mm), power-law bridge (0.1-0.5 mm), Atlas fit
    (>=0.5 mm). The Atlas fit reproduces Gunn-Kinzer within about 2 % over
    0.5-5.8 mm.
    """
    if d_mm <= 0:
        return 0.0
    if d_mm < 0.1:
        return min(stokes_velocity(d_mm), 0.27)
    if d_mm < 0.5:
        return 0.27 * (d_mm / 0.1) ** 1.25
    return 9.65 - 10.3 * math.exp(-0.6 * min(d_mm, 8.0))


def hail_terminal_velocity(d_mm: float, drag_factor: float = 0.85) -> float:
    """Hailstone fall speed (m/s). ``drag_factor`` below 1 models natural
    stones falling slower than solid ice spheres."""
    d_cm = max(d_mm, 0.0) / 10.0
    return drag_factor * 9.0 * min(d_cm, 8.0) ** 0.8


def snow_fall_speed(d_mm: float, base_ms: float = 1.0) -> float:
    """Snow fall speed (m/s). Dendrites are nearly size independent, so only
    a weak size term is applied around ``base_ms`` (studies report 1-2 m/s for
    larger flakes, lower for dry dendrites)."""
    return max(0.3, base_ms * (0.85 + 0.03 * min(max(d_mm, 0.0), 10.0)))


def relaxation_time(v_terminal: float) -> float:
    """Velocity relaxation time tau = v_t / g (s). Velocity converges to the
    target velocity as exp(-t / tau)."""
    return max(v_terminal / G, 1e-3)


def sample_truncated_exponential(u: float, lam: float, d_min: float, d_max: float) -> float:
    """Inverse-CDF sample (u in [0, 1)) of an exponential distribution
    truncated to [d_min, d_max] with slope ``lam`` (mm^-1)."""
    if lam <= 0:
        return d_min + u * (d_max - d_min)
    span = 1.0 - math.exp(-lam * (d_max - d_min))
    return d_min - math.log(1.0 - u * span) / lam


def mean_drop_diameter(lam: float, d_min: float, d_max: float, n: int = 2000) -> float:
    """Numerical mean diameter (mm) of the truncated exponential."""
    return sum(sample_truncated_exponential((i + 0.5) / n, lam, d_min, d_max)
               for i in range(n)) / n


def physical_number_density(rate_mm_h: float) -> float:
    """Total drops per m^3 of air, N0 / lambda (Marshall-Palmer)."""
    return MP_N0 / mp_lambda(rate_mm_h)


def physical_drop_count(rate_mm_h: float, volume_m3: float) -> int:
    return int(physical_number_density(rate_mm_h) * volume_m3)


def wind_vector(speed_ms: float, direction_deg: float) -> tuple[float, float, float]:
    """Horizontal wind vector. Direction is the compass-style angle the wind
    blows towards: 0 deg = +Y, 90 deg = +X."""
    a = math.radians(direction_deg)
    return (speed_ms * math.sin(a), speed_ms * math.cos(a), 0.0)


def fall_angle_deg(v_terminal: float, wind_ms: float) -> float:
    """Streak tilt from vertical for a drop fully coupled to the wind."""
    return math.degrees(math.atan2(wind_ms, v_terminal))


def streak_length(speed_ms: float, shutter_s: float) -> float:
    """Motion-blur streak length (m) for a given shutter time."""
    return speed_ms * shutter_s


def splash_speed(drop_speed: float, d_mm: float, k: float = 0.12) -> float:
    """Heuristic ejection speed (m/s) of splash droplets."""
    return k * drop_speed * (0.6 + 0.2 * min(d_mm, 5.0))


# --------------------------------------------------------------------------
# Cinematic look (sources: docs/PHYSICS.md "Look" section)
# --------------------------------------------------------------------------

def rain_extinction_per_m(rate_mm_h: float) -> float:
    """Optical extinction of rain (1/m) for a rainfall rate in mm/h.

    beta = 0.312 R^0.67 per km (Halder et al., ICCV 2019, after Marshall-Palmer
    rain); 10 mm/h gives about 1.5 per km, a visibility of roughly 2 km, in line
    with the 1-3 km observed for 10 mm/h (Gultepe et al.).
    """
    if rate_mm_h <= 0:
        return 0.0
    return 0.312e-3 * rate_mm_h ** 0.67


def rain_glare_strength(rate_mm_h: float) -> float:
    """Fog Glow strength for the compositor halo around lights (modelled).

    Halos come from multiple scattering in the rain-filled air, so they grow
    with rain rate; log growth keeps a downpour from washing the frame out.
    About 0.22 at 1.5 mm/h, 0.44 at 20 mm/h, capped at 0.6.
    """
    if rate_mm_h <= 0:
        return 0.15
    return min(0.6, 0.15 + 0.12 * math.log(1.0 + rate_mm_h / 2.0))


def wet_porosity(roughness: float, metallic: float = 0.0) -> float:
    """Porosity estimate for wet shading (Lagarde, "Water drop 3b").

    Rough dielectrics (stone, asphalt, wood) are porous and darken when wet;
    smooth or metallic surfaces are not porous and only gain a water film.
    """
    r = min(max(roughness, 0.0), 1.0)
    m = min(max(metallic, 0.0), 1.0)
    return min(max((r - 0.5) / 0.4, 0.0), 1.0) * (1.0 - m)


def wet_albedo_factor(porosity: float) -> float:
    """Albedo multiplier of a fully wet surface: lerp(1, 0.2, porosity)."""
    p = min(max(porosity, 0.0), 1.0)
    return 1.0 + (0.2 - 1.0) * p


def backlight_placement(cam, target, distance: float, azimuth_deg: float = 20.0,
                        elevation_deg: float = 30.0):
    """Where to put a rain backlight (location, aim point, beam direction).

    Rain streaks are bright only when lit from behind ("front-light snow,
    back-light rain"): the light sits beyond the rain, shining back toward the
    camera at an angle so it stays out of frame. The beam travels toward the
    camera, ``azimuth_deg`` to the side and ``elevation_deg`` downward; it is
    aimed at a point a quarter of the way from the rain centre to the camera so
    the drops nearest the lens catch it. Pure vector maths: tuples in, tuples out.
    """
    cx, cy, cz = cam
    tx, ty, tz = target
    fx, fy = tx - cx, ty - cy
    flen = math.hypot(fx, fy)
    if flen < 1e-6:                      # camera straight above: pick +Y
        fx, fy, flen = 0.0, 1.0, 1.0
    fx, fy = fx / flen, fy / flen        # horizontal camera -> rain direction
    sx, sy = fy, -fx                     # right-hand side of the view
    az, el = math.radians(azimuth_deg), math.radians(elevation_deg)
    # beam direction: back toward the camera (-f), to the side, downward
    ux = -fx * math.cos(el) * math.cos(az) + sx * math.cos(el) * math.sin(az)
    uy = -fy * math.cos(el) * math.cos(az) + sy * math.cos(el) * math.sin(az)
    uz = -math.sin(el)
    aim = (tx + (cx - tx) * 0.25, ty + (cy - ty) * 0.25, tz + (cz - tz) * 0.25)
    loc = (aim[0] - ux * distance, aim[1] - uy * distance, aim[2] - uz * distance)
    return loc, aim, (ux, uy, uz)


def angle_between_deg(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return math.degrees(math.acos(max(-1.0, min(1.0, dot / (na * nb)))))


# --------------------------------------------------------------------------
# Drop impact (sources: docs/PHYSICS.md "Impacts" section)
# --------------------------------------------------------------------------

SIGMA_WATER = 0.072         # N/m, surface tension of water near 20 C
MU_WATER = 1.0e-3           # Pa s, dynamic viscosity of water near 20 C
SPLASH_K_THIN_FILM = 2100.0  # K_S of a thin wet film: 2100 + 5880 H^1.44 as H -> 0 (Yarin 2006)
SPLASH_REF_D_MM = 2.0       # "Splash Amount" droplets belong to a 2 mm drop at terminal speed
CROWN_LIFE_S = 0.1          # crown rises and collapses within ~0.1 s (jet at ~116 ms, Yarin 2006)
CROWN_HEIGHT_RATIO = 0.57   # crown height grows with its radius at dh/dr ~ 0.57


def splash_k(d_mm: float, speed_ms: float) -> float:
    """Splashing parameter K = We * Oh^-2/5 of a water drop hitting a surface.

    We = rho D V^2 / sigma, Oh = mu / sqrt(rho sigma D) (Yarin, *Drop Impact
    Dynamics*, Annu. Rev. Fluid Mech. 2006). A drop splashes when K is above the
    surface's threshold K_S; a 2 mm drop at terminal speed gives about 12,800.
    """
    d = max(d_mm, 0.0) * 1e-3
    if d <= 0.0 or speed_ms <= 0.0:
        return 0.0
    we = RHO_WATER * d * speed_ms * speed_ms / SIGMA_WATER
    oh = MU_WATER / math.sqrt(RHO_WATER * SIGMA_WATER * d)
    return we * oh ** -0.4


def splash_threshold(film_ratio: float = 0.0) -> float:
    """K_S on a wet film of thickness ``film_ratio`` x drop diameter (H, 0..1)."""
    h = min(max(film_ratio, 0.0), 1.0)
    return 2100.0 + 5880.0 * h ** 1.44


SPLASH_K_REF = splash_k(SPLASH_REF_D_MM, rain_terminal_velocity(SPLASH_REF_D_MM))
_SPLASH_LOG_REF = math.log(SPLASH_K_REF / SPLASH_K_THIN_FILM)


def splash_droplet_mean(k: float, amount: float, k_s: float = SPLASH_K_THIN_FILM) -> float:
    """Mean number of splash droplets thrown by one impact (modelled).

    None below the threshold; ``amount`` for the 2 mm reference drop; grows with
    log(K / K_S) and is capped at twice ``amount`` for the biggest drops. The sim
    rounds it stochastically per impact, so the mean is kept exactly.
    """
    if k <= k_s or amount <= 0:
        return 0.0
    return amount * min(2.0, math.log(k / k_s) / _SPLASH_LOG_REF)


def splash_speed_factor(k: float) -> float:
    """Ejection-speed multiplier of splash droplets: (K / K_ref)^1/4 in 0.5..2."""
    if k <= 0:
        return 0.5
    return min(2.0, max(0.5, (k / SPLASH_K_REF) ** 0.25))


def crown_radius(d_mm: float, speed_ms: float, t_s: float) -> float:
    """Crown rim radius (m) at ``t_s`` after impact: R ~ D/2 sqrt(V t / D).

    Crown radius grows with the square root of time (Yarin 2006); about 11 mm
    for a 2 mm drop 40 ms after it lands at terminal speed.
    """
    d = max(d_mm, 0.0) * 1e-3
    if d <= 0.0 or speed_ms <= 0.0 or t_s <= 0.0:
        return 0.0
    return 0.5 * d * math.sqrt(speed_ms * t_s / d)


def ripple_weight(rate_mm_h: float) -> float:
    """Puddle ring-ripple intensity 0..1 from the rain rate (modelled).

    sqrt(R / 50): one ripple layer in light rain, all four (Lagarde's layered
    rings) from about 50 mm/h.
    """
    if rate_mm_h <= 0:
        return 0.0
    return min(1.0, math.sqrt(rate_mm_h / 50.0))


SPRAY_SCALE_HEIGHT_M = 0.1   # splash spray number density decays exponentially with height
SPRAY_TOP_M = 0.5            # spray layer top; max droplet heights ~0.33-0.45 m (JFM spray study)


def spray_mist_factor(rate_mm_h: float) -> float:
    """0..1 ramp of the low splash-spray mist: none below 8 mm/h, full from 40 mm/h."""
    t = min(max((rate_mm_h - 8.0) / 32.0, 0.0), 1.0)
    return t * t * (3.0 - 2.0 * t)


# Visual Scale fades in with distance from the camera: drops nearer than this are
# drawn at their true diameter; further out the width grows as distance / NEAR
# (up to Visual Scale), so a streak stays roughly the same on-screen width.
VISUAL_SCALE_NEAR_M = 2.0


def effective_visual_scale(distance_m: float, visual_scale: float) -> float:
    """Width factor applied to a drop ``distance_m`` from the camera."""
    return min(max(distance_m / VISUAL_SCALE_NEAR_M, 1.0), visual_scale)


# --- drips from edges ------------------------------------------------------
# Rain collected on a roof, a sill or a lamp head runs to the edge and leaves it
# as pendant drops. A drop detaches when gravity beats surface tension along
# the edge, at about 2 capillary lengths (water: l_c = sqrt(sigma / rho g)
# = 2.7 mm), so drips are 4-6 mm across: bigger than most raindrops.
DRIP_D_MM = 5.0
DRIP_SPACING_M = 0.3        # one drip point per this much edge (x density)
DRIP_MIN_FALL_M = 0.3       # edges closer than this to what is below (curbs) don't drip visibly
DRIP_PERIOD_REF_S = 1.2     # one drop per point per this long at 5 mm/h ...
DRIP_RATE_REF_MM_H = 5.0    # ... shorter in heavier rain (more water reaching each edge)


def capillary_length_m() -> float:
    return (SIGMA_WATER / (RHO_WATER * G)) ** 0.5


def drip_period_s(rate_mm_h: float) -> float:
    """Seconds between drops from one drip point: ~ (rate_ref / rate)^0.5, 0.25-4 s."""
    r = max(rate_mm_h, 0.05)
    return min(4.0, max(0.25, DRIP_PERIOD_REF_S * (DRIP_RATE_REF_MM_H / r) ** 0.5))


def drip_fall(t_s: float, vt: float) -> tuple[float, float]:
    """(distance fallen, speed) of a drop released at rest t_s seconds ago.

    Free fall up to terminal speed vt, then constant speed (the same piecewise
    model the Drips node group evaluates per frame).
    """
    t_v = vt / G
    if t_s <= t_v:
        return 0.5 * G * t_s * t_s, G * t_s
    return 0.5 * vt * t_v + vt * (t_s - t_v), vt
