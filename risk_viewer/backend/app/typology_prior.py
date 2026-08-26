"""An expert-specified, whole-city/neighborhood structural-typology
*prior*: "I know this population is roughly 80% M, 10% MR, 5% ADO, 5% W",
combined with the typology classifier ensemble's own per-building
prediction, instead of either trusting the raw ensemble alone or
replacing it outright.

Deliberately NOT the same mechanism as app/typology_hypothesis.py: that
one is a population-level override that reassigns EVERY building
(including ones with a real recorded structural_system) to a synthetic
sampled class, a fresh illustrative realization each time. This module
does the opposite on both counts:

1. **Ground truth is never touched.** A building with a real recorded
   structural_system (structural_system_estimated == False) keeps it,
   always -- only ML-estimated buildings (a real ensemble prediction
   filled a genuine gap, see data_loader.py::_fill_unlabeled_from_ensemble)
   are ever adjusted. This is the whole point: the model's own evidence
   is the only thing being corrected here, not confirmed data.
2. **The stated percentage is for the whole population, ground truth
   included.** If a city already has 200 confirmed "M" buildings out of
   1,000 total and the user asks for "80% M", only the remaining 800
   buildings' worth of target (800 - 200 = 600) is actually asked of the
   1,000-200=800 ML-estimated buildings -- not "80% of the estimated
   buildings should become M". Ground truth that already exceeds the
   requested share makes a request infeasible (see compute_feasible_prior),
   surfaced as a real error, not silently reinterpreted or clamped.

Per-building adjustment reuses the exact geometric-pooling formula
already designed and tested in ml_structural_system/prior_adjustment.py
(posterior_k ~ prior_k^alpha * mean_proba_k^(1-alpha)), reimplemented
here rather than imported: this backend never imports ml_structural_system
code, the same no-cross-import convention app/vulnerability/capacity_model.py
already uses for FragilityCurves (it reads that project's output files,
never its Python).
"""

from __future__ import annotations

import hashlib
import json
import math
import threading
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from app.typology_ensemble import get_ensemble_info
from app.typology_hypothesis import exact_quota_labels

PROPORTION_SUM_TOLERANCE = 1e-6
_PRIOR_FLOOR = 1e-12

# structural_system_class keeps GEM Building Taxonomy sub-types distinct
# for display/vulnerability-tier routing (see data_loader.py's
# STRUCTURAL_SYSTEM_REPLACEMENTS), but the classifier ensemble was never
# trained to tell them apart -- it only ever outputs one generic "M" (or
# "W"/"CR" for the light-frame/S_frame sub-types). A ground-truth
# building recorded as e.g. "MUR" must still count toward "M" when
# netting ground truth out of a requested city-wide percentage, or the
# math below would silently ignore real confirmed masonry buildings.
_ENSEMBLE_BUCKET = {"MUR": "M", "MCF": "M", "MR": "M", "S_light": "W", "S_frame": "CR"}


def _ensemble_bucket(display_class: str) -> str:
    return _ENSEMBLE_BUCKET.get(display_class, display_class)


# Real, displayable structural_system_class values (data_loader.py's
# STRUCTURAL_SYSTEM_REPLACEMENTS permanently folds S_light/S_frame into
# W/CR before any of this ever runs, so those two -- unlike the three
# below -- never reach here as an actual class value, and are
# deliberately left out even though _ENSEMBLE_BUCKET above still names
# them for ground-truth netting) that the classifier ensemble was never
# trained to tell apart from generic "M" (too few labeled examples --
# e.g. lomas_centinela's pooled model: 34 MUR and 91 MCF across all 3
# training cities, versus main.yaml's own 1% min_class_fraction floor,
# see that model's own config.yaml). A prior can still name one of
# these: available_classes() offers it, and compute_feasible_prior/
# compute_overrides split it back out of its bucket's own ML-estimated
# buildings via an exact-quota sub-split (see _split_bucket_labels),
# rather than pretending the ensemble itself predicted it. This is the
# "confirmed with the user directly" plan named in that config.yaml,
# finally wired up on the risk_viewer side.
_SPLITTABLE_SUBCLASSES = {"MUR": "M", "MCF": "M", "MR": "M"}


