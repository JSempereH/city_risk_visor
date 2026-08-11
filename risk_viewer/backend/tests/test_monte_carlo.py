import pytest

from app.risk.monte_carlo import BuildingMonteCarloInput, run_scenario_monte_carlo
from app.vulnerability.fragility import build_fragility_curves


def _make_curves(scale: float = 1.0):
    medians = {
        "slight": 5.0 * scale,
        "moderate": 10.0 * scale,
        "extensive": 20.0 * scale,
        "complete": 40.0 * scale,
    }
    return build_fragility_curves(medians, beta=0.7)


def test_percentile_bands_are_ordered():
    building = BuildingMonteCarloInput(
        fragility_curves=_make_curves(),
        median_sd_mm=15.0,
        sigma_ln=0.6,
        building_type="C1L",
        population_day=100.0,
        population_night=250.0,
    )
    summary = run_scenario_monte_carlo([(building, 0.0, 0.0)], n_samples=200)
    for band in (
        summary.casualties_day,
        summary.casualties_night,
        summary.fatalities_day,
        summary.fatalities_night,
    ):
        assert band.p10 <= band.p50 <= band.p90
        assert band.mean >= 0

    assert summary.n_buildings == 1
    assert summary.n_samples == 200


def test_deterministic_given_seed():
    building = BuildingMonteCarloInput(
        fragility_curves=_make_curves(),
        median_sd_mm=15.0,
        sigma_ln=0.6,
        building_type="W1",
        population_day=50.0,
        population_night=120.0,
    )
    a = run_scenario_monte_carlo([(building, 0.0, 0.0)], n_samples=150, seed=7)
    b = run_scenario_monte_carlo([(building, 0.0, 0.0)], n_samples=150, seed=7)
    assert a.casualties_night.p50 == b.casualties_night.p50


def test_higher_demand_increases_expected_casualties():
    low = BuildingMonteCarloInput(
        fragility_curves=_make_curves(),
        median_sd_mm=5.0,
        sigma_ln=0.6,
        building_type="C1L",
        population_day=100.0,
        population_night=100.0,
    )
    high = BuildingMonteCarloInput(
        fragility_curves=_make_curves(),
        median_sd_mm=60.0,
        sigma_ln=0.6,
        building_type="C1L",
        population_day=100.0,
        population_night=100.0,
    )
    low_summary = run_scenario_monte_carlo([(low, 0.0, 0.0)], n_samples=300)
    high_summary = run_scenario_monte_carlo([(high, 0.0, 0.0)], n_samples=300)
    assert high_summary.casualties_night.mean > low_summary.casualties_night.mean


def test_typology_disagreement_widens_the_band():
    certain = BuildingMonteCarloInput(
        fragility_curves=_make_curves(),
        median_sd_mm=15.0,
        sigma_ln=0.6,
        building_type="C1L",
        population_day=100.0,
        population_night=250.0,
    )
    summary_certain = run_scenario_monte_carlo([(certain, 0.0, 0.0)], n_samples=400, seed=1)
    summary_contested = run_scenario_monte_carlo([(certain, 0.5, 0.0)], n_samples=400, seed=1)
    width_certain = summary_certain.casualties_night.p90 - summary_certain.casualties_night.p10
    width_contested = summary_contested.casualties_night.p90 - summary_contested.casualties_night.p10
    assert width_contested >= width_certain


def test_capacity_curve_uncertainty_widens_the_band():
    # capacity_beta (the GPR capacity-curve model's own predictive
    # uncertainty, ML tier only) must widen the sampled demand the same
    # way typology_beta does above: it's included in the point-estimate
    # quadrature (uncertainty.py), so leaving it out here would make the
    # Monte Carlo band and that combined beta draw on different sets of
    # uncertainty sources for the same building.
    certain = BuildingMonteCarloInput(
        fragility_curves=_make_curves(),
        median_sd_mm=15.0,
        sigma_ln=0.6,
        building_type="C1L",
        population_day=100.0,
        population_night=250.0,
    )
    summary_certain = run_scenario_monte_carlo([(certain, 0.0, 0.0)], n_samples=400, seed=1)
    summary_uncertain_capacity = run_scenario_monte_carlo([(certain, 0.0, 0.5)], n_samples=400, seed=1)
    width_certain = summary_certain.casualties_night.p90 - summary_certain.casualties_night.p10
    width_uncertain_capacity = (
        summary_uncertain_capacity.casualties_night.p90 - summary_uncertain_capacity.casualties_night.p10
    )
    assert width_uncertain_capacity >= width_certain


def test_city_total_sums_multiple_buildings():
    a = BuildingMonteCarloInput(
        fragility_curves=_make_curves(),
        median_sd_mm=15.0,
        sigma_ln=0.6,
        building_type="C1L",
        population_day=100.0,
        population_night=100.0,
    )
    b = BuildingMonteCarloInput(
        fragility_curves=_make_curves(),
        median_sd_mm=15.0,
        sigma_ln=0.6,
        building_type="C1L",
        population_day=100.0,
        population_night=100.0,
    )
    one = run_scenario_monte_carlo([(a, 0.0, 0.0)], n_samples=500, seed=3)
    two = run_scenario_monte_carlo([(a, 0.0, 0.0), (b, 0.0, 0.0)], n_samples=500, seed=3)
    # Two identical independent buildings: the combined mean should be
    # roughly double one building's (not exactly, since it's a fresh RNG
    # stream position for the second building, not literally 2x the same
    # draw), well within a generous tolerance.
    assert two.casualties_night.mean == pytest.approx(one.casualties_night.mean * 2, rel=0.3)
