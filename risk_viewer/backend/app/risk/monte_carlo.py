"""Monte Carlo propagation of demand and structural-typology uncertainty
through to city-wide casualty totals, replacing a single combined-beta
number (see uncertainty.py) with an empirical spread of outcomes.

uncertainty.py's lognormal quadrature combines fragility beta, GMPE sigma,
and typology beta into one dispersion, reported per building, but that
number is never fed back into the damage/casualty point estimate (always
evaluated at the median demand). It also can't answer a question a real
risk assessment needs: what's a plausible range for total casualties
across the whole city, given every building's demand is uncertain at
once? Answering that requires actually sampling, since city-wide totals
are a sum of many nonlinear (damage-state threshold, casualty rate)
functions of that per-building uncertainty, not something a single
combined beta can be converted into after the fact.

Per building, per trial: draw a demand Sd from a lognormal distribution
centred on the GMPE's median with its reported sigma_ln (aleatory ground
motion variability), widened in quadrature by the building's typology
beta (entropy-based classifier disagreement) and, for the ML capacity-
model tier, its capacity beta (the GPR capacity curve's own predictive
uncertainty, see uncertainty.py::capacity_beta_from_gpr_std). Neither is
really a demand-side uncertainty (typology disagreement is about which
capacity curve applies, capacity beta is about the shape of that curve
itself, not the ground motion), but folding both into the demand draw
avoids resampling a different capacity curve per trial, the same
explicit modelling choice used for the point-estimate quadrature in
uncertainty.py, applied consistently here so the two reported ranges
(this Monte Carlo band and that combined beta) draw on the same set of
uncertainty sources per building. Evaluate the building's fragility
curves (which carry their own
beta) at the sampled demand to get exceedance probabilities, draw one
discrete damage state from them, then look up HAZUS casualty rates at
that state. Summing each trial's draws across all buildings in the city
gives one sample of the city-wide total; the resulting N-length array's
percentiles are the reported range.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from app.risk.casualty import rates_by_damage_state
from app.vulnerability.fragility import DAMAGE_STATES, FragilityCurve

ALL_STATES = ("none",) + DAMAGE_STATES

DEFAULT_N_SAMPLES = 300
DEFAULT_SEED = 42


@dataclass(frozen=True)
class BuildingMonteCarloInput:
    fragility_curves: list[FragilityCurve]  # ordered slight, moderate, extensive, complete
    median_sd_mm: float
    sigma_ln: float
    building_type: str  # HAZUS model building type, from casualty.hazus_building_type()
    population_day: float
    population_night: float


@dataclass(frozen=True)
class PercentileBand:
    p10: float
    p50: float
    p90: float
    mean: float


@dataclass(frozen=True)
class ScenarioMonteCarloSummary:
    n_samples: int
    n_buildings: int
    casualties_day: PercentileBand
    casualties_night: PercentileBand
    fatalities_day: PercentileBand
    fatalities_night: PercentileBand


def _percentile_band(samples: np.ndarray) -> PercentileBand:
    p10, p50, p90 = np.percentile(samples, [10, 50, 90])
    return PercentileBand(p10=float(p10), p50=float(p50), p90=float(p90), mean=float(samples.mean()))


def _sample_damage_state_index(
    fragility_curves: list[FragilityCurve], demand_samples: np.ndarray, rng: np.random.Generator
) -> np.ndarray:
    """One damage-state index (0=none .. 4=complete) per trial, drawn from
    the discrete state distribution at each trial's sampled demand."""
    n = len(demand_samples)
    exceedance = np.empty((4, n))
    curves_by_state = {c.damage_state: c for c in fragility_curves}
    for i, ds in enumerate(DAMAGE_STATES):
        curve = curves_by_state[ds]
        exceedance[i] = np.interp(demand_samples, curve.sd_mm, curve.probability)
    for i in range(1, 4):
        exceedance[i] = np.minimum(exceedance[i], exceedance[i - 1])

    state_probability = np.empty((5, n))
    state_probability[0] = 1.0 - exceedance[0]
    for i in range(4):
        next_exceedance = exceedance[i + 1] if i + 1 < 4 else 0.0
        state_probability[i + 1] = np.maximum(exceedance[i] - next_exceedance, 0.0)
    state_probability /= state_probability.sum(axis=0, keepdims=True)

    cumulative = np.cumsum(state_probability, axis=0)
    draw = rng.uniform(size=n)
    return (draw[None, :] > cumulative).sum(axis=0)


def _sample_building(
    building: BuildingMonteCarloInput,
    typology_beta: float,
    capacity_beta: float,
    n_samples: int,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    """Returns (casualties, fatalities), each shaped (2, n_samples) for (day, night)."""
    sigma = math.sqrt(building.sigma_ln**2 + typology_beta**2 + capacity_beta**2)
    demand_samples = building.median_sd_mm * np.exp(rng.standard_normal(n_samples) * sigma)
    state_idx = _sample_damage_state_index(building.fragility_curves, demand_samples, rng)

    rates = rates_by_damage_state(building.building_type)
    total_rate_by_state = np.array([sum(rates[s]) for s in ALL_STATES])
    fatality_rate_by_state = np.array([rates[s][3] for s in ALL_STATES])

    total_rate = total_rate_by_state[state_idx]
    fatality_rate = fatality_rate_by_state[state_idx]

    casualties = np.stack(
        [total_rate * building.population_day, total_rate * building.population_night]
    )
    fatalities = np.stack(
        [fatality_rate * building.population_day, fatality_rate * building.population_night]
    )
    return casualties, fatalities


def run_scenario_monte_carlo(
    buildings: list[tuple[BuildingMonteCarloInput, float, float]],
    n_samples: int = DEFAULT_N_SAMPLES,
    seed: int = DEFAULT_SEED,
) -> ScenarioMonteCarloSummary:
    """`buildings` is a list of (input, typology_beta, capacity_beta)
    triples, one per available building in the scenario (capacity_beta is
    0.0 for tiers with no capacity curve at all). Deterministic given
    `seed`, so repeat requests for the same scenario reproduce the same
    bands."""
    rng = np.random.default_rng(seed)
    total_casualties = np.zeros((2, n_samples))
    total_fatalities = np.zeros((2, n_samples))

    for building, typology_beta, capacity_beta in buildings:
        casualties, fatalities = _sample_building(building, typology_beta, capacity_beta, n_samples, rng)
        total_casualties += casualties
        total_fatalities += fatalities

    return ScenarioMonteCarloSummary(
        n_samples=n_samples,
        n_buildings=len(buildings),
        casualties_day=_percentile_band(total_casualties[0]),
        casualties_night=_percentile_band(total_casualties[1]),
        fatalities_day=_percentile_band(total_fatalities[0]),
        fatalities_night=_percentile_band(total_fatalities[1]),
    )
