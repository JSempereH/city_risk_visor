"""Deterministic seismic scenarios, one per pilot city.

Each is a "credible controlling event" (magnitude, representative source
distance, depth, tectonic regime), anchored to the controlling source
identified for each city in published regional hazard studies, using a
single point-source distance rather than those studies' full rupture
geometry or a probabilistic (PSHA/DSHA) treatment.

Sources used to anchor magnitude/regime/approximate distance:
- Guatemala City: Motagua-Jalpatagua crustal fault system, identified as
  the controlling source in Benito et al. (2012), "Seismic hazard
  assessment for Guatemala City" (Mw 6.5-7.0 at ~20-30 km). The system is
  dominantly left-lateral strike-slip (per the well-documented 1976 Mw
  7.5 Motagua earthquake on the same structure), so rake = 0 deg.
- San Jose: Cocos-Caribbean subduction interface, per Hidalgo-Leiva et al.
  (2022), "The 2022 Seismic Hazard Model for Costa Rica," BSSA 113(1).
  San Jose sits inland of the interface; ~75 km is a representative
  (illustrative) distance, not from the paper's own site-to-source table.
- Santo Domingo: Enriquillo-Plantain Garden fault system (same system
  that ruptured in the 2010 Mw 7.0 Haiti earthquake, continuous into
  southern Hispaniola), per Johnson et al. (2024), "Probabilistic seismic
  hazard analysis for the Dominican Republic," Earthquake Spectra (that
  paper's own headline number, Santiago's 475-yr PGA controlled by the
  Septentrional fault, is for the north; Santo Domingo, in the south, is
  used here with the Enriquillo-Plantain Garden system instead). Also
  left-lateral strike-slip, same as its 2010 Haiti rupture, so rake = 0 deg.

``rake`` and ``ztor_km`` feed the published GMPEs in gmpe.py:
- ``rake`` (degrees, Aki & Richards convention) selects style-of-faulting
  in crustal GMPEs; 0 deg/180 deg both mean pure strike-slip. Only used
  for the crustal regime here (Zhao et al. 2016's interface/intraslab
  GMPEs don't take a rake term).
- ``ztor_km`` (depth to top of rupture, km) is required by the interface/
  intraslab GMPEs and is deliberately a separate field from ``depth_km``
  (hypocentral/centroid depth, used for the point-source distance
  approximation in ground_motion.py). For a large interface rupture the
  top of the rupture sits well above the hypocenter: confirmed by direct
  testing of ZhaoEtAl2016SInter, where reusing depth_km (25 km) as ztor
  produced an unphysical spectral spike, while ztor=10-15 km gave a
  smooth, plausible spectrum. None for crustal scenarios (unused there).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Literal

from app.cities import CITIES, TectonicRegime

ScenarioMode = Literal["deterministic", "probabilistic"]


@dataclass(frozen=True)
class Scenario:
    city: str
    label: str
    magnitude: float
    depth_km: float
    epicenter_lat: float
    epicenter_lon: float
    tectonic_regime: TectonicRegime
    source_note: str
    rake: float = 0.0
    ztor_km: float | None = None
    # PSHA (probabilistic) scenarios, see psha.py: mode="probabilistic"
    # scenarios still carry the fields above (inherited from the city's
    # deterministic scenario, via probabilistic_scenario() below), but
    # they are inert placeholders in that mode, not the event actually
    # used to derive ground motion. Only return_period_years matters.
    mode: ScenarioMode = "deterministic"
    return_period_years: int | None = None


# Epicenter coordinates are illustrative: each city's real centroid offset
# by the scenario's representative distance/bearing toward its named
# fault/interface (straight-line degree-offset, not a real fault trace),
# so real per-building distances (and therefore real spatial variation in
# shaking across the city) can be computed from building geometry.
# See ground_motion.py. Derived from app.cities.CITIES, the single place
# these values are entered (see that module's docstring).
SCENARIOS: dict[str, Scenario] = {
    city: Scenario(
        city=profile.city,
        label=profile.scenario_label,
        magnitude=profile.magnitude,
        depth_km=profile.depth_km,
        epicenter_lat=profile.epicenter_lat,
        epicenter_lon=profile.epicenter_lon,
        tectonic_regime=profile.tectonic_regime,
        source_note=profile.deterministic_source_note,
        rake=profile.rake,
        ztor_km=profile.ztor_km,
    )
    for city, profile in CITIES.items()
}


def get_scenario(city: str) -> Scenario | None:
    return SCENARIOS.get(city)


# Return periods this UI offers for probabilistic scenarios (years). See
# app/hazard/psha.py's RETURN_PERIODS_YEARS docstring for what each one
# means; kept as a separate constant here so scenario.py has no import
# dependency on psha.py (psha.py already imports scenario.py, for the
# Vs30-amplification representative event; keeping the dependency
# one-directional avoids a cycle).
PROBABILISTIC_RETURN_PERIODS_YEARS: tuple[int, ...] = (475, 975, 2475)


def probabilistic_scenario(city: str, return_period_years: int) -> Scenario:
    """A PSHA scenario for a city with a precomputed hazard curve (see
    psha.PSHA_SUPPORTED_CITIES). The magnitude/depth/epicenter/regime
    fields are inherited from the city's deterministic scenario purely
    so this stays a plain Scenario (same type run_scenario() caches on),
    but are inert placeholders in this mode: see the Scenario.mode
    docstring."""
    base = SCENARIOS[city]
    return dataclasses.replace(
        base,
        label=f"PSHA, {return_period_years}-yr return period",
        source_note=CITIES[city].probabilistic_source_note,
        mode="probabilistic",
        return_period_years=return_period_years,
    )
