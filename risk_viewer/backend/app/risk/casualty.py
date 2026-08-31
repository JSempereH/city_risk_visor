"""Earthquake casualty rates from the HAZUS-MH Earthquake Model Technical
Manual (FEMA, MR4 edition), Chapter 13.

Casualties are reported at four injury-severity levels (Table 13.1):

1. Basic first aid (sprain, minor cut, minor burn).
2. Hospitalization, not life-threatening (fracture, major burn).
3. Life-threatening if untreated (uncontrolled bleeding, crush syndrome).
4. Instantaneously killed or mortally injured.

Rates are per person present indoors, by HAZUS model building type and
structural damage state (Tables 13.3-13.7). The complete damage state is
split into "no collapse" and "with collapse" cases, combined here using
each building type's collapse probability (Table 13.8), since a building
in the complete damage state is not necessarily a collapsed one. Outdoor
casualty rates (Tables 13.9-13.11) are not used, since this app only
tracks day/night indoor occupancy (see population.py), not an indoor/
outdoor population split.

HAZUS defines 36 US model building types; this app's structural classes
(ml_structural_system's ADO/CR/M/W plus the GEM-taxonomy masonry
sub-classes MUR/MCF/MR, see app/vulnerability/building_mapping.py and
gem_fragility.py) map to the closest available type, split by story
count where HAZUS itself splits by height (Chapter 3, Table 3.1):

- W (wood) -> W1, light wood frame. HAZUS gives W1 no height split.
- CR (reinforced concrete) -> C1L/C1M/C1H, concrete moment frame, by
  story count (1-3 / 4-7 / 8+).
- M, ADO, MUR (generic, adobe, and unreinforced masonry) -> URML/URMM,
  unreinforced masonry bearing walls, by story count (1-2 / 3+).
- MCF, MR (confined and reinforced masonry) -> RM1L/RM1M, reinforced
  masonry bearing walls with wood or metal deck diaphragms, by story
  count (1-3 / 4+; RM1 has no high-rise tier). RM1, not RM2 (precast
  concrete diaphragms), since this app has no diaphragm-type attribute
  to pick between them and the pilot cities' masonry stock is
  residential with light (wood/metal) roof structures, not precast
  concrete floor systems, the same light-construction assumption already
  used for CR -> C1 and W -> W1 above. Confined masonry's cast-in-place
  tie-columns/beams aren't a HAZUS model building type of their own;
  RM1's reinforced-bearing-wall behavior is the closest match HAZUS
  defines. Now that MCF/MR route here instead of sharing URML/URMM, both
  the *likelihood* of reaching a given damage state (GEM fragility
  curves, see gem_fragility.py) and the casualty rate *given* that
  damage state reflect confined/reinforced masonry rather than
  unreinforced masonry.
"""

from __future__ import annotations

from dataclasses import dataclass

HazusBuildingType = str

# Table 13.3: Slight structural damage. All 36 HAZUS model building types
# share the same slight-damage rate, so one entry covers every type used
# here.
_SLIGHT_RATE = (0.0005, 0.0, 0.0, 0.0)

# Table 13.4: Moderate structural damage.
_MODERATE_RATES: dict[HazusBuildingType, tuple[float, float, float, float]] = {
    "W1": (0.0025, 0.00030, 0.0, 0.0),
    "C1L": (0.0025, 0.00030, 0.0, 0.0),
    "C1M": (0.0025, 0.00030, 0.0, 0.0),
    "C1H": (0.0025, 0.00030, 0.0, 0.0),
    "RM1L": (0.0020, 0.00025, 0.0, 0.0),
    "RM1M": (0.0020, 0.00025, 0.0, 0.0),
    "URML": (0.0035, 0.00400, 0.00001, 0.00001),
    "URMM": (0.0035, 0.00400, 0.00001, 0.00001),
}

# Table 13.5: Extensive structural damage.
_EXTENSIVE_RATES: dict[HazusBuildingType, tuple[float, float, float, float]] = {
    "W1": (0.01, 0.001, 0.00001, 0.00001),
    "C1L": (0.01, 0.001, 0.00001, 0.00001),
    "C1M": (0.01, 0.001, 0.00001, 0.00001),
    "C1H": (0.01, 0.001, 0.00001, 0.00001),
    "RM1L": (0.01, 0.001, 0.00001, 0.00001),
    "RM1M": (0.01, 0.001, 0.00001, 0.00001),
    "URML": (0.02, 0.002, 0.00002, 0.00002),
    "URMM": (0.02, 0.002, 0.00002, 0.00002),
}

