"""Converts a scenario's spectral displacement demand + a building's
fragility curves into discrete damage-state probabilities.

P(DS >= ds | Sd) comes straight from the building's already-computed
fragility curves (ML-tier or published-fallback, whichever applies --
see app/vulnerability/). Discrete-state probabilities are the usual
differencing of consecutive exceedance probabilities:
    P(none)      = 1 - P(>=slight)
    P(slight)    = P(>=slight) - P(>=moderate)
    P(moderate)  = P(>=moderate) - P(>=extensive)
    P(extensive) = P(>=extensive) - P(>=complete)
    P(complete)  = P(>=complete)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.vulnerability.fragility import DAMAGE_STATES, FragilityCurve

ALL_STATES = ("none",) + DAMAGE_STATES


@dataclass(frozen=True)
class DamageDistribution:
    demand_sd_mm: float
    exceedance_probability: dict[str, float]  # per damage state, P(DS>=ds | demand)
    state_probability: dict[str, float]  # per state including "none", sums to 1
    expected_state: str


def _interpolate_exceedance(curve: FragilityCurve, demand_sd_mm: float) -> float:
    sd = curve.sd_mm
    p = curve.probability
    if demand_sd_mm <= sd[0]:
        # Below the curve's plotted range: extrapolate via the same
        # lognormal form rather than clamping, since demand can genuinely
        # be smaller than the smallest plotted Sd.
        return float(np.interp(demand_sd_mm, sd, p, left=p[0]))
    if demand_sd_mm >= sd[-1]:
        return float(np.interp(demand_sd_mm, sd, p, right=p[-1]))
    return float(np.interp(demand_sd_mm, sd, p))


def compute_damage_distribution(
    fragility_curves: list[FragilityCurve], demand_sd_mm: float
) -> DamageDistribution:
    exceedance = {
        curve.damage_state: _interpolate_exceedance(curve, demand_sd_mm)
        for curve in fragility_curves
    }
    # Monotonicity guard: exceedance probabilities must be non-increasing
    # from slight -> complete; interpolation/extrapolation noise could
    # otherwise produce a tiny negative discrete-state probability.
    ordered = [exceedance[ds] for ds in DAMAGE_STATES]
    for i in range(1, len(ordered)):
        ordered[i] = min(ordered[i], ordered[i - 1])
    exceedance = dict(zip(DAMAGE_STATES, ordered))

    state_probability: dict[str, float] = {}
    state_probability["none"] = 1.0 - ordered[0]
    for i, ds in enumerate(DAMAGE_STATES):
        next_exceedance = ordered[i + 1] if i + 1 < len(ordered) else 0.0
        state_probability[ds] = max(ordered[i] - next_exceedance, 0.0)

    expected_state = max(state_probability, key=lambda s: state_probability[s])

    return DamageDistribution(
        demand_sd_mm=demand_sd_mm,
        exceedance_probability=exceedance,
        state_probability=state_probability,
        expected_state=expected_state,
    )
