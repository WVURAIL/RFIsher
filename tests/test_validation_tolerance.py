"""Statistical and identity regressions for signed block tolerance limits."""
import copy
import json

import pytest
from scipy.stats import beta, binom

from rfisher_results.validation.tolerance import (
    calibrate_joint_additive,
    evaluate_joint_additive,
)


def blocks(n=60, *, prefix="cal", claim=2., truth=1., kept=100):
    return {f"{prefix}-{i:03d}": {"mixed": {"claim": claim, "truth": truth, "kept": kept}, "null": {"claim": .5, "truth": 0., "kept": 75}} for i in range(n)}


def test_rank_is_exact_tolerance_rank_not_empirical_quantile():
    cal = calibrate_joint_additive(blocks())
    assert cal["status"] == "calibrated"
    assert cal["order_rank"] == 60
    assert cal["achieved_confidence"] == pytest.approx(1-.95**60)
    assert cal["correction"] == -.5
    hundred = calibrate_joint_additive(blocks(100))
    assert hundred["order_rank"] == 99
    assert binom.cdf(97, 100, .95) < .95 <= hundred["achieved_confidence"]
    # The Beta law for the transformed kth statistic gives the same confidence.
    assert hundred["achieved_confidence"] == pytest.approx(beta.sf(.95, 99, 2))


def test_too_few_blocks_refuse_requested_confidence():
    result = calibrate_joint_additive(blocks(58))
    assert result["status"] == "refused"
    assert result["correction"] is None
    assert result["order_rank"] is None
    assert result["maximum_attainable_confidence"] < .95
    assert calibrate_joint_additive(blocks(59))["status"] == "calibrated"
    with pytest.raises(ValueError, match="refused"):
        evaluate_joint_additive(result, blocks(prefix="eval"))


def test_shared_case_maximum_not_pooled_as_independent_trials():
    source = blocks()
    source["cal-003"]["mixed"]["truth"] = 3.25
    result = calibrate_joint_additive(source)
    assert result["calibration_blocks"] == 60
    assert result["correction"] == 1.25
    # One copied case changes neither sample size nor bound.
    for row in source.values():
        row["duplicate"] = copy.deepcopy(row["mixed"])
    repeated = calibrate_joint_additive(source)
    assert repeated["correction"] == result["correction"]
    assert repeated["achieved_confidence"] == result["achieved_confidence"]


def test_negative_correction_and_zero_clipping_preserve_reference_claims():
    cal = calibrate_joint_additive(blocks())
    fresh = blocks(prefix="eval")
    fresh["eval-001"]["null"]["claim"] = .1
    result = evaluate_joint_additive(cal, fresh)
    assert result["successes"] == result["base_successes"] == 60
    null = result["cases"]["null"]["rows"][1]
    assert null["claim"] == .1
    assert null["upper"] == 0.
    assert result["joint_success_probability_lower"] == pytest.approx(.05**(1/60))
    assert result["requested_content_demonstrated"]
    json.dumps(cal, allow_nan=False)
    json.dumps(result, allow_nan=False)


def test_unsupported_calibration_is_infinite_not_dropped():
    source = blocks()
    source["cal-000"]["mixed"] = {"kept": 0, "claim": None, "truth": None}
    result = calibrate_joint_additive(source)
    assert result["status"] == "refused"
    assert result["unsupported_blocks"] == 1
    assert result["calibration_blocks"] == 60
    assert result["correction"] is None
    json.dumps(result, allow_nan=False)
    # n=100 uses the second largest score, allowing one unsupported block
    # within the predeclared tolerance tail without conditioning it away.
    source = blocks(100)
    source["cal-000"]["mixed"]["kept"] = 29
    result = calibrate_joint_additive(source)
    assert result["status"] == "calibrated"
    assert result["unsupported_blocks"] == 1
    assert result["order_rank"] == 99


def test_evaluation_counts_joint_failures_including_unsupported():
    cal = calibrate_joint_additive(blocks())
    fresh = blocks(prefix="eval")
    fresh["eval-000"]["mixed"]["truth"] = 1.75
    fresh["eval-001"]["mixed"]["kept"] = 29
    result = evaluate_joint_additive(cal, fresh)
    assert result["successes"] == 58
    assert result["failures"] == 2
    assert result["underbooked_blocks"] == 1
    assert result["unsupported_blocks"] == 1
    assert result["base_successes"] == 59
    assert not result["requested_content_demonstrated"]
    assert result["cases"]["null"]["successes"] == 60
    assert result["joint_success_probability_lower"] == pytest.approx(beta.ppf(.05, 58, 3))


@pytest.mark.parametrize("kind", ["overlap", "missing", "extra"])
def test_evaluation_binds_block_and_case_identities(kind):
    cal = calibrate_joint_additive(blocks())
    fresh = blocks(prefix="eval")
    if kind == "overlap":
        fresh["cal-000"] = fresh.pop("eval-000")
    elif kind == "missing":
        for row in fresh.values():
            del row["null"]
    else:
        for row in fresh.values():
            row["extra"] = copy.deepcopy(row["null"])
    with pytest.raises(ValueError, match="overlap|family"):
        evaluate_joint_additive(cal, fresh)


@pytest.mark.parametrize("field,value", [("truth", float("nan")), ("claim", float("inf")), ("truth", -1), ("claim", True), ("kept", True), ("kept", 1.5), ("kept", -1)])
def test_malformed_measurements_refuse(field, value):
    source = blocks()
    source["cal-000"]["mixed"][field] = value
    with pytest.raises(ValueError):
        calibrate_joint_additive(source)


@pytest.mark.parametrize("kwargs", [{"content": 1}, {"confidence": 0}, {"confidence": float("nan")}, {"min_retained": 0}, {"min_retained": True}])
def test_invalid_probability_or_support(kwargs):
    with pytest.raises(ValueError):
        calibrate_joint_additive(blocks(), **kwargs)


def test_inconsistent_calibration_family_and_empty_means_refuse():
    source = blocks()
    del source["cal-000"]["null"]
    with pytest.raises(ValueError, match="same case"):
        calibrate_joint_additive(source)
    source = blocks()
    source["cal-000"]["mixed"]["kept"] = 0
    with pytest.raises(ValueError, match="unavailable"):
        calibrate_joint_additive(source)
    with pytest.raises(ValueError, match="nonempty"):
        calibrate_joint_additive({})


def test_mutated_nonfinite_calibration_and_overflow_refuse():
    cal = calibrate_joint_additive(blocks())
    cal["correction"] = float("inf")
    with pytest.raises(ValueError, match="finite"):
        evaluate_joint_additive(cal, blocks(prefix="eval"))
    cal["correction"] = 1e308
    with pytest.raises(ValueError, match="overflow"):
        evaluate_joint_additive(cal, blocks(prefix="eval", claim=1e308))
