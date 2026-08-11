from app.hazard.scenario import SCENARIOS
from app.risk.service import _lock_for


def test_lock_for_same_scenario_returns_same_lock():
    scenario = SCENARIOS["san_jose"]
    assert _lock_for(scenario) is _lock_for(scenario)


def test_lock_for_different_scenarios_returns_different_locks():
    assert _lock_for(SCENARIOS["san_jose"]) is not _lock_for(SCENARIOS["guatemala"])
