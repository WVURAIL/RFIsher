"""``tab:tolerance:worlds``: what a delay cut would buy, booked on both sides.

Chapter 9 asks the question the delay filter invites: if the pipeline throws
away the low-``k_parallel`` modes anyway, does the pilot residual stop
mattering? The honest answer books the cut twice. The chain gains the shelf
suppression the cut removes (``rfisher.residual.DELAY_SUPPRESSION_DB``), and
the forecast loses the modes the cut removes, so the tolerance is re-derived
from a Fisher bank built under that same cut. Reporting only the first half
is the error the table exists to avoid.

Four worlds, each a published cut: no filter, the two BAO-preserving design
points (55 ns and 110 ns, the ``kfg`` 22 and 44 banks) and the deployed
200 ns (``kfg`` 80). Each channel enters at its own operating point
(:mod:`..operating`), the knee its calibration block chose, and each world
divides that residual by its suppression and prices it against its own bank's
tolerance. ``R = r / r_tol`` per parameter; ``R <= 1`` passes.

Three fragments. ``worlds`` (``tab:tolerance:worlds``) is the chapter table:
one row per channel, the residual under each world and the binding ratio there
--- the largest of the three parameters, which is the one that has to pass.
``worlds_ledger`` (``tab:archive:worlds``) is Appendix~C's: the same rows
opened out to every parameter's ratio, with the tolerance behind it. And
``worlds_class_floor`` (``tab:tolerance:classfloor``) asks the stronger
question.

The class floor. An operating point is a choice, so a ratio quoted there says
only that *this* policy fails. The residual is a functional of the per-frame
shelf estimate alone, so the coarse rule's frontier is the lower envelope of
the ``(f, r_sys)`` plane by construction and its minimum is the least residual
any threshold on that statistic can leave, at any masked fraction, anywhere on
the surface. Priced through the same four worlds, that minimum bounds the whole
class of per-frame masking policies driven by this measurement rather than one
member of it. The third fragment carries it, and the counts it reports --- how
many channels reach each tier *at the floor* --- are the chapter's strongest
claim.

The tolerance is the smallest per-unit-residual bias over the integration
times that pass the registered response-stability gate, taken over the
forecast bins the channel overlaps --- the ledger's own footing
(:mod:`..tolerances`), applied bank by bank.

Numbers: ``ch09.worlds.<column>.chNN`` per cell and ``ch09.worlds.<name>``
for the band-level counts; ``appC.worlds.*`` for the ledger fragment. A
channel with no operating point, or none of whose bins the stability gate
accepted, prints dashes and says so in the notes.

What this table does not claim. It models the cut's mode geometry only. It
says nothing about how well a delay filter removes foregrounds, and a world
is not a statement that the filter has been applied.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from ..worlds import PARAMETERS, WORLD_LABEL, WORLDS, suppression_db
from . import core
from .core import DASH, Channel, Fragment, Run
from .tolerance_channels import sci

NAME = "worlds"
LABEL = "tab:tolerance:worlds"
LEDGER_NAME = "worlds_ledger"
LEDGER_LABEL = "tab:archive:worlds"
FLOOR_NAME = "worlds_class_floor"
FLOOR_LABEL = "tab:tolerance:classfloor"
KEY = "ch09.worlds"
LEDGER_KEY = "appC.worlds"
FLOOR_KEY = "ch09.classfloor"
LEDGER_CAPTION = (
    "The four delay-cut worlds opened out per parameter, behind the binding ratios of "
    "Table~\\ref{tab:tolerance:worlds}. Four rows per channel, one per world: the shelf suppression that "
    "world's cut removes, the residual it leaves at the channel's operating point, and $R = r_{\\rm sys}/"
    "r_{\\rm tol}$ for each of the three parameters against that world's own bank. The tolerances behind the "
    "ratios are carried as numbers rather than printed; the ratio is what the reader needs, and the tolerance "
    "changes bank by bank. Each world's tolerance is a minimum over the integration times its own stability "
    "gate accepts, so a ratio may rise between worlds without the cut removing less power.")
DILATIONS = tuple(p for p in PARAMETERS if p != "fs8")
GROWTH = "fs8"
SECTION = "worlds"
HALF_BAND_BREAK = 25
PARAM_LABEL = {"aperp": r"\alpha_\perp", "apar": r"\alpha_\parallel", "fs8": r"f\sigma_8"}
WORLD_NAMES = tuple(w[0] for w in WORLDS)

HEADER = ("ch", "$z$", "$f$") + tuple(f"{WORLD_LABEL[w]}: $r$ / $R$" for w in WORLD_NAMES)
ALIGN = "lcc" + "r" * len(WORLD_NAMES)
LEDGER_HEADER = ("ch", "world", "cut (dB)", "$r$") + tuple(f"$R_{{{PARAM_LABEL[p]}}}$" for p in PARAMETERS)
LEDGER_ALIGN = "llr" + "r" * (1 + len(PARAMETERS))


def _finite(value) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _num(value):
    return float(value) if _finite(value) else None


def binding(section, world: str) -> tuple[str, object]:
    """``(parameter, R)`` of the world's binding ratio: the largest, the one that must pass."""
    best, name = None, ""
    for p in PARAMETERS:
        value = _num(section.get(f"{world}_{p}_R"))
        if value is not None and (best is None or value > best):
            best, name = value, p
    return name, best


