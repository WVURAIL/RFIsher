"""Quiet data and diagnostics must not become measured RFI by implication."""
from __future__ import annotations

import numpy as np
import pytest

from rfisher.response.evidence import (
    UnqualifiedResponseError, require_science_selection_evidence,
)
from rfisher.response.same_mask import coordinates, select
from rfisher.response.visibility import (
    linear_parameter_response, quadratic_contamination,
)


def physical_declaration():
    return {
        "evidence_kind": "physical_same_mask_response",
        "physical_response_qualified": True,
        "science_selection_eligible": True,
        "residual_contains_sensitivity_floor": False,
    }


@pytest.mark.parametrize("proxy_ratio", [0., .01, 1., 100.])
@pytest.mark.parametrize("kind", [None, "conditional_screening_allowance",
                                  "matched_null_detector_contrast"])
def test_no_diagnostic_ratio_can_select_or_prove_excision(proxy_ratio, kind):
    # Even otherwise favorable or contradictory flags cannot promote a proxy.
    row = dict(physical_declaration(), r_sys=proxy_ratio, r_tol=1.)
    if kind is None:
        del row["evidence_kind"]
    else:
        row["evidence_kind"] = kind
    with pytest.raises(UnqualifiedResponseError, match="does not justify reject-all"):
        require_science_selection_evidence(row)


@pytest.mark.parametrize("key,value", [
    ("physical_response_qualified", False),
    ("physical_response_qualified", "True"),
    ("science_selection_eligible", None),
    ("science_selection_eligible", 1),
    ("residual_contains_sensitivity_floor", True),
    ("residual_contains_sensitivity_floor", "False"),
])
def test_physical_boundary_requires_exact_explicit_flags(key, value):
    row = physical_declaration()
    row[key] = value
    with pytest.raises(UnqualifiedResponseError):
        require_science_selection_evidence(row)


def test_legacy_rows_are_ineligible_and_declared_physical_response_can_continue():
    with pytest.raises(UnqualifiedResponseError):
        require_science_selection_evidence({"r_sys": 0., "r_tol": 1.})
    require_science_selection_evidence(physical_declaration())
    with pytest.raises(TypeError, match="mapping"):
        require_science_selection_evidence([])


def test_clean_limit_has_zero_bias_positive_noise_and_prefers_full_retention():
    # Identical clean and observed distributions have finite thermal variance;
    # that variance must never become a positive interference residual.
    covariance = np.diag([2., 3.])
    moments = quadratic_contamination(
        [0., 0.], covariance, [0., 0.], covariance,
        np.array([np.diag([1., 0.]), np.diag([0., 1.])]))
    np.testing.assert_array_equal(moments["statistic_bias"], [0., 0.])
    assert np.all(np.diag(moments["observed_statistic_covariance"]) > 0.)
    fit = linear_parameter_response(
        np.eye(2), moments["clean_statistic_covariance"],
        moments["statistic_bias"], moments["observed_statistic_covariance"],
        parameter_names=["alpha_parallel", "alpha_perpendicular"])
    target = np.diag(fit["covariance"])/100.
    full = coordinates(fit, target)
    half = coordinates(dict(fit, covariance=fit["covariance"]*2), target)
    np.testing.assert_array_equal(full[:2], [0., 0.])
    np.testing.assert_array_equal(half[:2], [0., 0.])
    assert full[2] == pytest.approx(100.)
    assert half[2] == pytest.approx(200.)
    rows = [{"index": index, "status": "calibration_feasible",
             "time_point_blocks": int(round(value[2])),
             "time_lower_blocks": value[2], "time_upper_blocks": value[2]}
            for index, value in enumerate((half, full))]
    assert select(rows)["selected_index"] == 1
    assert select(rows)["point_minimum_blocks"] == 100
    # Failure of all admissions is not a least-residual fallback or excision.
    for row in rows:
        row["status"] = "bias_requirement_unresolved"
    assert select(rows) == {"status": "no_admitted_candidate", "selected_index": None}
