from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import json

import pytest

from rfisher_results.archive import eras
from rfisher_results.validation.causal_eras import (
    append_monitor, freeze_candidate, month_evidence, record_evaluation, verify_ledger,
)

HASH = "a" * 64


def t(value):
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def record(month, level=2., *, maps=("map-A",), populated=True):
    return eras.MonthRecord(month=2020 * 12 + month - 1,
                           frames=100 if populated else 1, units=5 if populated else 1,
                           days=3 if populated else 1, populated=populated,
                           level_db=level, state=eras.state_of(level), peak_offset_bins=0.,
                           peak_cohort="detected", peak_frames=100 if populated else 1,
                           input_maps=maps, software_tags=())


def evidence(month, level=2., **kwargs):
    return month_evidence(record(month, level, **kwargs),
                          available_at=t(f"2020-{month + 1:02}-01"), source_sha256=HASH)


def frozen():
    return freeze_candidate([evidence(1), evidence(2)], eras.DEFAULT_CONFIG,
                            version_id="candidate-1", cutoff_month="2020-02",
                            frozen_at=t("2020-03-01"), candidate_activation_at=t("2020-03-02"),
                            calibration_sha256="b" * 64, source_identity={"producer": HASH})


def evaluated(ledger, name="acq-A", start="2020-03-10", end="2020-03-11"):
    return record_evaluation(ledger, acquisition_id=name, start=t(start), end=t(end),
                             recorded_at=t(end), source_sha256="c" * 64)


def test_freeze_roundtrips_exactly_and_binds_source_policy_availability():
    ledger = frozen()
    verify_ledger(json.loads(json.dumps(ledger)))
    assert ledger["status"] == "candidate_frozen"
    assert ledger["frozen_assignments"]["2020-01"]["state"] == eras.PROXY_HIGH
    assert ledger["config_digest"] == eras.DEFAULT_CONFIG.digest
    assert ledger["source_identity"] == {"producer": HASH}
    assert ledger["operational_acceptance"] is False
    assert ledger["policy_activation_at"] is None


def test_month_completion_and_evidence_availability_cannot_be_backdated():
    with pytest.raises(ValueError, match="month is complete"):
        month_evidence(record(2), available_at=t("2020-02-29"), source_sha256=HASH)
    history = [evidence(1), {**evidence(2), "available_at": t("2020-03-03").isoformat()}]
    with pytest.raises(ValueError, match="unavailable"):
        freeze_candidate(history, eras.DEFAULT_CONFIG, version_id="v", cutoff_month="2020-02",
                         frozen_at=t("2020-03-01"), candidate_activation_at=t("2020-03-02"),
                         calibration_sha256=HASH, source_identity={"producer": HASH})
    with pytest.raises(ValueError, match="availability"):
        append_monitor(frozen(), evidence(3), detected_at=t("2020-03-31"))


def test_future_months_cannot_enter_freeze_or_change_earlier_commitments():
    with pytest.raises(ValueError, match="at or before"):
        freeze_candidate([evidence(1), evidence(2), evidence(3)], eras.DEFAULT_CONFIG,
                         version_id="v", cutoff_month="2020-02", frozen_at=t("2020-04-01"),
                         candidate_activation_at=t("2020-04-02"), calibration_sha256=HASH,
                         source_identity={"producer": HASH})
    original = evaluated(frozen())
    preserved = deepcopy(original)
    first = append_monitor(original, evidence(3, .75), detected_at=t("2020-04-01"))
    second = append_monitor(first, evidence(4, 0.), detected_at=t("2020-05-01"))
    third = append_monitor(second, evidence(5, 0.), detected_at=t("2020-06-01"))
    assert original == preserved
    assert third["evaluations"] == original["evaluations"]
    assert third["frozen_assignments"] == original["frozen_assignments"]
    assert third["monitor_decisions"][:2] == second["monitor_decisions"]
    changes = third["monitor_decisions"][-1]["revised_prior_assignments"]
    assert any(r["month"] == "2020-03" and r["committed"]["state"] == eras.PROXY_HIGH
               and r["new_diagnostic"]["state"] == eras.ZONE for r in changes)
    assert first["halted_at"] == t("2020-04-01").isoformat()
    assert third["monitor_decisions"][-1]["inferred_onset_month"] == "2020-03"
    assert third["monitor_decisions"][-1]["detected_at"] == t("2020-06-01").isoformat()
    assert third["policy_activation_at"] is None