def _math(text: str) -> str:
    return DASH if text == DASH else f"${text}$"


def _row(c: Channel, frag: Fragment, absent: list[str]) -> list[str]:
    """One channel across the four worlds: the residual and the binding ratio in each."""
    s = c.section(SECTION)
    ch = c.channel
    row = {"channel": ch}

    def add(column: str, value, **kw):
        frag.add(f"{KEY}.{column}.ch{ch}", value, row=row, column=column, **kw)

    def gap(column: str, why: str):
        absent.append(f"ch{ch} {column}: {why}")
        add(column, None, kind="text", status="pending", renderings=(DASH,))

    cells = [str(ch)]
    zl, zh = _num(s.get("z_lo")), _num(s.get("z_hi"))
    cells.append(core.fmt_range(zl, zh, 1) if zl is not None and zh is not None else DASH)
    if zl is not None and zh is not None:
        add("z_lo", zl, precision=1)
        add("z_hi", zh, precision=1)
    else:
        gap("z_lo", "the channel overlaps no forecast bin")
        add("z_hi", None, kind="text", renderings=(DASH,))

    f = _num(s.get("masked_fraction"))
    cells.append(_math(core.fmt(f, 3)) if f is not None else DASH)
    if f is not None:
        add("masked_fraction", f, precision=3)
    else:
        gap("masked_fraction", "no operating point on the calibration surface")

    status = str(s.get("status") or "")
    for world in WORLD_NAMES:
        r = _num(s.get(f"{world}_r"))
        name, R = binding(s, world)
        if r is None or R is None:
            cells.append(DASH)
            gap(f"{world}_r", f"no residual to carry through ({status or 'no worlds section'})")
            add(f"{world}_R", None, kind="text", renderings=(DASH,))
            add(f"{world}_binding", None, kind="text", renderings=(DASH,))
            continue
        cells.append(f"${sci(r)}$ / ${sci(R)}$")
        add(f"{world}_r", r, renderings=(sci(r).replace("\\times", "x"),), status="bounded")
        add(f"{world}_R", R, renderings=(sci(R).replace("\\times", "x"),), status="bounded")
        add(f"{world}_binding", name, kind="text", renderings=(PARAM_LABEL.get(name, name),))
    return cells


