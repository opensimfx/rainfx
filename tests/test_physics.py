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
