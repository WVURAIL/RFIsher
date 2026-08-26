import json

import pytest

from rfisher import forecast, residual, selection_policy, thresholds


def test_registry_has_unique_valid_decisions():
    assert len(selection_policy.DECISIONS) >= 50
    assert len(selection_policy.DECISIONS) == len(
        set(selection_policy.DECISIONS))
    for key, item in selection_policy.DECISIONS.items():
        assert key == item.id
        assert item.basis in selection_policy.DECISION_BASES
        assert item.status in selection_policy.DECISION_STATUSES
        assert item.rationale
        json.dumps(item.record(), allow_nan=False)


def test_snapshot_and_digest_are_deterministic():
    forward = list(selection_policy.DECISIONS)
    reverse = list(reversed(forward))
    assert selection_policy.snapshot(forward) == selection_policy.snapshot(reverse)
    assert selection_policy.sha256(forward) == selection_policy.sha256(reverse)
    assert len(selection_policy.sha256()) == 64


def test_operational_gate_lists_open_and_conditional_choices():
    unresolved = {item.id for item in selection_policy.blockers(
        selection_policy.OPERATIONAL_REQUIRED_IDS)}
    assert "stability.maximum_cost_ratio" in unresolved
    assert "transfer.systematic_gain" in unresolved
    assert "preparation.designated_set_calibration" in unresolved
    assert "science.systematic_budget.primary_zeta" in unresolved
    assert "selection.cost_plateau_ratio" in unresolved
    assert "archive_diagnostic.null_center_agreement_db" not in unresolved
    with pytest.raises(selection_policy.PolicyNotOperational,
                       match="unresolved threshold decisions"):
        selection_policy.require_operational()


def test_allowing_conditional_does_not_hide_open_choices():
    unresolved = {item.id for item in selection_policy.blockers(
        selection_policy.OPERATIONAL_REQUIRED_IDS,
        allow_provisional=True, allow_conditional=True)}
    assert "transfer.systematic_gain" not in unresolved
    assert "stability.maximum_cost_ratio" in unresolved


def test_public_constants_come_from_the_registry():
    assert thresholds.MIN_RETAINED_FRAMES == selection_policy.value(
        "selection.minimum_retained_frames")
    assert thresholds.COST_PLATEAU == selection_policy.value(
        "selection.cost_plateau_ratio")
    assert residual.MIN_THRESHOLD_SWEEP_KEPT_FRAMES == thresholds.MIN_RETAINED_FRAMES
    assert residual.MIN_MEASURED_NULLS == selection_policy.value(
        "floor.minimum_null_frames")
    assert residual.TRIM_PROBES == tuple(selection_policy.value(
        "correlation.trim_probes"))
    assert residual.CORRELATION_BOOTSTRAP_SEED == selection_policy.value(
        "correlation.bootstrap_seed")
    assert residual.DEFAULT_DELAY_KEY == selection_policy.value(
        "transfer.delay_suppression.default_key")
    assert forecast.FISHER_CONDITION_LIMIT == selection_policy.value(
        "science.response_solver.maximum_condition_number")
    assert forecast.FISHER_NULLSPACE_RTOL == selection_policy.value(
        "science.response_solver.relative_nullspace_cutoff")
    assert forecast.V_FRAC_MIN == selection_policy.value(
        "science.response_solver.minimum_volume_fraction")


def test_cross_project_keyword_sets_are_explicit():
    assert selection_policy.value("preparation.rank_index_mapping") == (
        "rho_equals_zero_based_cfar_rank_plus_one")
    assert selection_policy.era_kwargs() == {
        "min_months": 6,
        "min_days": 270.0,
        "min_step_db": 2.0,
        "z_crit": 4.0,
        "max_eras": 5,
    }
    assert selection_policy.quiet_floor_kwargs() == {
        "level_threshold_db": 1.0,
        "percentile": 90.0,
        "minimum_frames": 30,
    }


def test_unknown_decision_fails_loudly():
    with pytest.raises(KeyError, match="unknown threshold decision"):
        selection_policy.decision("missing.choice")