def _ledger_rows(c: Channel, frag: Fragment) -> list[list[str]]:
    """Four rows, one per world: the cut, the residual and every parameter's ratio."""
    s = c.section(SECTION)
    ch = c.channel
    out = []
    for world in WORLD_NAMES:
        row = {"channel": ch, "world": world}
        r = _num(s.get(f"{world}_r"))
        db = suppression_db(world)
        cells = [str(ch) if world == WORLD_NAMES[0] else "", f"${WORLD_LABEL[world]}$",
                 _math(core.fmt(db, 1)), _math(sci(r)) if r is not None else DASH]
        frag.add(f"{LEDGER_KEY}.suppression_db.{world}.ch{ch:02d}", db, precision=1, row=row, column="suppression_db")
        frag.add(f"{LEDGER_KEY}.r.{world}.ch{ch:02d}", r, row=row, column="r", status="bounded",
                 renderings=(sci(r).replace("\\times", "x"),) if r is not None else (DASH,),
                 **({} if r is not None else {"kind": "text"}))
        for p in PARAMETERS:
            R, tol = _num(s.get(f"{world}_{p}_R")), _num(s.get(f"{world}_{p}_r_tol"))
            cells.append(_math(sci(R)) if R is not None else DASH)
            frag.add(f"{LEDGER_KEY}.R.{world}.{p}.ch{ch:02d}", R, row=row, column=p, status="bounded",
                     renderings=(sci(R).replace("\\times", "x"),) if R is not None else (DASH,),
                     **({} if R is not None else {"kind": "text"}))
            frag.add(f"{LEDGER_KEY}.r_tol.{world}.{p}.ch{ch:02d}", tol, row=row, column=f"{p}_r_tol",
                     renderings=(sci(tol).replace("\\times", "x"),) if tol is not None else (DASH,),
                     **({} if tol is not None else {"kind": "text"}))
        out.append(cells)
    return out


@dataclass(frozen=True)
class Verdict:
    """What the band as a whole does in one world."""

    world: str
    passing: tuple
    channels: int
    best_channel: int | None
    best_ratio: float


def verdict(channels, world: str) -> Verdict:
    """Which channels pass in this world, and which comes closest."""
    passing, best_ch, best = [], None, math.inf
    scored = 0
    for c in channels:
        _, R = binding(c.section(SECTION), world)
        if R is None:
            continue
        scored += 1
        if R <= 1.0:
            passing.append(c.channel)
        if R < best:
            best, best_ch = R, c.channel
    return Verdict(world, tuple(passing), scored, best_ch, best)


def _channel_list(channels) -> str:
    return ", ".join(f"ch{c:02d}" for c in sorted(channels)) or "none"


def _half_band_breaks(channels) -> tuple[int, ...]:
    for i, c in enumerate(channels):
        if c.channel > HALF_BAND_BREAK:
            return (i,) if i else ()
    return ()


