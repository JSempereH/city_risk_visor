from app.risk.population import OCCUPANCY_FACTOR, estimate_population


def test_known_building_uses_worldpop_disaggregation():
    estimate = estimate_population("guatemala_7", "guatemala", 40.0, 2)
    assert estimate.night > 0
    assert estimate.day == estimate.night * OCCUPANCY_FACTOR["day"]


def test_unknown_building_falls_back_to_floor_area_proxy():
    # Not in any city's WorldPop CSV: falls back to the floor-area proxy
    # rather than reporting zero population.
    estimate = estimate_population("does_not_exist", "guatemala", 100.0, 2)
    assert estimate.night > 0


def test_unknown_city_falls_back_to_floor_area_proxy():
    estimate = estimate_population("some_id", "nonexistent_city", 100.0, 2)
    assert estimate.night > 0


def test_night_population_exceeds_day():
    estimate = estimate_population("guatemala_7", "guatemala", 40.0, 2)
    assert estimate.night > estimate.day
