"""Conditional delay-cut scenarios rendered from an archive ledger.

The Fisher banks price mode loss, while the separate suppression constants
are hypothetical. Neither the coordinate map nor a scalar auto-power shelf
measures complex-visibility transfer. Historical ledgers retain their original
tolerances; rendering does not authenticate or recompute their analysis.
Minimum frontier scores are booked allowances, not physical class bounds.
Evaluation policies can differ from calibration knees and need separate
identities. Era-conditioned retrospective replay is not a prospective holdout.
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
    "Conditional delay-cut scenarios behind Table~\\ref{tab:tolerance:worlds}. "
    "Four rows per channel: the hypothetical shelf-suppression credit, the resulting "
    "booked residual allowance at the calibration operating point, and "
    "$R = r_{\\rm sys}/r_{\\rm tol}$ for each parameter against that world's bank. "
    "The suppression credits are assumptions, not measured filter attenuation or "
    "complex-visibility transfer. Tolerances are retained in the numerical ledger. ")


def tolerance_note(run: Run) -> str:
    """Describe the recorded time contract without relabelling older results."""
    contract = run.run.get("worlds_contract") or {}
    rule = contract.get("time_rule")
    if rule == "target_only":
        years = _num(contract.get("target_years"))
        if years is not None and years > 0:
            return (f"Tolerances use the declared target of {years:g} on-sky year(s), "
                    "taking each parameter's minimum over every overlapping forecast bin; "
                    "joint dilation results require both dilations. Refused target-time cells remain unpriced. "
                    "No alternative integration time supplies a refused tolerance.")
    elif rule == "accepted_time_minimum":
        return ("This historical ledger uses the minimum over the integration times accepted "
                "by each world's response-stability gate. Those historical tolerances are "
                "preserved; rendering does not recompute them at a new target time.")
    return ("The integration-time convention is not recorded in this ledger. Its original "
            "tolerances are preserved; rendering does not authenticate or recompute them.")

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
        if value is None:
            return "", None
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
        add(f"{world}_r", r, renderings=(sci(r).replace("\\times", "x"),), status="derived")
        add(f"{world}_R", R, renderings=(sci(R).replace("\\times", "x"),), status="derived")
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
        frag.add(f"{LEDGER_KEY}.r.{world}.ch{ch:02d}", r, row=row, column="r", status="derived",
                 renderings=(sci(r).replace("\\times", "x"),) if r is not None else (DASH,),
                 **({} if r is not None else {"kind": "text"}))
        for p in PARAMETERS:
            R, tol = _num(s.get(f"{world}_{p}_R")), _num(s.get(f"{world}_{p}_r_tol"))
            cells.append(_math(sci(R)) if R is not None else DASH)
            frag.add(f"{LEDGER_KEY}.R.{world}.{p}.ch{ch:02d}", R, row=row, column=p, status="derived",
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
            frag.add(f"{KEY}.best_ratio.{world}", v.best_ratio, row={"world": world}, column="best_ratio", status="derived",
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
    frag.notes.append("the conditional calculation assigns hypothetical suppression credits of "
                      + ", ".join(f"{WORLD_LABEL[w].replace('$', '').replace('~', ' ')} {suppression_db(w):.1f} dB"
                                  for w in WORLD_NAMES if suppression_db(w) > 0)
                      + " (rfisher.residual.DELAY_SUPPRESSION_DB); the recorded tolerance comes from the Fisher bank "
                        "built with that mode cut. These credits do not measure filter attenuation.")
    frag.notes.append(f"verdict: {len(deployed.passing)} of {deployed.channels} scored channels reach R <= 1 in the "
                      f"deployed 200 ns world ({_channel_list(deployed.passing)}); the closest is "
                      + (f"ch{deployed.best_channel:02d} at R = {core.fmt(deployed.best_ratio, 3, sig=True)}"
                         if deployed.best_channel is not None else "none")
                      + f", and with no filter {len(verdicts['none'].passing)} pass")
    frag.notes.append("the residual entering every world is the channel's own operating point on its calibration "
                      "block (the knee of the mask-against-residual frontier), with no delay credit: that is the "
                      "convention the rest of the chapter uses, and the worlds are the only place a credit is taken")
    frag.notes.append(tolerance_note(run))
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
                          "different worlds; incomplete parameter sets remain unpriced and cannot establish a "
                          "combined pass. The "
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
                             caption=LEDGER_CAPTION + tolerance_note(run), label=LEDGER_LABEL)
    frag.notes.append(f"layout: a longtable of {len(LEDGER_HEADER)} columns, four rows per channel (one per "
                      f"world) over {len(channels)} channels, a midrule between channels and the header repeated "
                      "on every page; it carries its own caption and label, so the chapter must input it directly "
                      "rather than wrapping it in a table float")
    frag.notes.append("cut (dB) is an assigned hypothetical suppression credit; r is the corresponding "
                      "booked allowance, not a measured visibility residual; each R uses the world's recorded tolerance")
    frag.notes.append("the tolerances are carried as numbers (appC.worlds.r_tol.*) but not printed: the ratio is what "
                      "the reader needs, and the tolerance changes bank by bank")
    return frag


FLOOR_HEADER = ("ch", r"$r_{\rm floor}$", r"$r_{\rm floor}/r_{\rm point}$", r"best $R_{f\sigma_8}$",
                "world", r"best $R_{\rm dil}$", "world")
FLOOR_ALIGN = "lrr" + "rl" * 2


def _coarse_floor(c: Channel) -> float | None:
    """Minimum booked allowance on the evaluated coarse frontier, or None.

    This is the recorded coarse minimum ratio times its tolerance. It is not
    a lower bound on physical contamination or on unevaluated masking rules.
    """
    sel = c.selection or {}
    ratio, tol = _num(sel.get("coarse_min_R")), _num(sel.get("r_tol"))
    if ratio is None or ratio < 0 or tol is None or not (tol > 0):
        return None
    return ratio * tol


def _best_over(c: Channel, parameters, *, floor: bool):
    """``(world, R, parameter)`` the channel reaches over ``parameters``, at the floor or the point."""
    s = c.section(SECTION)
    tag = "_floor_R" if floor else "_R"
    best = ("", math.inf, "")
    for world in WORLD_NAMES:
        inside = [(_num(s.get(f"{world}_{p}{tag}")), p) for p in parameters]
        inside = [(v, p) for v, p in inside if v is not None]
        if len(inside) != len(parameters):
            continue
        value, param = max(inside)
        if value < best[1]:
            best = (world, value, param)
    return best


def _coarse_floor_best(c: Channel, parameters):
    """Price the displayed allowance using recorded credits and tolerances."""
    floor = _coarse_floor(c)
    if floor is None:
        return "", math.inf, ""
    section = c.section(SECTION)
    best = ("", math.inf, "")
    for world in WORLD_NAMES:
        credit = _num(section.get(f"{world}_suppression_db"))
        tols = [(_num(section.get(f"{world}_{p}_r_tol")), p) for p in parameters]
        if credit is None or any(tol is None or tol <= 0 for tol, _ in tols):
            continue
        residual = floor * 10.0 ** (-credit / 10.0)
        ratio, parameter = max((residual / tol, p) for tol, p in tols)
        if ratio < best[1]:
            best = world, ratio, parameter
    return best


def build_class_floor(run: Run) -> Fragment:
    """``tab:tolerance:classfloor``: minimum booked coarse-frontier allowance.

    The rows and summary price the same coarse minimum in each recorded
    scenario. None of these scalar allowances establishes a physical bound.
    """
    frag = Fragment(FLOOR_NAME, FLOOR_LABEL, "")
    channels = [c for c in sorted(run.channels, key=lambda c: c.channel)
                if _coarse_floor(c) is not None]
    if not channels:
        frag.tex = ""
        frag.notes.append("no channel carries a frontier allowance: the run predates this diagnostic, or no channel's "
                          "calibration surface produced a frontier")
        return frag

    rows = []
    for c in channels:
        s = c.section(SECTION)
        ch = c.channel
        row = {"channel": ch}

        def add(column, value, **kw):
            frag.add(f"{FLOOR_KEY}.{column}.ch{ch}", value, row=row, column=column, **kw)

        floor, point = _coarse_floor(c), _num(s.get("r_point"))
        gw, gr, _ = _coarse_floor_best(c, (GROWTH,))
        dw, dr, _ = _coarse_floor_best(c, DILATIONS)
        share = floor / point if point else math.nan
        cells = [str(ch), f"${sci(floor)}$", f"${core.fmt(share, 3)}$" if math.isfinite(share) else DASH]
        for value, world in ((gr, gw), (dr, dw)):
            cells.append(f"${sci(value)}$" if math.isfinite(value) else DASH)
            cells.append(WORLD_LABEL[world] if world else DASH)
        rows.append(cells)

        add("r_floor", floor, status="derived", renderings=(sci(floor).replace("\\times", "x"),))
        add("floor_over_point", share, precision=3)
        for column, value, world in (("growth_R", gr, gw), ("dilation_R", dr, dw)):
            if math.isfinite(value):
                add(column, value, status="derived", renderings=(sci(value).replace("\\times", "x"),))
                add(f"{column}_world", world, kind="text",
                    renderings=(WORLD_LABEL[world].replace("$", "").replace("~", " "),))
            else:
                add(column, None, kind="text", status="pending", renderings=(DASH,))
                add(f"{column}_world", None, kind="text", status="pending", renderings=(DASH,))

    frag.tex = core.booktabs(FLOOR_HEADER, rows, FLOOR_ALIGN, midrules=_half_band_breaks(channels))

    growth = [(c.channel, _coarse_floor_best(c, (GROWTH,))[1]) for c in channels]
    dil = [(c.channel, _coarse_floor_best(c, DILATIONS)[1]) for c in channels]
    growth_in = [ch for ch, v in growth if v <= 1.0]
    dil_in = [ch for ch, v in dil if v <= 1.0]
    best_growth = min((v for _, v in growth if math.isfinite(v)), default=math.nan)
    best_growth_ch = next((ch for ch, v in growth if v == best_growth), None)
    frag.add(f"{FLOOR_KEY}.channels", len(channels), kind="int", column="channels")
    frag.add(f"{FLOOR_KEY}.n_growth_inside", len(growth_in), kind="int", column="channels")
    frag.add(f"{FLOOR_KEY}.n_dilation_inside", len(dil_in), kind="int", column="channels")
    if best_growth_ch is not None:
        frag.add(f"{FLOOR_KEY}.best_growth_R", best_growth, status="derived", column="R",
                 renderings=(sci(best_growth).replace("\\times", "x"),))
        frag.add(f"{FLOOR_KEY}.best_growth_channel", best_growth_ch, kind="int", column="channel")
    worst = max((v for _, v in growth if math.isfinite(v)), default=math.nan)
    if math.isfinite(worst):
        frag.add(f"{FLOOR_KEY}.worst_growth_R", worst, status="derived", column="R",
                 renderings=(sci(worst).replace("\\times", "x"),))

    frag.notes.append(f"layout: one {len(FLOOR_HEADER)}-column tabular, natural width 336pt at 11pt; it sets "
                      "upright inside the text block unscaled")
    frag.notes.append("the floor is the minimum booked allowance on the evaluated coarse frontier; "
                      "it is not a lower bound on actual residual contamination or on other masking policies")
    frag.notes.append(f"at the floor, and in the most favourable of the four worlds, {len(growth_in)} of "
                      f"{len(channels)} channels reach the growth-rate tolerance ({_channel_list(growth_in)}) and "
                      f"{len(dil_in)} reach both dilations ({_channel_list(dil_in)})")
    if best_growth_ch is not None:
        frag.notes.append(f"the closest the band comes on the growth rate is ch{best_growth_ch:02d} at R = "
                          f"{core.fmt(best_growth, 3, sig=True)}, and the furthest is "
                          f"{core.fmt(worst, 3, sig=True)}")
    frag.notes.append("scope: conditional scalar allowance with hypothetical delay suppression; "
                      "visibility transfer, signal preservation and mask-dependent noise remain unmeasured")
    return frag


HELD_OUT_NAME = "worlds_held_out"
HELD_OUT_LABEL = "tab:tolerance:worlds_heldout"
HELD_OUT_KEY = "ch09.worlds_heldout"
HELD_OUT_HEADER = ("ch", r"$r$ (held out)", r"$110$~ns: $R_{f\sigma_8}$", r"$R_{\rm dil}$",
                   r"$200$~ns: $R_{f\sigma_8}$", r"$R_{\rm dil}$", "basis")
HELD_OUT_ALIGN = "lr" + "r" * 4 + "l"


def build_held_out(run: Run) -> Fragment:
    """Conditional scenarios on the replay block; its policy can differ from the knee."""
    frag = Fragment(HELD_OUT_NAME, HELD_OUT_LABEL, "")
    channels = [c for c in sorted(run.channels, key=lambda c: c.channel)
                if c.has(SECTION) and _num(c.section(SECTION).get("r_evaluation")) is not None]
    if not channels:
        frag.tex = ""
        frag.notes.append("no channel carries a held-out residual: the run predates the replay, or no point "
                          "was replayed on an evaluation block")
        return frag
    rows, inside_110, inside_200, bounded = [], [], [], []
    growth_inside = {"110": [], "200": []}
    for c in channels:
        s_ = c.section(SECTION)
        ch = c.channel
        row = {"channel": ch}

        def add(column, value, **kw):
            frag.add(f"{HELD_OUT_KEY}.{column}.ch{ch}", value, row=row, column=column, **kw)

        r = _num(s_.get("r_evaluation"))
        fb = bool(s_.get("floor_bound"))
        if fb:
            bounded.append(ch)
        cells = [str(ch), f"${sci(r)}$"]
        add("r_evaluation", r, status="derived",
            renderings=(sci(r).replace("\\times", "x"),))
        for world, tag in (("peak2", "110"), ("deployed", "200")):
            g = _num(s_.get(f"{world}_{GROWTH}_evaluation_R"))
            ds = [_num(s_.get(f"{world}_{p}_evaluation_R")) for p in DILATIONS]
            d = max(ds) if all(v is not None for v in ds) else None
            for column, value in ((f"{tag}_growth_R", g), (f"{tag}_dilation_R", d)):
                if value is None:
                    cells.append(DASH)
                    add(column, None, kind="text", status="pending", renderings=(DASH,))
                else:
                    cells.append(f"${sci(value)}$")
                    add(column, value, status="derived", renderings=(sci(value).replace("\\times", "x"),))
            if d is not None and d <= 1.0:
                (inside_110 if tag == "110" else inside_200).append(ch)
            if g is not None and g <= 1.0:
                growth_inside[tag].append(ch)
        cells.append("model/floor" if fb else "model")
        add("basis", "model/floor" if fb else "model", kind="text",
            renderings=("model/floor" if fb else "model",))
        rows.append(cells)
    frag.tex = core.booktabs(HELD_OUT_HEADER, rows, HELD_OUT_ALIGN, midrules=_half_band_breaks(channels))

    for key, value in (("channels", len(channels)), ("n_inside_110", len(inside_110)),
                       ("n_inside_200", len(inside_200)), ("n_floor_bound", len(bounded))):
        frag.add(f"{HELD_OUT_KEY}.{key}", value, kind="int", column=key)
    frag.notes.append("the residual is the replayed diagnostic or selected policy, which may differ "
                      "from the calibration knee; historical full-archive fits prevent an untouched-holdout claim")
    frag.notes.append(f"in the hypothetical 110 ns scenario {len(inside_110)} of {len(channels)} channels reach "
                      f"R <= 1 on the two dilations ({_channel_list(inside_110)}); at the deployed 200 ns cut "
                      f"{len(inside_200)} ({_channel_list(inside_200)}); growth-rate counts are "
                      f"{len(growth_inside['110'])} at 110 ns and {len(growth_inside['200'])} at 200 ns; "
                      "all are conditional scenario counts")
    if bounded:
        frag.notes.append(f"floor-only evaluation assignments ({_channel_list(bounded)}): the replayed allowance "
                          "matches the assigned floor within the recorded numerical tolerance. The ratios are "
                          "conditional assignments, not measurements or confidence limits; this calculation "
                          "does not determine the true retained contamination")
    return frag


BUILDERS = (build, build_ledger, build_class_floor, build_held_out)
