"""The operating point each channel's kernel should run, and what it buys.

The selector of chapter 9 answers "is any point inside the science tolerance",
and on this archive the answer is no on every channel. That is a screening
verdict, not an operating instruction: the kernel still has to be given a rank
and a multiplier, and the useful question is where on the channel's own
mask-against-residual frontier the masking stops paying.

The frontier. Every evaluated ``(rho, eta)`` gives a masked fraction ``f`` and
a kept-frame residual ``r``. The Pareto lower envelope of ``r`` against ``f``
is the frontier: for each amount of data you are willing to lose, the least
residual any rank and multiplier can leave. It falls steeply and then flattens
--- on channel 29 half the frames buy a factor of 31, and the remaining half
buys a further fifth --- so the operating point is the corner, not the end.

The rule (a declared policy, with its sensitivities recorded). The operating
point is the **knee**: cost ``1/(1-f)`` and residual ``r`` are each mapped to
``[0, 1]`` across the frontier's own span in log space, and the point chosen is
the one closest to the corner where both are least. It is where the curve turns
--- past it, each further percent of data bought a diminishing share of the
residual.

The alternative rule, reported beside it rather than instead of it, is the
smallest mask within a margin of the frontier's floor,
``f = min{f : r(f) <= (1 + margin) r_floor}`` for
``margin`` in ``(0.05, 0.10, 0.25, 0.50)``. On this archive it does not choose
an operating point: the frontier keeps descending slowly for the last few
percent of data, so even a fifty-percent margin lands far out in the tail
where a few dozen frames survive. That is a fact about the frontier and it is
recorded, but a point keeping forty frames is not a mask to run.

What it is not. The point is not a claim that the channel passes: ``R`` at the
operating point is reported and on this archive exceeds one everywhere. It is
the value to run, and the evaluation block is where it is scored.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import numpy as np

MARGIN = 0.10
MARGIN_SENSITIVITY = (0.05, 0.10, 0.25, 0.50)
MIN_KEPT = 30                      # the selector's own support floor: a point keeping less is not a point


@dataclass(frozen=True)
class FrontierPoint:
    rho: int
    eta_q16: int
    eta: float
    masked_fraction: float
    kept: int
    r_sys: float
    cost: float

    def as_dict(self, prefix: str) -> dict:
        return {f"{prefix}_rho": self.rho, f"{prefix}_eta_q16": self.eta_q16, f"{prefix}_eta": self.eta,
                f"{prefix}_masked_fraction": self.masked_fraction, f"{prefix}_kept": self.kept,
                f"{prefix}_r_sys": self.r_sys, f"{prefix}_cost": self.cost}


@dataclass(frozen=True)
class OperatingPoint:
    """One channel's frontier and the point chosen on it."""

    channel: int
    frontier: tuple[FrontierPoint, ...]
    r_floor: float
    margin: float
    point: FrontierPoint | None            # the rule's choice
    knee: FrontierPoint | None             # maximum curvature, as a check
    keep_everything_r: float               # r at f = 0: what the mask is measured against
    sensitivity: dict = field(default_factory=dict)   # margin -> (f, r, rho, eta_q16)
    status: str = "measured"
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def suppression(self) -> float:
        """Keep-everything residual over the operating point's, the factor the mask buys."""
        if self.point is None or not (self.point.r_sys > 0 and math.isfinite(self.keep_everything_r)):
            return math.nan
        return self.keep_everything_r / self.point.r_sys

    def as_row(self) -> dict:
        row = {"channel": self.channel, "frontier_points": len(self.frontier), "r_floor": self.r_floor,
               "margin": self.margin, "keep_everything_r_sys": self.keep_everything_r,
               "suppression_factor": self.suppression,
               "suppression_db": 10.0 * math.log10(self.suppression) if self.suppression > 0 and math.isfinite(self.suppression) else math.nan,
               "status": self.status, "notes": "; ".join(self.notes)}
        row.update((self.point or _nan_point()).as_dict("operating"))
        row.update((self.knee or _nan_point()).as_dict("knee"))
        for margin, value in sorted(self.sensitivity.items()):
            tag = f"{margin:g}".replace(".", "p")
            row[f"sensitivity_{tag}_masked_fraction"] = value[0]
            row[f"sensitivity_{tag}_r_sys"] = value[1]
            row[f"sensitivity_{tag}_rho"] = value[2]
            row[f"sensitivity_{tag}_eta_q16"] = value[3]
        return row


def _nan_point() -> FrontierPoint:
    return FrontierPoint(-1, -1, math.nan, math.nan, 0, math.nan, math.nan)


