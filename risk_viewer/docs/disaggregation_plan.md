# Disaggregation

Companion to `docs/psha_plan.md` (read that first). Answers a question
the hazard curve itself doesn't: at a given return period, which
magnitude/distance combination actually controls the hazard. Phase 1
(scalar summary) is implemented for all 3 cities; a magnitude by
distance heatmap is not built.

## What it computes

At the target PGA level for a chosen return period, `lambda(PGA>x*)`
broken down into a probability mass over magnitude bins by distance
bins, normalized to sum to 1. Reported as `mean_magnitude` and
`mean_distance_km` (the fraction-weighted bin-center average, the
standard "controlling earthquake" figure in hazard studies) plus the
full bin breakdown.

## Method

OpenQuake's `disaggregation` calculator, run via `base.run_calc(job_ini,
hazard_calculation_id=N)` reusing each city's already-completed
classical PSHA run rather than rebuilding the model. One run per city
computes all 3 return periods at once (`poes_disagg`, each city's own
target exceedance probabilities). The disaggregation job.ini's
`intensity_measure_types_and_levels` block must exactly match the reused
classical run's own, since the reused precalc's context still expects
the full original IMT list; only the PGA slice is read back out.

Output shape confirmed empirically as `(n_sites, n_mag_bins, n_dist_bins,
n_imts, n_poes, n_stats)`, e.g. `(1, 7, 14, 13, 3, 1)` for San Jose. The
raw array values are proportional to exceedance contribution, not a
pre-normalized probability mass, so each return period's matrix is
divided by its own sum before computing means or bin fractions.

## Results

| City | 475yr | 975yr | 2475yr |
|---|---|---|---|
| San Jose | Mw 6.16, 45 km | Mw 6.20, 44 km | Mw 6.25, 42 km |
| Guatemala | Mw 7.31, 78 km | Mw 7.37, 78 km | Mw 7.46, 78 km |
| Santo Domingo | Mw 6.74, 64 km | Mw 6.82, 62 km | Mw 6.89, 60 km |

All three follow the expected pattern: longer return periods are
controlled by slightly larger (and, except Guatemala, slightly closer)
events, consistent with rarer hazard levels drawing more from the tail
of each source's magnitude-frequency distribution. Guatemala's much
larger controlling magnitude and distance reflects the CCA regional
model's large subduction sources, further from the site than San
Jose's or Santo Domingo's dominant crustal sources.

Guatemala and Santo Domingo's numbers reflect the source-model
epistemic uncertainty in `psha_plan.md` (previously Mw 7.30/77km and Mw
6.32/40km using only GMPE-choice uncertainty over a single source-model
branch). Santo Domingo's shift (Mw 6.32 to 6.74, 40km to 64km) is
substantial because the single branch used before was one specific pick
out of 96 real alternatives; averaging over 16 sampled combinations
pulls in more distant sources that branch did not represent. This is a
real consequence of averaging over more of the source-model tree, not a
data error.

## Implementation

- `app/data/psha/{city}_disagg.csv`: long format, PGA only, computed
  offline via `backend/scripts/psha/run_disagg.py` (part of
  `build_all.py`'s pipeline).
- `app/hazard/psha.py`: `DISAGG_SUPPORTED_CITIES` derived from which
  `{city}_disagg.csv` files exist; `disaggregation(city,
  return_period_years)` loads and normalizes the CSV.
- API: `GET /api/scenarios/{city}/disaggregation?return_period_years=475`,
  400 for an unsupported return period, 404 for an unsupported city.
- UI: fetched alongside the hazard curve for probabilistic scenarios,
  rendered as "Controlling event at this return period: Mw X.X at Y km"
  under the hazard curve chart.

## Validation

The Mendeley Costa Rica dataset includes a disaggregation file (`Dissag_
CRSHM2022.zip`, confirmed to exist, not inspected here); no equivalent
exists for Guatemala or Santo Domingo. Confidence rests on internal
consistency (magnitude/distance values matching each source model's
known geometry) and reusing the same classical-run precalc already
validated in `psha_plan.md`, not a direct published comparison.

## Not built: heatmap

A 2D magnitude by distance heatmap would use the full bin breakdown
already returned by the API but is not rendered: `chart.ts` is a
line-chart-only component today, and a heatmap needs a new primitive (a
grid of colored cells). Worth doing only if the scalar summary proves
insufficient.
