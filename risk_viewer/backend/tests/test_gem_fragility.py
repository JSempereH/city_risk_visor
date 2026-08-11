from app.vulnerability.gem_fragility import compute_gem_fragility, supported


def test_supported_classes():
    assert supported("CR") is True
    assert supported("W") is True
    assert supported("ADO") is True
    assert supported("M") is False
    assert supported("unlabeled") is False


def test_height_class_clamps_to_available_range():
    # CR only has GEM height classes 1-10; a 20-storey building should
    # clamp to the tallest available class rather than raising.
    curves, reference, _period_s = compute_gem_fragility("CR", "low_code", 20)
    assert "H10" in reference["height"]
    assert len(curves) == 4


def test_taller_building_is_less_fragile_at_same_ductility():
    curves_low, _, _ = compute_gem_fragility("CR", "low_code", 1)
    curves_high, _, _ = compute_gem_fragility("CR", "low_code", 8)
    low_complete = next(fc for fc in curves_low if fc.damage_state == "complete")
    high_complete = next(fc for fc in curves_high if fc.damage_state == "complete")
    assert high_complete.median_sd_mm > low_complete.median_sd_mm


def test_higher_ductility_increases_capacity():
    curves_dul, _, _ = compute_gem_fragility("CR", "pre_code", 3)
    curves_duh, _, _ = compute_gem_fragility("CR", "high_code", 3)
    dul_complete = next(fc for fc in curves_dul if fc.damage_state == "complete")
    duh_complete = next(fc for fc in curves_duh if fc.damage_state == "complete")
    assert duh_complete.median_sd_mm > dul_complete.median_sd_mm


def test_ado_ignores_code_quality():
    curves_a, _, _ = compute_gem_fragility("ADO", "pre_code", 1)
    curves_b, _, _ = compute_gem_fragility("ADO", "high_code", 1)
    medians_a = [fc.median_sd_mm for fc in curves_a]
    medians_b = [fc.median_sd_mm for fc in curves_b]
    assert medians_a == medians_b


def test_period_s_matches_height_class_own_published_period():
    # The whole point of returning period_s: it's GEM's own fundamental
    # period for this height class, not the generic code-formula period
    # (see ground_motion.py's fixed_period_s override): taller buildings
    # get longer periods.
    _, _, period_1 = compute_gem_fragility("CR", "low_code", 1)
    _, _, period_8 = compute_gem_fragility("CR", "low_code", 8)
    assert period_8 > period_1
