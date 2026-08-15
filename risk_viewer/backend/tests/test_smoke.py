from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    # Distinguishes "process is up" from "the build-time precompute step
    # actually produced results" (see app/precomputed.py); 0 in local dev
    # (scripts/precompute.py isn't run automatically), up to 12 once it has.
    assert body["precomputed_scenarios"] >= 0


def test_list_layers_includes_exposure_typology():
    response = client.get("/api/layers")
    assert response.status_code == 200
    layer_ids = [layer["id"] for layer in response.json()]
    assert "exposure_typology" in layer_ids


def test_layer_data_returns_feature_collection_with_unlabeled_bucket():
    response = client.get("/api/layers/exposure_typology/data")
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) == 5026
    classes = {f["properties"]["structural_system_class"] for f in body["features"]}
    assert "unlabeled" in classes


def test_layer_data_city_filter():
    response = client.get("/api/layers/exposure_typology/data", params={"city": "san_jose"})
    body = response.json()
    assert all(f["properties"]["city"] == "san_jose" for f in body["features"])
    assert len(body["features"]) > 0


def test_unknown_layer_404():
    response = client.get("/api/layers/does_not_exist/data")
    assert response.status_code == 404


def test_legend_has_expected_categorical_attributes():
    response = client.get("/api/layers/exposure_typology/legend")
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"structural_system_class", "code_quality", "roof_material"}
    assert body["structural_system_class"]["unlabeled"] == "#9e9d94"
