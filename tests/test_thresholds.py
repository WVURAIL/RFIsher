import numpy as np
import pytest

from rfisher import residual, thresholds

Q16 = thresholds.Q16_SCALE


def _hist(counts=(32, 32, 36), systematic=(2.0, 6.0, 43.0),
          variance=None, bulk_size=10):
    return thresholds.ResidualScoreHistogram(
        bulk_size=bulk_size,
        candidate_multiplier_q16=(Q16, 2 * Q16),
        counts=counts,
        systematic_residual_sums=systematic,
        variance_residual_sums=variance,
    )


def test_policy_constants_match_the_reference_sweep():
    assert (thresholds.MIN_RETAINED_FRAMES ==
            residual.MIN_THRESHOLD_SWEEP_KEPT_FRAMES)


def test_histogram_derives_frame_count_from_every_bin():
    histogram = _hist()
    assert histogram.frame_count == 100

    result = thresholds.optimize_threshold({7: histogram}, 0.125)
    assert result.frame_count == 100
    assert result.bulk_size == 10
    assert result.selected.eta == 2.0
    assert result.selected.kept_frames == 64
    assert result.selected.masked_frames == 36
    assert result.selected.masked_fraction == pytest.approx(0.36)
    assert result.selected.rank_fraction == pytest.approx(7 / 11)


def test_tolerance_equality_is_feasible():
    result = thresholds.optimize_threshold({7: _hist()}, 0.125)
    point = next(point for point in result.points if point.eta == 2.0)
    assert point.systematic_residual == 0.125
    assert point.tolerance_fraction == 1.0
    assert point.feasible


def test_tighter_tolerance_selects_a_stricter_threshold():
    loose = thresholds.optimize_threshold({7: _hist()}, 0.125)
    tight = thresholds.optimize_threshold({7: _hist()}, 0.08)
    assert loose.selected.eta == 2.0
    assert tight.selected.eta == 1.0


def test_competing_ranks_use_the_lowest_cost_plateau():
    first = _hist()
    second = _hist(counts=(56, 16, 28),
                   systematic=(3.0, 6.0, 42.0))
    result = thresholds.optimize_threshold({8: second, 7: first}, 0.125)
    assert result.selected.rho == 8
    assert result.selected.eta == 2.0
    assert result.selected.masked_fraction == pytest.approx(0.28)


def test_variance_residual_can_change_the_selected_threshold():
    without_variance = _hist(
        counts=(50, 50, 0), systematic=(2.5, 2.5, 0.0))
    with_variance = _hist(
        counts=(50, 50, 0), systematic=(2.5, 2.5, 0.0),
        variance=(0.0, 200.0, 0.0))

    plain = thresholds.optimize_threshold({4: without_variance}, 0.1)
    priced = thresholds.optimize_threshold({4: with_variance}, 0.1)
    assert plain.selected.eta == 2.0
    assert plain.selected.variance_residual is None
    assert priced.selected.eta == 1.0
    assert priced.selected.variance_residual == pytest.approx(0.0)


def test_no_feasible_threshold_is_a_structured_result():
    result = thresholds.optimize_threshold({7: _hist()}, 0.05)
    assert result.selected is None
    assert result.status == "no_feasible_threshold"
    assert result.points


def test_zero_kept_candidate_is_skipped():
    histogram = _hist(counts=(0, 50, 50), systematic=(0.0, 10.0, 41.0))
    result = thresholds.optimize_threshold({7: histogram}, 0.2)
    assert [point.eta for point in result.points] == [2.0]
    assert result.selected.eta == 2.0


def test_retained_frame_floor_is_derived_from_counts():
    histogram = _hist(
        counts=(29, 1, 70), systematic=(2.9, 0.1, 48.0))
    result = thresholds.optimize_threshold({7: histogram}, 0.1)
    assert [point.eta for point in result.points] == [2.0]
    assert result.selected.kept_frames == thresholds.MIN_RETAINED_FRAMES


def test_all_unsupported_candidates_return_a_structured_result():
    histogram = _hist(
        counts=(0, 29, 71), systematic=(0.0, 2.9, 48.1))
    result = thresholds.optimize_threshold({7: histogram}, 0.1)
    assert result.points == ()
    assert result.selected is None
    assert result.status == "no_evaluable_threshold"


