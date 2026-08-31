# Risk Viewer

A web viewer for seismic exposure, typology, vulnerability, hazard, and
risk data. Covers the full pipeline: exposure and structural typology
(with real multi-model uncertainty), capacity and fragility curves, a
seismic hazard scenario (deterministic and probabilistic), and
per-building damage, population, and expected casualties. Each stage
cites the method or dataset it uses; see [References](#references).

## Architecture

- `backend/`: a FastAPI service. Loads its own vendored copy of the
  exposure dataset once at startup and serves it as GeoJSON through a
  generic layer-registry API (`/api/layers`), plus
  `/api/buildings/{id}/vulnerability` (capacity/fragility curves and
  model agreement) and `/api/scenarios/*` (hazard/risk). Self-contained:
  every data file it reads at runtime lives under `backend/app/data/`
  (see `app/config.py`).
- `frontend/`: a Vite + TypeScript app using MapLibre GL JS with a
  deck.gl overlay, switchable between an exposure/typology layer and a
  seismic risk scenario layer, plus a small dependency-free SVG chart
  module.

Cities are a registry (`app/cities.py`), not scattered per-city code:
adding a compatible city is one entry plus data files. See
`docs/adding_a_city.md` for the workflow and
`docs/exposure_acquisition_brief.md` for the hardest part, acquiring
real per-building exposure and typology data for a new city.

## Per-building vulnerability

Clicking a building fetches `/api/buildings/{id}/vulnerability`, which
always reports which of three tiers produced the result:

1. **ML capacity model** (`ml_capacity_model`): masonry (`M`) buildings
   with a known floor count. A GPR+PCA model (test R^2 ~0.94) predicts a
   capacity curve, bilinearized into fragility curves.
2. **GEM global vulnerability model** (`gem_global_vulnerability`): `CR`,
   `W`, `ADO` buildings. Fragility curves from Martins & Silva (2020),
   matched by structural class, ductility (`code_quality`), and height
   class (`n_floors`). No capacity curve at this tier.
3. **Published-typology fallback** (`published_fallback`): `M` buildings
   with no floor count. Generic drift-ratio thresholds, ordered by
   `ml_structural_system`'s own fragility ranking.

Buildings with no usable structural class report `available: false`.
The panel's "Override inputs" section recomputes a hypothetical result
for a different class/floors/height/quality without touching stored
data.

## Structural typology and model agreement

`ml_structural_system` trains three classifiers per city
(LogisticRegression, RandomForest, XGBoost) and runs them on every
building, producing per-model votes and agreement stats
(`agreement_ratio`, `normalized_entropy`, `is_contested`). The building
panel's "model agreement" section shows each model's vote, with a
button per candidate class to recompute for that hypothesis.

Buildings with no recorded `structural_system` get the ensemble's
majority-vote class filled in automatically, flagged as an estimate
(`structural_system_estimated`, an amber outline on the map, an
"estimated" badge in the building panel) rather than shown as confirmed
data. Estimated buildings get a fixed, deliberately high uncertainty
contribution (`ESTIMATED_TYPOLOGY_BETA` in `app/risk/service.py`)
instead of one derived from model agreement, since even unanimous
models agreeing on a class with no real label to check against is not
the same thing as measured confidence.

`normalized_entropy` also feeds the combined-uncertainty calculation in
the risk pipeline (`app/risk/uncertainty.py::typology_beta_from_entropy`).

Regenerating a city's ensemble is done from `ml_structural_system/`; see
that project's own docs for the `mlss` pipeline. The two files this
backend reads (`predictions.csv`, `preprocessing.json`) get copied into
`backend/app/data/typology_ensemble/<city>/`.

## Hazard and risk

`/api/scenarios/{city}/summary` and `/api/scenarios/{city}/risk` run one
earthquake scenario per city through the full chain: distance to
source, a published GMPE, spectral demand (elastic, or the nonlinear
ATC-40 performance point where a capacity curve exists), fragility
curves, damage-state probabilities, population, and expected casualties.

- **Deterministic scenario**: a default magnitude, depth, and epicenter
  per city, anchored to a controlling source from published regional
  studies (see [References](#references)). Adjustable from the UI's
  "Custom scenario" panel.
- **Probabilistic (PSHA)**: for a return period (475, 975, or 2475
  years), Sa(T) comes from a precomputed hazard curve run through the
  full OpenQuake Engine against each city's national/regional source
  model. Includes 16th/84th percentile bands and, per return period, the
  disaggregated controlling event (magnitude/distance). San Jose's curve
  is validated against its source model's own published curve (under
  1.3% relative difference). See `docs/psha_plan.md` and
  `docs/disaggregation_plan.md` for the full derivation and validation.
  Regenerate with `uv run python scripts/psha/build_all.py`.
- **GMPE** (`app/hazard/gmpe.py`): Boore, Stewart, Seyhan & Atkinson
  (2014) for the crustal regime, Zhao et al. (2016) for San Jose's
  subduction interface. Vs30 from the USGS Global Vs30 Map, looked up
  per building.
- **Population**: WorldPop 2020, disaggregated to buildings by built
  volume.
- **Casualties**: HAZUS-MH Technical Manual injury-severity rates by
  building type and damage state.
- **Uncertainty**: per-building lognormal quadrature over fragility,
  GMPE, typology, and (ML tier) capacity-curve uncertainty
  (`app/risk/uncertainty.py`), plus a 300-trial Monte Carlo propagation
  for city-wide P10 to P90 casualty ranges (`app/risk/monte_carlo.py`).

## Map colors

Categorical attributes use four hues checked pairwise under simulated
color-vision deficiency (not just adjacent pairs, since a map can put
any two categories side by side). Damage state uses a single-hue
ordinal ramp (light to dark), not a green-to-red scale, since green and
red are hard to tell apart under simulated deuteranopia. Sequential
attributes use a single-hue blue ramp. See `backend/app/colors.py` and
`frontend/src/colors.ts`.

## Run it

**Backend** (from `backend/`):

```bash
uv sync
uv run uvicorn app.main:app --reload --port 8001
```

**Frontend** (from `frontend/`, in another terminal):

```bash
npm install
npm run dev
```

Open http://localhost:5183/. To point at a different backend, copy
`.env.example` to `.env` and set `VITE_API_BASE`.

**Or via Docker** (production-shaped: precomputed scenarios baked in,
static frontend served by Caddy, which proxies `/api/*` to the backend):

```bash
docker compose up -d --build
```

Open http://localhost/. First boot takes anywhere from 15s to a couple
of minutes (importing `openquake.hazardlib` and loading exposure data
before accepting connections); `docker compose ps` shows `(healthy)`
once ready. For a public deploy, point DNS at the server and replace the
`:80` line in `deploy/proxy/Caddyfile` with the real domain (Caddy then
provisions HTTPS automatically), then run the same command there.

> Backend defaults to port 8001, frontend to 5183 (ports 8000/5173 were
> already in use on the machine this was built on). Change
> `RISK_VIEWER_FRONTEND_ORIGIN` (backend) and `VITE_API_BASE` (frontend)
> together for different ports.

## Tests

```bash
cd backend && uv run pytest
```

## Data notes

- `structural_system_class` collapses the raw `structural_system` value
  into 7 classes (`ADO`, `CR`, `M`, `MCF`, `MR`, `MUR`, `W`), with an
  explicit `unlabeled` bucket so every building still renders even with
  no usable class. `MCF`/`MR`/`MUR` (GEM Building Taxonomy's confined/
  reinforced/unreinforced masonry codes) are kept distinct rather than
  folded into the generic `M` bucket, so each routes to its own
  published GEM fragility curve instead of the ML capacity-model tier's
  best-quality-masonry default.
- The exposure dataset (~2811 features) is served as one GeoJSON blob,
  no tiling or pagination.
- `relative_position` (isolated, lateral, corner, confined, torque) is
  computed once at startup from real building footprint geometry.

## References

- Benito, B. et al. (2012). Seismic hazard assessment for Guatemala City.
- Hidalgo-Leiva, D. A. et al. (2022). The 2022 Seismic Hazard Model for
  Costa Rica. *Bulletin of the Seismological Society of America*, 113(1).
- Arroyo, M. (2025). Supplementary material for the 2022 Costa Rica
  hazard model. Mendeley Data, V2.
  [doi.org/10.17632/7x8xv2yf23.2](https://doi.org/10.17632/7x8xv2yf23.2).
- Johnson, K. et al. (2024). Probabilistic seismic hazard analysis for
  the Dominican Republic. *Earthquake Spectra*.
- GEM Foundation. Caribbean & Central America (CCA) Regional Hazard
  Model, v2026.0.0.
  [hazard.openquake.org/gem/models/CCA](https://hazard.openquake.org/gem/models/CCA).
- Boore, D. M., Stewart, J. P., Seyhan, E., & Atkinson, G. M. (2014).
  NGA-West2 equations for shallow crustal earthquakes. *Earthquake
  Spectra*, 30(3).
- Zhao, J. X. et al. (2016). Ground motion prediction equations for
  subduction interface earthquakes. *Bulletin of the Seismological
  Society of America*, 106(4).
- Wald, D. J., & Allen, T. I. (2007). Topographic slope as a proxy for
  seismic site conditions and amplification. *Bulletin of the
  Seismological Society of America*, 97(5).
- Allen, T. I., & Wald, D. J. (2009). High-resolution topographic data
  as a proxy for seismic site conditions (VS30). *Bulletin of the
  Seismological Society of America*, 99(2A).
- Martins, L., & Silva, V. (2020). Development of a fragility and
  vulnerability model for global seismic risk analyses. *Bulletin of
  Earthquake Engineering*.
  [github.com/lmartins88/global_fragility_vulnerability](https://github.com/lmartins88/global_fragility_vulnerability).
- Applied Technology Council (1996). *ATC-40: Seismic Evaluation and
  Retrofit of Concrete Buildings*. Chapter 8.
- Federal Emergency Management Agency. *HAZUS-MH Earthquake Model
  Technical Manual*. Chapter 13.
- WorldPop (2020). Global High Resolution Population Denominators.
  [worldpop.org](https://www.worldpop.org).
- openquake.hazardlib:
  [github.com/gem/oq-engine](https://github.com/gem/oq-engine), GEM
  Foundation.
