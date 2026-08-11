"""Builds La Guaira, Venezuela's exposure data from public HDX resources
and merges it into a new combined exposure GeoPackage. See
scripts/exposure/README.md for sources, licenses, and the reasoning
behind each modeling choice below (this is a real, cited-but-generic
regional assumption for structural typology, not a per-building
measurement, see that README and docs/adding_a_city.md).

Primary footprint source is Microsoft AI for Good Lab's building damage
assessment (`laguaira_damage.gpkg`): it already carries real per-building
polygon geometry (Overture Maps footprints) *and* real observed damage
attributes, so it doubles as both the exposure layer and the source of
`observed_damage_pct`/`observed_damaged`, no separate join needed for
those. `n_floors` is filled in from OpenStreetMap's `building_levels` tag
where it happens to be present (real but sparse: ~0.3% of buildings in
this area) via a spatial join; everywhere else it's left null, the same
"unknown" convention this project already uses elsewhere (see
app/data_loader.py's DEFAULT_HEIGHT_FOR_POSITION_M / METRES_PER_FLOOR
fallback).

Usage (from backend/): uv run python scripts/exposure/build_venezuela.py
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

from lib import EXPOSURE_GPKG_PATH, RAW_DIR

DAMAGE_URL = (
    "https://data.humdata.org/dataset/bace623a-d4c1-42d2-b6c1-6d25d492da14/resource/"
    "2c08dd20-3408-4bae-8913-a2c8378445c2/download/"
    "la_guaira_and_surrounding_vantor_6-26_building_predictions_merged_1.gpkg"
)
OSM_BUILDINGS_URL = "https://production-raw-data-api.s3.amazonaws.com/ISO3/VEN/buildings/hot_eq_osm_ven_buildings_osm_gpkg.zip"

CITY = "la_guaira"

# Post-event structural engineering assessments (see
# scripts/exposure/README.md for citations) identify non-ductile
# reinforced-concrete frame with masonry infill as the dominant
# construction type in La Guaira, assigned uniformly here as a real,
# cited, but city-wide (not per-building) typology assumption.
GENERIC_STRUCTURAL_SYSTEM = "CR"
# "Poorly confined columns", "critical dynamic flaws" per the same
# assessments: pre-code construction, not a modern-code building stock.
GENERIC_CODE_QUALITY = "pre_code"


def _download(url: str, dest: Path) -> Path:
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "risk_viewer-exposure-fetch/1.0"})
    with urllib.request.urlopen(req, timeout=180) as resp, open(dest, "wb") as f:
        f.write(resp.read())
    return dest


def _fetch_damage_gpkg() -> Path:
    return _download(DAMAGE_URL, RAW_DIR / "laguaira_damage.gpkg")


def _fetch_osm_buildings() -> Path:
    import zipfile

    zip_path = _download(OSM_BUILDINGS_URL, RAW_DIR / "osm_buildings.gpkg.zip")
    extracted = RAW_DIR / "buildings.gpkg"
    if not extracted.exists():
        with zipfile.ZipFile(zip_path) as zf:
            zf.extract("buildings.gpkg", RAW_DIR)
    return extracted


def build() -> None:
    import geopandas as gpd
    import pandas as pd

    damage_path = _fetch_damage_gpkg()
    print(f"{CITY}: loading {damage_path}")
    damage = gpd.read_file(damage_path, layer="out").to_crs("EPSG:4326")

    # Real polygons (Overture footprints), but MultiPolygon. This
    # project's ingestion (app/data_loader.py, via footprint_attributes)
    # requires single Polygon geometries.
    damage = damage.explode(index_parts=False).reset_index(drop=True)
    damage["geometry"] = damage["geometry"].make_valid()

    # A handful of exploded/repaired parts are degenerate slivers (<1 sq
    # m), not real buildings: distinct from genuinely small real
    # structures (informal housing units in the 10-20 sq m range are
    # common here and kept).
    sliver_area_m2 = damage.geometry.to_crs(damage.estimate_utm_crs()).area
    n_slivers = int((sliver_area_m2 < 1.0).sum())
    if n_slivers:
        print(f"{CITY}: dropping {n_slivers} degenerate sliver geometry part(s) (<1 sq m)")
        damage = damage[sliver_area_m2 >= 1.0].reset_index(drop=True)

    osm_path = _fetch_osm_buildings()
    print(f"{CITY}: loading {osm_path} (bbox-filtered)")
    bounds = damage.total_bounds  # (lon_min, lat_min, lon_max, lat_max)
    from shapely.geometry import box

    osm = gpd.read_file(osm_path, layer="buildings", mask=box(*bounds))
    osm_levels = osm[osm["building_levels"].notna() & (osm["building_levels"] != "")].copy()
    osm_levels["n_floors"] = pd.to_numeric(osm_levels["building_levels"], errors="coerce")
    osm_levels = osm_levels[osm_levels["n_floors"].notna()][["geometry", "n_floors"]]
    print(f"{CITY}: {len(osm_levels)} OSM buildings in bbox have a real building_levels tag")

    joined = gpd.sjoin(
        damage, osm_levels, how="left", predicate="intersects"
    ).drop(columns=["index_right"])
    # A damage-gpkg footprint can intersect more than one OSM building
    # (different digitisation); keep the first match per footprint id
    # rather than duplicating rows.
    joined = joined.drop_duplicates(subset="id", keep="first").reset_index(drop=True)

    import numpy as np

    n = len(joined)
    result = gpd.GeoDataFrame(
        {
            "id": [f"{CITY}_{i}" for i in range(n)],
            "city": CITY,
            "n_floors": joined["n_floors"].astype(float),
            "height": np.full(n, np.nan),
            "year": np.full(n, np.nan),
            "code_quality": GENERIC_CODE_QUALITY,
            "roof_material": None,
            "structural_system": GENERIC_STRUCTURAL_SYSTEM,
            "observed_damage_pct": joined["damage_pct_0m"].astype(float),
            "observed_damaged": joined["damaged"].astype(float) if "damaged" in joined else np.nan,
            "observed_damage_unknown_pct": joined["unknown_pct"].astype(float),
            "geometry": joined["geometry"],
        },
        crs="EPSG:4326",
    )

    print(f"{CITY}: {n} buildings, {result['n_floors'].notna().sum()} with a real floor count")

    existing = gpd.read_file(EXPOSURE_GPKG_PATH)
    for col in ("observed_damage_pct", "observed_damaged", "observed_damage_unknown_pct"):
        if col not in existing.columns:
            existing[col] = np.full(len(existing), np.nan)
    combined = pd.concat([existing, result], ignore_index=True)
    combined = gpd.GeoDataFrame(combined, crs="EPSG:4326")

    out_path = EXPOSURE_GPKG_PATH.with_suffix(".new.gpkg")
    combined.to_file(out_path, driver="GPKG")
    print(f"wrote {out_path} ({len(combined)} total buildings, {n} new). Review before replacing {EXPOSURE_GPKG_PATH.name}.")


if __name__ == "__main__":
    build()
