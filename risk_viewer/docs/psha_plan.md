# PSHA in risk_viewer

Implemented for all 4 pilot cities (San Jose, Guatemala City, Santo
Domingo, Lomas del Centinela): a mean hazard curve plus 16th/84th
percentile bands across the full GMPE logic tree, surfaced in the UI.
San Jose is validated against its source model's own published curve;
the other three have no published curve at their exact site to validate
against directly, but do each have an independent, weaker cross-check
now (section 3): Guatemala's disaggregation partially agrees with a
regional academic model, Santo Domingo's single-point PGA is close, and
Lomas del Centinela's is a real, unresolved, documented gap against two
independent Mexican sources.

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
| GEM Mexico (MEX) national model | Lomas del Centinela | v2025.0.0 | [model docs](https://hazard.openquake.org/gem/models/MEX/) | CC BY-NC-SA 4.0 |

The Mendeley Costa Rica dataset's `CRSHM2022` subfolder is the
unmodified base 2022 model (29 sources, single branch), used here for an
apples-to-apples validation (section 3). The CCA model is a regional
mosaic restricted to Guatemala/CAM-tagged sources for tractability (a
full run is billions of realizations; restricting the source model and
GMPE tree to CAM-tagged sources gives 432, see
`backend/scripts/psha/README.md`). The MEX model has only one
source-model branch (nothing to restrict there), sampled at 200 of its
155,520 source-model x GMPE combinations instead, the same sampling
technique as Santo Domingo. All four licenses permit non-commercial
reuse (this project's own use, a thesis/research tool).

Guatemala's, Santo Domingo's, and Lomas del Centinela's `MultiFaultSource`/
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

No published curve exists at Guatemala City's, Santo Domingo's, or Lomas
del Centinela's exact site. Confidence in those three rests on internal
consistency (monotonic curves, p16<=mean<=p84 at every level of
practical interest), the Engine completing a full or minimally-restricted
run of the real published input files, and this same method reproducing
San Jose's curve to within 1.3%, stated explicitly in each city's UI
source note, not glossed over. Independent (weaker, single-point or
disaggregation-only) cross-checks for these three are below.

### Independent cross-checks (Guatemala, Santo Domingo, Lomas del Centinela)

None of these three has a published hazard curve at its exact site, so
these are not full-curve overlays like San Jose's, but the best
independently published estimate this project could find per city, each
with a real, documented gap in precision or agreement. Reproduced by
`scripts/psha/validate_independent.py` (downloads and parses the source
itself; see that script's docstrings for full citations) and locked in
offline as regression tests in `tests/test_psha.py`.

**Guatemala City** vs. Gamboa-Cante et al. (2025), *Comprehensive
Methodology for Assessing Structural Response to Probable Seismic
Motions: Application to Guatemala City*, Geosciences 15(11):427 (CC BY
4.0), whose KUKAHPAN-25 regional model gives a 475yr PGA control
earthquake of Mw 6.5-7.0, R 20-30km. No numeric PGA value is published
in text (only an unparsed map figure), so this is a magnitude/distance
disaggregation cross-check, not a PGA-value one. This project's own
475yr PGA disaggregation for Guatemala is genuinely bimodal (a near-field
~10km mode and a comparably-weighted far-field ~110km subduction mode,
see `app/data/psha/guatemala_disagg.csv`); its near-field mode (the
single largest bin, Mw 7.25, R 10km) is broadly consistent with the
published range, but the weighted-mean single-event summary the app
otherwise uses (`_controlling_event()`, ~Mw 7.3, ~78km) sits between the
two modes and matches neither well: a real, documented limitation of
collapsing a bimodal disaggregation into one (M,R) pair, not something
this cross-check papers over.

**Santo Domingo** vs. Johnson et al. (2023), *PSHA for the Dominican
Republic*, EGU23-13313 conference abstract (CC BY 4.0, freely accessible;
the peer-reviewed Johnson et al. 2024 *Earthquake Spectra* paper this
project's own source model comes from is paywalled): "in the capital
(Santo Domingo) PGA of ~0.5g is impacted by all tectonic region types",
stated for the same 2% probability of exceedance in 50yr (2475yr) level
as the preceding sentence. This project's own 2475yr PGA: 0.5183g, a
3.7% relative difference, close agreement, but against a single
order-of-magnitude figure (one significant digit, "~"), not a full
curve, so this is weaker evidence than San Jose's <0.5% full-curve match
despite the small percentage.

**Lomas del Centinela** vs. Buenrostro Orozco (2017), *Analisis de
peligro sismico para la Zona Metropolitana de Guadalajara* (UAM
Azcapotzalco Master's thesis, open access): two independent numbers, both
from the ZMG grid point closest to the site (20.7617, -103.3641):

| Return period | This project | PRODISISv4.1 (CFE 2015, official, ~7.8km away) | Thesis's own EZ-FRISK PSHA (~3.5km away) |
|---|---|---|---|
| 100yr | 0.0543g | 0.10g | (n/a) |
| 475yr | 0.1183g | 0.23g | 0.173g |
| 975yr | 0.1597g | 0.33g | (n/a) |
| 2475yr | 0.2321g | 0.54g | (n/a) |

This project's curve reads **consistently lower** than both independent
Mexican sources at every shared return period (by roughly a third to
half). Not a match: a real, unresolved discrepancy. Worth noting in its
own right: the thesis's own EZ-FRISK PSHA also reads meaningfully higher
than PRODISIS at the same sites (its own Table 6.4), so even these two
independently published Mexican sources disagree with each other by a
similar margin, so this project's GEM MEX-based curve isn't uniquely an
outlier so much as a third estimate in a range that already spans
roughly 2x between two "official"/published sources.

Two candidate causes were checked directly and ruled out (or found not
to explain the gap in the needed direction):

- **Reference Vs30** (this project's 800 m/s vs. the thesis/PRODISIS's
  760 m/s): moves the result a few percent at most, far too small to
  explain 30-55%.
- **GMPE choice.** The GEM MEX model's subduction-interface branches use
  NGA-Subduction-2020 GMPEs (`AbrahamsonGulerce2020SInter`,
  `KuehnEtAl2020SInter`) with `region='CAM'` (Central America), since
  those GMPEs have no Mexico-specific region option
  (`SUPPORTED_REGIONS` in hazardlib is `GLO/USA-AK/CAS/CAM/JPN/NZL/
  SAM/TWN`). The natural hypothesis was that this underpredicts relative
  to the Mexico-specific attenuation laws (Youngs et al. 1997, Garcia et
  al. 2005, Arroyo et al. 2010) the thesis/PRODISIS use. Tested directly
  with `hazardlib` at this project's own dominant controlling scenario
  for Lomas del Centinela (Mw 7.75-8.75, R~210km, from
  `psha.disaggregation("lomas_centinela", 475)`): `ArroyoEtAl2010SInter`
  (Mexico-specific) gives **lower** median PGA than the CAM-regionalized
  GEM branches at that scenario (e.g. Mw8.75/R210km: Arroyo 0.026g vs.
  AbrahamsonGulerce2020SInter-CAM 0.037g), the opposite of what would be
  needed to explain the gap. (At smaller magnitude/shorter distance,
  e.g. Mw6.5/R50km, Arroyo reads higher than the CAM branches, so the
  two GMPE families cross over; but at the scenario that actually
  dominates this project's own hazard curve, GMPE choice is not the
  explanation.)

Not yet ruled out, and the most likely remaining explanation: **source
characterization** (which fault/area sources are included near Jalisco,
their recurrence rates, Mmax) differing between GEM's regional MEX
model and CFE's own national seismic zonation, i.e. the two models may
simply disagree on how much annual seismic rate the region around
Guadalajara gets assigned, or even on which scenario controls the
hazard there at all. This can't be checked without CFE's own zonation
parameters (PRODISIS is closed-source), so it remains open. The MEX
model's reduced 200-of-155,520 logic-tree sample (see below) is a
secondary, lower-likelihood suspect: pure logic-tree sampling adds
variance to the p16/p84 bands but shouldn't systematically bias the
mean curve low.

## Per-city summary

| | San Jose | Guatemala City | Santo Domingo | Lomas del Centinela |
|---|---|---|---|---|
| Source model | CRSHM2022 (unmodified) | GEM CCA, CAM-restricted | GEM DR model | GEM MEX (unmodified) |
| Source-model branches used | 1 of 1 (full) | 2 of 2 (both fault-geometry variants, full) | 16-sample of 96 | 200-sample of 155,520 |
| GMPE branches | 11, 45 combos | 24, 864 combos (x2 fault branches) | 9, sampled jointly with source | 65 across 7 TRTs, sampled jointly with source |
| Reference Vs30 | 760 m/s | 800 m/s | 800 m/s | 800 m/s |
| Investigation time | 50 yr | 1 yr | 1 yr | 1 yr |
| Published validation curve | Yes, <0.5% | No | No | No |
| Independent cross-check (weaker, see above) | (n/a) | Disaggregation only, near-field mode consistent | Single-point PGA, 3.7% diff | Single-point PGA, ~30-55% lower than 2 sources |

Guatemala's source-model epistemic uncertainty (fault-geometry
alternatives) is fully enumerated (2 branches, weight 0.5/0.5). Santo
Domingo and Lomas del Centinela both use logic-tree sampling rather than
full enumeration (96 and 155,520 combinations respectively, too many to
run fully on modest hardware, the same sampling technique the GEM CCA
model's own published job.ini uses at regional scale), so their p16/p84
bands mix real source-model/GMPE spread with sampling noise, a
documented and bounded tradeoff. For Lomas del Centinela this shows up
as the mean curve slightly exceeding p84 at the most extreme grid levels
(PGA/SA >= ~3g, annual PoE below ~3e-8, return periods beyond a million
years) -- far past the 475/975/2475yr levels this project actually uses
(PoE ~4e-4 to 2e-3), see `backend/scripts/psha/README.md`.

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
- Disaggregation implemented for PGA, all 4 cities, as a scalar
  controlling-event summary (see `docs/disaggregation_plan.md`). Not
  yet: a magnitude by distance heatmap, disaggregation for other IMTs,
  or a check against San Jose's own published disaggregation file.
- Guatemala/Santo Domingo/Lomas del Centinela have no published
  validation curve at the exact site; confidence is internal-consistency
  plus method-level cross-check, plus one independent-source cross-check
  each, weaker than San Jose's direct comparison (see section 3). Lomas
  del Centinela's is a real, unresolved discrepancy (this project's
  curve reads ~30-55% lower than two independent Mexican sources), not
  yet investigated further.
- No tiling or pagination if the exposure dataset grows to whole-city
  scale.
