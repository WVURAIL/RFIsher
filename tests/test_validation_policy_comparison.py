"""Boundary checks for exact policy thresholds and paired accounting."""

from fractions import Fraction

import numpy as np
import pytest

from rfisher.thresholds import ALWAYS_MASKED_Q16, MAX_MULTIPLIER_Q16
from rfisher_results.validation.policy_comparison import (
    coarse_quantile_threshold,
    fine_keep,
    fine_quantile_threshold,
    overlap_2x2,
    same_mask_summary,
)


def test_fine_rank_uses_exact_fraction_and_ties():
    # ceil(9/10 * 10) is exactly 9, without floating rank arithmetic.
    result = fine_quantile_threshold(list(range(11)), quantile=(9, 10))
    assert result["selected_index"] == 9
    assert result["eta_q16"] == 9
    assert result["calibration_kept"] == 10
    tied = fine_quantile_threshold([9, 1, 9, 9], quantile=Fraction(1, 2))
    assert tied["selected_index"] == 2
    assert tied["eta_q16"] == 9
    assert tied["calibration_retention"] == 1.0


def test_large_uint64_scores_are_not_rounded():
    values = np.array(
        [MAX_MULTIPLIER_Q16 - 2, MAX_MULTIPLIER_Q16 - 1, MAX_MULTIPLIER_Q16],
        dtype=np.uint64,
    )
    result = fine_quantile_threshold(values, percent=50)
    assert result["eta_q16"] == MAX_MULTIPLIER_Q16 - 1
    assert result["calibration_kept"] == 2
    np.testing.assert_array_equal(
        fine_keep(values, result["eta_q16"]), [True, True, False]
    )
    maximum = fine_quantile_threshold(values, percent=100)
    assert maximum["eta_q16"] == MAX_MULTIPLIER_Q16
    assert maximum["status"] == "selected"


def test_sentinel_remains_in_order_statistic_and_denominator():
    values = np.array([1, ALWAYS_MASKED_Q16, 2], dtype=object)
    result = fine_quantile_threshold(values, percent=50)
    assert result["eta_q16"] == 2
    assert result["frames"] == 3
    assert result["sentinel_frames"] == 1
    assert result["calibration_retention"] == pytest.approx(2 / 3)
    for percent in (90, 100):
        refused = fine_quantile_threshold(values, percent=percent)
        assert refused["status"] == "unavailable"
        assert refused["selected_requirement"] == ALWAYS_MASKED_Q16
        assert refused["eta_q16"] is None
    np.testing.assert_array_equal(
        fine_keep(values, MAX_MULTIPLIER_Q16), [True, False, True]
    )


def test_zero_requirement_maps_to_lowest_deployed_eta():
    result = fine_quantile_threshold([0, 0, 1, 2], percent=0)
    assert result["selected_requirement"] == 0
    assert result["eta_q16"] == 1
    assert result["calibration_kept"] == 3
    np.testing.assert_array_equal(fine_keep([0, 1, 2], 1), [True, True, False])


@pytest.mark.parametrize(
    "values,error",
    [
        ([True], TypeError),
        ([np.bool_(True)], TypeError),
        ([1.0], TypeError),
        (["1"], TypeError),
        ([None], TypeError),
        ([1 + 0j], TypeError),
        ([-1], ValueError),
        ([ALWAYS_MASKED_Q16 + 1], ValueError),
        ([[1]], ValueError),
        (1, ValueError),
    ],
)
def test_invalid_fine_requirements(values, error):
    with pytest.raises(error):
        fine_quantile_threshold(values, percent=50)
    with pytest.raises(error):
        fine_keep(values, 1)


@pytest.mark.parametrize(
    "eta,error",
    [
        (0, ValueError),
        (-1, ValueError),
        (ALWAYS_MASKED_Q16, ValueError),
        (True, TypeError),
        (np.bool_(True), TypeError),
        (1.0, TypeError),
    ],
)
def test_invalid_eta(eta, error):
    with pytest.raises(error):
        fine_keep([1], eta)


@pytest.mark.parametrize(
    "kwargs,error",
    [
        ({}, ValueError),
        ({"quantile": (1, 2), "percent": 50}, ValueError),
        ({"quantile": 0.5}, TypeError),
        ({"quantile": True}, TypeError),
        ({"quantile": (1, False)}, TypeError),
        ({"quantile": (1, 2.0)}, TypeError),
        ({"quantile": (1, 0)}, ValueError),
        ({"quantile": (1, -2)}, ValueError),
        ({"quantile": (-1, 2)}, ValueError),
        ({"quantile": (3, 2)}, ValueError),
        ({"percent": True}, TypeError),
        ({"percent": 50.0}, TypeError),
        ({"percent": -1}, ValueError),
        ({"percent": 101}, ValueError),
    ],
)
def test_invalid_quantile(kwargs, error):
    for helper in (fine_quantile_threshold, coarse_quantile_threshold):
        with pytest.raises(error):
            helper([1, 2], **kwargs)


