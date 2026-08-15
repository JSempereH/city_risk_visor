"""Refines Lomas del Centinela's uniform height estimate (set by
estimate_lomas_centinela_heights.py) with real per-building heights from
GlobalBuildingAtlas (TUM), where a confident match exists. See
scripts/exposure/README.md for the full evidence, licensing caveat, and
why this wasn't the first choice for this neighborhood.

Run order: build_lomas_centinela.py, then
estimate_lomas_centinela_heights.py (uniform baseline for every
building), then this script (overwrites that baseline for buildings
with a real GBA match; buildings with no match keep the uniform
estimate).

Why this needed a full-tile download instead of a windowed read: GBA's
raster height product (GBA.Height, would support cheap windowed reads
the same way this project already streams Vs30/WorldPop, see
scripts/geodata/build_vs30.py) is hosted on mediaTUM behind an
always-on bot-detection challenge (Anubis) that blocks scripted access
entirely, confirmed by direct testing, not just an assumption. The
JSON-keyed alternative (GBA.LoD1, this script's actual source) was
checked for a range-request shortcut before committing to the full
download: a byte-offset probe (decoding the Google Plus Codes embedded
in a sample of building IDs at 9 offsets across the 1.38GB file, see
this conversation's history) confirmed entries are geographically
clustered only in small local batches, scattered with no global sort
order across the file, so there's no way to isolate one neighborhood's
data with a partial download; a near-complete download is genuinely
required.

Every OSM-sourced GBA entry is skipped, not just Google-sourced ones:
this project's own live Overpass check for this neighborhood (see
build_lomas_centinela.py's `_check_osm_coverage()`) found ~0 real OSM
building coverage here, so `osm...`-keyed GBA entries for this specific
area would be equally sparse or absent, and their IDs don't encode a
usable coordinate the way a Google Plus Code does (would need the
separate, even larger, GBA.Polygon geometry file to locate them).
Google-sourced entries alone are assumed to cover this neighborhood
adequately; not verified against a ground truth, same mockup-level
caveat as the rest of this neighborhood's data.

License: GBA.Height/LoD1 is CC BY-NC 4.0 (non-commercial), confirmed
from the dataset's own README. Check this is compatible with this
project's actual use before treating this as more than a mockup input.

Accuracy caveat: the GlobalBuildingAtlas paper reports height RMSE of
1.5-8.9m across continents (5.5m global average), a margin comparable
to the very difference this data is meant to resolve (a 1-story house
is ~3m, a 2-story one ~6m). Real per-building variation, not a
precision improvement guaranteed to beat the uniform estimate it
replaces; kept anyway per this neighborhood's own docs/user decision.

Usage (from backend/, after build_lomas_centinela.py and
estimate_lomas_centinela_heights.py have both already run):
uv run python scripts/exposure/apply_gba_heights_lomas_centinela.py
"""

from __future__ import annotations

import re
import urllib.request
from pathlib import Path

from lib import EXPOSURE_GPKG_PATH, RAW_DIR

CITY = "lomas_centinela"
CITY_RAW_DIR = RAW_DIR / "lomas_centinela"

GBA_TILE_URL = (
    "https://huggingface.co/datasets/zhu-xlab/GBA.LoD1/resolve/main/"
    "LoD1/northamerica/w105_n25_w100_n20.json"
)
GBA_TILE_PATH = CITY_RAW_DIR / "gba_lod1_w105_n25_w100_n20.json"

# 2.5m, not this project's project-wide 3.0m default (app/data_loader.py),
# matching estimate_lomas_centinela_heights.py's own reasoning: this
# neighborhood's informal/pre_code housing profile implies shorter
# floor-to-floor heights, and Mexico's own building code (RCDF Art. 106)
# cites 2.30m as the minimum habitable height, 2.40-2.60m as the
# recommended comfort range for social/mid-level housing. Lowered from
# 3.0m after real GBA heights, converted with the original 3.0m divisor,
# undercounted 2-story buildings visible in a real street-level photo of
# the neighborhood (round(5m / 3.0) still gives 2 floors, but a real
# 2-story building under ~4.5m, plausible at 2.5m/floor, used to round
# down to 1).
METRES_PER_FLOOR = 2.5

