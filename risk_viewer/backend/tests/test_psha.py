import math

import pytest

from app.hazard import psha
from app.hazard.scenario import PROBABILISTIC_RETURN_PERIODS_YEARS, probabilistic_scenario
from app.hazard.spectrum import SPECTRUM_PERIODS_S

SAN_JOSE_LAT, SAN_JOSE_LON = 9.9281, -84.0907


def test_return_period_to_target_poe_475yr():
    # Standard code-level check: 475yr return period corresponds to ~10%
    # probability of exceedance in the (also standard) 50-year window.
    poe = psha.return_period_to_target_poe(475, investigation_time_years=50.0)
    assert poe == pytest.approx(1 - math.exp(-50 / 475), rel=1e-9)
    assert 0.09 < poe < 0.10


def test_sa_increases_with_return_period():
    # A rarer (longer return period) event should always mean higher Sa.
    values = [
        psha.sa_by_period_for_return_period("san_jose", tr)[0.2]
        for tr in PROBABILISTIC_RETURN_PERIODS_YEARS
    ]
    assert values == sorted(values)
    assert values[0] > 0


def test_pga_matches_published_hidalgo_leiva_validation():
    # Regression check locking in the calc_hazard_curves() computation
    # against Hidalgo-Leiva et al. (2022)'s own published San Jose PGA
    # curve (see docs/psha_plan.md's validation table): at PGA=0.1032g the
    # published 50-year mean PoE is 0.9433; this precomputed CSV's own
    # value is 0.9447 (0.14% relative difference, well within the <0.5%
    # agreement documented in docs/psha_plan.md). If this drifts further,
    # either the precomputed CSV or the source/GMPE data underneath it
    # changed.
    levels, poe = psha._hazard_curves("san_jose")["PGA"]["mean"]
    idx = (abs(levels - 0.103153) < 1e-4).nonzero()[0][0]
    computed = float(poe[idx])
    published = 0.9433346
    assert computed == pytest.approx(0.9446826, abs=1e-4)
    assert abs(computed - published) / published < 0.005


def test_build_demand_spectrum_psha_shape():
    spectrum = psha.build_demand_spectrum_psha("san_jose", 475, SAN_JOSE_LAT, SAN_JOSE_LON, 760.0)
    assert spectrum.periods_s == SPECTRUM_PERIODS_S
    assert len(spectrum.sa_g) == len(SPECTRUM_PERIODS_S)
    assert all(sa > 0 for sa in spectrum.sa_g)
    # See psha.py's module docstring: aleatory variability is already
    # integrated into the hazard curve, so there is nothing left to
    # report as a separate GMPE sigma.
    assert all(s == 0.0 for s in spectrum.sigma_ln)


def test_vs30_amplification_softer_soil_higher():
    rock = psha.sa_at_period_psha("san_jose", 475, 0.3, SAN_JOSE_LAT, SAN_JOSE_LON, 760.0)
    soft = psha.sa_at_period_psha("san_jose", 475, 0.3, SAN_JOSE_LAT, SAN_JOSE_LON, 250.0)
    assert soft > rock > 0


def test_vs30_amplification_uses_each_return_periods_own_controlling_event():
    # Each return period's disaggregated controlling event is genuinely
    # different (see docs/disaggregation_plan.md's results table). This
    # is the actual point of computing the amplification ratio per return
    # period instead of at one fixed representative event.
    events = {years: psha._controlling_event("san_jose", years) for years in (475, 975, 2475)}
    assert all(event is not None for event in events.values())
    assert len(set(events.values())) == 3
    for magnitude, distance_km in events.values():  # type: ignore[misc]
        assert 5.0 < magnitude < 8.0
        assert 0.0 < distance_km < 200.0


def test_vs30_amplification_falls_back_without_disaggregation_data(monkeypatch):
    monkeypatch.setattr(psha, "_controlling_event", lambda city, years: None)
    # Should not raise, and should still amplify sensibly, using the
    # DSHA scenario's own event as the fallback.
    rock = psha.sa_at_period_psha("san_jose", 475, 0.3, SAN_JOSE_LAT, SAN_JOSE_LON, 760.0)
    soft = psha.sa_at_period_psha("san_jose", 475, 0.3, SAN_JOSE_LAT, SAN_JOSE_LON, 250.0)
    assert soft > rock > 0


def test_probabilistic_scenario_factory():
    scenario = probabilistic_scenario("san_jose", 475)
    assert scenario.mode == "probabilistic"
    assert scenario.return_period_years == 475
    assert scenario.city == "san_jose"


def test_all_pilot_cities_supported():
    assert psha.PSHA_SUPPORTED_CITIES == frozenset(
        {"san_jose", "guatemala", "santo_domingo", "lomas_centinela"}
    )