def pareto_frontier(points: Sequence[dict], *, min_kept: int = MIN_KEPT) -> list[FrontierPoint]:
    """The lower envelope of ``r_sys`` against masked fraction, ascending in ``f``.

    A point keeping fewer than ``min_kept`` frames is not on the frontier: the
    selector will not choose one, and its residual is an average over too few
    frames to mean anything.
    """
    rows = [p for p in points if p.get("kept", 0) >= min_kept and math.isfinite(p.get("r_sys", math.nan))]
    if not rows:
        return []
    rows.sort(key=lambda p: (p["masked_fraction"], p["r_sys"]))
    out: list[FrontierPoint] = []
    best = math.inf
    for p in rows:
        if p["r_sys"] < best:
            best = p["r_sys"]
            out.append(FrontierPoint(int(p["rho"]), int(p["eta_q16"]), float(p["eta"]), float(p["masked_fraction"]),
                                     int(p["kept"]), float(p["r_sys"]), float(p.get("cost", math.nan))))
    return out


def _at_margin(frontier: Sequence[FrontierPoint], r_floor: float, margin: float) -> FrontierPoint | None:
    """The smallest-``f`` frontier point within ``margin`` of the floor."""
    target = (1.0 + margin) * r_floor
    return next((p for p in frontier if p.r_sys <= target), None)


def _knee(frontier: Sequence[FrontierPoint]) -> FrontierPoint | None:
    """The frontier's point of greatest curvature, on normalised log axes.

    Cost and residual are made commensurate by mapping each to [0, 1] over the
    frontier's own span in log space, so the knee is where the corner is and
    not where the units happen to be.
    """
    if len(frontier) < 3:
        return None
    cost = np.array([1.0 / (1.0 - p.masked_fraction) if p.masked_fraction < 1.0 else np.inf for p in frontier])
    r = np.array([p.r_sys for p in frontier])
    ok = np.isfinite(cost) & np.isfinite(r) & (cost > 0) & (r > 0)
    if ok.sum() < 3:
        return None
    x, y = np.log10(cost[ok]), np.log10(r[ok])
    x = (x - x.min()) / (x.max() - x.min()) if x.max() > x.min() else x * 0
    y = (y - y.min()) / (y.max() - y.min()) if y.max() > y.min() else y * 0
    # the utopia corner is (0, 0): the knee is the frontier point closest to it
    index = int(np.argmin(x ** 2 + y ** 2))
    return [p for p, keep in zip(frontier, ok) if keep][index]


def choose(channel: int, points: Sequence[dict], *, margin: float = MARGIN,
           sensitivity: Sequence[float] = MARGIN_SENSITIVITY, min_kept: int = MIN_KEPT) -> OperatingPoint:
    """The operating point of one channel from its evaluated surface."""
    frontier = pareto_frontier(points, min_kept=min_kept)
    notes: list[str] = []
    if not frontier:
        return OperatingPoint(channel, (), math.nan, margin, None, None, math.nan, {}, "no frontier",
                              (f"no evaluated point keeps {min_kept} frames with a finite residual",))
    r_floor = min(p.r_sys for p in frontier)
    keep_all = next((p.r_sys for p in frontier if p.masked_fraction <= 0.0), math.nan)
    if not math.isfinite(keep_all):
        keep_all = max(p.r_sys for p in frontier)
        notes.append("no point masks nothing: the reference residual is the frontier's largest")
    knee = _knee(frontier)
    sens = {}
    for m in sensitivity:
        p = _at_margin(frontier, r_floor, m)
        sens[m] = (p.masked_fraction, p.r_sys, p.rho, p.eta_q16) if p else (math.nan, math.nan, -1, -1)
    if knee is None:
        notes.append("the frontier has too few points to have a knee")
    elif knee.masked_fraction >= 0.99:
        notes.append(f"the knee itself masks {knee.masked_fraction:.3f}: this channel has no cheap mask, "
                     "and the point is reported for completeness rather than as an operating instruction")
    return OperatingPoint(channel, tuple(frontier), r_floor, margin, knee, knee, keep_all, sens,
                          "measured" if knee else "undefined", tuple(notes))


OPERATING_COLUMNS = ("channel", "frontier_points", "r_floor", "margin", "keep_everything_r_sys",
                     "suppression_factor", "suppression_db", "operating_rho", "operating_eta_q16", "operating_eta",
                     "operating_masked_fraction", "operating_kept", "operating_r_sys", "operating_cost",
                     "knee_rho", "knee_eta_q16", "knee_eta", "knee_masked_fraction", "knee_kept", "knee_r_sys",
                     "knee_cost", "status", "notes")


def write_operating_points(results: Sequence[OperatingPoint], path: Path | str) -> Path:
    """One row per channel: the point to run and what it buys."""
    import csv

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [r.as_row() for r in results]
    keys = list(OPERATING_COLUMNS) + [k for r in rows for k in r if k not in OPERATING_COLUMNS]
    seen, fields = set(), []
    for k in keys:
        if k not in seen:
            seen.add(k)
            fields.append(k)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: (repr(v) if isinstance(v, float) else row.get(k, "")) for k, v in
                             ((k, row.get(k, "")) for k in fields)})
    return path