def build(run: Run) -> Fragment:
    """``tab:tolerance:worlds``: the chapter table, one row per channel."""
    frag = Fragment(NAME, LABEL, "")
    absent: list[str] = []
    channels = sorted((c for c in run.channels if c.has(SECTION)), key=lambda c: c.channel)
    if not channels:
        frag.tex = ""
        frag.notes.append("no channel carries a worlds section: the run predates the world table, or the "
                          "forecast banks were not readable when it aggregated")
        return frag
    rows = [_row(c, frag, absent) for c in channels]
    frag.tex = core.booktabs(HEADER, rows, ALIGN, midrules=_half_band_breaks(channels))

    verdicts = {w: verdict(channels, w) for w in WORLD_NAMES}
    frag.add(f"{KEY}.channels", len(channels), kind="int", column="channels")
    for world in WORLD_NAMES:
        v = verdicts[world]
        frag.add(f"{KEY}.n_passing.{world}", len(v.passing), kind="int", row={"world": world}, column="n_passing")
        frag.add(f"{KEY}.n_scored.{world}", v.channels, kind="int", row={"world": world}, column="n_scored")
        frag.add(f"{KEY}.suppression_db.{world}", suppression_db(world), precision=1, row={"world": world},
                 column="suppression_db")
        if v.best_channel is not None:
            frag.add(f"{KEY}.best_ratio.{world}", v.best_ratio, row={"world": world}, column="best_ratio", status="bounded",
                     renderings=(sci(v.best_ratio).replace("\\times", "x"),))
            frag.add(f"{KEY}.best_channel.{world}", v.best_channel, kind="int", row={"world": world},
                     column="best_channel")

    deployed = verdicts["deployed"]
    frag.notes.append(f"layout: one {len(HEADER)}-column tabular, natural width 452pt at 11pt; it sets upright inside "
                      f"the 469.8pt text block unscaled, with a midrule after channel {HALF_BAND_BREAK} for the "
                      "half-band break")
    frag.notes.append("each cell is the residual under that world's cut over the binding ratio R = r / r_tol, the "
                      "largest of the three parameters; R <= 1 passes; the per-parameter ratios and the tolerances "
                      f"behind them are the companion fragment {LEDGER_NAME} ({LEDGER_LABEL}, Appendix C)")
    frag.notes.append("both sides of the cut are booked: the chain gains the suppression "
                      + ", ".join(f"{WORLD_LABEL[w].replace('$', '').replace('~', ' ')} {suppression_db(w):.1f} dB"
                                  for w in WORLD_NAMES if suppression_db(w) > 0)
                      + " (rfisher.residual.DELAY_SUPPRESSION_DB) and the tolerance is re-derived from the Fisher bank "
                        "built under the same cut, so no world claims the credit without the cost")
    frag.notes.append(f"verdict: {len(deployed.passing)} of {deployed.channels} scored channels reach R <= 1 in the "
                      f"deployed 200 ns world ({_channel_list(deployed.passing)}); the closest is "
                      + (f"ch{deployed.best_channel:02d} at R = {core.fmt(deployed.best_ratio, 3, sig=True)}"
                         if deployed.best_channel is not None else "none")
                      + f", and with no filter {len(verdicts['none'].passing)} pass")
    frag.notes.append("the residual entering every world is the channel's own operating point on its calibration "
                      "block (the knee of the mask-against-residual frontier), with no delay credit: that is the "
                      "convention the rest of the chapter uses, and the worlds are the only place a credit is taken")
    frag.notes.append("the tolerance is the smallest per-unit-residual bias over the integration times passing the "
                      "registered response-stability gate, over the forecast bins the channel overlaps (the ledger's "
                      "own footing), taken bank by bank so each world prices against its own forecast")
    frag.notes.append("the tolerance is a minimum over a gate-filtered set, and the gate accepts different "
                      "integration times in different worlds, so a tolerance need not move monotonically with cut "
                      "depth; a ratio that rises between adjacent columns is a statement about which times survived "
                      "the gate in each world, not about the cut removing less")
    frag.notes.append("scope: the worlds model the cut's mode geometry only; the table says nothing about how well a "
                      "delay filter removes foregrounds, and no world asserts that the filter has been applied")
    uneven = []
    for c in channels:
        s = c.section(SECTION)
        priced = {w: frozenset(p for p in PARAMETERS if _num(s.get(f"{w}_{p}_R")) is not None) for w in WORLD_NAMES}
        if len(set(priced.values())) > 1:
            uneven.append(c.channel)
    if uneven:
        frag.notes.append(f"on {_channel_list(uneven)} the stability gate accepts a different parameter set in "
                          "different worlds, so the binding ratio is over different parameters from column to "
                          "column and a fall between columns there is not by itself a gain from the cut; the "
                          f"per-parameter ratios in {LEDGER_NAME} are the ones to compare")
    if absent:
        frag.notes.append("absent cells: " + "; ".join(absent[:12])
                          + (f" (and {len(absent) - 12} more)" if len(absent) > 12 else ""))
    return frag


