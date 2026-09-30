"""The screen of a band: keep, excise or undetermined, with its precedence.

The steps, in the order the selector policy declares them
(``selector.precedence``); the first that matches decides:

1. ``tolerance refused``: the band has no tolerance in the rule scenario.
2. ``detector refused``: the detector refused the band's surface (a floor or
   preparation refusal, or a stability refusal of every family). The
   interval is still computed and reported beside the outcome, as a
   diagnostic.
3. ``keep``: some family has a nonempty deployable set in the keep reading
   and its false-alarm limit is certified. Without the certification the
   band is undetermined ("keep-eligible; P_fa unverified").
4. ``excise``: every family has an empty deployable set in the exclusion
   reading and, where the floor is not verified, the least-R candidate's
   floor share is below ``selector.sensitivity_limited_share`` (an R that
   only measures the floor cannot excise).
5. ``undetermined`` otherwise.

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

from .interval import (STATUS_NONEMPTY, STATUS_THINNED, FamilyInterval,
                       fine_candidates, interval, points)

RULE_VERSION = "screen-precedence-v1"
OUTCOMES = ("keep", "excise", "undetermined")
STEPS = ("tolerance refused", "detector refused", "keep", "excise",
         "undetermined")
SCREEN_COLUMNS = ("band_id", "screen_outcome", "precedence_step",
                  "screen_reason", "families_checked", "rule_version")
RESIDUAL = {"booked": "r_sys", 1: "r_sys_incoherent"}
NONEMPTY = (STATUS_NONEMPTY, STATUS_THINNED)


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


def detector_refusal(summaries: Sequence[Mapping],
                     families: Sequence[Readings]) -> str:
    """The detector's refusal of the band's surface, or ``""``.

    A band is refused when it has no fine family and its summary carries a
    refusal, or when every fine family's stability screen refused.
    """
    reasons = sorted({str(s["refusal"]) for s in summaries if s["refusal"]})
    if not families:
        return reasons[0] if reasons else ""
    refused = [f for f in families
               if str(f.summary["stability_status"] or "").startswith("refused")
               or f.summary["refusal"]]
    if len(refused) == len(families):
        return str(refused[0].summary["refusal"] or
                   refused[0].summary["stability_status"])
    return ""


def certified(reading: FamilyInterval) -> bool:
    """A false-alarm limit is certified only when it is available."""
    return reading.eta_pfa_status == "available" and math.isfinite(
        reading.eta_pfa)


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
                "rule_version": RULE_VERSION}


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
    keepable = [f for f in families if f.keep.status in NONEMPTY]
    if keepable:
        if any(certified(f.keep) for f in keepable):
            return Screen(band_id, "keep", 3,
                          f"deployable set nonempty on {len(keepable)} "
                          f"famil{'y' if len(keepable) == 1 else 'ies'} with "
                          "a certified false-alarm limit", n)
        return Screen(band_id, "undetermined", 5,
                      "keep-eligible; P_fa unverified", n)
    empty = n > 0 and all(f.exclusion.status not in NONEMPTY
                          and f.exclusion.status.startswith("empty")
                          for f in families)
    if empty:
        share = float(policy.value("selector.sensitivity_limited_share"))
        verified = all(s["floor_verified"] for s in summaries
                       if s["floor_verified"] is not None)
        least = [f.exclusion.least for f in families
                 if f.exclusion.least is not None]
        best = min(least, key=lambda p: (p.R, p.candidate_order),
                   default=None)
        floor_share = (float(best.row["floor_share"]) if best is not None
                       else math.nan)
        if verified or (math.isfinite(floor_share) and floor_share < share):
            return Screen(band_id, "excise", 4,
                          f"every family's deployable set is empty in the "
                          f"exclusion reading (least R {best.R!r})", n)
        return Screen(band_id, "undetermined", 5,
                      f"sensitivity-limited: the least-R candidate's floor "
                      f"share {floor_share!r} is not below {share!r}", n)
    return Screen(band_id, "undetermined", 5,
                  "no family keeps, and not every family is empty", n)