# Table 13.6: Complete structural damage, no collapse.
_COMPLETE_NO_COLLAPSE_RATES: dict[HazusBuildingType, tuple[float, float, float, float]] = {
    "W1": (0.05, 0.01, 0.0001, 0.0001),
    "C1L": (0.05, 0.01, 0.0001, 0.0001),
    "C1M": (0.05, 0.01, 0.0001, 0.0001),
    "C1H": (0.05, 0.01, 0.0001, 0.0001),
    "RM1L": (0.05, 0.01, 0.0001, 0.0001),
    "RM1M": (0.05, 0.01, 0.0001, 0.0001),
    "URML": (0.10, 0.02, 0.0002, 0.0002),
    "URMM": (0.10, 0.02, 0.0002, 0.0002),
}

# Table 13.7: Complete structural damage, with collapse.
_COMPLETE_WITH_COLLAPSE_RATES: dict[HazusBuildingType, tuple[float, float, float, float]] = {
    "W1": (0.40, 0.20, 0.03, 0.05),
    "C1L": (0.40, 0.20, 0.05, 0.10),
    "C1M": (0.40, 0.20, 0.05, 0.10),
    "C1H": (0.40, 0.20, 0.05, 0.10),
    "RM1L": (0.40, 0.20, 0.05, 0.10),
    "RM1M": (0.40, 0.20, 0.05, 0.10),
    "URML": (0.40, 0.20, 0.05, 0.10),
    "URMM": (0.40, 0.20, 0.05, 0.10),
}

# Table 13.8: probability of collapse given the complete damage state.
_COLLAPSE_PROBABILITY: dict[HazusBuildingType, float] = {
    "W1": 0.03,
    "C1L": 0.13,
    "C1M": 0.10,
    "C1H": 0.05,
    "RM1L": 0.13,
    "RM1M": 0.10,
    "URML": 0.15,
    "URMM": 0.15,
}


def hazus_building_type(structural_system_class: str, n_floors: float | None) -> HazusBuildingType:
    floors = n_floors if n_floors and n_floors > 0 else 1
    if structural_system_class == "W":
        return "W1"
    if structural_system_class == "CR":
        if floors <= 3:
            return "C1L"
        if floors <= 7:
            return "C1M"
        return "C1H"
    if structural_system_class in ("M", "ADO", "MUR"):
        # Unreinforced/generic masonry. See module docstring.
        return "URML" if floors <= 2 else "URMM"
    if structural_system_class in ("MCF", "MR"):
        # Confined/reinforced masonry. See module docstring.
        return "RM1L" if floors <= 3 else "RM1M"
    # A new city's structural taxonomy (e.g. steel, hybrid) has no HAZUS
    # mapping decided for it yet, so fail loudly here rather than silently
    # costing it as masonry, which this module's tables were never
    # designed to represent for that class.
    raise ValueError(f"no HAZUS building-type mapping for structural class {structural_system_class!r}")


def _complete_rate(building_type: HazusBuildingType) -> tuple[float, float, float, float]:
    p_collapse = _COLLAPSE_PROBABILITY[building_type]
    nc = _COMPLETE_NO_COLLAPSE_RATES[building_type]
    wc = _COMPLETE_WITH_COLLAPSE_RATES[building_type]
    return (
        p_collapse * wc[0] + (1 - p_collapse) * nc[0],
        p_collapse * wc[1] + (1 - p_collapse) * nc[1],
        p_collapse * wc[2] + (1 - p_collapse) * nc[2],
        p_collapse * wc[3] + (1 - p_collapse) * nc[3],
    )


@dataclass(frozen=True)
class CasualtyEstimate:
    severity_1: float
    severity_2: float
    severity_3: float
    severity_4: float

    @property
    def total(self) -> float:
        return self.severity_1 + self.severity_2 + self.severity_3 + self.severity_4


def rates_by_damage_state(
    building_type: HazusBuildingType,
) -> dict[str, tuple[float, float, float, float]]:
    """Per-severity-level rate (fractions, not percent) at each damage
    state, "none" included as all-zero. Shared by `expected_casualties`
    (probability-weighted) and `monte_carlo.py` (sampled per trial)."""
    return {
        "none": (0.0, 0.0, 0.0, 0.0),
        "slight": _SLIGHT_RATE,
        "moderate": _MODERATE_RATES[building_type],
        "extensive": _EXTENSIVE_RATES[building_type],
        "complete": _complete_rate(building_type),
    }


def expected_casualties(
    structural_system_class: str,
    n_floors: float | None,
    state_probability: dict[str, float],
    population: float,
) -> CasualtyEstimate:
    building_type = hazus_building_type(structural_system_class, n_floors)
    totals = [0.0, 0.0, 0.0, 0.0]
    for damage_state, rates in rates_by_damage_state(building_type).items():
        prob = state_probability.get(damage_state, 0.0)
        for i in range(4):
            totals[i] += prob * rates[i] * population
    return CasualtyEstimate(*totals)
