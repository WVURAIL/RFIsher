"""``tab:tolerance:eta``: the fine operating point of every channel (chapter 9,
"Thresholds"), and its evidence ledger for Appendix C.

Two fragments, one row per channel 14--36 in each, keyed alike.

``tolerance_eta`` (``tab:tolerance:eta``) is the chapter table and prints
exactly the columns the chapter's stub names: the current era, ``|B|``, the
rank ``rho*`` (with the normalized rank ``q_rho``) and multiplier ``eta*``
(display value and exact ``eta*_q16``), the masked fraction ``f`` at that
point, the cost ``C``, the plateau width, the kept-frame floor with its
population, ``r_proxy``, the operable-tier tolerance ``r_tol``, the ratio
``R = r_sys/r_tol`` and the selector's status --- with a mark where ``tau_c``
is bounded or refused. Those sixteen columns do not set in one tabular (883pt
at the dissertation's 11pt, over the ~860pt a sideways table can carry at
scale 0.75; 932pt if the tau_c mark is given a column of its own), so the
fragment **stacks two panels** one above the other, each with the channel
column, separated by ``\\medskip`` and a short ``\\emph`` panel caption:

* panel 1, *the operating point*: ch, era, ``|B|``, ``rho*``, ``q_rho``,
  ``eta*``, ``eta*_q16``, ``f``, ``C``, plateau. Natural width 452pt.
* panel 2, *the verdict*: ch, floor (dB), null frames, ``r_proxy``,
  ``r_tol``, ``R``, status. Natural width 458pt.

Both panels set upright inside the dissertation's 469.8pt text block
unscaled: the chapter needs neither ``sidewaystable`` nor ``\\resizebox``,
and must not wrap the fragment as a whole in one (it is a vertical block of
two tabulars with paragraph captions between them; scale the tabulars
individually if it ever must scale).

``tolerance_eta_ledger`` (``tab:archive:tolerance_eta``) is the companion the
chapter's stub sends to Appendix~\\ref{app:archive-diagnostics} beside the
channel's plate --- "the term-by-term evidence ledger behind each row ...
rather than into a 23-column table". Same one-row-per-channel shape, seven
columns: the era's transmitter state, the basis of the floor, the ``tau_c``
outcome the chapter table only marks, the coarse rule's frontier minimum
``R_c (eta_c)`` beside the fine point, the chain gain with its basis, and the
screen's refusal in words. Natural width 633pt: it sets sideways
(``rotating``) on the 650pt sideways line unscaled. Every number keeps its
``ch09.eta.*`` key; only which fragment prints it moved.

The point. The stub asks for the selected point ``(rho*, eta*)``. The v5 run
has none: the within-era drift screen refused every channel,
``selection.claim_status`` is ``diagnostic`` and ``selection.rho``/``eta`` are
null. The point columns then print the least-residual point of the
calibration surface that the run replayed as a declared diagnostic
(``selection.diagnostic_*``; it coincides with ``selection.min_r_sys_*``),
marked with a dagger on the rank, labelled ``(diagnostic)`` in the status
column and in a comment line above the panels. Where the selector refused
before a surface existed (``selection.status == 'refused'``, no
``diagnostic_rho``: channels without a floor) the point columns are dashes. A
selected point, when a run has one, prints without the dagger from
``selection.rho``, ``q_rho``, ``eta``, ``eta_q16``,
``masked_fraction_calibration``, ``r_sys_calibration``, ``R_calibration``,
``cost`` and ``plateau_*``.

The tau_c mark. ``chain.tau_quality`` decides whether the residual is a
measurement or a bound, so it rides on the two cells it bounds rather than on
a column of its own: ``r_proxy`` and ``R`` carry ``*`` where ``tau_c`` is
bounded above (``bound``) and ``dagger-dagger`` where it is refused (``cap``:
the chain is booked at the sidereal-day cap, no ground-filter credit). The
word itself is the ledger's ``tau_c`` column.

Chapter columns (ledger keys as ``section.key``; ``a | b`` is the selected
value or the diagnostic point's):

``ch``            channel
``era``           the current era's span from ``selection.era``
                  (``YYYY-MM..YYYY-MM (state)``), else
                  ``era.current_first_month..current_last_month``
``|B|``           ``selection.bulk_size``
``rho*``          ``selection.rho | selection.diagnostic_rho`` (dagger: the diagnostic point)
``q_rho``         ``selection.q_rho``, else ``rho / (selection.bulk_size + 1)`` (status ``derived``; the text's
                  definition, which is the surface file's ``rank_fraction``)
``eta*``          ``selection.eta | selection.diagnostic_eta`` (the display value ``eta_q16 / 2^16``)
``eta*_q16``      ``selection.eta_q16 | selection.diagnostic_eta_q16`` (the exact deployed multiplier)
``f``             ``selection.masked_fraction_calibration | selection.diagnostic_masked_fraction``
``C``             ``selection.cost | selection.diagnostic_cost`` (Eq. tolerance:teff, r_var unavailable: the
                  time cost 1/(1-f) of the masking, which is why it sits beside f)
``plateau``       ``selection.plateau_members`` with ``plateau_eta_low``--``plateau_eta_high``; defined only for a
                  selected point, so dashed on every diagnostic row
``floor (dB)``    ``selection.floor_db``; dash when ``selection.floor_evidence`` is ``refused``
``frames``        ``null.floor_frames``, the population the floor was measured or stated on; dash with the floor
``r_proxy``       ``selection.r_sys_calibration | selection.diagnostic_r_sys`` (an upper bound when tau_c is not
                  measured, marked)
``r_tol``         ``selection.r_tol`` (the operable-tier dilation tolerance of the channel's bin)
``R``             ``selection.R_calibration | selection.diagnostic_R`` = r_sys / r_tol; R <= 1 passes and prints bold
``status``        ``selection.status`` with ``selection.claim_status`` in parentheses; where the selector refused
                  outright the cell is the reason in brief (:func:`brief_refusal`: ``refused: no floor``), whose
                  gloss and whose keyed number (``refusal``) are the ledger's ``screen refusal`` column

Ledger columns (Appendix C):

``ch``            channel
``state``         the era's transmitter state from ``selection.era`` (``era.current_state`` as the fallback),
                  with ``(off)`` appended when ``era.off_era_current`` (the current era is a verified off era,
                  so the point is a false-alarm operating point)
``floor basis``   ``null.floor_basis`` shortened (``off era p90``: the measured floor of a verified off era;
                  ``kept half`` and ``bulk left side``: the sigma-implied stated substitutes); dash when the
                  floor is refused (basis ``none``)
``tau_c``         ``chain.tau_quality`` as ``measured`` / ``bound`` (bounded_above) / ``cap`` (refused: the chain
                  is booked at the sidereal-day cap) --- the word behind the chapter table's mark
``R_c (eta_c)``   the coarse rule's frontier minimum ``selection.coarse_min_R`` at ``selection.coarse_min_R_eta``,
                  the companion of R on the coarse axis; dash when no frontier was written (a refused floor)
``gain (basis)``  ``selection.chain_gain`` (``chain.chain_gain`` when the selection carries none): the coherent
                  gain the residual convention multiplies the shelf by, the cap value on ``cap`` rows, with
                  ``selection.gain_basis`` shortened (``era``: the era chain; ``archive``: the archive-wide chain
                  where the era chain refused)
``screen``        ``selection.refusal`` (the drift screen's, or the floor's) shortened to its reason
                  (:func:`short_refusal`), printed without the ``refused:`` prefix the column header carries

Numbers are keyed ``ch09.eta.<column>.chNN`` per channel, unchanged by the
split. The chapter fragment carries ``era``, ``bulk_size``, ``point_basis``,
``rho``, ``q_rho``, ``eta``, ``eta_q16``, ``masked_fraction``, ``cost``,
``plateau_members``, ``plateau_eta_low``, ``plateau_eta_high``,
``floor_evidence``, ``floor_db``, ``floor_frames``, ``r_proxy``, ``r_tol``,
``R``, ``status`` and ``claim_status``; the ledger fragment ``state``,
``floor_basis``, ``tau_quality``, ``coarse_min_R``, ``coarse_min_R_eta``,
``chain_gain``, ``gain_basis`` and ``refusal``. The band-level counts
``ch09.eta.n_<name>`` (channels, selected, diagnostic, no_point, pass,
floor_measured, floor_stated, floor_refused, coarse, tau_measured, tau_bound,
tau_cap, off_era, gain_archive) stay with the chapter fragment. Beside the
printed cells each row carries ``point_basis`` (``selected`` |
``diagnostic``, rendering ``selection.diagnostic_basis``) and
``floor_evidence`` (``selection.floor_evidence``): the statuses of the point
and floor cells. ``r_proxy``, ``R``, ``coarse_min_R`` and ``chain_gain``
carry status ``bounded`` on channels whose tau_c is bounded or refused.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .core import DASH, Channel, Fragment, Run, booktabs, fmt, fmt_int, tex

NAME = "tolerance_eta"
LABEL = "tab:tolerance:eta"
LEDGER_NAME = "tolerance_eta_ledger"
LEDGER_LABEL = "tab:archive:tolerance_eta"
KEY = "ch09.eta"                          # both fragments key their numbers alike
DAGGER = r"^\dagger"                      # inside the rank cell's math mode
TAU_MARKS = {"measured": "measured", "bounded_above": "bound", "refused": "cap"}
TAU_MARK = {"bound": r"{}^{\ast}", "cap": r"{}^{\ddagger}"}    # on r_proxy and R: the residual is an upper bound
LEGEND = (
    "% tab:tolerance:eta: two panels, one row per channel in each, sharing the channel column: the operating point,\n"
    "% then the verdict on the same rows. The term-by-term evidence ledger is tab:archive:tolerance_eta (Appendix C).\n"
    "% A dagger on the rank marks the least-residual point of the calibration surface (selection.diagnostic_*), a\n"
    "% declared diagnostic replay printed where no point was selected. A star (tau_c bounded above) or double dagger\n"
    "% (tau_c refused: the sidereal-day cap) on r_proxy and R marks a residual that is an upper bound."
)
POINT_CAPTION = r"\emph{Panel 1: the fine operating point $(\rho^\star,\eta^\star)$ of each channel, what it masks and what that costs.}"
VERDICT_CAPTION = r"\emph{Panel 2: the kept-frame floor the point is measured against and the tolerance verdict, same rows.}"

FLOOR_BASES = {"off era p90": "off era p90", "kept half about mu_0": "kept half", "bulk left side (not H0)": "bulk left side",
               "none": ""}
GAIN_BASES = {"era chain": "era", "archive-wide chain (era chain refused)": "archive"}

POINT_COLUMNS = (  # (header cell, alignment)
    ("ch", "l"), ("era", "l"), (r"$|\mathcal B|$", "r"), (r"$\rho^\star$", "r"), (r"$q_\rho$", "r"),
    (r"$\eta^\star$", "r"), (r"$\eta^\star_{q16}$", "r"), ("$f$", "r"), (r"$\mathcal C$", "r"), ("plateau", "l"),
)
VERDICT_COLUMNS = (
    ("ch", "l"), ("floor (dB)", "r"), ("frames", "r"), (r"$r_{\rm proxy}$", "r"), (r"$r_{\rm tol}$", "r"),
    ("$R$", "r"), ("status", "l"),
)
LEDGER_COLUMNS = (
    ("ch", "l"), ("state", "l"), ("floor basis", "l"), (r"$\tau_c$", "l"), (r"$R_{\rm c}$ ($\eta_{\rm c}$)", "l"),
    ("gain (basis)", "r"), ("screen refusal", "l"),
)
POINT_HEADER = [h for h, _ in POINT_COLUMNS]
POINT_ALIGN = "".join(a for _, a in POINT_COLUMNS)
VERDICT_HEADER = [h for h, _ in VERDICT_COLUMNS]
VERDICT_ALIGN = "".join(a for _, a in VERDICT_COLUMNS)
LEDGER_HEADER = [h for h, _ in LEDGER_COLUMNS]
LEDGER_ALIGN = "".join(a for _, a in LEDGER_COLUMNS)

_ERA = re.compile(r"^\s*(\S+?)\.\.(\S+?)\s*(?:\((.*?)\))?\s*$")
_REFUSALS = (
    (re.compile(r"(early|late) half has (\d+) observed months; need (\d+)"),
     lambda m: f"{m[1]} half {m[2]} months < {m[3]}"),
    (re.compile(r"(early|late) half spans ([\d.eE+-]+) days; need ([\d.eE+-]+)"),
     lambda m: f"{m[1]} half {float(m[2]):.0f} days < {float(m[3]):g}"),
    (re.compile(r"candidate rho=(\d+), eta=([\d.eE+-]+) retains fewer than (\d+) frames"),
     lambda m: f"sparse candidate rho={m[1]} eta={fmt(float(m[2]), 2)}"),
    (re.compile(r"no selector-evaluable candidate has supported era halves"), lambda m: "no supported candidate"),
    (re.compile(r"both drift limits and the per-half retained-frame floor must be declared"), lambda m: "drift limits unconfigured"),
    (re.compile(r"no floor for frames without a shelf estimate"), lambda m: "no floor (frames without a shelf estimate)"),
)
REFUSED_PREFIX = "refused: "


# ------------------------------------------------------------------ helpers
def _finite(value) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _float(text) -> float:
    try:
        return float(text)
    except (TypeError, ValueError):
        return math.nan


def _int(value) -> int | None:
    return int(round(float(value))) if _finite(value) else None


def _decimals(text: str) -> int | None:
    """The decimals a rendered number carries (``None`` for the exponent form, whose precision is the mantissa's)."""
    if "times" in text:
        return None
    return len(text.split(".", 1)[1]) if "." in text else 0


def sig(value, digits: int = 3) -> str:
    """``digits`` significant figures; magnitudes of 1e5 and beyond, or below 1e-3, print as ``m\\times10^{e}``.

    The decade is decided after rounding, so 99960 at three figures is
    ``1.00\\times10^{5}``, not ``99960``.
    """
    if not _finite(value):
        return DASH
    x = float(value)
    if x == 0.0:
        return "0"
    e = int(math.floor(math.log10(abs(x))))
    m = round(x / 10.0 ** e, digits - 1)
    if abs(m) >= 10.0:                        # 9.996 -> 10.0: carry into the exponent
        e += 1
        m /= 10.0
    if -3 <= e < 5:
        return fmt(m * 10.0 ** e, digits, sig=True)
    return f"{fmt(m, digits - 1)}\\times10^{{{e}}}"


def short_refusal(text: str) -> str:
    """The refusal reduced to its reason: ``refused: early half 3 months < 6``."""
    text = str(text or "").strip()
    if not text:
        return ""
    for pattern, render in _REFUSALS:
        m = pattern.search(text)
        if m:
            return REFUSED_PREFIX + render(m)
    return REFUSED_PREFIX + text.rsplit(": ", 1)[-1]


def era_label(ch: Channel) -> tuple[str, str]:
    """``(span, state)`` from ``selection.era``, else from the era section; empty strings when neither exists."""
    label = ch.get("selection", "era")
    m = _ERA.match(str(label)) if label else None
    if m:
        return f"{m[1]}..{m[2]}", m[3] or ""
    first, last = ch.get("era", "current_first_month"), ch.get("era", "current_last_month")
    if first and last:
        return f"{first}..{last}", str(ch.get("era", "current_state") or "")
    return "", ""


def tau_mark(ch: Channel) -> tuple[str, str, str]:
    """``(word, mark, status)``: the tau_c outcome, the superscript it puts on a bounded cell, the number status."""
    word = TAU_MARKS.get(str(ch.chain.get("tau_quality") or ""), str(ch.chain.get("tau_quality") or ""))
    return word, TAU_MARK.get(word, ""), "measured" if word == "measured" else "bounded"


def refusal_text(sel) -> str:
    """The screen's refusal as the ledger prints it: the reason without the ``refused:`` prefix."""
    short = short_refusal(sel.get("refusal"))
    return short[len(REFUSED_PREFIX):] if short.startswith(REFUSED_PREFIX) else short


def brief_refusal(sel) -> str:
    """The refusal as the chapter's status column prints it: the reason without its parenthetical gloss.

    ``refused: no floor (frames without a shelf estimate)`` prints as
    ``refused: no floor``; the gloss is the ledger's ``screen refusal``
    column, keyed alike.
    """
    return re.sub(r"\s*\(.*\)\s*$", "", short_refusal(sel.get("refusal")))


def _screen_math(text: str) -> str:
    """The refusal's inline symbols in math mode."""
    return tex(text).replace("<", "$<$").replace("rho=", r"$\rho=$").replace("eta=", r"$\eta=$")


# ------------------------------------------------------------------ the point
@dataclass
class Point:
    """The operating point a row prints: the selection, or the diagnostic (least-residual) point."""

    source: str = ""                  # 'selection' | 'diagnostic' | ''
    rho: int | None = None
    q_rho: float = math.nan
    q_rho_derived: bool = False       # q_rho = rho / (|B| + 1), the ledger carrying none
    eta: float = math.nan
    eta_q16: int | None = None
    masked_fraction: float = math.nan
    r_sys: float = math.nan
    R: float = math.nan
    cost: float = math.nan
    basis: str = ""                   # selection.diagnostic_basis on a diagnostic point

    @property
    def diagnostic(self) -> bool:
        return self.source == "diagnostic"


def resolve_point(ch: Channel) -> Point:
    sel = ch.selection
    if sel.get("rho") is not None:
        pt = Point("selection", int(sel["rho"]), _float(sel.get("q_rho")), False, _float(sel.get("eta")), _int(sel.get("eta_q16")),
                   _float(sel.get("masked_fraction_calibration")), _float(sel.get("r_sys_calibration")),
                   _float(sel.get("R_calibration")), _float(sel.get("cost")))
    elif sel.get("diagnostic_rho") is not None:
        pt = Point("diagnostic", int(sel["diagnostic_rho"]), math.nan, False, _float(sel.get("diagnostic_eta")),
                   _int(sel.get("diagnostic_eta_q16")), _float(sel.get("diagnostic_masked_fraction")),
                   _float(sel.get("diagnostic_r_sys")), _float(sel.get("diagnostic_R")), _float(sel.get("diagnostic_cost")),
                   str(sel.get("diagnostic_basis") or ""))
    else:
        return Point()
    bulk = sel.get("bulk_size")
    if not _finite(pt.q_rho) and _finite(bulk) and float(bulk) > 0:
        pt.q_rho, pt.q_rho_derived = pt.rho / (float(bulk) + 1.0), True
    return pt


def no_point_reason(ch: Channel) -> str:
    """Why a row has no point at all, for the dashed notes."""
    return ("no diagnostic point: the selector refused before a surface existed"
            if ch.selection.get("status") == "refused" else "no selected or diagnostic point")


# ------------------------------------------------------------------ one row's cells and numbers
class _Row:
    """The cell helpers of one channel's row: keyed numbers, dashes with their reason, formatted figures."""

    def __init__(self, ch: Channel, frag: Fragment, dashed: dict):
        self.ch, self.frag, self.dashed = ch, frag, dashed
        self.tag = f"ch{ch.channel:02d}"
        self.row = {"channel": ch.channel}

    def add(self, column: str, value, *, precision=None, kind="float", status="measured", renderings=()) -> None:
        self.frag.add(f"{KEY}.{column}.{self.tag}", value, precision=precision, kind=kind, status=status,
                      renderings=renderings, row=self.row, column=column)

    def dash(self, reason: str) -> str:
        self.dashed.setdefault(reason, []).append(self.tag)
        return DASH

    def number(self, column: str, value, digits: int, *, status: str = "measured", bold: bool = False, mark: str = "") -> str:
        """A significant-figure cell (bold when asked, marked when bounded) with its number."""
        text = sig(value, digits)
        self.add(column, float(value), precision=_decimals(text), status=status, renderings=(text,))
        body = f"\\mathbf{{{text}}}" if bold else text
        return f"${body}{mark}$"


def _point_row(ch: Channel, frag: Fragment, dashed: dict) -> list[str]:
    """Panel 1: era, bulk, the point (rho*, q_rho, eta*, eta*_q16), the masked fraction, the cost and the plateau."""
    r = _Row(ch, frag, dashed)
    sel = ch.selection
    pt = resolve_point(ch)
    cells = [tex(ch.channel)]

    span, _ = era_label(ch)
    if span:
        cells.append(tex(span).replace("..", "--"))
        r.add("era", span, kind="text", renderings=(span, span.replace("..", "--")))
    else:
        cells.append(r.dash("era: no selection.era and no era section"))

    bulk = sel.get("bulk_size")
    if _finite(bulk):
        cells.append(f"${fmt_int(bulk)}$")
        r.add("bulk_size", int(bulk), precision=0, kind="int")
    else:
        cells.append(r.dash("bulk_size: no selection section"))

    if pt.source:
        basis = "selected" if pt.source == "selection" else "diagnostic"
        r.add("point_basis", basis, kind="text", renderings=tuple(s for s in (basis, pt.basis) if s))
    absent = no_point_reason(ch)
    if pt.rho is not None:
        cells.append(f"${fmt_int(pt.rho, thousands=False)}{DAGGER if pt.diagnostic else ''}$")
        r.add("rho", pt.rho, precision=0, kind="int")
    else:
        cells.append(r.dash(f"rho: {absent}"))
    if _finite(pt.q_rho):
        cells.append(f"${fmt(pt.q_rho, 4)}$")
        r.add("q_rho", pt.q_rho, precision=4, status="derived" if pt.q_rho_derived else "measured")
    else:
        cells.append(r.dash(f"q_rho: {absent}" if pt.rho is None else "q_rho: no selection.q_rho and no bulk_size"))
    if _finite(pt.eta):
        text = sig(pt.eta, 4)
        cells.append(f"${text}$")
        r.add("eta", pt.eta, precision=_decimals(text), renderings=(text,))
    else:
        cells.append(r.dash(f"eta: {absent}"))
    if pt.eta_q16 is not None:
        cells.append(f"${fmt_int(pt.eta_q16)}$")
        r.add("eta_q16", pt.eta_q16, precision=0, kind="int")
    else:
        cells.append(r.dash(f"eta_q16: {absent}" if pt.rho is None else "eta_q16: the point carries no eta_q16"))
    if _finite(pt.masked_fraction):
        cells.append(f"${fmt(pt.masked_fraction, 4)}$")
        r.add("masked_fraction", pt.masked_fraction, precision=4)
    else:
        cells.append(r.dash(f"masked_fraction: {absent}"))
    if _finite(pt.cost):
        cells.append(r.number("cost", pt.cost, 3))
    else:
        cells.append(r.dash(f"cost: {absent}" if pt.rho is None else "cost: the point carries no cost"))

    members, lo, hi = sel.get("plateau_members"), sel.get("plateau_eta_low"), sel.get("plateau_eta_high")
    if _finite(members):
        text = f"${fmt_int(members)}$"
        r.add("plateau_members", int(members), precision=0, kind="int")
        if _finite(lo) and _finite(hi):
            text += f" (${sig(lo, 4)}$--${sig(hi, 4)}$)"
            r.add("plateau_eta_low", float(lo), precision=_decimals(sig(lo, 4)), renderings=(sig(lo, 4),))
            r.add("plateau_eta_high", float(hi), precision=_decimals(sig(hi, 4)), renderings=(sig(hi, 4),))
        cells.append(text)
    else:
        cells.append(r.dash("plateau: no selected point"))

    if len(cells) != len(POINT_HEADER):
        raise AssertionError(f"{r.tag}: {len(cells)} cells for {len(POINT_HEADER)} panel-1 columns")
    return cells


def _verdict_row(ch: Channel, frag: Fragment, dashed: dict) -> list[str]:
    """Panel 2: the kept-frame floor and its population, r_proxy, r_tol, R and the selector's status."""
    r = _Row(ch, frag, dashed)
    sel, null = ch.selection, ch.null
    pt = resolve_point(ch)
    _, mark, bound = tau_mark(ch)
    cells = [tex(ch.channel)]

    floor_db, evidence = sel.get("floor_db"), str(sel.get("floor_evidence") or "")
    refused_floor = evidence == "refused"
    if evidence:
        r.add("floor_evidence", evidence, kind="text", renderings=(evidence,),
              status={"measured": "measured", "stated": "derived", "refused": "refused"}.get(evidence, "measured"))
    if _finite(floor_db):
        cells.append(f"${fmt(floor_db, 1)}$")
        r.add("floor_db", float(floor_db), precision=1, status="measured" if evidence == "measured" else "derived")
    else:
        cells.append(r.dash("floor_db: floor refused (the block carries no null population)" if refused_floor
                            else "floor_db: no selection floor"))
    frames = null.get("floor_frames")
    if _finite(frames) and float(frames) > 0:
        cells.append(f"${fmt_int(frames)}$")
        r.add("floor_frames", int(frames), precision=0, kind="int")
    else:
        cells.append(r.dash("floor frames: floor refused (no null population)" if refused_floor
                            else "floor frames: no null.floor_frames"))

    absent = no_point_reason(ch)
    if _finite(pt.r_sys):
        cells.append(r.number("r_proxy", pt.r_sys, 3, status=bound, mark=mark))
    else:
        cells.append(r.dash(f"r_proxy: {absent}"))
    r_tol = sel.get("r_tol")
    if _finite(r_tol):
        text = fmt(r_tol, 3, sig=True)
        cells.append(f"${text}$")
        r.add("r_tol", float(r_tol), precision=_decimals(text), renderings=(text,))
    else:
        cells.append(r.dash("r_tol: no selection section"))
    if _finite(pt.R):
        cells.append(r.number("R", pt.R, 3, status=bound, bold=float(pt.R) <= 1.0, mark=mark))
    else:
        cells.append(r.dash(f"R: {absent}"))

    status, claim = str(sel.get("status") or ""), str(sel.get("claim_status") or "")
    if status:
        cell = tex(status) + (f" ({tex(claim)})" if claim else "")
        brief = brief_refusal(sel)
        if status == "refused" and brief:          # the stub's 'refused with reason': the reason rides on the status
            cell = _screen_math(brief) + (f" ({tex(claim)})" if claim else "")
        cells.append(cell)
        r.add("status", status, kind="text", renderings=(status,))
        if claim:
            r.add("claim_status", claim, kind="text", renderings=(claim,))
    else:
        cells.append(r.dash("status: no selection section"))

    if len(cells) != len(VERDICT_HEADER):
        raise AssertionError(f"{r.tag}: {len(cells)} cells for {len(VERDICT_HEADER)} panel-2 columns")
    return cells


def _ledger_row(ch: Channel, frag: Fragment, dashed: dict) -> list[str]:
    """Appendix C: the state, the floor's basis, the tau_c word, the coarse frontier, the gain and the refusal."""
    r = _Row(ch, frag, dashed)
    sel, null, chain, era = ch.selection, ch.null, ch.chain, ch.era
    word, _, bound = tau_mark(ch)
    cells = [tex(ch.channel)]

    _, state = era_label(ch)
    off_era = bool(era.get("off_era_current"))
    if state:
        shown = f"{state} (off)" if off_era else state
        cells.append(tex(shown))
        r.add("state", state, kind="text", renderings=(state, shown))
    else:
        cells.append(r.dash("state: no era state"))

    basis = str(null.get("floor_basis") or "")
    short = FLOOR_BASES.get(basis, basis)
    evidence = str(sel.get("floor_evidence") or "")
    if short:
        cells.append(tex(short))
        r.add("floor_basis", short, kind="text", renderings=tuple(s for s in (short, basis, evidence) if s))
    else:
        cells.append(r.dash("floor basis: floor refused (null.floor_basis 'none')" if basis == "none" or evidence == "refused"
                            else "floor basis: no null.floor_basis"))

    if word:
        cells.append(tex(word))
        r.add("tau_quality", word, kind="text", status={"cap": "refused", "bound": "bounded"}.get(word, "measured"),
              renderings=(word, str(chain.get("tau_quality") or "")))
    else:
        cells.append(r.dash("tau_c: no chain section"))

    coarse_R, coarse_eta = sel.get("coarse_min_R"), sel.get("coarse_min_R_eta")
    if _finite(coarse_R):
        cell = r.number("coarse_min_R", coarse_R, 3, status=bound, bold=float(coarse_R) <= 1.0)
        if _finite(coarse_eta):
            text = sig(coarse_eta, 4)
            cell += f" (${text}$)"
            r.add("coarse_min_R_eta", float(coarse_eta), precision=_decimals(text), renderings=(text,))
        cells.append(cell)
    else:
        cells.append(r.dash("R_c: no coarse frontier (floor refused)" if evidence == "refused" else "R_c: no coarse frontier"))

    gain = sel.get("chain_gain") if _finite(sel.get("chain_gain")) else chain.get("chain_gain")
    gain_basis = str(sel.get("gain_basis") or "")
    if _finite(gain):
        cell = f"${fmt_int(gain)}$"
        r.add("chain_gain", float(gain), precision=0, status=bound)
        if gain_basis:
            cell += f" ({tex(GAIN_BASES.get(gain_basis, gain_basis))})"
        cells.append(cell)
    else:
        cells.append(r.dash("gain: no chain gain in the selection or chain section"))
    if gain_basis:
        short_basis = GAIN_BASES.get(gain_basis, gain_basis)
        r.add("gain_basis", short_basis, kind="text", renderings=(short_basis, gain_basis))
    elif _finite(gain):
        r.dash("gain basis: no selection.gain_basis (the gain prints without its basis)")

    refusal = short_refusal(sel.get("refusal"))
    if refusal:
        cells.append(_screen_math(refusal_text(sel)))
        r.add("refusal", refusal, kind="text", status="refused",
              renderings=(refusal, refusal_text(sel), brief_refusal(sel), str(sel.get("refusal"))))
    else:
        cells.append(r.dash("screen: no refusal recorded"))

    if len(cells) != len(LEDGER_HEADER):
        raise AssertionError(f"{r.tag}: {len(cells)} cells for {len(LEDGER_HEADER)} ledger columns")
    return cells


# ------------------------------------------------------------------ the band-level counts
COUNTS = ("channels", "selected", "diagnostic", "no_point", "pass", "floor_measured", "floor_stated", "floor_refused",
          "coarse", "tau_measured", "tau_bound", "tau_cap", "off_era", "gain_archive")


def _tally(ch: Channel, counts: dict) -> None:
    """One channel's contribution to the band-level counts, whichever fragment prints the column."""
    sel = ch.selection
    pt = resolve_point(ch)
    counts["channels"] += 1
    counts["selected"] += pt.source == "selection"
    counts["diagnostic"] += pt.diagnostic
    counts["no_point"] += not pt.source
    counts["pass"] += _finite(pt.R) and float(pt.R) <= 1.0
    evidence = str(sel.get("floor_evidence") or "")
    for name in ("measured", "stated", "refused"):
        counts[f"floor_{name}"] += evidence == name
    counts["coarse"] += _finite(sel.get("coarse_min_R"))
    word = tau_mark(ch)[0]
    if word in ("measured", "bound", "cap"):
        counts[f"tau_{word}"] += 1
    counts["off_era"] += bool(ch.era.get("off_era_current"))
    counts["gain_archive"] += GAIN_BASES.get(str(sel.get("gain_basis") or ""), "") == "archive"


def _channels(tags: list[str]) -> str:
    return ", ".join(tags)


# ------------------------------------------------------------------ the fragments
def build(run: Run) -> Fragment:
    """``tab:tolerance:eta``: two stacked panels, the operating point and the verdict, one row per channel in each."""
    frag = Fragment(NAME, LABEL, "")
    frag.inputs = list(run.inputs())
    counts = dict.fromkeys(COUNTS, 0)
    dashed: dict[str, list[str]] = {}
    point_rows, verdict_rows = [], []
    for ch in run.channels:
        point_rows.append(_point_row(ch, frag, dashed))
        verdict_rows.append(_verdict_row(ch, frag, dashed))
        _tally(ch, counts)
    frag.tex = "\n".join([LEGEND, "", POINT_CAPTION, "",
                          booktabs(POINT_HEADER, point_rows, POINT_ALIGN).rstrip("\n"), "",
                          r"\medskip", "", VERDICT_CAPTION, "",
                          booktabs(VERDICT_HEADER, verdict_rows, VERDICT_ALIGN).rstrip("\n"), ""])
    for name, value in counts.items():
        frag.add(f"{KEY}.n_{name}", int(value), precision=0, kind="int", status="derived", column=name)

    frag.notes.append(f"layout: two stacked panels in one fragment, each a tabular sharing the channel column --- panel 1 the "
                      f"operating point ({len(POINT_HEADER)} columns, natural width 452pt at 11pt) and panel 2 the verdict "
                      f"({len(VERDICT_HEADER)} columns, 458pt), separated by \\medskip and a short emph panel caption. The "
                      "stub's columns do not set in one tabular (883pt, over the ~860pt a sideways table carries at scale "
                      "0.75, and 932pt with a tau_c column of its own); both panels set upright inside the 469.8pt text "
                      "block unscaled, so the chapter needs no sidewaystable and no resizebox, and must not wrap the "
                      "fragment as a whole in one (it is a vertical block: scale the tabulars individually if it ever "
                      "must scale)")
    frag.notes.append(f"the term-by-term evidence ledger behind each row is the companion fragment {LEDGER_NAME} "
                      f"({LEDGER_LABEL}, Appendix C, beside the channel's plate): the era's transmitter state, the floor's "
                      "basis, the tau_c word, the coarse frontier R_c (eta_c), the chain gain with its basis and the "
                      "screen's refusal, one row per channel, same keys")
    if counts["diagnostic"]:
        frag.notes.append(f"{counts['diagnostic']} of {counts['channels']} channels have no selected point: their rows print "
                          "the least-residual point of the calibration surface (selection.diagnostic_*), marked with a dagger "
                          "on the rank and '(diagnostic)' in the status column; R is r_sys/r_tol at that point")
    if counts["no_point"]:
        frag.notes.append(f"{counts['no_point']} channels have no point at all (selector status 'refused': no floor, so no "
                          "surface was evaluated); their point columns are dashed and the status carries the reason")
    if counts["selected"] == 0:
        frag.notes.append("no channel has a selected point, so no plateau is defined (dashed)")
    bounded_channels = counts["tau_bound"] + counts["tau_cap"]
    if bounded_channels:
        frag.notes.append(f"r_proxy and R are upper bounds on {bounded_channels} channels whose tau_c is bounded above "
                          "(marked with a star) or refused (marked with a double dagger: the chain gain is the sidereal-day "
                          f"cap, no ground-filter credit); the word itself, the gain and R_c are the {LEDGER_NAME} columns")
    frag.notes.append("floor (dB) is the kept-frame floor with the population it was measured or stated on (null.floor_frames); "
                      "its basis (off era p90, kept half, bulk left side) is the ledger's, and a refused floor (no null "
                      "population) dashes the floor, its frames and the ledger's basis and coarse frontier")
    if counts["off_era"]:
        frag.notes.append(f"{counts['off_era']} channels are evaluated on a verified off era (the ledger's state column marks "
                          "them '(off)'): the point is a false-alarm operating point, not a masking policy")
    for reason, channels in dashed.items():
        frag.notes.append(f"dashed {reason}: {_channels(channels)}")
    return frag


def build_ledger(run: Run) -> Fragment:
    """``tab:archive:tolerance_eta``: the chapter table's evidence ledger, for Appendix C."""
    frag = Fragment(LEDGER_NAME, LEDGER_LABEL, "")
    frag.inputs = list(run.inputs())
    dashed: dict[str, list[str]] = {}
    rows = [_ledger_row(ch, frag, dashed) for ch in run.channels]
    frag.tex = booktabs(LEDGER_HEADER, rows, LEDGER_ALIGN)

    frag.notes.append(f"layout: one {len(LEDGER_HEADER)}-column tabular, one row per channel, keyed to {LABEL} row for row; "
                      "natural width 633pt at 11pt, which sets on the 650pt sideways line (rotating) unscaled")
    frag.notes.append(f"the evidence behind {LABEL} (chapter 9): the columns the chapter's stub sends to Appendix C beside "
                      "the channel's plate rather than into a 23-column table; the stub's own columns (era, bulk, the point, "
                      "f, cost, plateau, floor and its population, r_proxy, r_tol, R and the status) stay in the chapter "
                      "table and are not repeated here")
    frag.notes.append("tau_c is the word behind the chapter table's mark: 'measured', 'bound' (bounded above) or 'cap' "
                      "(refused: the chain is booked at the sidereal-day cap and takes no ground-filter credit); r_proxy, R, "
                      "R_c and the gain are upper bounds wherever it is not 'measured'")
    frag.notes.append("floor basis 'off era p90' is the measured floor (the 90th percentile of a verified off era's shelf); "
                      "'kept half' (about mu_0) and 'bulk left side' (the bulk's left-side scale about its median) are the "
                      "sigma-implied stated substitutes; a refused floor (no null population) dashes the basis and the "
                      "coarse frontier")
    frag.notes.append("R_c (eta_c) is the coarse rule's frontier minimum on the same residual convention, the companion of "
                      "the chapter table's R on the coarse axis")
    frag.notes.append("gain (basis) is the coherent gain the residual convention multiplies the shelf by, with the chain it "
                      "was priced on: 'era' the era chain, 'archive' the archive-wide chain where the era chain refused")
    frag.notes.append("screen refusal prints selection.refusal shortened to its reason, without the 'refused:' prefix the "
                      "column header carries; the number keeps the prefixed value")
    for reason, channels in dashed.items():
        frag.notes.append(f"dashed {reason}: {_channels(channels)}")
    return frag


BUILDERS = (build, build_ledger)
