"""Resolves where the backend reads its demo exposure dataset from.

Kept as a single settings module so swapping the dataset (e.g. to a
per-city file, or a whole-city-scale export) is a one-line change or an
env var override, not a code change scattered across the app.

All data referenced here is vendored into app/data/ so this backend is
self-contained and buildable/deployable from a clone of risk_viewer/
alone, without needing the sibling ml_structural_system/ or
FragilityCurves/ repos present on disk (unlike an earlier version of this
file, which read them directly via a parents[3] path traversal). If any
of that source data is retrained/updated, re-copy the resulting artifact
into the paths below and redeploy; see README.md.
"""

from __future__ import annotations

import os
from pathlib import Path

from app.cities import CITIES

DATA_DIR = Path(__file__).resolve().parent / "data"

# Sourced from ml_structural_system/experiments/sjose_guatemala_sdomingo/
# data/prepared/all_cities_combined.gpkg.
DEFAULT_DATA_PATH = DATA_DIR / "exposure" / "all_cities_combined.gpkg"
DATA_PATH = Path(os.environ.get("RISK_VIEWER_DATA_PATH", DEFAULT_DATA_PATH))

# Trained via `FragilityCurves/train_gpr.py --exp_name risk_viewer_v1
# --n_components 10 --conservative_bias 0.0` from FragilityCurves' own
# 165-curve masonry-aggregate dataset. See app/vulnerability/ for how this
# is used and what it does and doesn't cover. Sourced from
# FragilityCurves/runs/gpr/risk_viewer_v1/gpr_model.pkl.
DEFAULT_CAPACITY_MODEL_PATH = DATA_DIR / "vulnerability" / "gpr_model.pkl"
CAPACITY_MODEL_PATH = Path(
    os.environ.get("RISK_VIEWER_CAPACITY_MODEL_PATH", DEFAULT_CAPACITY_MODEL_PATH)
)

FRONTEND_ORIGIN = os.environ.get("RISK_VIEWER_FRONTEND_ORIGIN", "http://localhost:5183")

# Per-city structural-typology classifier ensembles (LogisticRegression,
# RandomForest, XGBoost), trained via:
#   mlss split/preprocess/train --config
#     ml_structural_system/experiments/sjose_guatemala_sdomingo/
#     risk_viewer_models/<city>/config.yaml
# then `mlss infer` against that city's subset of all_cities_combined.gpkg,
# writing predictions.csv + reusing preprocessed_splits/preprocessing.json's
# label_mapping for decoding. See app/typology_ensemble/. Sourced from
# ml_structural_system/experiments/sjose_guatemala_sdomingo/
# risk_viewer_models/<city>/{predictions.csv,preprocessed_splits/
# preprocessing.json} (that directory also holds ~210MB of training
# scaffolding never read at runtime, only those two files per city are
# vendored here).
DEFAULT_RISK_VIEWER_MODELS_DIR = DATA_DIR / "typology_ensemble"
RISK_VIEWER_MODELS_DIR = Path(
    os.environ.get("RISK_VIEWER_MODELS_DIR", DEFAULT_RISK_VIEWER_MODELS_DIR)
)
# A city is "ensembled" once its predictions.csv actually exists, not
# just because it has an entry in app.cities.CITIES (same
# derive-from-file-existence pattern as psha.PSHA_SUPPORTED_CITIES).
ENSEMBLE_CITIES = [city for city in CITIES if (RISK_VIEWER_MODELS_DIR / city / "predictions.csv").exists()]

# Held-out-test-only F1/Fleiss' Kappa per city's actual deployed ensemble
# above (not the unrelated pooled-calibration figure the cross-city
# generalisation study under ml_structural_system/experiments/
# sjose_guatemala_sdomingo/ produces). See
# ml_structural_system/experiments/sjose_guatemala_sdomingo/
# risk_viewer_held_out_metrics.py for how this was computed and why it
# restricts to a small held-out subset of predictions.csv, and
# app/typology_ensemble/loader.py for how it's read.
HELD_OUT_METRICS_PATH = RISK_VIEWER_MODELS_DIR / "held_out_metrics.json"

# SHAP/built-in feature importances per city, consensus-ranked across the
# 3-model ensemble. See ml_structural_system/experiments/
# sjose_guatemala_sdomingo/risk_viewer_feature_importance.py for how this
# was computed (against each city's already-trained models, no
# retraining) and app/typology_ensemble/loader.py for how it's read.
FEATURE_IMPORTANCE_PATH = RISK_VIEWER_MODELS_DIR / "feature_importance.json"
