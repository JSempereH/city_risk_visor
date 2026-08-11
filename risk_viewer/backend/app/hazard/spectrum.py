"""A discretized 5%-damped elastic response spectrum (period -> Sa),
built by evaluating the real GMPE (see gmpe.py) at a fixed set of
periods, rather than at a single building-specific period. Used by
atc40.py to find a nonlinear performance point, which needs demand at
whatever period the structure's effective stiffness corresponds to
during the capacity-spectrum iteration, not just its initial period.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.hazard.gmpe import TectonicRegime, ground_motion_at_period

# Log-spaced periods spanning the range structural periods and their
# damped/softened effective periods can plausibly fall in for the
# low-rise masonry buildings this feeds (app/vulnerability/gem_fragility.py's
# CR/W/ADO buildings and the fallback tier use their own single-period
# elastic demand instead, see ground_motion.py).
SPECTRUM_PERIODS_S: tuple[float, ...] = (
    0.05, 0.075, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.6, 0.75,
    0.9, 1.0, 1.2, 1.5, 1.8, 2.0, 2.5, 3.0,
)


@dataclass(frozen=True)
class DemandSpectrum:
    periods_s: tuple[float, ...]
    sa_g: tuple[float, ...]
    sigma_ln: tuple[float, ...]


def build_demand_spectrum(
    magnitude: float,
    distance_km: float,
    depth_km: float,
    regime: TectonicRegime,
    vs30: float,
    rake: float,
    ztor_km: float | None,
) -> DemandSpectrum:
    sa_g = []
    sigma_ln = []
    for period_s in SPECTRUM_PERIODS_S:
        gm = ground_motion_at_period(
            magnitude, distance_km, depth_km, regime, period_s, vs30, rake=rake, ztor_km=ztor_km
        )
        sa_g.append(gm.median_sa_g)
        sigma_ln.append(gm.sigma_ln)
    return DemandSpectrum(periods_s=SPECTRUM_PERIODS_S, sa_g=tuple(sa_g), sigma_ln=tuple(sigma_ln))
