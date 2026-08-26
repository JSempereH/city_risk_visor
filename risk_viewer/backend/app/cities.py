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
        scenario_label="Mw 6.5, Zapopan Graben (Tesistan Valley) crustal normal fault",
        magnitude=6.5,
        depth_km=8.0,
        epicenter_lat=20.796944,
        epicenter_lon=-103.479444,
        tectonic_regime="crustal",
        deterministic_source_note=(
            "Quinteros-Cartaya, C., Solorio-Magana, G., Nunez-Cornu, F.J., "
            "Escalona-Alcazar, F.J. & Nunez, D. (2023), 'Microearthquakes in the "
            "Guadalajara Metropolitan Zone, Mexico: evidence from buried active faults "
            "in Tesistan Valley, Zapopan', Natural Hazards 116(3), 2797-2818, a "
            "seismological study of this exact area (temporary local network, "
            "Sep 2017-Jan 2018, 188 located microearthquakes, 11 clusters). It documents "
            "two buried normal faults bounding the Zapopan Graben, east (16 km, Mw up to "
            "~6.2) and west (28 km, Mw up to ~6.5), with associated seismicity at 0-13.5 km "
            "depth; the larger (west) fault is used here as the more conservative controlling "
            "event, depth_km=8.0 as the midpoint of the observed range. Corroborated by "
            "Martinez-Jaramillo, D., Zuniga, F.R., Wyss, M., Lacan, P. & Nunez Meneses, A. "
            "(2025), 'Fatality estimates based on earthquake modeling in the Guadalajara "
            "Metropolitan Area', Natural Hazards 121(10), 11443-11457, which uses this same "
            "structure for city-scale scenario/fatality modeling. Epicenter placed at "
            "Tesistan (20.796944, -103.479444), the locality nearest the documented "
            "seismicity, an illustrative point ~12.6 km from Lomas del Centinela, not the "
            "paper's own fault trace geometry (not published at that resolution); rake=-90 "
            "(normal faulting), consistent with the graben's extensional setting at the "
            "Tepic-Zacoalco/Chapala-Tula/Colima rift triple junction. Replaces this project's "
            "earlier choice of the 1932 Mw 8.1 Jalisco-Colima subduction mainshock (Singh, "
            "Ponce & Nishenko 1985): that event is ~168 km away and, even though it caused "
            "real historical damage in Guadalajara's own soft-soil lakebed center, produces "
            "negligible shaking this far from the interface at Lomas del Centinela's stiffer "
            "hillside site; this closer, shallower crustal source is the more representative "
            "controlling event for this specific neighborhood."
        ),
        rake=-90.0,
        probabilistic_source_note=(
            "GEM Foundation's Mexico (MEX) national hazard model, v2025.0.0 (Johnson, Styron, "
            "Brooks et al.), CC BY-NC-SA 4.0, same license class already used here for "
            "Guatemala City's CCA model. Single source-model branch (no fault-geometry-style "
            "epistemic choice to restrict, unlike Guatemala); the full GMPE logic tree spans "
            "7 tectonic region types (MEX/CAM/USA crustal, CAM interface, CAM intraslab) with "
            "155,520 possible combinations, run at a 200-sample reduction (see "
            "scripts/psha/README.md) rather than full enumeration, the same sampling technique "
            "already used for Santo Domingo. No published hazard curve exists at this exact "
            "site to validate against directly."
        ),
        reference_vs30=800.0,
        investigation_time_years=1.0,
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
