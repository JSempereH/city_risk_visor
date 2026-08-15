"""Orchestrates one building's full hazard -> vulnerability -> damage ->
casualty -> uncertainty chain for a given scenario, and aggregates it
across a city.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Iterable, Optional

from app import data_loader
from app import typology_hypothesis
from app.cities import CITIES
from app.hazard import psha
from app.hazard.ground_motion import DemandEstimate, compute_demand
from app.hazard.scenario import Scenario
from app.risk.casualty import CasualtyEstimate, expected_casualties, hazus_building_type
from app.risk.damage import DamageDistribution, compute_damage_distribution
from app.risk.monte_carlo import BuildingMonteCarloInput, ScenarioMonteCarloSummary, run_scenario_monte_carlo
from app.risk.population import PopulationEstimate, estimate_population
from app.risk.uncertainty import (
    CombinedUncertainty,
    capacity_beta_from_gpr_std,
    combine_uncertainty,
    typology_beta_from_entropy,
)
from app.typology_ensemble import get_ensemble_info
from app.vulnerability.fragility import FragilityCurve
from app.vulnerability.service import compute_vulnerability

# Fixed typology_beta floor for a building whose structural_system_class
# came from the typology ensemble's own prediction rather than recorded
# data (data_loader.py::_fill_unlabeled_from_ensemble). Set above
# typology_beta_from_entropy()'s own 0.5 ceiling, same reasoning as
# CityProfile.typology_beta_generic's documented precedent: there being
# no real ground truth for this building at all is a different, larger
# kind of uncertainty than mere inter-model disagreement, so it should
# never read as more confident than a maximally-disagreeing real
# ensemble, let alone as confident as a recorded label.
ESTIMATED_TYPOLOGY_BETA = 0.6


@dataclass(frozen=True)
class BuildingRisk:
    building_id: str
    available: bool
    reason: Optional[str]
    curve_source: Optional[str]
    demand: Optional[DemandEstimate]
    damage: Optional[DamageDistribution]
    population: Optional[PopulationEstimate]
    expected_casualties_day: Optional[CasualtyEstimate]
    expected_casualties_night: Optional[CasualtyEstimate]
    uncertainty: Optional[CombinedUncertainty]
    fragility_curves: Optional[list[FragilityCurve]]
    typology_beta: float
    # The structural_system_class actually used for this risk run, which
    # under an active typology hypothesis (app/typology_hypothesis.py) is
    # the hypothesis-sampled class, not necessarily the building's
    # recorded/stored one. app/risk/api.py reads this (rather than the
    # stored value) when serialising the map layer, so the map's
    # structural_system_class colouring and building panel actually
    # reflect a "what if" hypothesis instead of silently showing stale
    # data while only the aggregate numbers update.
    structural_system_class: str
    structural_system_estimated: bool


def compute_building_risk(
    building: dict[str, Any], scenario: Scenario, typology_beta: float = 0.0
) -> BuildingRisk:
    vulnerability = compute_vulnerability(
        structural_system_class=building["structural_system_class"],
        n_floors=building["n_floors"],
        height=building["height"],
        relative_position=building["relative_position"],
        code_quality=building["code_quality"],
    )
    if not vulnerability.available:
        return BuildingRisk(
            building_id=building["id"],
            available=False,
            reason=vulnerability.reason,
            curve_source=None,
            demand=None,
            damage=None,
            population=None,
            expected_casualties_day=None,
            expected_casualties_night=None,
            uncertainty=None,
            fragility_curves=None,
            typology_beta=typology_beta,
            structural_system_class=building["structural_system_class"],
            structural_system_estimated=building["structural_system_estimated"],
        )

    assert vulnerability.fragility_curves is not None
    demand = compute_demand(
        scenario,
        building["centroid_lat"],
        building["centroid_lon"],
        building["n_floors"],
        bilinear=vulnerability.bilinear,
        fixed_period_s=vulnerability.fixed_period_s,
    )
    damage = compute_damage_distribution(vulnerability.fragility_curves, demand.sd_mm)
    population = estimate_population(
        building["id"], building["city"], building["footprint_area_m2"], building["n_floors"]
    )
    casualties_day = expected_casualties(
        building["structural_system_class"], building["n_floors"], damage.state_probability, population.day
    )
    casualties_night = expected_casualties(
        building["structural_system_class"], building["n_floors"], damage.state_probability, population.night
    )
    capacity_beta = (
        capacity_beta_from_gpr_std(vulnerability.capacity_curve.v_over_w, vulnerability.capacity_curve.v_over_w_std)
        if vulnerability.capacity_curve is not None
        else 0.0
    )
    uncertainty = combine_uncertainty(
        fragility_beta=vulnerability.fragility_curves[0].beta,
        gmpe_sigma_ln=demand.sigma_ln,
        typology_beta=typology_beta,
        capacity_beta=capacity_beta,
    )

    return BuildingRisk(
        building_id=building["id"],
        available=True,
        reason=None,
        curve_source=vulnerability.curve_source,
        demand=demand,
        damage=damage,
        population=population,
        expected_casualties_day=casualties_day,
        expected_casualties_night=casualties_night,
        uncertainty=uncertainty,
        fragility_curves=vulnerability.fragility_curves,
        typology_beta=typology_beta,
        structural_system_class=building["structural_system_class"],
        structural_system_estimated=building["structural_system_estimated"],
    )


@dataclass(frozen=True)
class CityScenarioSummary:
    city: str
    scenario: Scenario
    n_buildings: int
    n_available: int
    damage_state_counts: dict[str, int]
    total_population_day: float
    total_population_night: float
    total_expected_casualties_day: CasualtyEstimate
    total_expected_casualties_night: CasualtyEstimate
    monte_carlo: ScenarioMonteCarloSummary
    building_risks: list[BuildingRisk]
    # PGA at mean/p16/p84 across the GMPE logic tree, for probabilistic
    # scenarios only (None for deterministic ones): the hazard curve's own
    # epistemic spread, distinct from monte_carlo's aleatory P10-P90 bands.
    hazard_percentiles: Optional[dict[str, float]]


@lru_cache(maxsize=32)
def run_scenario(scenario: Scenario) -> CityScenarioSummary:
    """Cached by the full scenario value (city, magnitude, epicenter,
    depth): a full run costs real compute time (~15-30s for a few hundred
    buildings), so repeat requests for the same scenario (e.g. the summary
    and the map layer both need it) reuse the same result for the process
    lifetime, whether that scenario is a city's default or a user-adjusted
    one.
    """
    city = scenario.city
    buildings = data_loader.get_buildings_by_city(city)

    # An active expert typology hypothesis (app/typology_hypothesis.py)
    # overrides every building's structural_system_class for this run,
    # the same "what if" spirit as building_vulnerability()'s single-
    # building query-param override, just applied city-wide and sampled
    # to match the hypothesis's own stated class proportions rather than
    # a single value repeated everywhere. scenario.typology_hypothesis_
    # fingerprint (set by the caller, see app/routers/scenarios.py)
    # guarantees this only runs, and this result only gets cached, under
    # a cache key distinct from the same city's non-hypothesis scenario.
    hypothesis = typology_hypothesis.get_hypothesis(city) if scenario.typology_hypothesis_fingerprint else None
    sampled_classes: dict[str, str] = {}
    hypothesis_beta = 0.0
    if hypothesis is not None:
        sampled_classes = typology_hypothesis.sample_classes(
            (b["id"] for b in buildings), hypothesis.proportions_dict(), hypothesis.seed
        )
        hypothesis_beta = typology_hypothesis.hypothesis_typology_beta(hypothesis.proportions_dict())

    def effective_building(building: dict[str, Any]) -> dict[str, Any]:
        sampled_class = sampled_classes.get(building["id"])
        if sampled_class is None:
            return building
        return {**building, "structural_system_class": sampled_class, "structural_system_estimated": True}

    def typology_beta_for(building: dict[str, Any]) -> float:
        if building["id"] in sampled_classes:
            return hypothesis_beta
        if building["structural_system_estimated"]:
            # This building's structural_system_class isn't recorded
            # data at all, just the typology classifier ensemble's own
            # prediction (see data_loader.py::_fill_unlabeled_from_
            # ensemble). Using typology_beta_from_entropy() here would
            # let the extra uncertainty drop to 0 whenever the ensemble's
            # 3 models happen to agree, understating it: model agreement
            # isn't the same thing as having a real label to check the
            # prediction against. Same fixed floor as ESTIMATED_TYPOLOGY_
            # BETA's own docstring explains.
            return ESTIMATED_TYPOLOGY_BETA
        ensemble = get_ensemble_info(building["id"], city)
        if ensemble is not None:
            return typology_beta_from_entropy(ensemble.normalized_entropy)
        # No per-building ML ensemble for this city at all (a generic,
        # documented regional typology assumption instead, see
        # app/cities.py's CityProfile.typology_beta_generic docstring):
        # fall back to that city's fixed, deliberately wide constant
        # rather than silently reporting zero extra uncertainty for a
        # typology that's actually a guess.
        return CITIES[city].typology_beta_generic or 0.0

    buildings = [effective_building(b) for b in buildings]
    risks = [compute_building_risk(b, scenario, typology_beta_for(b)) for b in buildings]

    damage_state_counts: dict[str, int] = {}
    total_pop_day = 0.0
    total_pop_night = 0.0
    available_risks = [r for r in risks if r.available]

    for risk in available_risks:
        assert risk.damage is not None and risk.population is not None
        damage_state_counts[risk.damage.expected_state] = (
            damage_state_counts.get(risk.damage.expected_state, 0) + 1
        )
        total_pop_day += risk.population.day
        total_pop_night += risk.population.night

    monte_carlo_inputs = [
        (
            BuildingMonteCarloInput(
                fragility_curves=risk.fragility_curves,
                median_sd_mm=risk.demand.sd_mm,
                sigma_ln=risk.demand.sigma_ln,
                building_type=hazus_building_type(b["structural_system_class"], b["n_floors"]),
                population_day=risk.population.day,
                population_night=risk.population.night,
            ),
            risk.typology_beta,
            risk.uncertainty.capacity_beta,
        )
        for b, risk in zip(buildings, risks)
        if risk.available
    ]
    monte_carlo = run_scenario_monte_carlo(monte_carlo_inputs)

    hazard_percentiles = (
        psha.pga_hazard_percentiles(city, scenario.return_period_years)
        if scenario.mode == "probabilistic" and scenario.return_period_years is not None
        else None
    )

    return CityScenarioSummary(
        city=city,
        scenario=scenario,
        n_buildings=len(buildings),
        n_available=len(available_risks),
        damage_state_counts=damage_state_counts,
        total_population_day=total_pop_day,
        total_population_night=total_pop_night,
        total_expected_casualties_day=_sum_casualties(r.expected_casualties_day for r in available_risks),
        total_expected_casualties_night=_sum_casualties(r.expected_casualties_night for r in available_risks),
        monte_carlo=monte_carlo,
        building_risks=risks,
        hazard_percentiles=hazard_percentiles,
    )


@lru_cache(maxsize=64)
def _lock_for(scenario: Scenario) -> threading.Lock:
    # A fresh Lock per distinct scenario, evicted by the same lru_cache
    # machinery (and hashability) run_scenario() already relies on, so
    # this doesn't grow without bound either.
    return threading.Lock()


def run_scenario_coalesced(scenario: Scenario) -> CityScenarioSummary:
    """run_scenario(), but safe against the same not-yet-cached scenario
    being requested by two concurrent requests at once (e.g. two browser
    tabs, or the summary and risk endpoints firing together for a new
    Custom Scenario). functools.lru_cache only locks its own dict
    lookup/insert, not the wrapped function's body, so without this both
    callers would independently pay the full 15-90s compute cost. Once a
    scenario is cached, the lock is held only as long as the (instant)
    cache hit takes."""
    with _lock_for(scenario):
        return run_scenario(scenario)


def _sum_casualties(estimates: Iterable[Optional[CasualtyEstimate]]) -> CasualtyEstimate:
    totals = [0.0, 0.0, 0.0, 0.0]
    for estimate in estimates:
        if estimate is None:
            continue
        totals[0] += estimate.severity_1
        totals[1] += estimate.severity_2
        totals[2] += estimate.severity_3
        totals[3] += estimate.severity_4
    return CasualtyEstimate(*totals)
