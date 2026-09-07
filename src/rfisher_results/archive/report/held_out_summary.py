"""The ch06 held-out summary (``tab:detection:heldout``): one row per channel,
the point frozen on the calibration block and its replay on the disjoint
evaluation block.

What the chapter prints. The ch06 stub names the columns: per channel, the
calibration-block ``(rho*, eta*)``, the evaluation-block masked fraction and
retained residual, ``r_sys/r_tol``, the empirical ``P_fa`` where an off state
exists, and the block-bootstrap intervals. Those seven columns are the whole
chapter table. Everything the builder used to print beside them --- the exact
Q16 multiplier, the calibration-block masked fraction, the kept-frame count,
the coarse survey flag's rate, the chain-gain basis, the tau_c quality and the
selector's status, claim and prose-length refusal --- is per-channel evidence,
so by the rule of Chapter~9 it goes to the companion ledger
:data:`LEDGER_NAME` (``tab:archive:held_out_summary``, Appendix C, beside the
channel's plate), one row per channel, and keeps its number key there.

Width. The wide table measured 1030.3pt against a 469.8pt text block and a
650.4pt landscape block. Trimming to the stub's columns, printing eta without
its parenthesised Q16 integer, and factoring the shared power of ten out of a
scientific residual interval (:func:`fmt_interval_sig`) reach 438.6pt, so the
chapter table fits the text block upright at full size: no rotation, no
``resizebox``, and no two-panel stack was needed. The companion ledger
measures 723.2pt, which sets in landscape (650.4pt) at scale 0.90.

The point. When the selector returned a point (``selection.status``
``feasible``, ``selection.rho`` set) the row prints it. No channel of the
2026-09-07 run has one: the within-era drift screen refused every channel
(``selection.claim_status`` ``diagnostic``), so the row prints the
least-residual point of the evaluated calibration surface, which the run
replayed on the evaluation block as a declared diagnostic
(``selection.diagnostic_*``; ``selection.diagnostic_basis`` names it), with a
dagger on the rank. Where the floor is refused and frames lack a shelf
estimate the selector refused outright (``selection.status`` ``refused``): no
point, no replay, every value cell dashed. The dagger is the chapter table's
only mark of the claim; the ledger's ``status`` and ``claim`` columns and the
fragment's notes carry the words.

Chapter columns (ledger keys as ``section.key``; ``a | b`` is the selected
value or the diagnostic point's; numeric cells are math mode; an absent or
undefined value prints as ``--`` and the fragment's notes say why):

``ch``
    The channel number.
``rho``
    ``selection.rho | selection.diagnostic_rho``, the rank; a dagger marks
    the diagnostic point.
``eta``
    ``selection.eta | selection.diagnostic_eta``, the display multiplier. The
    exact Q16 integer is the ledger's ``eta_q16`` column.
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
    archive-wide gain); ``b``/``c`` values are upper bounds. The ledger's
    ``gain`` and ``tau_c`` columns name what each mark stands for.
``R``
    ``selection.R_evaluation`` = ``r_sys_evaluation / r_tol`` on the evaluation
    block (``R <= 1`` passes); an upper bound where ``r_sys_evaluation`` is.
``false_alarm_rate``
    ``selection.false_alarm_rate``: the replay's masked fraction where the
    evaluation block is a verified transmitter-off era
    (``screening.off_era_current``; ``selection.false_alarm_basis``);
    dashed elsewhere, where no false-alarm rate is measurable.

Ledger columns (``held_out_summary_ledger``, one row per channel):

``eta_q16``
    ``selection.eta_q16 | selection.diagnostic_eta_q16``, the exact Q16
    integer behind the chapter's eta.
``masked_fraction_calibration``
    ``selection.masked_fraction_calibration |
    selection.diagnostic_masked_fraction``: the masked fraction on the
    calibration block at the printed point.
``kept_evaluation``
    ``selection.kept_evaluation``, the frames the replay kept; 0 is why a
    residual is dashed.
``false_alarm_rate_flag``
    ``blocks.evaluation_flag_rate`` on an off-era evaluation block: the coarse
    survey flag's false-alarm rate there; dashed elsewhere, where the flag
    rate is an occupancy indicator, not a false-alarm rate.
``gain``, ``tau_c``
    ``selection.gain_basis`` and the ``tau_quality`` of the chain that supplied
    the gain, in short form: what the chapter's ``a``, ``b`` and ``c`` marks
    stand for.
``status``, ``claim``, ``refusal``
    ``selection.status``, ``selection.claim_status`` and ``selection.refusal``
    (:func:`short_refusal`; the number carries the full text).

Numbers: ``ch06.heldout.<column>.chNN`` for every cell of both fragments --- no
key moved out of the export when its column moved to the ledger, only into the
ledger's own ``numbers.json`` --- with the interval bounds as
``masked_fraction_evaluation_q16`` etc., and the text numbers ``point_basis``
(``selected`` | the diagnostic basis | ``none``), ``false_alarm_basis``,
``gain_basis`` and ``tau_quality`` that explain a mark or a dash; ``None`` with
status ``refused`` where the ledger carries no value, status ``bounded`` on
residuals whose chain gain is a bound. Band-level counts
``ch06.heldout.n_channels``, ``n_selected``, ``n_diagnostic``, ``n_refused``,
``n_replayed``, ``n_replay_kept_none``, ``n_off_era_evaluation_blocks``,
``n_false_alarm_measured``, ``n_gain_archive``, ``n_residual_bounded`` stay
with the chapter fragment.
"""
from __future__ import annotations

