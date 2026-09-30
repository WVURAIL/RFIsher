"""Named sensitivities: the only place a sensitivity factor multiplies a residual.

A rule never takes a credit. A sensitivity scenario of the tolerance table
(its ``role`` is ``sensitivity``) names an assumed suppression S of the
residual and prices the band against its own tolerance; this module reads
each one beside the rule, and nothing else applies S.

For each band and sensitivity the least-R candidate of the exclusion reading
is priced as R_S = r * 10^(-S/10) / r_tol (the operands in that order, never
folded into the tolerance), and an excision of the rule is checked again:

- ``robust to post-processing``: the excision holds under every sensitivity;
- ``idealized-only``: it does not hold under at least one.

A sensitivity can only remove an excision: a band the rule does not excise
is never excised here.
"""
from __future__ import annotations

import math
from typing import Mapping, Sequence

SENSITIVITY = "sensitivity"
ROBUST = "robust to post-processing"
IDEALIZED = "idealized-only"
NO_EXCISION = "no excision under the rule"
COLUMNS = ("band_id", "scenario", "tolerance_basis", "suppression_db",
           "r_tol", "rule_outcome", "min_R", "min_R_with_suppression",
           "excision_holds", "label")


def factor(suppression_db: float) -> float:
    """10^(-S/10), the residual left by an assumed suppression S."""
    return 10.0 ** (-float(suppression_db) / 10.0)


def priced(r: float, suppression_db: float, r_tol: float) -> float:
    """R_S = r * 10^(-S/10) / r_tol."""
    return r * factor(suppression_db) / r_tol


def sensitivities(band_id: str, rule_outcome: str,
                  scenarios: Sequence[Mapping], exclusion_points) -> list[dict]:
    """The rows of ``sensitivity.csv`` for one band.

    ``scenarios`` are the band's tolerance rows of role ``sensitivity``;
    ``exclusion_points`` the band's candidates in the exclusion reading, as
    ``(r, family)`` pairs of kept residual and threshold family.
    """
    rows = []
    points = [(float(r), family) for r, family in exclusion_points
              if math.isfinite(float(r))]
    holds_all = True
    for s in scenarios:
        if s["role"] != SENSITIVITY:
            continue
        r_tol, sdb = float(s["r_tol"]), float(s["suppression_db"])
        if not (math.isfinite(r_tol) and points):
            rows.append({"band_id": band_id, "scenario": s["scenario"],
                         "tolerance_basis": s["tolerance_basis"],
                         "suppression_db": sdb, "r_tol": r_tol,
                         "rule_outcome": rule_outcome, "min_R": math.nan,
                         "min_R_with_suppression": math.nan,
                         "excision_holds": "", "label": ""})
            continue
        least = min(r for r, _ in points)
        with_s = [priced(r, sdb, r_tol) for r, _ in points]
        holds = all(v > 1.0 for v in with_s)
        excised = rule_outcome == "excise"
        holds_all = holds_all and (holds if excised else True)
        rows.append({"band_id": band_id, "scenario": s["scenario"],
                     "tolerance_basis": s["tolerance_basis"],
                     "suppression_db": sdb, "r_tol": r_tol,
                     "rule_outcome": rule_outcome, "min_R": least / r_tol,
                     "min_R_with_suppression": min(with_s),
                     "excision_holds": holds if excised else "",
                     "label": ""})
    label = ((ROBUST if holds_all else IDEALIZED)
             if rule_outcome == "excise" else NO_EXCISION)
    for row in rows:
        row["label"] = label
    return rows


def outcome_with_sensitivities(rule_outcome: str,
                               rows: Sequence[Mapping]) -> str:
    """The outcome a sensitivity reading gives: never an excision the rule
    did not make."""
    if rule_outcome != "excise":
        return rule_outcome
    return "excise" if all(r["excision_holds"] is True for r in rows
                           if r["excision_holds"] != "") else "undetermined"
