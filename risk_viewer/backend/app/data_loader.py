"""Loads the exposure/typology demo dataset once and serves it from memory.

The dataset (~2811 building footprints, ~2MB as GeoJSON) is small enough
that there is no need for a database, lazy loading, or per-request disk
I/O: it is read once at first access and cached for the process lifetime.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

import geopandas as gpd
import pandas as pd
from footprint_attributes import position as fp_position

from app.config import DATA_PATH
from app.typology_ensemble import get_ensemble_info

UNLABELED = "unlabeled"

# Mirrors ml_structural_system's own label_replacements (see
# ml_structural_system/experiments/sjose_guatemala_sdomingo/main.yaml),
# which collapses the raw structural_system values into 4 classes for
# training. Reused here for display consistency, but unlike the training
# pipeline (which drops rare/unlabeled rows), every building must still
# render on the map, so missing values get an explicit "unlabeled" class
# instead of being dropped.
STRUCTURAL_SYSTEM_REPLACEMENTS = {
    "S_light": "W",
    "S_frame": "CR",
    "MUR": "M",
    "MCF": "M",
    "MR": "M",
}


def _collapse_structural_system(raw: Any) -> str:
    if raw is None or (isinstance(raw, float)) or str(raw).strip() == "":
        return UNLABELED
    return STRUCTURAL_SYSTEM_REPLACEMENTS.get(raw, str(raw))


def _blank_to_unlabeled(raw: Any) -> Any:
    if raw is None or (isinstance(raw, float)) or str(raw).strip() == "":
        return UNLABELED
    return raw


def _fill_unlabeled_from_ensemble(gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    """For buildings with no recorded structural_system, substitutes the
    typology classifier ensemble's own prediction (see
    app/typology_ensemble/loader.py) where one exists, flagged as an
    estimate rather than recorded data via structural_system_estimated.

    Only fills genuine gaps: a building with a real recorded class keeps
    it untouched (and structural_system_estimated stays False for it)
    even if an ensemble prediction also exists for it. Uses majority_vote
    (the simple 2-of-3-models class), not ensemble_pred (a separate
    soft-voting figure, averaged predicted probability across the 3
    models rather than a vote count): the vulnerability panel's own
    "model agreement" section shows each model's individual vote and an
    agreement_ratio computed the same hard-vote way, so majority_vote is
    the figure that actually matches what a person sees broken out there
    (ensemble_pred can, on a close call, name a different class than the
    2-of-3 majority a viewer would read off that same panel).
    """
    structural_system_class = gdf["structural_system_class"].copy()
    estimated = pd.Series(False, index=gdf.index)
    for idx, row in gdf.iterrows():
        if structural_system_class.loc[idx] != UNLABELED:
            continue
        ensemble = get_ensemble_info(row["id"], row["city"])
        if ensemble is None:
            continue
        structural_system_class.loc[idx] = ensemble.majority_vote
        estimated.loc[idx] = True
    return pd.DataFrame(
        {"structural_system_class": structural_system_class, "structural_system_estimated": estimated}
    )


# Fallback building height (m) for buildings with no recorded height/floor
# count, used only to weight footprint_attributes' contact-force
# computation. It does not affect the displayed "height" attribute.
DEFAULT_HEIGHT_FOR_POSITION_M = 6.0
METRES_PER_FLOOR = 3.0


def _compute_relative_position(gdf: gpd.GeoDataFrame) -> pd.Series:
    """Real geometry-derived block position (isolated/lateral/corner/
    confined/torque) per building, via footprint_attributes.position().

    Computed per city (each reprojected to its own local UTM zone) rather
    than on the whole 3-city GeoDataFrame at once: touching detection is
    metric, and one shared UTM zone across cities as far apart as
    Guatemala City and Santo Domingo would badly distort distances.
    """
    height_for_position = gdf["height"].astype(float)
    floors_estimate = gdf["n_floors"].astype(float) * METRES_PER_FLOOR
    height_for_position = height_for_position.fillna(floors_estimate)
    height_for_position = height_for_position.fillna(DEFAULT_HEIGHT_FOR_POSITION_M)

    working = gdf[["geometry", "city"]].copy()
    working["_height_for_position"] = height_for_position

    # footprint_attributes.position() resets the index internally (see
    # geometry.py::to_gdf) but preserves row order, so results are
    # reattached by position, not by label, then assigned back by the
    # subset's original (global) index.
    result = pd.Series(index=gdf.index, dtype=object)
    for city in working["city"].dropna().unique():
        subset = working[working["city"] == city]
        classified = fp_position(
            subset, columns=["relativePosition"], height_column="_height_for_position"
        )
        result.loc[subset.index] = classified["relativePosition"].values
    return result


def _compute_geometry_metrics(gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    """Real centroid (lat/lon) and footprint area (m^2) per building.

    Area needs a projected (metric) CRS; computed per city, each
    reprojected to its own local UTM zone, for the same reason as
    ``_compute_relative_position``.
    """
    lat = pd.Series(index=gdf.index, dtype=float)
    lon = pd.Series(index=gdf.index, dtype=float)
    area_m2 = pd.Series(index=gdf.index, dtype=float)

    for city in gdf["city"].dropna().unique():
        subset = gdf[gdf["city"] == city]
        projected = subset.geometry.to_crs(subset.estimate_utm_crs())
        area_m2.loc[subset.index] = projected.area.values

        centroids_wgs84 = projected.centroid.to_crs(subset.crs)
        lat.loc[subset.index] = centroids_wgs84.y.values
        lon.loc[subset.index] = centroids_wgs84.x.values

    return pd.DataFrame({"centroid_lat": lat, "centroid_lon": lon, "footprint_area_m2": area_m2})


@lru_cache(maxsize=1)
def load_geodataframe() -> gpd.GeoDataFrame:
    gdf = gpd.read_file(DATA_PATH)
    gdf["structural_system_class"] = gdf["structural_system"].apply(_collapse_structural_system)
    gdf[["structural_system_class", "structural_system_estimated"]] = _fill_unlabeled_from_ensemble(gdf)
    for column in ("code_quality", "roof_material"):
        gdf[column] = gdf[column].apply(_blank_to_unlabeled)
    gdf["relative_position"] = _compute_relative_position(gdf)
    gdf = gdf.join(_compute_geometry_metrics(gdf))
    return gdf


def _row_to_dict(row: pd.Series) -> dict[str, Any]:
    return {
        "id": row["id"],
        "city": row["city"],
        "n_floors": None if pd.isna(row["n_floors"]) else float(row["n_floors"]),
        "height": None if pd.isna(row["height"]) else float(row["height"]),
        "structural_system_class": row["structural_system_class"],
        # True when structural_system_class came from the typology
        # classifier ensemble's own prediction rather than a recorded
        # value, because the source data had none (see
        # _fill_unlabeled_from_ensemble). False for both recorded classes
        # and buildings that stayed "unlabeled" (no ensemble prediction
        # either).
        "structural_system_estimated": bool(row["structural_system_estimated"]),
        "relative_position": row["relative_position"],
        "code_quality": row["code_quality"],
        "centroid_lat": float(row["centroid_lat"]),
        "centroid_lon": float(row["centroid_lon"]),
        "footprint_area_m2": float(row["footprint_area_m2"]),
        # Real observed damage from a post-event satellite-imagery
        # classification (see scripts/exposure/README.md), null for
        # cities with none. Not a modeled quantity, kept separate from
        # expected_damage_state.
        "observed_damage_pct": None if pd.isna(row["observed_damage_pct"]) else float(row["observed_damage_pct"]),
        "observed_damaged": None if pd.isna(row["observed_damaged"]) else bool(row["observed_damaged"]),
    }


def get_building(building_id: str) -> dict[str, Any] | None:
    gdf = load_geodataframe()
    matches = gdf[gdf["id"] == building_id]
    if matches.empty:
        return None
    return _row_to_dict(matches.iloc[0])


def get_buildings_by_city(city: str) -> list[dict[str, Any]]:
    gdf = load_geodataframe()
    subset = gdf[gdf["city"] == city]
    return [_row_to_dict(row) for _, row in subset.iterrows()]


def feature_collection(city: str | None = None) -> dict[str, Any]:
    gdf = load_geodataframe()
    if city:
        gdf = gdf[gdf["city"] == city]
    return json.loads(gdf.to_json())


def known_cities() -> list[str]:
    gdf = load_geodataframe()
    return sorted(gdf["city"].dropna().unique().tolist())


def attribute_domain(attribute: str) -> list[Any]:
    """Sorted list of distinct values for a categorical attribute, `unlabeled` last."""
    gdf = load_geodataframe()
    values = sorted(v for v in gdf[attribute].dropna().unique().tolist() if v != UNLABELED)
    if UNLABELED in gdf[attribute].unique().tolist():
        values.append(UNLABELED)
    return values
