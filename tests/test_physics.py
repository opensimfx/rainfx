import pytest

from rainfx.core import physics as P


@pytest.mark.parametrize("d,v", [(1.0, 4.03), (2.0, 6.49), (3.0, 8.06), (4.0, 8.83), (5.0, 9.09)])
def test_gunn_kinzer_reference_points(d, v):
    assert P.rain_terminal_velocity(d) == pytest.approx(v, rel=0.03)


def test_monotonic_and_continuous():
    prev = 0.0
    for i in range(1, 80):
        v = P.rain_terminal_velocity(i * 0.1)
        assert v >= prev - 0.05
        prev = v
    assert abs(P.rain_terminal_velocity(0.4999) - P.rain_terminal_velocity(0.5001)) < 0.25


def test_hail_matches_nssl_bands():
    assert 4 <= P.hail_terminal_velocity(10) <= 11      # under 1 in: 9-25 mph
    assert P.hail_terminal_velocity(40) < 25             # 1.6 in: 25-40 mph band, tolerance


def test_marshall_palmer_lambda_and_density():
    assert P.mp_lambda(1.0) == pytest.approx(4.1)
    assert P.mp_lambda(10.0) == pytest.approx(2.53, rel=0.01)
    assert P.physical_number_density(10.0) == pytest.approx(3162, rel=0.01)


def test_truncated_sampler_bounds_and_mean():
    lam, lo, hi = 2.5, 0.3, 5.0
    xs = [P.sample_truncated_exponential(i / 1000, lam, lo, hi) for i in range(1000)]
    assert min(xs) >= lo and max(xs) <= hi + 1e-9
    assert lo < P.mean_drop_diameter(lam, lo, hi) < 1.0


def test_wind_vector_axes():
    x, y, z = P.wind_vector(10, 90)
    assert x == pytest.approx(10) and y == pytest.approx(0, abs=1e-9) and z == 0


def test_relaxation_time_positive():
    assert P.relaxation_time(9.0) == pytest.approx(0.9177, rel=1e-3)
    assert P.relaxation_time(0.0) > 0


def test_rain_extinction_matches_observed_visibility():
    # 10 mm/h: observed visibility 1-3 km (Gultepe); Koschmieder V = 3/beta
    beta = P.rain_extinction_per_m(10.0)
    assert 1000 < 3.0 / beta < 3000
    assert P.rain_extinction_per_m(0.0) == 0.0
    # heavier rain is more veiled, sub-linearly
    r = P.rain_extinction_per_m(20.0) / P.rain_extinction_per_m(1.5)
    assert r == pytest.approx((20 / 1.5) ** 0.67)


def test_glare_grows_with_rate_and_caps():
    vals = [P.rain_glare_strength(r) for r in (0.5, 1.5, 5, 20, 60, 500)]
    assert vals == sorted(vals)
    assert vals[-1] == pytest.approx(0.6)
    assert 0.2 < P.rain_glare_strength(1.5) < 0.25


@pytest.mark.parametrize("rough,metal,por", [(0.2, 0.0, 0.0), (0.9, 0.0, 1.0), (0.7, 0.0, 0.5), (0.9, 1.0, 0.0)])
def test_wet_porosity(rough, metal, por):
    assert P.wet_porosity(rough, metal) == pytest.approx(por)


def test_wet_albedo_factor_lagarde():
    assert P.wet_albedo_factor(0.0) == 1.0     # metal / plastic: no darkening
    assert P.wet_albedo_factor(1.0) == pytest.approx(0.2)


def test_backlight_sits_behind_rain_and_points_at_camera():
    cam, target = (0.0, -20.0, 1.7), (0.0, 0.0, 3.0)
    loc, aim, beam = P.backlight_placement(cam, target, distance=15.0)
    assert loc[1] > target[1]                  # beyond the rain, seen from the camera
    assert loc[2] > aim[2]                     # above, shining down
    to_cam = tuple(c - a for c, a in zip(cam, aim))
    ang = P.angle_between_deg(beam, to_cam)
    assert 20 < ang < 50                       # back-lit but off the lens axis
    # distance is honoured
    assert sum((l - a) ** 2 for l, a in zip(loc, aim)) ** 0.5 == pytest.approx(15.0)


