# Reproducing the PSHA / disaggregation data

`app/data/psha/*.csv` (hazard curves and disaggregation) are precomputed
offline, not generated at request time; see `docs/psha_plan.md` and
`docs/disaggregation_plan.md` for the method and results. This directory
is the pipeline that produces them.

## One-shot

```bash
cd backend
uv run python scripts/psha/build_all.py            # all 4 cities
uv run python scripts/psha/build_all.py guatemala   # one city
```

Runs each city sequentially, not in parallel: OpenQuake's classical
calculator holds a regional source model's rupture data in memory, and
running two cities at once caused a real out-of-memory crash during
development. Budget roughly 15 to 60 minutes per city (Guatemala's
regional mosaic is slowest; Lomas del Centinela's single-site 200-sample
run finishes in well under 10 minutes) plus a few minutes of
disaggregation. Downloaded source models land in `scripts/psha/_raw/`
(gitignored, 120-350 MB per city, re-fetched if missing).

## What each step does

1. `fetch_sources.py <city>` downloads that city's published source
   model (see Sources below) into `_raw/{city}/`.
2. `run_classical.py <city>` overlays `configs/{city}/` (job.ini and any
   custom logic-tree/site files) onto the fetched model, runs
   `openquake.calculators.base.run_calc`, and writes
   `app/data/psha/{city}.csv` (mean/p16/p84 hazard curves per IMT).
3. `run_disagg.py <city>` reuses that classical run via
   `hazard_calculation_id` and writes `app/data/psha/{city}_disagg.csv`.

`configs/{city}/` encodes real methodology decisions (which branches to
keep, which site to evaluate at) and is committed on purpose.
`job_disagg.ini` is not committed: `run_disagg.py` builds it at runtime
from the classical run's own IMT list, so a hand-copied duplicate can't
go stale if the classical config changes.

## Sources

| City | Model | License | Download |
|---|---|---|---|
| San Jose | CRSHM2022 (Hidalgo-Leiva et al. 2022), unmodified base model, via Arroyo (2025)'s Mendeley supplement | CC BY 4.0 | [doi.org/10.17632/7x8xv2yf23.2](https://doi.org/10.17632/7x8xv2yf23.2), `CRSHM2022` subfolder |
| Guatemala City | GEM Caribbean & Central America (CCA) regional model, v2026.0.0 | CC BY-NC-SA 4.0 | [hazard.openquake.org/gem/models/CCA](https://hazard.openquake.org/gem/models/CCA) |
| Santo Domingo | GEM Dominican Republic Hazard Model (TREQ project) | CC BY-SA 4.0 | [cloud.openquake.org/s/PZ3yydAyy6XZR3X](https://cloud.openquake.org/s/PZ3yydAyy6XZR3X) |
| Lomas del Centinela | GEM Mexico (MEX) national model, v2025.0.0 | CC BY-NC-SA 4.0 | [hazard.openquake.org/gem/models/MEX](https://hazard.openquake.org/gem/models/MEX) (share [cloud.openquake.org/s/xqHswGaHQYJYXb8](https://cloud.openquake.org/s/xqHswGaHQYJYXb8)) |

San Jose is the only one of the four with a model built and published
at city scale, letting this project validate its own PSHA
implementation against the authors' published curve (under 0.5%
agreement, see `docs/psha_plan.md`), so it's the reference case.
Guatemala, Santo Domingo, and Lomas del Centinela have no city-scale
model; the GEM regional/national models are the best publicly available
source at those sites, at the cost of no direct published-curve
validation (a stated, documented limitation).

`configs/guatemala/` restricts the CCA regional model to Guatemala/
CAM-tagged sources: the unrestricted mosaic combined with its full GMPE
tree builds 48.4 billion realizations. The restriction leaves 3 TRTs and
864 realizations (with the fault-geometry branch restored, see
`ssmLT_cam_with_faults.xml`), see `docs/psha_plan.md`.

`configs/santo_domingo/job_hazard.ini` samples the full logic tree
(`number_of_logic_tree_samples = 16`) rather than enumerating all 2,592
source-model by GMPE combinations, the same sampling technique the GEM
CCA model's own published job.ini uses at regional scale, just at a
smaller count appropriate for a single-site run. A documented tradeoff
(more sampling noise in the p16/p84 bands, in exchange for a run that
finishes in hours instead of days).

`configs/lomas_centinela/job_hazard.ini` uses the MEX model's own
`ssmLT_clean.xml`/`gmmLT_clean.xml` logic-tree files unmodified (a
single source-model branch, unlike Guatemala's fault-geometry choice,
so there's no epistemic source-model uncertainty to restrict), just
sampled at 200 of 155,520 possible source-model x GMPE combinations
(same sampling technique as Santo Domingo, larger sample count since
the single-site run stayed fast). The share's zip nests a second zip
one level down (`v2025.0.0/job.zip`); `fetch_sources.py` extracts that
inner zip directly as the model root. At the most extreme grid levels
(PGA/SA >= ~3g, annual PoE below ~3e-8, return periods beyond a million
years) the reduced sample count makes the mean curve slightly exceed
the 84th-percentile band — a few high-rate realizations pulling the
mean above a 200-sample quantile estimate. Harmless: this project's
actual return periods (475/975/2475yr) sit at PoE ~4e-4 to 2e-3, many
orders of magnitude above where this happens (see
`tests/test_psha.py::test_percentile_bands_bracket_mean`).

## Other data pipelines

`app/data/vs30/*.csv` and `app/data/population/*.csv` have their own
reproduction scripts under `../geodata/`, same pattern as this
directory.
