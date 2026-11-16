import json
from pathlib import Path

import pytest

from rainfx.core import presets as PR

DATA = Path(__file__).resolve().parents[1] / "rainfx" / "data" / "presets.json"


def test_all_builtin_presets_valid_and_unique():
    ps = PR.load_file(DATA)
    ids = [p.id for p in ps]
    assert len(ids) == len(set(ids)) == 14
    for required in ("dew", "light_rain", "heavy_rain", "thunderstorm", "hailstorm", "light_snow"):
        assert required in ids


def test_rain_intensity_ordering():
    ps = {p.id: p for p in PR.load_file(DATA)}
    order = ["drizzle", "light_rain", "moderate_rain", "heavy_rain", "downpour"]
    rates = [ps[i].rate_mm_h for i in order]
    assert rates == sorted(rates)
    speeds = [PR.derive(ps[i])["vt_mean_ms"] for i in order]
    assert speeds == sorted(speeds), "heavier rain has larger drops, so falls faster"
    # drizzle is many tiny drops: its simulated count may exceed light rain by design


def test_derive_is_physical():
    ps = {p.id: p for p in PR.load_file(DATA)}
    d = PR.derive(ps["heavy_rain"])
    assert 3.0 < d["vt_mean_ms"] < 5.0
    assert d["tilt_deg"] == pytest.approx(46, abs=3)
    assert d["density_ratio"] < 0.05, "simulation must be far sparser than physical density"
    h = PR.derive(ps["hailstorm"])
    assert h["vt_mean_ms"] > d["vt_mean_ms"], "hail falls faster than rain"
    s = PR.derive(ps["light_snow"])
    assert s["vt_mean_ms"] < 2.0, "snow falls slowly"


def test_quality_and_cap():
    p = next(x for x in PR.load_file(DATA) if x.id == "downpour")
    assert PR.derive(p, quality=0.5)["count"] < PR.derive(p, quality=1.0)["count"]
    assert PR.derive(p, quality=100.0, max_count=1000)["count"] == 1000


@pytest.mark.parametrize("bad", [
    {"id": "x", "name": "x", "mode": "plasma"},
    {"id": "x", "name": "x", "d_min_mm": 5, "d_max_mm": 1},
    {"id": "x", "name": "x", "restitution": 1.5},
    {"id": "x", "name": "x", "splash_life_min": 2, "splash_life_max": 1},
])
def test_validation_rejects_bad_presets(bad):
    with pytest.raises(ValueError):
        PR.from_dict(bad)


def test_user_override_and_broken_file(tmp_path):
    (tmp_path / "mine.json").write_text(json.dumps(
        {"presets": [{"id": "heavy_rain", "name": "Mine", "rate_mm_h": 99},
                     {"id": "brand_new", "name": "New", "rate_mm_h": 3}]}))
    (tmp_path / "broken.json").write_text("{ not json")
    out = PR.load_dirs(DATA, tmp_path)
    assert out["heavy_rain"].name == "Mine" and out["heavy_rain"].rate_mm_h == 99
    assert "brand_new" in out and "light_rain" in out


def test_unknown_keys_ignored():
    p = PR.from_dict({"id": "x", "name": "x", "future_field": 1})
    assert p.id == "x"


def test_rain_fog_follows_rate():
    ps = {p.id: p for p in PR.load_file(DATA)}
    order = ["light_rain", "moderate_rain", "heavy_rain", "downpour"]
    fogs = [PR.fog_density_for(ps[i]) for i in order]
    assert fogs == sorted(fogs)
    # heavy vs light keeps the measured extinction ratio (R^0.67), not a hand-picked one
    assert fogs[2] / fogs[0] == pytest.approx((20 / 1.5) ** 0.67, rel=1e-6)
    # the stored fallback value agrees with the derived one (JSON stays readable)
    for i in order:
        assert ps[i].fog_density == pytest.approx(PR.fog_density_for(ps[i]), abs=1e-4)
    # changing the rate of a rain preset moves its fog
    wetter = PR.from_dict({**PR.asdict(ps["light_rain"]), "rate_mm_h": 15.0})
    assert PR.fog_density_for(wetter) > PR.fog_density_for(ps["light_rain"])


