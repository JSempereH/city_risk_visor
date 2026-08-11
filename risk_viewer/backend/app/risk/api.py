"""Serialises scenario risk results into JSON-safe dicts / GeoJSON."""

from __future__ import annotations

from typing import Any

from app import data_loader
from app.risk.monte_carlo import PercentileBand
from app.risk.service import BuildingRisk, CityScenarioSummary


def _band_to_json(band: PercentileBand) -> dict[str, float]:
    return {"p10": band.p10, "p50": band.p50, "p90": band.p90, "mean": band.mean}


def _building_risk_properties(risk: BuildingRisk) -> dict[str, Any]:
    if not risk.available:
        return {"id": risk.building_id, "risk_available": False, "risk_reason": risk.reason}

    assert risk.demand is not None
    assert risk.damage is not None
    assert risk.population is not None
    assert risk.uncertainty is not None

    return {
        "id": risk.building_id,
        "risk_available": True,
        "curve_source": risk.curve_source,
        "distance_km": risk.demand.distance_km,
        "demand_sa_g": risk.demand.sa_g,
        "demand_sd_mm": risk.demand.sd_mm,
        "performance_point_method": risk.demand.performance_point_method,
        "ductility": risk.demand.ductility,
        "effective_damping_pct": risk.demand.effective_damping_pct,
        "expected_damage_state": risk.damage.expected_state,
        "state_probability": risk.damage.state_probability,
        "exceedance_probability": risk.damage.exceedance_probability,
        "population_day": risk.population.day,
        "population_night": risk.population.night,
        "casualties_day_total": risk.expected_casualties_day.total,
        "casualties_day_severity_1": risk.expected_casualties_day.severity_1,
        "casualties_day_severity_2": risk.expected_casualties_day.severity_2,
        "casualties_day_severity_3": risk.expected_casualties_day.severity_3,
        "casualties_day_severity_4": risk.expected_casualties_day.severity_4,
        "casualties_night_total": risk.expected_casualties_night.total,
        "casualties_night_severity_1": risk.expected_casualties_night.severity_1,
        "casualties_night_severity_2": risk.expected_casualties_night.severity_2,
        "casualties_night_severity_3": risk.expected_casualties_night.severity_3,
        "casualties_night_severity_4": risk.expected_casualties_night.severity_4,
        "fragility_beta": risk.uncertainty.fragility_beta,
        "gmpe_sigma_ln": risk.uncertainty.gmpe_sigma_ln,
        "typology_beta": risk.uncertainty.typology_beta,
        "capacity_beta": risk.uncertainty.capacity_beta,
        "total_beta": risk.uncertainty.total_beta,
    }


def scenario_to_feature_collection(summary: CityScenarioSummary) -> dict[str, Any]:
    base = data_loader.feature_collection(summary.city)
    risk_by_id = {risk.building_id: risk for risk in summary.building_risks}

    features = []
    for feature in base["features"]:
        building_id = feature["properties"].get("id")
        risk = risk_by_id.get(building_id)
        properties = dict(feature["properties"])
        if risk is not None:
            properties.update(_building_risk_properties(risk))
        features.append({**feature, "properties": properties})

    return {"type": "FeatureCollection", "features": features}


def scenario_summary_to_json(summary: CityScenarioSummary) -> dict[str, Any]:
    return {
        "city": summary.city,
        "scenario": {
            "label": summary.scenario.label,
            "mode": summary.scenario.mode,
            "return_period_years": summary.scenario.return_period_years,
            # Inert placeholders in probabilistic mode (see Scenario.mode
            # docstring in scenario.py): still reported so deterministic
            # clients don't need a branch, but the frontend should only
            # display these when mode == "deterministic".
            "magnitude": summary.scenario.magnitude,
            "depth_km": summary.scenario.depth_km,
            "epicenter_lat": summary.scenario.epicenter_lat,
            "epicenter_lon": summary.scenario.epicenter_lon,
            "tectonic_regime": summary.scenario.tectonic_regime,
            "source_note": summary.scenario.source_note,
        },
        "n_buildings": summary.n_buildings,
        "n_available": summary.n_available,
        "damage_state_counts": summary.damage_state_counts,
        "total_population_day": summary.total_population_day,
        "total_population_night": summary.total_population_night,
        "total_casualties_day": summary.total_expected_casualties_day.total,
        "total_casualties_day_fatalities": summary.total_expected_casualties_day.severity_4,
        "total_casualties_night": summary.total_expected_casualties_night.total,
        "total_casualties_night_fatalities": summary.total_expected_casualties_night.severity_4,
        "monte_carlo": {
            "n_samples": summary.monte_carlo.n_samples,
            "casualties_day": _band_to_json(summary.monte_carlo.casualties_day),
            "casualties_night": _band_to_json(summary.monte_carlo.casualties_night),
            "fatalities_day": _band_to_json(summary.monte_carlo.fatalities_day),
            "fatalities_night": _band_to_json(summary.monte_carlo.fatalities_night),
        },
        "hazard_percentiles": summary.hazard_percentiles,
    }
