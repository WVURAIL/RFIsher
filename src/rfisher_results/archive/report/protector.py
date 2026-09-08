"""Conditional cleaner scenarios and the exposure of the evaluated policy.

10 log10 R is a derived model value. It inherits the scalar shelf assignment,
unmeasured visibility transfer, coherence assumptions and hypothetical delay
credit; it is not a measured engineering specification. The exposure columns
use the same diagnostic evaluation policy as the residual. Neither a model
crossing nor a floor assignment certifies physical recovery.
"""
from __future__ import annotations

import math

from ..worlds import PARAMETERS
from . import core
from .core import DASH, Channel, Fragment, Run
from .worlds import GROWTH, SECTION, _half_band_breaks, _num, _channel_list

NAME = "protector"
LABEL = "tab:tolerance:protector"
KEY = "ch09.protector"
DILATIONS = tuple(p for p in PARAMETERS if p != GROWTH)
WORLDS_SHOWN = (("none", "no cut"), ("peak2", "110~ns"))
CURVE_DB = (10.0, 20.0, 30.0)
HEADER = ("ch", r"no cut: dil.", r"$f\sigma_8$", r"$110$~ns: dil.", r"$f\sigma_8$",
          "kept", r"masked (\%)", r"$1/(1-f)$", "basis")
ALIGN = "l" + "r" * 7 + "l"


def requirement_db(ratio: float | None) -> float | None:
    """The extra shelf suppression that lands ``ratio`` on ``R = 1``, in dB.

    The residual is linear in surviving shelf power, so a protector removing a
    fixed fraction divides the ratio by that fraction and nothing else moves.
    A negative value is margin already in hand.
    """
    if ratio is None or not math.isfinite(ratio) or ratio <= 0.0:
        return None
    return 10.0 * math.log10(ratio)


def _binding(section, world: str, parameters) -> float | None:
    """The worst held-out ratio over ``parameters`` in one world; None when unpriced."""
    values = [_num(section.get(f"{world}_{p}_evaluation_R")) for p in parameters]
    return max(values) if values and all(v is not None for v in values) else None


def channel_requirements(c: Channel) -> dict[str, float | None]:
    """Every requirement one channel carries, keyed ``<world>_<tier>``."""
    s = c.section(SECTION) if c.has(SECTION) else {}
    out: dict[str, float | None] = {}
    for world, _ in WORLDS_SHOWN:
        out[f"{world}_dilation"] = requirement_db(_binding(s, world, DILATIONS))
        out[f"{world}_growth"] = requirement_db(_binding(s, world, (GROWTH,)))
    return out


def _cell(value: float | None) -> str:
    return DASH if value is None else f"${value:.1f}$"


