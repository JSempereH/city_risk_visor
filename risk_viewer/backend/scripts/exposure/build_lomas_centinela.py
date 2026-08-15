"""Builds Lomas del Centinela (Zapopan, Guadalajara metro, Mexico)'s
footprint layer and merges it into the combined exposure GeoPackage. See
scripts/exposure/README.md for the full source evaluation (including
what was tried and rejected) and docs/adding_a_city.md for what still
has to happen after this script (structural typology, floor counts,
hazard) before this neighborhood can actually be added to app/cities.py.

This is a neighborhood, not a city: the "city" value here is just the
join key this codebase already uses for any geographic group of
buildings (see app/cities.py's own docstring), it does not imply a
whole city was surveyed.

Boundary: IIEG Jalisco's "Colonias INE 2024" catalog, colonia
GEOCOL=120018 ("Lomas del Centinela", Zapopan). Chosen over OSM because
OSM only has an unbounded point for this neighborhood, no polygon (see
README.md).

Footprints: Microsoft Global ML Building Footprints only. OpenStreetMap
was checked first (this codebase's usual first candidate, see
build_venezuela.py) and rejected: every OSM-tagged building in a bbox
around this neighborhood turned out, on precise clipping, to sit outside
the official boundary polygon (0 of 431 candidates), i.e. OSM has no
real coverage of this specific colonia, not just sparse attributes.
Google Open Buildings v3 was also considered and rejected for a
different reason: its only public tiling granularity (S2 level 4) means
a ~1.7GB download for one small neighborhood, and Microsoft's
per-quadkey tiles already gave clean, plausible-looking coverage
(2,215 buildings inside the boundary vs. 2,339 total dwellings in the
2020 census for this same colonia, see README.md), so the marginal value
didn't justify the download.

No height, floor count, or structural typology in this dataset: Microsoft's
`height` field is `-1.0` (its own "unknown" sentinel) for every building
here, same as everywhere it lacks LiDAR/stereo coverage. Those stay null,
same convention as `n_floors`/`height` elsewhere in this codebase (see
app/data_loader.py's METRES_PER_FLOOR fallback), and are follow-up work,
not something this script fabricates.

Usage (from backend/): uv run python scripts/exposure/build_lomas_centinela.py
"""

from __future__ import annotations

import gzip
import json
import math
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from lib import EXPOSURE_GPKG_PATH, RAW_DIR

CITY = "lomas_centinela"
CITY_RAW_DIR = RAW_DIR / "lomas_centinela"

IIEG_COLONIAS_URL = "https://iieg.gob.mx/ns/wp-content/uploads/2024/11/SHAPEColonias20202024.zip"
COLONIA_GEOCOL = "120018"  # "Lomas del Centinela", Zapopan (IIEG Colonias INE 2024)

MS_DATASET_LINKS_URL = "https://minedbuildings.z5.web.core.windows.net/global-buildings/dataset-links.csv"
MS_QUADKEY_ZOOM = 9

OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def _download(url: str, dest: Path, timeout: int = 180) -> Path:
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "risk_viewer-exposure-fetch/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest, "wb") as f:
        f.write(resp.read())
    return dest


def _fetch_boundary():
    """Returns the "Lomas del Centinela" colonia polygon (EPSG:4326) from
    IIEG's Colonias INE 2024 catalog."""
    import geopandas as gpd

    zip_path = _download(IIEG_COLONIAS_URL, CITY_RAW_DIR / "colonias_ine2024.zip")
    extract_dir = CITY_RAW_DIR / "colonias_ine2024"
    shp_path = extract_dir / "ISDC2020_2024.shp"
    if not shp_path.exists():
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_dir)

    colonias = gpd.read_file(shp_path)
    match = colonias[colonias["GEOCOL"] == COLONIA_GEOCOL].to_crs("EPSG:4326")
    if len(match) != 1:
        raise RuntimeError(
            f"expected exactly 1 colonia with GEOCOL={COLONIA_GEOCOL}, found {len(match)}"
        )
    row = match.iloc[0]
    print(
        f"{CITY}: boundary = {row['NOMCOL1']!r} ({row['MUNICIPIO']}, CP {row['CP']}, "
        f"POBTOT={row['POBTOT']}, VIVTOT={row['VIVTOT']})"
    )
    return match.geometry.iloc[0]


