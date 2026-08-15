"""Hazard/risk scenario endpoints: the default per-city scenario, plus
user-adjustable magnitude/depth/epicenter overrides. See
app/risk/service.py for the full hazard -> vulnerability -> damage ->
casualty chain this wraps."""

from __future__ import annotations

import dataclasses

from fastapi import APIRouter, HTTPException, Response

from app import precomputed as precomputed_store
from app import typology_hypothesis
from app.hazard import psha
from app.hazard.geo import haversine_km
from app.hazard.scenario import SCENARIOS, PROBABILISTIC_RETURN_PERIODS_YEARS, Scenario, probabilistic_scenario
from app.risk import run_scenario_coalesced
from app.risk.api import scenario_summary_to_json, scenario_to_feature_collection
from app.risk.service import CityScenarioSummary

router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])

MIN_MAGNITUDE, MAX_MAGNITUDE = 4.5, 9.0
MIN_DEPTH_KM, MAX_DEPTH_KM = 1.0, 200.0
MAX_EPICENTER_DISTANCE_KM = 500.0


def _with_active_hypothesis(scenario: Scenario) -> Scenario:
    """Attaches the active typology hypothesis's fingerprint (if any) for
    this scenario's city, so app/risk/service.py::run_scenario()'s cache
    key (keyed on the whole Scenario) never collides between a plain
    request and a hypothesis-influenced one, or between two different
    hypotheses (see Scenario.typology_hypothesis_fingerprint's own
    docstring). A no-op (returns scenario unchanged) when no hypothesis
    is active for this city.
    """
    hypothesis = typology_hypothesis.get_hypothesis(scenario.city)
    if hypothesis is None:
        return scenario
    return dataclasses.replace(scenario, typology_hypothesis_fingerprint=hypothesis.fingerprint())


def _build_scenario(
    city: str,
    magnitude: float | None,
    depth_km: float | None,
    epicenter_lat: float | None,
    epicenter_lon: float | None,
) -> Scenario:
    """The city's default scenario, or a copy with any of
    magnitude/depth/epicenter overridden. Tectonic regime, rake and ztor
    stay fixed, since they characterise the specific fault/interface each
    scenario is anchored to (see scenario.py), not something a magnitude
    or location slider should change.
    """
    base = SCENARIOS[city]
    if magnitude is None and depth_km is None and epicenter_lat is None and epicenter_lon is None:
        return _with_active_hypothesis(base)

    # base.label is "Mw {default magnitude}, {fault/interface name}"; once
    # any field is overridden that magnitude no longer matches what's
    # actually run, so keep only the fault/interface name and mark the
    # scenario as custom instead of showing a stale magnitude next to the
    # real one in scenario-meta.
    _, _, fault_name = base.label.partition(", ")
    custom_label = f"Custom scenario, {fault_name}" if fault_name else "Custom scenario"

    if magnitude is not None and not (MIN_MAGNITUDE <= magnitude <= MAX_MAGNITUDE):
        raise HTTPException(
            status_code=400,
            detail=f"magnitude must be between {MIN_MAGNITUDE} and {MAX_MAGNITUDE}.",
        )
    if depth_km is not None and not (MIN_DEPTH_KM <= depth_km <= MAX_DEPTH_KM):
        raise HTTPException(
            status_code=400,
            detail=f"depth_km must be between {MIN_DEPTH_KM} and {MAX_DEPTH_KM}.",
        )
    lat = epicenter_lat if epicenter_lat is not None else base.epicenter_lat
    lon = epicenter_lon if epicenter_lon is not None else base.epicenter_lon
    distance = haversine_km(base.epicenter_lat, base.epicenter_lon, lat, lon)
    if distance > MAX_EPICENTER_DISTANCE_KM:
        raise HTTPException(
            status_code=400,
            detail=f"epicenter must be within {MAX_EPICENTER_DISTANCE_KM:.0f} km of the "
            f"default epicenter ({base.epicenter_lat}, {base.epicenter_lon}).",
        )

    return _with_active_hypothesis(
        dataclasses.replace(
            base,
            label=custom_label,
            magnitude=magnitude if magnitude is not None else base.magnitude,
            depth_km=depth_km if depth_km is not None else base.depth_km,
            epicenter_lat=lat,
            epicenter_lon=lon,
        )
    )


def _get_scenario_summary(
    city: str,
    magnitude: float | None = None,
    depth_km: float | None = None,
    epicenter_lat: float | None = None,
    epicenter_lon: float | None = None,
    return_period_years: int | None = None,
) -> CityScenarioSummary:
    if city not in SCENARIOS:
        raise HTTPException(status_code=404, detail=f"No scenario defined for city: {city}")

    if return_period_years is not None:
        if magnitude is not None or depth_km is not None or epicenter_lat is not None or epicenter_lon is not None:
            raise HTTPException(
                status_code=400,
                detail="return_period_years cannot be combined with magnitude/depth_km/epicenter overrides "
                "(they belong to different scenario modes, see scenario.py).",
            )
        if city not in psha.PSHA_SUPPORTED_CITIES:
            raise HTTPException(
                status_code=400,
                detail=f"No precomputed PSHA hazard curve for city: {city}. "
                f"Probabilistic scenarios are currently only available for: "
                f"{', '.join(sorted(psha.PSHA_SUPPORTED_CITIES))}.",
            )
        if return_period_years not in PROBABILISTIC_RETURN_PERIODS_YEARS:
            raise HTTPException(
                status_code=400,
                detail=f"return_period_years must be one of {PROBABILISTIC_RETURN_PERIODS_YEARS}.",
            )
        return run_scenario_coalesced(_with_active_hypothesis(probabilistic_scenario(city, return_period_years)))

    scenario = _build_scenario(city, magnitude, depth_km, epicenter_lat, epicenter_lon)
    return run_scenario_coalesced(scenario)


