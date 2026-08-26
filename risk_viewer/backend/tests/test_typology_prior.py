import pytest
from fastapi.testclient import TestClient

from app import typology_prior
from app.main import app

client = TestClient(app)

TEST_CITY = "guatemala"


@pytest.fixture(autouse=True)
def _clear_prior_after_each_test():
    yield
    typology_prior.clear_prior(TEST_CITY)


def test_compute_feasible_prior_nets_out_ground_truth():
    # city="nowhere" on every fixture: _real_ensemble_classes needs a
    # "city" key to look each estimated building up (get_ensemble_info),
    # and a made-up id under a made-up city always resolves to "no
    # ensemble info" -- exactly what these synthetic fixtures want, same
    # convention as test_typology_ensemble.py's own "nowhere" city.
    buildings = [
        {"id": "a", "city": "nowhere", "structural_system_class": "M", "structural_system_estimated": False, "structural_system_confirmed": True},
        {"id": "b", "city": "nowhere", "structural_system_class": "M", "structural_system_estimated": False, "structural_system_confirmed": True},
        {"id": "c", "city": "nowhere", "structural_system_class": "CR", "structural_system_estimated": False, "structural_system_confirmed": True},
        {"id": "d", "city": "nowhere", "structural_system_class": "M", "structural_system_estimated": True},
        {"id": "e", "city": "nowhere", "structural_system_class": "CR", "structural_system_estimated": True},
    ]
    # 5 buildings total, target 80% M (=4 buildings). Ground truth already
    # has 2 M -- the 2 estimated buildings must supply the other 2, i.e.
    # 100% of the estimated pool should target M.
    feasibility = typology_prior.compute_feasible_prior(buildings, {"M": 0.8, "CR": 0.2})
    assert feasibility.n_ground_truth == 3
    assert feasibility.n_estimated == 2
    assert feasibility.n_total == 5
    assert feasibility.prior_within_estimated["M"] == pytest.approx(1.0)
    assert feasibility.prior_within_estimated["CR"] == pytest.approx(0.0)


def test_compute_feasible_prior_folds_masonry_subtypes_into_m():
    # MUR/MCF/MR are real recorded (ground-truth) classes the ensemble
    # itself was never trained to distinguish -- must count toward "M"
    # when netting ground truth out, not be ignored or treated as unknown.
    buildings = [
        {"id": "a", "city": "nowhere", "structural_system_class": "MUR", "structural_system_estimated": False, "structural_system_confirmed": True},
        {"id": "b", "city": "nowhere", "structural_system_class": "MCF", "structural_system_estimated": False, "structural_system_confirmed": True},
        {"id": "c", "city": "nowhere", "structural_system_class": "M", "structural_system_estimated": True},
    ]
    # Not requested as their own classes here (target is just "M"), so
    # they net against the bucket, exactly as before _SPLITTABLE_SUBCLASSES
    # existed -- see the sibling test below for the opposite case.
    feasibility = typology_prior.compute_feasible_prior(buildings, {"M": 1.0})
    assert feasibility.ground_truth_counts == {"M": 2}


def test_compute_feasible_prior_nets_masonry_subtypes_against_their_own_request():
    # Once MUR is requested as its own class (not just folded into "M"),
    # a real MUR-recorded building nets against that specific request
    # instead of the generic "M" bucket.
    buildings = [
        {"id": "a", "city": "nowhere", "structural_system_class": "MUR", "structural_system_estimated": False, "structural_system_confirmed": True},
        {"id": "b", "city": "nowhere", "structural_system_class": "M", "structural_system_estimated": False, "structural_system_confirmed": True},
        {"id": "c", "city": "nowhere", "structural_system_class": "M", "structural_system_estimated": True},
    ]
    feasibility = typology_prior.compute_feasible_prior(buildings, {"MUR": 0.5, "M": 0.5})
    assert feasibility.ground_truth_counts == {"MUR": 1, "M": 1}
    # 3 total * 0.5 target = 1.5 wanted for each of MUR/M, minus 1
    # ground-truth building already confirmed as each -> 0.5 remaining
    # for MUR, 0.5 remaining for M. Both fold into the "M" ensemble slot
    # (1.0 total, the only slot with any demand left), which the one
    # estimated building supplies entirely -- the MUR/M split among
    # whichever buildings actually land in that slot is what
    # sub_shares_by_bucket carries forward for compute_overrides.
    assert feasibility.prior_within_estimated == {"M": pytest.approx(1.0)}
    assert feasibility.sub_shares_by_bucket["M"] == {
        "MUR": pytest.approx(0.5),
        "M": pytest.approx(0.5),
    }


