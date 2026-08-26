"""Loads each city's structural-typology classifier ensemble predictions
(LogisticRegression, RandomForest, XGBoost, see
`ml_structural_system/experiments/sjose_guatemala_sdomingo/risk_viewer_models/`)
and exposes, per building, what each model predicted and how much they
agree.

Generated once, offline, per city:
    mlss split/preprocess/train --config
        risk_viewer_models/<city>/config.yaml
    mlss infer --config risk_viewer_models/<city>/config.yaml
        --gpkg risk_viewer_models/<city>/infer_input.gpkg
        --output risk_viewer_models/<city>/predictions.csv

Not run automatically by this backend. If a city's predictions.csv is
missing, that city's buildings simply report no ensemble info (see
`get_ensemble_info`), the same fallback-friendly pattern as the rest of
this app's optional layers.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from app.config import ENSEMBLE_CITIES, HELD_OUT_METRICS_PATH, RISK_VIEWER_MODELS_DIR

MODEL_NAMES = ["LogisticRegression", "RandomForest", "XGBoost"]


@dataclass(frozen=True)
class EnsembleInfo:
    model_predictions: dict[str, str]
    majority_vote: str
    ensemble_pred: str
    agreement_ratio: float
    normalized_entropy: float
    is_contested: bool
    candidate_classes: list[str]
    # Class -> soft-ensemble probability (assess.py's mean_proba, one
    # proba_<class> column per class), empty when predictions.csv predates
    # this field (see _build_sample_dataframe's own docstring for why
    # these don't necessarily sum to 1.0: each model's own probabilities
    # are threshold-adjusted before being averaged, not raw predict_proba).
    class_probabilities: dict[str, float]


def _label_mapping(city: str) -> dict[str, str]:
    """int-as-string -> class name, e.g. {"0": "ADO", "1": "CR", "2": "M"}."""
    path = RISK_VIEWER_MODELS_DIR / city / "preprocessed_splits" / "preprocessing.json"
    if not path.exists():
        return {}
    with open(path) as f:
        mapping = json.load(f)["label_mapping"]
    return {str(index): name for name, index in mapping.items()}


def _load_city(city: str) -> dict[str, EnsembleInfo]:
    predictions_path = RISK_VIEWER_MODELS_DIR / city / "predictions.csv"
    if not predictions_path.exists():
        return {}

    decode = _label_mapping(city)
    if not decode:
        return {}

    result: dict[str, EnsembleInfo] = {}
    with open(predictions_path) as f:
        reader = csv.DictReader(f)
        # proba_<ClassName> columns already carry the real class name
        # (see assess.py::_proba_column_names), unlike pred_<model>/
        # majority_vote/ensemble_pred, which are encoded ints needing
        # `decode`. Detected from the header rather than hardcoded, since
        # the class set differs per city.
        proba_columns = [c for c in (reader.fieldnames or []) if c.startswith("proba_")]
        for row in reader:
            model_predictions = {
                model: decode.get(row[f"pred_{model}"], row[f"pred_{model}"])
                for model in MODEL_NAMES
                if f"pred_{model}" in row and row[f"pred_{model}"] != ""
            }
            if not model_predictions:
                continue
            candidate_classes = sorted(set(model_predictions.values()))
            class_probabilities = {
                column.removeprefix("proba_"): float(row[column]) for column in proba_columns
            }
            result[row["id"]] = EnsembleInfo(
                model_predictions=model_predictions,
                majority_vote=decode.get(row["majority_vote"], row["majority_vote"]),
                ensemble_pred=decode.get(row["ensemble_pred"], row["ensemble_pred"]),
                agreement_ratio=float(row["agreement_ratio"]),
                normalized_entropy=float(row["normalized_entropy"]),
                is_contested=row["is_contested"].strip().lower() == "true",
                candidate_classes=candidate_classes,
                class_probabilities=class_probabilities,
            )
    return result


@lru_cache(maxsize=1)
def _load_all() -> dict[str, dict[str, EnsembleInfo]]:
    return {city: _load_city(city) for city in ENSEMBLE_CITIES}


def get_ensemble_info(building_id: str, city: str) -> Optional[EnsembleInfo]:
    return _load_all().get(city, {}).get(building_id)


@dataclass(frozen=True)
class BootstrapCI:
    lower: float
    upper: float
    confidence: float


@dataclass(frozen=True)
class EnsembleQualityMetrics:
    """Real quality metrics for this city's ensemble, computed on a
    genuinely held-out subset. See risk_viewer_held_out_metrics.py
    (ml_structural_system) for the full methodology and why a naive
    computation over all of predictions.csv would be invalid (most of it
    turned out to overlap the model's own training split)."""

    n_predictions_csv: int
    n_held_out_test: int
    classes: list[str]
    has_ground_truth: bool
    ensemble_f1_macro: Optional[float]
    ensemble_f1_macro_ci: Optional[BootstrapCI]
    inter_model_fleiss_kappa: float
    inter_model_fleiss_kappa_ci: BootstrapCI


def _ci_from_json(raw: Optional[dict]) -> Optional[BootstrapCI]:
    if raw is None:
        return None
    return BootstrapCI(lower=raw["lower"], upper=raw["upper"], confidence=raw["confidence"])


@lru_cache(maxsize=1)
def _load_held_out_metrics() -> dict[str, EnsembleQualityMetrics]:
    if not HELD_OUT_METRICS_PATH.exists():
        return {}
    with open(HELD_OUT_METRICS_PATH) as f:
        raw = json.load(f)
    result: dict[str, EnsembleQualityMetrics] = {}
    for city, r in raw.items():
        kappa_ci = _ci_from_json(r["inter_model_fleiss_kappa_ci"])
        assert kappa_ci is not None  # always present, unlike the F1 CI (which needs ground truth)
        result[city] = EnsembleQualityMetrics(
            n_predictions_csv=r["n_predictions_csv"],
            n_held_out_test=r["n_held_out_test"],
            classes=r["classes"],
            has_ground_truth=r["has_ground_truth"],
            ensemble_f1_macro=r["ensemble_f1_macro"],
            ensemble_f1_macro_ci=_ci_from_json(r["ensemble_f1_macro_ci"]),
            inter_model_fleiss_kappa=r["inter_model_fleiss_kappa"],
            inter_model_fleiss_kappa_ci=kappa_ci,
        )
    return result


def get_ensemble_quality_metrics(city: str) -> Optional[EnsembleQualityMetrics]:
    return _load_held_out_metrics().get(city)