def _real_ensemble_classes(buildings: list[dict[str, Any]]) -> set[str]:
    """The real classes this city's classifier ensemble can predict,
    read directly from the class_probabilities keys among this city's
    ML-estimated buildings -- not a fixed global list, since different
    cities' models were trained on different class sets (e.g.
    lomas_centinela's pooled model has 5, ADO/CR/M/MR/W -- MR included,
    since its config.yaml kept it out of the generic "M" bucket unlike
    MUR/MCF; the 3 pilot cities' per-city models have up to 4,
    ADO/CR/M/W)."""
    classes: set[str] = set()
    for b in buildings:
        if not b.get("structural_system_estimated"):
            continue
        ensemble = get_ensemble_info(b["id"], b["city"])
        if ensemble is not None:
            classes.update(ensemble.class_probabilities)
    return classes


def available_classes(buildings: list[dict[str, Any]]) -> list[str]:
    """The classes a prior can target for this city: _real_ensemble_classes
    PLUS any _SPLITTABLE_SUBCLASSES whose bucket is among those real
    classes (e.g. MUR/MCF once "M" is predictable), even though the
    ensemble never outputs that sub-class itself."""
    classes = _real_ensemble_classes(buildings)
    classes = classes | {sub for sub, bucket in _SPLITTABLE_SUBCLASSES.items() if bucket in classes}
    return sorted(classes)


def validate_proportions(proportions: dict[str, float], known_classes: list[str]) -> dict[str, float]:
    """Raises ValueError with a message meant to be shown to the caller
    directly (user-input validation boundary, see
    app/routers/typology_prior.py), not an internal assertion."""
    if not proportions:
        raise ValueError("proportions must not be empty.")

    unknown = sorted(set(proportions) - set(known_classes))
    if unknown:
        raise ValueError(
            f"Unknown or unsupported class(es) {unknown} for this city's classifier; "
            f"expected a subset of {known_classes}."
        )

    negative = {cls: value for cls, value in proportions.items() if value < 0}
    if negative:
        raise ValueError(f"Proportions must be non-negative, got {negative}.")

    total = sum(proportions.values())
    if abs(total - 1.0) > PROPORTION_SUM_TOLERANCE:
        raise ValueError(f"Proportions must sum to 1.0, got {total:.6f}.")

    return proportions


@dataclass(frozen=True)
class PriorFeasibility:
    """What compute_feasible_prior() worked out, surfaced to the caller
    (and the UI) so the math behind the prior is inspectable, not a
    black box."""

    ground_truth_counts: dict[str, int]
    n_ground_truth: int
    n_estimated: int
    n_total: int
    # The prior actually fed into each estimated building's geometric
    # pooling: the user's requested city-wide proportions, with ground
    # truth's own share already subtracted out and the remainder
    # renormalized over the estimated population alone -- in the
    # ensemble's OWN class space (_apply_prior_to_building can only ever
    # pool over classes the ensemble actually outputs), so a
    # _SPLITTABLE_SUBCLASSES target (e.g. "MUR") is folded into its
    # bucket ("M") here.
    prior_within_estimated: dict[str, float]
    # {bucket: {sub_class: remaining_count}} for every bucket that had
    # more than one requested class fold into it (e.g. "M": {"MUR": ...,
    # "MCF": ..., "M": ...}) -- how compute_overrides further splits
    # whichever buildings the pooling above actually put in that bucket.
    # A bucket absent here (or present with only one key) got no split
    # request, so its buildings keep the bucket's own label untouched.
    sub_shares_by_bucket: dict[str, dict[str, float]]