@router.get("")
def list_scenarios() -> list[dict]:
    return [
        {
            "city": s.city,
            "label": s.label,
            "magnitude": s.magnitude,
            "depth_km": s.depth_km,
            "epicenter_lat": s.epicenter_lat,
            "epicenter_lon": s.epicenter_lon,
            "tectonic_regime": s.tectonic_regime,
            "source_note": s.source_note,
            "psha_available": s.city in psha.PSHA_SUPPORTED_CITIES,
            "psha_return_periods_years": list(PROBABILISTIC_RETURN_PERIODS_YEARS)
            if s.city in psha.PSHA_SUPPORTED_CITIES
            else [],
        }
        for s in SCENARIOS.values()
    ]


@router.get("/{city}/hazard_curve")
def hazard_curve(city: str, imt: str = "PGA") -> dict:
    """Raw precomputed hazard curve (level -> probability of exceedance,
    mean + p16/p84) for one intensity measure, for charting the curve
    itself (see docs/psha_plan.md section 1). Independent of any chosen
    return period."""
    if city not in psha.PSHA_SUPPORTED_CITIES:
        raise HTTPException(
            status_code=404,
            detail=f"No precomputed PSHA hazard curve for city: {city}.",
        )
    curve = psha.hazard_curve(city, imt)
    if curve is None:
        raise HTTPException(status_code=404, detail=f"No hazard curve for IMT {imt!r} in city {city!r}.")
    return {
        "city": city,
        "imt": imt,
        "investigation_time_years": psha.INVESTIGATION_TIME_YEARS_BY_CITY[city],
        **curve,
    }


@router.get("/{city}/disaggregation")
def disaggregation(city: str, return_period_years: int = 475) -> dict:
    """Which magnitude/distance combination controls this city's PGA
    hazard at a given return period (see docs/disaggregation_plan.md):
    mean magnitude/distance plus the full mag x dist bin breakdown."""
    if city not in psha.DISAGG_SUPPORTED_CITIES:
        raise HTTPException(
            status_code=404,
            detail=f"No precomputed disaggregation for city: {city}.",
        )
    if return_period_years not in PROBABILISTIC_RETURN_PERIODS_YEARS:
        raise HTTPException(
            status_code=400,
            detail=f"return_period_years must be one of {PROBABILISTIC_RETURN_PERIODS_YEARS}.",
        )
    result = psha.disaggregation(city, return_period_years)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No precomputed disaggregation for city {city!r} at {return_period_years}yr.",
        )
    return {"city": city, "return_period_years": return_period_years, "imt": "PGA", **result}


def _is_precomputable_request(
    city: str,
    magnitude: float | None,
    depth_km: float | None,
    epicenter_lat: float | None,
    epicenter_lon: float | None,
) -> bool:
    """True for a request shaped like one of the 12 known menu combos
    (city default, or city + return_period_years only), the only
    requests scripts/precompute.py bakes ahead of time. Any deterministic
    override makes a request a Custom Scenario, which is never
    precomputed (see app/precomputed.py). An active typology hypothesis
    for this city (app/typology_hypothesis.py) also disqualifies it: the
    baked-ahead precomputed bytes never reflect a hypothesis, since
    scripts/precompute.py runs with no hypothesis active."""
    if typology_hypothesis.get_hypothesis(city) is not None:
        return False
    return magnitude is None and depth_km is None and epicenter_lat is None and epicenter_lon is None


@router.get("/{city}/summary", response_model=None)
def scenario_summary(
    city: str,
    magnitude: float | None = None,
    depth_km: float | None = None,
    epicenter_lat: float | None = None,
    epicenter_lon: float | None = None,
    return_period_years: int | None = None,
) -> dict | Response:
    if _is_precomputable_request(city, magnitude, depth_km, epicenter_lat, epicenter_lon):
        # Raw bytes, returned as a Response directly: this is an
        # already-JSON-safe result baked at build time, so skip FastAPI's
        # jsonable_encoder + re-serialization on every request (see
        # app/precomputed.py; this matters most for /risk below, whose
        # payload is up to a few MB per city).
        precomputed = precomputed_store.get_precomputed_summary_bytes(city, return_period_years)
        if precomputed is not None:
            return Response(content=precomputed, media_type="application/json")

    return scenario_summary_to_json(
        _get_scenario_summary(city, magnitude, depth_km, epicenter_lat, epicenter_lon, return_period_years)
    )


@router.get("/{city}/risk", response_model=None)
def scenario_risk(
    city: str,
    magnitude: float | None = None,
    depth_km: float | None = None,
    epicenter_lat: float | None = None,
    epicenter_lon: float | None = None,
    return_period_years: int | None = None,
) -> dict | Response:
    if _is_precomputable_request(city, magnitude, depth_km, epicenter_lat, epicenter_lon):
        precomputed = precomputed_store.get_precomputed_risk_bytes(city, return_period_years)
        if precomputed is not None:
            return Response(content=precomputed, media_type="application/json")

    return scenario_to_feature_collection(
        _get_scenario_summary(city, magnitude, depth_km, epicenter_lat, epicenter_lon, return_period_years)
    )
