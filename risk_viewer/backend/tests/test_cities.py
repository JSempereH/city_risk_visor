"""Verifies app.cities.CITIES is genuinely the single source of truth for
a city's inherent scientific parameters: the 3 pilot cities' derived
values match their known literals (regression guard against a copy
mistake), and a brand-new CityProfile entry alone, no other file
touched, is enough for the consuming modules to pick it up. That
second property is the actual point of this refactor.
"""

import importlib

from app import cities as cities_module
from app.cities import CityProfile
from app.hazard import psha as psha_module
from app.hazard import scenario as scenario_module


def test_scenarios_keys_match_cities_registry():
    assert set(scenario_module.SCENARIOS.keys()) == set(cities_module.CITIES.keys())


def test_san_jose_scenario_matches_known_literals():
    # Regression guard: these are the values this project has published/
    # validated against (docs/psha_plan.md), not arbitrary.
    sj = scenario_module.SCENARIOS["san_jose"]
    assert sj.magnitude == 7.5
    assert sj.tectonic_regime == "interface"
    assert sj.ztor_km == 15.0
    assert psha_module.REFERENCE_VS30_BY_CITY["san_jose"] == 760.0
    assert psha_module.INVESTIGATION_TIME_YEARS_BY_CITY["san_jose"] == 50.0


def test_lomas_centinela_scenario_matches_known_literals():
    # Regression guard: Zapopan Graben / Tesistan Valley crustal source
    # (Quinteros-Cartaya et al. 2023), replacing the earlier 1932
    # subduction mainshock as the deterministic scenario -- see
    # cities.py's own deterministic_source_note for the full citation.
    lc = scenario_module.SCENARIOS["lomas_centinela"]
    assert lc.magnitude == 6.5
    assert lc.tectonic_regime == "crustal"
    assert lc.rake == -90.0
    assert lc.ztor_km is None


def test_new_city_profile_is_picked_up_with_no_other_code_changes():
    fake_profile = CityProfile(
        city="fake_city",
        scenario_label="Test scenario",
        magnitude=6.0,
        depth_km=10.0,
        epicenter_lat=0.0,
        epicenter_lon=0.0,
        tectonic_regime="crustal",
        deterministic_source_note="test fixture, not a real city",
        reference_vs30=500.0,
        investigation_time_years=1.0,
    )
    cities_module.CITIES["fake_city"] = fake_profile
    try:
        importlib.reload(scenario_module)
        importlib.reload(psha_module)

        assert "fake_city" in scenario_module.SCENARIOS
        assert scenario_module.SCENARIOS["fake_city"].magnitude == 6.0
        assert scenario_module.SCENARIOS["fake_city"].tectonic_regime == "crustal"
        assert psha_module.REFERENCE_VS30_BY_CITY["fake_city"] == 500.0
        assert psha_module.INVESTIGATION_TIME_YEARS_BY_CITY["fake_city"] == 1.0
    finally:
        del cities_module.CITIES["fake_city"]
        importlib.reload(scenario_module)
        importlib.reload(psha_module)
