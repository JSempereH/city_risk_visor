from app import data_loader


def test_unlabeled_building_gets_ensemble_estimate_when_available():
    # guatemala_752 has no recorded structural_system, but the typology
    # classifier ensemble has a real prediction for it (see
    # app/data_loader.py::_fill_unlabeled_from_ensemble).
    building = data_loader.get_building("guatemala_752")
    assert building is not None
    assert building["structural_system_class"] == "M"
    assert building["structural_system_estimated"] is True


def test_unlabeled_building_without_ensemble_prediction_stays_unlabeled():
    # guatemala_12998 has no recorded structural_system and no ensemble
    # prediction either, so it should stay honestly unlabeled rather than
    # being force-fit to something. (guatemala_761, then guatemala_12787,
    # were the previous fixtures for this case; both later gained a real
    # roof_material/height estimate and an ensemble prediction --
    # exactly the improvement each backfill was for, so they stopped
    # being valid "stays unlabeled" examples. Only 3 guatemala buildings
    # are left unlabeled as of the roof_material reference-based backfill,
    # see scripts/exposure/apply_guatemala_roof_material.py.)
    building = data_loader.get_building("guatemala_12998")
    assert building is not None
    assert building["structural_system_class"] == "unlabeled"
    assert building["structural_system_estimated"] is False


def test_recorded_structural_system_is_never_overridden_by_ensemble():
    # guatemala_7 has a real recorded structural_system ("CR"); even
    # though it also has ensemble info (used elsewhere for typology_beta),
    # the recorded value must win, not get silently swapped for a model
    # guess.
    building = data_loader.get_building("guatemala_7")
    assert building is not None
    assert building["structural_system_class"] == "CR"
    assert building["structural_system_estimated"] is False


def test_lomas_centinela_ensemble_covered_building_gets_estimate_not_fallback():
    # lomas_centinela_0 is covered by the cross-city pooled ensemble (see
    # scripts/exposure/assign_lomas_centinela_typology.py), so it should
    # get that model's own per-building estimate rather than the
    # neighborhood-wide MUR fallback used for the ~54 buildings the
    # ensemble's own inference step had to drop (missing `year`).
    building = data_loader.get_building("lomas_centinela_0")
    assert building is not None
    assert building["structural_system_estimated"] is True
    assert building["structural_system_class"] != "unlabeled"


def test_recorded_structural_system_is_confirmed():
    # guatemala_7 has a real recorded structural_system AND the ensemble
    # also has a prediction for it (used elsewhere for typology_beta) --
    # structural_system_confirmed should be True, the "real record" case.
    building = data_loader.get_building("guatemala_7")
    assert building is not None
    assert building["structural_system_confirmed"] is True


def test_lomas_centinela_generic_fallback_is_not_confirmed():
    # lomas_centinela_106 is one of the ~54 buildings the ensemble's own
    # inference step dropped (missing `year`), so it falls back to the
    # neighborhood-wide MUR assumption (see
    # scripts/exposure/assign_lomas_centinela_typology.py).
    # structural_system_estimated is False for it (it's not the
    # ensemble's own guess), but it must NOT read as structural_system_
    # confirmed either -- it's not a real per-building record, just a
    # generic assumption with the same CityProfile.typology_beta_generic
    # uncertainty as a whole unconfirmed city (app/risk/service.py).
    building = data_loader.get_building("lomas_centinela_106")
    assert building is not None
    assert building["structural_system_class"] == "MUR"
    assert building["structural_system_estimated"] is False
    assert building["structural_system_confirmed"] is False


def test_masonry_subclasses_stay_distinct_not_collapsed_into_m():
    # MUR/MCF/MR are GEM Building Taxonomy Level-1 material codes kept
    # distinct (see STRUCTURAL_SYSTEM_REPLACEMENTS's own docstring) so
    # they route to their own GEM fragility curves instead of the
    # generic "M" class's ML capacity-model tier.
    for building_id, expected_class in [
        ("guatemala_185", "MUR"),
        ("guatemala_184", "MCF"),
        ("guatemala_108", "MR"),
    ]:
        building = data_loader.get_building(building_id)
        assert building is not None
        assert building["structural_system_class"] == expected_class
        assert building["structural_system_estimated"] is False
