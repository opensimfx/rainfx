"""Regenerates rainfx/data/presets.json from the table below.
Run:  python tools/gen_presets.py
Rain rate categories follow the WMO scheme (light <=2.5, moderate 2.5-7.5, heavy 7.6-50, violent >50 mm/h).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rainfx.core.presets import from_dict, dump

T = [
 dict(id="dew", name="Dew", category="surface", mode="dew",
      description="Static condensation beads on upward-facing collider surfaces. No falling particles.",
      d_min_mm=0.4, d_max_mm=2.2, dew_density_m2=350, visual_scale=1.0, material="water",
      fog_density=0.0008, sky_mult=0.9, sun_mult=0.7, wind_ms=0, shutter_s=0, rate_mm_h=0),
 dict(id="drizzle", name="Drizzle", mode="rain", description="Fine, slow drops under 0.5 mm; almost no splash.",
      rate_mm_h=0.5, d_min_mm=0.15, d_max_mm=0.5, visual_density=22, wind_ms=1.0, wind_dir_deg=60, gust_strength=0.6,
      splash_amount=0, visual_scale=5.0, fog_density=0.006, sky_mult=0.65, sun_mult=0.15),
 dict(id="light_rain", name="Light Rain", mode="rain", description="Up to 2.5 mm/h. Sparse medium drops, soft splashes.",
      rate_mm_h=1.5, d_min_mm=0.3, d_max_mm=2.5, visual_density=7, wind_ms=1.5, wind_dir_deg=60, gust_strength=0.8,
      splash_amount=1, splash_speed=0.8, fog_density=0.004, sky_mult=0.7, sun_mult=0.25),
 dict(id="moderate_rain", name="Moderate Rain", mode="rain", description="2.5-7.5 mm/h. Steady rain with visible ground splashes.",
      rate_mm_h=5, d_min_mm=0.4, d_max_mm=3.5, visual_density=16, wind_ms=2.5, wind_dir_deg=60, gust_strength=1.2,
      splash_amount=2, fog_density=0.006, sky_mult=0.6, sun_mult=0.15),
 dict(id="heavy_rain", name="Heavy Rain", mode="rain", description="7.6-50 mm/h. Dense curtain, strong splash crowns.",
      rate_mm_h=20, d_min_mm=0.5, d_max_mm=4.5, visual_density=30, wind_ms=4.0, wind_dir_deg=60, gust_strength=2.0,
      splash_amount=3, splash_speed=1.5, visual_scale=4.0, fog_density=0.012, sky_mult=0.45, sun_mult=0.05, legacy_drag=0.0),
 dict(id="downpour", name="Downpour (Violent)", mode="rain", description="Over 50 mm/h. Cloudburst, near-zero visibility.",
      rate_mm_h=60, d_min_mm=0.6, d_max_mm=5.5, visual_density=48, wind_ms=6.0, wind_dir_deg=60, gust_strength=3.0,
      splash_amount=3, splash_speed=1.8, visual_scale=3.5, fog_density=0.03, sky_mult=0.3, sun_mult=0.0),
 dict(id="wind_driven_rain", name="Wind-Driven Rain", mode="rain", description="Strong horizontal wind, heavily slanted streaks, gusting.",
      rate_mm_h=15, d_min_mm=0.4, d_max_mm=4.0, visual_density=28, wind_ms=14, wind_dir_deg=75, gust_strength=6.0, gust_scale_m=8, gust_speed_ms=4,
      splash_amount=2, inertia=0.8, fog_density=0.015, sky_mult=0.4, sun_mult=0.05),
 dict(id="thunderstorm", name="Thunderstorm", mode="rain", description="Violent rain, large drops, gusts and lightning flashes.",
      rate_mm_h=45, d_min_mm=0.6, d_max_mm=5.5, visual_density=42, wind_ms=9, wind_dir_deg=70, gust_strength=5.0, gust_scale_m=9, gust_speed_ms=3.5,
      splash_amount=3, splash_speed=1.8, fog_density=0.02, sky_mult=0.2, sun_mult=0.0, lightning_per_min=5, lightning_energy=250000),
 dict(id="freezing_rain", name="Freezing Rain", mode="rain", description="Supercooled drops that freeze on contact; little splash, icy look.",
      rate_mm_h=3, d_min_mm=0.3, d_max_mm=2.0, visual_density=9, wind_ms=2, wind_dir_deg=40, gust_strength=0.8,
      splash_amount=0, material="ice", fog_density=0.004, sky_mult=0.7, sun_mult=0.2),
 dict(id="sleet", name="Sleet (Ice Pellets)", category="frozen", mode="hail", description="Small ice pellets that bounce a little; 1.5-4 mm.",
      d_min_mm=1.5, d_max_mm=4.0, lam_override=0.5, speed_scale=0.75, visual_density=14, wind_ms=3, wind_dir_deg=50, gust_strength=1.5,
      restitution=0.35, max_bounces=2, splash_amount=0, shutter_s=1/96, visual_scale=3.0, material="ice", fog_density=0.005, sky_mult=0.65, sun_mult=0.1,
      col_damping=0.35, col_friction=0.3),
 dict(id="hailstorm", name="Hailstorm", category="frozen", mode="hail", description="5-35 mm hail. Fast, sparse, bounces off surfaces.",
      d_min_mm=5, d_max_mm=35, lam_override=0.12, speed_scale=1.0, visual_density=1.6, wind_ms=8, wind_dir_deg=70, gust_strength=3.0,
      restitution=0.5, max_bounces=3, splash_amount=0, shutter_s=1/96, visual_scale=1.5, material="ice", fog_density=0.008, sky_mult=0.3, sun_mult=0.0,
      lightning_per_min=3, lightning_energy=200000, col_damping=0.4, col_friction=0.25),
 dict(id="light_snow", name="Light Snow", category="frozen", mode="snow", description="Slow large flakes with gentle flutter.",
      d_min_mm=3, d_max_mm=8, lam_override=0.3, snow_speed_ms=0.9, visual_density=10, wind_ms=1.0, wind_dir_deg=45, gust_strength=1.2, gust_scale_m=2.5, gust_speed_ms=1.0,
      inertia=2.5, splash_amount=0, shutter_s=0, visual_scale=3.0, material="snow", fog_density=0.004, sky_mult=0.9, sun_mult=0.3,
      col_stickiness=1.0, col_damping=1.0),
 dict(id="heavy_snow", name="Heavy Snow", category="frozen", mode="snow", description="Dense snowfall, reduced visibility.",
      d_min_mm=3, d_max_mm=9, lam_override=0.3, snow_speed_ms=1.2, visual_density=26, wind_ms=3, wind_dir_deg=45, gust_strength=2.2, gust_scale_m=3, gust_speed_ms=1.5,
      inertia=2.0, splash_amount=0, shutter_s=0, visual_scale=3.0, material="snow", fog_density=0.015, sky_mult=0.85, sun_mult=0.1,
      col_stickiness=1.0, col_damping=1.0),
 dict(id="blizzard", name="Blizzard", category="frozen", mode="snow", description="Wind-dominated snow, near-horizontal drift, whiteout fog.",
      d_min_mm=2, d_max_mm=7, lam_override=0.35, snow_speed_ms=1.3, visual_density=38, wind_ms=15, wind_dir_deg=80, gust_strength=7.0, gust_scale_m=6, gust_speed_ms=4,
      inertia=1.5, splash_amount=0, shutter_s=1/96, visual_scale=3.0, material="snow", fog_density=0.04, sky_mult=0.9, sun_mult=0.0,
      col_stickiness=1.0, col_damping=1.0),
]
presets = [from_dict(d) for d in T]
out = Path(__file__).resolve().parents[1] / "rainfx" / "data" / "presets.json"
out.write_text(dump(presets), encoding="utf-8")
print("wrote", out, len(presets), "presets")
