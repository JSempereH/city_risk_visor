"""An expert-specified structural-typology hypothesis for a city: "I
believe this population of buildings is roughly 80% M, 10% CR, 5% ADO,
5% W", used in place of (or as an addition to) a single hard-coded
generic assumption (e.g. lomas_centinela's uniform "every building is
MCF", see scripts/exposure/assign_lomas_centinela_typology.py) or a
per-building ML ensemble prediction.

This module deliberately does not invent a new damage-calculation
mechanism. It reuses this project's existing single-class-per-building
architecture end to end (app/risk/service.py's compute_building_risk(),
app/vulnerability/service.py's compute_vulnerability(), one fragility
curve set per building), the same one already used for the 3 pilot
cities' ML ensemble and for every other city's generic assumption. What
this module adds is:

1. A real, reproducible way to turn a population-level proportion
   hypothesis into per-building classes (sample_classes(), an exact
   quota allocation, not independent-Bernoulli sampling: the whole
   point is that the realized proportions match what was asked for, not
   merely approximate it under sampling noise).
2. A real uncertainty measure for those synthetic per-building labels
   (hypothesis_typology_beta()), which reuses app/risk/uncertainty.py's
   typology_beta_from_entropy() exactly as already used for the ML
   ensemble's inter-model disagreement, just computed from the
   hypothesis's own class-mix entropy instead. A confident hypothesis
   ("95% M") contributes little extra uncertainty; an evenly split one
   contributes more, the identical logic already shipped and validated
   for the 3 pilot cities, only the source of the probability
   distribution changes (an expert's stated proportions here, a
   classifier ensemble's vote split there).

Honesty this module is built to preserve, not an afterthought: the
per-building class assignment below is ONE stochastic realization
consistent with the stated proportions, not a claim about any specific
building's real class. The aggregate expected risk under this scheme is
unbiased, but the spatial pattern of which building "looks worse" on
the map is illustrative, not a measurement. See
docs/typology_hypothesis.md (if present) or this module's own
docstrings on set_hypothesis()/sample_classes() for the full reasoning.
"""

from __future__ import annotations

import hashlib
import json
import math
import threading
from dataclasses import dataclass
from typing import Iterable

# The real structural display classes this project's risk pipeline
# understands (see app/data_loader.py::STRUCTURAL_SYSTEM_REPLACEMENTS
# and app/risk/casualty.py::hazus_building_type(), which fails loudly on
# any other value). MUR/MCF/MR (unreinforced/confined/reinforced
# masonry) let a hypothesis express exactly the kind of refinement
# lomas_centinela's own single hard-coded "every building is MCF"
# assumption (see this module's docstring, and
# scripts/exposure/assign_lomas_centinela_typology.py) can't: e.g. "80%
# MCF, 15% MUR, 5% CR" instead of one uniform label for the whole
# neighborhood. "unlabeled" is deliberately excluded: a hypothesis
# assigns a real class to every building, it never leaves one unlabeled.
KNOWN_CLASSES = ("ADO", "CR", "M", "MCF", "MR", "MUR", "W")

# Normalizes hypothesis entropy against the full known taxonomy (4
# classes), not just however many the caller happened to name in this
# particular hypothesis: this keeps entropy comparable across different
# hypotheses (a 2-class 50/50 split and a 4-class 25/25/25/25 split are
# not treated as equally "maximally uncertain," the latter genuinely is
# more spread out over what this project can even represent).
_MAX_ENTROPY_BITS = math.log2(len(KNOWN_CLASSES))

PROPORTION_SUM_TOLERANCE = 1e-6