@pytest.mark.parametrize("kwargs, expected", [
    ({"maps": ("map-B",)}, "input-map identity changed"),
    ({"maps": ()}, "input-map identity unavailable"),
    ({"populated": False}, "monthly support insufficient"),
])
def test_conservative_monitor_stops_even_without_segmenter_confirmation(kwargs, expected):
    ledger = append_monitor(frozen(), evidence(3, **kwargs), detected_at=t("2020-04-01"))
    assert expected in ledger["monitor_decisions"][-1]["reasons"]
    assert ledger["status"] == "halted_requires_recalibration"


def test_calendar_gaps_and_raw_state_departures_stop_candidate():
    gap = append_monitor(frozen(), evidence(5), detected_at=t("2020-06-01"))
    assert "unobserved calendar gap exceeds frozen grace" in gap["monitor_decisions"][-1]["reasons"]
    state = append_monitor(frozen(), evidence(3, 0.), detected_at=t("2020-04-01"))
    assert "monthly level differs from frozen era state" in state["monitor_decisions"][-1]["reasons"]


def test_halt_latches_and_all_subsequent_evaluation_attempts_are_retained():
    halted = append_monitor(evaluated(frozen()), evidence(3, .75), detected_at=t("2020-04-01"))
    later = evaluated(halted, "acq-B", "2020-04-10", "2020-04-11")
    recovered = append_monitor(later, evidence(4), detected_at=t("2020-05-01"))
    assert recovered["status"] == "halted_requires_recalibration"
    assert recovered["evaluations"][0]["disposition"] == "offline_candidate_recorded"
    assert recovered["evaluations"][1]["disposition"] == "refused_after_halt"
    assert recovered["evaluations"] == later["evaluations"]


def test_successor_requires_new_calibration_and_preserves_lineage_exclusion():
    parent = append_monitor(evaluated(frozen()), evidence(3, .75), detected_at=t("2020-04-01"))
    parent = append_monitor(parent, evidence(4), detected_at=t("2020-05-01"))
    options = dict(version_id="candidate-2", cutoff_month="2020-04", frozen_at=t("2020-05-02"),
                   candidate_activation_at=t("2020-05-03"), source_identity={"producer": HASH}, previous=parent)
    with pytest.raises(ValueError, match="new version and calibration"):
        freeze_candidate(parent["monthly_history"], eras.DEFAULT_CONFIG,
                         calibration_sha256=parent["calibration_sha256"], **options)
    child = freeze_candidate(parent["monthly_history"], eras.DEFAULT_CONFIG,
                             calibration_sha256="d" * 64, **options)
    assert child["parent_ledger_sha256"] == parent["ledger_sha256"]
    assert child["excluded_acquisitions"] == ["acq-A"]
    assert child["operational_acceptance"] is False
    with pytest.raises(ValueError, match="already used"):
        evaluated(child, "acq-A", "2020-05-10", "2020-05-11")
    changed = deepcopy(parent["monthly_history"])
    changed[0]["record"]["level_db"] = 1.5
    with pytest.raises(ValueError, match="preserve"):
        freeze_candidate(changed, eras.DEFAULT_CONFIG, calibration_sha256="d" * 64, **options)


