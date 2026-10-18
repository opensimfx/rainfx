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
    splash_amount: int = 2            # splash droplets spawned per impact
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
    fog_density: float = 0.004        # 1/m
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
