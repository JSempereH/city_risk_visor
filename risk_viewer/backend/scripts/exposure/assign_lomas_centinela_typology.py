"""Fills in `structural_system`/`code_quality` for Lomas del Centinela's
buildings with a single documented, neighborhood-wide assumption, not a
per-building classification. See scripts/exposure/README.md for the
full evidence.

Mockup-level, not a survey: no labeled sample exists for this
neighborhood to bootstrap `ml_structural_system`'s per-building
ensemble (the approach the 3 active pilot cities use, per
docs/adding_a_city.md), and building one (fieldwork or photo-by-photo
labeling) is out of scope for a mockup. Instead every building gets the
same assignment, the same pattern `build_venezuela.py` used for La
Guaira when no per-building typology source existed there either:

- `structural_system = "MCF"` (mampostería confinada / confined
  masonry), the raw taxonomy value that collapses to display class "M"
  (`app/data_loader.py`'s `STRUCTURAL_SYSTEM_REPLACEMENTS`). Confined
  masonry (block or brick walls cast between reinforced-concrete tie
  columns and beams) is Mexico's dominant residential construction
  culture, documented directly by CENAPRED's own "Manual de
  Autoconstrucción Sismorresistente de Viviendas de Mampostería",
  written specifically because self-built housing nationwide
  overwhelmingly attempts this system, often without fully meeting its
  own detailing requirements.
- `code_quality = "pre_code"`, the most conservative of this project's 4
  levels. Justified by the same regularization/self-built evidence used
  for the height estimate (see estimate_lomas_centinela_heights.py):
  self-built housing that predates formal permitting is not engineered
  to a code edition. A comparable peri-urban colonia in the same
  Guadalajara metro area, Tlajomulco de Zúñiga, was found in academic
  literature to be predominantly unreinforced masonry, "extremely
  vulnerable" (see README.md), which if anything makes `pre_code` the
  less conservative of the two plausible readings, not an overcautious
  one.

Both raw values collapse to the same display class ("M") either way, so
this choice does not change which capacity/fragility tier the buildings
land on (`app/vulnerability`'s masonry GPR tier), only the
`structural_system` label shown in the building panel.

Real uncertainty, not fabricated confidence: this is a single label for
every building, not a per-building estimate with a confidence score.
Follows La Guaira's own precedent of flagging that explicitly in the
eventual `CityProfile.typology_beta_generic` (see docs/adding_a_city.md
and build_venezuela.py's README section), not attempted here since no
`CityProfile` exists yet for this neighborhood.

Usage (from backend/, after build_lomas_centinela.py has already run):
uv run python scripts/exposure/assign_lomas_centinela_typology.py
"""

from __future__ import annotations

from lib import EXPOSURE_GPKG_PATH

CITY = "lomas_centinela"

GENERIC_STRUCTURAL_SYSTEM = "MCF"
GENERIC_CODE_QUALITY = "pre_code"


def assign() -> None:
    import geopandas as gpd

    # See estimate_lomas_centinela_heights.py's estimate() for why this
    # falls back to the vendored path once the .new.gpkg staging file
    # has been reviewed and promoted.
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

    already_set = mask & gdf["structural_system"].notna()
    if already_set.any():
        print(f"{CITY}: {already_set.sum()} building(s) already have a real structural_system, left untouched")

    to_fill = mask & gdf["structural_system"].isna()
    gdf.loc[to_fill, "structural_system"] = GENERIC_STRUCTURAL_SYSTEM
    gdf.loc[to_fill, "code_quality"] = GENERIC_CODE_QUALITY
    print(
        f"{CITY}: set structural_system={GENERIC_STRUCTURAL_SYSTEM!r}, code_quality={GENERIC_CODE_QUALITY!r} "
        f"(neighborhood-wide estimate, see this script's docstring) on {int(to_fill.sum())} building(s)"
    )

    gdf = gpd.GeoDataFrame(gdf, crs="EPSG:4326")
    gdf.to_file(new_path, driver="GPKG")
    print(f"updated {new_path} in place")


if __name__ == "__main__":
    assign()
