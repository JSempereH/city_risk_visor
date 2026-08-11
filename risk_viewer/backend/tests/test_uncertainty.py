import numpy as np

from app.risk.uncertainty import capacity_beta_from_gpr_std, combine_uncertainty


def test_capacity_beta_zero_when_std_is_zero():
    v = np.array([0.1, 0.5, 1.0, 0.8])
    std = np.zeros_like(v)
    assert capacity_beta_from_gpr_std(v, std) == 0.0


def test_capacity_beta_scales_with_relative_uncertainty():
    v = np.array([0.1, 0.5, 1.0, 0.8])
    low_std = 0.01 * v
    high_std = 0.5 * v
    assert capacity_beta_from_gpr_std(v, low_std) < capacity_beta_from_gpr_std(v, high_std)


def test_capacity_beta_ignores_near_zero_curve_points():
    # Points at v_over_w ~ 0 (e.g. the curve's origin) shouldn't blow up
    # the coefficient of variation even if their std is nonzero.
    v = np.array([0.0, 0.5, 1.0])
    std = np.array([0.3, 0.05, 0.1])
    beta = capacity_beta_from_gpr_std(v, std)
    assert beta < 1.0


def test_capacity_beta_ignores_negative_origin_noise():
    # Real, confirmed case (santo_domingo_113): the GPR's predicted mean
    # goes slightly negative right at the curve's origin (an
    # extrapolation artifact, the model was never trained to guarantee
    # V/W(0) = 0), and the std does not shrink at the same rate, so the
    # single point right after the negative dip has a tiny positive mean
    # next to a much larger std. An absolute v_over_w > 1e-6 cutoff lets
    # that one point dominate the RMS average (beta blew up to 33.8
    # before this test's fix); a curve-relative cutoff excludes the whole
    # unstable ramp-up region instead of just the exact-zero point.
    v = np.array([-0.0083, -0.0114, 0.00007, 0.0199, 0.0432, 0.0656, 0.443])
    std = np.array([0.0119, 0.0241, 0.0378, 0.0454, 0.0501, 0.0532, 0.09])
    beta = capacity_beta_from_gpr_std(v, std)
    assert beta < 1.0


def test_combine_uncertainty_includes_capacity_beta():
    with_capacity = combine_uncertainty(fragility_beta=0.7, gmpe_sigma_ln=0.5, capacity_beta=0.3)
    without_capacity = combine_uncertainty(fragility_beta=0.7, gmpe_sigma_ln=0.5, capacity_beta=0.0)
    assert with_capacity.total_beta > without_capacity.total_beta
    assert with_capacity.capacity_beta == 0.3