import math
import re
from typing import Callable, Mapping

from .core import DASH, Channel, Fragment, Run, booktabs, fmt, fmt_int, tex

NAME = "held_out_summary"
LABEL = "tab:detection:heldout"
LEDGER_NAME = "held_out_summary_ledger"
LEDGER_LABEL = "tab:archive:held_out_summary"
PREFIX = "ch06.heldout"
DAGGER = r"{}^{\dagger}"
MATH_DASH = r"\mbox{--}"                 # the dash inside a math-mode interval

COLUMNS = ("ch", "rho", "eta", "masked_fraction_evaluation", "r_sys_evaluation", "R", "false_alarm_rate")
HEADER = ("ch", r"$\rho$", r"$\eta$", r"$f_{\rm eval}$ [16--84\%]", r"$r_{\rm sys,eval}$ [16--84\%]",
          r"$R_{\rm eval}$", r"$P_{\rm fa}$")
ALIGN = "lrrrrrr"

LEDGER_COLUMNS = ("ch", "eta_q16", "masked_fraction_calibration", "kept_evaluation", "false_alarm_rate_flag",
                  "gain", "tau_c", "status", "claim", "refusal")
LEDGER_HEADER = ("ch", r"$\eta_{q16}$", r"$f_{\rm cal}$", r"$N_{\rm keep,eval}$", r"$P_{\rm fa}^{\rm flag}$",
                 "gain", r"$\tau_c$", "status", "claim", "refusal")
LEDGER_ALIGN = "lrrrrlllll"

SELECTED = "selected"
DIAGNOSTIC = "least-residual point of the calibration surface, replayed as a diagnostic"
TAU_MARKS = {"refused": "c", "bounded_above": "b"}
TAU_WORDS = {"refused": "refused", "bounded_above": "bounded", "measured": "measured"}
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


def fmt_mantissa(value, exponent: int, digits: int = 3) -> str:
    """``value`` against a shared power of ten, at ``digits`` significant figures."""
    x = float(value) / 10.0 ** exponent
    if x == 0.0:
        return "0"
    mag = int(math.floor(math.log10(abs(x))))
    return f"{x:.{max(digits - 1 - mag, 0)}f}"


def fmt_interval(value, low, high, render: Callable[[float], str]) -> str:
    """``value [low, high]``; ``value [--]`` when the value exists but the interval does not; the dash when neither."""
    if not _finite(value):
        return DASH
    centre = render(value)
    if _finite(low) and _finite(high):
        return f"{centre}\\ [{render(low)}, {render(high)}]"
    return f"{centre}\\ [{MATH_DASH}]"