def build_ledger(run: Run) -> Fragment:
    """``tab:archive:worlds``: every parameter's ratio and the tolerance behind it."""
    frag = Fragment(LEDGER_NAME, LEDGER_LABEL, "")
    channels = sorted((c for c in run.channels if c.has(SECTION)), key=lambda c: c.channel)
    if not channels:
        frag.tex = ""
        frag.notes.append("no channel carries a worlds section")
        return frag
    rows, breaks = [], []
    for c in channels:
        if rows:
            breaks.append(len(rows))
        rows.extend(_ledger_rows(c, frag))
    # four rows per channel is taller than any page: a float would silently drop the tail,
    # so the fragment is a longtable and carries its own caption and label
    frag.tex = core.booktabs(LEDGER_HEADER, rows, LEDGER_ALIGN, midrules=tuple(breaks), longtable=True,
                             caption=LEDGER_CAPTION, label=LEDGER_LABEL)
    frag.notes.append(f"layout: a longtable of {len(LEDGER_HEADER)} columns, four rows per channel (one per "
                      f"world) over {len(channels)} channels, a midrule between channels and the header repeated "
                      "on every page; it carries its own caption and label, so the chapter must input it directly "
                      "rather than wrapping it in a table float")
    frag.notes.append("cut (dB) is the shelf suppression the world's delay cut removes; r is the operating point's "
                      "residual after it; each R is r over that world's own bank tolerance for the parameter")
    frag.notes.append("the tolerances are carried as numbers (appC.worlds.r_tol.*) but not printed: the ratio is what "
                      "the reader needs, and the tolerance changes bank by bank")
    return frag


FLOOR_HEADER = ("ch", r"$r_{\rm floor}$", r"$r_{\rm floor}/r_{\rm point}$", r"best $R_{f\sigma_8}$",
                "world", r"best $R_{\rm dil}$", "world")
FLOOR_ALIGN = "lrr" + "rl" * 2


def _best_over(c: Channel, parameters, *, floor: bool):
    """``(world, R, parameter)`` the channel reaches over ``parameters``, at the floor or the point."""
    s = c.section(SECTION)
    tag = "_floor_R" if floor else "_R"
    best = ("", math.inf, "")
    for world in WORLD_NAMES:
        inside = [(_num(s.get(f"{world}_{p}{tag}")), p) for p in parameters]
        inside = [(v, p) for v, p in inside if v is not None]
        if not inside:
            continue
        value, param = max(inside)
        if value < best[1]:
            best = (world, value, param)
    return best