# Sanity bounds: GBA occasionally reports implausible heights (ground
# noise, misdetections); outside this range a match is dropped rather
# than trusted, real buildings here are 1-3 stories per the visual/
# census evidence in README.md, not skyscrapers or literal ground level.
MIN_PLAUSIBLE_HEIGHT_M = 1.5
MAX_PLAUSIBLE_HEIGHT_M = 30.0

# A decoded 10-digit Plus Code is the SW corner of a ~14m x 13m grid
# cell (see this script's docstring for how this was verified, and the
# bug this constant used to paper over), not a building centroid; this
# is the max distance to a footprint centroid for a match to be
# trusted, generous enough to absorb that cell's diagonal (~19m) plus
# real digitisation differences between GBA's source footprints and
# Microsoft's (this neighborhood's own footprint source, see
# build_lomas_centinela.py), while still tight enough that it won't
# usually cross into a neighboring building in this dense colonia.
MAX_MATCH_DISTANCE_M = 25.0

_PLUS_CODE_ALPHABET = "23456789CFGHJMPQRVWX"
_ENTRY_RE = re.compile(
    r'"google([23456789CFGHJMPQRVWX]{8})\+([23456789CFGHJMPQRVWX]{2,7})MEX"'
    r':\s*\{"height":\s*([-0-9.eE]+),\s*"var":\s*([-0-9.eE]+)\}'
)


def _decode_pluscode(code8: str, suffix: str) -> tuple[float, float]:
    """Decodes a 10-significant-digit Open Location Code (Plus Code, the
    8-character prefix plus the first 2 characters after the '+') to its
    grid cell's SW corner (lat, lon). Standard OLC "pair stage" algorithm,
    deliberately reimplemented here (no extra dependency for a dozen lines
    of arithmetic).

    A first version of this function only decoded the 8-character prefix,
    which is a real bug this project's own user caught by comparing
    against a street-level photo: an 8-digit code alone is a ~278m x 260m
    cell (city-block scale), not the commonly-cited "Plus Codes are
    accurate to 14m", which refers to the 10-digit code, i.e. the 2 digits
    right after the '+' that the previous version silently discarded.
    That meant every "match" below was really being tested against a point
    that could be up to ~270m from the actual building, while the match
    radius was only 20m, so confirmed matches were close to what pure
    chance would produce (~1.8% of footprints, area of a 20m circle over
    a 278x260m cell), not real matches. Fixed by decoding 10 digits (~14m
    x 13m cell) instead of 8; digits beyond the 10th (further "grid stage"
    refinement, a different, non-pair encoding) are still ignored, not
    needed once the cell is already smaller than MAX_MATCH_DISTANCE_M."""
    code10 = code8 + suffix[:2]
    lat, lon = -90.0, -180.0
    lat_res, lon_res = 400.0, 400.0
    for i in range(10):
        digit = _PLUS_CODE_ALPHABET.index(code10[i])
        if i % 2 == 0:
            lat_res /= 20
            lat += digit * lat_res
        else:
            lon_res /= 20
            lon += digit * lon_res
    return lat, lon


def _download_gba_tile() -> Path:
    if GBA_TILE_PATH.exists():
        return GBA_TILE_PATH
    GBA_TILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    print(f"{CITY}: downloading GBA tile (~1.4GB, this takes a while, cached afterward)")
    req = urllib.request.Request(GBA_TILE_URL, headers={"User-Agent": "risk_viewer-exposure-fetch/1.0"})
    with urllib.request.urlopen(req, timeout=3600) as resp, open(GBA_TILE_PATH, "wb") as f:
        while chunk := resp.read(1 << 20):
            f.write(chunk)
    return GBA_TILE_PATH


