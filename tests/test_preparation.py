import datetime as dt
import hashlib
import json

import numpy as np
import pytest

from rfisher import preparation, selection_policy, thresholds


Q16 = thresholds.MULTIPLIER_ONE
Q_GRID = (1, 2 * Q16)
ETA_GRID = tuple(value / Q16 for value in Q_GRID)
EVIDENCE_SHA = "1" * 64
SOURCE_ID = "sha256:" + "2" * 64


def _hist(counts=(40, 40, 20), systematic=(4.0, 4.0, 12.0),
          variance=None, bulk_size=1, q16=Q_GRID):
    return thresholds.ResidualScoreHistogram(
        bulk_size=bulk_size,
        candidate_eta=tuple(value / Q16 for value in q16),
        candidate_multiplier_q16=q16,
        counts=counts,
        systematic_residual_sums=systematic,
        variance_residual_sums=variance,
    )


def _support(frames=100, months=12, days=365.0):
    return preparation.EraHalfSupport(
        frame_count=frames,
        acquisition_count=50,
        observed_months=months,
        span_days=days,
    )


def _assessment(early=None, late=None, **kwargs):
    return preparation.assess_histogram_stability(
        {1: _hist() if early is None else early},
        {1: _hist() if late is None else late},
        early_support=_support(),
        late_support=_support(),
        max_cost_ratio=kwargs.pop("max_cost_ratio", 1.0),
        max_systematic_residual_ratio=kwargs.pop(
            "max_systematic_residual_ratio", 1.0),
        minimum_half_retained_frames=kwargs.pop(
            "minimum_half_retained_frames", 30),
        **kwargs,
    )


def _evidence(state="measured"):
    values = dict(state=state, method="test method", source="test source")
    if state in {"measured", "bounded"}:
        values["artifact_sha256"] = EVIDENCE_SHA
    if state == "bounded":
        values.update(bounds=(None, 1.0), units="ratio")
    return preparation.CalibrationEvidence(**values)


def _family(stability=None, transfer="measured", correlation="measured",
            score="measured", **kwargs):
    values = dict(
        histograms_by_rho={1: _hist()},
        source_id=SOURCE_ID,
        era_label="2024-01..2026-07",
        latest_era=True,
        valid_frames_only=True,
        equal_exposure_frames=True,
        additive_residuals=True,
        stability=_assessment() if stability is None else stability,
        score=_evidence(score),
        correlation=_evidence(correlation),
        transfer=_evidence(transfer),
    )
    values.update(kwargs)
    return preparation.PreparedThresholdFamily(**values)


def test_candidate_rank_grid_covers_every_supported_order_statistic():
    assert preparation.candidate_rho_values(4) == (1, 2, 3, 4)
    with pytest.raises(ValueError, match="positive"):
        preparation.candidate_rho_values(0)


def test_detector_rank_maps_to_one_based_rho():
    assert preparation.rho_from_cfar_rank(0) == 1
    assert preparation.rho_from_cfar_rank(63) == 64
    with pytest.raises(TypeError, match="cfar_rank must be an integer"):
        preparation.rho_from_cfar_rank(True)
    with pytest.raises(ValueError, match="cfar_rank must be non-negative"):
        preparation.rho_from_cfar_rank(-1)


def test_candidate_multiplier_grid_is_the_exact_q16_staircase():
    requirements = [1, Q16, Q16, 3 * Q16,
                    thresholds.ALWAYS_MASKED_Q16]
    assert preparation.candidate_multiplier_q16_values(requirements) == (
        1, Q16, 3 * Q16)


@pytest.mark.parametrize(
    "requirements",
    [[], [1, 0], [1, thresholds.ALWAYS_MASKED_Q16 + 1], [1, 1.5]],
)
def test_candidate_multiplier_grid_rejects_invalid_boundaries(requirements):
    with pytest.raises((TypeError, ValueError)):
        preparation.candidate_multiplier_q16_values(requirements)


def test_identical_candidate_surfaces_pass_the_drift_screen():
    result = _assessment()
    assert result.status == "passed"
    assert result.points_checked == 2
    assert result.points_skipped == 0
    assert result.maximum_cost_ratio == pytest.approx(1.0)
    assert result.maximum_systematic_residual_ratio == pytest.approx(1.0)
    assert result.maximum_masked_fraction_difference == pytest.approx(0.0)


