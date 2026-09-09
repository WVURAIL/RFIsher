"""Candidate eligibility is metadata-only and cannot manufacture confirmation."""

import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json

import pytest

from rfisher_results.validation.followup import (
    CALIBRATION_SCHEMA,
    ETA,
    ETA_DENOMINATOR,
    ETA_NUMERATOR,
    audit_candidate_cohort,
    seal_protocol,
    verify_protocol,
)

UTC = timezone.utc
FREEZE = datetime(2026, 9, 9, 12, tzinfo=UTC)
NOW = datetime(2027, 1, 1, tzinfo=UTC)


def canonical_digest(payload, field):
    content = {k: v for k, v in payload.items() if k != field}
    return hashlib.sha256(
        json.dumps(
            content,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
    ).hexdigest()


@pytest.fixture
def raw_protocol(tmp_path):
    evidence = tmp_path / "metadata.json"
    evidence.write_text('{"kind":"small trusted metadata manifest"}')
    return {
        "schema": "rfisher-coarse-followup-v1",
        "status": "candidate_frozen",
        "operational_acceptance": False,
        "scientific_certification": False,
        "frozen_at": FREEZE.isoformat(),
        "policy": {
            "kind": "coarse_exact_rational",
            "eta_numerator": ETA_NUMERATOR,
            "eta_denominator": ETA_DENOMINATOR,
            "eta": ETA,
        },
        "geometry": {"nsamples": 128, "ninputs": 2048},
        "development": {"excluded_event_ids": ["complete-old-event-001"]},
        "confirmation": {
            "start_rule": "first_utc_day_after_calibration_freeze",
            "duration_days": 730,
            "partition": "two_equal_calendar_halves",
            "calibration_artifact": None,
        },
        "source_artifacts": {
            str(evidence): {"sha256": hashlib.sha256(evidence.read_bytes()).hexdigest()}
        },
    }


def unit(event="new-acquisition-001", uid="new-unit-001", start=None, end=None):
    start = start or FREEZE + timedelta(days=3)
    return {
        "event": event,
        "unit_id": uid,
        "start": start,
        "end": end if end is not None else start + timedelta(hours=1),
    }


def calibration(protocol, **updates):
    result = {
        "schema": CALIBRATION_SCHEMA,
        "status": "calibration_frozen",
        "operational_acceptance": False,
        "scientific_certification": False,
        "protocol_sha256": protocol["protocol_sha256"],
        "frozen_at": (FREEZE + timedelta(days=1)).isoformat(),
        "policy": copy.deepcopy(protocol["policy"]),
        "geometry": copy.deepcopy(protocol["geometry"]),
        "method": "Content-bound calibration method description; quality not audited",
        "excluded_event_ids": ["complete-calibration-event-001"],
        "source_artifacts": copy.deepcopy(protocol["source_artifacts"]),
    }
    result.update(updates)
    result["calibration_sha256"] = canonical_digest(result, "calibration_sha256")
    return result


def test_seal_and_audit_leave_inputs_unchanged_and_never_certify(raw_protocol):
    before = copy.deepcopy(raw_protocol)
    protocol = seal_protocol(raw_protocol)
    assert raw_protocol == before and "protocol_sha256" not in raw_protocol
    assert verify_protocol(protocol)
    assert seal_protocol(protocol) == protocol
    candidates = [unit()]
    candidates_before = copy.deepcopy(candidates)
    sealed_before = copy.deepcopy(protocol)
    result = audit_candidate_cohort(protocol, candidates, now=NOW)
    assert protocol == sealed_before and candidates == candidates_before
    assert result["passes_candidate_metadata_checks"]
    assert not result["confirmation_metadata_ready"]
    assert not result["passes_confirmation_metadata_checks"]
    assert result["confirmation_interval"] is None
    assert result["operational_acceptance"] is False
    assert result["scientific_certification"] is False


def test_canonical_digest_is_order_independent(raw_protocol):
    a = seal_protocol(raw_protocol)
    b = seal_protocol(dict(reversed(list(raw_protocol.items()))))
    assert a["protocol_sha256"] == b["protocol_sha256"]
    assert a["protocol_sha256"] == canonical_digest(a, "protocol_sha256")


@pytest.mark.parametrize("changed", ["geometry", "excluded", "digest"])
def test_payload_tampering_cannot_be_verified_or_resealed(raw_protocol, changed):
    protocol = seal_protocol(raw_protocol)
    if changed == "geometry":
        protocol["geometry"]["ninputs"] = 1
    elif changed == "excluded":
        protocol["development"]["excluded_event_ids"].append("exposed-event")
    else:
        protocol["protocol_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        verify_protocol(protocol)
    with pytest.raises(ValueError):
        seal_protocol(protocol)


def test_artifact_tampering_refused(raw_protocol):
    protocol = seal_protocol(raw_protocol)
    from pathlib import Path

    Path(next(iter(protocol["source_artifacts"]))).write_text("changed metadata")
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_protocol(protocol)


@pytest.mark.parametrize("kind", ["rounded_eta", "q16", "wrong_kind"])
def test_resealed_rounded_or_q16_policy_is_refused(raw_protocol, kind):
    if kind == "rounded_eta":
        raw_protocol["policy"]["eta"] = round(ETA, 6)
    elif kind == "q16":
        numerator = round(ETA * 65536)
        raw_protocol["policy"].update(
            eta_numerator=numerator, eta_denominator=65536, eta=numerator / 65536
        )
    else:
        raw_protocol["policy"]["kind"] = "coarse_q16"
    with pytest.raises(ValueError):
        seal_protocol(raw_protocol)


@pytest.mark.parametrize(
    "field", ["scientific_certification", "operational_acceptance"]
)
def test_false_scientific_claim_contract(raw_protocol, field):
    raw_protocol[field] = True
    with pytest.raises(ValueError, match="must be false"):
        seal_protocol(raw_protocol)


@pytest.mark.parametrize(
    "value", ["2026-09-09T12:00:00", "2026-09-09", "2026-09-09T12:00:00+02:00"]
)
def test_candidate_freeze_must_be_aware_utc(raw_protocol, value):
    raw_protocol["frozen_at"] = value
    with pytest.raises(ValueError, match="ISO UTC"):
        seal_protocol(raw_protocol)


def test_all_121_already_exposed_additions_remain_excluded(raw_protocol):
    additions = [f"full-additional-acquisition-{i:04d}" for i in range(121)]
    raw_protocol["development"]["excluded_event_ids"].extend(additions)
    protocol = seal_protocol(raw_protocol)
    candidates = [
        unit(event=event, uid=f"relabeled-frequency-output-{i}")
        for i, event in enumerate(additions)
    ]
    result = audit_candidate_cohort(protocol, candidates, now=NOW)
    assert not result["passes_candidate_metadata_checks"]
    assert result["overlapping_event_ids"] == sorted(additions)
    assert result["acquisitions"] == 121


def test_relabeled_outputs_do_not_reset_acquisition_start(raw_protocol):
    protocol = seal_protocol(raw_protocol)
    start = FREEZE - timedelta(days=1)
    candidate = unit(
        event="new-label",
        uid="2029-new-filename",
        start=start,
        end=FREEZE + timedelta(hours=1),
    )
    result = audit_candidate_cohort(protocol, [candidate], now=NOW)
    assert not result["passes_candidate_metadata_checks"]
    assert result["pre_candidate_freeze_unit_ids"] == ["2029-new-filename"]


@pytest.mark.parametrize("field", ["start", "end"])
@pytest.mark.parametrize("value", [None, datetime(2026, 9, 12), "2026-09-12T00:00:00Z"])
def test_missing_naive_or_unparsed_unit_times_refused(raw_protocol, field, value):
    candidate = unit()
    candidate[field] = value
    result = audit_candidate_cohort(seal_protocol(raw_protocol), [candidate], now=NOW)
    assert not result["passes_candidate_metadata_checks"]


@pytest.mark.parametrize("delta", [timedelta(0), timedelta(seconds=-1)])
def test_zero_or_negative_duration_refused(raw_protocol, delta):
    candidate = unit()
    candidate["end"] = candidate["start"] + delta
    result = audit_candidate_cohort(seal_protocol(raw_protocol), [candidate], now=NOW)
    assert not result["passes_candidate_metadata_checks"]
    assert result["invalid_end_unit_ids"] == [candidate["unit_id"]]


def test_not_yet_ended_acquisition_refused(raw_protocol):
    candidate = unit(end=NOW + timedelta(seconds=1))
    result = audit_candidate_cohort(seal_protocol(raw_protocol), [candidate], now=NOW)
    assert not result["passes_candidate_metadata_checks"]
    assert result["not_yet_ended_unit_ids"] == [candidate["unit_id"]]


def test_same_event_frequency_shards_must_share_exact_bounds(raw_protocol):
    protocol = seal_protocol(raw_protocol)
    a, b = unit(uid="f1"), unit(uid="f2")
    assert audit_candidate_cohort(protocol, [a, b], now=NOW)[
        "passes_candidate_metadata_checks"
    ]
    b["end"] += timedelta(seconds=1)
    result = audit_candidate_cohort(protocol, [a, b], now=NOW)
    assert not result["passes_candidate_metadata_checks"]
    assert result["conflicting_event_ids"] == [a["event"]]


@pytest.mark.parametrize("bad", ["duplicate", "empty_identity", "missing_identity"])
def test_unit_identity_validation(raw_protocol, bad):
    a = unit()
    candidates = [a]
    if bad == "duplicate":
        candidates.append(copy.deepcopy(a))
    elif bad == "empty_identity":
        a["event"] = ""
    else:
        del a["event"]
    with pytest.raises(ValueError):
        audit_candidate_cohort(seal_protocol(raw_protocol), candidates, now=NOW)


def test_empty_candidates_cannot_pass(raw_protocol):
    result = audit_candidate_cohort(seal_protocol(raw_protocol), [], now=NOW)
    assert not result["passes_candidate_metadata_checks"]
    assert not result["passes_confirmation_metadata_checks"]


def test_audit_now_requires_timezone(raw_protocol):
    with pytest.raises(ValueError, match="timezone-aware"):
        audit_candidate_cohort(
            seal_protocol(raw_protocol), [unit()], now=datetime(2027, 1, 1)
        )


def test_valid_calibration_resolves_metadata_interval_not_certification(raw_protocol):
    protocol = seal_protocol(raw_protocol)
    bundle = calibration(protocol)
    before = copy.deepcopy(bundle)
    result = audit_candidate_cohort(protocol, [unit()], calibration=bundle, now=NOW)
    assert bundle == before
    assert (
        result["confirmation_metadata_ready"]
        and result["passes_confirmation_metadata_checks"]
    )
    span = result["confirmation_interval"]
    assert span["start_inclusive"] == "2026-09-11T00:00:00+00:00"
    assert datetime.fromisoformat(span["midpoint"]) - datetime.fromisoformat(
        span["start_inclusive"]
    ) == timedelta(days=365)
    assert datetime.fromisoformat(span["end_exclusive"]) - datetime.fromisoformat(
        span["start_inclusive"]
    ) == timedelta(days=730)
    assert (
        not result["scientific_certification"] and not result["operational_acceptance"]
    )


def test_calibration_exclusions_union_with_development(raw_protocol):
    protocol = seal_protocol(raw_protocol)
    bundle = calibration(protocol)
    candidates = [
        unit(event="complete-old-event-001", uid="old"),
        unit(event="complete-calibration-event-001", uid="calibration"),
    ]
    result = audit_candidate_cohort(protocol, candidates, calibration=bundle, now=NOW)
    assert result["excluded_event_count"] == 2
    assert result["overlapping_event_ids"] == [
        "complete-calibration-event-001",
        "complete-old-event-001",
    ]
    assert (
        not result["passes_candidate_metadata_checks"]
        and not result["passes_confirmation_metadata_checks"]
    )


@pytest.mark.parametrize(
    "change",
    [
        "before_candidate",
        "same_freeze",
        "future",
        "method",
        "policy",
        "geometry",
        "digest",
        "protocol",
        "accepted",
        "source_sha",
        "missing_source",
    ],
)
def test_invalid_calibration_never_unlocks_confirmation(raw_protocol, change):
    protocol = seal_protocol(raw_protocol)
    bundle = calibration(protocol)
    if change == "before_candidate":
        bundle["frozen_at"] = (FREEZE - timedelta(seconds=1)).isoformat()
    elif change == "same_freeze":
        bundle["frozen_at"] = FREEZE.isoformat()
    elif change == "future":
        bundle["frozen_at"] = (NOW + timedelta(seconds=1)).isoformat()
    elif change == "method":
        bundle["method"] = ""
    elif change == "policy":
        bundle["policy"]["eta"] = 1.0
    elif change == "geometry":
        bundle["geometry"]["ninputs"] = 1
    elif change == "protocol":
        bundle["protocol_sha256"] = "0" * 64
    elif change == "accepted":
        bundle["scientific_certification"] = True
    elif change == "source_sha":
        next(iter(bundle["source_artifacts"].values()))["sha256"] = "not-a-sha"
    elif change == "missing_source":
        bundle["source_artifacts"] = {}
    bundle["calibration_sha256"] = canonical_digest(bundle, "calibration_sha256")
    if change == "digest":
        bundle["calibration_sha256"] = "0" * 64
    result = audit_candidate_cohort(protocol, [unit()], calibration=bundle, now=NOW)
    assert result["passes_candidate_metadata_checks"]
    assert (
        not result["confirmation_metadata_ready"]
        and not result["passes_confirmation_metadata_checks"]
    )
    assert result["confirmation_interval"] is None
    assert any(
        "calibration bundle refused" in text for text in result["confirmation_reasons"]
    )


@pytest.mark.parametrize("boundary", ["starts_before", "ends_after", "inside_at_edges"])
def test_complete_confirmation_acquisition_bounds(raw_protocol, boundary):
    protocol = seal_protocol(raw_protocol)
    bundle = calibration(protocol)
    first = datetime(2026, 9, 11, tzinfo=UTC)
    midpoint = first + timedelta(days=365)
    last = first + timedelta(days=730)
    candidates = [
        unit(event="first-half", uid="first", start=first, end=midpoint),
        unit(event="second-half", uid="second", start=midpoint, end=last),
    ]
    if boundary == "starts_before":
        candidates[0]["start"] -= timedelta(seconds=1)
    elif boundary == "ends_after":
        candidates[1]["end"] += timedelta(seconds=1)
    result = audit_candidate_cohort(
        protocol, candidates, calibration=bundle, now=last + timedelta(days=1)
    )
    assert result["passes_candidate_metadata_checks"]
    assert result["confirmation_interval_complete"]
    assert result["passes_confirmation_metadata_checks"] == (
        boundary == "inside_at_edges"
    )
    assert result["final_evaluation_metadata_prerequisites_met"] == (
        boundary == "inside_at_edges"
    )


def test_calibration_midnight_still_starts_next_utc_day(raw_protocol):
    protocol = seal_protocol(raw_protocol)
    bundle = calibration(protocol, frozen_at="2026-09-10T00:00:00Z")
    result = audit_candidate_cohort(protocol, [unit()], calibration=bundle, now=NOW)
    assert (
        result["confirmation_interval"]["start_inclusive"]
        == "2026-09-11T00:00:00+00:00"
    )


@pytest.mark.parametrize("field", ["event", "unit_id"])
def test_whitespace_cannot_relabel_acquisition_identity(raw_protocol, field):
    candidate = unit(event="complete-old-event-001")
    candidate[field] += " "
    with pytest.raises(ValueError, match="canonical identities"):
        audit_candidate_cohort(seal_protocol(raw_protocol), [candidate], now=NOW)


def test_midpoint_straddling_whole_acquisition_is_not_split(raw_protocol):
    protocol = seal_protocol(raw_protocol)
    bundle = calibration(protocol)
    midpoint = datetime(2026, 9, 11, tzinfo=UTC) + timedelta(days=365)
    candidate = unit(
        start=midpoint - timedelta(seconds=1), end=midpoint + timedelta(seconds=1)
    )
    result = audit_candidate_cohort(
        protocol, [candidate], calibration=bundle, now=midpoint + timedelta(days=1)
    )
    assert result["passes_candidate_metadata_checks"]
    assert not result["passes_confirmation_metadata_checks"]
    assert result["midpoint_straddling_unit_ids"] == [candidate["unit_id"]]


def test_interim_metadata_pass_never_means_final_interval_is_ready(raw_protocol):
    protocol = seal_protocol(raw_protocol)
    bundle = calibration(protocol)
    result = audit_candidate_cohort(protocol, [unit()], calibration=bundle, now=NOW)
    assert result["passes_confirmation_metadata_checks"]
    assert not result["confirmation_interval_complete"]
    assert result["confirmation_stage"] == "interim_metadata_only"
    assert not result["final_evaluation_metadata_prerequisites_met"]
    assert (
        not result["scientific_certification"] and not result["operational_acceptance"]
    )


def test_dst_fold_negative_actual_duration_is_refused(raw_protocol):
    from zoneinfo import ZoneInfo

    local = ZoneInfo("America/Chicago")
    start = datetime(2026, 11, 1, 1, 10, tzinfo=local, fold=1)
    end = datetime(2026, 11, 1, 1, 20, tzinfo=local, fold=0)
    candidate = unit(start=start, end=end)
    result = audit_candidate_cohort(seal_protocol(raw_protocol), [candidate], now=NOW)
    assert not result["passes_candidate_metadata_checks"]
    assert result["invalid_end_unit_ids"] == [candidate["unit_id"]]
    assert candidate["start"] is start and candidate["end"] is end
    assert candidate["start"].fold == 1 and candidate["end"].fold == 0


def test_dst_fold_shards_with_different_actual_bounds_conflict(raw_protocol):
    from zoneinfo import ZoneInfo

    local = ZoneInfo("America/Chicago")
    candidates = [
        unit(
            uid=f"fold-{fold}",
            start=datetime(2026, 11, 1, 1, 10, tzinfo=local, fold=fold),
            end=datetime(2026, 11, 1, 1, 20, tzinfo=local, fold=fold),
        )
        for fold in [0, 1]
    ]
    result = audit_candidate_cohort(seal_protocol(raw_protocol), candidates, now=NOW)
    assert not result["passes_candidate_metadata_checks"]
    assert result["conflicting_event_ids"] == [candidates[0]["event"]]
    assert [c["start"].fold for c in candidates] == [0, 1]