def test_cost_plateau_prefers_more_systematic_margin():
    histogram = _hist(
        counts=(99, 1, 0), systematic=(4.95, 1.05, 0.0))
    result = thresholds.optimize_threshold({7: histogram}, 0.1)
    assert result.points[1].cost < result.points[0].cost
    assert result.points[0].cost <= (
        thresholds.COST_PLATEAU * result.points[1].cost)
    assert result.selected.eta == 1.0


def test_q16_builder_keeps_frames_at_the_exact_boundary():
    histogram = thresholds.build_q16_residual_score_histogram(
        [1, Q16, 2 * Q16, thresholds.ALWAYS_MASKED_Q16],
        [1.0, 2.0, 3.0, 4.0],
        [1, Q16, 2 * Q16],
        bulk_size=1,
        variance_residuals=[4.0, 3.0, 2.0, 1.0],
    )
    assert histogram.candidate_multiplier_q16 == (1, Q16, 2 * Q16)
    assert histogram.counts == (1, 1, 1, 1)
    assert histogram.systematic_residual_sums == (1.0, 2.0, 3.0, 4.0)
    assert histogram.variance_residual_sums == (4.0, 3.0, 2.0, 1.0)


def test_q16_builder_preserves_boundaries_that_share_a_float_display():
    first = (1 << 63) - 1
    second = 1 << 63
    assert first / thresholds.Q16_SCALE == (
        second / thresholds.Q16_SCALE)
    histogram = thresholds.build_q16_residual_score_histogram(
        [first] * 30 + [second] * 30,
        [1.0] * 60,
        [first, second],
        bulk_size=1,
    )
    assert histogram.candidate_multiplier_q16 == (first, second)
    result = thresholds.optimize_threshold({1: histogram}, 1.0)
    assert [point.kept_frames for point in result.points] == [30, 60]
    assert [point.multiplier_q16 for point in result.points] == [first, second]


@pytest.mark.parametrize("field", ["systematic_residuals",
                                    "variance_residuals"])
def test_builder_rejects_complex_values(field):
    kwargs = dict(
        required_multiplier_q16=np.array([Q16, 2 * Q16]),
        systematic_residuals=np.array([1.0, 2.0]),
        variance_residuals=np.array([1.0, 2.0]),
        candidate_multiplier_q16=(Q16, 2 * Q16),
        bulk_size=10,
    )
    kwargs[field] = np.array([1.0 + 1.0j, 2.0 + 0.0j])
    with pytest.raises(TypeError, match="real numbers"):
        thresholds.build_q16_residual_score_histogram(**kwargs)


@pytest.mark.parametrize(
    "updates, message",
    [
        ({"systematic_residuals": np.array([-1.0, 1.0])},
         "non-negative and finite"),
        ({"variance_residuals": np.array([np.nan, 1.0])},
         "non-negative and finite"),
        ({"systematic_residuals": np.array([1.0])},
         "match required_multiplier_q16"),
        ({"systematic_residuals": np.array([[1.0, 2.0]])},
         "one-dimensional"),
    ],
)
def test_builder_rejects_invalid_arrays(updates, message):
    kwargs = dict(
        required_multiplier_q16=np.array([Q16, 2 * Q16]),
        systematic_residuals=np.array([1.0, 2.0]),
        variance_residuals=np.array([1.0, 2.0]),
        candidate_multiplier_q16=(Q16, 2 * Q16),
        bulk_size=10,
    )
    kwargs.update(updates)
    with pytest.raises((TypeError, ValueError), match=message):
        thresholds.build_q16_residual_score_histogram(**kwargs)


