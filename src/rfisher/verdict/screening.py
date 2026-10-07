"""Historical conditional screen: keep, excise or undetermined.

The outcome is a reading under the archived allowance assumptions, not a
qualified physical operating recommendation. ``as_row`` records this boundary
even when a verified floor permits the historical ``excise`` category.

The steps, in the order the selector policy declares them
(``selector.precedence``); the first that matches decides:

1. ``tolerance refused``: the band has no tolerance in the rule scenario.
2. ``detector refused``: the detector refused the band's surface (a floor or
   preparation refusal, or a stability refusal of every family). The
   interval is still computed and reported beside the outcome, as a
   diagnostic.
3. ``keep``: some family has a nonempty deployable set in the keep reading.
   No false-alarm limit is required: eta_Pfa is a reported diagnostic, as in
   the interval (:func:`certified` is reported beside the outcome).
4. ``excise``: every family has an empty deployable set in the exclusion
   reading and, unless the floor is verified on every family, the least-R
   candidate's floor share is below ``selector.sensitivity_limited_share``
   (an R that only measures the floor cannot excise).
5. ``undetermined`` otherwise.

Steps 3 and 4 read only the families the detector did not refuse: a family
whose stability screen or preparation refused carries no keep and no
excision, whatever its set.

A false-alarm limit is certified (:func:`certified`, the archive's
``false_alarm_certified`` column) only when the detector reports it
available, its integer null support and source are recorded, and its 95%
upper bound is at most the alpha the handoff declares.

The two readings differ only for a quantity that is not measured
(``selector.unmeasured``): an exclusion reads it at its most favorable value
and a keep at its least favorable. For the coherence gain
(``selector.archive_exclusion_gain``) the exclusion reads the booked gain
where the correlation time is measured and G = 1 where it is only bounded or
at the cap; a keep reads the booked gain, which there is the bound or the cap.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence

from ..response.evidence import HISTORICAL_SCREENING_EVIDENCE
from .interval import (STATUS_NONEMPTY, STATUS_THINNED, FamilyInterval,
                       fine_candidates, interval, points)

RULE_VERSION = "screen-precedence-v1"
OUTCOMES = ("keep", "excise", "undetermined")
STEPS = ("tolerance refused", "detector refused", "keep", "excise",
         "undetermined")
SCREEN_COLUMNS = ("band_id", "screen_outcome", "precedence_step",
                  "screen_reason", "families_checked", "rule_version",
                  *HISTORICAL_SCREENING_EVIDENCE)
RESIDUAL = {"booked": "r_sys", 1: "r_sys_incoherent"}
NONEMPTY = (STATUS_NONEMPTY, STATUS_THINNED)
BULK_NULL = "bulk of the mixture"


def check_precedence(policy) -> None:
    """The policy's precedence must be the steps this module implements."""
    declared = tuple(policy.value("selector.precedence"))
    if declared != STEPS:
        raise ValueError(f"selector.precedence {declared} is not {STEPS}")


def exclusion_residual(chain_gain_status: str, policy) -> str:
    """The residual column an exclusion reads for this chain-gain status."""
    reading = dict(policy.value("selector.archive_exclusion_gain"))
    if chain_gain_status not in reading:
        raise ValueError(f"no exclusion gain for chain status "
                         f"{chain_gain_status!r}")
    return RESIDUAL[reading[chain_gain_status]]


@dataclass(frozen=True)
class Readings:
    """A family's deployable set in the keep and the exclusion reading."""

    family: str
    summary: Mapping
    keep: FamilyInterval
    exclusion: FamilyInterval


def family_readings(rows: Sequence[Mapping], summaries: Sequence[Mapping],
                    r_tol: float, policy, *, thinned: bool = False
                    ) -> list[Readings]:
    """Each fine family of one band, priced both ways against ``r_tol``."""
    rows = fine_candidates(rows, policy)
    by_family: dict[str, list] = {}
    for r in rows:
        by_family.setdefault(r["threshold_family"], []).append(r)
    out = []
    for summary in summaries:
        family = summary["threshold_family"]
        if family not in by_family:
            continue
        excl = exclusion_residual(summary["chain_gain_status"], policy)
        out.append(Readings(
            family=family, summary=summary,
            keep=interval(points(by_family[family], r_tol, policy),
                          summary, thinned=thinned),
            exclusion=interval(points(by_family[family], r_tol, policy,
                                      residual=excl), summary,
                               thinned=thinned)))
    return out


def refused_family(family: Readings) -> bool:
    """Whether the detector refused this family (stability or preparation)."""
    return bool(str(family.summary["stability_status"] or "").startswith(
        "refused") or family.summary["refusal"])


