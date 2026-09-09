"""Integrity and metadata checks for the frozen channel-29 coarse candidate.

These checks establish neither physical calibration quality nor scientific
acceptance. Times and complete acquisition identities must come from trusted
metadata supplied by the caller; filenames and score values are never used.
"""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re

from .holdout import audit_future_cohort

SCHEMA = "rfisher-coarse-followup-v1"
CALIBRATION_SCHEMA = "rfisher-coarse-calibration-v1"
ETA_NUMERATOR = 4508969069674235
ETA_DENOMINATOR = 4503599627370496
ETA = ETA_NUMERATOR / ETA_DENOMINATOR
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _canonical(value):
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("payload must contain finite JSON values") from exc


def _digest(payload, field):
    return hashlib.sha256(
        _canonical({k: v for k, v in payload.items() if k != field})
    ).hexdigest()


def _ids(value, label):
    if not isinstance(value, list) or any(
        not isinstance(x, str) or not x.strip() or x != x.strip() for x in value
    ):
        raise ValueError(f"{label} must be a list of complete nonempty event IDs")
    if len(set(value)) != len(value):
        raise ValueError(f"{label} contains duplicate event IDs")
    return set(value)


def _aware(value):
    return isinstance(value, datetime) and value.utcoffset() is not None


def _utc_iso(value, label):
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an aware ISO UTC timestamp")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an aware ISO UTC timestamp") from exc
    if not _aware(result) or result.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be an aware ISO UTC timestamp")
    return result.astimezone(timezone.utc)


def _false_claims(payload):
    for key in ("scientific_certification", "operational_acceptance"):
        if payload.get(key) is not False:
            raise ValueError(f"{key} must be false")


def _source_artifacts(value):
    if not isinstance(value, dict) or not value:
        raise ValueError("source_artifacts must bind at least one source file")
    for name, identity in value.items():
        if (
            not isinstance(name, str)
            or not name.strip()
            or not isinstance(identity, dict)
        ):
            raise ValueError("source artifact paths and identities are invalid")
        wanted = identity.get("sha256")
        if not isinstance(wanted, str) or _SHA256.fullmatch(wanted) is None:
            raise ValueError("source artifact SHA256 is invalid")
        path = Path(name)
        if not path.is_absolute() or not path.is_file():
            raise ValueError(
                f"source artifact must be an existing absolute file: {name}"
            )
        digest = hashlib.sha256()
        try:
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError as exc:
            raise ValueError(f"source artifact cannot be read: {name}") from exc
        if digest.hexdigest() != wanted:
            raise ValueError(f"source artifact hash mismatch: {name}")


def _validate_protocol(protocol):
    if not isinstance(protocol, dict) or protocol.get("schema") != SCHEMA:
        raise ValueError("unsupported candidate protocol schema")
    if protocol.get("status") != "candidate_frozen":
        raise ValueError("candidate status must be candidate_frozen")
    _false_claims(protocol)
    _utc_iso(protocol.get("frozen_at"), "candidate frozen_at")
    policy = protocol.get("policy")
    if not isinstance(policy, dict) or policy.get("kind") != "coarse_exact_rational":
        raise ValueError("policy must use the exact coarse rational comparison")
    for key, wanted in (
        ("eta_numerator", ETA_NUMERATOR),
        ("eta_denominator", ETA_DENOMINATOR),
    ):
        if type(policy.get(key)) is not int or policy[key] != wanted:
            raise ValueError(
                "v1 requires the declared exact candidate rational, not a rounded or Q16 threshold"
            )
    if type(policy.get("eta")) is not float or policy["eta"] != ETA:
        raise ValueError("eta must exactly represent the declared candidate rational")
    geometry = protocol.get("geometry")
    if not isinstance(geometry, dict) or not geometry:
        raise ValueError("geometry must be a nonempty content-bound object")
    development = protocol.get("development")
    if not isinstance(development, dict):
        raise ValueError("development exclusions are required")
    if not _ids(development.get("excluded_event_ids"), "development exclusions"):
        raise ValueError("development exclusions must not be empty")
    confirmation = protocol.get("confirmation")
    if not isinstance(confirmation, dict):
        raise ValueError("confirmation contract is required")
    if (
        confirmation.get("start_rule") != "first_utc_day_after_calibration_freeze"
        or type(confirmation.get("duration_days")) is not int
        or confirmation["duration_days"] != 730
        or confirmation.get("partition") != "two_equal_calendar_halves"
        or confirmation.get("calibration_artifact", "missing") is not None
    ):
        raise ValueError(
            "confirmation must retain the pending next-UTC-day, 730-day, two-half contract"
        )
    _canonical(protocol)
    _source_artifacts(protocol.get("source_artifacts"))