def test_compute_feasible_prior_infeasible_when_ground_truth_exceeds_target():
    buildings = [
        {"id": "a", "structural_system_class": "ADO", "structural_system_estimated": False, "structural_system_confirmed": True},
        {"id": "b", "structural_system_class": "ADO", "structural_system_estimated": False, "structural_system_confirmed": True},
        {"id": "c", "structural_system_class": "M", "structural_system_estimated": True},
    ]
    # 2 of 3 buildings (66.7%) are already confirmed ADO; requesting 5% is impossible.
    with pytest.raises(ValueError, match="impossible given confirmed data"):
        typology_prior.compute_feasible_prior(buildings, {"ADO": 0.05, "M": 0.95})


def test_compute_feasible_prior_raises_without_any_estimated_buildings():
    buildings = [
        {"id": "a", "structural_system_class": "M", "structural_system_estimated": False, "structural_system_confirmed": True}
    ]
    with pytest.raises(ValueError, match="no ML-estimated predictions"):
        typology_prior.compute_feasible_prior(buildings, {"M": 1.0})


def test_compute_feasible_prior_excludes_unconfirmed_generic_fallback():
    # structural_system_estimated False AND structural_system_confirmed
    # False (lomas_centinela's ~54 year-less buildings' own state, see
    # data_loader.py::_compute_structural_system_confirmed) is neither
    # real ground truth nor ML-adjustable -- excluded from n_total
    # entirely, same as "unlabeled".
    buildings = [
        {"id": "a", "city": "nowhere", "structural_system_class": "MUR", "structural_system_estimated": False, "structural_system_confirmed": False},
        {"id": "b", "city": "nowhere", "structural_system_class": "M", "structural_system_estimated": True},
    ]
    feasibility = typology_prior.compute_feasible_prior(buildings, {"M": 1.0})
    assert feasibility.ground_truth_counts == {}
    assert feasibility.n_ground_truth == 0
    assert feasibility.n_total == 1


def test_apply_prior_to_building_alpha_zero_keeps_model_evidence():
    result = typology_prior._apply_prior_to_building({"M": 0.9, "CR": 0.1}, {"M": 0.1, "CR": 0.9}, alpha=0.0)
    assert result.structural_system_class == "M"


def test_apply_prior_to_building_alpha_one_lets_prior_decide():
    result = typology_prior._apply_prior_to_building({"M": 0.9, "CR": 0.1}, {"M": 0.1, "CR": 0.9}, alpha=1.0)
    assert result.structural_system_class == "CR"


def test_apply_prior_to_building_posterior_sums_to_one():
    result = typology_prior._apply_prior_to_building({"M": 0.6, "CR": 0.3, "ADO": 0.2}, {"M": 0.5, "CR": 0.3, "ADO": 0.2}, alpha=0.5)
    assert sum(result.class_probabilities.values()) == pytest.approx(1.0)
    assert 0.0 <= result.normalized_entropy <= 1.0


def test_available_classes_locally_validated_flag():
    guatemala = client.get(f"/api/cities/{TEST_CITY}/typology_prior/available_classes").json()
    assert guatemala["locally_validated"] is True

    # lomas_centinela's ensemble is pooled from 3 OTHER cities with no
    # held-out ground truth of its own (see
    # scripts/exposure/assign_lomas_centinela_typology.py) -- the prior
    # form still works (it has real estimated buildings to adjust), but
    # the settings UI uses this flag to caveat it.
    lomas = client.get("/api/cities/lomas_centinela/typology_prior/available_classes").json()
    assert lomas["classes"]
    assert lomas["locally_validated"] is False


def test_lomas_centinela_available_classes_include_mur_via_bucket_split():
    # The pooled model was never trained to tell MUR/MCF apart from
    # generic "M" (too few labeled examples, see that model's own
    # config.yaml) -- MUR/MCF must still be offered, reachable by
    # splitting the "M" bucket's own ML-estimated buildings, not by the
    # ensemble predicting them directly.
    classes = client.get("/api/cities/lomas_centinela/typology_prior/available_classes").json()["classes"]
    assert set(classes) == {"ADO", "CR", "M", "MCF", "MR", "MUR", "W"}


