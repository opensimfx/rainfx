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