@pytest.mark.parametrize(
    "requirements,message",
    [([], "must not be empty"), ([0], "invalid decision boundary"),
     ([thresholds.ALWAYS_MASKED_Q16 + 1], "invalid decision boundary"),
     ([1.5], "integers"), ([True], "integers")],
)
def test_builder_rejects_invalid_exact_boundaries(requirements, message):
    with pytest.raises((TypeError, ValueError), match=message):
        thresholds.build_q16_residual_score_histogram(
            requirements, [1.0] * len(requirements), (Q16,), bulk_size=10)


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"candidate_multiplier_q16": ()}, "must not be empty"),
        ({"bulk_size": 0}, "positive"),
        ({"bulk_size": True}, "integer"),
        ({"candidate_multiplier_q16": (Q16, Q16)}, "strictly increasing"),
        ({"candidate_multiplier_q16": (0, Q16)}, "between 1"),
        ({"counts": (1, 2)}, "overflow"),
        ({"counts": (1.0, 2, 3)}, "integers"),
        ({"counts": (0, 0, 0)}, "at least one frame"),
        ({"systematic_residual_sums": (1.0, 2.0)}, "match counts"),
        ({"systematic_residual_sums": (1.0, -1.0, 2.0)}, "non-negative"),
        ({"variance_residual_sums": (1.0, 2.0)}, "match counts"),
        ({"counts": (0, 3, 7),
          "systematic_residual_sums": (0.1, 0.9, 4.1)}, "empty bin"),
        ({"counts": (0, 3, 7),
          "systematic_residual_sums": (0.0, 0.9, 4.1),
          "variance_residual_sums": (0.1, 0.9, 4.1)}, "empty bin"),
    ],
)
def test_histogram_rejects_malformed_inputs(kwargs, message):
    base = dict(
        bulk_size=10,
        candidate_multiplier_q16=(Q16, 2 * Q16),
        counts=(40, 20, 40),
        systematic_residual_sums=(4.0, 9.2, 37.8),
    )
    base.update(kwargs)
    with pytest.raises((TypeError, ValueError), match=message):
        thresholds.ResidualScoreHistogram(**base)


@pytest.mark.parametrize("tolerance", [0.0, -1.0, np.inf, np.nan, True, "1"])
def test_optimizer_rejects_invalid_tolerance(tolerance):
    with pytest.raises((TypeError, ValueError), match="science_tolerance"):
        thresholds.optimize_threshold({7: _hist()}, tolerance)


def test_optimizer_rejects_invalid_mapping():
    with pytest.raises(TypeError, match="mapping"):
        thresholds.optimize_threshold([], 0.125)
    with pytest.raises(ValueError, match="must not be empty"):
        thresholds.optimize_threshold({}, 0.125)
    with pytest.raises(TypeError, match="rho keys"):
        thresholds.optimize_threshold({True: _hist()}, 0.125)
    with pytest.raises(ValueError, match="rho keys"):
        thresholds.optimize_threshold({0: _hist()}, 0.125)
    with pytest.raises(TypeError, match="mapping values"):
        thresholds.optimize_threshold({7: object()}, 0.125)


def test_optimizer_rejects_inconsistent_rank_populations():
    with pytest.raises(ValueError, match="same frame population"):
        thresholds.optimize_threshold(
            {7: _hist(), 8: _hist(counts=(32, 32, 37))}, 0.125)

    with pytest.raises(ValueError, match="same systematic residual total"):
        thresholds.optimize_threshold(
            {7: _hist(), 8: _hist(systematic=(2.0, 6.0, 43.1))},
            0.125)

    with pytest.raises(ValueError, match="same bulk size"):
        thresholds.optimize_threshold(
            {7: _hist(), 8: _hist(bulk_size=11)}, 0.125)


def test_optimizer_rejects_rank_above_bulk_size():
    with pytest.raises(ValueError, match="cannot exceed"):
        thresholds.optimize_threshold({11: _hist()}, 0.125)


def test_optimizer_rejects_mixed_variance_bases():
    with pytest.raises(ValueError, match="same variance-residual basis"):
        thresholds.optimize_threshold(
            {7: _hist(), 8: _hist(variance=(2.0, 6.0, 43.0))},
            0.125)

    with pytest.raises(ValueError, match="same variance residual total"):
        thresholds.optimize_threshold({
            7: _hist(variance=(2.0, 6.0, 43.0)),
            8: _hist(variance=(2.0, 6.0, 43.1)),
        }, 0.125)


def test_selection_is_independent_of_mapping_order():
    first = _hist()
    second = _hist(counts=(56, 16, 28),
                   systematic=(3.0, 6.0, 42.0))
    forward = thresholds.optimize_threshold({7: first, 8: second}, 0.125)
    reverse = thresholds.optimize_threshold({8: second, 7: first}, 0.125)
    assert forward == reverse


def test_exact_ties_prefer_the_lower_rank():
    histogram = _hist()
    result = thresholds.optimize_threshold({8: histogram, 7: histogram},
                                           0.125)
    assert result.selected.rho == 7
