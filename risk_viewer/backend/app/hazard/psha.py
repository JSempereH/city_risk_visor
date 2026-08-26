"""Probabilistic Seismic Hazard Analysis (PSHA): Sa(T) at a chosen return
period, read off precomputed hazard curves, instead of DSHA's single
magnitude/distance/GMPE evaluation (see ground_motion.py, scenario.py).

Where DSHA answers "how hard would this one credible earthquake shake
this building", PSHA answers "what shaking level is exceeded with a
given probability over a given time window", integrating over every
possible source, magnitude and distance in the source model, each
weighted by its Gutenberg-Richter recurrence rate, through a full GMPE
logic tree (Cornell-McGuire formulation; see docs/psha_plan.md).

Data: the hazard curves in app/data/psha/{city}.csv were precomputed
offline (see docs/psha_plan.md's "how the data was produced" section),
not computed on request. Full classical PSHA over a real regional source
model is far too slow for a web request: even a single site, single-GMPE
hazard curve over San Jose's ~1.1 million ruptures took tens of minutes.
That is why (like Vs30 and population, see site.py/population.py) this
module reads a small offline-computed file rather than calling
hazardlib's calc_hazard_curves() itself.

Coverage: four cities, four different published source models, at
different levels of simplification from the fully published logic tree
(see docs/psha_plan.md section 7/10 for what was simplified per city and
why):
- San Jose (Costa Rica): Hidalgo-Leiva et al. (2022)'s CRSHM2022 model,
  full GMPE logic tree, single source-model branch (the model only had
  one). Validated directly against the paper's own published curves.
- Guatemala City: GEM's Caribbean & Central America (CCA) regional
  mosaic model. A single representative source-model realisation (the
  main source-model branch plus one of its two fault-geometry variants,
  rather than the full ~16000-sample source-model x GMPE logic tree,
  which is far too large to enumerate at this project's compute budget),
  with the full GMPE logic tree for the tectonic region types relevant
  near Guatemala City.
- Santo Domingo: GEM's Dominican Republic model. Similarly a single
  representative source-model realisation (one of 24 source-model
  branches x one of the "extendModel" subduction-source additions,
  rather than the full ~96-branch source model), with the full GMPE
  logic tree.
- Lomas del Centinela: GEM's Mexico (MEX) national model. Single
  source-model branch (no fault-geometry-style choice to restrict), run
  at 200 of 155,520 possible source-model x GMPE logic-tree
  combinations, the same reduced-sampling technique as Santo Domingo,
  with the full GMPE logic tree.
No published hazard curve was available to validate Guatemala City,
Santo Domingo, or Lomas del Centinela against directly (unlike San
Jose); see docs/psha_plan.md.

What "mean_poe_Tyr" is: for each city, the GMPE-logic-tree-weighted
*mean* hazard curve (probability of exceedance in that city's own source
model's investigation time T, see INVESTIGATION_TIME_YEARS_BY_CITY),
not any one logic-tree realisation. It already integrates over each
GMPE's own aleatory sigma (that integration is what turns a GMPE's
lognormal distribution into a probability of exceedance in the
Cornell-McGuire integral) as well as over the epistemic GMPE-choice
uncertainty (via the logic-tree weights). That is why
demand_spectrum_psha() below reports sigma_ln = 0.0: unlike the DSHA
path's single-GMPE median-and-sigma, there is no further aleatory spread
to layer on top without double-counting.

Site condition: each city's curves were computed at that city's own
source model's reference/generic-rock Vs30 (REFERENCE_VS30_BY_CITY), not
per-building Vs30. Per-building Vs30 (site.py) is applied afterwards as a
simple amplification ratio (see _vs30_amplification_factor below), not
by recomputing PSHA per Vs30 value, which would multiply the offline
compute cost by however many distinct Vs30 values exist across a city's
buildings.
"""

from __future__ import annotations

import csv
import math
import re
from functools import lru_cache
from pathlib import Path

import numpy as np

from app.cities import CITIES
from app.hazard.gmpe import ground_motion_at_period
from app.hazard.geo import haversine_km
from app.hazard.scenario import SCENARIOS
from app.hazard.spectrum import SPECTRUM_PERIODS_S, DemandSpectrum

_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "psha"

# Each city's hazard curves were computed at that model's own
# reference/generic-rock Vs30 (its job.ini's reference_vs30_value), not a
# shared constant: San Jose's CRSHM2022 uses 760 m/s, Guatemala's CCA and
# Santo Domingo's DR model both use 800 m/s. Derived from app.cities.CITIES
# (a city with no PSHA model yet has reference_vs30=None and is excluded).
REFERENCE_VS30_BY_CITY: dict[str, float] = {
    city: profile.reference_vs30 for city, profile in CITIES.items() if profile.reference_vs30 is not None
}

