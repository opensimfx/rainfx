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
