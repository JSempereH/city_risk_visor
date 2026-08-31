# Adding a new city

What a new city needs before it can be added to the visor with the same
per-building rigor as San Jose, Guatemala City, and Santo Domingo. See
`app/cities.py`'s own docstring for the mechanical last step (the
registry entry); this document is everything that has to exist before
that step makes sense.

Investigated once for Colombia (2026-08-10): the public sources checked
(GEM's exposure model, DesignSafe-CI) do not give real per-building data
for any Colombian city, see "Hard requirement" below.

Done once, for La Guaira, Venezuela (built 2026-08-11, later pulled back
out over data-quality concerns, see `backend/scripts/exposure/
README.md`): real footprints and observed per-building damage existed
publicly, but structural typology did not, so a city-wide (not
per-building) assumption was used instead. Confirmed a real performance
finding worth knowing before adding a similarly large city:
`relative_position`'s per-building contact-geometry computation
(`footprint_attributes.position()`) scales worse than linearly with
building count, so a 26,000-building city takes several minutes to
cold-load versus a few seconds for the ~1,000-building existing cities.

## Hard requirement: real per-building exposure data

This is the actual bottleneck, not an engineering task. The pipeline
needs individual building footprints with real per-building attributes,
not a statistical or aggregated exposure model (population or
replacement cost per grid cell), which is what most publicly
downloadable "exposure models" actually are. GEM's own Colombia
documentation states this directly: aggregated points "do not represent
building-specific geolocations."

Target schema (matches `all_cities_combined.gpkg`, read by
`backend/app/data_loader.py`): one feature per building, with `id`,
`city`, `n_floors` (nullable), `height` (nullable), `code_quality`,
`roof_material`, `structural_system` (raw taxonomy string), and
`geometry` (a real footprint polygon, not a point). `centroid_lat/lon`
and `footprint_area_m2` are computed automatically from geometry.

- `structural_system` raw values must match this project's taxonomy
  (CR, M, ADO, MR, MCF, MUR, W, S_light, S_frame) or need a new entry in
  `data_loader.py`'s `STRUCTURAL_SYSTEM_REPLACEMENTS` mapping.
- If most buildings lack a labeled `structural_system`, the
  `ml_structural_system` classifier ensemble (`mlss`
  split/preprocess/train/infer) can fill in the rest, but needs a real
  labeled sample to train on first. Where a prediction exists,
  `data_loader.py::_fill_unlabeled_from_ensemble()` uses it directly as
  that building's `structural_system_class` (the ensemble's majority
  vote, not its soft-voting `ensemble_pred`, to stay consistent with
  what the building panel's own model-agreement section shows), flagged
  as `structural_system_estimated` (an amber outline on the map, a
  fixed uncertainty floor in the risk calculation, see
  `app/risk/service.py::ESTIMATED_TYPOLOGY_BETA`) rather than presented
  as confirmed data. This only fills genuine gaps: a building with a
  real recorded class is never overridden.

## Vulnerability tier compatibility

- Confirm the city's `structural_system_class` values fall inside
  ADO/CR/M/MCF/MR/MUR/W: a new class fails loudly (`app/risk/casualty.py`'s
  `hazus_building_type()`) rather than being silently miscosted, so the
  test suite surfaces it after loading a new city's data.
- The GPR capacity-curve model (masonry only) is already generic across
  cities; no retraining needed unless the new city's masonry
  construction differs meaningfully from the training set's.

## Hazard

- **Deterministic scenario**: research the controlling source for a
  credible design-level event, usually a published regional or national
  seismic hazard study (see `app/hazard/scenario.py`'s module docstring
  for the pattern each existing city follows). Becomes a `CityProfile`
  entry.
- **PSHA**: find a publicly available, OpenQuake-compatible source model
  and GMPE logic tree for the region (GEM regional models are the most
  common source). Build `backend/scripts/psha/configs/{city}/`, run
  `fetch_sources.py` then `run_classical.py`.
- **Disaggregation**: automatic once the classical run exists,
  `run_disagg.py` reuses it.

## Site data: already automated for any city

- **Vs30**: `uv run python scripts/geodata/build_vs30.py <city>` streams
  the USGS global grid, works for any city with buildings already
  loaded.
- **Population**: `uv run python scripts/geodata/build_population.py
  <city>`, after adding the country's ISO3 code to
  `scripts/geodata/lib.py`'s `ISO3_BY_CITY`.

## Registry and build

1. Add a `CityProfile` entry to `app/cities.py`.
2. `uv run python scripts/precompute.py` to bake the new city's scenario
   combos.
3. `uv run pytest -q`, should need no test changes for a city whose
   taxonomy fits ADO/CR/M/MCF/MR/MUR/W.
4. Manual check in the browser: exposure layer renders, a scenario run
   completes, casualty/damage numbers are sane.

## Checklist

- [ ] Real per-building footprints and attributes (the hard part)
- [ ] `structural_system` taxonomy mapped or extended
- [ ] Deterministic scenario researched and added
- [ ] PSHA source model found, configured, classical run completed
- [ ] Disaggregation run
- [ ] Vs30 built
- [ ] Population built
- [ ] `CityProfile` entry added
- [ ] Precompute regenerated, tests pass, manual browser check done
