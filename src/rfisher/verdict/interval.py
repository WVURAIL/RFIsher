"""The candidates of a threshold family priced against a tolerance, and the selector.

Per threshold family (the candidates of one statistic and one rank) and per
tolerance r_tol, a candidate is *feasible* when its kept residual r_sys meets
r_tol (equality is feasible when the selector policy says so). The selector
takes the least cost C = (1 + r_var) / (1 - f) among the feasible candidates,
keeps those within the plateau ratio of it, and breaks ties by residual, then
masked fraction, then the detector's declared candidate order. The floats are
those of the operands in that order, so a selection made here is
bit-identical to one made on the same candidates by the earlier selector.

Which fine families are read is one selector-policy value,
``selector.fine_rank``, read only by :func:`fine_candidates`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Mapping, Sequence

FINE = "fine_surface"
CALIBRATION = "calibration"
FAMILY_PREFIX = "rho="
# The tail of the policy's tie-break is the detector's declared candidate
# order (rank, then multiplier). The frozen archive policy copy names it by
# those two parameters, the order they stand for.
ORDER_NAMES = ("candidate_order",)
LEGACY_ORDER_NAMES = ("rho", "multiplier_q16")
TIE_FIELDS = {"systematic_residual": "r_sys", "masked_fraction":
              "masked_fraction"}


class SelectionRefused(ValueError):
    """The selector refuses a family whose feasible candidates lack a finite cost."""


def fine_candidates(rows: Sequence[Mapping], policy) -> list[Mapping]:
    """The calibration-block candidates of the fine families the policy reads.

    ``selector.fine_rank`` is ``"all"`` (every rank the detector enumerates)
    or one rank; this is the one place it is read.
    """
    rank = policy.value("selector.fine_rank")
    wanted = None if rank == "all" else f"{FAMILY_PREFIX}{int(rank)}"
    return [r for r in rows if r["candidate_set"] == FINE
            and r["block"] == CALIBRATION
            and (wanted is None or r["threshold_family"] == wanted)]


def cost(r_var: float, masked_fraction: float) -> float:
    """C = (1 + r_var) / (1 - f), the operands in the selector's order."""
    cost_residual = 0.0 if r_var is None else r_var
    return (1.0 + cost_residual) / (1.0 - masked_fraction)


def feasible(r_sys: float, r_tol: float, equality_is_feasible: bool) -> bool:
    return r_sys <= r_tol if equality_is_feasible else r_sys < r_tol


@dataclass(frozen=True)
class Point:
    """A candidate priced against one tolerance."""

    row: Mapping = field(repr=False)
    family: str
    eta: float
    masked_fraction: float
    r_sys: float
    candidate_order: int
    cost: float
    R: float
    feasible: bool


def points(rows: Sequence[Mapping], r_tol: float, policy, *,
           residual: str = "r_sys") -> list[Point]:
    """The candidates of ``rows`` priced against ``r_tol``.

    ``residual`` names the column read as the kept residual: ``r_sys`` (the
    booked coherence gain) or ``r_sys_incoherent`` (G = 1).
    """
    equality = bool(policy.value("selection.tolerance_equality_is_feasible"))
    out = []
    for r in rows:
        value = float(r[residual])
        out.append(Point(
            row=r, family=r["threshold_family"], eta=float(r["eta"]),
            masked_fraction=float(r["masked_fraction"]), r_sys=value,
            candidate_order=int(r["candidate_order"]),
            cost=cost(r["r_var"], r["masked_fraction"]),
            R=value / r_tol,
            feasible=feasible(value, r_tol, equality)))
    return out


def tie_key(policy):
    """The policy's tie-break as a key on a :class:`Point`."""
    names = tuple(policy.value("selection.tie_break"))
    tail = next((t for t in (ORDER_NAMES, LEGACY_ORDER_NAMES)
                 if names[len(names) - len(t):] == t), ORDER_NAMES)
    head = names[:len(names) - len(tail)]
    if names[len(head):] != tail or not all(n in TIE_FIELDS for n in head):
        raise ValueError(f"selection.tie_break {names} is not "
                         f"{list(TIE_FIELDS)} followed by the candidate order")
    fields = [TIE_FIELDS[n] for n in head]
    return lambda p: tuple(getattr(p, f) for f in fields) + (
        p.candidate_order,)


@dataclass(frozen=True)
class Selection:
    """The selector's choice among a set of candidates."""

    selected: Point | None
    minimum_cost: float
    plateau: tuple[Point, ...]
    status: str

    @property
    def plateau_eta(self) -> tuple[float, float]:
        """The eta range of the plateau members at the selected family."""
        if self.selected is None:
            return math.nan, math.nan
        at = [p.eta for p in self.plateau if p.family == self.selected.family]
        return (min(at), max(at)) if at else (math.nan, math.nan)

    @property
    def plateau_members(self) -> int | None:
        if self.selected is None:
            return None
        return sum(1 for p in self.plateau if p.family == self.selected.family)


def select(candidates: Sequence[Point], policy) -> Selection:
    """The least-cost feasible candidate, with the plateau and the tie-break.

    ``status`` is ``selected``, ``no_feasible_threshold`` (candidates exist
    but none is feasible) or ``no_evaluable_threshold`` (no candidate).
    """
    good = [p for p in candidates if p.feasible]
    if not good:
        return Selection(None, math.nan, (), "no_feasible_threshold"
                         if candidates else "no_evaluable_threshold")
    undefined = [p for p in good if not math.isfinite(p.cost)]
    if undefined:
        p = undefined[0]
        raise SelectionRefused(
            f"{p.family}, candidate {p.candidate_order}: the cost is not "
            f"finite (r_var {p.row.get('r_var')!r}); the selector needs a "
            "finite variance residual on every feasible candidate")
    ratio = float(policy.value("selection.cost_plateau_ratio"))
    minimum = min(p.cost for p in good)
    near = tuple(p for p in good if p.cost <= ratio * minimum)
    chosen = min(near, key=tie_key(policy))
    return Selection(chosen, minimum, near, "selected")