def test_integrity_chronology_duplicate_acquisitions_and_timezone_validation():
    changed = frozen()
    changed["frozen_assignments"]["2020-01"]["state"] = eras.PROXY_LOW
    with pytest.raises(ValueError, match="digest"):
        append_monitor(changed, evidence(3), detected_at=t("2020-04-01"))
    with pytest.raises(ValueError, match="chronological"):
        append_monitor(frozen(), evidence(2), detected_at=t("2020-04-01"))
    with pytest.raises(ValueError, match="already used"):
        evaluated(evaluated(frozen()))
    with pytest.raises(ValueError, match="follow the freeze"):
        evaluated(frozen(), start="2020-03-01", end="2020-03-02")
    with pytest.raises(ValueError, match="timezone-aware"):
        month_evidence(record(1), available_at=datetime(2020, 2, 1), source_sha256=HASH)
    bad = replace(record(1), units=101)
    with pytest.raises(ValueError, match="exceed frame count"):
        freeze_candidate([month_evidence(bad, available_at=t("2020-02-01"), source_sha256=HASH)],
                         eras.DEFAULT_CONFIG, version_id="v", cutoff_month="2020-01",
                         frozen_at=t("2020-02-01"), candidate_activation_at=t("2020-02-02"),
                         calibration_sha256=HASH, source_identity={"producer": HASH})


def test_assumed_availability_is_always_visible_in_candidate_scope():
    history = [evidence(1), evidence(2)]
    history[0]["availability_basis"] = "assumed_retrospective"
    ledger = freeze_candidate(history, eras.DEFAULT_CONFIG, version_id="v", cutoff_month="2020-02",
                              frozen_at=t("2020-03-01"), candidate_activation_at=t("2020-03-02"),
                              calibration_sha256=HASH, source_identity={"producer": HASH})
    assert ledger["availability_scope"] == "assumed_retrospective"
    assert ledger["scientific_certification"] is False


def test_absent_monitor_updates_cannot_leave_candidate_usable_indefinitely():
    ledger = evaluated(frozen(), "late-acq", "2020-06-10", "2020-06-11")
    assert ledger["status"] == "halted_requires_recalibration"
    assert ledger["evaluations"][0]["disposition"] == "refused_after_halt"
    assert "monthly evidence stale at evaluation decision" in ledger["evaluations"][0]["refusal_reasons"]
    assert ledger["halted_at"] == t("2020-06-11").isoformat()


def test_ambiguous_last_month_cannot_activate_from_inherited_definite_state():
    history = [evidence(1), evidence(2), evidence(3, .75)]
    ledger = freeze_candidate(history, eras.DEFAULT_CONFIG, version_id="v", cutoff_month="2020-03",
                              frozen_at=t("2020-04-01"), candidate_activation_at=t("2020-04-02"),
                              calibration_sha256=HASH, source_identity={"producer": HASH})
    assert ledger["reference_assignment"]["state"] == eras.PROXY_HIGH
    assert ledger["status"] == "halted_requires_recalibration"
    assert "latest observed monthly level is ambiguous" in ledger["initial_refusals"]


def test_opposite_raw_excursion_cannot_activate_as_inherited_old_state():
    history = [evidence(1), evidence(2), evidence(3, 0.)]
    ledger = freeze_candidate(history, eras.DEFAULT_CONFIG, version_id="v", cutoff_month="2020-03",
                              frozen_at=t("2020-04-01"), candidate_activation_at=t("2020-04-02"),
                              calibration_sha256=HASH, source_identity={"producer": HASH})
    assert ledger["reference_assignment"]["state"] == eras.PROXY_HIGH
    assert ledger["status"] == "halted_requires_recalibration"
    assert "latest monthly level contradicts inherited era state" in ledger["initial_refusals"]


def test_stale_evidence_counts_from_actual_month_not_later_empty_cutoff():
    ledger = freeze_candidate([evidence(1), evidence(2)], eras.DEFAULT_CONFIG, version_id="v",
                              cutoff_month="2020-03", frozen_at=t("2020-04-01"),
                              candidate_activation_at=t("2020-04-02"), calibration_sha256=HASH,
                              source_identity={"producer": HASH})
    assert ledger["status"] == "candidate_frozen"
    assert ledger["last_observed_month"] == "2020-02"
    result = evaluated(ledger, "late-acq", "2020-05-10", "2020-05-11")
    assert result["status"] == "halted_requires_recalibration"
    with pytest.raises(ValueError, match="follow the last observed cutoff"):
        append_monitor(ledger, evidence(3), detected_at=t("2020-04-02"))
