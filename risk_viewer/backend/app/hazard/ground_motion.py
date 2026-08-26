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
from typing import Any, Literal, Optional

import numpy as np

from app.hazard import atc40, psha, site
from app.hazard.geo import haversine_km, haversine_km_array
from app.hazard.gmpe import ground_motion_at_period, ground_motion_grid
from app.hazard.scenario import Scenario
from app.hazard.spectrum import SPECTRUM_PERIODS_S, DemandSpectrum, build_demand_spectrum
from app.vulnerability.service import VulnerabilityResult
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


def compute_demand_batch(
    scenario: Scenario,
    buildings: list[dict[str, Any]],
    vulnerabilities: list[VulnerabilityResult],
) -> list[Optional[DemandEstimate]]:
    """Same DemandEstimate per building as calling compute_demand() once
    per building, for a deterministic scenario only (PSHA demand already
    comes from precomputed curves with no GMPE call to batch, see
    _compute_demand_psha above). `vulnerabilities` must be the same
    length as `buildings`, in the same order (position i of one
    corresponds to position i of the other); the result is a same-length
    list too, None wherever that building's vulnerability isn't
    available.

    Deliberately positional, not keyed by building["id"]: some cities'
    exposure data has duplicate ids (confirmed for san_jose, 11 of 897
    ids each covering 2 rows), so an id-keyed intermediate dict would
    silently collapse those rows onto one shared result, applying
    whichever duplicate's demand to both, wrong whenever the two rows'
    attributes actually differ. See app/risk/api.py's own risk_by_id
    dict for the same latent risk one level up, at GeoJSON-serialization
    time, not fixed here since it's a pre-existing, separate concern.

    Only issues 1-2 hazardlib calls for the whole city (one for every
    building whose vulnerability tier has a capacity curve to iterate
    against with atc40.py, evaluated at the same fixed 18-period
    spectrum grid; one for every other available building, evaluated at
    whatever distinct set of periods those buildings actually use)
    instead of up to 1 + 18 calls per building. See gmpe.py's
    ground_motion_grid docstring for why this reproduces
    ground_motion_at_period's per-building results exactly.
    """
    assert scenario.mode == "deterministic"
    assert len(buildings) == len(vulnerabilities)

    n = len(buildings)
    result: list[Optional[DemandEstimate]] = [None] * n
    available_positions = [i for i in range(n) if vulnerabilities[i].available]
    if not available_positions:
        return result

    lats = np.array([buildings[i]["centroid_lat"] for i in available_positions])
    lons = np.array([buildings[i]["centroid_lon"] for i in available_positions])
    distances = haversine_km_array(scenario.epicenter_lat, scenario.epicenter_lon, lats, lons)
    vs30s = site.vs30_at_many(scenario.city, lats, lons)

    # Local indices, into available_positions/distances/vs30s (0..len(available_positions)-1).
    atc40_local = [
        j for j, i in enumerate(available_positions) if vulnerabilities[i].bilinear is not None
    ]
    atc40_local_set = set(atc40_local)
    elastic_local = [j for j in range(len(available_positions)) if j not in atc40_local_set]

    if atc40_local:
        idx = np.array(atc40_local)
        sa_grid, sigma_grid = ground_motion_grid(
            scenario.magnitude,
            distances[idx],
            scenario.depth_km,
            scenario.tectonic_regime,
            SPECTRUM_PERIODS_S,
            vs30s[idx],
            rake=scenario.rake,
            ztor_km=scenario.ztor_km,
        )
        for row, j in enumerate(atc40_local):
            i = available_positions[j]
            building = buildings[i]
            vulnerability = vulnerabilities[i]
            assert vulnerability.bilinear is not None
            spectrum = DemandSpectrum(
                periods_s=SPECTRUM_PERIODS_S,
                sa_g=tuple(sa_grid[row]),
                sigma_ln=tuple(sigma_grid[row]),
            )
            performance_point = atc40.compute_performance_point(vulnerability.bilinear, spectrum)
            period_s = (
                vulnerability.fixed_period_s
                if vulnerability.fixed_period_s is not None
                else building_period_s(building["n_floors"])
            )
            sigma_ln = float(np.interp(period_s, spectrum.periods_s, spectrum.sigma_ln))
            result[i] = DemandEstimate(
                distance_km=float(distances[j]),
                period_s=period_s,
                sa_g=performance_point.sa_g,
                sd_mm=performance_point.sd_mm,
                sigma_ln=sigma_ln,
                vs30_ms=float(vs30s[j]),
                performance_point_method="atc40",
                ductility=performance_point.ductility,
                effective_damping_pct=performance_point.effective_damping_pct,
            )

    if elastic_local:
        periods_by_local = {}
        for j in elastic_local:
            i = available_positions[j]
            building = buildings[i]
            vulnerability = vulnerabilities[i]
            periods_by_local[j] = (
                vulnerability.fixed_period_s
                if vulnerability.fixed_period_s is not None
                else building_period_s(building["n_floors"])
            )
        distinct_periods = sorted(set(periods_by_local.values()))
        period_to_column = {period: column for column, period in enumerate(distinct_periods)}

        idx = np.array(elastic_local)
        sa_grid, sigma_grid = ground_motion_grid(
            scenario.magnitude,
            distances[idx],
            scenario.depth_km,
            scenario.tectonic_regime,
            tuple(distinct_periods),
            vs30s[idx],
            rake=scenario.rake,
            ztor_km=scenario.ztor_km,
        )
        for row, j in enumerate(elastic_local):
            i = available_positions[j]
            period_s = periods_by_local[j]
            column = period_to_column[period_s]
            sa_g = float(sa_grid[row, column])
            sa_ms2 = sa_g * 9.81
            sd_mm = sa_ms2 * period_s**2 / (4 * math.pi**2) * 1000.0
            result[i] = DemandEstimate(
                distance_km=float(distances[j]),
                period_s=period_s,
                sa_g=sa_g,
                sd_mm=sd_mm,
                sigma_ln=float(sigma_grid[row, column]),
                vs30_ms=float(vs30s[j]),
                performance_point_method="elastic",
            )

    return result