def compute_feasible_prior(buildings: list[dict[str, Any]], target_proportions: dict[str, float]) -> PriorFeasibility:
    """Nets the requested whole-population proportions against this
    city's real ground-truth counts, and derives what share of the
    ML-estimated population alone would need to land in each class to
    hit the requested total. Raises ValueError (message meant for the
    end user) when ground truth already exceeds what was requested for
    some class -- an infeasible request, not something to silently
    clamp or reinterpret.

    A ground-truth building nets against the exact class it was
    requested as when the caller named that class specifically (e.g.
    "MUR": 0.3 nets only real MUR-recorded buildings out of that 0.3),
    falling back to its ensemble bucket otherwise (e.g. a real MUR
    building still nets against a plain "M": 0.8 request, same as
    before _SPLITTABLE_SUBCLASSES existed) -- see _ensemble_bucket.

    A building whose structural_system_estimated is False AND
    structural_system_confirmed is also False (a city-wide fallback
    assumption with no real per-building signal at all, e.g.
    lomas_centinela's ~54 year-less buildings, see
    data_loader.py::_compute_structural_system_confirmed) is neither
    real ground truth to net out against nor something this prior can
    adjust -- excluded from n_total entirely, the same as "unlabeled".
    """
    requested_classes = set(target_proportions)
    ground_truth_counts: dict[str, int] = {}
    n_estimated = 0
    for b in buildings:
        cls = b["structural_system_class"]
        if cls == "unlabeled":
            continue
        if b["structural_system_estimated"]:
            n_estimated += 1
        elif b.get("structural_system_confirmed"):
            netting_key = cls if cls in requested_classes else _ensemble_bucket(cls)
            ground_truth_counts[netting_key] = ground_truth_counts.get(netting_key, 0) + 1

    n_ground_truth = sum(ground_truth_counts.values())
    n_total = n_ground_truth + n_estimated
    if n_total == 0:
        raise ValueError("No labeled or ML-estimated buildings in this city to apply a prior to.")
    if n_estimated == 0:
        raise ValueError(
            "Every building in this city already has a recorded structural system; there are no "
            "ML-estimated predictions for a prior to adjust."
        )

    remaining_by_class: dict[str, float] = {}
    infeasible: list[str] = []
    for cls, target_pct in target_proportions.items():
        target_count = target_pct * n_total
        gt_count = ground_truth_counts.get(cls, 0)
        remaining = target_count - gt_count
        if remaining < -1e-6:
            infeasible.append(
                f"'{cls}': {gt_count} of {n_total} buildings ({gt_count / n_total:.1%}) are already "
                f"confirmed '{cls}', more than the {target_pct:.1%} requested"
            )
        remaining_by_class[cls] = max(0.0, remaining)

    if infeasible:
        raise ValueError("Target proportion(s) impossible given confirmed data: " + "; ".join(infeasible) + ".")

    total_remaining = sum(remaining_by_class.values())
    if total_remaining <= 0:
        raise ValueError(
            "Ground truth alone already accounts for the entire requested mix; nothing is left to "
            "assign to ML-estimated buildings."
        )

    # A requested class only folds into its _SPLITTABLE_SUBCLASSES bucket
    # when the ensemble genuinely can't predict it directly -- lomas_
    # centinela's own model DOES output "MR" itself (its config.yaml
    # deliberately kept MR out of the generic "M" bucket, unlike MUR/
    # MCF), so an "MR" request there must stay its own top-level
    # ensemble slot, not get folded into (and diluted through) "M".
    real_classes = _real_ensemble_classes(buildings)
    bucket_remaining: dict[str, float] = {}
    sub_shares_by_bucket: dict[str, dict[str, float]] = {}
    for cls, remaining in remaining_by_class.items():
        bucket = cls if cls in real_classes else _SPLITTABLE_SUBCLASSES.get(cls, cls)
        bucket_remaining[bucket] = bucket_remaining.get(bucket, 0.0) + remaining
        sub_shares_by_bucket.setdefault(bucket, {})[cls] = remaining
    prior_within_estimated = {cls: value / total_remaining for cls, value in bucket_remaining.items()}

    return PriorFeasibility(
        ground_truth_counts=ground_truth_counts,
        n_ground_truth=n_ground_truth,
        n_estimated=n_estimated,
        n_total=n_total,
        prior_within_estimated=prior_within_estimated,
        sub_shares_by_bucket=sub_shares_by_bucket,
    )