def test_empty_thresholds_explicitly_unavailable():
    for helper in (fine_quantile_threshold, coarse_quantile_threshold):
        result = helper([], percent=50)
        assert result["status"] == "unavailable"
        assert result["frames"] == 0
        assert result["calibration_retention"] is None


def test_coarse_higher_preserves_exact_float_ratio():
    values = np.array([1.000001, 1.000002, 1.000003, 9.0])
    result = coarse_quantile_threshold(values, percent=50)
    assert result["eta"] == np.quantile(values, 0.5, method="higher")
    assert result["eta"].as_integer_ratio() == (
        result["eta_numerator"],
        result["eta_denominator"],
    )
    assert result["calibration_kept"] == 3
    assert result["calibration_retention"] == 0.75


@pytest.mark.parametrize(
    "values", [[np.nan], [np.inf], [-1], [[1]], [True], [1j], ["1"]]
)
def test_invalid_coarse_scores(values):
    with pytest.raises((ValueError, TypeError)):
        coarse_quantile_threshold(values, percent=50)


def test_overlap_has_declared_row_column_orientation():
    result = overlap_2x2(
        [False, False, True, True, True], [False, True, False, True, True]
    )
    assert result["matrix"] == [[1, 1], [1, 2]]
    assert result["left_only_kept"] == result["right_only_kept"] == 1
    assert result["left_kept"] == result["right_kept"] == 3
    assert result["agreement_fraction"] == 0.6
    assert result["kept_jaccard"] == 0.5
    assert overlap_2x2([False], [False])["kept_jaccard"] is None
    assert overlap_2x2([], [])["agreement_fraction"] is None


def test_same_mask_residual_and_exposure_stay_paired():
    result = same_mask_summary([True, False, True], [1, 100, 3], [1, 100, 3])
    assert result["kept"] == 2
    assert result["retention"] == pytest.approx(2 / 3)
    assert result["total_exposure"] == 104
    assert result["kept_exposure"] == 4
    assert result["mask_only_exposure_cost"] == 26
    assert result["kept_residual_sum"] == 4
    assert result["kept_residual_mean"] == 2
    assert result["kept_exposure_weighted_residual_sum"] == 10
    assert result["kept_exposure_weighted_residual_mean"] == 2.5
    assert result["scientific_certification"] is False
    assert result["physical_confidence_claim"] is False


def test_empty_and_zero_kept_summaries_do_not_claim_residual_zero():
    for result in (same_mask_summary([], []), same_mask_summary([False], [10])):
        assert result["kept"] == 0
        assert result["kept_residual_sum"] == 0
        assert result["kept_residual_mean"] is None
        assert result["kept_exposure_weighted_residual_mean"] is None
        assert result["mask_only_exposure_cost"] is None
    default_exposure = same_mask_summary([True, False], [2, 10])
    assert default_exposure["total_exposure"] == 2
    assert default_exposure["mask_only_exposure_cost"] == 2


@pytest.mark.parametrize("residual", [np.nan, np.inf, -1, True, 1j])
def test_bad_residual_is_refused_even_when_dropped(residual):
    with pytest.raises((ValueError, TypeError)):
        same_mask_summary([False], [residual])


@pytest.mark.parametrize("exposure", [0, -1, np.nan, np.inf, True, 1j])
def test_bad_exposure_is_refused_even_when_dropped(exposure):
    with pytest.raises((ValueError, TypeError)):
        same_mask_summary([False], [1], [exposure])


@pytest.mark.parametrize("mask", [[0, 1], [[True]], ["True"]])
def test_masks_must_be_boolean_vectors(mask):
    with pytest.raises((TypeError, ValueError)):
        overlap_2x2(mask, mask)
    with pytest.raises((TypeError, ValueError)):
        same_mask_summary(mask, [1, 2])


def test_shapes_must_match():
    with pytest.raises(ValueError):
        overlap_2x2([True], [True, False])
    with pytest.raises(ValueError):
        same_mask_summary([True], [1, 2])
    with pytest.raises(ValueError):
        same_mask_summary([True], [1], [1, 2])


def test_nonfinite_derived_totals_are_refused():
    with pytest.raises(ValueError):
        same_mask_summary([True, True], [1e308, 1e308])
    with pytest.raises(ValueError):
        same_mask_summary([True], [1e308], [2.0])


def test_helpers_do_not_mutate_inputs():
    requirements = np.array([ALWAYS_MASKED_Q16, 2, 1], dtype=object)
    scores = np.array([3.0, 2.0, 1.0])
    mask = np.array([True, False, True])
    copies = [array.copy() for array in (requirements, scores, mask)]
    fine_quantile_threshold(requirements, percent=50)
    fine_keep(requirements, 2)
    coarse_quantile_threshold(scores, percent=50)
    overlap_2x2(mask, ~mask)
    same_mask_summary(mask, scores, scores)
    for original, before in zip((requirements, scores, mask), copies):
        np.testing.assert_array_equal(original, before)


def test_zero_coarse_threshold_is_unavailable():
    result = coarse_quantile_threshold([0, 0, 1], percent=0)
    assert result["status"] == "unavailable"
    assert result["eta"] is None
    assert result["reason"] == "selected coarse threshold is not positive"
