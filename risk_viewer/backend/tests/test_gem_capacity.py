from app.vulnerability.gem_capacity import compute_gem_capacity, supported


def test_supported_classes():
    assert supported("CR") is True
    assert supported("W") is True
    assert supported("ADO") is True
    assert supported("MUR") is True
    assert supported("MCF") is True
    assert supported("MR") is True
    assert supported("M") is False
    assert supported("unlabeled") is False


def test_curve_starts_at_origin_and_is_monotonic():
    for structural_class in ("CR", "W", "ADO", "MUR", "MCF", "MR"):
        sd_mm, sa_g, _ = compute_gem_capacity(structural_class, "low_code", 2)
        assert sd_mm[0] == 0.0
        assert sa_g[0] == 0.0
        assert sd_mm == sorted(sd_mm)
        assert len(sd_mm) == len(sa_g)
        assert len(sd_mm) >= 3


def test_no_floor_count_defaults_to_height_class_2():
    sd_default, sa_default, _ = compute_gem_capacity("CR", "low_code", None)
    sd_two, sa_two, _ = compute_gem_capacity("CR", "low_code", 2)
    assert sd_default == sd_two
    assert sa_default == sa_two


def test_taller_building_has_higher_capacity():
    _, sa_g_low, _ = compute_gem_capacity("CR", "low_code", 1)
    _, sa_g_high, _ = compute_gem_capacity("CR", "low_code", 8)
    assert max(sa_g_high) != max(sa_g_low)


def test_higher_ductility_increases_capacity():
    _, sa_g_dul, _ = compute_gem_capacity("CR", "pre_code", 3)
    _, sa_g_duh, _ = compute_gem_capacity("CR", "high_code", 3)
    assert max(sa_g_duh) >= max(sa_g_dul)


def test_mur_ignores_code_quality():
    # Non-ductile, same as ADO: GEM has no ductility-graded series for
    # unreinforced masonry.
    curve_a = compute_gem_capacity("MUR", "pre_code", 1)
    curve_b = compute_gem_capacity("MUR", "high_code", 1)
    assert curve_a == curve_b


def test_height_class_clamps_to_available_range():
    # CR only has GEM height classes 1-10; a 20-storey building should
    # clamp to the tallest available class rather than raising.
    _, _, assumptions = compute_gem_capacity("CR", "low_code", 20)
    assert "H10" in assumptions["capacity_curve"]


def test_same_archetype_key_as_fragility():
    # The whole point of gem_taxonomy.py: a building's capacity curve and
    # fragility curve must resolve to the exact same archetype key.
    from app.vulnerability.gem_fragility import compute_gem_fragility

    for structural_class in ("CR", "W", "ADO", "MUR", "MCF", "MR"):
        _, _, capacity_assumptions = compute_gem_capacity(structural_class, "medium_code", 4)
        _, fragility_assumptions, _ = compute_gem_fragility(structural_class, "medium_code", 4)
        # Both assumptions dicts embed the same "key '...'" fragment.
        capacity_key = capacity_assumptions["capacity_curve"].split("key '")[1].split("'")[0]
        fragility_key = fragility_assumptions["structural_system_class"].split("key '")[1].split("'")[0]
        assert capacity_key == fragility_key
