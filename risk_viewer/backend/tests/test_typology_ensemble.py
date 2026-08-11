from fastapi.testclient import TestClient

from app.main import app
from app.typology_ensemble import get_ensemble_info

client = TestClient(app)

CONTESTED_BUILDING_ID = "guatemala_2814"  # LR=M, RF=ADO, XGB=CR -- 3-way split
AGREED_BUILDING_ID = "guatemala_7"  # all 3 models say CR


def test_get_ensemble_info_contested():
    info = get_ensemble_info(CONTESTED_BUILDING_ID, "guatemala")
    assert info is not None
    assert info.is_contested is True
    assert len(info.candidate_classes) == 3
    assert set(info.model_predictions.keys()) == {"LogisticRegression", "RandomForest", "XGBoost"}


def test_get_ensemble_info_agreed():
    info = get_ensemble_info(AGREED_BUILDING_ID, "guatemala")
    assert info is not None
    assert info.is_contested is False
    assert info.agreement_ratio == 1.0
    assert info.candidate_classes == ["CR"]


def test_get_ensemble_info_missing_returns_none():
    assert get_ensemble_info("does_not_exist", "guatemala") is None
    assert get_ensemble_info(AGREED_BUILDING_ID, "nowhere") is None


def test_vulnerability_endpoint_includes_typology_ensemble():
    response = client.get(f"/api/buildings/{CONTESTED_BUILDING_ID}/vulnerability")
    assert response.status_code == 200
    body = response.json()
    ensemble = body["typology_ensemble"]
    assert ensemble is not None
    assert ensemble["is_contested"] is True
    assert len(ensemble["candidate_classes"]) == 3


def test_vulnerability_endpoint_ensemble_none_when_unavailable():
    response = client.get("/api/buildings/does_not_exist_xyz/vulnerability")
    assert response.status_code == 404