# The investigation time (years) each city's precomputed curve's
# "mean_poe_Tyr" column is a probability of exceedance over. San Jose's
# CRSHM2022 job.ini used 50 years directly; Guatemala's CCA and Santo
# Domingo's DR model both use annual (1-year) rates instead, converted
# here rather than at precompute time so the raw precomputed data stays
# a direct, checkable copy of what calc_hazard_curves() returned.
INVESTIGATION_TIME_YEARS_BY_CITY: dict[str, float] = {
    city: profile.investigation_time_years
    for city, profile in CITIES.items()
    if profile.investigation_time_years is not None
}

# A city is "supported" once its precomputed CSV actually exists, not
# just because it has an entry in the per-city constants above (those
# describe every model this project has integrated the input data for;
# the CSV only exists once its offline precomputation has actually run).
PSHA_SUPPORTED_CITIES: frozenset[str] = frozenset(
    city for city in REFERENCE_VS30_BY_CITY if (_DATA_DIR / f"{city}.csv").exists()
)

# Same idea, for the separate {city}_disagg.csv files (see
# docs/disaggregation_plan.md): PGA disaggregation by magnitude/distance
# bin, at each of RETURN_PERIODS_YEARS, computed via
# openquake.calculators.disaggregation reusing each city's own classical
# PSHA precalc (hazard_calculation_id).
DISAGG_SUPPORTED_CITIES: frozenset[str] = frozenset(
    city for city in REFERENCE_VS30_BY_CITY if (_DATA_DIR / f"{city}_disagg.csv").exists()
)

# Common structural-code return periods (years). 475yr / 10%-in-50yr is
# the traditional "life safety" design level (e.g. ASCE 7's older basis,
# most legacy seismic codes); 975yr / 5%-in-50yr and 2475yr / 2%-in-50yr
# are the "collapse prevention"-tier levels newer codes (ASCE 7-16+,
# Eurocode 8) also check against.
RETURN_PERIODS_YEARS: tuple[int, ...] = (475, 975, 2475)

# PGA has no associated spectral period; placed at a small nonzero period
# for log-period interpolation purposes only (Sa(T) is approximately
# flat and close to PGA for T below ~0.1s anyway).
_PGA_PROXY_PERIOD_S = 0.01

_SA_PERIOD_RE = re.compile(r"^SA\(([\d.]+)\)$")


def _imt_to_period_s(imt: str) -> float:
    if imt == "PGA":
        return _PGA_PROXY_PERIOD_S
    m = _SA_PERIOD_RE.match(imt)
    if not m:
        raise ValueError(f"Unrecognised IMT string: {imt!r}")
    return float(m.group(1))


def return_period_to_target_poe(return_period_years: float, investigation_time_years: float) -> float:
    """Probability of exceedance in the curve's own investigation time
    for a given return period, assuming a Poisson occurrence process
    (standard PSHA assumption): P = 1 - exp(-t/Tr)."""
    return 1.0 - math.exp(-investigation_time_years / return_period_years)


@lru_cache(maxsize=8)
def _hazard_curves(city: str) -> dict[str, dict[str, tuple[np.ndarray, np.ndarray]]]:
    """{imt: {"mean"/"p16"/"p84": (levels ascending, poe descending)}}
    for a city. "p16"/"p84" are only present for cities whose CSV
    carries those columns (see docs/psha_plan.md section 9)."""
    path = _DATA_DIR / f"{city}.csv"
    raw: dict[str, dict[str, list[tuple[float, float]]]] = {}
    with path.open() as f:
        reader = csv.DictReader(f)
        stat_columns = [c for c in reader.fieldnames or [] if c.endswith("_poe")]
        for row in reader:
            imt = row["imt"]
            level = float(row["level"])
            for col in stat_columns:
                stat = col.removesuffix("_poe")
                raw.setdefault(imt, {}).setdefault(stat, []).append((level, float(row[col])))
    curves: dict[str, dict[str, tuple[np.ndarray, np.ndarray]]] = {}
    for imt, by_stat in raw.items():
        curves[imt] = {}
        for stat, pairs in by_stat.items():
            pairs.sort(key=lambda p: p[0])
            levels = np.array([p[0] for p in pairs])
            poe = np.array([p[1] for p in pairs])
            curves[imt][stat] = (levels, poe)
    return curves


