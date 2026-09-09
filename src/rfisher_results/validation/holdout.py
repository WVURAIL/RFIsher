"""Acquisition-level checks for a future validation cohort.

Passing these checks establishes neither blindness nor scientific calibration.
Those require a reviewed acquisition history and an accepted frozen policy.
"""
from __future__ import annotations

from datetime import datetime


def audit_future_cohort(development_event_ids, units, *, frozen_at: datetime | None):
    """Group all frequencies of an event together and reject reused acquisitions.

    Each unit supplies `event`, `unit_id`, and timezone-aware `start`. No date
    is guessed from a file name or a date-only archive field.
    """
    if frozen_at is not None and (not isinstance(frozen_at, datetime) or frozen_at.utcoffset() is None):
        raise ValueError("policy freeze time must be timezone-aware")
    development = set(development_event_ids)
    if any(not isinstance(x, str) or not x.strip() for x in development):
        raise ValueError("development event IDs must be nonempty strings")
    reasons = []
    if frozen_at is None:
        reasons.append("accepted policy and calibration have not been frozen")
    events, unit_ids, missing_times, too_early = set(), set(), [], []
    for unit in units:
        event, unit_id = unit["event"], unit["unit_id"]
        if not isinstance(event, str) or not event.strip() or not isinstance(unit_id, str) or not unit_id.strip():
            raise ValueError("event and unit identities must be nonempty strings")
        if unit_id in unit_ids:
            raise ValueError("duplicate candidate unit")
        unit_ids.add(unit_id)
        events.add(event)
        start = unit.get("start")
        if not isinstance(start, datetime) or start.utcoffset() is None:
            missing_times.append(unit_id)
        elif frozen_at is not None and start <= frozen_at:
            too_early.append(unit_id)
    overlap = sorted(events & development)
    if not units or not unit_ids:
        reasons.append("no candidate units")
    if overlap:
        reasons.append("candidate acquisitions overlap development data")
    if missing_times:
        reasons.append("candidate acquisition timestamps unavailable or not timezone-aware")
    if too_early:
        reasons.append("candidate acquisitions do not follow the policy freeze")
    return {"passes_cohort_checks": not reasons, "reasons": reasons,
            "units": len(unit_ids), "acquisitions": len(events),
            "overlapping_event_ids": overlap, "missing_time_unit_ids": sorted(missing_times),
            "pre_freeze_unit_ids": sorted(too_early),
            "scientific_certification": False}
