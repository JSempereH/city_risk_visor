import pytest
from fastapi.testclient import TestClient

from app import typology_hypothesis
from app.main import app
from app.routers import scenarios as scenarios_router

client = TestClient(app)

TEST_CITY = "guatemala"


def test_is_precomputable_request():
    assert scenarios_router._is_precomputable_request(TEST_CITY, None, None, None, None) is True
    assert scenarios_router._is_precomputable_request(TEST_CITY, 7.0, None, None, None) is False
    assert scenarios_router._is_precomputable_request(TEST_CITY, None, 10.0, None, None) is False
    assert scenarios_router._is_precomputable_request(TEST_CITY, None, None, 9.9, None) is False
    assert scenarios_router._is_precomputable_request(TEST_CITY, None, None, None, -84.0) is False


def test_is_precomputable_request_false_under_active_hypothesis():
    typology_hypothesis.set_hypothesis(TEST_CITY, {"M": 1.0})
    try:
        assert scenarios_router._is_precomputable_request(TEST_CITY, None, None, None, None) is False
    finally:
        typology_hypothesis.clear_hypothesis(TEST_CITY)


def test_scenario_summary_uses_precomputed_shortcut(monkeypatch):
    # The router should return a precomputed result verbatim, without
    # ever calling the (slow) live compute path, for a menu-shaped
    # request (no deterministic overrides).
    sentinel = b'{"city": "san_jose", "fake": "precomputed-summary"}'
    monkeypatch.setattr(
        scenarios_router.precomputed_store, "get_precomputed_summary_bytes", lambda city, years: sentinel
    )
    response = client.get("/api/scenarios/san_jose/summary")
    assert response.json() == {"city": "san_jose", "fake": "precomputed-summary"}


def test_scenario_risk_uses_precomputed_shortcut(monkeypatch):
    sentinel = b'{"type": "FeatureCollection", "features": ["fake-precomputed"]}'
    monkeypatch.setattr(scenarios_router.precomputed_store, "get_precomputed_risk_bytes", lambda city, years: sentinel)
    response = client.get("/api/scenarios/san_jose/risk")
    assert response.json() == {"type": "FeatureCollection", "features": ["fake-precomputed"]}


def test_custom_scenario_never_consults_precomputed_store(monkeypatch):
    calls = []
    monkeypatch.setattr(
        scenarios_router.precomputed_store,
        "get_precomputed_summary_bytes",
        lambda city, years: calls.append((city, years)) or b'{"should": "never be returned"}',
    )
    response = client.get("/api/scenarios/guatemala/summary", params={"magnitude": 7.0})
    assert calls == []
    assert response.json()["scenario"]["magnitude"] == 7.0


def test_list_scenarios():
    response = client.get("/api/scenarios")
    assert response.status_code == 200
    cities = {s["city"] for s in response.json()}
    assert cities == {"guatemala", "san_jose", "santo_domingo", "lomas_centinela"}


def test_unknown_city_scenario_404():
    response = client.get("/api/scenarios/nowhere/summary")
    assert response.status_code == 404


def test_scenario_summary_guatemala():
    response = client.get("/api/scenarios/guatemala/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["n_buildings"] == 436
    assert body["n_available"] > 0
    assert sum(body["damage_state_counts"].values()) == body["n_available"]
    assert body["total_population_night"] > body["total_population_day"] > 0
    assert body["total_casualties_night"] > 0
    assert body["total_casualties_night"] >= body["total_casualties_night_fatalities"] >= 0


def test_scenario_risk_feature_collection():
    response = client.get("/api/scenarios/guatemala/risk")
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) == 436

    available = [f for f in body["features"] if f["properties"]["risk_available"]]
    assert len(available) > 0
    props = available[0]["properties"]
    assert props["expected_damage_state"] in ("none", "slight", "moderate", "extensive", "complete")
    assert abs(sum(props["state_probability"].values()) - 1.0) < 1e-6
    assert props["distance_km"] > 0
    assert props["total_beta"] >= max(props["fragility_beta"], props["gmpe_sigma_ln"])
    assert props["casualties_night_total"] == pytest.approx(
        sum(props[f"casualties_night_severity_{i}"] for i in (1, 2, 3, 4))
    )