def _invert_curve(levels: np.ndarray, poe: np.ndarray, target_poe: float) -> float:
    """The intensity level at which the hazard curve crosses
    target_poe, by log-level interpolation (levels ascending, poe
    monotonically descending from ~1 to ~0)."""
    target = min(max(target_poe, float(poe[-1])), float(poe[0]))
    poe_ascending = poe[::-1]
    log_levels_ascending = np.log(levels[::-1])
    log_level = np.interp(target, poe_ascending, log_levels_ascending)
    return float(math.exp(log_level))


def sa_by_period_for_return_period(
    city: str, return_period_years: float, percentile: str = "mean"
) -> dict[float, float]:
    """{period_s: Sa(T) in g, at the reference Vs30} for every
    precomputed IMT, at the intensity level whose probability of
    exceedance (over that city's own investigation time) matches the
    given return period. percentile is "mean" (the logic-tree-weighted
    mean, always present), or "p16"/"p84" where available."""
    curves = _hazard_curves(city)
    investigation_time = INVESTIGATION_TIME_YEARS_BY_CITY[city]
    target_poe = return_period_to_target_poe(return_period_years, investigation_time)
    result = {}
    for imt, by_stat in curves.items():
        if percentile not in by_stat:
            continue
        levels, poe = by_stat[percentile]
        result[_imt_to_period_s(imt)] = _invert_curve(levels, poe, target_poe)
    return result


def available_percentiles(city: str) -> list[str]:
    curves = _hazard_curves(city)
    stats: set[str] = set()
    for by_stat in curves.values():
        stats.update(by_stat)
    return sorted(stats)


def hazard_curve(city: str, imt: str = "PGA") -> dict[str, list[float]] | None:
    """Raw precomputed hazard curve for one IMT, for charting: {"levels":
    [...], "mean": [...poe...], "p16": [...], "p84": [...]} (levels
    ascending; p16/p84 only where available). None if that IMT isn't in
    this city's precomputed data (e.g. an unrecognised imt argument)."""
    curves = _hazard_curves(city)
    by_stat = curves.get(imt)
    if by_stat is None or "mean" not in by_stat:
        return None
    levels, _ = by_stat["mean"]
    result: dict[str, list[float]] = {"levels": levels.tolist()}
    for stat in ("mean", "p16", "p84"):
        if stat in by_stat:
            result[stat] = by_stat[stat][1].tolist()
    return result


def pga_hazard_percentiles(city: str, return_period_years: float) -> dict[str, float]:
    """{"mean"/"p16"/"p84": PGA in g at the reference Vs30} for the given
    return period: the epistemic (GMPE logic-tree) spread already present
    in the hazard curve itself (see module docstring), read directly off
    the precomputed CSV with no per-building computation. Distinct from
    the Monte Carlo module's aleatory P10-P90 bands, which this pairs
    with in the UI as a second, differently-sourced uncertainty range."""
    result: dict[str, float] = {}
    for percentile in available_percentiles(city):
        sa_by_period = sa_by_period_for_return_period(city, return_period_years, percentile)
        if _PGA_PROXY_PERIOD_S in sa_by_period:
            result[percentile] = sa_by_period[_PGA_PROXY_PERIOD_S]
    return result


def _interp_sa_at_period(sa_by_period: dict[float, float], period_s: float) -> float:
    """Log-period, log-Sa interpolation across the precomputed spectral
    ordinates (standard practice for response spectra), flat below the
    shortest precomputed period / beyond the longest."""
    periods = np.array(sorted(sa_by_period))
    sa = np.array([sa_by_period[p] for p in periods])
    clamped = min(max(period_s, float(periods[0])), float(periods[-1]))
    log_sa = np.interp(math.log(clamped), np.log(periods), np.log(sa))
    return float(math.exp(log_sa))


def _controlling_event(city: str, return_period_years: int) -> tuple[float, float] | None:
    """(mean_magnitude, mean_distance_km) from disaggregation() below, or
    None if this (city, return_period_years) has no precomputed
    disaggregation. A typed wrapper since disaggregation()'s dict
    return type is shared with the API response shape."""
    controlling = disaggregation(city, return_period_years)
    if controlling is None:
        return None
    return float(controlling["mean_magnitude"]), float(controlling["mean_distance_km"])  # type: ignore[arg-type]


