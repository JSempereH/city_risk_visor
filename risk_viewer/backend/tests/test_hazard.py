from app.hazard.ground_motion import building_period_s, compute_demand, haversine_km
from app.hazard.gmpe import ground_motion_at_period, median_pga_g
from app.hazard.scenario import get_scenario
from app.hazard.site import default_vs30, vs30_at
from app.risk.damage import compute_damage_distribution
from app.vulnerability.fragility import DAMAGE_STATES, build_fragility_curves


def test_pga_increases_with_magnitude():
    pga_m6 = median_pga_g(6.0, 25.0, 15.0, "crustal", vs30=280.0)
    pga_m7 = median_pga_g(7.0, 25.0, 15.0, "crustal", vs30=280.0)
    assert pga_m7 > pga_m6


def test_pga_decreases_with_distance():
    near = median_pga_g(7.0, 10.0, 15.0, "crustal", vs30=280.0)
    far = median_pga_g(7.0, 100.0, 15.0, "crustal", vs30=280.0)
    assert near > far > 0


def test_pga_positive_for_interface_regime():
    # Exercises the Zhao et al. (2016) SInter GMPE with a shallow ztor,
    # distinct from the (deeper) hypocentral depth_km. See scenario.py.
    pga = median_pga_g(7.5, 75.0, 25.0, "interface", vs30=300.0, ztor_km=15.0)
    assert pga > 0


def test_softer_soil_amplifies_more():
    stiff = ground_motion_at_period(7.0, 25.0, 15.0, "crustal", 0.2, vs30=600.0)
    soft = ground_motion_at_period(7.0, 25.0, 15.0, "crustal", 0.2, vs30=200.0)
    assert soft.median_sa_g > stiff.median_sa_g


def test_haversine_zero_distance():
    assert haversine_km(14.6, -90.5, 14.6, -90.5) == 0


def test_haversine_known_order_of_magnitude():
    # Guatemala City centre to the scenario epicenter, ~25 km by design.
    km = haversine_km(14.6349, -90.5069, 14.794, -90.342)
    assert 15 < km < 35


def test_building_period_scales_with_floors():
    assert building_period_s(1) < building_period_s(5)


def test_compute_demand_guatemala():
    scenario = get_scenario("guatemala")
    assert scenario is not None
    demand = compute_demand(scenario, 14.6349, -90.5069, 3)
    assert demand.distance_km > 0
    assert demand.sa_g > 0
    assert demand.sd_mm > 0
    assert demand.sigma_ln > 0  # real GMPE sigma, regime/period-dependent (not a flat constant)


def test_default_vs30_known_cities():
    assert default_vs30("guatemala") > 0
    assert default_vs30("nonexistent_city") > 0  # falls back to a default


def test_vs30_at_varies_within_a_city():
    # Real grid values, not a flat per-city constant: two points a few
    # hundred metres apart in Guatemala City sit on different grid cells.
    a = vs30_at("guatemala", 14.64, -90.51)
    b = vs30_at("guatemala", 14.60, -90.55)
    assert a > 0 and b > 0
    assert a != b


def test_vs30_at_falls_back_for_unknown_city():
    assert vs30_at("nonexistent_city", 0.0, 0.0) > 0


def test_damage_distribution_sums_to_one():
    medians = {"slight": 5.0, "moderate": 10.0, "extensive": 20.0, "complete": 40.0}
    curves = build_fragility_curves(medians, beta=0.7)
    dist = compute_damage_distribution(curves, demand_sd_mm=15.0)
    assert abs(sum(dist.state_probability.values()) - 1.0) < 1e-9
    assert set(dist.state_probability.keys()) == {"none", *DAMAGE_STATES}


def test_damage_distribution_high_demand_favours_complete():
    medians = {"slight": 5.0, "moderate": 10.0, "extensive": 20.0, "complete": 40.0}
    curves = build_fragility_curves(medians, beta=0.7)
    low_demand = compute_damage_distribution(curves, demand_sd_mm=1.0)
    high_demand = compute_damage_distribution(curves, demand_sd_mm=200.0)
    assert low_demand.state_probability["none"] > high_demand.state_probability["none"]
    assert high_demand.state_probability["complete"] > low_demand.state_probability["complete"]
