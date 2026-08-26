"""Fills in `structural_system`/`code_quality` for Lomas del Centinela's
buildings. See scripts/exposure/README.md for the full evidence.

No labeled sample exists for this neighborhood itself to bootstrap
`ml_structural_system`'s per-building ensemble the way the 3 pilot
cities' own per-city models do (per docs/adding_a_city.md); building one
(fieldwork or photo-by-photo labeling) is out of scope for a mockup.
Instead, most buildings get a per-building ML estimate from a model
POOLED across the 3 pilot cities (`ml_structural_system/experiments/
sjose_guatemala_sdomingo/risk_viewer_models/lomas_centinela/config.yaml`),
flagged `structural_system_estimated` like any other ensemble estimate
(see `app/data_loader.py::_fill_unlabeled_from_ensemble`) but ALSO
`locally_validated=False` (see `app/typology_ensemble/loader.py::
get_ensemble_quality_metrics`, absent for this city on purpose): a
distribution-shift check run against that pooled model
(`risk_viewer_models/lomas_centinela/drift_report.txt`) found 27/30
features significantly shifted between Lomas and the 3 training cities,
a two-sample classifier AUC of 0.9997 (near-perfect separability), and a
negative inter-model Fleiss' kappa (-0.30, the 3 models agree with each
other WORSE than chance on this population) -- real warning signs this
model is being asked to extrapolate well outside what it was trained on,
not evidence to hide by omission. The UI surfaces this via
`locally_validated` rather than presenting these per-building guesses
with the same footing as the 3 pilot cities' own validated estimates.

The ~54 buildings the pooled model's own inference step had to drop
(missing `year`, `mlss infer`'s own hard requirement -- see
risk_viewer_models/lomas_centinela/infer.log) still fall back to the
same single documented, neighborhood-wide assumption used before any
ensemble existed for this city, the same pattern `build_venezuela.py`
used for La Guaira when no per-building typology source existed there
either:

- `structural_system = "MUR"` (mampostería sin refuerzo / unreinforced
  masonry), the exposure dataset's own raw GEM Building Taxonomy value
  (kept as its own `structural_system_class`, not collapsed into the
  generic "M" bucket, see `app/data_loader.py`'s
  `STRUCTURAL_SYSTEM_REPLACEMENTS`). Corrected from an earlier "MCF"
  (confined masonry) assignment after the user asked directly where
  that choice came from: the original reasoning leaned on CENAPRED's
  "Manual de Autoconstrucción Sismorresistente de Viviendas de
  Mampostería" documenting that self-built housing nationwide
  *attempts* confined masonry, but underweighted that same manual's own
  caveat ("often without fully meeting its own detailing requirements")
  and the area-comparable study cited two lines below for `code_quality`
  (Preciado & Rodriguez 2015 on Tlajomulco de Zuniga), which was never
  actually about confined masonry at all: it documents unreinforced
  fired-brick walls with deficient-or-no confinement, plus some
  traditional adobe, calling the housing stock "extremely vulnerable".
  National census context: 92.4% of Mexican dwellings have tabique/
  block/concrete walls (INEGI ENVI 2020), arguing against adobe being
  *predominant* here specifically, even though it's part of the
  Tlajomulco mix; no colonia-level wall-material field exists in IIEG's
  own census layer for Lomas del Centinela to check directly (only
  floor material is present there: ~4-7% dirt floor, itself a real but
  moderate, not extreme, poverty indicator). MUR is the better-supported
  single label given this: it matches what the comparable-area study
  actually found (unreinforced/deficiently-confined masonry behavior),
  not what CENAPRED's manual says self-built housing merely *attempts*.
- `code_quality = "pre_code"`, the most conservative of this project's 4
  levels. Justified by the same regularization/self-built evidence used
  for the height estimate (see estimate_lomas_centinela_heights.py):
  self-built housing that predates formal permitting is not engineered
  to a code edition. Preciado, D. & Rodriguez, R. (2015), "Vulnerabilidad
  sismica de viviendas de mamposteria no reforzada en el pueblo de
  Tlajomulco, Jalisco", XX Congreso Nacional de Ingenieria Sismica
  (SMIS), Acapulco -- a comparable peri-urban colonia in the same
  Guadalajara metro area -- found predominantly unreinforced masonry
  (fired brick with deficient or no confinement) plus traditional
  adobe, "extremely vulnerable" to the region's seismicity (Tlajomulco
  is in CFE seismic zone C), which if anything makes `pre_code` the
  less conservative of the two plausible readings, not an overcautious
  one.

MUR and MCF now route to their own separate published GEM fragility
curves (`app/vulnerability/gem_fragility.py`), MCF noticeably less
fragile than MUR at most damage states -- so, unlike when this script
was first written (when both collapsed into the same generic "M" class
and its ML capacity-model tier), this choice does now change modeled
damage, not just the label shown in the building panel.

Real uncertainty, not fabricated confidence, either way: the ~54
fallback buildings get a single label, not a per-building estimate with
a confidence score (same `CityProfile.typology_beta_generic` precedent
as La Guaira, see docs/adding_a_city.md and build_venezuela.py's README
section); the pooled-model majority does get a per-building estimate,
but explicitly not treated as confident, real ground truth (see
`locally_validated` above).

Usage (from backend/, after build_lomas_centinela.py has already run,
and after the pooled ensemble's predictions.csv has been vendored into
app/data/typology_ensemble/lomas_centinela/, see scripts/psha/README.md's
sibling vendoring convention):
uv run python scripts/exposure/assign_lomas_centinela_typology.py

Idempotent, safe to re-run against an already-assigned gpkg: buildings
the pooled ensemble covers always end up with `structural_system` left
NULL (so `app/data_loader.py::_fill_unlabeled_from_ensemble` fills them
from the ensemble at runtime instead), buildings it doesn't always end
up with the GENERIC_STRUCTURAL_SYSTEM fallback, `code_quality` is set to
GENERIC_CODE_QUALITY for the whole neighborhood either way (the ensemble
never estimates code_quality, only structural_system). Originally this
script blanket-filled every building including the ~2,161 the ensemble
now covers, back when no pooled model existed yet for this city; that
fill was corrected in place on the already-committed
`all_cities_combined.gpkg` when the pooled ensemble above was added, the
same direct-edit precedent as the earlier MCF -> MUR correction.
"""

