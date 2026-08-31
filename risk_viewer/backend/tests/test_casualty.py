import pytest

from app.risk.casualty import expected_casualties, hazus_building_type


def test_hazus_building_type_mapping():
    assert hazus_building_type("W", 2) == "W1"
    assert hazus_building_type("CR", 2) == "C1L"
    assert hazus_building_type("CR", 5) == "C1M"
    assert hazus_building_type("CR", 10) == "C1H"
    assert hazus_building_type("M", 1) == "URML"
    assert hazus_building_type("M", 5) == "URMM"
    assert hazus_building_type("ADO", 1) == "URML"
    assert hazus_building_type("MUR", 1) == "URML"
    assert hazus_building_type("MCF", 1) == "RM1L"
    assert hazus_building_type("MCF", 3) == "RM1L"
    assert hazus_building_type("MCF", 4) == "RM1M"
    assert hazus_building_type("MR", 5) == "RM1M"


def test_hazus_building_type_unknown_class_raises():
    # A city with a taxonomy this module has no HAZUS mapping decided for
    # yet (e.g. steel) must fail loudly, not silently cost it as masonry.
    with pytest.raises(ValueError, match="no HAZUS building-type mapping"):
        hazus_building_type("S", 3)


def test_casualties_increase_with_damage_severity():
    population = 100.0
    low_damage = {"none": 0.9, "slight": 0.1}
    high_damage = {"none": 0.0, "complete": 1.0}
    low = expected_casualties("CR", 3, low_damage, population)
    high = expected_casualties("CR", 3, high_damage, population)
    assert high.total > low.total
    assert high.severity_4 > low.severity_4


def test_fatalities_never_exceed_total():
    estimate = expected_casualties("M", 2, {"complete": 1.0}, 100.0)
    assert estimate.severity_4 <= estimate.total


def test_no_damage_gives_zero_casualties():
    estimate = expected_casualties("W", 1, {"none": 1.0}, 100.0)
    assert estimate.total == 0.0


def test_confined_masonry_casualties_differ_from_unreinforced():
    # Regression guard for the RM1 rollout: MCF/MR must no longer share
    # URML/URMM's rates given a damage state (see module docstring).
    damage = {"moderate": 0.5, "complete": 0.5}
    unreinforced = expected_casualties("MUR", 2, damage, 100.0)
    confined = expected_casualties("MCF", 2, damage, 100.0)
    assert confined.total != unreinforced.total
