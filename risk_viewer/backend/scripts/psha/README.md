# Reproducing the PSHA / disaggregation data

`app/data/psha/*.csv` (hazard curves and disaggregation) are precomputed
offline, not generated at request time; see `docs/psha_plan.md` and
`docs/disaggregation_plan.md` for the method and results. This directory
is the pipeline that produces them.

## One-shot

```bash
cd backend
uv run python scripts/psha/build_all.py            # all 3 cities
uv run python scripts/psha/build_all.py guatemala   # one city
```

Runs each city sequentially, not in parallel: OpenQuake's classical
calculator holds a regional source model's rupture data in memory, and
running two cities at once caused a real out-of-memory crash during
development. Budget roughly 15 to 60 minutes per city (Guatemala's
regional mosaic is slowest) plus a few minutes of disaggregation.
Downloaded source models land in `scripts/psha/_raw/` (gitignored,
150-350 MB per city, re-fetched if missing).

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

San Jose is the only one of the three with a model built and published
at city scale, letting this project validate its own PSHA
implementation against the authors' published curve (under 0.5%
agreement, see `docs/psha_plan.md`), so it's the reference case.
Guatemala and Santo Domingo have no city-scale model; the GEM
regional/national models are the best publicly available source at
those sites, at the cost of no direct published-curve validation (a
stated, documented limitation).

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

## Other data pipelines

`app/data/vs30/*.csv` and `app/data/population/*.csv` have their own
reproduction scripts under `../geodata/`, same pattern as this
directory.
