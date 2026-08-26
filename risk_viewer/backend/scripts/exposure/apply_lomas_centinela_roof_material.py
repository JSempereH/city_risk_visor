"""Fills Lomas del Centinela's `roof_material` column with per-building
classifications from the `roof_material` package (Sentinel-2 + orthophoto,
Gram-Schmidt fusion, K-means clustering -- see
../../../../roof_material/README.md), replacing what was previously an
entirely empty column (0/2,215 buildings had a value).

Run order: build_lomas_centinela.py, then this script (any time after --
independent of the height/year scripts).

Confidence caveat, important: unlike the other 3 pilot cities (guatemala,
san_jose, santo_domingo), whose roof_material is real recorded survey
data, Lomas del Centinela has no reference layer to validate against.
The cluster<->material mapping used here
(roof_material/examples/LomasCentinela/manual_cluster_mapping.yaml) is a
human visual/spectral judgment call, not a validated classification --
see that file's own extensive docstring for the evidence and reasoning
(weak silhouette score, near-parallel spectral centroids across all 4
clusters -- i.e. the clustering mostly separates on brightness, not a
distinctive per-material signature). 1,558 of 2,215 buildings (70.3%)
got a mapped value (1,202 at the `classified` confidence tier, 356 more
at the lower-confidence `low_dominance` tier -- both still carry a real
mapped material, see `classification_status` in the source gpkg to tell
them apart); the remaining 657 had too few valid pixels
(`insufficient_data`) and keep `roof_material = None`, not a fabricated
guess.

Source run: roof_material/examples/LomasCentinela/lomas_centinela_example.py,
writing roof_material/examples/LomasCentinela/output/buildings_roof_material.gpkg.
That output's own `id`/`building_id` columns are a renumbered sequential
integer (the building mask rasterizer requires an int id, see
prepare_buildings() in that example script); the int-id<->real-id mapping
doesn't survive into that output file, so it's recovered here from
roof_material/examples/LomasCentinela/lomas_centinela_footprints_intid.gpkg
(the intermediate file prepare_buildings() itself wrote, id + source_id).

Usage (from backend/, after build_lomas_centinela.py and the
roof_material example run above have both already run):
uv run python scripts/exposure/apply_lomas_centinela_roof_material.py
"""

from __future__ import annotations

from pathlib import Path

from lib import EXPOSURE_GPKG_PATH

CITY = "lomas_centinela"

ROOF_MATERIAL_DIR = Path(__file__).resolve().parents[4] / "roof_material" / "examples" / "LomasCentinela"
ROOF_MATERIAL_RESULTS_GPKG = ROOF_MATERIAL_DIR / "output" / "buildings_roof_material.gpkg"
ROOF_MATERIAL_INTID_GPKG = ROOF_MATERIAL_DIR / "lomas_centinela_footprints_intid.gpkg"


def apply_lomas_centinela_roof_material() -> None:
    import geopandas as gpd

    if not ROOF_MATERIAL_RESULTS_GPKG.exists() or not ROOF_MATERIAL_INTID_GPKG.exists():
        raise RuntimeError(
            f"{ROOF_MATERIAL_RESULTS_GPKG} or {ROOF_MATERIAL_INTID_GPKG} not found, run "
            "roof_material/examples/LomasCentinela/lomas_centinela_example.py first"
        )

    gdf = gpd.read_file(EXPOSURE_GPKG_PATH)
    mask = gdf["city"] == CITY
    if not mask.any():
        raise RuntimeError(f"no city={CITY!r} rows in {EXPOSURE_GPKG_PATH}, run build_lomas_centinela.py first")

    intid = gpd.read_file(ROOF_MATERIAL_INTID_GPKG)
    source_id_by_intid = dict(zip(intid["id"], intid["source_id"]))

    results = gpd.read_file(ROOF_MATERIAL_RESULTS_GPKG)
    results["source_id"] = results["building_id"].map(source_id_by_intid)
    material_by_id = dict(zip(results["source_id"], results["roof_material"]))

    material = gdf.loc[mask, "id"].map(material_by_id)
    n_filled = int(material.notna().sum())
    gdf.loc[mask, "roof_material"] = material
    print(
        f"{CITY}: filled roof_material for {n_filled} of {mask.sum()} building(s) from roof_material's "
        f"manually-mapped K-means classification ({mask.sum() - n_filled} keep roof_material=None -- "
        "either insufficient valid pixels or a majority cluster below the confidence threshold, "
        "not a fabricated guess)"
    )

    gdf = gpd.GeoDataFrame(gdf, crs="EPSG:4326")
    gdf.to_file(EXPOSURE_GPKG_PATH, driver="GPKG")
    print(f"updated {EXPOSURE_GPKG_PATH} in place")


if __name__ == "__main__":
    apply_lomas_centinela_roof_material()
