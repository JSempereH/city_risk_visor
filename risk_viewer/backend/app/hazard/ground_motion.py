"""Per-building ground motion demand for a scenario.

Building period uses the common code-style approximation T = 0.1 * N
(0.1 s per floor, e.g. as in several seismic codes' simplified formulas
for low-rise buildings) rather than a full modal analysis.

Two ways to get from spectral acceleration to spectral displacement
demand:

- **Elastic** (`performance_point_method = "elastic"`): Sd = Sa(T) *
  T^2 / (4*pi^2) at the building's fixed period, evaluated directly
  against its lognormal fragility curves. Used whenever there's no
  capacity curve to iterate against (the GEM and published-fallback
  vulnerability tiers, see app/vulnerability/service.py, have fragility
  curves but no capacity curve).
- **ATC-40 nonlinear performance point**
  (`performance_point_method = "atc40"`): the actual capacity-spectrum
  intersection (see atc40.py), for buildings with a real bilinear
  capacity curve (the ML tier). Reduces demand for the effective damping
  the building's own hysteretic response adds once it yields, instead of
  applying the elastic spectrum directly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Optional

import numpy as np

from app.hazard import atc40, psha, site
from app.hazard.geo import haversine_km
from app.hazard.gmpe import ground_motion_at_period
from app.hazard.scenario import Scenario
from app.hazard.spectrum import build_demand_spectrum
from app.vulnerability.spectral import BilinearCapacity

METRES_PER_FLOOR_PERIOD = 0.1  # seconds per floor, simplified code formula

PerformancePointMethod = Literal["elastic", "atc40"]


def building_period_s(n_floors: float | None) -> float:
    floors = n_floors if n_floors and n_floors > 0 else 2.0
    return max(METRES_PER_FLOOR_PERIOD * floors, 0.05)


@dataclass(frozen=True)
class DemandEstimate:
    # None for probabilistic (PSHA) scenarios: there is no single
    # epicenter to measure distance from, see psha.py.
    distance_km: Optional[float]
    period_s: float
    sa_g: float
    sd_mm: float
    sigma_ln: float
    vs30_ms: float
    performance_point_method: PerformancePointMethod
    ductility: Optional[float] = None
    effective_damping_pct: Optional[float] = None


def compute_demand(
    scenario: Scenario,
    building_lat: float,
    building_lon: float,
    n_floors: float | None,
    bilinear: Optional[BilinearCapacity] = None,
    fixed_period_s: Optional[float] = None,
) -> DemandEstimate:
    # fixed_period_s overrides the generic code-formula period for tiers
    # whose fragility curves were derived at their own published period
    # (currently only the GEM tier, see
    # VulnerabilityResult.fixed_period_s). Using the code-formula period
    # there would evaluate demand and capacity at two different periods for
    # the same building.
    period_s = fixed_period_s if fixed_period_s is not None else building_period_s(n_floors)
    vs30 = site.vs30_at(scenario.city, building_lat, building_lon)

    if scenario.mode == "probabilistic":
        return _compute_demand_psha(scenario, building_lat, building_lon, period_s, vs30, bilinear)

    distance_km = haversine_km(
        scenario.epicenter_lat, scenario.epicenter_lon, building_lat, building_lon
    )

    if bilinear is not None:
        spectrum = build_demand_spectrum(
            scenario.magnitude,
            distance_km,
            scenario.depth_km,
            scenario.tectonic_regime,
            vs30,
            rake=scenario.rake,
            ztor_km=scenario.ztor_km,
        )
        performance_point = atc40.compute_performance_point(bilinear, spectrum)
        sigma_ln = float(np.interp(period_s, spectrum.periods_s, spectrum.sigma_ln))
        return DemandEstimate(
            distance_km=distance_km,
            period_s=period_s,
            sa_g=performance_point.sa_g,
            sd_mm=performance_point.sd_mm,
            sigma_ln=sigma_ln,
            vs30_ms=vs30,
            performance_point_method="atc40",
            ductility=performance_point.ductility,
            effective_damping_pct=performance_point.effective_damping_pct,
        )

    gm = ground_motion_at_period(
        scenario.magnitude,
        distance_km,
        scenario.depth_km,
        scenario.tectonic_regime,
        period_s,
        vs30,
        rake=scenario.rake,
        ztor_km=scenario.ztor_km,
    )
    sa_g = gm.median_sa_g

    # Sd[mm] = Sa[m/s^2] * T^2 / (4*pi^2) * 1000
    sa_ms2 = sa_g * 9.81
    sd_mm = sa_ms2 * period_s**2 / (4 * math.pi**2) * 1000.0

    return DemandEstimate(
        distance_km=distance_km,
        period_s=period_s,
        sa_g=sa_g,
        sd_mm=sd_mm,
        sigma_ln=gm.sigma_ln,
        vs30_ms=vs30,
        performance_point_method="elastic",
    )


def _compute_demand_psha(
    scenario: Scenario,
    building_lat: float,
    building_lon: float,
    period_s: float,
    vs30: float,
    bilinear: Optional[BilinearCapacity],
) -> DemandEstimate:
    assert scenario.return_period_years is not None
    spectrum = psha.build_demand_spectrum_psha(
        scenario.city, scenario.return_period_years, building_lat, building_lon, vs30
    )

    if bilinear is not None:
        performance_point = atc40.compute_performance_point(bilinear, spectrum)
        return DemandEstimate(
            distance_km=None,
            period_s=period_s,
            sa_g=performance_point.sa_g,
            sd_mm=performance_point.sd_mm,
            sigma_ln=0.0,
            vs30_ms=vs30,
            performance_point_method="atc40",
            ductility=performance_point.ductility,
            effective_damping_pct=performance_point.effective_damping_pct,
        )

    sa_g = float(np.interp(period_s, spectrum.periods_s, spectrum.sa_g))
    sa_ms2 = sa_g * 9.81
    sd_mm = sa_ms2 * period_s**2 / (4 * math.pi**2) * 1000.0
    return DemandEstimate(
        distance_km=None,
        period_s=period_s,
        sa_g=sa_g,
        sd_mm=sd_mm,
        sigma_ln=0.0,
        vs30_ms=vs30,
        performance_point_method="elastic",
    )
