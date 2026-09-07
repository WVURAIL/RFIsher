"""The ch06 held-out summary (``tab:detection:heldout``): one row per channel,
the point frozen on the calibration block and its replay on the disjoint
evaluation block.

The point. When the selector returned a point (``selection.status``
``feasible``, ``selection.rho`` set) the row prints it. No channel of the
2026-09-07 run has one: the within-era drift screen refused every channel
(``selection.claim_status`` ``diagnostic``), so the row prints the
least-residual point of the evaluated calibration surface, which the run
replayed on the evaluation block as a declared diagnostic
(``selection.diagnostic_*``; ``selection.diagnostic_basis`` names it), with a
dagger on the rank and ``diagnostic`` in the claim column. Where the floor is
refused and frames lack a shelf estimate the selector refused outright
(``selection.status`` ``refused``): no point, no replay, every value cell
dashed.

Columns (ledger keys as ``section.key``; ``a | b`` is the selected value or
the diagnostic point's; numeric cells are math mode; an absent or undefined
value prints as ``--`` and the fragment's notes say why):

``ch``
    The channel number.
``rho``
    ``selection.rho | selection.diagnostic_rho``, the rank; a dagger marks
    the diagnostic point.
``eta``
    ``selection.eta | selection.diagnostic_eta``, the display multiplier, with
    the exact Q16 integer ``selection.eta_q16 | selection.diagnostic_eta_q16``
    in parentheses.
``masked_fraction_calibration``
    ``selection.masked_fraction_calibration |
    selection.diagnostic_masked_fraction``: the masked fraction on the
    calibration block at the printed point.
``masked_fraction_evaluation``
    ``selection.masked_fraction_evaluation`` with its 16--84% acquisition-block
    bootstrap interval ``masked_fraction_evaluation_q16`` / ``_q84``; the
    interval prints as ``[--]`` when the value exists but no interval was
    formed (``selection.bootstrap_blocks_evaluation`` below the minimum).
``r_sys_evaluation``
    ``selection.r_sys_evaluation``, the kept-frame mean systematic residual on
    the evaluation block, with ``r_sys_evaluation_q16`` / ``_q84``; undefined
    (dashed) when the replay kept no frame (``selection.kept_evaluation`` 0).
    Marks: ``a`` when the chain gain is the archive-wide chain
    (``selection.gain_basis``); ``c`` when tau_c is refused and the gain is
    the sidereal-day cap, ``b`` when tau_c is bounded above
    (``chain.tau_quality``, or ``chain_archive.tau_quality`` under the
    archive-wide gain); ``b``/``c`` values are upper bounds.
``R``
    ``selection.R_evaluation`` = ``r_sys_evaluation / r_tol`` on the evaluation
    block (``R <= 1`` passes); an upper bound where ``r_sys_evaluation`` is.
``false_alarm_rate``
    ``selection.false_alarm_rate``: the replay's masked fraction where the
    evaluation block is a verified transmitter-off era
    (``screening.off_era_current``; ``selection.false_alarm_basis``);
    dashed elsewhere, where no false-alarm rate is measurable.
``false_alarm_rate_flag``
    ``blocks.evaluation_flag_rate`` on the same off-era blocks: the coarse
    survey flag's false-alarm rate on the block; dashed elsewhere, where the
    flag rate is an occupancy indicator, not a false-alarm rate.
``status``, ``claim_status``, ``refusal``
    ``selection.status``, ``selection.claim_status`` and ``selection.refusal``
    in short form (:func:`short_refusal`; the number carries the full text).

Numbers: ``ch06.heldout.<column>.chNN`` for every cell above (the interval
bounds as ``masked_fraction_evaluation_q16`` etc.; ``eta_q16`` beside
``eta``), with the text numbers ``point_basis`` (``selected`` | the
diagnostic basis | ``none``), ``false_alarm_basis``, ``gain_basis``,
``tau_quality`` and the count ``kept_evaluation`` that explain a mark or a
dash; ``None`` with status ``refused`` where the ledger carries no value,
status ``bounded`` on residuals whose chain gain is a bound. Band-level
counts ``ch06.heldout.n_channels``, ``n_selected``, ``n_diagnostic``,
``n_refused``, ``n_replayed``, ``n_replay_kept_none``,
``n_off_era_evaluation_blocks``, ``n_false_alarm_measured``,
``n_gain_archive``, ``n_residual_bounded``.
"""
from __future__ import annotations

