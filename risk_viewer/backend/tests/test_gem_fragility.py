from app.vulnerability.gem_fragility import compute_gem_fragility, supported


def test_supported_classes():
    assert supported("CR") is True
    assert supported("W") is True
    assert supported("ADO") is True
    assert supported("MUR") is True
    assert supported("MCF") is True
    assert supported("MR") is True
    assert supported("M") is False
    assert supported("unlabeled") is False


def test_mur_ignores_code_quality():
    # Non-ductile, same as ADO: GEM has no ductility-graded series for
    # unreinforced masonry.
    curves_a, _, _ = compute_gem_fragility("MUR", "pre_code", 1)
    curves_b, _, _ = compute_gem_fragility("MUR", "high_code", 1)
    medians_a = [fc.median_sd_mm for fc in curves_a]
    medians_b = [fc.median_sd_mm for fc in curves_b]
    assert medians_a == medians_b


def test_mcf_and_mr_ductility_increases_capacity():
    for structural_class in ("MCF", "MR"):
        curves_dul, _, _ = compute_gem_fragility(structural_class, "pre_code", 3)
        curves_duh, _, _ = compute_gem_fragility(structural_class, "high_code", 3)
        dul_complete = next(fc for fc in curves_dul if fc.damage_state == "complete")
        duh_complete = next(fc for fc in curves_duh if fc.damage_state == "complete")
        assert duh_complete.median_sd_mm > dul_complete.median_sd_mm


def test_masonry_damage_state_medians_increase_monotonically():
    # Each class's own 4 damage-state medians (slight < moderate <
    # extensive < complete) should increase regardless of which IM the
    # underlying archetype was published against. Not a cross-class
    # ordering claim: the published MUR/MCF/MR archetypes don't actually
    # rank unreinforced < confined < reinforced at every damage state
    # (confirmed by direct inspection -- MCF's H1/pre_code archetype
    # has a *lower* "complete" threshold than MUR's own, likely a real
    # difference in the two archetypes' assumed geometry/detailing, not
    # a data error), so that isn't asserted here.
    for structural_class in ("MUR", "MCF", "MR"):
        curves, _, _ = compute_gem_fragility(structural_class, "pre_code", 1)
        medians = [fc.median_sd_mm for fc in curves]
        assert medians == sorted(medians)


def test_pga_anchored_low_rise_masonry_still_produces_valid_curves():
    # MCF/MR H1 archetypes are published against PGA, not SA(T); see
    # scripts/vulnerability/build_gem_fragility.py. Confirms the PGA
    # proxy period doesn't break curve monotonicity or positivity.
    curves, reference, period_s = compute_gem_fragility("MCF", "pre_code", 1)
    assert period_s == 0.01
    assert "PGA-anchored" in reference["period_s"]
    medians = [fc.median_sd_mm for fc in curves]
    assert all(m > 0 for m in medians)
    assert medians == sorted(medians)


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
