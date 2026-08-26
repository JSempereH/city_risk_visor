"""Fills Lomas del Centinela's `year` column with real per-building
first-urbanization estimates from the `building_year` package (WSF
Evolution + GHSL, no reference data or per-city training needed -- see
../../../../building_year/README.md), replacing what was previously an
entirely empty column (0/2,215 buildings had a year).

Run order: build_lomas_centinela.py, then this script (any time after --
independent of the height/roof_material scripts).

Source run: building_year/examples/lomas_centinela_example.py
(assign="first_urbanization" only, the change-detection product isn't
needed for a single year value), writing
building_year/examples/output/LomasCentinela/buildings_results.csv.
`first_construction_year` there is WSF-primary/GHSL-fallback (see
building_year/docs/methodology.md); 2,161 of 2,215 buildings (97.6%) got
a real estimate, the remaining 54 keep `year=None` (both sources failed
sampling for those footprints, not fabricated).

Usage (from backend/, after build_lomas_centinela.py and the
building_year example run above have both already run):
uv run python scripts/exposure/apply_lomas_centinela_year.py
"""

from __future__ import annotations

from pathlib import Path

from lib import EXPOSURE_GPKG_PATH

CITY = "lomas_centinela"

BUILDING_YEAR_RESULTS_CSV = (
    Path(__file__).resolve().parents[4]
    / "building_year"
    / "examples"
    / "output"
    / "LomasCentinela"
    / "buildings_results.csv"
)


def apply_lomas_centinela_year() -> None:
    import geopandas as gpd
    import pandas as pd

    if not BUILDING_YEAR_RESULTS_CSV.exists():
        raise RuntimeError(
            f"{BUILDING_YEAR_RESULTS_CSV} not found, run "
            "building_year/examples/lomas_centinela_example.py first"
        )

    gdf = gpd.read_file(EXPOSURE_GPKG_PATH)
    mask = gdf["city"] == CITY
    if not mask.any():
        raise RuntimeError(f"no city={CITY!r} rows in {EXPOSURE_GPKG_PATH}, run build_lomas_centinela.py first")

    results = pd.read_csv(BUILDING_YEAR_RESULTS_CSV)
    year_by_id = dict(zip(results["id"], results["first_construction_year"]))

    year = gdf.loc[mask, "id"].map(year_by_id)
    n_filled = int(year.notna().sum())
    gdf.loc[mask, "year"] = year
    print(
        f"{CITY}: filled year for {n_filled} of {mask.sum()} building(s) from building_year's "
        f"first_construction_year estimate ({mask.sum() - n_filled} keep year=None, no confident "
        "WSF/GHSL sample for that footprint)"
    )

    gdf = gpd.GeoDataFrame(gdf, crs="EPSG:4326")
    gdf.to_file(EXPOSURE_GPKG_PATH, driver="GPKG")
    print(f"updated {EXPOSURE_GPKG_PATH} in place")


if __name__ == "__main__":
    apply_lomas_centinela_year()