import math
import re
from typing import Callable, Mapping

from .core import DASH, Channel, Fragment, Run, booktabs, fmt, fmt_int, tex

NAME = "held_out_summary"
LABEL = "tab:detection:heldout"
PREFIX = "ch06.heldout"
DAGGER = r"{}^{\dagger}"
MATH_DASH = r"\mbox{--}"                 # the dash inside a math-mode interval

COLUMNS = ("ch", "rho", "eta", "masked_fraction_calibration", "masked_fraction_evaluation", "r_sys_evaluation", "R",
           "false_alarm_rate", "false_alarm_rate_flag", "status", "claim_status", "refusal")
HEADER = ("ch", r"$\rho$", r"$\eta$ ($\eta_{q16}$)", r"$f_{\rm cal}$", r"$f_{\rm eval}$ [16--84\%]",
          r"$r_{\rm sys,eval}$ [16--84\%]", r"$R_{\rm eval}$", r"$P_{\rm fa}$", r"$P_{\rm fa}^{\rm flag}$",
          "status", "claim", "refusal")
ALIGN = "lrrrrrrrrlll"

SELECTED = "selected"
DIAGNOSTIC = "least-residual point of the calibration surface, replayed as a diagnostic"
TAU_MARKS = {"refused": "c", "bounded_above": "b"}
FLOOR_GAIN_TOLERANCE = 0.01             # r_sys within 1% of floor x gain: every kept frame is booked at the floor


# ------------------------------------------------------------------ helpers
def _finite(value) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _decimals(text: str) -> int:
    """Decimals printed by a plain ``fmt`` rendering (0 when none)."""
    return len(text.split(".")[1]) if "." in text else 0


def fmt_sig(value, digits: int = 3) -> tuple[str, int | None, tuple[str, ...]]:
    """``digits`` significant figures, plain inside ``[0.01, 1000)`` after
    rounding and ``m\\times10^{e}`` outside. Returns the math-mode text, the
    printed decimals (None for the scientific form) and its extra renderings."""
    if not _finite(value):
        return DASH, None, ()
    x = float(value)
    if x == 0.0:
        return "0", 0, ()
    mant, exp_text = f"{x:.{digits - 1}e}".split("e")
    exp = int(exp_text)
    if -2 <= exp < 3:
        decimals = max(digits - 1 - exp, 0)
        return f"{x:.{decimals}f}", decimals, ()
    return f"{mant}\\times10^{{{exp}}}", None, (f"{mant}x10^{{{exp}}}", f"{mant}e{exp}")


def fmt_interval(value, low, high, render: Callable[[float], str]) -> str:
    """``value [low, high]``; ``value [--]`` when the value exists but the interval does not; the dash when neither."""
    if not _finite(value):
        return DASH
    centre = render(value)
    if _finite(low) and _finite(high):
        return f"{centre}\\ [{render(low)}, {render(high)}]"
    return f"{centre}\\ [{MATH_DASH}]"


_REFUSALS = (
    (re.compile(r"candidate rho=(\d+), eta=([\d.]+) retains fewer than (\d+) frames in one era half"),
     lambda m: f"drift screen: $<{m[3]}$ frames/half at $\\rho={m[1]}$, $\\eta={fmt(float(m[2]), 3)}$"),
    (re.compile(r"(early|late) half has (\d+) observed months?; need (\d+)"),
     lambda m: f"drift screen: {m[1]} half {m[2]} months (need {m[3]})"),
    (re.compile(r"(early|late) half spans ([\d.]+) days; need (\d+)"),
     lambda m: f"drift screen: {m[1]} half {float(m[2]):.0f} d (need {m[3]})"),
)


def short_refusal(refusal) -> str:
    """The refusal as one short LaTeX cell (the dash when there is none)."""
    text = str(refusal or "").strip()
    if not text:
        return DASH
    for pattern, render in _REFUSALS:
        m = pattern.search(text)
        if m:
            return render(m)
    text = text.replace("within-era stability refused_insufficient_support: ", "drift screen: ")
    text = text.replace("within-era stability refused_", "drift screen ")
    return tex(text)


