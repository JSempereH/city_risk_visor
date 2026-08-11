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
    # guatemala_761 has no recorded structural_system and no ensemble
    # prediction either (most commonly because it's also missing the
    # other features the classifier needs), so it should stay honestly
    # unlabeled rather than being force-fit to something.
    building = data_loader.get_building("guatemala_761")
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