def test_splash_k_matches_worked_values():
    # Yarin's K = We Oh^-2/5 for water drops at terminal speed (research table)
    k = {d: P.splash_k(d, P.rain_terminal_velocity(d)) for d in (0.3, 1.0, 2.0, 4.0)}
    assert k[0.3] == pytest.approx(35, rel=0.1)
    assert k[1.0] == pytest.approx(2100, rel=0.05)
    assert k[2.0] == pytest.approx(12800, rel=0.03)
    assert k[4.0] == pytest.approx(52000, rel=0.05)
    assert P.splash_k(0.0, 5.0) == 0.0 and P.splash_k(2.0, 0.0) == 0.0


def test_splash_threshold_film():
    assert P.splash_threshold(0.0) == P.SPLASH_K_THIN_FILM
    assert P.splash_threshold(0.5) == pytest.approx(2100 + 5880 * 0.5 ** 1.44)
    assert P.splash_threshold(1.0) > P.splash_threshold(0.1)


def test_splash_droplets_per_drop():
    vt = P.rain_terminal_velocity
    mean = lambda d: P.splash_droplet_mean(P.splash_k(d, vt(d)), 2)  # noqa: E731
    assert mean(0.3) == 0.0 and mean(0.8) == 0.0          # drizzle never splashes
    assert mean(2.0) == pytest.approx(2.0, rel=1e-6)      # the reference drop throws "amount"
    assert 0 < mean(1.5) < mean(2.0) < mean(3.0) < mean(5.5) <= 4.0
    assert P.splash_droplet_mean(P.splash_k(2.0, vt(2.0)), 0) == 0.0
    # a thicker film raises the threshold: fewer droplets from the same drop
    k = P.splash_k(1.5, vt(1.5))
    assert P.splash_droplet_mean(k, 2, P.splash_threshold(0.5)) < P.splash_droplet_mean(k, 2)


def test_splash_speed_factor():
    vt = P.rain_terminal_velocity
    assert P.splash_speed_factor(P.SPLASH_K_REF) == pytest.approx(1.0)
    assert P.splash_speed_factor(P.splash_k(4.0, vt(4.0))) > 1.0
    assert P.splash_speed_factor(1.0) == 0.5 and P.splash_speed_factor(1e12) == 2.0


def test_crown_radius_sqrt_time():
    r1 = P.crown_radius(2.0, 6.5, 0.01)
    r4 = P.crown_radius(2.0, 6.5, 0.04)
    assert r4 == pytest.approx(2 * r1)                    # R ~ sqrt(t)
    assert 0.008 < r4 < 0.015                             # ~1 cm at 40 ms
    assert P.crown_radius(2.0, 6.5, 0.0) == 0.0


def test_ripple_weight_and_spray_ramp():
    assert P.ripple_weight(0) == 0.0
    assert P.ripple_weight(1.5) < P.ripple_weight(20) < P.ripple_weight(50) == 1.0
    assert P.spray_mist_factor(5) == 0.0 and P.spray_mist_factor(40) == 1.0
    assert 0 < P.spray_mist_factor(20) < 1


def test_effective_visual_scale_true_size_near_camera():
    assert P.effective_visual_scale(0.5, 4.0) == 1.0          # passing the lens: true width
    assert P.effective_visual_scale(4.0, 4.0) == 2.0          # grows with distance
    assert P.effective_visual_scale(30.0, 4.0) == 4.0         # capped at Visual Scale
    assert P.effective_visual_scale(30.0, 0.5) == 0.5         # a user scale below 1 is kept


def test_drips():
    assert 2.6e-3 < P.capillary_length_m() < 2.8e-3          # water: ~2.7 mm
    assert 1.5 < P.DRIP_D_MM / (P.capillary_length_m() * 1000) < 2.2
    assert P.drip_period_s(25.0) < P.drip_period_s(5.0) < P.drip_period_s(0.5) <= 4.0
    assert P.drip_period_s(1000.0) == 0.25
    s, v = P.drip_fall(0.2, 9.0)                              # free fall: 0.5 g t^2
    assert abs(s - 0.5 * P.G * 0.04) < 1e-9 and abs(v - P.G * 0.2) < 1e-9
    s2, v2 = P.drip_fall(3.0, 9.0)                            # capped at terminal speed
    assert v2 == 9.0 and s2 < 0.5 * P.G * 9.0
    t_v = 9.0 / P.G
    assert abs(P.drip_fall(t_v, 9.0)[0] - P.drip_fall(t_v + 1e-9, 9.0)[0]) < 1e-6   # continuous
