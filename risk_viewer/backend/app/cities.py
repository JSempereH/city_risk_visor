"""Single source of truth for each pilot city's inherent, hand-entered
scientific parameters: the deterministic scenario (magnitude, epicenter,
tectonic regime, rake/ztor; see hazard/scenario.py's own docstring for
the published sources behind each), and the PSHA reference Vs30 /
investigation time (pulled from that city's own OpenQuake job.ini, see
scripts/psha/configs/{city}/).

This is the one place a new city's science goes in. Adding a city that
has real per-building exposure data, a tectonic-regime-compatible GMPE
(see hazard/gmpe.py), and someone doing the actual seismological work of
defining its scenario, means adding one CityProfile entry here. Every
other module that needs to know "which cities exist" derives it from
this dict or from data-file presence (app/data/{vs30,population,psha,
typology_ensemble}/{city}...), not from a separately hardcoded list.

A CityProfile with no PSHA model yet (reference_vs30/investigation_time_
years both None) is valid: it can still have a deterministic scenario,
just no probabilistic one until its source model is built.

This module is deliberately a leaf: no imports from config.py/
scenario.py/psha.py, so nothing importing it risks a cycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

TectonicRegime = Literal["crustal", "interface", "intraslab"]


@dataclass(frozen=True)
class CityProfile:
    city: str
    scenario_label: str
    magnitude: float
    depth_km: float
    epicenter_lat: float
    epicenter_lon: float
    tectonic_regime: TectonicRegime
    deterministic_source_note: str
    rake: float = 0.0
    ztor_km: Optional[float] = None
    probabilistic_source_note: Optional[str] = None
    reference_vs30: Optional[float] = None
    investigation_time_years: Optional[float] = None
    # Fixed epistemic-uncertainty contribution for a city with no
    # per-building ML typology ensemble (get_ensemble_info() returns
    # None): a documented, deliberately-wide constant, not derived from
    # classifier disagreement like typology_beta_from_entropy() (see
    # app/risk/uncertainty.py and scripts/exposure/README.md). None means
    # "this city has a real ensemble, use that instead" (the 3 pilot
    # cities' existing behaviour, unaffected).
    typology_beta_generic: Optional[float] = None


CITIES: dict[str, CityProfile] = {
    "guatemala": CityProfile(
        city="guatemala",
        scenario_label="Mw 7.0, Motagua-Jalpatagua fault system",
        magnitude=7.0,
        depth_km=15.0,
        epicenter_lat=14.794,
        epicenter_lon=-90.342,
        tectonic_regime="crustal",
        deterministic_source_note=(
            "Controlling source per Benito et al. (2012); illustrative "
            "point epicenter ~25 km NE of the city, not the paper's full rupture geometry."
        ),
        rake=0.0,  # left-lateral strike-slip, Motagua-Jalpatagua system
        probabilistic_source_note=(
            "GEM Foundation's Caribbean & Central America (CCA) regional hazard model "
            "(Johnson, Styron, Brooks et al., built under the USAID-funded CCARA/FORCE "
            "projects; hazard.openquake.org/gem/models/CCA), restricted to Guatemala/CAM-"
            "tagged sources. Mean hazard curve across the full GMPE logic tree and both "
            "fault-geometry source-model branches (864 realisations; see docs/psha_plan.md), "
            "at reference Vs30 = 800 m/s; no published curve for this exact site was "
            "available to validate against directly."
        ),
        reference_vs30=800.0,
        investigation_time_years=1.0,
    ),
    "san_jose": CityProfile(
        city="san_jose",
        scenario_label="Mw 7.5, Cocos-Caribbean subduction interface",
        magnitude=7.5,
        depth_km=25.0,
        epicenter_lat=9.450,
        epicenter_lon=-84.576,
        tectonic_regime="interface",
        deterministic_source_note=(
            "Tectonic regime per Hidalgo-Leiva et al. (2022); illustrative "
            "point epicenter ~75 km SW of the city (toward the Pacific interface)."
        ),
        # Top of rupture kept shallower than the 25 km hypocentral/centroid
        # depth above. See hazard/scenario.py's module docstring and gmpe.py for why.
        ztor_km=15.0,
        probabilistic_source_note=(
            "Hidalgo-Leiva et al. (2022), 'The 2022 Seismic Hazard Model for Costa Rica' "
            "(CRSHM2022); source model and GMPE logic tree via Arroyo (2025), Mendeley Data "
            "DOI 10.17632/7x8xv2yf23.2. Mean hazard curve across the full GMPE logic tree, "
            "at reference Vs30 = 760 m/s; validated against the paper's own published "
            "curves for San Jose (see docs/psha_plan.md)."
        ),
        reference_vs30=760.0,
        investigation_time_years=50.0,
    ),
    "santo_domingo": CityProfile(
        city="santo_domingo",
        scenario_label="Mw 7.0, Enriquillo-Plantain Garden fault system",
        magnitude=7.0,
        depth_km=15.0,
        epicenter_lat=18.486,
        epicenter_lon=-70.216,
        tectonic_regime="crustal",
        deterministic_source_note=(
            "Same fault system as the 2010 Mw 7.0 Haiti earthquake; per "
            "Johnson et al. (2024)'s characterisation of DR's fault sources. "
            "Illustrative point epicenter ~30 km west, along the fault's trend."
        ),
        rake=0.0,  # left-lateral strike-slip, Enriquillo-Plantain Garden system
        probabilistic_source_note=(
            "GEM Foundation's Dominican Republic hazard model (built under the "
            "USAID-funded TREQ project; globalquakemodel.org/product/dominican-republic-"
            "hazard-model). Mean hazard curve across a 16-sample logic-tree draw spanning "
            "both the full GMPE tree and the source model's 96-combination source/extend "
            "tree (see docs/psha_plan.md), at reference Vs30 = 800 m/s; no published curve "
            "for this exact site was available to validate against directly."
        ),
        reference_vs30=800.0,
        investigation_time_years=1.0,
    ),
    "lomas_centinela": CityProfile(
        city="lomas_centinela",
        scenario_label="Mw 8.1, 3 June 1932 Jalisco-Colima subduction mainshock",
        magnitude=8.1,
        depth_km=60.0,
        epicenter_lat=19.5,
        epicenter_lon=-104.25,
        tectonic_regime="interface",
        deterministic_source_note=(
            "Real historical event, not an illustrative magnitude: the Mw 8.1 (Ms 8.2) "
            "3 June 1932 mainshock, per Singh, Ponce & Nishenko (1985), 'The great Jalisco, "
            "Mexico, earthquakes of 1932: Subduction of the Rivera plate', BSSA 75(5), the "
            "standard anchor event for Jalisco seismic hazard (CENAPRED/SSN); much of its "
            "historical damage and casualties concentrated in Guadalajara despite the ~170 km "
            "distance, attributed to local soil response. Illustrative point epicenter, not "
            "the paper's full rupture geometry; ztor_km assumed shallower than the 60 km "
            "hypocentral depth for a large interface rupture, same convention as san_jose. "
            "A closer but smaller-magnitude alternative controlling source exists locally: "
            "SSN/UNAM attribute Zapopan's own highest-in-ZMG seismicity to the Tesistan and "
            "Rio Santiago crustal faults, not modeled here."
        ),
        ztor_km=20.0,
        # No PSHA source model integrated yet (candidate: GEM's Mexico national model,
        # MEX v2025.0.0, CC BY-NC 4.0, license not yet checked for this use), so
        # reference_vs30 and investigation_time_years stay None, a deterministic-only
        # CityProfile, same as this module's docstring says is valid.
        typology_beta_generic=0.6,
    ),
    # la_guaira (Venezuela) was built and wired up 2026-08-11: real
    # footprints, real observed damage, a real deterministic scenario,
    # but pulled back out for now over data-quality concerns (the
    # city-wide generic CR/pre_code typology assumption, and the gap
    # between modeled and observed damage; see scripts/exposure/
    # README.md, which also documents its CityProfile field values).
    # The build script and raw downloads are kept in place; re-adding it
    # means re-running scripts/exposure/build_venezuela.py and restoring
    # its CityProfile entry from that README.
}
