"""City-level structural-typology ensemble quality: real F1/Fleiss' Kappa
on a genuinely held-out test subset, for the "how much should I trust
this classifier" question the per-building agreement display (see
app/routers/vulnerability.py) doesn't answer on its own. See
app/typology_ensemble/loader.py's EnsembleQualityMetrics docstring and
ml_structural_system/experiments/sjose_guatemala_sdomingo/
risk_viewer_held_out_metrics.py for the full methodology."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.typology_ensemble import get_ensemble_quality_metrics

router = APIRouter(prefix="/api/typology_ensemble", tags=["typology_ensemble"])


def _ci_json(ci) -> dict | None:
    if ci is None:
        return None
    return {"lower": ci.lower, "upper": ci.upper, "confidence": ci.confidence}


@router.get("/{city}/quality")
def ensemble_quality(city: str) -> dict:
    metrics = get_ensemble_quality_metrics(city)
    if metrics is None:
        raise HTTPException(status_code=404, detail=f"No held-out quality metrics available for city: {city}.")
    return {
        "city": city,
        "n_predictions_csv": metrics.n_predictions_csv,
        "n_held_out_test": metrics.n_held_out_test,
        "classes": metrics.classes,
        "has_ground_truth": metrics.has_ground_truth,
        "ensemble_f1_macro": metrics.ensemble_f1_macro,
        "ensemble_f1_macro_ci": _ci_json(metrics.ensemble_f1_macro_ci),
        "inter_model_fleiss_kappa": metrics.inter_model_fleiss_kappa,
        "inter_model_fleiss_kappa_ci": _ci_json(metrics.inter_model_fleiss_kappa_ci),
    }