def test_lomas_centinela_mr_stays_its_own_ensemble_slot_not_folded_into_m():
    # lomas_centinela's pooled model DOES predict "MR" directly (its
    # config.yaml deliberately kept it out of the generic "M" bucket,
    # unlike MUR/MCF) -- a real regression here: _SPLITTABLE_SUBCLASSES
    # unconditionally folding MR into "M" would throw away the model's
    # own per-building MR evidence for every building, not just split
    # M-bucket buildings after the fact.
    from app import data_loader

    buildings = data_loader.get_buildings_by_city("lomas_centinela")
    proportions = {"ADO": 0.1, "CR": 0.1, "M": 0.1, "MCF": 0.1, "MR": 0.1, "MUR": 0.4, "W": 0.1}
    feasibility = typology_prior.compute_feasible_prior(buildings, proportions)
    assert "MR" in feasibility.prior_within_estimated
    assert feasibility.prior_within_estimated["MR"] == pytest.approx(0.1)
    # M's own ensemble slot only absorbs M/MCF/MUR (0.1+0.1+0.4=0.6), MR
    # is not part of that bucket.
    assert feasibility.prior_within_estimated["M"] == pytest.approx(0.6)
    assert set(feasibility.sub_shares_by_bucket["MR"]) == {"MR"}


def test_lomas_centinela_prior_can_target_mur_via_bucket_split():
    city = "lomas_centinela"
    try:
        response = client.post(
            f"/api/cities/{city}/typology_prior",
            json={
                "proportions": {"ADO": 0.1, "CR": 0.1, "MR": 0.1, "W": 0.1, "M": 0.1, "MUR": 0.4, "MCF": 0.1},
                "alpha": 0.9,
            },
        )
        assert response.status_code == 200

        layer = client.get(f"/api/layers/exposure_typology/data?city={city}").json()
        classes_seen = {f["properties"]["structural_system_class"] for f in layer["features"]}
        # The point of the whole mechanism: MUR shows up on real
        # buildings even though no ensemble prediction ever names it.
        assert "MUR" in classes_seen
    finally:
        typology_prior.clear_prior(city)


def test_set_prior_via_api_rejects_infeasible_target():
    response = client.post(
        f"/api/cities/{TEST_CITY}/typology_prior",
        json={"proportions": {"ADO": 0.05, "CR": 0.15, "M": 0.80}, "alpha": 0.7},
    )
    assert response.status_code == 400
    assert "impossible" in response.json()["detail"]


def test_set_prior_via_api_only_changes_estimated_buildings_class():
    from app import data_loader

    buildings_before = {b["id"]: b for b in data_loader.get_buildings_by_city(TEST_CITY)}
    ground_truth_ids = [b["id"] for b in buildings_before.values() if not b["structural_system_estimated"] and b["structural_system_class"] != "unlabeled"]
    assert ground_truth_ids

    response = client.post(
        f"/api/cities/{TEST_CITY}/typology_prior",
        json={"proportions": {"ADO": 0.30, "CR": 0.15, "M": 0.55}, "alpha": 0.9},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["feasibility"]["n_total"] == len(
        [b for b in buildings_before.values() if b["structural_system_class"] != "unlabeled"]
    )

    buildings_after = {b["id"]: b for b in data_loader.get_buildings_by_city(TEST_CITY)}
    for building_id in ground_truth_ids:
        assert buildings_after[building_id]["structural_system_class"] == buildings_before[building_id]["structural_system_class"]


def test_typology_prior_reflected_in_exposure_layer_and_building_endpoint():
    client.post(
        f"/api/cities/{TEST_CITY}/typology_prior",
        json={"proportions": {"ADO": 0.30, "CR": 0.15, "M": 0.55}, "alpha": 0.9},
    )

    layer = client.get(f"/api/layers/exposure_typology/data?city={TEST_CITY}").json()
    ids_in_layer = {f["properties"]["id"] for f in layer["features"]}
    assert "guatemala_752" in ids_in_layer

    body = client.get("/api/buildings/guatemala_752/vulnerability").json()
    assert body["typology_prior"] is not None
    assert abs(sum(body["typology_prior"]["posterior_class_probabilities"].values()) - 1.0) < 1e-6


def test_delete_typology_prior_clears_it():
    client.post(f"/api/cities/{TEST_CITY}/typology_prior", json={"proportions": {"ADO": 0.30, "CR": 0.15, "M": 0.55}})
    assert client.get(f"/api/cities/{TEST_CITY}/typology_prior").json() is not None

    response = client.delete(f"/api/cities/{TEST_CITY}/typology_prior")
    assert response.status_code == 200
    assert client.get(f"/api/cities/{TEST_CITY}/typology_prior").json() is None

    body = client.get("/api/buildings/guatemala_752/vulnerability").json()
    assert body["typology_prior"] is None