def fmt_interval_sig(value, low, high) -> str:
    """``value [low, high]`` at three significant figures, the shared power of
    ten factored out of the bracket where the value prints in scientific form:
    ``(4.23\\ [4.15, 4.32])\\times10^{5}``, not three separate powers. Each
    bound still shows three significant figures of its own; factoring is what
    brings the residual column inside the text block."""
    if not _finite(value):
        return DASH
    text, _, _ = fmt_sig(value)
    if not (_finite(low) and _finite(high)):
        return f"{text}\\ [{MATH_DASH}]"
    if "\\times" in text:
        mantissa, exponent = text.split("\\times10^{")
        exp = int(exponent.rstrip("}"))
        return f"({mantissa}\\ [{fmt_mantissa(low, exp)}, {fmt_mantissa(high, exp)}])\\times10^{{{exp}}}"
    return f"{text}\\ [{fmt_sig(low)[0]}, {fmt_sig(high)[0]}]"


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


def short_gain(basis) -> str:
    """``selection.gain_basis`` as a ledger cell: ``archive-wide`` (the chapter's mark a) or ``era``."""
    text = str(basis or "").strip()
    if not text:
        return DASH
    return "archive-wide" if text.startswith("archive-wide") else "era"


def short_tau(quality) -> str:
    """The gain chain's ``tau_quality`` as a ledger cell (``bounded`` is the chapter's mark b, ``refused`` its mark c)."""
    text = str(quality or "").strip()
    if not text:
        return DASH
    return TAU_WORDS.get(text, text)


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


def _adder(frag: Fragment, ch: int):
    """``add(column, value, ...)``: one number of channel ``ch``, keyed for this fragment."""
    where = {"channel": ch}

    def add(column, value, *, precision=None, kind="float", status=None, renderings=()):
        if status is None:
            status = "measured" if (kind == "text" or _finite(value)) else "refused"
        frag.add(f"{PREFIX}.{column}.ch{ch}", value, precision=precision, kind=kind, status=status,
                 renderings=renderings, row=where, column=column)

    return add


def _cell(text: str, mark: str = "") -> str:
    return DASH if text == DASH else f"${text}{mark}$"


# ------------------------------------------------------------------ the chapter table
def _row(frag: Fragment, channel: Channel) -> list[str]:
    """One chapter row: the stub's columns, and the numbers only the chapter prints."""
    ch = channel.channel
    sel = channel.selection
    add = _adder(frag, ch)

    # the point the row prints
    basis, rho, eta, _q16, _f_cal = point(sel)
    dagger = DAGGER if basis == DIAGNOSTIC else ""
    add("point_basis", basis or "none", kind="text", renderings=(basis or DASH,))
    rho_text = fmt_int(rho, thousands=False)
    add("rho", rho, precision=0, kind="int", renderings=(rho_text,) if rho_text != DASH else ())
    eta_text = fmt(eta, 5, sig=True)
    add("eta", eta, precision=_decimals(eta_text) if eta_text != DASH else None)

    # the replay on the evaluation block
    mark, _gain, quality = gain_basis(channel)
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

    # the false-alarm rate on a verified off era
    off = off_era_block(channel)
    pfa = sel.get("false_alarm_rate") if off else None
    basis_text = false_alarm_basis(channel)
    add("false_alarm_rate", pfa, precision=3)
    add("false_alarm_basis", basis_text, kind="text", renderings=(basis_text or DASH,))

    return [
        str(ch), _cell(rho_text, dagger), _cell(eta_text),
        _cell(fmt_interval(f_ev, f_lo, f_hi, lambda x: fmt(x, 3))),
        _cell(fmt_interval_sig(r_ev, r_lo, r_hi), mark), _cell(R_text), _cell(fmt(pfa, 3)),
    ]