def test_ensemble_estimated_structural_system_gets_real_risk():
    # guatemala_752 has no recorded structural_system, but the typology
    # classifier ensemble predicts "M" for it (see
    # app/data_loader.py::_fill_unlabeled_from_ensemble). It should get
    # a real risk computation, flagged as resting on an estimated class,
    # not the "unavailable, no defensible typology" treatment genuinely
    # unlabeled buildings get.
    response = client.get("/api/scenarios/guatemala/risk", params={"magnitude": 7.0})
    features = {f["properties"]["id"]: f["properties"] for f in response.json()["features"]}
    props = features["guatemala_752"]
    assert props["risk_available"] is True
    assert props["structural_system_class"] == "M"
    assert props["structural_system_estimated"] is True
    # Fixed floor (see app/risk/service.py::ESTIMATED_TYPOLOGY_BETA), not
    # derived from the ensemble's own entropy: this building's 3 models
    # happen to agree unanimously (normalized_entropy == 0), which must
    # not read as extra confidence when there's no real label to check
    # the prediction against in the first place.
    assert props["typology_beta"] == 0.6


def test_capacity_beta_present_only_for_ml_tier():
    # The GPR capacity-curve model's own predictive uncertainty (see
    # app/risk/uncertainty.py::capacity_beta_from_gpr_std) only applies
    # to buildings actually using that model; other tiers have no
    # capacity curve to be uncertain about.
    response = client.get("/api/scenarios/guatemala/risk")
    available = [f for f in response.json()["features"] if f["properties"]["risk_available"]]
    ml_tier = [f for f in available if f["properties"]["curve_source"] == "ml_capacity_model"]
    other_tier = [f for f in available if f["properties"]["curve_source"] != "ml_capacity_model"]
    assert len(ml_tier) > 0
    assert len(other_tier) > 0
    assert all(f["properties"]["capacity_beta"] > 0 for f in ml_tier)
    assert all(f["properties"]["capacity_beta"] == 0.0 for f in other_tier)


def test_typology_beta_falls_back_to_generic_when_no_ensemble(monkeypatch):
    # A city with no per-building ML ensemble (see
    # app/cities.py's typology_beta_generic docstring) should report
    # that city's fixed generic constant, not silently 0.0. Tested here
    # against guatemala with a monkeypatched typology_beta_generic
    # rather than a real such city, since none is currently in CITIES.
    import dataclasses

    from app.cities import CITIES
    from app.risk import service as service_module

    monkeypatch.setattr(service_module, "get_ensemble_info", lambda building_id, city: None)
    patched = dataclasses.replace(CITIES["guatemala"], typology_beta_generic=0.6)
    monkeypatch.setitem(CITIES, "guatemala", patched)
    # run_scenario() is lru_cache'd by the full Scenario value, and another
    # test already requested this exact (guatemala, magnitude=7.0) scenario
    # before this monkeypatch was applied, so this clears it, so the test
    # exercises the patched typology_beta_for(), not a stale cached result.
    service_module.run_scenario.cache_clear()

    response = client.get("/api/scenarios/guatemala/risk", params={"magnitude": 7.0})
    available = [f for f in response.json()["features"] if f["properties"]["risk_available"]]
    assert len(available) > 0
    assert all(f["properties"]["typology_beta"] == 0.6 for f in available)


def test_scenario_risk_is_cached_across_calls():
    summary1 = client.get("/api/scenarios/guatemala/summary").json()
    summary2 = client.get("/api/scenarios/guatemala/summary").json()
    assert summary1 == summary2