@dataclass(frozen=True)
class TypologyHypothesis:
    city: str
    # Sorted-tuple-of-pairs, not a dict: dicts aren't hashable, and this
    # needs to be usable as (part of) a cache key, see
    # app/hazard/scenario.py's typology_hypothesis_fingerprint field.
    proportions: tuple[tuple[str, float], ...]
    seed: int

    def proportions_dict(self) -> dict[str, float]:
        return dict(self.proportions)

    def fingerprint(self) -> str:
        """Stable short hash identifying this exact hypothesis (city,
        proportions, seed), used as part of the Scenario cache key
        (app/hazard/scenario.py) so a hypothesis-influenced result never
        gets served to, or cached over, a request without one, or a
        request under a different hypothesis. Content-addressed, not a
        counter, so the same hypothesis reapplied later still hits the
        same run_scenario() cache entry instead of forcing a recompute."""
        payload = json.dumps(
            {"city": self.city, "proportions": sorted(self.proportions), "seed": self.seed}, sort_keys=True
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


def validate_proportions(proportions: dict[str, float]) -> dict[str, float]:
    """Validates a proportions dict and returns it with zero-value
    entries dropped (kept simple downstream: sample_classes() never has
    to special-case a class with 0 buildings to assign).

    Raises ValueError with a message meant to be shown to the caller
    directly (this is a user-input validation boundary, see
    app/routers/typology_hypothesis.py), not an internal assertion.
    """
    if not proportions:
        raise ValueError("proportions must not be empty.")

    unknown = sorted(set(proportions) - set(KNOWN_CLASSES))
    if unknown:
        raise ValueError(f"Unknown structural class(es) {unknown}; expected a subset of {list(KNOWN_CLASSES)}.")

    negative = {cls: value for cls, value in proportions.items() if value < 0}
    if negative:
        raise ValueError(f"Proportions must be non-negative, got {negative}.")

    total = sum(proportions.values())
    if abs(total - 1.0) > PROPORTION_SUM_TOLERANCE:
        raise ValueError(f"Proportions must sum to 1.0, got {total:.6f}.")

    return {cls: value for cls, value in proportions.items() if value > 0}


def normalized_entropy(proportions: dict[str, float]) -> float:
    """Shannon entropy of the proportions, normalized to [0, 1] against
    the full 4-class taxonomy (see _MAX_ENTROPY_BITS): 0.0 for a single
    class at 100%, 1.0 for an even split across all 4 known classes."""
    bits = -sum(p * math.log2(p) for p in proportions.values() if p > 0)
    return max(0.0, min(1.0, bits / _MAX_ENTROPY_BITS))


def exact_quota_labels(ids: list[str], proportions: dict[str, float], seed: int) -> dict[str, str]:
    """Assigns exactly one class to each id, matching the given
    proportions (must already sum to ~1.0) as closely as integer counts
    allow, not merely in expectation the way independent per-item random
    draws would. Shared by this module's own sample_classes() (a whole
    city's worth of buildings, replacing every class) and
    typology_prior.py's sub-class split (just the buildings a prior's
    own pooling already put in one bucket, e.g. "M" -> MUR/MCF/M) --
    same algorithm, different population it's run over.

    Method: exact quota per class via the largest-remainder method
    (the same class of algorithm used for apportioning seats to
    parties by vote share), then the class labels (not the ids) are
    shuffled with the given seed and handed out in id order. Id order
    itself is never touched, so the assignment is a pure function of
    (ids, proportions, seed): the same inputs always reproduce the same
    per-id map, and which specific id lands in which class is what the
    seed controls, not the aggregate counts (those are exact,
    seed-independent).
    """
    n = len(ids)
    if n == 0:
        return {}

    classes = sorted(proportions)  # stable order, independent of dict insertion order
    exact_counts = {cls: proportions[cls] * n for cls in classes}
    base_counts = {cls: int(math.floor(exact_counts[cls])) for cls in classes}
    remainder = n - sum(base_counts.values())

    # Largest-remainder method: give the leftover slots to the classes
    # whose exact (fractional) count was closest to rounding up, ties
    # broken by class name for determinism.
    remainders = sorted(classes, key=lambda cls: (-(exact_counts[cls] - base_counts[cls]), cls))
    for cls in remainders[:remainder]:
        base_counts[cls] += 1

    labels: list[str] = []
    for cls in classes:
        labels.extend([cls] * base_counts[cls])

    import random

    random.Random(seed).shuffle(labels)

    sorted_ids = sorted(ids)  # deterministic order the shuffled labels are handed out in
    return dict(zip(sorted_ids, labels))


def sample_classes(building_ids: Iterable[str], proportions: dict[str, float], seed: int) -> dict[str, str]:
    """Assigns exactly one class to each building -- see
    exact_quota_labels() for the method. This is a synthetic realization
    consistent with the stated proportions, not a real classification of
    any specific building, see this module's own docstring."""
    return exact_quota_labels(list(building_ids), proportions, seed)


def hypothesis_typology_beta(proportions: dict[str, float]) -> float:
    """typology_beta for a hypothesis-sampled building class: reuses
    app/risk/uncertainty.py's typology_beta_from_entropy() exactly as
    already used for the ML ensemble's inter-model disagreement, fed by
    the hypothesis's own class-mix entropy instead. A confident
    hypothesis ("95% M") contributes little extra uncertainty; an evenly
    split one contributes up to the same 0.5 ceiling that function
    already applies to the ensemble case, no separate formula."""
    from app.risk.uncertainty import typology_beta_from_entropy

    return typology_beta_from_entropy(normalized_entropy(proportions))


_lock = threading.Lock()
_active: dict[str, TypologyHypothesis] = {}


def set_hypothesis(city: str, proportions: dict[str, float], seed: int = 0) -> TypologyHypothesis:
    """Sets (replacing any existing one) the active hypothesis for a
    city. Process-lifetime, in-memory state, same convention as this
    backend's other module-level state (see app/data_loader.py's
    load_geodataframe() docstring): no database, this is a research/demo
    tool for one running instance, not a multi-user persisted setting.
    """
    validated = validate_proportions(proportions)
    hypothesis = TypologyHypothesis(city=city, proportions=tuple(sorted(validated.items())), seed=seed)
    with _lock:
        _active[city] = hypothesis
    return hypothesis


def get_hypothesis(city: str) -> TypologyHypothesis | None:
    with _lock:
        return _active.get(city)


def clear_hypothesis(city: str) -> None:
    with _lock:
        _active.pop(city, None)