@pytest.mark.parametrize("city", ["san_jose", "guatemala", "santo_domingo", "lomas_centinela"])
def test_percentile_bands_bracket_mean(city):
    # p16/p84 come from the Engine's quantile_hazard_curves output for the
    # full GMPE logic tree, so at every level of practical interest
    # p16 <= mean <= p84 must hold. Only checked above 1e-6 (annual PoE):
    # lomas_centinela's 200-sample reduced logic tree (see
    # scripts/psha/README.md) shows mean slightly exceeding p84 at its most
    # extreme grid levels (PGA/SA >= ~3g, PoE ~1e-9 to 3e-8, return periods
    # beyond a million years) -- a few high-rate realizations pulling the
    # mean above a 200-sample 84th-percentile estimate, not a bug: this
    # project's actual return periods of interest (475/975/2475yr) sit at
    # PoE ~4e-4 to 2e-3, many orders of magnitude above where this happens.
    assert set(psha.available_percentiles(city)) >= {"mean", "p16", "p84"}
    _, mean_poe = psha._hazard_curves(city)["PGA"]["mean"]
    _, p16_poe = psha._hazard_curves(city)["PGA"]["p16"]
    _, p84_poe = psha._hazard_curves(city)["PGA"]["p84"]
    relevant = mean_poe > 1e-6
    assert relevant.any()
    assert (p16_poe[relevant] <= mean_poe[relevant] + 1e-12).all()
    assert (mean_poe[relevant] <= p84_poe[relevant] + 1e-12).all()


@pytest.mark.parametrize("city", ["guatemala", "santo_domingo"])
def test_sa_increases_with_return_period_other_cities(city):
    values = [
        psha.sa_by_period_for_return_period(city, tr)[0.2]
        for tr in PROBABILISTIC_RETURN_PERIODS_YEARS
    ]
    assert values == sorted(values)
    assert values[0] > 0


# Independent-source cross-checks for the 3 cities with no published curve
# at their exact site (see docs/psha_plan.md's Validation section). Values
# below are reproduced from scripts/psha/validate_independent.py, which
# fetches and parses the underlying sources at run time; these tests
# hardcode the same numbers so this regression check runs offline in CI
# (no network, no pdftotext) rather than re-fetching every run.


def test_guatemala_disaggregation_near_field_mode_matches_published_control_earthquake():
    # Gamboa-Cante et al. (2025), Geosciences 15(11):427 (KUKAHPAN-25
    # regional model): Guatemala City's 475yr PGA control earthquake is
    # Mw 6.5-7.0, R 20-30km. This project's own 475yr PGA disaggregation
    # is bimodal (see scripts/psha/validate_independent.py's note); its
    # near-field mode (single largest bin) is the comparable one.
    disagg = psha.disaggregation("guatemala", 475)
    assert disagg is not None
    bins = disagg["bins"]  # type: ignore[index]
    top_bin = max(bins, key=lambda b: b["fraction"])  # type: ignore[arg-type]
    assert 6.0 <= top_bin["mag_bin"] <= 7.5
    assert top_bin["dist_bin"] <= 40.0


def test_santo_domingo_2475yr_pga_matches_published_estimate():
    # Johnson et al. (2023), EGU23-13313 abstract (CC BY 4.0): Santo
    # Domingo's PGA at 2% probability of exceedance in 50yr (2475yr) is
    # "~0.5g". A single order-of-magnitude point, not a full curve.
    published_pga = 0.5
    our_pga = psha.sa_by_period_for_return_period("santo_domingo", 2475)[0.01]
    assert abs(our_pga - published_pga) / published_pga < 0.10


def test_lomas_centinela_pga_lower_than_published_mexican_sources():
    # Buenrostro Orozco (2017) UAM thesis: PRODISISv4.1 (CFE's official
    # 2015 hazard tool) gives 0.23g/0.54g at 475/2475yr for a ZMG site
    # ~7.8km from Lomas del Centinela; the thesis's own EZ-FRISK PSHA
    # gives 0.173g at 475yr for a closer (~3.5km) point. This project's
    # own curve reads consistently *lower* than both, a real,
    # unresolved discrepancy (see docs/psha_plan.md), not a match. This
    # test locks in that known gap so it's visible if it changes.
    our_475 = psha.sa_by_period_for_return_period("lomas_centinela", 475)[0.01]
    our_2475 = psha.sa_by_period_for_return_period("lomas_centinela", 2475)[0.01]
    assert our_475 < 0.173  # thesis's own EZ-FRISK value, closest site
    assert our_475 < 0.23  # PRODISIS/CFE 2015, official
    assert our_2475 < 0.54  # PRODISIS/CFE 2015, official
