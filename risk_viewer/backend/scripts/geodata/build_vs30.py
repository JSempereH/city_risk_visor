"""Crops the USGS Global Vs30 Map to each city's building extent and
writes app/data/vs30/{city}.csv (lon,lat,vs30_ms). See
app/hazard/site.py's own module docstring for how this data is used, and
scripts/geodata/README.md for the source.

Streams the crop via GDAL's /vsicurl/ virtual filesystem (confirmed the
USGS server supports HTTP range requests): only the few hundred KB
covering each city are actually downloaded, not the full ~610 MB global
grid.

Usage (from backend/): uv run python scripts/geodata/build_vs30.py [city ...]
"""

from __future__ import annotations

import csv
import sys

from lib import CITIES, VS30_DATA_DIR, city_bbox

VS30_GRID_URL = "/vsicurl/https://apps.usgs.gov/shakemap_geodata/vs30/global_vs30.grd"


def build_city(city: str) -> None:
    import numpy as np
    import rasterio
    from rasterio.windows import from_bounds

    lon_min, lat_min, lon_max, lat_max = city_bbox(city)

    with rasterio.open(VS30_GRID_URL) as src:
        window = from_bounds(lon_min, lat_min, lon_max, lat_max, transform=src.transform)
        window = window.round_offsets().round_lengths()
        data = src.read(1, window=window)
        win_transform = src.window_transform(window)

    rows, cols = data.shape
    row_idx = np.arange(rows).repeat(cols)
    col_idx = np.tile(np.arange(cols), rows)
    xs, ys = rasterio.transform.xy(win_transform, row_idx, col_idx)
    values = data.flatten()

    out_csv = VS30_DATA_DIR / f"{city}.csv"
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    n_written = 0
    with open(out_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["lon", "lat", "vs30_ms"])
        for x, y, v in zip(xs, ys, values):
            if np.isnan(v):
                continue
            writer.writerow([f"{x:.6f}", f"{y:.6f}", f"{float(v):.1f}"])
            n_written += 1
    print(f"{city}: wrote {out_csv} ({n_written} grid points)")


def main() -> None:
    cities = sys.argv[1:] or list(CITIES)
    for city in cities:
        build_city(city)


if __name__ == "__main__":
    main()
