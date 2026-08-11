"""Combines per-stage uncertainty into one total dispersion per building,
via lognormal quadrature, the same approach HAZUS itself uses internally
to combine capacity/demand/threshold uncertainty into a single
fragility-curve beta (see app/vulnerability/fragility.py's own
docstring), extended here with the GMPE's aleatory sigma, the
structural-typology classifier's ensemble disagreement, and (for the ML
capacity-model tier only) the GPR capacity-curve model's own predictive
uncertainty.

Reported per building as a quick summary statistic (`total_beta`),
assuming the contributing terms are independent. For a genuine
propagated range (e.g. a P10 to P90 band on city-wide casualties, which
this single combined beta cannot produce on its own since it never feeds
back into the damage/casualty point estimate), see monte_carlo.py.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np


# Fraction of a capacity curve's own peak V/W below which a point is
# excluded from capacity_beta_from_gpr_std()'s CV average. Near the
# origin, the GPR's predicted mean can be tiny or even slightly negative
# (a real, confirmed extrapolation artifact, not a data error: the model
# was never trained to guarantee V/W(0) = 0), while its predictive std
# does not shrink at the same rate, so std/mean explodes at exactly the
# points closest to zero. An absolute cutoff like `v_over_w > 1e-6` only
# excludes points at or below exact zero, not the noisy small-but-
# positive points right next to them, which is what actually produced
# betas above 30 for a handful of real buildings (confirmed empirically:
# santo_domingo_113 went from beta=33.8 to beta=0.29 under this
# threshold). A curve-relative threshold scales with each building's own
# curve instead of one global magnitude.
_CAPACITY_CURVE_SIGNAL_FLOOR_FRACTION = 0.05


def capacity_beta_from_gpr_std(v_over_w: np.ndarray, v_over_w_std: np.ndarray) -> float:
    """Converts the GPR capacity-curve model's own per-point predictive
    std (app/vulnerability/capacity_model.py's `v_over_w_std`, computed
    but previously unused downstream) into a lognormal-dispersion-
    equivalent beta contribution: the curve-averaged coefficient of
    variation (std/mean), RMS-combined across every point where the
    curve carries real signal (see _CAPACITY_CURVE_SIGNAL_FLOOR_FRACTION
    for why that excludes more than just v_over_w <= 0). std/mean is the
    standard first-order approximation of a lognormal dispersion for
    small relative uncertainty. Like typology_beta_from_entropy below,
    this is a documented modelling choice, not a canonical formula:
    there's no standard way to reduce a whole curve's heteroscedastic
    uncertainty to one scalar beta. Returns 0.0 if the curve carries no
    signal at all (shouldn't happen for a real prediction, guarded for
    safety)."""
    peak = v_over_w.max() if v_over_w.size else 0.0
    mask = v_over_w > _CAPACITY_CURVE_SIGNAL_FLOOR_FRACTION * peak
    if not mask.any():
        return 0.0
    cv = v_over_w_std[mask] / v_over_w[mask]
    return float(np.sqrt(np.mean(cv**2)))


def typology_beta_from_entropy(normalized_entropy: Optional[float]) -> float:
    """Converts classifier ensemble disagreement (normalized Shannon
    entropy over the models' predicted-class votes, 0=unanimous,
    1=maximally split) into a lognormal-dispersion-equivalent beta
    contribution. There is no canonical formula for this conversion, it
    is a modelling choice: scaled so full agreement contributes 0 and
    maximal disagreement contributes 0.5, comparable in order of
    magnitude to the fragility/GMPE terms it's combined with.
    """
    if normalized_entropy is None:
        return 0.0
    return 0.5 * max(0.0, min(1.0, normalized_entropy))


@dataclass(frozen=True)
class CombinedUncertainty:
    fragility_beta: float
    gmpe_sigma_ln: float
    typology_beta: float
    capacity_beta: float
    total_beta: float


def combine_uncertainty(
    fragility_beta: float,
    gmpe_sigma_ln: float,
    typology_beta: float = 0.0,
    capacity_beta: float = 0.0,
) -> CombinedUncertainty:
    total = math.sqrt(fragility_beta**2 + gmpe_sigma_ln**2 + typology_beta**2 + capacity_beta**2)
    return CombinedUncertainty(
        fragility_beta=fragility_beta,
        gmpe_sigma_ln=gmpe_sigma_ln,
        typology_beta=typology_beta,
        capacity_beta=capacity_beta,
        total_beta=total,
    )
