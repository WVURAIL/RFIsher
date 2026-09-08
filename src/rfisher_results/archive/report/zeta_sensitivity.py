r"""``tab:tolerance:zeta``: the held-out verdict re-priced at every declared budget.

Chapter 9 prices every ratio against ``r_tol``, the largest residual whose
induced parameter bias stays under ``zeta`` times the statistical error, and
adopts ``zeta = 1``: the loosest reading there is, one whole sigma of bias
allowed. The register declares that choice as ``provisional``
(``science.systematic_budget.primary_zeta``) and names the tighter budgets a
collaboration might set instead
(``science.systematic_budget.sensitivity_zeta``), and until this fragment
nothing in the code evaluated them: the sensitivity values were documentation.
The chapter asserted that the verdict does not turn on the convention and
never showed it. This table shows it, and the budgets are read from the
register rather than restated here, so a changed register changes the rows.

Why one column of arithmetic is enough. The tolerance is exactly linear in
the budget. ``scripts/bias_tolerance.py`` builds it as
``zeta * sigma / |dtheta/dr|`` (``evaluate_raw``, both the noise-normalized
and the reported-amplitude form), and the world banks the archive prices
against build the same quantity at ``zeta = 1``, as ``min`` over the accepted
integration times of ``sig[p] / abs(dth[p])``
(:func:`rfisher_results.archive.worlds.compute_tolerances`). The response
stability gate that decides which of those times are accepted compares a
*ratio* of tolerances against a limit (``bias_tolerance.stability``, and the
same quantity in ``evaluate_fisher_point``), so the budget cancels inside the
gate and the accepted set does not move with it. A positive ``zeta`` therefore
scales the minimum of a fixed set of positive numbers:

    ``r_tol(zeta) = zeta * r_tol(1)``   and so   ``R(zeta) = R(1) / zeta``.

A channel is inside at budget ``zeta`` exactly when its published ``zeta = 1``
ratio is at or below ``zeta``. Nothing else in the analysis moves: the
residual, the operating point, the masked fraction and the gate are all
budget-free, so this is a sensitivity in the convention alone and not a
re-run.

The basis is the held-out one. The chapter's other world tables price the
operating point on the calibration block that chose it. This table reads the
ledger's ``<world>_<parameter>_evaluation_R`` --- the same point replayed on
the evaluation block, which the calibration never saw, and the same numbers
:func:`.worlds.build_held_out` prints at ``zeta = 1``. Two cuts are
carried, the operative BAO-preserving 110 ns (``peak2``) and the deployed
200 ns (``deployed``), because those are the two the chapter operates.

Reading the table. Rows descend from the adopted budget to the strictest
declared one, and a smaller ``zeta`` is a *stricter* budget: it allows less
bias, so a count can only fall down a block. A count that rose would be an
arithmetic fault, not a result. The last column names the channels that come
inside on both dilations, since a distance-scale verdict needs both.

Numbers: ``ch09.zeta.n_<parameter|dilations>.<zeta>.<cut>`` for the counts,
``ch09.zeta.inside_dilations.<zeta>.<cut>`` for the names,
``ch09.zeta.n_scored.<cut>`` and the budget-free
``ch09.zeta.least_<growth|dilation>_R.<cut>`` with the channel that holds it
--- the tightest budget at which that tier still admits anything at all.

What the table does not cover. It carries two of the four worlds, not the
no-filter and 55 ns ones; it reports the held-out basis only; and it counts
what the ledger scored, so a channel whose stability gate accepted no
integration time is absent from every count rather than failing in it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from rfisher import selection_policy

from . import core
from .core import Fragment, Run
from .tolerance_channels import sci
from .worlds import DILATIONS, GROWTH, PARAM_LABEL, SECTION
from ..worlds import WORLD_LABEL

NAME = "zeta_sensitivity"
LABEL = "tab:tolerance:zeta"
KEY = "ch09.zeta"
PRIMARY_ID = "science.systematic_budget.primary_zeta"
SENSITIVITY_ID = "science.systematic_budget.sensitivity_zeta"
CUTS = (("peak2", "110"), ("deployed", "200"))          # the two cuts the chapter operates
DAGGER = r"$^{\dagger}$"

HEADER = (r"$\zeta$", "cut", "scored", rf"$R_{{{PARAM_LABEL[GROWTH]}}} \le 1$") \
    + tuple(rf"$R_{{{PARAM_LABEL[p]}}} \le 1$" for p in DILATIONS) \
    + ("both dilations", "inside")
ALIGN = "llr" + "r" * (1 + len(DILATIONS)) + "rl"


def _num(value):
    """A finite float, or ``None``: a refused ratio reaches the ledger as null or NaN."""
    try:
        return float(value) if value is not None and math.isfinite(float(value)) else None
    except (TypeError, ValueError):
        return None


def zetas() -> tuple[float, ...]:
    """The declared budgets, the adopted one first and the rest loosest first.

    The register states the sensitivity list twice --- on the primary
    decision and as its own decision --- so the union is taken: a budget
    declared in only one of them still earns a row, and a drift between the
    two entries shows up as an extra row rather than silently choosing one.
    """
    primary = float(selection_policy.value(PRIMARY_ID))
    declared = [float(v) for v in selection_policy.decision(PRIMARY_ID).sensitivity_values]
    declared += [float(v) for v in selection_policy.value(SENSITIVITY_ID)]
    return (primary,) + tuple(sorted({v for v in declared if v != primary and v > 0.0}, reverse=True))


def ratio(section, world: str, parameter: str, zeta: float):
    """The held-out ``R`` at this budget, or ``None`` where the ledger scored none.

    ``R(zeta) = R(1) / zeta`` is exact, not an approximation: the tolerance is
    ``zeta`` times a budget-free minimum (see the module docstring), and the
    budget cancels out of the stability gate that fixes which times that
    minimum is taken over.
    """
    value = _num(section.get(f"{world}_{parameter}_evaluation_R"))
    return None if value is None or not (zeta > 0.0) else value / zeta


def _pair(section, world: str):
    """The larger of the two dilation ratios at ``zeta = 1``, or ``None``.

    A distance-scale verdict needs both dilations, so the pair is scored on
    the worse of the two and is undefined unless the ledger carries both.
    """
    values = [_num(section.get(f"{world}_{p}_evaluation_R")) for p in DILATIONS]
    return max(values) if all(v is not None for v in values) else None


@dataclass(frozen=True)
class Tally:
    """One (budget, cut) cell of the table: who is inside, and who was scored."""

    zeta: float
    world: str
    scored: tuple                          # channels the ledger scored in this world
    inside: dict                           # parameter -> channels with R(zeta) <= 1
    inside_dilations: tuple
    floor_bound_inside: tuple              # of those, the ones whose ratios are upper limits


def tally(channels, world: str, zeta: float) -> Tally:
    """Count the channels inside the budget on each parameter and on the dilation pair."""
    parameters = (GROWTH,) + DILATIONS
    scored, inside, pairs, bound = [], {p: [] for p in parameters}, [], []
    for c in channels:
        section = c.section(SECTION)
        if any(ratio(section, world, p, zeta) is not None for p in parameters):
            scored.append(c.channel)
        for p in parameters:
            value = ratio(section, world, p, zeta)
            if value is not None and value <= 1.0:
                inside[p].append(c.channel)
        pair = _pair(section, world)
        if pair is not None and pair <= zeta:
            pairs.append(c.channel)
            if bool(section.get("floor_bound")):
                bound.append(c.channel)
    return Tally(zeta, world, tuple(scored), {p: tuple(v) for p, v in inside.items()},
                 tuple(pairs), tuple(bound))


def least(channels, world: str, parameters) -> tuple:
    """``(channel, R)`` of the channel that comes closest over ``parameters`` at ``zeta = 1``.

    Read it as a budget rather than as a ratio. A channel is inside at ``zeta``
    exactly when its published ratio is at or below it, so this least ratio is
    the tightest budget the tier still admits anything at: every stricter
    budget leaves it empty. It says what the convention would have to be for
    the band to admit anything at all there.
    """
    best = (None, math.inf)
    for c in channels:
        s = c.section(SECTION)
        values = [_num(s.get(f"{world}_{p}_evaluation_R")) for p in parameters]
        if any(v is None for v in values):
            continue
        worst = max(values)
        if worst < best[1]:
            best = (c.channel, worst)
    return best


def _channel_list(channels, bound=()) -> str:
    """``ch21, ch29`` for a note; the empty set is 'none', which is a result here."""
    return ", ".join(f"ch{c:02d}" + ("*" if c in bound else "") for c in sorted(channels)) or "none"


def _cell_list(channels, bound=()) -> str:
    """The same list for a table cell, with the dagger the notes gloss."""
    return ", ".join(f"ch{c:02d}" + (DAGGER if c in bound else "") for c in sorted(channels)) or "none"


def _zeta_text(zeta: float) -> str:
    return f"{zeta:g}"


def _zeta_key(zeta: float) -> str:
    """A key-safe budget: 1 -> ``z1``, 0.5 -> ``z0p5``, so keys sort with the rows."""
    return "z" + _zeta_text(zeta).replace(".", "p")


def build(run: Run) -> Fragment:
    """``tab:tolerance:zeta``: the held-out counts at each declared systematic budget."""
    frag = Fragment(NAME, LABEL, "")
    channels = [c for c in sorted(run.channels, key=lambda c: c.channel)
                if c.has(SECTION) and _num(c.section(SECTION).get("r_evaluation")) is not None]
    if not channels:
        frag.tex = ""
        frag.notes.append("no channel carries a held-out residual: the run predates the replay, so there is "
                          "nothing to re-price against the declared budgets")
        return frag

    budgets = zetas()
    rows, breaks = [], []
    tallies = {}
    for zeta in budgets:
        if rows:
            breaks.append(len(rows))
        for world, tag in CUTS:
            t = tally(channels, world, zeta)
            tallies[(zeta, world)] = t
            zk = _zeta_key(zeta)
            row = {"zeta": zeta, "cut": tag}

            def add(column, value, **kw):
                frag.add(f"{KEY}.{column}.{zk}.{tag}", value, row=row, column=column, **kw)

            cells = [f"${_zeta_text(zeta)}$" if world == CUTS[0][0] else "", WORLD_LABEL[world],
                     str(len(t.scored))]
            for p in (GROWTH,) + DILATIONS:
                cells.append(str(len(t.inside[p])))
                add(f"n_{p}", len(t.inside[p]), kind="int", renderings=(str(len(t.inside[p])),))
                add(f"inside_{p}", _channel_list(t.inside[p]), kind="text",
                    renderings=(_channel_list(t.inside[p]),))
            cells.append(str(len(t.inside_dilations)))
            cells.append(_cell_list(t.inside_dilations, t.floor_bound_inside))
            add("n_dilations", len(t.inside_dilations), kind="int",
                renderings=(str(len(t.inside_dilations)),))
            add("inside_dilations", _channel_list(t.inside_dilations, t.floor_bound_inside), kind="text",
                renderings=(_channel_list(t.inside_dilations, t.floor_bound_inside),))
            rows.append(cells)
    frag.tex = core.booktabs(HEADER, rows, ALIGN, midrules=tuple(breaks))

    frag.add(f"{KEY}.channels", len(channels), kind="int", column="channels")
    frag.add(f"{KEY}.budgets", len(budgets), kind="int", column="budgets")
    for zeta in budgets:
        frag.add(f"{KEY}.zeta.{_zeta_key(zeta)}", zeta, precision=2, row={"zeta": zeta}, column="zeta")
    closest = {}
    for world, tag in CUTS:
        scored = tallies[(budgets[0], world)].scored
        frag.add(f"{KEY}.n_scored.{tag}", len(scored), kind="int", row={"cut": tag}, column="scored")
        for name, parameters in (("growth", (GROWTH,)), ("dilation", DILATIONS)):
            ch, value = least(channels, world, parameters)
            closest[(world, name)] = (ch, value)
            if ch is None:
                continue
            frag.add(f"{KEY}.least_{name}_R.{tag}", value, row={"cut": tag}, column=f"least_{name}_R",
                     status="bounded", renderings=(sci(value).replace("\\times", "x"),))
            frag.add(f"{KEY}.least_{name}_channel.{tag}", ch, kind="int", row={"cut": tag},
                     column=f"least_{name}_channel")

    # two ways to be absent from the counts, and they are different facts: a channel the replay
    # left no held-out residual for is not in the table at all, and a channel in the table whose
    # gate accepted no time in one world is scored in the other
    no_replay = sorted(c.channel for c in run.channels
                       if c.has(SECTION) and _num(c.section(SECTION).get("r_evaluation")) is None)
    ungated = {tag: sorted(set(c.channel for c in channels) - set(tallies[(budgets[0], world)].scored))
               for world, tag in CUTS}
    floor_bound = sorted(c.channel for c in channels if bool(c.section(SECTION).get("floor_bound")))

    frag.notes.append(f"layout: one {len(HEADER)}-column tabular, natural width 413pt at 11pt (measured by "
                      "boxing the fragment in an 11pt Latin Modern document and reading back its width); it sets "
                      "upright inside the 469.8pt text block unscaled, with a midrule between budgets")
    frag.notes.append("zeta is the share of the statistical error the induced bias may take: r_tol is the largest "
                      "residual whose induced parameter bias stays under zeta sigma, and the chapter adopts "
                      f"zeta = {_zeta_text(budgets[0])}, one whole sigma, which is the loosest reading there is")
    frag.notes.append("the re-pricing is exact arithmetic, not a re-run: scripts/bias_tolerance.py builds the "
                      "tolerance as zeta * sigma / |dtheta/dr| (evaluate_raw) and the world banks take the zeta = 1 "
                      "form sig/|dth| read at the declared target integration T*, falling back to the smallest "
                      "accepted elsewhere only where the stability gate refuses T* (archive.worlds.compute_tolerances), "
                      "while the response-stability gate that fixes which times are accepted compares a ratio of "
                      "tolerances, in which zeta cancels; so r_tol(zeta) = zeta * r_tol(1) exactly, R(zeta) = "
                      "R(1)/zeta, and a channel is inside at zeta exactly when its published ratio is at or below it")
    frag.notes.append("a smaller zeta is a stricter budget -- less bias allowed, a smaller tolerance, a larger R -- "
                      "so every count can only fall as the rows descend; a count that rose would be an arithmetic "
                      "fault rather than a result")
    frag.notes.append("basis: the held-out ratios <world>_<parameter>_evaluation_R, the channel's own operating "
                      "point replayed on the evaluation block the calibration never saw, the same numbers "
                      f"tab:tolerance:worlds_heldout prints at zeta = {_zeta_text(budgets[0])}; the calibration-block "
                      "verdict is not restated here")
    for world, tag in CUTS:
        top, strict = tallies[(budgets[0], world)], tallies[(budgets[-1], world)]
        frag.notes.append(
            f"verdict at the {tag} ns cut, out of {len(top.scored)} scored channels: both dilations inside for "
            f"{len(top.inside_dilations)} at zeta = {_zeta_text(budgets[0])} "
            f"({_channel_list(top.inside_dilations)}), for {len(strict.inside_dilations)} at the strictest declared "
            f"zeta = {_zeta_text(budgets[-1])} ({_channel_list(strict.inside_dilations)}); the growth rate inside "
            + (f"for {len(top.inside[GROWTH])} at zeta = {_zeta_text(budgets[0])} "
               f"({_channel_list(top.inside[GROWTH])})" if top.inside[GROWTH]
               else "for none, at any declared budget"))
    for name, tier in (("growth", "growth rate"), ("dilation", "dilation pair")):
        parts = []
        for world, tag in CUTS:
            ch, value = closest[(world, name)]
            if ch is not None:
                parts.append(f"{tag} ns: zeta = {core.fmt(value, 3, sig=True)} on ch{ch:02d}")
        if parts:
            frag.notes.append(f"the tightest budget the {tier} still admits a channel at, which is just the least "
                              "published ratio on that tier because a channel is inside at zeta exactly when its "
                              "ratio is at or below it -- " + "; ".join(parts)
                              + "; every stricter budget leaves the tier empty")
    if floor_bound:
        frag.notes.append(f"floor-bound channels ({_channel_list(floor_bound)}, daggered in the last column when "
                          "they appear): every kept frame sits at the sensitivity floor, so their ratios are upper "
                          "limits; one of them counted inside is genuinely inside, since the true residual is lower "
                          "still, but one counted outside may not be, so each count is a lower bound on that "
                          "channel's tier")
    if no_replay:
        frag.notes.append(f"outside the table entirely ({_channel_list(no_replay)}): the run carries no held-out "
                          "residual for these channels, so they neither pass nor fail at any budget and are in no "
                          "denominator here")
    for tag, missing in ungated.items():
        if missing:
            frag.notes.append(f"scored in the table but not at the {tag} ns cut ({_channel_list(missing)}): that "
                              "world's stability gate accepted no integration time for the channel's bins, so the "
                              "row's denominator is smaller than the number of channels listed")
    frag.notes.append("scope: two of the four worlds, the operative 110 ns and the deployed 200 ns, on the held-out "
                      "basis only; zeta rescales the tolerance and nothing else, so the residual, the operating "
                      "point, the masked fraction and the stability gate are the same in every row, and the table "
                      "is a sensitivity in the budget convention rather than in the analysis")
    return frag


BUILDERS = (build,)