def _extract_points_in_bbox(tile_path: Path, minlon: float, minlat: float, maxlon: float, maxlat: float):
    """Streams the (huge, single-line) GBA JSON file in overlapping chunks,
    regex-extracting google-sourced {id: {height, var}} entries without a
    full JSON parse (avoids holding the whole ~1.4GB structure in memory).
    A 200-char overlap between chunks catches matches split across a
    chunk boundary; re.finditer naturally dedupes since a full match can
    only be found once even if its bytes appear in both the tail of one
    chunk and the head of the next."""
    chunk_size = 64 * 1024 * 1024
    overlap = 200
    tail = ""
    points = []
    n_seen = 0
    with open(tile_path, "r", encoding="utf-8", errors="ignore") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            text = tail + chunk
            for m in _ENTRY_RE.finditer(text):
                n_seen += 1
                lat, lon = _decode_pluscode(m.group(1), m.group(2))
                if minlat <= lat <= maxlat and minlon <= lon <= maxlon:
                    height = float(m.group(3))
                    var = float(m.group(4))
                    points.append({"lat": lat, "lon": lon, "height": height, "var": var})
            tail = text[-overlap:]
    print(f"{CITY}: scanned {n_seen} Google-sourced GBA entries total, {len(points)} inside the padded bbox")
    return points


def apply_gba_heights() -> None:
    import geopandas as gpd
    import pandas as pd
    from shapely.geometry import Point

    new_path = EXPOSURE_GPKG_PATH
    gdf = gpd.read_file(new_path)
    mask = gdf["city"] == CITY
    if not mask.any():
        raise RuntimeError(f"no city={CITY!r} rows in {new_path}, run build_lomas_centinela.py first")

    footprints = gdf[mask].copy()
    minlon, minlat, maxlon, maxlat = footprints.total_bounds
    pad = 0.01  # ~1km, generous margin for the Plus Code SW-corner offset
    tile_path = _download_gba_tile()
    points = _extract_points_in_bbox(tile_path, minlon - pad, minlat - pad, maxlon + pad, maxlat + pad)
    if not points:
        print(f"{CITY}: no GBA points found near this neighborhood, leaving the uniform estimate as-is")
        return

    plausible = [
        p for p in points if MIN_PLAUSIBLE_HEIGHT_M <= p["height"] <= MAX_PLAUSIBLE_HEIGHT_M
    ]
    print(f"{CITY}: {len(plausible)} of {len(points)} GBA points pass the plausible-height sanity check")

    gba_points = gpd.GeoDataFrame(
        plausible,
        geometry=[Point(p["lon"], p["lat"]) for p in plausible],
        crs="EPSG:4326",
    )

    utm = footprints.estimate_utm_crs()
    footprints_utm = footprints.to_crs(utm)
    footprints_utm["geometry"] = footprints_utm.geometry.centroid
    gba_points_utm = gba_points.to_crs(utm)

    joined = gpd.sjoin_nearest(
        footprints_utm, gba_points_utm, how="left", max_distance=MAX_MATCH_DISTANCE_M, distance_col="_dist_m"
    )
    # A footprint can have more than one GBA point within range (dense
    # small houses); keep the closest.
    joined = joined.sort_values("_dist_m").drop_duplicates(subset="id", keep="first")
    matched = joined[joined["height_right"].notna()]
    print(f"{CITY}: {len(matched)} of {len(footprints)} footprints matched to a GBA point within {MAX_MATCH_DISTANCE_M:.0f}m")

    height_by_id = dict(zip(matched["id"], matched["height_right"]))
    var_by_id = dict(zip(matched["id"], matched["var"]))

    real_height = gdf.loc[mask, "id"].map(height_by_id)
    n_updated = int(real_height.notna().sum())
    gdf.loc[mask, "height"] = real_height.combine_first(gdf.loc[mask, "height"])
    gdf.loc[mask, "n_floors"] = real_height.apply(
        lambda h: max(1.0, round(h / METRES_PER_FLOOR)) if pd.notna(h) else None
    ).combine_first(gdf.loc[mask, "n_floors"])

    mean_var = sum(var_by_id.values()) / len(var_by_id) if var_by_id else float("nan")
    print(
        f"{CITY}: replaced the uniform estimate on {n_updated} building(s) with real GBA heights "
        f"(mean reported variance {mean_var:.2f} m^2), {len(footprints) - n_updated} building(s) "
        f"keep the neighborhood-wide uniform estimate (no confident GBA match)"
    )

    gdf = gpd.GeoDataFrame(gdf, crs="EPSG:4326")
    gdf.to_file(new_path, driver="GPKG")
    print(f"updated {new_path} in place")


if __name__ == "__main__":
    apply_gba_heights()