@dataclass(frozen=True)
class BuildingPriorResult:
    structural_system_class: str
    # Normalized Shannon entropy (0..1) of this building's own posterior
    # distribution after prior injection -- reuses the exact same
    # entropy-to-[0,1] convention as typology_hypothesis.normalized_entropy
    # and the ensemble's own normalized_entropy, so it's comparable
    # against both.
    normalized_entropy: float
    class_probabilities: dict[str, float]


def _apply_prior_to_building(
    class_probabilities: dict[str, float], prior: dict[str, float], alpha: float
) -> BuildingPriorResult:
    """Geometric pooling: posterior_k ~ prior_k^alpha * mean_proba_k^(1-alpha),
    renormalised. alpha=0 ignores the prior (posterior == the ensemble's own,
    renormalized, probabilities); alpha=1 lets the prior alone decide.
    Mirrors ml_structural_system/prior_adjustment.py::apply_prior() exactly,
    see this module's own docstring for why it's reimplemented here rather
    than imported."""
    classes = sorted(class_probabilities)
    proba = np.array([class_probabilities[c] for c in classes], dtype=float)
    # class_probabilities isn't guaranteed to sum to 1.0 (threshold-adjusted
    # soft-ensemble shares, see EnsembleInfo's own docstring) -- renormalized
    # here so it's a real probability distribution before pooling.
    proba_sum = proba.sum()
    proba = proba / proba_sum if proba_sum > 0 else np.full(len(classes), 1.0 / len(classes))
    prior_vec = np.array([prior.get(c, 0.0) for c in classes], dtype=float)

    log_prior = np.log(np.clip(prior_vec, _PRIOR_FLOOR, None))
    log_model = np.log(np.clip(proba, _PRIOR_FLOOR, None))
    log_posterior = alpha * log_prior + (1.0 - alpha) * log_model
    log_posterior -= log_posterior.max()
    posterior = np.exp(log_posterior)
    posterior /= posterior.sum()

    argmax_idx = int(np.argmax(posterior))
    bits = -sum(float(p) * math.log2(p) for p in posterior if p > 0)
    max_bits = math.log2(len(classes)) if len(classes) > 1 else 1.0
    normalized_entropy = max(0.0, min(1.0, bits / max_bits)) if max_bits > 0 else 0.0

    return BuildingPriorResult(
        structural_system_class=classes[argmax_idx],
        normalized_entropy=normalized_entropy,
        class_probabilities=dict(zip(classes, posterior.tolist())),
    )