def _vs30_amplification_factor(
    city: str, return_period_years: float, building_lat: float, building_lon: float, vs30: float, period_s: float
) -> float:
    """Ratio of GMPE median Sa at the building's real Vs30 vs. the
    reference Vs30 the hazard curves were computed at, evaluated at
    magnitude/distance and evaluated at that return period's own
    disaggregated controlling magnitude/distance (disaggregation() below)
    when available, rather than one fixed representative event. The
    disaggregated event is genuinely specific to (city, return_period),
    e.g. San Jose's 475yr event differs from its 2475yr event (see
    docs/disaggregation_plan.md's results table). Falls back to that
    city's DSHA scenario (scenario.py) if disaggregation data isn't
    available for this (city, return_period_years): a city can have a
    PSHA hazard curve without a disaggregation run yet. Depth/regime/
    rake/ztor still come from the DSHA scenario either way:
    disaggregation only gives magnitude/distance, not those. Recomputing
    full PSHA per Vs30 value (rather than this GMPE-ratio approximation)
    is still not practical at this project's compute budget (see module
    docstring)."""
    base = SCENARIOS[city]
    reference_vs30 = REFERENCE_VS30_BY_CITY[city]
    controlling = _controlling_event(city, int(return_period_years))
    if controlling is not None:
        magnitude, distance_km = controlling
    else:
        magnitude = base.magnitude
        distance_km = haversine_km(base.epicenter_lat, base.epicenter_lon, building_lat, building_lon)
    at_building_vs30 = ground_motion_at_period(
        magnitude, distance_km, base.depth_km, base.tectonic_regime, period_s, vs30,
        rake=base.rake, ztor_km=base.ztor_km,
    )
    at_reference_vs30 = ground_motion_at_period(
        magnitude, distance_km, base.depth_km, base.tectonic_regime, period_s, reference_vs30,
        rake=base.rake, ztor_km=base.ztor_km,
    )
    if at_reference_vs30.median_sa_g <= 0:
        return 1.0
    return at_building_vs30.median_sa_g / at_reference_vs30.median_sa_g


def sa_at_period_psha(
    city: str,
    return_period_years: float,
    period_s: float,
    building_lat: float,
    building_lon: float,
    vs30: float,
) -> float:
    sa_by_period = sa_by_period_for_return_period(city, return_period_years)
    sa_reference_site = _interp_sa_at_period(sa_by_period, period_s)
    amplification = _vs30_amplification_factor(
        city, return_period_years, building_lat, building_lon, vs30, period_s
    )
    return sa_reference_site * amplification


def build_demand_spectrum_psha(
    city: str,
    return_period_years: float,
    building_lat: float,
    building_lon: float,
    vs30: float,
) -> DemandSpectrum:
    sa_by_period = sa_by_period_for_return_period(city, return_period_years)
    sa_g = []
    for period_s in SPECTRUM_PERIODS_S:
        sa_reference_site = _interp_sa_at_period(sa_by_period, period_s)
        amplification = _vs30_amplification_factor(
            city, return_period_years, building_lat, building_lon, vs30, period_s
        )
        sa_g.append(sa_reference_site * amplification)
    # See module docstring: aleatory variability is already integrated
    # into the hazard curve, so there is no separate GMPE sigma left to
    # report here (unlike DSHA's DemandSpectrum, built from one GMPE
    # call per period).
    sigma_ln = [0.0] * len(SPECTRUM_PERIODS_S)
    return DemandSpectrum(periods_s=SPECTRUM_PERIODS_S, sa_g=tuple(sa_g), sigma_ln=tuple(sigma_ln))


@lru_cache(maxsize=8)
def _disagg_bins(city: str) -> dict[int, list[tuple[float, float, float]]]:
    """{return_period_years: [(mag_bin_center, dist_bin_center_km, fraction), ...]}
    for a city, PGA only (see docs/disaggregation_plan.md). fraction is
    each bin's share of the total exceedance contribution at that return
    period (normalized so they sum to ~1 per return period)."""
    path = _DATA_DIR / f"{city}_disagg.csv"
    result: dict[int, list[tuple[float, float, float]]] = {}
    with path.open() as f:
        for row in csv.DictReader(f):
            years = int(row["return_period_years"])
            result.setdefault(years, []).append(
                (float(row["mag_bin"]), float(row["dist_bin"]), float(row["fraction"]))
            )
    return result


def disaggregation(city: str, return_period_years: int) -> dict[str, object] | None:
    """The controlling magnitude/distance for this city's PGA hazard at a
    given return period: {"mean_magnitude", "mean_distance_km", "bins":
    [{"mag_bin", "dist_bin", "fraction"}, ...]}. None if this city/return
    period has no precomputed disaggregation."""
    by_rp = _disagg_bins(city)
    bins = by_rp.get(return_period_years)
    if not bins:
        return None
    total = sum(frac for _, _, frac in bins)
    mean_mag = sum(mag * frac for mag, _, frac in bins) / total
    mean_dist = sum(dist * frac for _, dist, frac in bins) / total
    return {
        "mean_magnitude": mean_mag,
        "mean_distance_km": mean_dist,
        "bins": [{"mag_bin": mag, "dist_bin": dist, "fraction": frac / total} for mag, dist, frac in bins],
    }
