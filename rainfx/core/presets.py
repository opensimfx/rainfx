"""Weather presets: schema, validation, derived physics, JSON loading.

A preset is plain data. ``derive()`` converts it to the exact numbers fed to
the Geometry Nodes simulation so the UI, tests and docs share one source of
truth. No ``bpy`` import here.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Iterable

from . import physics as P

MODES = ("rain", "hail", "snow", "dew")
MODE_INDEX = {"rain": 0, "hail": 1, "snow": 2, "dew": 3}
CATEGORIES = ("rain", "frozen", "surface")


@dataclass
class Preset:
    id: str
    name: str
    category: str = "rain"
    mode: str = "rain"
    description: str = ""
    # --- hydrometeor population -------------------------------------------
    rate_mm_h: float = 5.0            # equivalent rainfall rate (drives Marshall-Palmer slope)
    d_min_mm: float = 0.3
    d_max_mm: float = 4.0
    lam_override: float = 0.0         # mm^-1, 0 = derive from rate (rain only)
    speed_scale: float = 1.0          # multiplies terminal speed
    snow_speed_ms: float = 1.0        # base snow fall speed
    visual_density: float = 10.0      # simulated particles per m^3 (artistic budget)
    # --- air ---------------------------------------------------------------
    wind_ms: float = 0.0
    wind_dir_deg: float = 0.0
    gust_strength: float = 0.0        # m/s amplitude of spatial/temporal gusts
    gust_scale_m: float = 6.0
    gust_speed_ms: float = 2.0
    inertia: float = 1.0              # multiplies relaxation time tau = vt/g
    # --- impact ------------------------------------------------------------
    splash_amount: int = 2            # splash droplets of a 2 mm drop at terminal speed (scaled per drop by K)
    splash_speed: float = 1.2         # m/s
    splash_life_min: float = 0.15
    splash_life_max: float = 0.4
    splash_size: float = 0.35         # fraction of parent diameter
    restitution: float = 0.0          # >0 => bounce (hail)
    max_bounces: int = 0
    # --- look --------------------------------------------------------------
    shutter_s: float = 1 / 48         # streak length = speed * shutter; 0 = spheres
    visual_scale: float = 4.0         # exaggerates sub-pixel drops
    material: str = "water"           # water | ice | snow
    # --- atmosphere --------------------------------------------------------
    fog_density: float = 0.004        # 1/m, used as-is when fog_mist is 0
    fog_mist: float = 0.0             # >0 (rain): fog = fog_mist x rain extinction of rate_mm_h
    fog_anisotropy: float = 0.3
    sky_mult: float = 0.8             # world background strength multiplier
    sun_mult: float = 0.5             # sun lamps strength multiplier
    # --- lightning ---------------------------------------------------------
    lightning_per_min: float = 0.0
    lightning_energy: float = 0.0     # W of the flash light
    # --- dew (surface beads) ----------------------------------------------
    dew_density_m2: float = 0.0
    dew_min_normal_z: float = 0.35
    # --- legacy particle engine / Blender Collision modifier ---------------
    col_permeability: float = 0.0
    col_stickiness: float = 0.0
    col_damping: float = 0.0
    col_friction: float = 0.2
    legacy_drag: float = 0.0

    def validate(self) -> list[str]:
        errs = []
        if self.mode not in MODES:
            errs.append(f"mode must be one of {MODES}")
        if self.category not in CATEGORIES:
            errs.append(f"category must be one of {CATEGORIES}")
        if not (0 < self.d_min_mm <= self.d_max_mm):
            errs.append("need 0 < d_min_mm <= d_max_mm")
        if self.mode != "dew" and self.visual_density <= 0:
            errs.append("visual_density must be > 0")
        if not (0.0 <= self.restitution <= 1.0):
            errs.append("restitution must be in [0, 1]")
        if self.mode == "rain" and self.rate_mm_h <= 0 and not self.lam_override:
            errs.append("rain needs rate_mm_h > 0 or lam_override")
        if self.fog_mist < 0:
            errs.append("fog_mist must be >= 0")
        if self.splash_life_min > self.splash_life_max:
            errs.append("splash_life_min > splash_life_max")
        return errs


def derive(p: Preset, box_m: tuple[float, float, float] = (16.0, 16.0, 10.0),
           quality: float = 1.0, max_count: int = 250_000) -> dict:
    """Numbers the simulation needs, derived from physics + preset."""
    volume = box_m[0] * box_m[1] * box_m[2]
    if p.mode == "dew":
        return {"count": 0, "mode_index": MODE_INDEX["dew"]}
    lam = p.lam_override or (P.mp_lambda(p.rate_mm_h) if p.mode == "rain" else 0.4)
    lam = max(lam, 0.01)
    d_mean = P.mean_drop_diameter(lam, p.d_min_mm, p.d_max_mm)
    if p.mode == "rain":
        vt_mean = P.rain_terminal_velocity(d_mean)
    elif p.mode == "hail":
        vt_mean = P.hail_terminal_velocity(d_mean) * p.speed_scale
    else:
        vt_mean = P.snow_fall_speed(d_mean, p.snow_speed_ms) * p.speed_scale
    count = int(min(max(p.visual_density * volume * quality, 100), max_count))
    out = {
        "count": count,
        "lambda": lam,
        "d_mean_mm": d_mean,
        "vt_mean_ms": vt_mean,
        "tau_s": P.relaxation_time(vt_mean) * p.inertia,
        "wind_vec": P.wind_vector(p.wind_ms, p.wind_dir_deg),
        "tilt_deg": P.fall_angle_deg(vt_mean, p.wind_ms),
        "streak_len_m": P.streak_length(vt_mean, p.shutter_s),
        "mode_index": MODE_INDEX[p.mode],
    }
    if p.mode == "rain":
        out["physical_count"] = P.physical_drop_count(p.rate_mm_h, volume)
        out["density_ratio"] = count / max(out["physical_count"], 1)
    return out


def fog_density_for(p: Preset) -> float:
    """Fog Volume Scatter density (1/m) for a preset.

    Rain presets with ``fog_mist`` > 0 follow their rain rate: the physical
    extinction of the falling drops (``physics.rain_extinction_per_m``) times
    ``fog_mist``, which stands in for the mist, spray and humid haze that come
    with rain and for the short depth of the fog box. Heavier rain is then more
    veiled in the measured proportion (extinction ~ R^0.67). Other presets, and
    user presets written before 0.4, use ``fog_density`` unchanged.
    """
    if p.fog_mist > 0 and p.mode == "rain" and p.rate_mm_h > 0:
        return p.fog_mist * P.rain_extinction_per_m(p.rate_mm_h)
    return p.fog_density


SPRAY_OVER_FOG = 3.0   # spray mist at the ground, relative to the rain fog (modelled)


def spray_density_for(p: Preset) -> float:
    """Ground-level density (1/m) of the low splash-spray mist; 0 = no spray layer.

    Only rain presets that follow the rain rate (``fog_mist`` > 0) get it, from
    8 mm/h (none) to 40 mm/h (full): heavy rain throws a thin white mist of
    splash droplets that thins out exponentially with height.
    """
    if p.fog_mist <= 0 or p.mode != "rain" or p.rate_mm_h <= 0:
        return 0.0
    return SPRAY_OVER_FOG * fog_density_for(p) * P.spray_mist_factor(p.rate_mm_h)


def glare_strength_for(p: Preset) -> float:
    """Compositor Fog Glow strength (halo around lights) for a preset."""
    return P.rain_glare_strength(p.rate_mm_h if p.mode == "rain" else 0.0)


def from_dict(d: dict) -> Preset:
    known = {f.name for f in fields(Preset)}
    p = Preset(**{k: v for k, v in d.items() if k in known})
    errs = p.validate()
    if errs:
        raise ValueError(f"preset '{p.id}': " + "; ".join(errs))
    return p


def load_file(path: Path) -> list[Preset]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    items = data["presets"] if isinstance(data, dict) and "presets" in data else data
    return [from_dict(d) for d in items]


def load_dirs(builtin: Path, user_dir: Path | None = None) -> dict[str, Preset]:
    """Built-in presets first; any ``*.json`` in ``user_dir`` overrides by id."""
    out: dict[str, Preset] = {}
    for p in load_file(builtin):
        out[p.id] = p
    if user_dir and Path(user_dir).is_dir():
        for f in sorted(Path(user_dir).glob("*.json")):
            try:
                for p in load_file(f):
                    out[p.id] = p
            except Exception as exc:  # a broken user file must never break the add-on
                print(f"[RainFX] skipped user preset file {f.name}: {exc}")
    return out


def dump(presets: Iterable[Preset]) -> str:
    return json.dumps({"schema": 1, "presets": [asdict(p) for p in presets]}, indent=2)


def ripple_weight_for(p: Preset) -> float:
    """Puddle ring-ripple intensity 0..1 for a preset (rain only)."""
    return P.ripple_weight(p.rate_mm_h) if p.mode == "rain" else 0.0


# --- ambient wetness -------------------------------------------------------
# The simulation only carries a thinned-out sample of the drops, and only inside
# its volume, so its hits alone leave most of a real scene dry. In rain every
# surface the rain can reach is wet; these give that ambient level per preset.

def ambient_wet_for(p: Preset) -> float:
    """Wetness (0-1) of every exposed surface while this preset falls."""
    if p.mode == "rain":
        rate = max(p.rate_mm_h, 0.0)
        return min(1.0, 0.6 + 0.4 * (rate / 10.0) ** 0.5)   # drizzle ~0.7, 10 mm/h and up soaked
    if p.mode == "hail":
        return 0.8 if p.material == "ice" else 0.9           # hailstones melt; sleet is mostly water
    return 0.0                                               # snow and dew: their own surfaces


def ambient_pool_for(p: Preset) -> float:
    """Standing-water level (0-0.7) on exposed flat ground; the shader floods its low spots."""
    if p.mode != "rain":
        return 0.15 if p.mode == "hail" else 0.0
    import math
    return min(0.7, 0.25 * math.log2(1.0 + max(p.rate_mm_h, 0.0) / 2.5))


def ambient_snow_for(p: Preset) -> float:
    """Snow cover (0-1 of Snow Depth) on exposed up-facing ground while a snow preset falls.

    Snow presets carry no snowfall rate, so cover follows their flake density
    (light snow ~0.57, heavy and blizzard 1).
    """
    if p.mode != "snow":                # hail is wet ground (a layer of stones is not modelled)
        return 0.0
    return min(1.0, 0.35 + 0.012 * p.visual_density)


def wet_up_time_for(p: Preset) -> float:
    """Seconds for dry ground to wet up when the shot starts dry (heavier rain is faster)."""
    rate = max(p.rate_mm_h, 0.1) if p.mode == "rain" else 5.0
    return min(120.0, max(10.0, 120.0 / rate ** 0.5))


def rain_direction_for(p: Preset, wind_mult: float = 1.0) -> tuple[float, float, float]:
    """Unit vector toward where the rain comes from: up, and into the wind (x the panel's Wind)."""
    d = derive(p, quality=0.01)
    wx, wy, _ = (c * wind_mult for c in d.get("wind_vec", (0.0, 0.0, 0.0)))
    vt = max(d.get("vt_mean_ms", 5.0), 0.1)
    n = (wx * wx + wy * wy + vt * vt) ** 0.5
    return (-wx / n, -wy / n, vt / n)
