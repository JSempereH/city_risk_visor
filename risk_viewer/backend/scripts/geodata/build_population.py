"""Disaggregates WorldPop's per-cell population estimate to individual
buildings, weighted by built volume (footprint area x floor count), and
writes app/data/population/{city}.csv (building_id,resident_population).
See app/risk/population.py's own module docstring for how this data is
used downstream, and scripts/geodata/README.md for the source.

Buildings whose own raster cell has no data under WorldPop's built-up-
area mask (e.g. Guatemala City's ravines) snap to the nearest cell that
does, rather than getting a zero, see app/risk/population.py's
docstring for why.

Usage (from backend/): uv run python scripts/geodata/build_population.py [city ...]
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from lib import CITIES, DEFAULT_FLOORS_FOR_UNKNOWN, ISO3_BY_CITY, POPULATION_DATA_DIR, RAW_DIR, city_bbox

BACKEND_DIR = Path(__file__).resolve().parents[2]
WORLDPOP_URL_TEMPLATE = (
    "https://data.worldpop.org/GIS/Population/Global_2000_2020_Constrained/2020/BSGM/"
    "{ISO3}/{iso3}_ppp_2020_UNadj_constrained.tif"
)


def _fetch_raster(city: str) -> Path:
    import urllib.request

    iso3 = ISO3_BY_CITY[city]
    dest = RAW_DIR / f"{iso3}_ppp_2020_UNadj_constrained.tif"
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = WORLDPOP_URL_TEMPLATE.format(ISO3=iso3.upper(), iso3=iso3)
    print(f"{city}: downloading {url}")
    urllib.request.urlretrieve(url, dest)
    return dest


def build_city(city: str) -> None:
    import numpy as np
    import rasterio

    sys.path.insert(0, str(BACKEND_DIR))
    from app import data_loader

    raster_path = _fetch_raster(city)
    buildings = data_loader.get_buildings_by_city(city)
    lon_min, lat_min, lon_max, lat_max = city_bbox(city)

    with rasterio.open(raster_path) as src:
        window = rasterio.windows.from_bounds(lon_min, lat_min, lon_max, lat_max, transform=src.transform)
        window = window.round_offsets().round_lengths()
        grid = src.read(1, window=window)
        win_transform = src.window_transform(window)
        nodata = src.nodata

    grid = grid.astype(float)
    if nodata is not None:
        grid[grid == nodata] = np.nan
    grid[grid < 0] = np.nan  # WorldPop uses small negative sentinels in some tiles too
    populated_mask = ~np.isnan(grid)
    populated_rows, populated_cols = np.nonzero(populated_mask)

    def cell_for(lon: float, lat: float) -> tuple[int, int] | None:
        row, col = rasterio.transform.rowcol(win_transform, lon, lat)
        if 0 <= row < grid.shape[0] and 0 <= col < grid.shape[1] and populated_mask[row, col]:
            return row, col
        if populated_rows.size == 0:
            return None
        # Nearest populated cell by simple Euclidean distance in
        # row/col space (grid cells are ~100m square here, so this is
        # close enough to a true nearest-neighbour-in-metres search for
        # the handful of buildings that ever need it).
        dist_sq = (populated_rows - row) ** 2 + (populated_cols - col) ** 2
        nearest = int(np.argmin(dist_sq))
        return int(populated_rows[nearest]), int(populated_cols[nearest])

    built_volume: dict[str, float] = {}
    assigned_cell: dict[str, tuple[int, int]] = {}
    for b in buildings:
        floors = b["n_floors"] if b["n_floors"] is not None else DEFAULT_FLOORS_FOR_UNKNOWN
        built_volume[b["id"]] = b["footprint_area_m2"] * floors
        cell = cell_for(b["centroid_lon"], b["centroid_lat"])
        if cell is not None:
            assigned_cell[b["id"]] = cell

    volume_by_cell: dict[tuple[int, int], float] = {}
    for building_id, cell in assigned_cell.items():
        volume_by_cell[cell] = volume_by_cell.get(cell, 0.0) + built_volume[building_id]

    out_csv = POPULATION_DATA_DIR / f"{city}.csv"
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    n_written = 0
    with open(out_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["building_id", "resident_population"])
        for building_id, cell in assigned_cell.items():
            cell_population = float(grid[cell])
            share = built_volume[building_id] / volume_by_cell[cell]
            writer.writerow([building_id, f"{cell_population * share:.4f}"])
            n_written += 1
    print(f"{city}: wrote {out_csv} ({n_written}/{len(buildings)} buildings)")


def main() -> None:
    cities = sys.argv[1:] or list(CITIES)
    for city in cities:
        build_city(city)


if __name__ == "__main__":
    main()