def test_mask_and_cost_drift_refuses_the_surface():
    result = _assessment(
        late=_hist(counts=(30, 40, 30), systematic=(3.0, 4.0, 13.0)),
        max_cost_ratio=1.1,
        max_systematic_residual_ratio=1.1,
    )
    assert result.status == "refused_drift"
    assert result.maximum_cost_ratio > 1.1
    assert result.worst_cost_point == (1, ETA_GRID[0])


def test_residual_only_drift_refuses_with_unchanged_counts():
    result = _assessment(
        late=_hist(systematic=(8.0, 8.0, 4.0)),
        max_cost_ratio=1.0,
        max_systematic_residual_ratio=1.5,
    )
    assert result.status == "refused_drift"
    assert result.maximum_masked_fraction_difference == pytest.approx(0.0)
    assert result.maximum_systematic_residual_ratio == pytest.approx(2.0)


@pytest.mark.parametrize(
    "updates",
    [{"max_cost_ratio": None},
     {"max_systematic_residual_ratio": None},
     {"minimum_half_retained_frames": None}],
)
def test_missing_drift_choice_is_a_structured_refusal(updates):
    result = _assessment(**updates)
    assert result.status == "refused_unconfigured"
    assert "must be declared" in result.reason


@pytest.mark.parametrize(
    "support, expected",
    [(_support(months=5), "observed months"),
     (_support(days=269.0), "spans")],
)
def test_sparse_era_half_refuses_before_surface_comparison(support, expected):
    result = preparation.assess_histogram_stability(
        {1: _hist()}, {1: _hist()},
        early_support=support, late_support=_support(),
        max_cost_ratio=1.1, max_systematic_residual_ratio=1.1,
        minimum_half_retained_frames=30)
    assert result.status == "refused_insufficient_support"
    assert expected in result.reason


def test_selector_unsupported_points_are_skipped_before_half_support_gate():
    thin = _hist(counts=(10, 30, 60), systematic=(1.0, 3.0, 16.0))
    result = _assessment(early=thin, late=thin)
    assert result.status == "passed"
    assert result.points_skipped == 1
    assert result.points_checked == 1


def test_evaluable_candidate_needs_the_declared_half_support():
    thin = _hist(counts=(20, 20, 60), systematic=(2.0, 2.0, 16.0))
    result = _assessment(early=thin, late=thin,
                         minimum_half_retained_frames=30)
    assert result.status == "refused_insufficient_support"
    assert "rho=1" in result.reason


def test_stability_requires_matching_ranks_and_grids():
    with pytest.raises(ValueError, match="same ranks"):
        preparation.assess_histogram_stability(
            {1: _hist()}, {2: _hist()},
            early_support=_support(), late_support=_support(),
            max_cost_ratio=1.1, max_systematic_residual_ratio=1.1,
            minimum_half_retained_frames=30)
    other_grid = _hist(q16=(1, 3 * Q16))
    with pytest.raises(ValueError, match="same eta grid"):
        preparation.assess_histogram_stability(
            {1: _hist()}, {1: other_grid},
            early_support=_support(), late_support=_support(),
            max_cost_ratio=1.1, max_systematic_residual_ratio=1.1,
            minimum_half_retained_frames=30)
    first = (1 << 63) - 1
    second = 1 << 63
    same_float_a = _hist(q16=(first, thresholds.MAX_MULTIPLIER_Q16))
    same_float_b = _hist(q16=(second, thresholds.MAX_MULTIPLIER_Q16))
    assert same_float_a.candidate_eta == same_float_b.candidate_eta
    with pytest.raises(ValueError, match="same Q16 grid"):
        preparation.assess_histogram_stability(
            {1: same_float_a}, {1: same_float_b},
            early_support=_support(), late_support=_support(),
            max_cost_ratio=1.1, max_systematic_residual_ratio=1.1,
            minimum_half_retained_frames=30)


def test_global_open_decisions_prevent_an_operational_label():
    family = _family()
    assert family.status == "screening"
    with pytest.raises(preparation.PreparationRefused,
                       match="unresolved operating decisions"):
        preparation.select_prepared_threshold(family, 0.15)


def test_screening_selection_preserves_its_claim_and_provenance():
    family = _family(transfer="conditional")
    result = preparation.select_prepared_threshold(
        family, 0.15, allow_screening=True)
    assert result.claim_status == "screening"
    assert result.source_id == family.source_id
    assert result.policy_sha256 == family.policy_sha256
    assert result.status == "selected"
    assert result.selected is not None