def _check_osm_coverage(boundary) -> None:
    """Queries OSM buildings in the boundary's bbox and reports how many
    actually fall inside it, precisely clipped. Documents the finding
    (near-zero coverage as of this writing) rather than assuming it silently;
    OSM is not used as a footprint source here, see this module's docstring.
    Purely informational: the Overpass public instance is flaky under load,
    so a failure here is logged and skipped rather than aborting the build,
    it doesn't affect the Microsoft-derived footprints below."""
    import geopandas as gpd
    from shapely.geometry import Polygon

    minlon, minlat, maxlon, maxlat = boundary.bounds
    query = (
        f"[out:json][timeout:60];"
        f"(way[\"building\"]({minlat},{minlon},{maxlat},{maxlon});"
        f"relation[\"building\"]({minlat},{minlon},{maxlat},{maxlon}););"
        f"out geom;"
    )
    data = urllib.parse.urlencode({"data": query}).encode()
    req = urllib.request.Request(
        OVERPASS_URL, data=data, headers={"User-Agent": "risk_viewer-exposure-fetch/1.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            result = json.load(resp)
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        print(f"{CITY}: OSM check skipped, Overpass request failed ({exc}); see README.md for the recorded result")
        return

    polys = []
    for el in result["elements"]:
        if el["type"] == "way" and "geometry" in el:
            coords = [(pt["lon"], pt["lat"]) for pt in el["geometry"]]
            if len(coords) >= 4 and coords[0] == coords[-1]:
                polys.append(Polygon(coords).buffer(0))
    gdf = gpd.GeoDataFrame(geometry=polys, crs="EPSG:4326")
    inside = int(gdf.geometry.centroid.within(boundary).sum()) if len(gdf) else 0
    print(
        f"{CITY}: OSM check: {len(gdf)} tagged building way(s) in the bbox, "
        f"{inside} with centroid inside the official boundary (not used as a source, see README.md)"
    )


def _quadkey(lat: float, lon: float, zoom: int) -> str:
    sin_lat = math.sin(lat * math.pi / 180)
    x = (lon + 180) / 360
    y = 0.5 - math.log((1 + sin_lat) / (1 - sin_lat)) / (4 * math.pi)
    n = 2**zoom
    tile_x, tile_y = int(x * n), int(y * n)
    digits = []
    for i in range(zoom, 0, -1):
        digit = 0
        mask = 1 << (i - 1)
        if tile_x & mask:
            digit += 1
        if tile_y & mask:
            digit += 2
        digits.append(str(digit))
    return "".join(digits)


def _quadkeys_for_bounds(minlon: float, minlat: float, maxlon: float, maxlat: float) -> set[str]:
    corners = [(minlat, minlon), (minlat, maxlon), (maxlat, minlon), (maxlat, maxlon)]
    return {_quadkey(lat, lon, MS_QUADKEY_ZOOM) for lat, lon in corners}


def _fetch_microsoft_footprints(boundary):
    """Downloads the Microsoft Global ML Building Footprints tile(s)
    (per-quadkey) covering the boundary's bbox, clips precisely to the
    boundary polygon, and returns a GeoDataFrame of real footprint
    geometry, no attributes beyond `height` (Microsoft's own -1.0 =
    "unknown" sentinel for this area)."""
    import geopandas as gpd
    from shapely.geometry import shape

    links_path = _download(MS_DATASET_LINKS_URL, CITY_RAW_DIR / "ms_dataset_links.csv")
    links = {}
    with open(links_path) as f:
        next(f)  # header
        for line in f:
            location, quadkey, url, *_ = line.rstrip("\n").split(",")
            if location == "Mexico":
                links[quadkey] = url

    quadkeys = _quadkeys_for_bounds(*boundary.bounds)
    envelope = boundary.envelope
    rows = []
    for qk in sorted(quadkeys):
        if qk not in links:
            raise RuntimeError(f"no Microsoft Mexico tile found for quadkey {qk}")
        tile_path = _download(links[qk], CITY_RAW_DIR / f"ms_{qk}.csv.gz", timeout=300)
        print(f"{CITY}: reading Microsoft tile {qk} ({tile_path.stat().st_size / 1e6:.1f} MB)")
        with gzip.open(tile_path, "rt") as f:
            for line in f:
                rec = json.loads(line)
                geom = shape(rec["geometry"])
                if envelope.intersects(geom):
                    rows.append({"height": rec["properties"]["height"], "geometry": geom})

    gdf = gpd.GeoDataFrame(rows, crs="EPSG:4326")
    gdf["_wkb"] = gdf.geometry.apply(lambda g: g.wkb)
    before = len(gdf)
    gdf = gdf.drop_duplicates(subset="_wkb").drop(columns="_wkb").reset_index(drop=True)
    if before != len(gdf):
        print(f"{CITY}: dropped {before - len(gdf)} duplicate geometrie(s) from overlapping tiles")

    within = gdf[gdf.geometry.centroid.within(boundary)].reset_index(drop=True)
    print(f"{CITY}: {len(within)} Microsoft footprints inside the official boundary (of {len(gdf)} near it)")
    return within


def build() -> None:
    import geopandas as gpd
    import numpy as np
    import pandas as pd

    boundary = _fetch_boundary()
    _check_osm_coverage(boundary)
    footprints = _fetch_microsoft_footprints(boundary)

    # This codebase's ingestion (app/data_loader.py, via footprint_attributes)
    # requires single Polygon geometries, not MultiPolygon. Microsoft's data
    # was already all-Polygon for this tile as of this writing, but explode
    # defensively, same as build_venezuela.py.
    footprints = footprints.explode(index_parts=False).reset_index(drop=True)
    footprints["geometry"] = footprints["geometry"].make_valid()

    sliver_area_m2 = footprints.geometry.to_crs(footprints.estimate_utm_crs()).area
    n_slivers = int((sliver_area_m2 < 1.0).sum())
    if n_slivers:
        print(f"{CITY}: dropping {n_slivers} degenerate sliver geometry part(s) (<1 sq m)")
        footprints = footprints[sliver_area_m2 >= 1.0].reset_index(drop=True)

    n = len(footprints)
    result = gpd.GeoDataFrame(
        {
            "id": [f"{CITY}_{i}" for i in range(n)],
            "city": CITY,
            # Not yet known for any building here: floor counts, real height,
            # construction year, code era, roof material, and structural
            # typology are all follow-up work (see docs/adding_a_city.md),
            # not fabricated by this script.
            "n_floors": np.full(n, np.nan),
            "height": np.full(n, np.nan),
            "year": np.full(n, np.nan),
            "code_quality": None,
            "roof_material": None,
            "structural_system": None,
            "observed_damage_pct": np.full(n, np.nan),
            "observed_damaged": np.full(n, np.nan),
            "observed_damage_unknown_pct": np.full(n, np.nan),
            "geometry": footprints["geometry"],
        },
        crs="EPSG:4326",
    )

    print(f"{CITY}: {n} building footprints ready (geometry only, no attributes yet)")

    existing = gpd.read_file(EXPOSURE_GPKG_PATH)
    for col in ("observed_damage_pct", "observed_damaged", "observed_damage_unknown_pct"):
        if col not in existing.columns:
            existing[col] = np.full(len(existing), np.nan)
    combined = pd.concat([existing, result], ignore_index=True)
    combined = gpd.GeoDataFrame(combined, crs="EPSG:4326")

    out_path = EXPOSURE_GPKG_PATH.with_suffix(".new.gpkg")
    combined.to_file(out_path, driver="GPKG")
    print(
        f"wrote {out_path} ({len(combined)} total buildings, {n} new). "
        f"Review before replacing {EXPOSURE_GPKG_PATH.name}."
    )


if __name__ == "__main__":
    build()
