"""Per-building resident population, from WorldPop's Global High Resolution
Population Denominators dataset (2020, 100m resolution, UN-adjusted
constrained individual-country product:
https://data.worldpop.org/GIS/Population/Global_2000_2020_Constrained/2020/BSGM/,
Guatemala/Costa Rica/Dominican Republic), disaggregated to individual
buildings via dasymetric mapping weighted by built volume (footprint area
times floor count), per this project's own master-plan doc
("desagregacion dasimetrica ponderada por volumen construido").

Each building's centroid was snapped to its nearest WorldPop raster cell
(cropped to each city's building extent) at preprocessing time; buildings
sharing a cell split that cell's population in proportion to their built
volume. The result is a small per-building CSV
(`app/data/population/{city}.csv`), not a raster, so no raster reading
happens at request time, reproducible via
`scripts/geodata/build_population.py`, see that directory's README.md
(including a note on why re-running it doesn't reproduce San
Jose's file byte-for-byte). A handful of raster cells inside these urban
extents (e.g. Guatemala City's ravines) carry no population under
WorldPop's own built-up-area mask; buildings there snap to the nearest
populated cell instead of getting a zero.

WorldPop gives one population figure per location (its residential/census
anchor), not a day/night split, so the existing HAZUS-style day/night
occupancy factor (most residential occupants away from home during the
day) is still applied on top of it. Cities or buildings with no
disaggregated figure (not in the CSV) fall back to the same floor-area
proxy this module used before WorldPop was integrated.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

TimeOfDay = Literal["day", "night"]

_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "population"

PERSONS_PER_M2 = 1.0 / 25.0  # ~25 m^2 of floor area per resident, fallback only
OCCUPANCY_FACTOR: dict[TimeOfDay, float] = {"night": 1.0, "day": 0.4}


@dataclass(frozen=True)
class PopulationEstimate:
    day: float
    night: float


@lru_cache(maxsize=8)
def _load(city: str) -> dict[str, float]:
    path = _DATA_DIR / f"{city}.csv"
    if not path.exists():
        return {}
    with path.open() as f:
        return {row["building_id"]: float(row["resident_population"]) for row in csv.DictReader(f)}


def _floor_area_proxy(footprint_area_m2: float, n_floors: float | None) -> float:
    floors = n_floors if n_floors and n_floors > 0 else 1.0
    return footprint_area_m2 * floors * PERSONS_PER_M2


def estimate_population(
    building_id: str, city: str, footprint_area_m2: float, n_floors: float | None
) -> PopulationEstimate:
    resident_population = _load(city).get(building_id)
    if resident_population is None:
        resident_population = _floor_area_proxy(footprint_area_m2, n_floors)
    return PopulationEstimate(
        day=resident_population * OCCUPANCY_FACTOR["day"],
        night=resident_population * OCCUPANCY_FACTOR["night"],
    )
