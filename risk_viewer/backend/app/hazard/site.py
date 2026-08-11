"""Per-building Vs30 from the USGS Global Vs30 Map Server (Wald & Allen,
2007, "Topographic Slope as a Proxy for Seismic Site Conditions and
Amplification", BSSA 97(5); Allen & Wald, 2009), a topographic-slope-based
Vs30 estimate at 30-arcsecond resolution with global coverage.

The full global grid
(https://apps.usgs.gov/shakemap_geodata/vs30/global_vs30.grd, ~610 MB) was
cropped to each city's building extent plus a margin and reduced to its
raw (longitude, latitude, Vs30) grid points, stored in
`app/data/vs30/{city}.csv` (a few hundred KB per city rather than the
global raster), reproducible via `scripts/geodata/build_vs30.py`, see
that directory's README.md. Each building's Vs30 is the nearest grid
point to its centroid, so it varies across a city instead of using one
flat value.

Vs30 is fed directly into the GMPEs in gmpe.py, which each include their
own published Vs30 site-response term, so there is no separate
amplification step here.
"""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

import numpy as np

_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "vs30"

DEFAULT_VS30_FALLBACK = 280.0


@lru_cache(maxsize=8)
def _grid(city: str) -> np.ndarray | None:
    """(N, 3) array of (lon, lat, vs30_ms) grid points for a city, or None
    if that city has no cropped grid (see module docstring)."""
    path = _DATA_DIR / f"{city}.csv"
    if not path.exists():
        return None
    with path.open() as f:
        rows = [(float(r["lon"]), float(r["lat"]), float(r["vs30_ms"])) for r in csv.DictReader(f)]
    return np.array(rows)


def vs30_at(city: str, lat: float, lon: float) -> float:
    grid = _grid(city)
    if grid is None:
        return DEFAULT_VS30_FALLBACK
    dist_sq = (grid[:, 0] - lon) ** 2 + (grid[:, 1] - lat) ** 2
    return float(grid[np.argmin(dist_sq), 2])


def default_vs30(city: str) -> float:
    """City-wide average Vs30, for contexts with no specific coordinate
    (e.g. a legend or a city missing its cropped grid)."""
    grid = _grid(city)
    if grid is None:
        return DEFAULT_VS30_FALLBACK
    return float(grid[:, 2].mean())
