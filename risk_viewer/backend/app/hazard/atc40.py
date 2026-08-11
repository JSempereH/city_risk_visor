"""ATC-40 Capacity Spectrum Method (Procedure A): finds the performance
point where a building's capacity curve intersects its demand spectrum,
progressively reduced for the effective viscous damping the building's
own hysteretic response adds at that displacement (ATC-40, "Seismic
Evaluation and Retrofit of Concrete Buildings," 1996, Chapter 8).

Replaces ground_motion.py's elastic demand (Sd = Sa(T) * T^2/(4*pi^2) at
a single, fixed period) with the actual nonlinear intersection, for
buildings that have a real capacity curve (the ML tier, see
app/vulnerability/capacity_model.py). Buildings on the GEM or
published-fallback tiers have fragility curves but no capacity curve to
iterate against, so they keep using the elastic point.

Per-iteration steps (ATC-40 Eq 8-1 to 8-22):
1. Ductility at the trial point: mu = dpi / dy.
2. Hysteretic damping beta_0 = 63.7 * kappa * (ay*dpi - dy*api) / (api*dpi),
   percent; kappa is ATC-40's damping-modification (degradation) factor.
   This implementation uses a single fixed kappa = 0.667 (ATC-40 Table 8-1's
   Type B value, "average existing buildings," moderate strength/stiffness
   degradation), rather than ATC-40's full piecewise Type A/B/C table,
   which needs a structural-behavior-type classification this app doesn't
   have.
3. Effective damping beta_eff = 5 + beta_0 (percent), capped at 40%.
4. Spectral reduction factors (ATC-40 Eq 8-21, 8-22):
     SRA = max(3.21 - 0.68*ln(beta_eff), 0.33)
     SRV = max(2.31 - 0.41*ln(beta_eff), 0.50)
5. Reduced demand spectrum: SRA scales Sa at or below the spectrum's own
   peak period (its acceleration-sensitive range), SRV beyond it (its
   velocity-sensitive range), using the empirical spectrum's own peak
   period as that transition, rather than an idealized code spectrum's
   analytical corner period, since the demand spectrum here comes from a
   real GMPE evaluated at discrete periods (see spectrum.py), not a
   two-branch code shape.
6. New trial point: the intersection of the reduced spectrum with the
   capacity curve, found numerically. The capacity curve is only two line
   segments (elastic ramp to yield, then a plastic plateau), so this is
   a straightforward piecewise root-find, not a closed-form solution.
Repeat until the displacement changes by less than 5% between iterations
or a fixed iteration budget is used up.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from app.hazard.spectrum import DemandSpectrum
from app.vulnerability.spectral import BilinearCapacity

G_MS2 = 9.81

TYPE_B_KAPPA = 0.667
MAX_EFFECTIVE_DAMPING_PCT = 40.0
MIN_EFFECTIVE_DAMPING_PCT = 5.0
MAX_ITERATIONS = 15
CONVERGENCE_TOLERANCE = 0.05


@dataclass(frozen=True)
class PerformancePoint:
    sd_mm: float
    sa_g: float
    ductility: float
    effective_damping_pct: float
    converged: bool
    iterations: int


def capacity_sa_at_sd(sd_mm: float, bilinear: BilinearCapacity) -> float:
    """Elastic ramp from the origin to (sdy, say), flat plateau beyond
    (spectral.py's bilinearize() always sets say_g == sau_g, an
    elasto-perfectly-plastic idealisation). Zero beyond sdu: the pushover
    curve was only analysed up to that near-collapse displacement, so
    there is no reliable capacity past it."""
    if sd_mm <= 0 or bilinear.sdy_mm <= 0:
        return bilinear.say_g
    if sd_mm <= bilinear.sdy_mm:
        return bilinear.say_g * (sd_mm / bilinear.sdy_mm)
    if sd_mm <= bilinear.sdu_mm:
        return bilinear.say_g
    return 0.0


def _reduced_demand_curve(
    spectrum: DemandSpectrum, sra: float, srv: float, corner_period_s: float
) -> tuple[np.ndarray, np.ndarray]:
    periods = np.array(spectrum.periods_s)
    sa_5pct = np.array(spectrum.sa_g)
    factor = np.where(periods <= corner_period_s, sra, srv)
    sa_reduced = sa_5pct * factor
    sd_reduced = sa_reduced * G_MS2 * periods**2 / (4 * math.pi**2) * 1000.0
    return sd_reduced, sa_reduced


def _intersect_with_capacity(
    demand_sd: np.ndarray, demand_sa: np.ndarray, bilinear: BilinearCapacity
) -> tuple[float, float]:
    """First point (walking from short to long period, i.e. low to high
    Sd) where the demand curve crosses the capacity curve. If they never
    cross, the building's capacity exceeds demand everywhere (returns the
    last, largest-Sd demand point, i.e. still within the elastic/plateau
    capacity) or demand exceeds capacity everywhere (returns the capacity
    curve's ultimate point, i.e. the closest this model gets to "collapse
    under this demand")."""
    order = np.argsort(demand_sd)
    sd_sorted = demand_sd[order]
    sa_sorted = demand_sa[order]
    capacity_sorted = np.array([capacity_sa_at_sd(sd, bilinear) for sd in sd_sorted])
    diff = sa_sorted - capacity_sorted  # >0: demand above capacity (not yet stable)

    sign_changes = np.where(np.diff(np.sign(diff)) != 0)[0]
    if len(sign_changes) == 0:
        if diff[0] <= 0:
            # Capacity already exceeds demand at the shortest period: the
            # building responds (near-)elastically to this scenario.
            return float(sd_sorted[0]), float(sa_sorted[0])
        # Demand exceeds capacity even at the longest period: cap at the
        # capacity curve's own ultimate point.
        return bilinear.sdu_mm, bilinear.sau_g

    i = sign_changes[0]
    sd0, sd1 = float(sd_sorted[i]), float(sd_sorted[i + 1])
    d0, d1 = float(diff[i]), float(diff[i + 1])
    t = -d0 / (d1 - d0) if d1 != d0 else 0.0
    sd_cross = sd0 + t * (sd1 - sd0)
    sa_cross = capacity_sa_at_sd(sd_cross, bilinear)
    return sd_cross, sa_cross


def compute_performance_point(bilinear: BilinearCapacity, spectrum: DemandSpectrum) -> PerformancePoint:
    periods = np.array(spectrum.periods_s)
    sa_5pct = np.array(spectrum.sa_g)
    corner_period_s = float(periods[int(np.argmax(sa_5pct))])

    sd_5pct, sa_5pct_curve = _reduced_demand_curve(spectrum, 1.0, 1.0, corner_period_s)
    trial_sd, trial_sa = _intersect_with_capacity(sd_5pct, sa_5pct_curve, bilinear)

    converged = False
    iterations = 0
    effective_damping_pct = MIN_EFFECTIVE_DAMPING_PCT
    for iterations in range(1, MAX_ITERATIONS + 1):
        api = capacity_sa_at_sd(trial_sd, bilinear)
        dpi = trial_sd
        mu = dpi / bilinear.sdy_mm if bilinear.sdy_mm > 0 else 1.0

        if mu <= 1.0 or api <= 0 or dpi <= 0:
            effective_damping_pct = MIN_EFFECTIVE_DAMPING_PCT
            converged = True
            break

        beta_hyst = 63.7 * TYPE_B_KAPPA * (bilinear.say_g * dpi - bilinear.sdy_mm * api) / (api * dpi)
        effective_damping_pct = min(
            max(MIN_EFFECTIVE_DAMPING_PCT + beta_hyst, MIN_EFFECTIVE_DAMPING_PCT),
            MAX_EFFECTIVE_DAMPING_PCT,
        )
        sra = max(3.21 - 0.68 * math.log(effective_damping_pct), 0.33)
        srv = max(2.31 - 0.41 * math.log(effective_damping_pct), 0.50)

        sd_reduced, sa_reduced = _reduced_demand_curve(spectrum, sra, srv, corner_period_s)
        new_sd, new_sa = _intersect_with_capacity(sd_reduced, sa_reduced, bilinear)

        if trial_sd > 0 and abs(new_sd - trial_sd) / trial_sd < CONVERGENCE_TOLERANCE:
            trial_sd, trial_sa = new_sd, new_sa
            converged = True
            break
        trial_sd, trial_sa = new_sd, new_sa

    final_mu = trial_sd / bilinear.sdy_mm if bilinear.sdy_mm > 0 else 1.0
    return PerformancePoint(
        sd_mm=trial_sd,
        sa_g=trial_sa,
        ductility=final_mu,
        effective_damping_pct=effective_damping_pct,
        converged=converged,
        iterations=iterations,
    )
