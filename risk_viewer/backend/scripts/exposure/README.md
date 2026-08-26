# Reproducing per-city/neighborhood exposure data

- [La Guaira, Venezuela](#reproducing-la-guairas-exposure-data)
- [Lomas del Centinela, Zapopan (Mexico)](#lomas-del-centinela-zapopan-mexico)

---

# Reproducing La Guaira's exposure data

**Currently pulled out of the live app** (2026-08-11: `app/cities.py`
has no `la_guaira` entry, `all_cities_combined.gpkg` has no
`city="la_guaira"` rows), over data-quality concerns: the city-wide
generic `CR`/`pre_code` typology assumption reads as too coarse, and the
gap between modeled and observed damage is not closed. The raw
downloads, build script, and this README are kept in place. To bring it
back:

1. `uv run python scripts/exposure/build_venezuela.py`, review the
   `.new.gpkg` diff, then replace the vendored file with it.
2. Add this `CityProfile` entry back to `app/cities.py`'s `CITIES` dict:

   ```python
   "la_guaira": CityProfile(
       city="la_guaira",
       scenario_label="Mw 7.5, 24 June 2026 Venezuela doublet mainshock",
       magnitude=7.5,
       depth_km=10.0,
       epicenter_lat=10.6221,
       epicenter_lon=-67.1935,
       tectonic_regime="crustal",
       deterministic_source_note=(
           "USGS event us6000t7zp, the Mw 7.5 mainshock of the 24 June 2026 Venezuela "
           "earthquake doublet (17 km W of Catia La Mar). Real epicenter and depth, not an "
           "illustrative point. Real observed per-building damage is available to compare "
           "against (see scripts/exposure/README.md). Strike-slip, Caribbean-South American "
           "plate boundary system (rake=0 as a simplification)."
       ),
       rake=0.0,
       # No PSHA source model integrated yet, so reference_vs30 and
       # investigation_time_years stay None.
       typology_beta_generic=0.6,
   ),
   ```

3. Restore `test_la_guaira_scenario_matches_usgs_event()` and
   `test_la_guaira_typology_beta_generic_exceeds_entropy_ceiling()` in
   `tests/test_cities.py`, add `"la_guaira"` back to
   `test_list_scenarios()`'s expected set in `tests/test_risk.py`, and
   update the expected feature count in `tests/test_smoke.py`.
4. The eager exposure-data load in `app/main.py`'s lifespan hook, and
   the `start_period` in `Dockerfile`/`docker-compose.yml`'s
   healthchecks, will need lengthening again: La Guaira's ~26k buildings
   made that data load slow (15-20 minutes cold).

---

`app/data/exposure/all_cities_combined.gpkg`'s `city="la_guaira"` rows
are built from public post-earthquake data, not vendored by hand.

## One-shot

```bash
cd backend
uv run python scripts/exposure/build_venezuela.py
```

Writes `app/data/exposure/all_cities_combined.new.gpkg`; review the diff
before replacing the vendored file.

## Why this city is different

La Guaira's building footprints and observed damage come from the
actual 24 June 2026 Mw 7.2 + Mw 7.5 Venezuela earthquake doublet
response, not a general-purpose exposure survey: a real scientific
opportunity (a modeled scenario can be compared against real observed
damage) and a real limitation (no source gives per-building
structural-typology classification).

## Sources

| Data | Source | License |
|---|---|---|
| Building footprints + observed damage | Microsoft AI for Good Lab, "Building Damage Assessment - La Guaira" (HDX). A model classifying "building"/"damaged"/"cloud"/"other" per pixel in post-event satellite imagery, joined to Overture Maps footprints. | CC BY |
| `n_floors` (where available) | OpenStreetMap footprints, `hot_eq_ven` HDX bundle. Sparse: 84 of ~26,400 buildings have a `building_levels` tag. | ODbL v1.0 |

Two other HDX resources were investigated and not used: HOTOSM's fAIr
building-detection layer turned out to be point predictions, not
footprint polygons. UNEP/OCHA's debris-assessment file's own listing
describes a modeled height attribute, but the actual download only
carries `fid` and `debris`, no height. Confirmed by reading both files'
real schemas before writing this pipeline.

## Structural typology: a city-wide assumption

No source gives per-building structural classification. A
footprint-area heuristic was tested against the 84 real
`building_levels`-tagged buildings and rejected: it correlated the wrong
way (low-rise buildings had a larger median footprint than mid/high-rise
ones, likely large low-rise port/industrial buildings). Instead, every
La Guaira building is assigned `structural_system_class = "CR"`
uniformly, per real post-event structural engineering assessments:
Loughborough University's earthquake engineering press release and
other post-event assessments identify non-ductile reinforced-concrete
frame with masonry infill as the dominant construction type in coastal
Venezuela, consistent with `code_quality = "pre_code"` (also assigned
uniformly).

This is a real, cited, but deliberately coarse city-wide typology, not a
per-building measurement. `CityProfile.typology_beta_generic` (0.6,
above the ~0.5 ceiling `typology_beta_from_entropy()` produces for the
other cities' real classifier disagreement) makes this uncertainty
explicit in the risk calculation rather than presenting the CR
assignment as confident. `roof_material` stays `unlabeled`.

## Observed damage

`observed_damage_pct` and `observed_damaged` ride along as plain
exposure attributes, null for the other 3 cities. Exposed as data only;
a dedicated modeled-vs-observed comparison view is out of scope for now.

## A real bug this city's data surfaced

Because every La Guaira building lands on the `gem_global_vulnerability`
tier, a sanity check against the deterministic scenario's modeled damage
turned up a real, pre-existing bug affecting that tier in all 4 cities:
`ground_motion.py` was converting Sa(T) demand to spectral displacement
using a generic 0.1s/floor code formula, while the GEM fragility curve's
own median thresholds were built at a different, taxonomy-specific
period, understating demand and pushing nearly every GEM-tier building
to "no damage" regardless of shaking level. Fixed 2026-08-11 (see
`app/hazard/ground_motion.py`'s `fixed_period_s`). Before the fix, La
Guaira's mainshock modeled about 0% damage for its ~26k buildings; after,
about 67% at least "slight", still well above the ~3.7% Microsoft's
model flagged as `observed_damaged` (candidate causes: the generic
typology assumption, and satellite damage classification's own known
under-detection of non-collapse damage).

## Not yet done

PSHA for La Guaira, via GEM's South America (SAM) regional model
(confirmed to cover Venezuela): only the deterministic scenario is
wired up so far.

---

# Lomas del Centinela, Zapopan (Mexico)

**Not yet in the live app.** This is only the footprint-acquisition step
(building geometry, no attributes). `app/cities.py` has no entry for
this neighborhood, and `all_cities_combined.gpkg` is not updated by
this script directly, it writes a `.new.gpkg` for review. See
`docs/adding_a_city.md`'s checklist for everything still needed
(floor counts, structural typology, deterministic scenario, PSHA)
before this can be added for real.

This is a neighborhood, not a whole city (~8,000 residents, 2020
census), added because that's what was asked for, not because the
pipeline requires city-sized units. `city="lomas_centinela"` is just
this codebase's usual join key for a geographic group of buildings.

## One-shot

```bash
cd backend
uv run python scripts/exposure/build_lomas_centinela.py
```

Downloads and caches raw sources under `scripts/exposure/_raw/lomas_centinela/`
(gitignored, ~50MB), takes a few minutes on a modest connection (two
Microsoft footprint tiles, ~17MB and ~28MB). Writes
`app/data/exposure/all_cities_combined.new.gpkg`; review the diff before
replacing the vendored file. Re-running is cheap: every download is
cached by filename and skipped if already present.

## Boundary: IIEG "Colonias INE 2024"

OpenStreetMap has no polygon for this neighborhood, only an unbounded
`place=neighbourhood` point, so an official boundary was needed to know
which buildings belong to it at all.

| Data | Source | License |
|---|---|---|
| Colonia boundary polygon | IIEG (Instituto de Información Estadística y Geográfica de Jalisco), "Colonias INE 2024" (`https://iieg.gob.mx/ns/wp-content/uploads/2024/11/SHAPEColonias20202024.zip`). 6,624 colonia polygons statewide, built on INE electoral geography validated against INEGI's 2020 census. | Public, IIEG open data portal |

`GEOCOL=120018` is "Lomas del Centinela", municipio Zapopan, CP 45180,
POBTOT (2020 census population) 8,038, VIVTOT (total dwellings) 2,339.
It sits in a zoom-9 Bing quadkey pair (`023301102`/`023301103`), i.e. the
polygon straddles two Microsoft footprint tiles, both are fetched.

The same layer carries the full 2020 census record per colonia
(household size, floor/wall material, electricity/water/drainage
access, etc.), not used by the build script (it's colonia-level, not
per-building), but worth pulling later as context for the structural
typology and code-quality work `docs/adding_a_city.md` still requires.

## Footprints: Microsoft Global ML Building Footprints

| Data | Source | License |
|---|---|---|
| Building footprint geometry | Microsoft Global ML Building Footprints, Mexico region, quadkeys `023301102`+`023301103` (`https://github.com/microsoft/GlobalMLBuildingFootprints`). Satellite-derived, ML-detected polygons. | ODbL 1.0 |

2,215 footprints fall inside the official boundary (of 3,804 found near
it across both tiles), all valid single `Polygon` geometry, no slivers,
median footprint area ~65 m². Close to VIVTOT=2,339 from the same IIEG
census record, a reasonable order-of-magnitude cross-check for a
neighborhood of mostly small detached houses (a building and a dwelling
aren't the same thing, so exact equality isn't expected).

No height or floor count: Microsoft's `height` field is its own `-1.0`
"unknown" sentinel for every building in this tile (no LiDAR/stereo
coverage here), left as a real `NaN` in the output, not fabricated.

## Sources evaluated and not used

- **OpenStreetMap.** This codebase's usual first candidate
  (`build_venezuela.py` uses it for `building_levels`), checked first
  here too via a live Overpass query
  (`_check_osm_coverage()`, run automatically by the build script,
  informational only). Result as of this writing: 0 OSM-tagged
  buildings with a centroid inside the official boundary polygon. This
  isn't a sparse-attributes problem like La Guaira's OSM data, it's a
  coverage problem: OSM has essentially no traced buildings for this
  specific colonia. (A wider, padded bounding box around the
  neighborhood's OSM point does have hundreds of tagged buildings, they
  just belong to neighboring colonias, e.g. "Bosques del Centinela",
  "Colinas del Centinela", which are separate IIEG polygons.)
- **Google Open Buildings v3.** Confirmed to cover Mexico, but its only
  public tiling granularity is S2 level 4, and the cell covering this
  area is a ~1.7GB single download (tested: ~400KB/s from this
  environment, so over an hour) for one small neighborhood. Not worth
  it given Microsoft's tiles already gave clean, census-consistent
  coverage at ~46MB combined. Worth revisiting if Microsoft's coverage
  ever looks insufficient somewhere else in this area.

## Floor counts / height: a city-wide estimate, not measured

```bash
cd backend
uv run python scripts/exposure/estimate_lomas_centinela_heights.py
```

Run after `build_lomas_centinela.py`. Fills `n_floors`/`height` for
every building in this neighborhood with a single estimate (1 floor,
3.0m, using `app/data_loader.py`'s own `METRES_PER_FLOOR` convention),
not a per-building measurement, since no cheap per-building source
panned out (see below). Mockup-level, good enough to render on the map
and drive a scenario, not a survey.

Two real per-building sources were investigated and rejected:

- **Zapopan's municipal cadastre.** No public REST/WFS/API endpoint
  found for construction-level data; the municipal digital map
  (`geomatica.zapopan.gob.mx/mxsig/`) is a static viewer with no
  discoverable service URL, and cadastral records require an in-person
  request at the municipal office. Not automatable.
- **GlobalBuildingAtlas (TUM), see the height-source discussion in the
  planning conversation for this neighborhood.** Confirmed to cover this
  area (5°×5° tile `LoD1/northamerica/w105_n25_w100_n20.json` on
  Hugging Face, `zhu-xlab/GBA.LoD1`), but that tile is 1.38GB (the
  lighter-looking `Polygon/` GeoJSON equivalent is actually *larger*,
  7.5GB, uncompressed coordinates). Same call as Google Open Buildings
  in the section above: not worth a 1+GB download for 2,215 buildings
  when the neighborhood is expected to be uniformly low-rise anyway
  (see evidence below). Worth revisiting if a real per-building height
  source is ever needed here.

What justifies the 1-floor estimate instead, real evidence, but
neighborhood-wide, not per-building (see
`estimate_lomas_centinela_heights.py`'s docstring for the full
reasoning):

- IIEG's 2020 census for this colonia: 2,339 total dwellings against
  2,215 building footprints, a roughly 1:1 ratio consistent with
  single-family, single-unit-per-building construction.
- Zapopan municipal records: a COMUR resolution regularizing an
  irregular lot in this area, and a 2026 paving/water-infrastructure
  project description for ~23,000 residents, both consistent with a
  self-built, incrementally regularized "colonia popular" (typically
  low-rise), not a planned mid/high-rise development.
- A wide-area satellite check (ArcGIS World Imagery, no API key, the
  script re-fetches and saves this to
  `_raw/lomas_centinela/reference_satellite.png` as reviewable
  evidence): organic, non-gridded street layout, small densely packed
  rooflines, no tall-building silhouette anywhere in the neighborhood.
  One visual pass over the whole colonia, not a per-building review.

## Height refinement: GlobalBuildingAtlas (TUM), where it actually matched

```bash
cd backend
uv run python scripts/exposure/apply_gba_heights_lomas_centinela.py
```

Run after `estimate_lomas_centinela_heights.py`. Revisits the "not worth
a 1+GB download" call above: the user pushed back on it, so this was
tested for real rather than left as an assumption.

- The lighter route, GBA's own height *raster* (`GBA.Height`, would
  support cheap windowed reads the same way this project already
  streams Vs30/WorldPop via GDAL `/vsicurl/`, see
  `scripts/geodata/build_vs30.py`) is hosted on mediaTUM behind an
  always-on bot-detection challenge (Anubis) that blocks all scripted
  access, confirmed by direct testing (curl with a real browser
  User-Agent still gets the JS challenge page), not assumed.
- Before committing to the full `GBA.LoD1` download, a range-request
  shortcut was tested: sampling small byte windows at 9+ offsets across
  the 1.38GB tile and decoding the Google Plus Codes embedded in the
  building IDs found there. Result: entries are geographically clustered
  only in small local batches, scattered with no global sort order
  across the file, so there's no way to isolate one neighborhood's data
  with a partial download.
- Downloaded the full tile (`LoD1/northamerica/w105_n25_w100_n20.json`,
  1,377,026,940 bytes, cached under `_raw/lomas_centinela/`) and
  streamed it in 64MB chunks with a regex over `"google<PlusCode>MEX":
  {"height": ..., "var": ...}` entries (no full JSON parse of a 1.4GB
  single-object file), decoding each Plus Code to a coordinate directly
  from the building ID, no separate (7.5GB) geometry file needed.
  `osm...`-keyed entries were skipped entirely: this neighborhood's own
  live OSM check (above) found ~0 real coverage here, and an OSM ID
  alone carries no coordinate the way a Plus Code does.
- First attempt yielded only 27 of 2,215 footprints (1.2%) matched
  within 20m, which turned out to be a real bug, not real sparse
  coverage: the Plus Code decoder only used the 8-character prefix
  (a ~278m x 260m cell), silently dropping the 2 digits right after the
  `+` that get a Plus Code to its commonly-cited ~14m x 13m accuracy.
  Caught by the user comparing the map against a real street-level
  photo of the neighborhood showing several 2-story buildings, which
  didn't square with an almost-empty match rate. A ~270m-uncertain
  point matched against a 20m radius mostly succeeds by chance (~1.8%
  predicted, 1.2% observed), not by real correspondence. Fixed by
  decoding 10 significant digits instead of 8, and widening the match
  radius to 25m (the 10-digit cell's diagonal, ~19m, plus digitisation
  slack). See `apply_gba_heights_lomas_centinela.py`'s
  `_decode_pluscode()` docstring for the full account.
- Real yield after the fix: 16,126,425 Google-sourced entries scanned
  tile-wide, 49,552 within a padded box around the neighborhood,
  **2,132 of 2,215 footprints (96.3%)** matched a GBA point within 25m.
  Those 2,132 got their `n_floors`/`height` overwritten with the real
  GBA value (mean reported variance 0.92 m²); the other 83 (mostly at
  the neighborhood's edges, outside the padded box or with no plausible
  match) keep the uniform 1-floor/3.0m estimate.
- First distribution (with the 3.0m project-wide `METRES_PER_FLOOR`):
  2,122 buildings at 1 floor, 92 at 2 floors, 1 at 3 floors. Flagged as
  suspicious: a real street-level photo of the neighborhood showed
  several clearly 2-story buildings on a single block, hard to square
  with only 4.2% of the whole neighborhood at 2+ floors.
- **Lowered `METRES_PER_FLOOR` to 2.5m for this neighborhood only**
  (both `estimate_lomas_centinela_heights.py` and
  `apply_gba_heights_lomas_centinela.py`, not the project-wide 3.0m
  default in `app/data_loader.py`, which stays as-is for the other 3
  cities). Not a fabricated number: Mexico's own building code (RCDF,
  Reglamento de Construcciones para la Ciudad de México, Art. 106)
  cites 2.30m as the minimum habitable height and 2.40-2.60m as the
  recommended comfort range for social/mid-level housing, consistent
  with this neighborhood's own `pre_code` assumption (see
  `assign_lomas_centinela_typology.py`).
- Resulting distribution after the fix: **1,944 at 1 floor, 262 at 2
  floors (11.8%), 9 at 3 floors** (height range 1.5-7.7m, median
  2.5m). A meaningfully better match to the photographic evidence than
  the 3.0m-divisor result, though not independently validated against
  a full ground survey, still a mockup-level estimate.

**License**: `GBA.Height`/`GBA.LoD1` is CC BY-NC 4.0 (non-commercial),
confirmed from the dataset's own GitHub README. Not yet checked against
this project's actual intended use, do that before relying on this for
more than a mockup.

**Accuracy caveat**: the GlobalBuildingAtlas paper (Arxiv 2506.04106)
reports height RMSE of 1.5-8.9m across continents, 5.5m global average,
a margin comparable to the very difference this is meant to resolve (a
1-story house is ~3m, a 2-story one ~6m). Real per-building variation
for the 27 matched buildings, not a guaranteed accuracy improvement over
the uniform estimate it replaced.

## Structural typology: mostly a pooled-model estimate, MUR fallback for the rest

No labeled sample exists for this neighborhood itself to bootstrap a
per-city `ml_structural_system` ensemble the way the 3 pilot cities'
own models do (per `docs/adding_a_city.md`). Unlike La Guaira above,
though, this isn't left as a pure city-wide assumption: a model POOLED
across the 3 pilot cities' own labeled data (`ml_structural_system/
experiments/sjose_guatemala_sdomingo/risk_viewer_models/lomas_centinela/
config.yaml`) was trained and run against this neighborhood instead,
giving 2,161 of 2,215 buildings (97.6%) a real per-building estimate
(`structural_system_estimated = True`), the same mechanism the 3 pilot
cities use for their own gaps. The remaining 54 (the pooled model's own
inference step dropped them for missing `year`) still get the uniform
`structural_system_class = "MUR"` (mamposteria sin refuerzo /
unreinforced masonry) fallback, with `code_quality = "pre_code"` set on
all 2,215 either way (typology is the only thing the ensemble
estimates). See `assign_lomas_centinela_typology.py`'s own docstring for
the full, up to date reasoning and citations (Preciado & Rodriguez 2015
on a comparable Guadalajara-metro peri-urban colonia, CENAPRED's
autoconstruccion manual, INEGI national wall-material statistics) --
kept there rather than duplicated here since it's changed twice already
(originally MCF, corrected to MUR; originally a blanket MUR assumption
for every building, corrected to mostly-pooled-model once that model
existed) and the docstring is the version that actually ships with the
code that reads it.

**Not on the same footing as the 3 pilot cities' own estimates.** A
distribution-shift check against that pooled model
(`risk_viewer_models/lomas_centinela/drift_report.txt`) found 27 of 30
features significantly shifted between this neighborhood and the 3
training cities, a two-sample classifier AUC of 0.9997 (near-perfect
separability -- the model is being asked to extrapolate well outside
what it saw in training), and a negative inter-model Fleiss' kappa
(-0.30: the ensemble's own 3 models agree with each other WORSE than
chance here, versus positive agreement in the pilot cities). There's
also no local held-out ground truth to score it against at all
(`held_out_metrics.json` has no `lomas_centinela` entry, by design, see
`app/typology_ensemble/loader.py::get_ensemble_quality_metrics`). The
app surfaces this as `locally_validated = False` wherever this city's
ensemble is shown, rather than hiding the caveat or not using the model
at all.

`CityProfile.typology_beta_generic = 0.6` (see `app/cities.py`) still
covers the 54 MUR-fallback buildings, same convention as La Guaira's own
generic assumption; the 2,161 pooled-model estimates instead get
`ESTIMATED_TYPOLOGY_BETA` (`app/risk/service.py`), the same fixed
uncertainty floor every other city's ML-estimated buildings get.

## Not yet done

`app/cities.py` has a `CityProfile` entry, the deterministic scenario
(Zapopan Graben crustal source, see `app/hazard/scenario.py`) and PSHA
(GEM's MEX v2025.0.0 model) are both wired up -- see
`risk_viewer/docs/adding_a_city.md`'s checklist for what "wired up"
covers. What's still genuinely a mockup-level simplification, not a
to-do: the single neighborhood-wide structural typology and floor-count
assumptions above (no per-building survey exists), same caveat as
everywhere else in this file.