def point(sel: Mapping) -> tuple[str, object, object, object, object]:
    """``(basis, rho, eta, eta_q16, masked_fraction_calibration)`` of the point the row prints."""
    if sel.get("rho") is not None:
        return SELECTED, sel.get("rho"), sel.get("eta"), sel.get("eta_q16"), sel.get("masked_fraction_calibration")
    if sel.get("diagnostic_rho") is not None:
        return (DIAGNOSTIC, sel.get("diagnostic_rho"), sel.get("diagnostic_eta"), sel.get("diagnostic_eta_q16"),
                sel.get("diagnostic_masked_fraction"))
    return "", None, None, None, None


def gain_basis(channel: Channel) -> tuple[str, str, str]:
    """``(mark, basis, tau_quality)``: the residual's chain gain and what bounds it.

    ``mark`` is the math-mode superscript for the residual cell (``a`` for the
    archive-wide chain, ``c`` for tau_c refused, ``b`` for bounded above, empty
    when the gain is the era chain with a measured tau_c or no chain section
    exists); ``basis`` is ``selection.gain_basis``; ``tau_quality`` is read from
    the chain that supplied the gain."""
    basis = str(channel.selection.get("gain_basis") or "")
    archive = basis.startswith("archive-wide")
    chain = channel.section("chain_archive") if archive else channel.chain
    quality = str(chain.get("tau_quality") or "")
    letters = ("a" if archive else "") + TAU_MARKS.get(quality, "")
    return (f"{{}}^{{\\mathrm{{{letters}}}}}" if letters else ""), basis, quality


def off_era_block(channel: Channel) -> bool:
    """The evaluation block is a verified transmitter-off era."""
    basis = str(channel.selection.get("false_alarm_basis") or "")
    return channel.screening.get("off_era_current") is True or basis.startswith("verified off era")


def false_alarm_basis(channel: Channel) -> str:
    """The replay's own basis, or what the replay would have said when nothing was replayed."""
    basis = str(channel.selection.get("false_alarm_basis") or "").strip()
    if basis:
        return basis
    if not channel.has("screening"):
        return ""
    if off_era_block(channel):
        return ("evaluation block is a verified transmitter-off era (screening.off_era_current) but nothing was replayed: "
                "the selector refused")
    return "not measurable: no verified off state in the evaluation block (screening.off_era_current false; no replay)"


def floor_times_gain(sel: Mapping):
    """The residual every frame booked at the floor carries: ``10^(floor_db/10) x chain_gain`` (None when undefined)."""
    floor_db, gain = sel.get("floor_db"), sel.get("chain_gain")
    if not (_finite(floor_db) and _finite(gain)):
        return None
    return 10.0 ** (float(floor_db) / 10.0) * float(gain)