def seal_protocol(protocol):
    """Validate and return a new sealed payload, leaving the input unchanged.

    If a digest already exists, it must verify; sealing cannot silently bless a
    modified existing protocol. Small source/manifest files are authenticated,
    not the large telescope products whose identities those manifests record.
    """
    if isinstance(protocol, dict) and "protocol_sha256" in protocol:
        verify_protocol(protocol)
        return copy.deepcopy(protocol)
    _validate_protocol(protocol)
    result = copy.deepcopy(protocol)
    result["protocol_sha256"] = _digest(result, "protocol_sha256")
    return result


def verify_protocol(protocol):
    """Raise ValueError on contract, payload or source tampering; return True."""
    _validate_protocol(protocol)
    claimed = protocol.get("protocol_sha256")
    if not isinstance(claimed, str) or _SHA256.fullmatch(claimed) is None:
        raise ValueError("candidate protocol SHA256 is invalid")
    if claimed != _digest(protocol, "protocol_sha256"):
        raise ValueError("candidate protocol digest mismatch")
    return True


def _validate_calibration(calibration, protocol, now):
    if (
        not isinstance(calibration, dict)
        or calibration.get("schema") != CALIBRATION_SCHEMA
    ):
        raise ValueError("unsupported calibration bundle schema")
    if calibration.get("status") != "calibration_frozen":
        raise ValueError("calibration status must be calibration_frozen")
    _false_claims(calibration)
    if calibration.get("protocol_sha256") != protocol["protocol_sha256"]:
        raise ValueError("calibration does not bind this candidate protocol")
    for field in ("policy", "geometry"):
        if _canonical(calibration.get(field)) != _canonical(protocol[field]):
            raise ValueError(f"calibration {field} differs from the candidate protocol")
    method = calibration.get("method")
    if not isinstance(method, str) or not method.strip():
        raise ValueError("calibration method must be explicitly identified")
    excluded = _ids(calibration.get("excluded_event_ids"), "calibration exclusions")
    frozen = _utc_iso(calibration.get("frozen_at"), "calibration frozen_at")
    if frozen <= _utc_iso(protocol["frozen_at"], "candidate frozen_at"):
        raise ValueError("calibration must be frozen strictly after the candidate")
    if frozen > now:
        raise ValueError("calibration freeze is after the audit time")
    claimed = calibration.get("calibration_sha256")
    if not isinstance(claimed, str) or _SHA256.fullmatch(claimed) is None:
        raise ValueError("calibration SHA256 is invalid")
    if claimed != _digest(calibration, "calibration_sha256"):
        raise ValueError("calibration digest mismatch")
    _source_artifacts(calibration.get("source_artifacts"))
    return frozen, excluded