def test_fog_mist_zero_keeps_hand_value():
    ps = {p.id: p for p in PR.load_file(DATA)}
    for i in ("drizzle", "light_snow", "hailstorm", "dew"):
        assert ps[i].fog_mist == 0.0
        assert PR.fog_density_for(ps[i]) == ps[i].fog_density
    old_user = PR.from_dict({"id": "mine", "name": "Mine", "rate_mm_h": 30, "fog_density": 0.002})
    assert PR.fog_density_for(old_user) == 0.002


def test_glare_follows_rate():
    ps = {p.id: p for p in PR.load_file(DATA)}
    assert PR.glare_strength_for(ps["downpour"]) > PR.glare_strength_for(ps["light_rain"])
    assert PR.glare_strength_for(ps["light_snow"]) == pytest.approx(0.15)


def test_spray_mist_only_in_heavy_rain():
    ps = {p.id: p for p in PR.load_file(DATA)}
    assert PR.spray_density_for(ps["light_rain"]) == 0.0
    assert PR.spray_density_for(ps["moderate_rain"]) == 0.0
    assert 0 < PR.spray_density_for(ps["heavy_rain"]) < PR.spray_density_for(ps["downpour"])
    for i in ("drizzle", "light_snow", "hailstorm", "dew"):
        assert PR.spray_density_for(ps[i]) == 0.0


def test_ripple_weight_follows_rate():
    ps = {p.id: p for p in PR.load_file(DATA)}
    assert PR.ripple_weight_for(ps["light_rain"]) < PR.ripple_weight_for(ps["downpour"]) == 1.0
    assert PR.ripple_weight_for(ps["light_snow"]) == 0.0


def test_ambient_wetness_follows_rain_rate_and_mode():
    ps = {p.id: p for p in PR.load_file(DATA)}
    dr, hv, sn = ps["drizzle"], ps["heavy_rain"], ps["light_snow"]
    assert 0.6 < PR.ambient_wet_for(dr) < PR.ambient_wet_for(hv) <= 1.0
    assert PR.ambient_wet_for(sn) == 0.0 and PR.ambient_pool_for(sn) == 0.0
    assert PR.ambient_pool_for(dr) < PR.ambient_pool_for(hv) <= 0.7
    assert PR.wet_up_time_for(hv) < PR.wet_up_time_for(dr) <= 120.0


def test_rain_direction_points_up_and_into_the_wind():
    ps = {p.id: p for p in PR.load_file(DATA)}
    x, y, z = PR.rain_direction_for(ps["wind_driven_rain"])
    assert abs(x * x + y * y + z * z - 1.0) < 1e-6 and z > 0
    wx, wy, _ = PR.derive(ps["wind_driven_rain"])["wind_vec"]
    assert x * wx + y * wy < 0            # against the wind: rain arrives from upwind
    calm = PR.Preset(**{**PR.asdict(ps["heavy_rain"]), "wind_ms": 0.0})
    assert PR.rain_direction_for(calm)[2] > 0.999            # still air: straight down
    # slow drizzle drops lean far more in the same breeze than fast heavy drops
    assert PR.rain_direction_for(ps["drizzle"])[2] < PR.rain_direction_for(calm)[2]


def test_ambient_snow_only_for_snow_and_grows_with_density():
    ps = {p.id: p for p in PR.load_file(DATA)}
    assert PR.ambient_snow_for(ps["heavy_rain"]) == 0.0
    assert PR.ambient_snow_for(ps["hailstorm"]) == 0.0 and PR.ambient_snow_for(ps["dew"]) == 0.0
    assert 0.0 < PR.ambient_snow_for(ps["light_snow"]) < PR.ambient_snow_for(ps["heavy_snow"]) \
        <= PR.ambient_snow_for(ps["blizzard"]) <= 1.0