# ------------------------------------------------------------------ the builder
def _row(frag: Fragment, channel: Channel) -> list[str]:
    ch = channel.channel
    sel = channel.selection
    where = {"channel": ch}

    def add(column, value, *, precision=None, kind="float", status=None, renderings=()):
        if status is None:
            status = "measured" if (kind == "text" or _finite(value)) else "refused"
        frag.add(f"{PREFIX}.{column}.ch{ch}", value, precision=precision, kind=kind, status=status,
                 renderings=renderings, row=where, column=column)

    def cell(text, mark=""):
        return DASH if text == DASH else f"${text}{mark}$"

    # the point the row prints
    basis, rho, eta, eta_q16, f_cal = point(sel)
    dagger = DAGGER if basis == DIAGNOSTIC else ""
    add("point_basis", basis or "none", kind="text", renderings=(basis or DASH,))
    rho_text = fmt_int(rho, thousands=False)
    add("rho", rho, precision=0, kind="int", renderings=(rho_text,) if rho_text != DASH else ())
    eta_text = fmt(eta, 5, sig=True)
    add("eta", eta, precision=_decimals(eta_text) if eta_text != DASH else None)
    q16_text = fmt_int(eta_q16)
    add("eta_q16", eta_q16, precision=0, kind="int", renderings=(str(int(eta_q16)),) if _finite(eta_q16) else ())
    f_cal_text = fmt(f_cal, 3)
    add("masked_fraction_calibration", f_cal, precision=3)

    # the replay on the evaluation block
    mark, gain, quality = gain_basis(channel)
    bounded = quality in TAU_MARKS
    f_ev, f_lo, f_hi = (sel.get(k) for k in ("masked_fraction_evaluation", "masked_fraction_evaluation_q16",
                                              "masked_fraction_evaluation_q84"))
    for column, value in (("masked_fraction_evaluation", f_ev), ("masked_fraction_evaluation_q16", f_lo),
                          ("masked_fraction_evaluation_q84", f_hi)):
        add(column, value, precision=3)
    r_ev, r_lo, r_hi = (sel.get(k) for k in ("r_sys_evaluation", "r_sys_evaluation_q16", "r_sys_evaluation_q84"))
    for column, value in (("r_sys_evaluation", r_ev), ("r_sys_evaluation_q16", r_lo), ("r_sys_evaluation_q84", r_hi)):
        text, precision, renderings = fmt_sig(value)
        add(column, value, precision=precision, renderings=renderings,
            status=("bounded" if bounded else "measured") if text != DASH else "refused")
    R = sel.get("R_evaluation")
    R_text, R_precision, R_renderings = fmt_sig(R)
    add("R", R, precision=R_precision, renderings=R_renderings,
        status=("bounded" if bounded else "measured") if R_text != DASH else "refused")
    kept = sel.get("kept_evaluation")
    add("kept_evaluation", kept, precision=0, kind="int", renderings=(fmt_int(kept, thousands=False),) if _finite(kept) else ())
    add("gain_basis", gain, kind="text", renderings=(gain or DASH,))
    add("tau_quality", quality, kind="text", renderings=(quality or DASH,))

    # the false-alarm rate on a verified off era, the coarse flag's beside it
    off = off_era_block(channel)
    pfa = sel.get("false_alarm_rate") if off else None
    flag = channel.blocks.get("evaluation_flag_rate") if off else None
    basis_text = false_alarm_basis(channel)
    add("false_alarm_rate", pfa, precision=3)
    add("false_alarm_rate_flag", flag, precision=3)
    add("false_alarm_basis", basis_text, kind="text", renderings=(basis_text or DASH,))

    # the selector's word
    status = str(sel.get("status") or "")
    claim = str(sel.get("claim_status") or "")
    refusal = str(sel.get("refusal") or "")
    refusal_short = short_refusal(refusal)
    add("status", status, kind="text", renderings=(status or DASH,))
    add("claim_status", claim, kind="text", renderings=(claim or DASH,))
    add("refusal", refusal, kind="text", renderings=(refusal_short,))

    eta_cell = DASH if eta_text == DASH else f"${eta_text}\\ ({q16_text})$"
    return [
        str(ch), cell(rho_text, dagger), eta_cell, cell(f_cal_text),
        cell(fmt_interval(f_ev, f_lo, f_hi, lambda x: fmt(x, 3))),
        cell(fmt_interval(r_ev, r_lo, r_hi, lambda x: fmt_sig(x)[0]), mark), cell(R_text),
        cell(fmt(pfa, 3)), cell(fmt(flag, 3)),
        tex(status) if status else DASH, tex(claim) if claim else DASH, refusal_short,
    ]


