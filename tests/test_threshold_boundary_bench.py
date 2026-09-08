"""Malformed container, exact eligibility and cumulative-population boundaries."""
from dataclasses import replace

import numpy as np
import pytest

from rfisher import thresholds as t


def _hist(**changes):
    values = dict(bulk_size=2, candidate_multiplier_q16=(1, 65536), counts=(30, 30, 40),
                   systematic_residual_sums=(3.0, 9.0, 20.0), variance_residual_sums=(6.0, 12.0, 20.0))
    values.update(changes)
    return t.ResidualScoreHistogram(**values)


@pytest.mark.parametrize("field,value", [
    ("counts", "100"), ("counts", None), ("counts", (-1, 61, 40)),
    ("systematic_residual_sums", "123"), ("systematic_residual_sums", None),
    ("systematic_residual_sums", (True, 1, 2)), ("systematic_residual_sums", (1, np.inf, 2)),
    ("candidate_multiplier_q16", "123"), ("candidate_multiplier_q16", None),
    ("candidate_multiplier_q16", (1.0, 2)),
    ("candidate_eligible", (True,)), ("candidate_eligible", (1, 0)),
])
def test_histogram_refuses_malformed_containers_without_coercion(field, value):
    with pytest.raises((TypeError, ValueError), match=field):
        _hist(**{field: value})


@pytest.mark.parametrize("requirements,candidates,scores", [
    ("1", [1], [1]), (None, [1], [1]), ([1], [], [1]),
    ([1], [2, 1], [1]), ([1], [1], ["1"]),
])
def test_builder_refuses_invalid_boundaries_and_text_scores(requirements, candidates, scores):
    with pytest.raises((TypeError, ValueError)):
        t.build_q16_residual_score_histogram(requirements, scores, candidates, bulk_size=1)


def test_ineligible_candidate_does_not_remove_its_frames_from_later_prefixes():
    histogram = _hist(candidate_eligible=(False, True))
    result = t.optimize_threshold({1: histogram}, 0.25)
    assert len(result.points) == 1 and result.selected.multiplier_q16 == 65536
    assert result.selected.kept_frames == 60
    assert result.selected.systematic_residual == pytest.approx(12 / 60)
    assert result.selected.variance_residual == pytest.approx(18 / 60)
    assert result.selected.cost == pytest.approx(1.3 / 0.6)
    refused = t.optimize_threshold({1: replace(histogram, candidate_eligible=(False, False))}, 0.25)
    assert refused.status == "no_evaluable_threshold" and not refused.points


def test_one_ulp_above_science_budget_is_infeasible():
    histogram = _hist()
    assert t.optimize_threshold({1: histogram}, 0.1).selected.multiplier_q16 == 1
    assert t.optimize_threshold({1: histogram}, np.nextafter(0.1, 0)).selected is None
