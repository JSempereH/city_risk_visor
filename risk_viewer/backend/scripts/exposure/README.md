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
