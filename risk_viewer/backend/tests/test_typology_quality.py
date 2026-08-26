from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_quality_metrics_all_three_cities():
    for city in ("guatemala", "san_jose", "santo_domingo"):
        response = client.get(f"/api/typology_ensemble/{city}/quality")
        assert response.status_code == 200
        body = response.json()
        assert body["n_held_out_test"] > 0
        assert body["n_held_out_test"] < body["n_predictions_csv"]
        # Kappa is always computable (doesn't need ground truth), F1 only
        # for cities whose evaluation zone has real labels.
        assert body["inter_model_fleiss_kappa_ci"] is not None
        if body["has_ground_truth"]:
            assert 0.0 <= body["ensemble_f1_macro"] <= 1.0
            ci = body["ensemble_f1_macro_ci"]
            assert ci["lower"] <= body["ensemble_f1_macro"] <= ci["upper"]
        else:
            assert body["ensemble_f1_macro"] is None


def test_quality_metrics_all_three_cities_have_ground_truth():
    # All 3 evaluation zones have real structural_system labels (verified
    # against the raw source gpkg). Santo Domingo's predictions.csv
    # initially had none due to a since-fixed bug in ml_structural_system's
    # infer.py: a single batch label_encoder.transform() call raised on the
    # whole column the moment it hit one label value (a "W", present in
    # this zone but absent from this model's own training split) the
    # fitted encoder never saw, discarding all 785 otherwise-valid labels
    # instead of masking just the 2 unencodable rows.
    for city in ("guatemala", "san_jose", "santo_domingo"):
        response = client.get(f"/api/typology_ensemble/{city}/quality")
        body = response.json()
        assert body["has_ground_truth"] is True
        assert body["ensemble_f1_macro"] is not None


def test_quality_metrics_unknown_city_404():
    response = client.get("/api/typology_ensemble/nowhere/quality")
    assert response.status_code == 404


def test_quality_metrics_lomas_centinela_404():
    # A real city with a real ensemble, but no held-out ground truth to
    # score it against (its pooled model was trained on 3 OTHER cities,
    # see scripts/exposure/assign_lomas_centinela_typology.py) -- 404
    # here is what drives typology_ensemble's own locally_validated=False
    # for this city, not an error.
    response = client.get("/api/typology_ensemble/lomas_centinela/quality")
    assert response.status_code == 404
