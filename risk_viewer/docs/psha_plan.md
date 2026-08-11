# PSHA in risk_viewer

Implemented for all 3 pilot cities (San Jose, Guatemala City, Santo
Domingo): a mean hazard curve plus 16th/84th percentile bands across the
full GMPE logic tree, surfaced in the UI. San Jose is validated against
its source model's own published curve; Guatemala and Santo Domingo have
no published curve at their exact site to validate against directly
(section 3).

## Method

A GMPE gives a lognormal distribution, not a point:
`ln(IM) ~ Normal(ln(IM_median(m,r)), sigma)`. Each source's magnitudes
follow Gutenberg-Richter (`hazardlib.TruncatedGRMFD`), giving an annual
rate and a magnitude/distance density. The hazard curve sums the
exceedance probability over every source:
`lambda(IM>x) = sum_i nu_i * integral P(IM>x|m,r) f_Mi(m) f_Ri(r) dm dr`.
Poisson occurrence converts this to a return period:
`P(exceed in T yr) = 1 - exp(-lambda*T)` (a "475-yr" value is where
`lambda = 1/475`).

The logic tree (which GMPE/Mmax/b is right) gives epistemic uncertainty:
weighted branches produce a mean curve plus p16/p84. This is distinct
from the app's Monte Carlo module, which propagates aleatory uncertainty
(the GMPE's own sigma) but not epistemic spread.

PSHA only changes how `Sa(T)` is produced (a return-period hazard curve
instead of one GMPE call at an assumed magnitude/distance); everything
downstream (ATC-40, fragility curves, damage states, casualties, Monte
Carlo) is unchanged. UI: a "Hazard model" selector next to the scenario
panel.

## Data sources

| Model | City | Version | Download | License |
|---|---|---|---|---|
| Hidalgo-Leiva et al. (2022) CRSHM2022, via Arroyo (2025) Mendeley supplement | San Jose | (n/a) | [data.mendeley.com/datasets/7x8xv2yf23/2](https://data.mendeley.com/datasets/7x8xv2yf23/2) | CC BY 4.0 |
| GEM Caribbean & Central America (CCA) regional model | Guatemala City | v2026.0.0 | [model docs](https://hazard.openquake.org/gem/models/CCA/) | CC BY-NC-SA 4.0 |
| GEM Dominican Republic model (TREQ project) | Santo Domingo | v2021.2.0 | [cloud.openquake.org/s/PZ3yydAyy6XZR3X](https://cloud.openquake.org/s/PZ3yydAyy6XZR3X) | CC BY-SA 4.0 |

The Mendeley Costa Rica dataset's `CRSHM2022` subfolder is the
unmodified base 2022 model (29 sources, single branch), used here for an
apples-to-apples validation (section 3). The CCA model is a regional
mosaic restricted to Guatemala/CAM-tagged sources for tractability (a
full run is billions of realizations; restricting the source model and
GMPE tree to CAM-tagged sources gives 432, see
`backend/scripts/psha/README.md`). All three licenses permit
non-commercial reuse.

Guatemala's and Santo Domingo's `MultiFaultSource`/
`NonParametricSeismicSource` types need the full OpenQuake Engine
(`openquake.calculators.base.run_calc()`) to resolve rupture geometry,
not just `hazardlib`'s standalone functions; San Jose was run both ways
as a cross-check. Precomputed offline via `backend/scripts/psha/`
(`build_all.py`) into `app/data/psha/{city}.csv`, one representative
site per city (city center; hazard varies smoothly over a city a few km
wide relative to the tens to hundreds of km to controlling sources).

## Validation

San Jose vs. Hidalgo-Leiva et al.'s own published PGA curve (Vs30=760
m/s):

| PGA (g) | Published mean | This impl. mean | Rel. diff |
|---|---|---|---|
| 0.10 | 0.9433 | 0.9447 | 0.14% |
| 0.18 | 0.5901 | 0.5924 | 0.40% |
| 0.32 | 0.2098 | 0.2106 | 0.41% |
| 0.47 | 0.08338 | 0.08362 | 0.29% |
| 1.00 | 0.008761 | 0.008772 | 0.12% |
| 1.21 | 0.004623 | 0.004627 | 0.09% |
| 3.11 | 0.0001217 | 0.0001219 | 0.13% |

Mean agreement is under 0.5% across nearly the whole range. p16/p84
track the published percentiles too, with wider relative gaps only in
the near-saturated tail (small absolute differences read as large
relative ones). Locked in as a regression test
(`tests/test_psha.py::test_pga_matches_published_hidalgo_leiva_validation`).

No published curve exists at Guatemala City's or Santo Domingo's exact
site. Confidence in those two rests on internal consistency (monotonic
curves, p16<=mean<=p84), the Engine completing a full or
minimally-restricted run of the real published input files, and this
same method reproducing San Jose's curve to within 1.3%, stated
explicitly in each city's UI source note, not glossed over.

## Per-city summary

| | San Jose | Guatemala City | Santo Domingo |
|---|---|---|---|
| Source model | CRSHM2022 (unmodified) | GEM CCA, CAM-restricted | GEM DR model |
| Source-model branches used | 1 of 1 (full) | 2 of 2 (both fault-geometry variants, full) | 16-sample of 96 |
| GMPE branches | 11, 45 combos | 24, 864 combos (x2 fault branches) | 9, sampled jointly with source |
| Reference Vs30 | 760 m/s | 800 m/s | 800 m/s |
| Investigation time | 50 yr | 1 yr | 1 yr |
| Published validation curve | Yes, <0.5% | No | No |

Guatemala's source-model epistemic uncertainty (fault-geometry
alternatives) is fully enumerated (2 branches, weight 0.5/0.5). Santo
Domingo uses 16-sample logic-tree sampling rather than full enumeration
over its 96 source-model combinations (too many to run fully on modest
hardware, the same sampling technique the GEM CCA model's own published
job.ini uses at regional scale), so its p16/p84 bands mix real
source-model spread with sampling noise, a documented and bounded
tradeoff.

## DSHA vs. PSHA, San Jose

Deterministic (Mw 7.5 Cocos-Caribbean interface, ~75 km away, one
illustrative point): 650/650 buildings show no damage. 475-yr PSHA
(life-safety design level): 350 none, 23 slight, 204 extensive, 73
complete. Not a bug: PSHA integrates over every magnitude/distance the
full source model allows, including sources much closer than the single
illustrative deterministic point, so it surfaces hazard levels a
hand-picked event does not.

## Architecture

`app/hazard/psha.py`: per-city reference Vs30/investigation time;
`PSHA_SUPPORTED_CITIES` derived from which `{city}.csv` files exist.
Inverts the hazard curve to the return period's target exceedance
probability, interpolates across periods onto the demand spectrum,
applies a Vs30 amplification ratio at that return period's own
disaggregated controlling magnitude/distance when available
(`_controlling_event()`). `Scenario.mode`/`return_period_years`
(`scenario.py`) let `run_scenario()` handle probabilistic scenarios with
no other changes. API: `return_period_years` query param on `/summary`
and `/risk`, mutually exclusive with deterministic overrides;
`/api/scenarios/{city}/hazard_curve` returns the full precomputed curve
for charting.

## Current scope and limitations

- Vs30 amplification uses each return period's own disaggregated
  controlling event, not one fixed representative event (verified for
  San Jose: the 475/975/2475yr events genuinely differ, though the
  resulting amplification ratio itself shifts only slightly, since most
  GMPEs' site-response terms depend more on Vs30 and input motion than
  on magnitude/distance).
- Disaggregation implemented for PGA, all 3 cities, as a scalar
  controlling-event summary (see `docs/disaggregation_plan.md`). Not
  yet: a magnitude by distance heatmap, disaggregation for other IMTs,
  or a check against San Jose's own published disaggregation file.
- Guatemala/Santo Domingo have no published validation curve at the
  exact site; confidence is internal-consistency plus method-level
  cross-check only, weaker than San Jose's direct comparison.
- No tiling or pagination if the exposure dataset grows to whole-city
  scale.
