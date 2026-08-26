"""Fills the 42 (of 436) Guatemala City buildings missing `roof_material`
(all in zona1, see scripts/exposure/README.md) using the `roof_material`
package's reference-based (Hungarian algorithm) cluster mapping --
guatemala's other 394 buildings already have real surveyed
roof_material, used as ground truth to resolve the mapping
automatically (no manual visual judgment call, unlike
apply_lomas_centinela_roof_material.py).

Only fills genuine gaps: a building with a real recorded roof_material
is never overwritten, even though the classification pipeline predicts
a value for every building in the city (needed to fit K-means and
resolve the reference mapping).

Source run: roof_material/examples/Guatemala/guatemala_example.py,
writing roof_material/examples/Guatemala/output/buildings_roof_material.gpkg.
That output's own `id`/`building_id` columns are a renumbered sequential
integer; the int-id<->real-id mapping is recovered from
roof_material/examples/Guatemala/guatemala_footprints_intid.gpkg.

Usage (from backend/, after the roof_material example run above):
uv run python scripts/exposure/apply_guatemala_roof_material.py
"""

from __future__ import annotations

from pathlib import Path

from lib import EXPOSURE_GPKG_PATH

CITY = "guatemala"

ROOF_MATERIAL_DIR = Path(__file__).resolve().parents[4] / "roof_material" / "examples" / "Guatemala"
ROOF_MATERIAL_RESULTS_GPKG = ROOF_MATERIAL_DIR / "output" / "buildings_roof_material.gpkg"
ROOF_MATERIAL_INTID_GPKG = ROOF_MATERIAL_DIR / "guatemala_footprints_intid.gpkg"


def apply_guatemala_roof_material() -> None:
    import geopandas as gpd

    if not ROOF_MATERIAL_RESULTS_GPKG.exists() or not ROOF_MATERIAL_INTID_GPKG.exists():
        raise RuntimeError(
            f"{ROOF_MATERIAL_RESULTS_GPKG} or {ROOF_MATERIAL_INTID_GPKG} not found, run "
            "roof_material/examples/Guatemala/guatemala_example.py first"
        )

    gdf = gpd.read_file(EXPOSURE_GPKG_PATH)
    mask = gdf["city"] == CITY
    if not mask.any():
        raise RuntimeError(f"no city={CITY!r} rows in {EXPOSURE_GPKG_PATH}")

    already_recorded = mask & gdf["roof_material"].notna()
    fillable = mask & gdf["roof_material"].isna()

    intid = gpd.read_file(ROOF_MATERIAL_INTID_GPKG)
    source_id_by_intid = dict(zip(intid["id"], intid["source_id"]))

    results = gpd.read_file(ROOF_MATERIAL_RESULTS_GPKG)
    results["source_id"] = results["building_id"].map(source_id_by_intid)
    material_by_id = dict(zip(results["source_id"], results["roof_material"]))

    new_material = gdf.loc[fillable, "id"].map(material_by_id)
    n_filled = int(new_material.notna().sum())
    gdf.loc[fillable, "roof_material"] = new_material
    print(
        f"{CITY}: {already_recorded.sum()} building(s) already had real roof_material (untouched), "
        f"filled {n_filled} of {fillable.sum()} previously-missing building(s), "
        f"{fillable.sum() - n_filled} still missing (insufficient valid pixels or below confidence threshold)"
    )

    gdf = gpd.GeoDataFrame(gdf, crs="EPSG:4326")
    gdf.to_file(EXPOSURE_GPKG_PATH, driver="GPKG")
    print(f"updated {EXPOSURE_GPKG_PATH} in place")


if __name__ == "__main__":
    apply_guatemala_roof_material()
