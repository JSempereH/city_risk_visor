"""Fills in `n_floors`/`height` for Lomas del Centinela's buildings
(written by build_lomas_centinela.py, still null after that script) with
a single documented, city-wide estimate, not a per-building measurement.
See scripts/exposure/README.md for the full evidence and the sources
that were checked and rejected as automatable per-building height
sources.

Mockup-level, not a survey: this project's usual per-building height
sources (a labeled sample, a LiDAR-derived height raster, a municipal
cadastre with construction levels) were checked for this neighborhood
and none panned out cheaply, see README.md. What's used instead is a
single low-rise estimate for every building, justified by evidence that
is real but neighborhood-wide, not per-building:

- IIEG's 2020 census for this colonia (GEOCOL=120018): 2,339 total
  dwellings against the 2,215 building footprints found by
  build_lomas_centinela.py, a roughly 1:1 ratio consistent with
  predominantly single-family, single-unit-per-building construction
  (a colonia of multi-story multi-family buildings would show
  meaningfully more dwellings than buildings).
- Zapopan municipal records: a COMUR (Comisión Municipal de
  Regularización) resolution regularizing an irregular lot in this same
  area, and a 2026 municipal paving/water-infrastructure project
  description for ~23,000 residents here, both consistent with a
  self-built, incrementally regularized "colonia popular", the typical
  profile for which is low-rise (1-2 floors), not the profile of a
  planned mid/high-rise development.
- Direct visual check: a wide-area satellite image of the whole colonia
  (ArcGIS World Imagery, see `_fetch_reference_imagery()` below, no API
  key needed) shows an organic, non-gridded street layout and small,
  densely packed rooflines with no tall-building silhouettes anywhere in
  the neighborhood, i.e. a single visual pass over the whole area rather
  than checking buildings one by one.

Usage (from backend/, after build_lomas_centinela.py has already run):
uv run python scripts/exposure/estimate_lomas_centinela_heights.py
"""

from __future__ import annotations

import urllib.request

from lib import EXPOSURE_GPKG_PATH, RAW_DIR

CITY = "lomas_centinela"
CITY_RAW_DIR = RAW_DIR / "lomas_centinela"

# Deliberately lower than app/data_loader.py's project-wide 3.0m
# METRES_PER_FLOOR: that default matches the other 3 cities' more
# formal construction, but this neighborhood's own pre_code/informal
# assumption (see assign_lomas_centinela_typology.py) implies shorter
# floor-to-floor heights too. 2.5m sits at the "optimal comfort" figure
# cited in Mexico's own building code (RCDF, Reglamento de
# Construcciones para la Ciudad de México, Art. 106: 2.30m minimum
# habitable height, 2.40-2.60m recommended for social/mid-level
# housing), not a fabricated number. Lowered from the original 3.0m
# after a real street-level photo of the neighborhood showed several
# 2-story buildings that a 3.0m-per-floor conversion of GBA's real
# heights (see apply_gba_heights_lomas_centinela.py) was undercounting
# as 1-story.
METRES_PER_FLOOR = 2.5
N_FLOORS_ASSUMED = 1.0

# Same bbox build_lomas_centinela.py's boundary polygon covers (IIEG
# GEOCOL=120018), just for a documentation image, not used for any
# computation below.
BOUNDARY_BBOX = (-103.3717, 20.7546, -103.3571, 20.7711)  # minlon, minlat, maxlon, maxlat
IMAGERY_URL = (
    "https://services.arcgisonline.com/arcgis/rest/services/World_Imagery/MapServer/export"
    f"?bbox={','.join(str(v) for v in BOUNDARY_BBOX)}&bboxSR=4326&size=1400,1400"
    "&format=png32&f=image"
)


def _fetch_reference_imagery() -> None:
    """Downloads the same satellite image used to visually sanity-check the
    low-rise assumption above, so it's kept as reviewable evidence rather
    than an unverifiable claim. Not read back or parsed by this script."""
    dest = CITY_RAW_DIR / "reference_satellite.png"
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(IMAGERY_URL, headers={"User-Agent": "risk_viewer-exposure-fetch/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as f:
        f.write(resp.read())
    print(f"{CITY}: saved reference imagery to {dest}")


def estimate() -> None:
    import geopandas as gpd

    _fetch_reference_imagery()

    # A fresh build (build_lomas_centinela.py's output not yet reviewed
    # and promoted to replace the vendored file, see that script's
    # docstring) still has this city's rows in the .new.gpkg staging
    # file; once promoted, that file no longer exists and the vendored
    # path itself has the rows instead (e.g. re-running this script to
    # apply a revised assumption, as happened once already, see
    # METRES_PER_FLOOR's comment above).
    staging_path = EXPOSURE_GPKG_PATH.with_suffix(".new.gpkg")
    new_path = staging_path if staging_path.exists() else EXPOSURE_GPKG_PATH
    if not new_path.exists():
        raise FileNotFoundError(
            f"neither {staging_path} nor {EXPOSURE_GPKG_PATH} found, run build_lomas_centinela.py first"
        )

    gdf = gpd.read_file(new_path)
    mask = gdf["city"] == CITY
    if not mask.any():
        raise RuntimeError(f"no city={CITY!r} rows in {new_path}, run build_lomas_centinela.py first")

    already_set = mask & gdf["n_floors"].notna()
    if already_set.any():
        print(f"{CITY}: {already_set.sum()} building(s) already have a real n_floors, left untouched")

    to_fill = mask & gdf["n_floors"].isna()
    gdf.loc[to_fill, "n_floors"] = N_FLOORS_ASSUMED
    gdf.loc[to_fill, "height"] = N_FLOORS_ASSUMED * METRES_PER_FLOOR
    print(
        f"{CITY}: set n_floors={N_FLOORS_ASSUMED:.0f}, height={N_FLOORS_ASSUMED * METRES_PER_FLOOR:.1f}m "
        f"(city-wide estimate, see this script's docstring) on {int(to_fill.sum())} building(s)"
    )

    gdf = gpd.GeoDataFrame(gdf, crs="EPSG:4326")
    gdf.to_file(new_path, driver="GPKG")
    print(f"updated {new_path} in place")


if __name__ == "__main__":
    estimate()
