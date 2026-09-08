r"""``tab:tolerance:protector``: what a cleaner would have to deliver.

Every other table in this chapter answers "does the channel pass?", and on
the held-out evidence the answer is almost always no. That is a verdict about
the instrument as built, and it is easy to misread as a verdict about the
band. The two are different claims, and the difference is worth stating as a
number rather than as a hedge: a channel fails by a *finite* amount, and the
amount is a specification something else could be designed against.

The something else is a protector -- any subsystem that removes shelf power
the mask leaves behind, sited after the mask and before the estimator. This
fragment does not propose one, model one, or claim one is achievable. It
reports the requirement: the additional shelf suppression, in decibels, that
would bring each channel's held-out residual exactly to ``R = 1``.

Why a decibel is the right unit for it. The residual is linear in surviving
shelf power (:mod:`rfisher.residual`), so a protector that removes a fixed
fraction of that power divides every ratio by the same factor, and the
requirement is ``10 log10 R`` with no further modelling. That is also the
whole content of the claim: it says what a protector would have to remove,
not that removing it is possible, and nothing here asserts that the surviving
power is removable at all.

Two worlds, because the delay cut is not the protector's competitor but its
substrate. ``none`` is the requirement standing alone, for a protector asked
to do the whole job. ``peak2`` is the requirement *on top of* the operative
110 ns cut, which is the configuration a BAO analysis in this band would
actually run --- the cut has already taken 8.2 dB and the protector is asked
only for the remainder. A negative requirement is margin: the channel is
already inside and needs no protector at all.

What a floor-bound row means, and it matters more here than anywhere else in
the chapter. Where every kept frame sits at the sensitivity floor, the
residual reported is the floor rather than a measurement, so the requirement
is an *upper limit*: the surviving contamination is somewhere below where
this instrument can see, the true requirement is somewhere below the number
printed, and it may be zero. A protector designed to the printed figure would
be over-specified on those channels by an unknown margin. They are marked,
and they are excluded from the band-level specification below, because a
specification quoted from an upper limit is not a specification.

The band-level numbers are the useful summary and they are a curve, not a
scalar: sort the channels by requirement and the k-th smallest is what it
takes to bring k channels inside. ``ch09.protector.n_dilation_at_<D>db`` and
``n_growth_at_<D>db`` carry that curve at 10, 20 and 30 dB, on top of the
110 ns cut, over the channels whose requirement is a measurement.

Numbers: ``ch09.protector.<column>.chNN`` per cell, ``ch09.protector.*`` for
the band-level counts and the cheapest requirement in each tier.
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
HEADER = ("ch", r"no cut: dil.", r"$f\sigma_8$", r"$110$~ns: dil.", r"$f\sigma_8$", "basis")
ALIGN = "l" + "r" * 4 + "l"


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
    values = [v for v in values if v is not None]
    return max(values) if values else None


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
                         status="pending" if value is None else ("bounded" if floor_bound else "measured"),
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
        cells.append("floor" if floor_bound else "measured")
        frag.add(f"{KEY}.basis.ch{ch}", "floor" if floor_bound else "measured", kind="text", row=row,
                 column="basis", renderings=("floor" if floor_bound else "measured",))
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
                 kind="float" if cheapest else "text", status="measured" if cheapest else "pending",
                 column=f"cheapest_{tier}_db",
                 renderings=(DASH,) if cheapest is None else (f"{cheapest[0]:.1f}",))
        frag.add(f"{KEY}.cheapest_{tier}_channel", None if cheapest is None else cheapest[1], kind="int",
                 column=f"cheapest_{tier}_channel")
    for key, value in (("channels", len(rows)), ("n_floor_bound", len(bounded)),
                       ("n_measured", len(rows) - len(bounded)), ("n_inside_110", len(inside))):
        frag.add(f"{KEY}.{key}", value, kind="int", column=key)

    frag.notes.append("the requirement is the additional shelf suppression that would land the held-out "
                      "residual on R = 1; the residual is linear in surviving shelf power, so it is "
                      "10 log10 R and needs no further modelling")
    frag.notes.append("the 110 ns columns are the requirement on top of the operative BAO-preserving cut, "
                      "which has already taken its own suppression; a negative value is margin in hand")
    for tier, word in (("dilation", "the two dilations"), ("growth", "the growth rate")):
        counts = ", ".join(f"{sum(1 for v, _ in measured[tier] if v <= db)} at {db:g} dB" for db in CURVE_DB)
        frag.notes.append(f"on top of the 110 ns cut, a protector brings {word} inside on {counts}, counted "
                          f"over the {len(measured[tier])} channels whose requirement is a measurement")
    if bounded:
        frag.notes.append(f"floor-bound channels ({_channel_list(bounded)}) are excluded from those counts: "
                          "their residual is the sensitivity floor rather than a measurement, so the "
                          "requirement printed is an upper limit and may be zero")
    if unpriced:
        frag.notes.append(f"no world prices {_channel_list(unpriced)}, so no requirement is stated for them")
    frag.notes.append("nothing here proposes a protector, models one, or claims the surviving power is "
                      "removable; the table states what one would have to remove")
    return frag


BUILDERS = (build,)