@dataclass(frozen=True)
class TypologyPrior:
    city: str
    # Sorted-tuple-of-pairs, not a dict: dicts aren't hashable, and this
    # needs to be usable as (part of) a cache key, mirroring
    # TypologyHypothesis.fingerprint()'s own reasoning.
    proportions: tuple[tuple[str, float], ...]
    alpha: float

    def proportions_dict(self) -> dict[str, float]:
        return dict(self.proportions)

    def fingerprint(self) -> str:
        """Stable short hash identifying this exact prior (city,
        proportions, alpha), used as part of the Scenario cache key
        (app/hazard/scenario.py) the same way
        TypologyHypothesis.fingerprint() already is, so a prior-adjusted
        risk result never gets served to, or cached over, a plain
        request or a request under a different prior."""
        payload = json.dumps(
            {"city": self.city, "proportions": sorted(self.proportions), "alpha": self.alpha}, sort_keys=True
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


_lock = threading.Lock()
_active: dict[str, TypologyPrior] = {}
# Cache of resolved per-building overrides, keyed by (city, fingerprint):
# {building_id: BuildingPriorResult}. compute_overrides() is called from
# data_loader.py on effectively every request that touches this city's
# buildings (map render, building detail, risk scenario), so memoizing
# by fingerprint (not recomputed unless the prior itself changes) keeps
# that cheap -- no GPR/model calls involved, just per-building geometric
# pooling, but still real work across a whole city's estimated buildings.
_overrides_cache: dict[tuple[str, str], dict[str, BuildingPriorResult]] = {}


def set_prior(
    city: str, proportions: dict[str, float], alpha: float, buildings: list[dict[str, Any]]
) -> tuple[TypologyPrior, PriorFeasibility]:
    """Validates, checks feasibility, and activates a prior for `city`,
    replacing any existing one. Raises ValueError (message meant for the
    end user) on invalid or infeasible input -- nothing is activated in
    that case."""
    if not 0.0 <= alpha <= 1.0:
        raise ValueError(f"alpha must be between 0.0 and 1.0, got {alpha:g}.")
    known = available_classes(buildings)
    validated = validate_proportions(proportions, known)
    feasibility = compute_feasible_prior(buildings, validated)

    prior = TypologyPrior(city=city, proportions=tuple(sorted(validated.items())), alpha=alpha)
    with _lock:
        _active[city] = prior
    return prior, feasibility


def get_prior(city: str) -> Optional[TypologyPrior]:
    with _lock:
        return _active.get(city)


def clear_prior(city: str) -> None:
    with _lock:
        _active.pop(city, None)


def _split_bucket_labels(
    buildings_by_bucket: dict[str, list[str]], sub_shares_by_bucket: dict[str, dict[str, float]], fingerprint: str
) -> dict[str, str]:
    """{building_id: sub_class} for every building that a requested
    _SPLITTABLE_SUBCLASSES split actually moves out of its bucket's own
    label (e.g. "M" -> "MUR"). Only ever touches buildings the pooling
    in compute_overrides already put in a bucket that has more than one
    class competing for it; a bucket with no such request is untouched,
    its buildings keep the plain bucket label _apply_prior_to_building
    gave them. Same exact-quota method as typology_hypothesis.py's own
    sample_classes (see exact_quota_labels), seeded off this prior's own
    fingerprint so the same prior always splits the same way."""
    seed = int(fingerprint, 16)
    result: dict[str, str] = {}
    for bucket, sub_shares in sub_shares_by_bucket.items():
        if len(sub_shares) <= 1:
            continue
        ids = buildings_by_bucket.get(bucket)
        if not ids:
            continue
        total = sum(sub_shares.values())
        if total <= 0:
            continue
        normalized = {cls: value / total for cls, value in sub_shares.items()}
        for building_id, sub_class in exact_quota_labels(ids, normalized, seed).items():
            if sub_class != bucket:
                result[building_id] = sub_class
    return result


def compute_overrides(buildings: list[dict[str, Any]], prior: TypologyPrior) -> dict[str, BuildingPriorResult]:
    """{building_id: BuildingPriorResult} for every ML-estimated building
    in `buildings` that has a real ensemble prediction to adjust.
    Buildings with a recorded structural_system, or with no ensemble
    prediction at all, are simply absent from the result (data_loader.py
    leaves those completely untouched)."""
    cache_key = (prior.city, prior.fingerprint())
    cached = _overrides_cache.get(cache_key)
    if cached is not None:
        return cached

    feasibility = compute_feasible_prior(buildings, prior.proportions_dict())
    result: dict[str, BuildingPriorResult] = {}
    buildings_by_bucket: dict[str, list[str]] = {}
    for b in buildings:
        if not b.get("structural_system_estimated"):
            continue
        ensemble = get_ensemble_info(b["id"], b["city"])
        if ensemble is None or not ensemble.class_probabilities:
            continue
        pooled = _apply_prior_to_building(ensemble.class_probabilities, feasibility.prior_within_estimated, prior.alpha)
        result[b["id"]] = pooled
        buildings_by_bucket.setdefault(pooled.structural_system_class, []).append(b["id"])

    # Sub-classes the ensemble can't predict directly (see
    # _SPLITTABLE_SUBCLASSES) never influenced the pooling above -- only
    # a building already argmax'd into their shared bucket is eligible
    # to become one of them. class_probabilities/normalized_entropy stay
    # the pooled (ensemble-space) result: this only overrides which
    # display class the bucket's own weight actually resolves to.
    splits = _split_bucket_labels(buildings_by_bucket, feasibility.sub_shares_by_bucket, prior.fingerprint())
    for building_id, sub_class in splits.items():
        pooled = result[building_id]
        result[building_id] = BuildingPriorResult(
            structural_system_class=sub_class,
            normalized_entropy=pooled.normalized_entropy,
            class_probabilities=pooled.class_probabilities,
        )

    _overrides_cache[cache_key] = result
    return result