def build(run: Run) -> Fragment:
    """``tab:tolerance:protector``: the decibels a cleaner would have to deliver."""
    frag = Fragment(NAME, LABEL, "")
    channels = [c for c in sorted(run.channels, key=lambda c: c.channel)
                if c.has(SECTION) and _num(c.section(SECTION).get("r_evaluation")) is not None]
    if not channels:
        frag.notes.append("no channel carries a held-out residual, so no requirement can be stated: the run "
                          "predates the replay, or no point was replayed on an evaluation block")
        return frag

    rows: list[list[str]] = []
    measured: dict[str, list[tuple[float, int]]] = {"dilation": [], "growth": []}
    bounded: list[int] = []
    inside: list[int] = []
    unpriced: list[int] = []
    for c in channels:
        ch = c.channel
        s = c.section(SECTION)
        floor_bound = bool(s.get("floor_bound"))
        req = channel_requirements(c)
        if all(v is None for v in req.values()):
            unpriced.append(ch)
            continue
        row = {"channel": ch}
        cells = [str(ch)]
        for world, _ in WORLDS_SHOWN:
            for tier in ("dilation", "growth"):
                column = f"{world}_{tier}_db"
                value = req[f"{world}_{tier}"]
                cells.append(_cell(value))
                frag.add(f"{KEY}.{column}.ch{ch}", value, precision=1, row=row, column=column,
                         kind="float" if value is not None else "text",
                         status="pending" if value is None else "derived",
                         renderings=(DASH,) if value is None else (f"{value:.1f}",))
                if world == "peak2" and value is not None:
                    if floor_bound:
                        pass                       # an upper limit is not a specification; see the module docstring
                    else:
                        measured[tier].append((value, ch))
        if floor_bound:
            bounded.append(ch)
        peak2_dil = req["peak2_dilation"]
        if peak2_dil is not None and peak2_dil <= 0.0:
            inside.append(ch)
        sel = c.section("selection") if c.has("selection") else {}
        kept = _num(sel.get("kept_evaluation"))
        fraction = _num(sel.get("masked_fraction_evaluation"))
        cost = 1 / (1 - fraction) if fraction is not None and 0 <= fraction < 1 else None
        cells.extend((DASH if kept is None else str(int(kept)),
                      DASH if fraction is None else f"{100 * fraction:.3f}",
                      DASH if cost is None else f"{cost:.1f}"))
        for column, value in (("kept_evaluation", kept), ("masked_fraction_evaluation", fraction),
                              ("exposure_multiplier", cost)):
            frag.add(f"{KEY}.{column}.ch{ch}", value, status="derived" if value is not None else "pending", row=row, column=column)
        basis = "model/floor" if floor_bound else "model"
        cells.append(basis)
        frag.add(f"{KEY}.basis.ch{ch}", basis, kind="text", status="derived", row=row,
                 column="basis", renderings=(basis,))
        rows.append(cells)

    priced = [c for c in channels if c.channel not in unpriced]
    frag.tex = core.booktabs(HEADER, rows, ALIGN, midrules=_half_band_breaks(priced))

    for tier in ("dilation", "growth"):
        values = sorted(measured[tier])
        for db in CURVE_DB:
            n = sum(1 for v, _ in values if v <= db)
            frag.add(f"{KEY}.n_{tier}_at_{int(db)}db", n, kind="int", column=f"n_{tier}_at_{int(db)}db")
        cheapest = values[0] if values else None
        frag.add(f"{KEY}.cheapest_{tier}_db", None if cheapest is None else cheapest[0], precision=1,
                 kind="float" if cheapest else "text", status="derived" if cheapest else "pending",
                 column=f"cheapest_{tier}_db",
                 renderings=(DASH,) if cheapest is None else (f"{cheapest[0]:.1f}",))
        frag.add(f"{KEY}.cheapest_{tier}_channel", None if cheapest is None else cheapest[1], kind="int",
                 column=f"cheapest_{tier}_channel")
    for key, value in (("channels", len(rows)), ("n_floor_bound", len(bounded)),
                       ("n_measured", 0), ("n_conditional", len(rows)), ("n_inside_110", len(inside))):
        frag.add(f"{KEY}.{key}", value, kind="int", column=key)

    frag.notes.append("the conditional model value is the additional shelf suppression that would land the held-out "
                      "residual on R = 1; the residual is linear in surviving shelf power, so it is "
                      "10 log10 R; its physical interpretation requires measured transfer and signal preservation")
    frag.notes.append("the 110 ns columns use hypothetical suppression, not a measured filter response")
    frag.notes.append("kept frames, mask fraction, and exposure multiplier describe the same diagnostic policy as the evaluation residual, not the calibration knee")
    for tier, word in (("dilation", "the two dilations"), ("growth", "the growth rate")):
        counts = ", ".join(f"{sum(1 for v, _ in measured[tier] if v <= db)} at {db:g} dB" for db in CURVE_DB)
        frag.notes.append(f"on top of the 110 ns cut, a protector brings {word} inside on {counts}, counted "
                          f"over {len(measured[tier])} conditional non-floor-only model rows; no physical recovery is certified")
    if bounded:
        frag.notes.append(f"floor-bound channels ({_channel_list(bounded)}) are excluded from those counts: "
                          "their score is set by the sensitivity assignment, which is neither unavoidable contamination nor a calibrated confidence bound")
    if unpriced:
        frag.notes.append(f"no world prices {_channel_list(unpriced)}, so no requirement is stated for them")
    frag.notes.append("nothing here proposes a protector, models one, or claims the surviving power is "
                      "removable; the table states what one would have to remove")
    return frag


BUILDERS = (build,)
