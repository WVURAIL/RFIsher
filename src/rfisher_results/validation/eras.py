"""Quantify hindsight in the archived monthly era rule using prefix replays.

This is a retrospective sensitivity audit, not a new era classifier or a
prospective validation. Each replay only sees months available at its cutoff.
The fixed rule can revise old assignments when later evidence arrives.
"""
from __future__ import annotations

import re
from typing import Mapping, Sequence

from rfisher_results.archive import blocks, eras


def _month(value: str) -> int:
    if not isinstance(value, str) or re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", value) is None:
        raise ValueError("month must be YYYY-MM")
    year, month = map(int, value.split("-"))
    return year * 12 + month - 1


def monthly_records_from_document(document: Mapping) -> tuple[eras.EraConfig, tuple[eras.MonthRecord, ...]]:
    """Read the recorded, month-local inputs and verify the policy digest.

    The archive JSON stores only software-tag counts, not tag identities.
    They are omitted here because segment() does not use software tags;
    the actual input-map identities that determine instrument changes remain.
    Fitted anchors, residuals, and final state labels are never replay inputs.
    """
    config = eras.EraConfig(**document["config"])
    if config.digest != document["config_digest"]:
        raise ValueError("era configuration digest mismatch")
    records = []
    for row in document["months"]:
        records.append(eras.MonthRecord(
            month=_month(row["month"]), frames=row["frames"], units=row["units"], days=row["days"],
            populated=row["populated"], level_db=float("nan") if row["level_db"] is None else row["level_db"],
            state=row["state"], peak_offset_bins=(float("nan") if row["peak_offset_bins"] is None
                                                  else row["peak_offset_bins"]),
            peak_cohort=row["peak_cohort"], peak_frames=row["peak_frames"],
            input_maps=tuple(row["input_maps"]), software_tags=(),
        ))
    return config, tuple(records)


def _assignments(seg: eras.Segmentation) -> dict:
    # Extending an era's last month is expected, so exclude that coordinate.
    assigned = {m: (e.state, e.first_month, e.evidence) for e in seg.eras for m in e.months}
    assigned.update({m: (eras.ZONE, None, "") for m in seg.zone_months})
    return assigned


def _assignment_row(value):
    if value is None:
        return None
    state, start, evidence = value
    return {"state": state, "era_start": blocks.month_label(start) if start is not None else None,
            "opening_evidence": evidence}


def _boundary_key(boundary):
    return boundary.kind, boundary.old_last, boundary.new_first


def audit_era_prefixes(records: Sequence[eras.MonthRecord], config: eras.EraConfig) -> dict:
    """Replay every recorded month and count revisions of earlier assignments.

    The same month-local features and fixed policy are reused in all prefixes.
    Month order must be strict. No station record is supplied: independent
    administrative or operational events need their own reviewed timing model.
    Boundary detection times are retrospective summaries against the final
    segmentation, not forward-looking certifications of a stable boundary.
    """
    records = tuple(records)
    if any(a.month >= b.month for a, b in zip(records, records[1:])):
        raise ValueError("records must have unique months in chronological order")
    for record in records:
        if any(isinstance(x, bool) or not isinstance(x, int) or x < 0
               for x in (record.frames, record.units, record.days, record.peak_frames)):
            raise ValueError("monthly support counts must be nonnegative integers")
        if record.populated != eras.is_populated(record, config):
            raise ValueError("record population flag disagrees with the era configuration")
    previous = {}
    revisions = []
    snapshots = []
    seen_boundaries = []
    final = eras.segment((), config, station_record={})
    for index, record in enumerate(records):
        final = eras.segment(records[:index + 1], config, station_record={})
        current = _assignments(final)
        changed = [month for month in previous if previous[month] != current.get(month)]
        for month in sorted(changed):
            revisions.append({
                "as_of": record.label, "revised_month": blocks.month_label(month),
                "age_calendar_months": record.month - month,
                "age_populated_months": sum(r.populated for r in records[:index + 1]
                                              if month < r.month <= record.month),
                "before": _assignment_row(previous[month]), "after": _assignment_row(current.get(month)),
            })
        latest = final.eras[-1] if final.eras else None
        snapshots.append({
            "as_of": record.label, "populated_months": len(final.populated), "eras": len(final.eras),
            "latest_era_start": latest.first_label if latest else None,
            "latest_era_last": latest.last_label if latest else None,
            "latest_state": latest.state if latest else None,
            "previous_assignments_revised": len(changed),
        })
        seen_boundaries.append((record.month, {_boundary_key(b) for b in final.boundaries}))
        previous = current
    boundary_rows = []
    for boundary in final.boundaries:
        key = _boundary_key(boundary)
        seen = [month for month, keys in seen_boundaries if key in keys]
        last_missing = max((month for month, keys in seen_boundaries
                            if month >= boundary.new_first and key not in keys),
                           default=boundary.new_first - 1)
        stable_seen = min(month for month in seen if month > last_missing)
        boundary_rows.append({
            "kind": boundary.kind, "old_last": blocks.month_label(boundary.old_last),
            "new_first": blocks.month_label(boundary.new_first),
            "first_seen": blocks.month_label(min(seen)),
            "first_seen_lag_months": min(seen) - boundary.new_first,
            "stable_seen": blocks.month_label(stable_seen),
            "stable_seen_lag_months": stable_seen - boundary.new_first,
        })
    return {
        "status": "retrospective prefix sensitivity audit", "scientific_certification": False,
        "independent_station_records_used": False, "config_digest": config.digest,
        "months": len(records), "populated_months": len(final.populated), "final_eras": len(final.eras),
        "revision_events": len(revisions),
        "distinct_revised_months": len({r["revised_month"] for r in revisions}),
        "max_revision_age_months": max((r["age_calendar_months"] for r in revisions), default=0),
        "revisions_older_than_two_populated_months": sum(r["age_populated_months"] > 2 for r in revisions),
        "final_boundaries": len(final.boundaries),
        "max_final_boundary_stable_lag_months": max((b["stable_seen_lag_months"] for b in boundary_rows), default=0),
        "snapshots": snapshots, "revisions": revisions, "boundaries": boundary_rows,
    }


def audit_era_document(document: Mapping) -> dict:
    """Replay an era JSON only if its full segmentation can be reproduced."""
    config, records = monthly_records_from_document(document)
    result = audit_era_prefixes(records, config)
    seg = eras.segment(records, config, station_record={})
    actual = [(e.first_label, e.last_label, e.state, e.evidence, list(map(blocks.month_label, e.months)))
              for e in seg.eras]
    expected = [(e["first_month"], e["last_month"], e["state"], e["evidence"], e["months"])
                for e in document["eras"]]
    if actual != expected:
        raise ValueError("full replay does not reproduce recorded era spans, states, evidence and membership")
    return {"channel": document["channel"], "source_segmentation_reproduced": True, **result}