# ------------------------------------------------------------------ the appendix ledger
def _ledger_row(frag: Fragment, channel: Channel) -> list[str]:
    """One ledger row: the per-channel evidence the chapter table no longer prints."""
    ch = channel.channel
    sel = channel.selection
    add = _adder(frag, ch)

    _basis, _rho, _eta, eta_q16, f_cal = point(sel)
    q16_text = fmt_int(eta_q16)
    add("eta_q16", eta_q16, precision=0, kind="int", renderings=(str(int(eta_q16)),) if _finite(eta_q16) else ())
    f_cal_text = fmt(f_cal, 3)
    add("masked_fraction_calibration", f_cal, precision=3)

    kept = sel.get("kept_evaluation")
    add("kept_evaluation", kept, precision=0, kind="int",
        renderings=(fmt_int(kept, thousands=False),) if _finite(kept) else ())
    _mark, gain, quality = gain_basis(channel)
    add("gain_basis", gain, kind="text", renderings=(gain or DASH,))
    add("tau_quality", quality, kind="text", renderings=(quality or DASH,))

    flag = channel.blocks.get("evaluation_flag_rate") if off_era_block(channel) else None
    add("false_alarm_rate_flag", flag, precision=3)

    status = str(sel.get("status") or "")
    claim = str(sel.get("claim_status") or "")
    refusal = str(sel.get("refusal") or "")
    refusal_short = short_refusal(refusal)
    add("status", status, kind="text", renderings=(status or DASH,))
    add("claim_status", claim, kind="text", renderings=(claim or DASH,))
    add("refusal", refusal, kind="text", renderings=(refusal_short,))

    return [
        str(ch), _cell(q16_text), _cell(f_cal_text), _cell(fmt_int(kept)), _cell(fmt(flag, 3)),
        short_gain(gain), short_tau(quality), tex(status) if status else DASH, tex(claim) if claim else DASH,
        refusal_short,
    ]


def build_ledger(run: Run) -> Fragment:
    """The companion evidence ledger for Appendix C, one row per channel."""
    frag = Fragment(LEDGER_NAME, LEDGER_LABEL, "")
    frag.tex = booktabs(LEDGER_HEADER, [_ledger_row(frag, c) for c in run.channels], LEDGER_ALIGN)
    frag.inputs = run.inputs()
    channels = list(run.channels)

    def chs(items):
        return ", ".join(str(c) for c in items)

    frag.notes.append(f"The per-channel evidence behind Table~\\ref{{{LABEL}}}, printed here rather than in the chapter: the "
                      "chapter table prints the columns its stub names (rho, eta, the evaluation-block masked fraction and "
                      "retained residual with their block-bootstrap intervals, R_eval and P_fa) and nothing else, and this "
                      "ledger carries the exact Q16 multiplier, the calibration-block masked fraction, the frames the replay "
                      "kept, the coarse survey flag's rate, the chain-gain basis, the tau_c quality and the selector's word. "
                      "Every number keeps the key it had (ch06.heldout.<column>.chNN).")
    frag.notes.append("eta_q16 and f_cal are the printed point's (selection.eta_q16, masked_fraction_calibration, or the "
                      "diagnostic point's selection.diagnostic_eta_q16, diagnostic_masked_fraction): the same point the "
                      "chapter row prints, dagger and all.")
    frag.notes.append("gain and tau_c name the chapter's residual marks: gain 'archive-wide' (selection.gain_basis) is mark a, "
                      "tau_c 'bounded' (tau_quality bounded_above) is mark b and tau_c 'refused' is mark c, where the chain "
                      "gain is the sidereal-day cap; a marked residual is an upper bound. tau_c is read from the chain that "
                      "supplied the gain (chain.tau_quality, or chain_archive.tau_quality under the archive-wide gain).")
    off_blocks = [c.channel for c in channels if off_era_block(c)]
    if off_blocks:
        frag.notes.append(f"P_fa^flag is the coarse survey flag's rate on the evaluation block (blocks.evaluation_flag_rate) "
                          f"and is printed only on the verified transmitter-off blocks {chs(off_blocks)}, where it is a "
                          "false-alarm rate; elsewhere the flag rate is an occupancy indicator, not a false-alarm rate, and "
                          "the cell is dashed.")
    else:
        frag.notes.append("No evaluation block is a verified transmitter-off era, so P_fa^flag is dashed throughout: without a "
                          "verified off state the coarse flag rate is an occupancy indicator, not a false-alarm rate.")
    frag.notes.append("refusal is the short form of selection.refusal; the numbers document carries the full text under "
                      "ch06.heldout.refusal.chNN.")
    return frag