def build(run: Run) -> Fragment:
    frag = Fragment(NAME, LABEL, "")
    rows = [_row(frag, c) for c in run.channels]
    frag.tex = booktabs(HEADER, rows, ALIGN)
    frag.inputs = run.inputs()

    channels = list(run.channels)

    def chs(items):
        return ", ".join(str(c) for c in items)

    def sel(c):
        return c.selection

    selected = [c.channel for c in channels if point(sel(c))[0] == SELECTED]
    diagnostic = [c.channel for c in channels if point(sel(c))[0] == DIAGNOSTIC]
    no_point = [c.channel for c in channels if not point(sel(c))[0]]
    refused = [c.channel for c in channels if str(sel(c).get("status") or "") == "refused"]
    claim_diagnostic = [c.channel for c in channels if str(sel(c).get("claim_status") or "") == "diagnostic"]
    replayed = [c.channel for c in channels if _finite(sel(c).get("masked_fraction_evaluation"))]
    kept_none = [c.channel for c in channels if c.channel in replayed and not _finite(sel(c).get("r_sys_evaluation"))]
    no_interval = [c.channel for c in channels if c.channel in replayed
                   and not (_finite(sel(c).get("masked_fraction_evaluation_q16")) and _finite(sel(c).get("masked_fraction_evaluation_q84")))]
    off_blocks = [c.channel for c in channels if off_era_block(c)]
    off_not_replayed = [ch for ch in off_blocks if ch not in replayed]
    pfa = [c.channel for c in channels if off_era_block(c) and _finite(sel(c).get("false_alarm_rate"))]
    with_residual = [c.channel for c in channels if _finite(sel(c).get("r_sys_evaluation"))]
    archive_gain = [c.channel for c in channels if gain_basis(c)[1].startswith("archive-wide")]
    cap = [ch for ch in with_residual if gain_basis(run.by_channel()[ch])[2] == "refused"]
    bound = [ch for ch in with_residual if gain_basis(run.by_channel()[ch])[2] == "bounded_above"]
    bounded = cap + bound
    floor_refused_evaluated = [c.channel for c in channels if str(sel(c).get("floor_evidence") or "") == "refused"
                               and c.channel not in refused and point(sel(c))[0]]
    all_shelf = [ch for ch in floor_refused_evaluated
                 if all(run.by_channel()[ch].blocks.get(k) == 1.0 for k in ("calibration_finite_estimate_rate",
                                                                             "evaluation_finite_estimate_rate"))]
    at_floor, collapsed = [], []
    for c in channels:
        r, fg = sel(c).get("r_sys_evaluation"), floor_times_gain(sel(c))
        if _finite(r) and fg and abs(float(r) / fg - 1.0) <= FLOOR_GAIN_TOLERANCE:
            at_floor.append(c.channel)
            printed = {fmt_sig(sel(c).get(k))[0] for k in ("r_sys_evaluation", "r_sys_evaluation_q16", "r_sys_evaluation_q84")}
            if len(printed) == 1:                 # the interval prints as the value: collapsed at the printed precision
                collapsed.append(c.channel)

    for key, value in (("n_channels", len(channels)), ("n_selected", len(selected)), ("n_diagnostic", len(claim_diagnostic)),
                       ("n_refused", len(refused)), ("n_replayed", len(replayed)), ("n_replay_kept_none", len(kept_none)),
                       ("n_off_era_evaluation_blocks", len(off_blocks)), ("n_false_alarm_measured", len(pfa)),
                       ("n_gain_archive", len(archive_gain)), ("n_residual_bounded", len(bounded))):
        frag.add(f"{PREFIX}.{key}", value, precision=0, kind="int", status="derived", renderings=(str(value),), column=key)

    notes = frag.notes
    if selected:
        notes.append(f"Selected points (selection.rho, eta, eta_q16, masked_fraction_calibration): channels {chs(selected)}.")
    else:
        notes.append("No channel has a selected point on this run: the star of the stub's (rho*, eta*) was never earned, and "
                     "the rank and multiplier columns carry no star.")
    if diagnostic:
        notes.append(f"Dagger rows ({chs(diagnostic)}): the selector returned no point (selection.rho is null), so rho, eta "
                     "(eta_q16) and f_cal print the least-residual point of the evaluated calibration surface "
                     "(selection.diagnostic_rho, diagnostic_eta, diagnostic_eta_q16, diagnostic_masked_fraction), which the "
                     "run replayed on the evaluation block as a declared diagnostic (selection.diagnostic_basis); the "
                     "evaluation cells are that replay. A diagnostic point is not an operating point.")
    if refused:
        reasons = sorted({str(sel(run.by_channel()[ch]).get("refusal") or "") for ch in refused})
        notes.append(f"Status 'refused' on channels {chs(refused)} ({'; '.join(r for r in reasons if r) or 'no reason recorded'}): "
                     "the floor is refused (selection.floor_evidence) and frames without a shelf estimate have no floor to be "
                     "booked at, so no point was evaluated and nothing was replayed; every value cell is dashed and the claim "
                     "column is empty.")
    if floor_refused_evaluated:
        why = (" every frame of both blocks carries a shelf estimate (blocks.calibration_finite_estimate_rate and "
               "evaluation_finite_estimate_rate 1.0), so the residual needed no floor" if all_shelf == floor_refused_evaluated
               else " the residual is defined without it on the frames that carry a shelf estimate")
        notes.append(f"Channels {chs(floor_refused_evaluated)} also carry a refused floor (selection.floor_evidence 'refused'), "
                     f"but{why}; their diagnostic point stands.")
    if no_point:
        empty = [ch for ch in no_point if ch not in refused]
        if empty:
            notes.append(f"Channels {chs(empty)} carry no selection point and no diagnostic point: every value cell is dashed.")
    not_replayed = [c.channel for c in channels if c.channel not in replayed and c.channel not in no_point]
    if not_replayed:
        notes.append(f"Evaluation-block cells (f_eval, r_sys,eval, their intervals, R_eval, P_fa) are dashed on channels "
                     f"{chs(not_replayed)}: the point was not replayed on the evaluation block.")
    if kept_none:
        notes.append(f"Channels {chs(kept_none)}: the replay kept no frame of the evaluation block (selection.kept_evaluation 0), "
                     "so f_eval prints 1.000 and r_sys,eval and R_eval are undefined (dashed).")
    if no_interval:
        notes.append(f"Channels {chs(no_interval)} print an evaluation value with '[--]': fewer acquisition blocks than the "
                     "bootstrap minimum (selection.bootstrap_blocks_evaluation), so no 16-84% interval was formed.")
    if off_blocks:
        text = (f"P_fa on channels {chs(off_blocks)} is the replay's masked fraction on a verified transmitter-off evaluation "
                "block (screening.off_era_current; selection.false_alarm_rate, false_alarm_basis), and P_fa^flag the coarse "
                "survey flag rate on the same block (blocks.evaluation_flag_rate), the coarse rule's false-alarm rate there. "
                "Both are dashed on every other channel: without a verified off state no false-alarm rate is measurable, and "
                "the flag rate is an occupancy indicator, not a false-alarm rate.")
        if off_not_replayed:
            text += (f" On channels {chs(off_not_replayed)} the block is an off era but nothing was replayed, so P_fa is dashed "
                     "and P_fa^flag stands alone.")
        notes.append(text)
    else:
        notes.append("No evaluation block is a verified transmitter-off era: P_fa and P_fa^flag are dashed throughout.")
    if cap or bound or archive_gain:
        parts = []
        if cap:
            parts.append(f"tau_c is refused and the chain gain is the sidereal-day cap (mark c; selection.chain_gain) on channels {chs(cap)}")
        if bound:
            parts.append(f"tau_c is bounded above (mark b) on channels {chs(bound)}")
        if archive_gain:
            parts.append(f"the gain is the archive-wide chain because the era chain refused (mark a; selection.gain_basis) on channels {chs(archive_gain)}")
        notes.append("r_sys,eval and R_eval are upper bounds where the chain gain is a bound (chain.tau_quality, or "
                     "chain_archive.tau_quality under the archive-wide gain): " + "; ".join(parts) + ".")
    if not archive_gain:
        notes.append("Every channel's chain gain is the era chain (selection.gain_basis 'era chain'): no residual carries the "
                     "archive-wide mark a.")
    if at_floor:
        text = (f"On channels {chs(at_floor)} r_sys,eval is within {FLOOR_GAIN_TOLERANCE:.0%} of the floor times the chain gain "
                "(10^(selection.floor_db/10) x selection.chain_gain): the kept frames are booked at the floor, and the 16-84% "
                "interval is correspondingly narrow")
        if collapsed:
            text += f" (it prints as the value itself on channels {chs(collapsed)})"
        notes.append(text + ".")
    if claim_diagnostic:
        notes.append(f"Claim 'diagnostic' on channels {chs(claim_diagnostic)}: the within-era drift screen refused the threshold "
                     "family, so no point is screening or operational; the refusal column gives the screen's reason in short "
                     "form and the numbers document carries the full text (selection.refusal).")
    return frag
