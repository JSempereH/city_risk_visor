from app.hazard.atc40 import capacity_sa_at_sd, compute_performance_point
from app.hazard.spectrum import build_demand_spectrum
from app.vulnerability.spectral import BilinearCapacity

BILINEAR = BilinearCapacity(sdy_mm=8.0, say_g=0.15, sdu_mm=40.0, sau_g=0.15)


def test_capacity_curve_shape():
    assert capacity_sa_at_sd(0.0, BILINEAR) == BILINEAR.say_g
    assert capacity_sa_at_sd(4.0, BILINEAR) == BILINEAR.say_g * 0.5  # elastic ramp midpoint
    assert capacity_sa_at_sd(8.0, BILINEAR) == BILINEAR.say_g
    assert capacity_sa_at_sd(20.0, BILINEAR) == BILINEAR.say_g  # plateau
    assert capacity_sa_at_sd(40.0, BILINEAR) == BILINEAR.say_g  # exactly at ultimate
    assert capacity_sa_at_sd(41.0, BILINEAR) == 0.0  # beyond ultimate: no reliable capacity


def test_weak_shaking_stays_elastic():
    spectrum = build_demand_spectrum(6.0, 60.0, 15.0, "crustal", 280.0, rake=0.0, ztor_km=None)
    pp = compute_performance_point(BILINEAR, spectrum)
    assert pp.ductility < 1.0
    assert pp.effective_damping_pct == 5.0
    assert pp.converged


def test_strong_shaking_yields_but_stays_bounded_by_ultimate_point():
    # Regression test: capacity_sa_at_sd used to have no cutoff beyond
    # sdu, so a long-period demand tail with even a tiny Sa could
    # "intersect" the infinite plateau at an arbitrarily large,
    # physically meaningless Sd (this produced displacements of hundreds
    # of mm and ductilities over 100 for a building whose real ultimate
    # displacement was 40mm). The performance point must never exceed the
    # capacity curve's own ultimate displacement.
    spectrum = build_demand_spectrum(8.5, 5.0, 15.0, "crustal", 200.0, rake=0.0, ztor_km=None)
    pp = compute_performance_point(BILINEAR, spectrum)
    assert pp.sd_mm <= BILINEAR.sdu_mm + 1e-6
    assert pp.ductility <= BILINEAR.sdu_mm / BILINEAR.sdy_mm + 1e-6


def test_more_severe_demand_increases_or_maintains_ductility():
    moderate = build_demand_spectrum(7.0, 40.0, 15.0, "crustal", 280.0, rake=0.0, ztor_km=None)
    severe = build_demand_spectrum(7.5, 10.0, 15.0, "crustal", 280.0, rake=0.0, ztor_km=None)
    pp_moderate = compute_performance_point(BILINEAR, moderate)
    pp_severe = compute_performance_point(BILINEAR, severe)
    assert pp_severe.ductility >= pp_moderate.ductility


def test_effective_damping_never_exceeds_cap():
    spectrum = build_demand_spectrum(9.0, 2.0, 10.0, "crustal", 150.0, rake=0.0, ztor_km=None)
    pp = compute_performance_point(BILINEAR, spectrum)
    assert 5.0 <= pp.effective_damping_pct <= 40.0
