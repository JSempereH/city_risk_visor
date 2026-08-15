"""Shared constants for the Vs30/population reproduction scripts. See
scripts/geodata/README.md for sources.
"""

from __future__ import annotations

from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
RAW_DIR = SCRIPTS_DIR / "_raw"  # downloaded rasters, gitignored
BACKEND_DIR = SCRIPTS_DIR.parents[1]
VS30_DATA_DIR = BACKEND_DIR / "app" / "data" / "vs30"
POPULATION_DATA_DIR = BACKEND_DIR / "app" / "data" / "population"

CITIES = ("san_jose", "guatemala", "santo_domingo", "la_guaira", "lomas_centinela")

# Building-extent margin added on every side before cropping a raster to
# a city (degrees). Matches the margin already baked into the vendored
# Vs30 CSVs (confirmed by re-deriving it from their own lon/lat range).
MARGIN_DEG = 0.1

ISO3_BY_CITY = {
    "san_jose": "cri",
    "guatemala": "gtm",
    "santo_domingo": "dom",
    "la_guaira": "ven",
    "lomas_centinela": "mex",
}

# Buildings with no recorded floor count (see app/data_loader.py) still
# need a built-volume weight for the population disaggregation below;
# 1 floor is the same kind of simple, documented fallback this project
# already uses elsewhere for missing geometry (README.md's "Data notes",
# missing heights filled with n_floors x 3m or a flat default).
DEFAULT_FLOORS_FOR_UNKNOWN = 1.0


def city_bbox(city: str, margin_deg: float = MARGIN_DEG) -> tuple[float, float, float, float]:
    """(lon_min, lat_min, lon_max, lat_max) for a city's buildings, padded
    by margin_deg on every side."""
    import sys

    sys.path.insert(0, str(BACKEND_DIR))
    from app import data_loader

    buildings = data_loader.get_buildings_by_city(city)
    lats = [b["centroid_lat"] for b in buildings]
    lons = [b["centroid_lon"] for b in buildings]
    return (
        min(lons) - margin_deg,
        min(lats) - margin_deg,
        max(lons) + margin_deg,
        max(lats) + margin_deg,
    )