@pytest.mark.parametrize(
    "updates, message",
    [({"latest_era": False}, "latest era"),
     ({"valid_frames_only": False}, "invalid frames"),
     ({"equal_exposure_frames": False}, "equal-exposure"),
     ({"additive_residuals": False}, "non-additive")],
)
def test_preparation_invariants_refuse_even_screening(updates, message):
    family = _family(**updates)
    with pytest.raises(preparation.PreparationRefused, match=message):
        preparation.select_prepared_threshold(
            family, 0.15, allow_screening=True)


def test_prepared_family_requires_every_rank_and_exact_q16_grid():
    with pytest.raises(ValueError, match="every supported rank"):
        _family(histograms_by_rho={1: _hist(bulk_size=2)})
    plain = thresholds.ResidualScoreHistogram(
        bulk_size=1, candidate_eta=(1.0, 2.0), counts=(40, 40, 20),
        systematic_residual_sums=(4.0, 4.0, 12.0))
    with pytest.raises(ValueError, match="exact Q16"):
        _family(histograms_by_rho={1: plain})


def test_policy_digest_mismatch_refuses_stale_family():
    policy = selection_policy.snapshot()
    policy["release_note"] = "older"
    policy_json = json.dumps(
        policy, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False)
    policy_sha256 = hashlib.sha256(policy_json.encode()).hexdigest()
    family = _family(policy_json=policy_json, policy_sha256=policy_sha256)
    with pytest.raises(preparation.PreparationRefused,
                       match="snapshot does not match"):
        preparation.select_prepared_threshold(
            family, 0.15, allow_screening=True)
    assert family.metadata()["policy"]["release_note"] == "older"


def test_bounded_evidence_requires_a_structured_bound():
    with pytest.raises(ValueError, match="bounds and units"):
        preparation.CalibrationEvidence(
            "bounded", "test", "test", artifact_sha256=EVIDENCE_SHA)
    assert _evidence("bounded").bounds == (None, 1.0)


def test_factory_derives_grids_split_support_and_histograms():
    stamps = []
    for year in (2024, 2025):
        for month in range(1, 13):
            stamp = dt.datetime(
                year, month, 1, tzinfo=dt.timezone.utc).timestamp()
            stamps.extend([stamp] * 5)
    n = len(stamps)
    pattern = [1, Q16, 2 * Q16, thresholds.ALWAYS_MASKED_Q16, Q16]
    requirements = pattern * (n // len(pattern))
    family = preparation.prepare_threshold_family(
        {1: requirements, 2: requirements},
        np.full(n, 0.02),
        frame_times=stamps,
        acquisition_ids=range(n),
        exposure_seconds=np.full(n, 41.0),
        source_id=SOURCE_ID,
        era_label="2024-01..2025-12",
        latest_era=True,
        additive_residuals=True,
        score=_evidence(),
        correlation=_evidence(),
        transfer=_evidence("conditional"),
        max_cost_ratio=1.0,
        max_systematic_residual_ratio=1.0,
        minimum_half_retained_frames=10,
    )
    assert tuple(family.histograms_by_rho) == (1, 2)
    assert family.histograms_by_rho[1].candidate_multiplier_q16 == (
        1, Q16, 2 * Q16)
    assert family.stability.status == "passed"
    assert family.stability.early_support.observed_months == 12
    assert family.stability.late_support.observed_months == 12
    assert family.status == "screening"


def test_factory_rejects_unequal_exposure():
    with pytest.raises(ValueError, match="equal exposure"):
        preparation.prepare_threshold_family(
            {1: [1, Q16]}, [0.1, 0.1],
            frame_times=[0.0, 86400.0], acquisition_ids=[1, 2],
            exposure_seconds=[1.0, 2.0], source_id="test",
            era_label="test", latest_era=True, additive_residuals=True,
            score=_evidence(), correlation=_evidence(), transfer=_evidence(),
            max_cost_ratio=1.0, max_systematic_residual_ratio=1.0,
            minimum_half_retained_frames=1,
            minimum_observed_months=1, minimum_span_days=0.5)


def test_prepared_family_requires_content_pinned_source_rows():
    with pytest.raises(ValueError, match="sha256 content identifier"):
        _family(source_id="latest-era rows")
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        _family(source_id="sha256:not-a-digest")


def test_metadata_embeds_the_stored_policy_snapshot():
    metadata = _family().metadata()
    assert metadata["policy_sha256"] == selection_policy.sha256()
    assert metadata["policy"] == selection_policy.snapshot()
    assert metadata["status"] == "screening"
    assert metadata["stability"]["cost_ratio_limit"] == 1.0
    assert metadata["score"]["state"] == "measured"
    json.dumps(metadata, allow_nan=False)