# ------------------------------------------------------------------ the builder
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
    factored = [c.channel for c in channels
                if "\\times" in fmt_sig(sel(c).get("r_sys_evaluation"))[0]
                and _finite(sel(c).get("r_sys_evaluation_q16")) and _finite(sel(c).get("r_sys_evaluation_q84"))]
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
    notes.append(f"The stub's columns only, one tabular (no panel split was needed): the wide form measured 1030.3pt against "
                 f"a 469.8pt text block, and these seven columns measure 438.6pt, so the table sets upright at full size. The "
                 f"exact Q16 multiplier, the calibration-block masked fraction, the kept-frame count, the coarse survey flag's "
                 f"rate, the chain-gain basis, the tau_c quality and the selector's status, claim and refusal are per-channel "
                 f"evidence and print one row per channel in the companion ledger Table~\\ref{{{LEDGER_LABEL}}} "
                 f"({LEDGER_NAME}, Appendix C, beside the channel's plate); every one of their numbers keeps its key there.")
    if selected:
        notes.append(f"Selected points (selection.rho, eta, eta_q16, masked_fraction_calibration): channels {chs(selected)}.")
    else:
        notes.append("No channel has a selected point on this run: the star of the stub's (rho*, eta*) was never earned, and "
                     "the rank and multiplier columns carry no star.")
    if diagnostic:
        notes.append(f"Dagger rows ({chs(diagnostic)}): the selector returned no point (selection.rho is null), so rho and eta "
                     "print the least-residual point of the evaluated calibration surface (selection.diagnostic_rho, "
                     "diagnostic_eta), which the run replayed on the evaluation block as a declared diagnostic "
                     "(selection.diagnostic_basis); the evaluation cells are that replay. A diagnostic point is not an "
                     "operating point. The dagger is the chapter table's only mark of the claim: the ledger's status and claim "
                     "columns carry the words.")
    if refused:
        reasons = sorted({str(sel(run.by_channel()[ch]).get("refusal") or "") for ch in refused})
        notes.append(f"Status 'refused' on channels {chs(refused)} ({'; '.join(r for r in reasons if r) or 'no reason recorded'}): "
                     "the floor is refused (selection.floor_evidence) and frames without a shelf estimate have no floor to be "
                     "booked at, so no point was evaluated and nothing was replayed; every value cell of the row is dashed.")
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
        notes.append(f"Channels {chs(kept_none)}: the replay kept no frame of the evaluation block (selection.kept_evaluation 0, "
                     "in the ledger's N_keep,eval column), so f_eval prints 1.000 and r_sys,eval and R_eval are undefined "
                     "(dashed).")
    if no_interval:
        notes.append(f"Channels {chs(no_interval)} print an evaluation value with '[--]': fewer acquisition blocks than the "
                     "bootstrap minimum (selection.bootstrap_blocks_evaluation), so no 16-84% interval was formed.")
    if off_blocks:
        text = (f"P_fa on channels {chs(off_blocks)} is the replay's masked fraction on a verified transmitter-off evaluation "
                "block (screening.off_era_current; selection.false_alarm_rate, false_alarm_basis). It is dashed on every other "
                "channel: without a verified off state no false-alarm rate is measurable. The coarse survey flag's rate on the "
                "same blocks (blocks.evaluation_flag_rate) is the ledger's P_fa^flag column.")
        if off_not_replayed:
            text += (f" On channels {chs(off_not_replayed)} the block is an off era but nothing was replayed, so P_fa is dashed "
                     "and only the ledger's flag rate stands.")
        notes.append(text)
    else:
        notes.append("No evaluation block is a verified transmitter-off era: P_fa is dashed throughout.")
    if factored:
        notes.append(f"Residual cells on channels {chs(factored)} factor the shared power of ten out of the interval --- "
                     "(m [q16, q84])x10^e, each of the three at three significant figures --- rather than repeating the power "
                     "three times; that factoring is what brings the column inside the text block.")
    if cap or bound or archive_gain:
        parts = []
        if cap:
            parts.append(f"tau_c is refused and the chain gain is the sidereal-day cap (mark c; selection.chain_gain) on channels {chs(cap)}")
        if bound:
            parts.append(f"tau_c is bounded above (mark b) on channels {chs(bound)}")
        if archive_gain:
            parts.append(f"the gain is the archive-wide chain because the era chain refused (mark a; selection.gain_basis) on channels {chs(archive_gain)}")
        notes.append("r_sys,eval and R_eval are upper bounds where the chain gain is a bound (chain.tau_quality, or "
                     "chain_archive.tau_quality under the archive-wide gain; the ledger's gain and tau_c columns): "
                     + "; ".join(parts) + ".")
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
                     "family, so no point is screening or operational; the ledger's refusal column gives the screen's reason in "
                     "short form and the numbers document carries the full text (selection.refusal).")
    return frag


BUILDERS = (build, build_ledger)