def build_class_floor(run: Run) -> Fragment:
    """``tab:tolerance:classfloor``: the least residual any threshold on this statistic can leave.

    One row per channel: the frontier's floor, how far below the operating
    point it sits, and the best ratio any of the four worlds reaches *there*
    for the growth rate and for the dilations. A channel outside at the floor
    is outside for every threshold on the statistic, not just for the one the
    knee chose.
    """
    frag = Fragment(FLOOR_NAME, FLOOR_LABEL, "")
    channels = [c for c in sorted(run.channels, key=lambda c: c.channel)
                if c.has(SECTION) and _num(c.section(SECTION).get("r_floor")) is not None]
    if not channels:
        frag.tex = ""
        frag.notes.append("no channel carries a frontier floor: the run predates the class bound, or no channel's "
                          "calibration surface produced a frontier")
        return frag

    rows = []
    for c in channels:
        s = c.section(SECTION)
        ch = c.channel
        row = {"channel": ch}

        def add(column, value, **kw):
            frag.add(f"{FLOOR_KEY}.{column}.ch{ch}", value, row=row, column=column, **kw)

        floor, point = _num(s.get("r_floor")), _num(s.get("r_point"))
        gw, gr, _ = _best_over(c, (GROWTH,), floor=True)
        dw, dr, _ = _best_over(c, DILATIONS, floor=True)
        share = floor / point if point else math.nan
        cells = [str(ch), f"${sci(floor)}$", f"${core.fmt(share, 3)}$" if math.isfinite(share) else DASH]
        for value, world in ((gr, gw), (dr, dw)):
            cells.append(f"${sci(value)}$" if math.isfinite(value) else DASH)
            cells.append(WORLD_LABEL[world] if world else DASH)
        rows.append(cells)

        add("r_floor", floor, status="bounded", renderings=(sci(floor).replace("\\times", "x"),))
        add("floor_over_point", share, precision=3)
        for column, value, world in (("growth_R", gr, gw), ("dilation_R", dr, dw)):
            if math.isfinite(value):
                add(column, value, status="bounded", renderings=(sci(value).replace("\\times", "x"),))
                add(f"{column}_world", world, kind="text",
                    renderings=(WORLD_LABEL[world].replace("$", "").replace("~", " "),))
            else:
                add(column, None, kind="text", status="pending", renderings=(DASH,))
                add(f"{column}_world", None, kind="text", status="pending", renderings=(DASH,))

    frag.tex = core.booktabs(FLOOR_HEADER, rows, FLOOR_ALIGN, midrules=_half_band_breaks(channels))

    growth = [(c.channel, _best_over(c, (GROWTH,), floor=True)[1]) for c in channels]
    dil = [(c.channel, _best_over(c, DILATIONS, floor=True)[1]) for c in channels]
    growth_in = [ch for ch, v in growth if v <= 1.0]
    dil_in = [ch for ch, v in dil if v <= 1.0]
    best_growth = min((v for _, v in growth if math.isfinite(v)), default=math.nan)
    best_growth_ch = next((ch for ch, v in growth if v == best_growth), None)
    frag.add(f"{FLOOR_KEY}.channels", len(channels), kind="int", column="channels")
    frag.add(f"{FLOOR_KEY}.n_growth_inside", len(growth_in), kind="int", column="channels")
    frag.add(f"{FLOOR_KEY}.n_dilation_inside", len(dil_in), kind="int", column="channels")
    if best_growth_ch is not None:
        frag.add(f"{FLOOR_KEY}.best_growth_R", best_growth, status="bounded", column="R",
                 renderings=(sci(best_growth).replace("\\times", "x"),))
        frag.add(f"{FLOOR_KEY}.best_growth_channel", best_growth_ch, kind="int", column="channel")
    worst = max((v for _, v in growth if math.isfinite(v)), default=math.nan)
    if math.isfinite(worst):
        frag.add(f"{FLOOR_KEY}.worst_growth_R", worst, status="bounded", column="R",
                 renderings=(sci(worst).replace("\\times", "x"),))

    frag.notes.append(f"layout: one {len(FLOOR_HEADER)}-column tabular, natural width 336pt at 11pt; it sets "
                      "upright inside the text block unscaled")
    frag.notes.append("the floor is the least r_sys anywhere on the coarse rule's own frontier, which is the lower "
                      "envelope of the (f, r_sys) plane by construction because the residual is a functional of the "
                      "per-frame shelf estimate alone; it is therefore a bound on every threshold on that statistic "
                      "and not a setting anyone would operate at")
    frag.notes.append(f"at the floor, and in the most favourable of the four worlds, {len(growth_in)} of "
                      f"{len(channels)} channels reach the growth-rate tolerance ({_channel_list(growth_in)}) and "
                      f"{len(dil_in)} reach both dilations ({_channel_list(dil_in)})")
    if best_growth_ch is not None:
        frag.notes.append(f"the closest the band comes on the growth rate is ch{best_growth_ch:02d} at R = "
                          f"{core.fmt(best_growth, 3, sig=True)}, and the furthest is "
                          f"{core.fmt(worst, 3, sig=True)}")
    frag.notes.append("scope: this bounds masking, not subtraction; it is at frame resolution, because the products "
                      "carry one spectrum per frame and nothing within one; and it prices a residual transferred "
                      "across the allocation rather than measured in the bins it protects")
    return frag


BUILDERS = (build, build_ledger, build_class_floor)