def detector_refusal(summaries: Sequence[Mapping],
                     families: Sequence[Readings]) -> str:
    """The detector's refusal of the band's surface, or ``""``.

    A band is refused when it has no fine family and its summary carries a
    refusal, or when every fine family's stability screen refused.
    """
    reasons = sorted({str(s["refusal"]) for s in summaries if s["refusal"]})
    if not families:
        return reasons[0] if reasons else ""
    refused = [f for f in families if refused_family(f)]
    if len(refused) == len(families):
        return str(refused[0].summary["refusal"] or
                   refused[0].summary["stability_status"])
    return ""


def certified(reading: FamilyInterval, summary: Mapping | None = None,
              alpha: float | None = None) -> bool:
    """Accept only a complete exact-null certificate at the declared target."""
    if not (reading.eta_pfa_status == "available"
            and math.isfinite(reading.eta_pfa)) or summary is None:
        return False
    if summary.get("candidate_set") == "fine_surface" and reading.eta_pfa <= 0.0:
        return False
    source = summary.get("null_source")
    prefix = ("transmitter-off epoch " if summary.get("candidate_set") == "fine_surface"
              else "verified signal-free transmitter-off epoch ")
    if (not isinstance(source, str) or not source.startswith(prefix)
            or not source[len(prefix):].strip()):
        return False
    frames = summary.get("null_frames")
    if isinstance(frames, bool) or not isinstance(frames, int) or frames <= 0:
        return False
    try:
        target = float(summary["pfa_target"])
        upper = float(summary["pfa_upper_95"])
        trials = float(summary["pfa_effective_samples"])
        declared = target if alpha is None else float(alpha)
    except (KeyError, TypeError, ValueError, OverflowError):
        return False
    if not (0.0 < upper <= target < 1.0 and declared == target
            and math.isfinite(trials) and trials == frames):
        return False
    zero_upper = -math.expm1(math.log(0.05) / frames)
    return upper + 8 * math.ulp(zero_upper) >= zero_upper



@dataclass(frozen=True)
class Screen:
    band_id: str
    outcome: str
    step: int
    reason: str
    families_checked: int

    def as_row(self) -> dict:
        return {"band_id": self.band_id, "screen_outcome": self.outcome,
                "precedence_step": self.step, "screen_reason": self.reason,
                "families_checked": self.families_checked,
                "rule_version": RULE_VERSION, **HISTORICAL_SCREENING_EVIDENCE}


def screen(band_id: str, tolerance: Mapping | None,
           summaries: Sequence[Mapping], families: Sequence[Readings],
           policy) -> Screen:
    """The band's outcome under the precedence (see the module docstring)."""
    check_precedence(policy)
    n = len(families)
    r_tol = float(tolerance["r_tol"]) if tolerance else math.nan
    if not math.isfinite(r_tol):
        why = (tolerance or {}).get("refusal") or "no tolerance row"
        return Screen(band_id, "undetermined", 1, f"tolerance refused: {why}",
                      n)
    refusal = detector_refusal(summaries, families)
    if refusal:
        return Screen(band_id, "undetermined", 2,
                      f"detector refused: {refusal}", n)
    usable = [f for f in families if not refused_family(f)]
    keepable = [f for f in usable if f.keep.status in NONEMPTY]
    if keepable:
        return Screen(band_id, "keep", 3,
                      f"deployable set nonempty on {len(keepable)} "
                      f"famil{'y' if len(keepable) == 1 else 'ies'}", n)
    empty = bool(usable) and all(f.exclusion.status not in NONEMPTY
                                 and f.exclusion.status.startswith("empty")
                                 for f in usable)
    if empty:
        share = float(policy.value("selector.sensitivity_limited_share"))
        verified = all(f.summary["floor_verified"] is True for f in usable)
        least = [f.exclusion.least for f in usable
                 if f.exclusion.least is not None]
        best = min(least, key=lambda p: (p.R, p.candidate_order),
                   default=None)
        if best is None:
            return Screen(band_id, "undetermined", 5,
                          "no finite R in the exclusion reading", n)
        floor_share = float(best.row["floor_share"])
        if verified or (math.isfinite(floor_share) and floor_share < share):
            return Screen(band_id, "excise", 4,
                          f"every family's deployable set is empty in the "
                          f"exclusion reading (least R {best.R!r})", n)
        return Screen(band_id, "undetermined", 5,
                      f"sensitivity-limited: the least-R candidate's floor "
                      f"share {floor_share!r} is not below {share!r}", n)
    return Screen(band_id, "undetermined", 5,
                  "no family keeps, and not every family is empty", n)