def audit_candidate_cohort(protocol, units, *, calibration=None, now=None):
    """Audit supplied acquisition metadata without scores or scientific decisions.

    Candidate metadata can pass while confirmation remains pending. A valid
    calibration bundle resolves only the confirmation metadata prerequisites;
    hashing a method description does not qualify its physical calibration.
    All frequency shards of one event must report identical acquisition bounds.
    No inference about missing times or actual observation identity is possible.
    """
    verify_protocol(protocol)
    if now is None:
        now = datetime.now(timezone.utc)
    if not _aware(now):
        raise ValueError("audit now must be timezone-aware")
    now = now.astimezone(timezone.utc)
    candidate_freeze = _utc_iso(protocol["frozen_at"], "candidate frozen_at")
    units = list(units)
    if any(
        not isinstance(unit, dict) or "event" not in unit or "unit_id" not in unit
        for unit in units
    ):
        raise ValueError("candidate units require complete event and unit identities")
    if any(
        not isinstance(unit[key], str)
        or not unit[key].strip()
        or unit[key] != unit[key].strip()
        for unit in units
        for key in ("event", "unit_id")
    ):
        raise ValueError(
            "candidate units require complete nonempty canonical identities"
        )
    # Python compares two datetimes sharing a ZoneInfo by wall time, which
    # can ignore distinct DST folds. Normalize copied metadata to actual UTC
    # instants before durations, interval membership, or shard equality.
    units = [dict(unit) for unit in units]
    for unit in units:
        for field in ("start", "end"):
            if _aware(unit.get(field)):
                unit[field] = unit[field].astimezone(timezone.utc)
    excluded = set(protocol["development"]["excluded_event_ids"])
    calibration_reasons = []
    calibration_freeze = None
    calibration_exclusions = set()
    if calibration is None:
        calibration_reasons.append(
            "a separately content-bound calibration bundle is pending"
        )
    else:
        try:
            calibration_freeze, calibration_exclusions = _validate_calibration(
                calibration, protocol, now
            )
        except ValueError as exc:
            calibration_reasons.append(f"calibration bundle refused: {exc}")
    excluded.update(calibration_exclusions)
    base = audit_future_cohort(excluded, units, frozen_at=candidate_freeze)
    reasons = list(base["reasons"])
    missing_ends, invalid_ends, future_units = [], [], []
    intervals = {}
    if candidate_freeze > now:
        reasons.append("candidate freeze is after the audit time")
    for unit in units:
        start, end = unit.get("start"), unit.get("end")
        uid = unit["unit_id"]
        if not _aware(end):
            missing_ends.append(uid)
        elif end > now:
            future_units.append(uid)
        if _aware(start) and _aware(end):
            if end <= start:
                invalid_ends.append(uid)
            intervals.setdefault(unit["event"], set()).add((start, end))
    conflicts = sorted(event for event, spans in intervals.items() if len(spans) > 1)
    if missing_ends:
        reasons.append(
            "complete timezone-aware acquisition end timestamps are required"
        )
    if invalid_ends:
        reasons.append("acquisition end must be strictly later than start")
    if future_units:
        reasons.append("candidate acquisitions must have ended by the audit time")
    if conflicts:
        reasons.append(
            "frequency shards of the same event report conflicting acquisition intervals"
        )
    interval = None
    outside = []
    straddling = []
    interval_complete = False
    confirmation_reasons = list(calibration_reasons)
    if calibration_freeze is not None:
        first = (calibration_freeze + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        midpoint = first + timedelta(days=365)
        end = first + timedelta(days=730)
        interval_complete = now >= end
        interval = {
            "start_inclusive": first.isoformat(),
            "midpoint": midpoint.isoformat(),
            "end_exclusive": end.isoformat(),
            "duration_days": 730,
            "half_duration_days": 365,
            "support_opportunity_only": "Each half allows at least 270 days and six months; actual support is not evaluated",
        }
        for unit in units:
            start, stop = unit.get("start"), unit.get("end")
            if _aware(start) and _aware(stop) and not (first <= start < stop <= end):
                outside.append(unit["unit_id"])
            if _aware(start) and _aware(stop) and start < midpoint < stop:
                straddling.append(unit["unit_id"])
        confirmation_base = audit_future_cohort(
            excluded, units, frozen_at=calibration_freeze
        )
        confirmation_reasons.extend(confirmation_base["reasons"])
        if outside:
            confirmation_reasons.append(
                "complete acquisitions must lie inside the resolved confirmation interval"
            )
        if straddling:
            confirmation_reasons.append(
                "whole acquisitions must not straddle the confirmation midpoint"
            )
    confirmation_reasons.extend(reasons)
    confirmation_reasons = list(dict.fromkeys(confirmation_reasons))
    return {
        "schema": "rfisher-coarse-followup-audit-v1",
        "protocol_sha256": protocol["protocol_sha256"],
        "audited_at": now.isoformat(),
        "passes_candidate_metadata_checks": not reasons,
        "candidate_reasons": reasons,
        "confirmation_metadata_ready": calibration_freeze is not None,
        "passes_confirmation_metadata_checks": calibration_freeze is not None
        and not confirmation_reasons,
        "confirmation_reasons": confirmation_reasons,
        "confirmation_interval": interval,
        "confirmation_interval_complete": interval_complete,
        "confirmation_stage": (
            "pending_calibration"
            if calibration_freeze is None
            else "interval_complete_metadata_only"
            if interval_complete
            else "interim_metadata_only"
        ),
        "final_evaluation_metadata_prerequisites_met": (
            interval_complete
            and calibration_freeze is not None
            and not confirmation_reasons
        ),
        "units": base["units"],
        "acquisitions": base["acquisitions"],
        "excluded_event_count": len(excluded),
        "calibration_excluded_event_count": len(calibration_exclusions),
        "overlapping_event_ids": base["overlapping_event_ids"],
        "missing_start_unit_ids": base["missing_time_unit_ids"],
        "missing_end_unit_ids": sorted(missing_ends),
        "invalid_end_unit_ids": sorted(invalid_ends),
        "not_yet_ended_unit_ids": sorted(future_units),
        "pre_candidate_freeze_unit_ids": base["pre_freeze_unit_ids"],
        "conflicting_event_ids": conflicts,
        "outside_confirmation_interval_unit_ids": sorted(outside),
        "midpoint_straddling_unit_ids": sorted(straddling),
        "operational_acceptance": False,
        "scientific_certification": False,
        "scope": "Identity and timing metadata only; no support, scores, physical calibration quality or scientific acceptance evaluated",
    }
