"""Offline candidate-era versions with an append-only decision history.

This helper freezes what was known and stops a candidate when its monitor
changes. It never accepts a calibration, starts a live policy, or establishes
that supplied source hashes, availability times or acquisition histories are
correct. Callers must independently qualify those inputs and use the cohort
checks in validation.holdout. The archived segmenter remains descriptive.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
import re

from rfisher_results.archive import blocks, eras

SCHEMA = "rfisher-offline-causal-era-v1"
MONITOR_VERSION = "conservative-monthly-monitor-v1"


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def _hash(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("source and calibration identities must be lowercase SHA256 digests")
    return value


def _name(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("identities must be nonempty strings")
    return value


def _time(value):
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("timestamps must be timezone-aware ISO datetimes") from exc
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def _month(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", value) is None:
        raise ValueError("month must be YYYY-MM")
    year, month = map(int, value.split("-"))
    if not 1 <= year <= 9998:
        raise ValueError("month year must lie in [1, 9998]")
    return year * 12 + month - 1


def _month_start(value):
    year, month = divmod(value, 12)
    return datetime(year, month + 1, 1, tzinfo=timezone.utc)


def month_evidence(record, *, available_at, source_sha256, availability_basis="recorded"):
    """Bind one completed UTC-month aggregate to its asserted availability.

    Use ``assumed_retrospective`` for a historical demonstration without actual
    ingestion records. Such timestamps cannot demonstrate prospective use.
    """
    if not isinstance(record, eras.MonthRecord):
        raise ValueError("record must be a MonthRecord")
    if isinstance(record.month, bool) or not isinstance(record.month, int):
        raise ValueError("record month must be an integer UTC month")
    _month(record.label)
    when = _time(available_at)
    if when < _month_start(record.month + 1):
        raise ValueError("monthly aggregate cannot be available before its UTC month is complete")
    if availability_basis not in ("recorded", "assumed_retrospective"):
        raise ValueError("availability basis must be recorded or assumed_retrospective")
    row = asdict(record)
    for key in ("level_db", "peak_offset_bins"):
        value = row[key]
        if not isinstance(value, (int, float)) or isinstance(value, bool) or math.isinf(value):
            raise ValueError("monthly features must be finite or unavailable")
        row[key] = None if math.isnan(value) else float(value)
    for key in ("input_maps", "software_tags"):
        if any(not isinstance(x, str) or not x.strip() for x in row[key]):
            raise ValueError("map/tag identities cannot be blank")
        row[key] = list(row[key])
    return {"record": row, "available_at": when.isoformat(),
            "source_sha256": _hash(source_sha256), "availability_basis": availability_basis}


def _records(history, config):
    records = []
    for item in history:
        values = dict(item["record"])
        for key in ("level_db", "peak_offset_bins"):
            values[key] = float("nan") if values[key] is None else values[key]
        for key in ("input_maps", "software_tags"):
            values[key] = tuple(values[key])
        record = eras.MonthRecord(**values)
        # Revalidate evidence loaded from JSON as well as freshly constructed rows.
        if month_evidence(record, available_at=item["available_at"],
                          source_sha256=item["source_sha256"],
                          availability_basis=item["availability_basis"]) != item:
            raise ValueError("monthly evidence is not canonical")
        counts = (record.frames, record.units, record.days, record.peak_frames)
        if any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in counts):
            raise ValueError("monthly support counts must be nonnegative integers")
        if any(v > record.frames for v in counts[1:]):
            raise ValueError("monthly support cannot exceed frame count")
        if record.populated != eras.is_populated(record, config):
            raise ValueError("monthly population flag disagrees with frozen configuration")
        records.append(record)
    if any(a.month >= b.month for a, b in zip(records, records[1:])):
        raise ValueError("monthly history must be strictly chronological without duplicates")
    return tuple(records)


def _assignments(seg):
    rows = {blocks.month_label(m): {"state": e.state, "era_start": e.first_label,
                                  "opening_evidence": e.evidence}
            for e in seg.eras for m in e.months}
    rows.update({blocks.month_label(m): {"state": eras.ZONE, "era_start": None,
                                       "opening_evidence": ""} for m in seg.zone_months})
    return rows


def _boundary_keys(seg):
    return {(b.kind, b.old_last, b.new_first) for b in seg.boundaries}


def _seal(ledger):
    ledger.pop("ledger_sha256", None)
    ledger["ledger_sha256"] = _digest(ledger)
    return ledger


def verify_ledger(ledger):
    """Check serialized integrity; a checksum cannot establish source truth."""
    if not isinstance(ledger, dict) or ledger.get("schema") != SCHEMA:
        raise ValueError("unrecognized causal era ledger")
    payload = {k: v for k, v in ledger.items() if k != "ledger_sha256"}
    if _digest(payload) != ledger.get("ledger_sha256"):
        raise ValueError("causal era ledger digest mismatch")
    config = eras.EraConfig(**ledger["config"])
    if config.digest != ledger["config_digest"]:
        raise ValueError("era configuration digest mismatch")
    if ledger["monitor_version"] != MONITOR_VERSION:
        raise ValueError("unrecognized monitor version")
    _records(ledger["monthly_history"], config)


def freeze_candidate(history, config, *, version_id, cutoff_month, frozen_at,
                     candidate_activation_at, calibration_sha256, source_identity, previous=None):
    """Freeze an offline era candidate, never an accepted operational policy.

    The activation date is the earliest proposed evaluation start. It must be
    after the freeze; operational activation always remains unset. A successor
    requires a halted parent and a different externally supplied calibration
    artifact identity. That identity is not proof of calibration quality.
    """
    cutoff = _month(cutoff_month)
    frozen = _time(frozen_at)
    activation = _time(candidate_activation_at)
    if frozen < _month_start(cutoff + 1):
        raise ValueError("freeze cutoff must be a completed UTC month")
    if activation <= frozen:
        raise ValueError("candidate activation must follow the freeze")
    history = deepcopy(list(history))
    records = _records(history, config)
    if not records or records[-1].month > cutoff:
        raise ValueError("freeze needs a nonempty history entirely at or before its cutoff")
    if any(_time(e["available_at"]) > frozen for e in history):
        raise ValueError("freeze cannot use evidence unavailable at the freeze time")
    if not isinstance(source_identity, dict) or not source_identity:
        raise ValueError("source identity must bind at least one producing source")
    sources = {_name(k): _hash(v) for k, v in sorted(source_identity.items())}
    _name(version_id)
    _hash(calibration_sha256)
    predecessor = None
    excluded = []
    if previous is not None:
        verify_ledger(previous)
        if previous["status"] != "halted_requires_recalibration":
            raise ValueError("a successor requires a halted parent")
        if version_id == previous["version_id"] or calibration_sha256 == previous["calibration_sha256"]:
            raise ValueError("a successor requires new version and calibration identities")
        if frozen <= _time(previous["last_event_at"]) or activation <= _time(previous["last_event_at"]):
            raise ValueError("a successor must be frozen after its parent's complete decision history")
        if cutoff < max(_month(previous["last_observed_month"]), _month(previous["cutoff_month"])):
            raise ValueError("a successor cannot rewind its parent's observed months")
        # Previously observed monthly features cannot be replaced silently.
        by_month = {e["record"]["month"]: e for e in history}
        if any(by_month.get(e["record"]["month"]) != e for e in previous["monthly_history"]):
            raise ValueError("a successor must preserve all parent monthly evidence")
        predecessor = previous["ledger_sha256"]
        excluded = sorted(set(previous["excluded_acquisitions"]) |
                          {e["acquisition_id"] for e in previous["evaluations"]})
    seg = eras.segment(records, config, station_record={})
    assigned = _assignments(seg)
    reference = assigned.get(records[-1].label)
    reasons = []
    if reference is None or reference["state"] not in (eras.PROXY_HIGH, eras.PROXY_LOW):
        reasons.append("latest observed month has no definite era assignment")
    latest_raw = eras.state_of(records[-1].level_db, config)
    if latest_raw == eras.AMBIGUOUS:
        reasons.append("latest observed monthly level is ambiguous")
    elif reference is not None and latest_raw != reference["state"]:
        reasons.append("latest monthly level contradicts inherited era state")
    if not records[-1].input_maps:
        reasons.append("latest observed input-map identity unavailable")
    if cutoff - records[-1].month > config.stale_grace_months:
        reasons.append("latest monthly evidence is stale at freeze cutoff")
    return _seal({
        "schema": SCHEMA, "version_id": version_id, "source_identity": sources,
        "config": asdict(config), "config_digest": config.digest,
        "monitor_version": MONITOR_VERSION, "calibration_sha256": calibration_sha256,
        "cutoff_month": cutoff_month, "frozen_at": frozen.isoformat(),
        "candidate_activation_at": activation.isoformat(), "policy_activation_at": None,
        "parent_ledger_sha256": predecessor, "previous_ledger_sha256": None,
        "status": "halted_requires_recalibration" if reasons else "candidate_frozen",
        "initial_refusals": reasons, "halted_at": frozen.isoformat() if reasons else None,
        "frozen_assignments": assigned, "reference_assignment": reference,
        "monthly_history": history, "monitor_decisions": [], "evaluations": [],
        "excluded_acquisitions": excluded, "last_observed_month": records[-1].label,
        "last_event_at": frozen.isoformat(), "scientific_certification": False,
        "operational_acceptance": False,
        "availability_scope": "assumed_retrospective" if any(
            e["availability_basis"] != "recorded" for e in history) else "asserted_recorded",
    })


def append_monitor(ledger, evidence, *, detected_at):
    """Append one later observed month; any stop is latched until a new version.

    Stops include missing support/maps, missing-month gaps beyond the frozen
    grace, changed input maps, ambiguous/opposite raw level, a new boundary,
    or disagreement with a frozen historical assignment. Diagnostic onset
    labels are not independently verified physical transition dates.
    """
    verify_ledger(ledger)
    detected = _time(detected_at)
    if detected < _time(ledger["last_event_at"]):
        raise ValueError("decision timestamps cannot go backwards")
    config = eras.EraConfig(**ledger["config"])
    evidence = deepcopy(evidence)
    history = ledger["monthly_history"] + [evidence]
    records = _records(history, config)
    record = records[-1]
    if record.month <= max(_month(ledger["last_observed_month"]), _month(ledger["cutoff_month"])):
        raise ValueError("monitor month must follow the last observed cutoff")
    if _time(evidence["available_at"]) > detected:
        raise ValueError("monitor cannot use evidence before its availability")
    before = eras.segment(records[:-1], config, station_record={})
    after = eras.segment(records, config, station_record={})
    current = _assignments(after)
    commitments = dict(ledger["frozen_assignments"])
    commitments.update({d["observed_month"]: d["as_known_assignment"]
                        for d in ledger["monitor_decisions"]})
    changed = [{"month": m, "committed": a, "new_diagnostic": current.get(m)}
               for m, a in sorted(commitments.items()) if current.get(m) != a]
    new_boundaries = sorted(_boundary_keys(after) - _boundary_keys(before))
    reasons = []
    if not record.populated:
        reasons.append("monthly support insufficient")
    if not record.input_maps:
        reasons.append("input-map identity unavailable")
    elif set(record.input_maps) != set(records[-2].input_maps):
        reasons.append("input-map identity changed")
    if record.month - records[-2].month - 1 > config.stale_grace_months:
        reasons.append("unobserved calendar gap exceeds frozen grace")
    raw = eras.state_of(record.level_db, config)
    reference = ledger["reference_assignment"]
    if raw == eras.AMBIGUOUS:
        reasons.append("monthly level ambiguous")
    elif reference is None or raw != reference["state"]:
        reasons.append("monthly level differs from frozen era state")
    if new_boundaries:
        reasons.append("segmenter detects a new boundary")
    if changed:
        reasons.append("later data disagree with committed historical assignments")
    candidate_months = [b[2] for b in new_boundaries] + [_month(r["month"]) for r in changed]
    if reasons and not candidate_months:
        candidate_months = [record.month]
    result = deepcopy(ledger)
    result["previous_ledger_sha256"] = ledger["ledger_sha256"]
    if reasons and result["halted_at"] is None:
        result["status"] = "halted_requires_recalibration"
        result["halted_at"] = detected.isoformat()
    result["monitor_decisions"].append({
        "observed_month": record.label, "available_at": evidence["available_at"],
        "detected_at": detected.isoformat(), "status_before": ledger["status"],
        "status_after": result["status"], "reasons": reasons,
        "inferred_onset_month": blocks.month_label(min(candidate_months)) if candidate_months else None,
        "candidate_activation_at": ledger["candidate_activation_at"], "policy_activation_at": None,
        "as_known_assignment": current.get(record.label), "revised_prior_assignments": changed,
        "new_boundaries": [{"kind": kind, "old_last": blocks.month_label(old),
                            "new_first": blocks.month_label(new)} for kind, old, new in new_boundaries],
        "evidence_sha256": _digest(evidence),
    })
    result["monthly_history"] = history
    result["last_observed_month"] = record.label
    result["last_event_at"] = detected.isoformat()
    if evidence["availability_basis"] != "recorded":
        result["availability_scope"] = "assumed_retrospective"
    return _seal(result)


def record_evaluation(ledger, *, acquisition_id, start, end, recorded_at, source_sha256):
    """Record an acquisition's assignment using only the current candidate version.

    No score is fitted or policy accepted here. Halted attempts are retained as
    refusals. A separate cohort audit must establish development exclusion and
    group all frequency shards of an acquisition before this call.
    """
    verify_ledger(ledger)
    _name(acquisition_id)
    start, end, recorded = _time(start), _time(end), _time(recorded_at)
    if end <= start or recorded < end or recorded < _time(ledger["last_event_at"]):
        raise ValueError("acquisition and decision timestamps must be chronological")
    if start <= _time(ledger["frozen_at"]) or start < _time(ledger["candidate_activation_at"]):
        raise ValueError("evaluation acquisition must follow the freeze and candidate activation")
    if acquisition_id in ledger["excluded_acquisitions"] or any(
            r["acquisition_id"] == acquisition_id for r in ledger["evaluations"]):
        raise ValueError("acquisition identity already used by this version or its ancestors")
    result = deepcopy(ledger)
    result["previous_ledger_sha256"] = ledger["ledger_sha256"]
    config = eras.EraConfig(**ledger["config"])
    decision_month = recorded.year * 12 + recorded.month - 1
    reasons = []
    if decision_month - _month(ledger["last_observed_month"]) - 1 > config.stale_grace_months:
        reasons.append("monthly evidence stale at evaluation decision")
        if result["halted_at"] is None:
            result["status"] = "halted_requires_recalibration"
            result["halted_at"] = recorded.isoformat()
    if ledger["halted_at"]:
        reasons.append("candidate already halted")
    result["evaluations"].append({
        "acquisition_id": acquisition_id, "start": start.isoformat(), "end": end.isoformat(),
        "recorded_at": recorded.isoformat(), "source_sha256": _hash(source_sha256),
        "version_id": ledger["version_id"], "calibration_sha256": ledger["calibration_sha256"],
        "assignment": deepcopy(ledger["reference_assignment"]),
        "disposition": "refused_after_halt" if result["halted_at"] else "offline_candidate_recorded",
        "refusal_reasons": reasons, "status_before": ledger["status"], "status_after": result["status"],
        "operational_acceptance": False,
    })
    result["last_event_at"] = recorded.isoformat()
    return _seal(result)
