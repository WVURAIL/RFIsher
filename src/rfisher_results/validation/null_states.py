"""Conservative joins of independently documented transmitter states.

This module checks the join and preserves its provenance. It cannot verify
the truth or independence of an external operator log or monitoring record.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime


def _hash(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _interval(start, end):
    if (not isinstance(start, datetime) or not isinstance(end, datetime)
            or start.utcoffset() is None or end.utcoffset() is None or start >= end):
        raise ValueError("intervals require ordered, timezone-aware start/end times")


@dataclass(frozen=True)
class StateRecord:
    transmitter: str
    start: datetime
    end: datetime
    state: str
    source_sha256: str
    # This must name reviewed evidence establishing independence. A digest
    # alone cannot establish independence or validate an inferred pilot label.
    independence_review_sha256: str | None = None

    def __post_init__(self):
        _interval(self.start, self.end)
        if not isinstance(self.transmitter, str) or not self.transmitter.strip() or self.state not in {"on", "off", "unknown"}:
            raise ValueError("invalid transmitter or state")
        if not _hash(self.source_sha256):
            raise ValueError("state evidence requires a SHA256 identity")
        if self.independence_review_sha256 is not None and not _hash(self.independence_review_sha256):
            raise ValueError("invalid independence-review identity")


def join_null_state(start, end, transmitters, records, *, candidate_scope_review_sha256=None):
    """Join half-open acquisition [start,end) against each candidate transmitter.

    An off classification requires complete off coverage for every declared
    candidate, reviewed independence, and reviewed completeness of the candidate
    scope. A single sign-off, uncovered time, conflicting state or unreviewed
    evidence leaves the allocation null unknown. Adjacent off records may join.
    """
    _interval(start, end)
    records = list(records)
    transmitters = list(transmitters)
    if (not transmitters or len(set(transmitters)) != len(transmitters)
            or any(not isinstance(t, str) or not t.strip() for t in transmitters)):
        raise ValueError("candidate transmitters must be nonempty and unique")
    if candidate_scope_review_sha256 is not None and not _hash(candidate_scope_review_sha256):
        raise ValueError("invalid candidate-scope review identity")
    states, evidence = {}, set()
    for transmitter in transmitters:
        relevant = [r for r in records if r.transmitter == transmitter
                    and r.start < end and start < r.end]
        boundaries = sorted({start, end, *[max(start, r.start) for r in relevant],
                             *[min(end, r.end) for r in relevant]})
        segments = []
        for lo, hi in zip(boundaries, boundaries[1:]):
            active = [r for r in relevant if r.start <= lo and r.end >= hi]
            # Unreviewed, conflicting or missing records never establish off.
            declared = {r.state for r in active}
            if (not active or len(declared) != 1 or "unknown" in declared
                    or any(r.independence_review_sha256 is None for r in active)):
                segments.append("unknown")
            else:
                segments.append(next(iter(declared)))
            for r in active:
                evidence.add(r.source_sha256)
                if r.independence_review_sha256:
                    evidence.add(r.independence_review_sha256)
        states[transmitter] = ("on" if "on" in segments else
                               "off" if set(segments) == {"off"} else "unknown")
    null = "unknown"
    if "on" in states.values():
        null = "not_null"
    elif set(states.values()) == {"off"} and candidate_scope_review_sha256:
        null = "off_for_reviewed_scope"
    return {"null_state": null, "transmitter_states": states,
            "candidate_scope_review_sha256": candidate_scope_review_sha256,
            "evidence_sha256": sorted(evidence),
            "interpretation": "join result conditional on the reviewed source records and candidate scope; not an independent verification of those records"}