from __future__ import annotations

import csv

from lib import BACKEND_DIR, EXPOSURE_GPKG_PATH

CITY = "lomas_centinela"

GENERIC_STRUCTURAL_SYSTEM = "MUR"
GENERIC_CODE_QUALITY = "pre_code"

ENSEMBLE_PREDICTIONS_PATH = BACKEND_DIR / "app" / "data" / "typology_ensemble" / CITY / "predictions.csv"


def _ensemble_covered_ids() -> set[str]:
    if not ENSEMBLE_PREDICTIONS_PATH.exists():
        return set()
    with open(ENSEMBLE_PREDICTIONS_PATH) as f:
        return {row["id"] for row in csv.DictReader(f)}


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

    covered_ids = _ensemble_covered_ids()
    ensemble_covered = mask & gdf["id"].isin(covered_ids)
    fallback = mask & ~gdf["id"].isin(covered_ids)

    # Clear structural_system for ensemble-covered buildings even if a
    # prior run of this script (pre-dating the pooled ensemble) already
    # blanket-filled them -- _fill_unlabeled_from_ensemble only ever
    # substitutes for a real gap, never overrides a recorded value.
    already_estimated = ensemble_covered & gdf["structural_system"].notna()
    gdf.loc[ensemble_covered, "structural_system"] = None
    if already_estimated.any():
        print(
            f"{CITY}: cleared structural_system on {int(already_estimated.sum())} ensemble-covered building(s) "
            "so the ML estimate (not a blanket fallback) applies at runtime"
        )

    gdf.loc[fallback, "structural_system"] = GENERIC_STRUCTURAL_SYSTEM
    gdf.loc[mask, "code_quality"] = GENERIC_CODE_QUALITY
    print(
        f"{CITY}: {int(ensemble_covered.sum())} building(s) left for the ML ensemble to estimate, "
        f"{int(fallback.sum())} building(s) set to the neighborhood-wide structural_system="
        f"{GENERIC_STRUCTURAL_SYSTEM!r} fallback; code_quality={GENERIC_CODE_QUALITY!r} set on all "
        f"{int(mask.sum())}"
    )

    gdf = gpd.GeoDataFrame(gdf, crs="EPSG:4326")
    gdf.to_file(new_path, driver="GPKG")
    print(f"updated {new_path} in place")


if __name__ == "__main__":
    assign()