def test_psha_scenario_summary_san_jose():
    response = client.get("/api/scenarios/san_jose/summary", params={"return_period_years": 475})
    assert response.status_code == 200
    body = response.json()
    assert body["scenario"]["mode"] == "probabilistic"
    assert body["scenario"]["return_period_years"] == 475
    # A 475-year probabilistic scenario is a rarer, stronger shaking level
    # than the single "credible" deterministic event, so it should show
    # real damage rather than the deterministic scenario's near-zero
    # damage at this same city (see docs/psha_plan.md's results section).
    assert sum(v for k, v in body["damage_state_counts"].items() if k != "none") > 0


def test_hazard_curve_endpoint():
    response = client.get("/api/scenarios/san_jose/hazard_curve", params={"imt": "PGA"})
    assert response.status_code == 200
    body = response.json()
    assert body["imt"] == "PGA"
    assert body["investigation_time_years"] == 50.0
    assert len(body["levels"]) == len(body["mean"]) == len(body["p16"]) == len(body["p84"])
    # PoE decreases monotonically as the intensity level increases.
    assert body["mean"] == sorted(body["mean"], reverse=True)
    assert all(p16 <= mean <= p84 for p16, mean, p84 in zip(body["p16"], body["mean"], body["p84"]))


def test_hazard_curve_unknown_city_404():
    response = client.get("/api/scenarios/nowhere/hazard_curve")
    assert response.status_code == 404


def test_psha_hazard_percentiles_present_and_ordered():
    response = client.get("/api/scenarios/san_jose/summary", params={"return_period_years": 475})
    body = response.json()
    hp = body["hazard_percentiles"]
    assert hp is not None
    assert hp["p16"] < hp["mean"] < hp["p84"]


def test_deterministic_scenario_has_no_hazard_percentiles():
    response = client.get("/api/scenarios/san_jose/summary")
    body = response.json()
    assert body["hazard_percentiles"] is None


def test_psha_scenario_risk_distance_is_null():
    response = client.get("/api/scenarios/san_jose/risk", params={"return_period_years": 475})
    assert response.status_code == 200
    body = response.json()
    available = [f for f in body["features"] if f["properties"].get("risk_available")]
    assert len(available) > 0
    # No single epicenter in probabilistic mode, see ground_motion.py.
    assert all(f["properties"]["distance_km"] is None for f in available)
    assert all(f["properties"]["gmpe_sigma_ln"] == 0.0 for f in available)


def test_psha_unsupported_city_400(monkeypatch):
    # All 3 pilot cities in SCENARIOS now have precomputed PSHA curves, so this
    # guard (for a city added to SCENARIOS before its curve is precomputed) is
    # exercised here via monkeypatch rather than a real unsupported city.
    from app.hazard import psha as psha_module

    monkeypatch.setattr(psha_module, "PSHA_SUPPORTED_CITIES", frozenset({"san_jose"}))
    # Force a miss on the baked-scenario shortcut too, so this exercises the
    # live validation path being tested rather than a real precomputed
    # guatemala/475yr result (baked before this simulated support change).
    monkeypatch.setattr(scenarios_router.precomputed_store, "get_precomputed_summary_bytes", lambda city, years: None)
    response = client.get("/api/scenarios/guatemala/summary", params={"return_period_years": 475})
    assert response.status_code == 400


def test_psha_invalid_return_period_400():
    response = client.get("/api/scenarios/san_jose/summary", params={"return_period_years": 100})
    assert response.status_code == 400


def test_psha_cannot_combine_with_deterministic_overrides():
    response = client.get(
        "/api/scenarios/san_jose/summary",
        params={"return_period_years": 475, "magnitude": 7.0},
    )
    assert response.status_code == 400


def test_list_scenarios_reports_psha_availability():
    response = client.get("/api/scenarios")
    by_city = {s["city"]: s for s in response.json()}
    for city in ("san_jose", "guatemala", "santo_domingo"):
        assert by_city[city]["psha_available"] is True
        assert set(by_city[city]["psha_return_periods_years"]) == {475, 975, 2475}
