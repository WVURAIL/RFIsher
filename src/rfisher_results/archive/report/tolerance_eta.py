"""``tolerance_eta``: Table ``tab:tolerance:eta`` -- the fine operating point of every channel.

One row per channel, in channel order, from the ledger's ``selection``,
``null``, ``chain`` and ``era`` sections. The stub asks for the selected point
``(rho*, eta*)``. The v5 run has none: the within-era drift screen refused
every channel, ``selection.claim_status`` is ``diagnostic`` and
``selection.rho``/``eta`` are null. The point columns then print the
least-residual point of the calibration surface that the run replayed as a
declared diagnostic (``selection.diagnostic_*``; it coincides with
``selection.min_r_sys_*``), marked with a dagger on the rank, labelled
``(diagnostic)`` in the status column and in a comment line above the
tabular. Where the selector refused before a surface existed
(``selection.status == 'refused'``, no ``diagnostic_rho``: channels without a
floor) the point columns are dashes. A selected point, when a run has one,
prints without the dagger from ``selection.rho``, ``q_rho``, ``eta``,
``eta_q16``, ``masked_fraction_calibration``, ``r_sys_calibration``,
``R_calibration``, ``cost`` and ``plateau_*``.

Columns (ledger keys as ``section.key``; ``a | b`` is the selected value or the diagnostic point's):

``ch``            channel
``era``           the current era's span from ``selection.era`` (``YYYY-MM..YYYY-MM (state)``), else
                  ``era.current_first_month..current_last_month``
``state``         the era's transmitter state from the same label (``era.current_state`` as the fallback),
                  with ``(off)`` appended when ``era.off_era_current`` (the current era is a verified off era,
                  so the point is a false-alarm operating point)
``|B|``           ``selection.bulk_size``
``rho*``          ``selection.rho | selection.diagnostic_rho`` (dagger: the diagnostic point)
``q_rho``         ``selection.q_rho``, else ``rho / (selection.bulk_size + 1)`` (status ``derived``; the text's
                  definition, which is the surface file's ``rank_fraction``)
``eta*``          ``selection.eta | selection.diagnostic_eta`` (the display value ``eta_q16 / 2^16``)
``eta*_q16``      ``selection.eta_q16 | selection.diagnostic_eta_q16`` (the exact deployed multiplier)
``f``             ``selection.masked_fraction_calibration | selection.diagnostic_masked_fraction``
``floor (dB)``    ``selection.floor_db``; dash when ``selection.floor_evidence`` is ``refused``
``floor basis``   ``null.floor_basis`` shortened (``off era p90``: the measured floor of a verified off era;
                  ``kept half`` and ``bulk left side``: the sigma-implied stated substitutes) with its frame
                  population ``null.floor_frames``; dash when the floor is refused (basis ``none``)
``r_proxy``       ``selection.r_sys_calibration | selection.diagnostic_r_sys`` (an upper bound when tau_c is not measured)
``r_tol``         ``selection.r_tol`` (the operable-tier dilation tolerance of the channel's bin)
``R``             ``selection.R_calibration | selection.diagnostic_R`` = r_sys / r_tol; R <= 1 passes and prints bold
``R_c (eta_c)``   the coarse rule's frontier minimum ``selection.coarse_min_R`` at ``selection.coarse_min_R_eta``,
                  the companion of R on the coarse axis; dash when no frontier was written (a refused floor)
``C``             ``selection.cost | selection.diagnostic_cost`` (Eq. tolerance:teff, r_var unavailable)
``plateau``       ``selection.plateau_members`` with ``plateau_eta_low``--``plateau_eta_high``; defined only for a
                  selected point, so dashed on every diagnostic row
``tau_c``         ``chain.tau_quality`` as ``measured`` / ``bound`` (bounded_above) / ``cap`` (refused: the chain is
                  booked at the sidereal-day cap)
``gain``          ``selection.chain_gain`` (``chain.chain_gain`` when the selection carries none): the coherent
                  gain the residual convention multiplies the shelf by; the cap value on ``cap`` rows
``gain basis``    ``selection.gain_basis`` shortened (``era``: the era chain; ``archive``: the archive-wide chain
                  where the era chain refused)
``status``        ``selection.status`` with ``selection.claim_status`` in parentheses
``screen``        ``selection.refusal`` (the drift screen's, or the floor's) shortened to its reason
                  (:func:`short_refusal`)

Numbers are keyed ``ch09.eta.<column>.chNN`` per channel (``rho``, ``q_rho``,
``eta``, ``eta_q16``, ``masked_fraction``, ``floor_db``, ``floor_basis``,
``floor_frames``, ``r_proxy``, ``r_tol``, ``R``, ``coarse_min_R``,
``coarse_min_R_eta``, ``cost``, ``plateau_members``, ``plateau_eta_low``,
``plateau_eta_high``, ``tau_quality``, ``chain_gain``, ``gain_basis``,
``status``, ``claim_status``, ``refusal``, ``era``, ``state``, ``bulk_size``)
and ``ch09.eta.n_<name>`` for the band-level counts. Beside the printed cells
each row carries ``point_basis`` (``selected`` | ``diagnostic``, rendering
``selection.diagnostic_basis``) and ``floor_evidence``
(``selection.floor_evidence``): the statuses of the point and floor cells.
``r_proxy``, ``R``, ``coarse_min_R`` and ``chain_gain`` carry status
``bounded`` on channels whose tau_c is bounded or refused.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .core import DASH, Channel, Fragment, Run, booktabs, fmt, fmt_int, tex

NAME = "tolerance_eta"
LABEL = "tab:tolerance:eta"
KEY = "ch09.eta"
DAGGER = r"^\dagger"                      # inside the rank cell's math mode
LEGEND = ("% tab:tolerance:eta: a dagger on the rank marks the least-residual point of the calibration surface "
          "(selection.diagnostic_*), a declared diagnostic replay printed where no point was selected")

TAU_MARKS = {"measured": "measured", "bounded_above": "bound", "refused": "cap"}
FLOOR_BASES = {"off era p90": "off era p90", "kept half about mu_0": "kept half", "bulk left side (not H0)": "bulk left side",
               "none": ""}
GAIN_BASES = {"era chain": "era", "archive-wide chain (era chain refused)": "archive"}
COLUMNS = (  # (header cell, alignment)
    ("ch", "l"), ("era", "l"), ("state", "l"), (r"$|\mathcal B|$", "r"), (r"$\rho^\star$", "r"), (r"$q_\rho$", "r"),
    (r"$\eta^\star$", "r"), (r"$\eta^\star_{q16}$", "r"), ("$f$", "r"), ("floor (dB)", "r"), ("floor basis", "l"),
    (r"$r_{\rm proxy}$", "r"), (r"$r_{\rm tol}$", "r"), ("$R$", "r"), (r"$R_{\rm c}$ ($\eta_{\rm c}$)", "r"),
    (r"$\mathcal C$", "r"), ("plateau", "l"), (r"$\tau_c$", "l"), ("gain", "r"), ("gain basis", "l"), ("status", "l"),
    ("screen", "l"),
)
HEADER = [h for h, _ in COLUMNS]
ALIGN = "".join(a for _, a in COLUMNS)

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
            return "refused: " + render(m)
    return "refused: " + text.rsplit(": ", 1)[-1]


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


# ------------------------------------------------------------------ the table
def _row(ch: Channel, frag: Fragment, counts: dict, dashed: dict) -> list[str]:
    tag = f"ch{ch.channel:02d}"
    row = {"channel": ch.channel}
    sel, null, chain, era = ch.selection, ch.null, ch.chain, ch.era
    pt = resolve_point(ch)

    def add(column: str, value, *, precision=None, kind="float", status="measured", renderings=()):
        frag.add(f"{KEY}.{column}.{tag}", value, precision=precision, kind=kind, status=status,
                 renderings=renderings, row=row, column=column)

    def dash(reason: str) -> str:
        dashed.setdefault(reason, []).append(tag)
        return DASH

    def number(column: str, value, digits: int, *, status: str = "measured", bold: bool = False) -> str:
        """A significant-figure cell (bold when asked) with its number; the exponent form has no decimals."""
        text = sig(value, digits)
        add(column, float(value), precision=_decimals(text), status=status, renderings=(text,))
        return f"$\\mathbf{{{text}}}$" if bold else f"${text}$"

    cells = [tex(ch.channel)]

    # era and state
    span, state = era_label(ch)
    if span:
        cells.append(tex(span).replace("..", "--"))
        add("era", span, kind="text", renderings=(span, span.replace("..", "--")))
    else:
        cells.append(dash("era: no selection.era and no era section"))
    off_era = bool(era.get("off_era_current"))
    counts["off_era"] += off_era
    if state:
        shown = f"{state} (off)" if off_era else state
        cells.append(tex(shown))
        add("state", state, kind="text", renderings=(state, shown))
    else:
        cells.append(dash("state: no era state"))

    # |B|
    bulk = sel.get("bulk_size")
    if _finite(bulk):
        cells.append(f"${fmt_int(bulk)}$")
        add("bulk_size", int(bulk), precision=0, kind="int")
    else:
        cells.append(dash("bulk_size: no selection section"))

    # the point: rho, q_rho, eta, eta_q16, f
    if pt.source:
        point_basis = "selected" if pt.source == "selection" else "diagnostic"
        counts[point_basis] += 1
        add("point_basis", point_basis, kind="text", renderings=tuple(s for s in (point_basis, pt.basis) if s))
    else:
        counts["no_point"] += 1
    no_point = ("no diagnostic point: the selector refused before a surface existed" if sel.get("status") == "refused"
                else "no selected or diagnostic point")
    if pt.rho is not None:
        cells.append(f"${fmt_int(pt.rho, thousands=False)}{DAGGER if pt.diagnostic else ''}$")
        add("rho", pt.rho, precision=0, kind="int")
    else:
        cells.append(dash(f"rho: {no_point}"))
    if _finite(pt.q_rho):
        cells.append(f"${fmt(pt.q_rho, 4)}$")
        add("q_rho", pt.q_rho, precision=4, status="derived" if pt.q_rho_derived else "measured")
    else:
        cells.append(dash(f"q_rho: {no_point}" if pt.rho is None else "q_rho: no selection.q_rho and no bulk_size"))
    if _finite(pt.eta):
        text = sig(pt.eta, 4)
        cells.append(f"${text}$")
        add("eta", pt.eta, precision=_decimals(text), renderings=(text,))
    else:
        cells.append(dash(f"eta: {no_point}"))
    if pt.eta_q16 is not None:
        cells.append(f"${fmt_int(pt.eta_q16)}$")
        add("eta_q16", pt.eta_q16, precision=0, kind="int")
    else:
        cells.append(dash(f"eta_q16: {no_point}" if pt.rho is None else "eta_q16: the point carries no eta_q16"))
    if _finite(pt.masked_fraction):
        cells.append(f"${fmt(pt.masked_fraction, 4)}$")
        add("masked_fraction", pt.masked_fraction, precision=4)
    else:
        cells.append(dash(f"masked_fraction: {no_point}"))

    # the floor and its basis
    floor_db, evidence = sel.get("floor_db"), str(sel.get("floor_evidence") or "")
    refused_floor = evidence == "refused"
    if evidence:
        add("floor_evidence", evidence, kind="text", renderings=(evidence,),
            status={"measured": "measured", "stated": "derived", "refused": "refused"}.get(evidence, "measured"))
        counts["floor_measured"] += evidence == "measured"
        counts["floor_stated"] += evidence == "stated"
        counts["floor_refused"] += refused_floor
    if _finite(floor_db):
        cells.append(f"${fmt(floor_db, 1)}$")
        add("floor_db", float(floor_db), precision=1, status="measured" if evidence == "measured" else "derived")
    else:
        cells.append(dash("floor_db: floor refused (the block carries no null population)" if refused_floor
                          else "floor_db: no selection floor"))
    basis = str(null.get("floor_basis") or "")
    short = FLOOR_BASES.get(basis, basis)
    frames = null.get("floor_frames")
    if short:
        text = tex(short)
        if _finite(frames) and float(frames) > 0:
            text += f", ${fmt_int(frames)}$"
            add("floor_frames", int(frames), precision=0, kind="int")
        cells.append(text)
        add("floor_basis", short, kind="text", renderings=tuple(s for s in (short, basis, evidence) if s))
    else:
        cells.append(dash("floor basis: floor refused (null.floor_basis 'none')" if basis == "none" or refused_floor
                          else "floor basis: no null.floor_basis"))

    # r_proxy, r_tol, R, R_c, C
    tau_quality = str(chain.get("tau_quality") or "")
    bound = "bounded" if tau_quality != "measured" else "measured"
    if _finite(pt.r_sys):
        cells.append(number("r_proxy", pt.r_sys, 3, status=bound))
    else:
        cells.append(dash(f"r_proxy: {no_point}"))
    r_tol = sel.get("r_tol")
    if _finite(r_tol):
        text = fmt(r_tol, 3, sig=True)
        cells.append(f"${text}$")
        add("r_tol", float(r_tol), precision=_decimals(text), renderings=(text,))
    else:
        cells.append(dash("r_tol: no selection section"))
    if _finite(pt.R):
        passes = float(pt.R) <= 1.0
        counts["pass"] += passes
        cells.append(number("R", pt.R, 3, status=bound, bold=passes))
    else:
        cells.append(dash(f"R: {no_point}"))
    coarse_R, coarse_eta = sel.get("coarse_min_R"), sel.get("coarse_min_R_eta")
    if _finite(coarse_R):
        counts["coarse"] += 1
        cell = number("coarse_min_R", coarse_R, 3, status=bound, bold=float(coarse_R) <= 1.0)
        if _finite(coarse_eta):
            text = sig(coarse_eta, 4)
            cell += f" (${text}$)"
            add("coarse_min_R_eta", float(coarse_eta), precision=_decimals(text), renderings=(text,))
        cells.append(cell)
    else:
        cells.append(dash("R_c: no coarse frontier (floor refused)" if refused_floor else "R_c: no coarse frontier"))
    if _finite(pt.cost):
        cells.append(number("cost", pt.cost, 3))
    else:
        cells.append(dash(f"cost: {no_point}" if pt.rho is None else "cost: the point carries no cost"))

    # plateau
    members, lo, hi = sel.get("plateau_members"), sel.get("plateau_eta_low"), sel.get("plateau_eta_high")
    if _finite(members):
        text = f"${fmt_int(members)}$"
        add("plateau_members", int(members), precision=0, kind="int")
        if _finite(lo) and _finite(hi):
            text += f" (${sig(lo, 4)}$--${sig(hi, 4)}$)"
            add("plateau_eta_low", float(lo), precision=_decimals(sig(lo, 4)), renderings=(sig(lo, 4),))
            add("plateau_eta_high", float(hi), precision=_decimals(sig(hi, 4)), renderings=(sig(hi, 4),))
        cells.append(text)
    else:
        cells.append(dash("plateau: no selected point"))

    # tau_c mark
    if tau_quality:
        mark = TAU_MARKS.get(tau_quality, tau_quality)
        cells.append(tex(mark))
        add("tau_quality", mark, kind="text", status={"cap": "refused", "bound": "bounded"}.get(mark, "measured"),
            renderings=(mark, tau_quality))
        key = {"measured": "tau_measured", "bound": "tau_bound", "cap": "tau_cap"}.get(mark)
        if key:
            counts[key] += 1
    else:
        cells.append(dash("tau_c: no chain section"))

    # gain and its basis
    gain = sel.get("chain_gain") if _finite(sel.get("chain_gain")) else chain.get("chain_gain")
    if _finite(gain):
        cells.append(f"${fmt_int(gain)}$")
        add("chain_gain", float(gain), precision=0, status=bound)
    else:
        cells.append(dash("gain: no chain gain in the selection or chain section"))
    gain_basis = str(sel.get("gain_basis") or "")
    if gain_basis:
        short = GAIN_BASES.get(gain_basis, gain_basis)
        cells.append(tex(short))
        add("gain_basis", short, kind="text", renderings=(short, gain_basis))
        counts["gain_archive"] += short == "archive"
    else:
        cells.append(dash("gain basis: no selection.gain_basis"))

    # status and screen
    status, claim = str(sel.get("status") or ""), str(sel.get("claim_status") or "")
    if status:
        cells.append(tex(status) + (f" ({tex(claim)})" if claim else ""))
        add("status", status, kind="text", renderings=(status,))
        if claim:
            add("claim_status", claim, kind="text", renderings=(claim,))
    else:
        cells.append(dash("status: no selection section"))
    refusal = short_refusal(sel.get("refusal"))
    if refusal:
        cells.append(tex(refusal).replace("<", "$<$").replace("rho=", r"$\rho=$").replace("eta=", r"$\eta=$"))
        add("refusal", refusal, kind="text", status="refused", renderings=(refusal, str(sel.get("refusal"))))
    else:
        cells.append(dash("screen: no refusal recorded"))

    if len(cells) != len(HEADER):
        raise AssertionError(f"{tag}: {len(cells)} cells for {len(HEADER)} columns")
    return cells


def build(run: Run) -> Fragment:
    frag = Fragment(NAME, LABEL, "")
    frag.inputs = list(run.inputs())
    counts = {"channels": 0, "selected": 0, "diagnostic": 0, "no_point": 0, "pass": 0, "floor_measured": 0, "floor_stated": 0,
              "floor_refused": 0, "coarse": 0, "tau_measured": 0, "tau_bound": 0, "tau_cap": 0, "off_era": 0, "gain_archive": 0}
    dashed: dict[str, list[str]] = {}
    rows = []
    for ch in run.channels:
        counts["channels"] += 1
        rows.append(_row(ch, frag, counts, dashed))
    frag.tex = LEGEND + "\n" + booktabs(HEADER, rows, ALIGN)
    for name, value in counts.items():
        frag.add(f"{KEY}.n_{name}", int(value), precision=0, kind="int", status="derived", column=name)

    if counts["diagnostic"]:
        frag.notes.append(f"{counts['diagnostic']} of {counts['channels']} channels have no selected point: their rows print "
                          "the least-residual point of the calibration surface (selection.diagnostic_*), marked with a dagger "
                          "on the rank and '(diagnostic)' in the status column; R is r_sys/r_tol at that point")
    if counts["no_point"]:
        frag.notes.append(f"{counts['no_point']} channels have no point at all (selector status 'refused': no floor, so no "
                          "surface was evaluated); their point columns are dashed")
    if counts["selected"] == 0:
        frag.notes.append("no channel has a selected point, so no plateau is defined (dashed)")
    bounded_channels = counts["tau_bound"] + counts["tau_cap"]
    if bounded_channels:
        frag.notes.append(f"r_proxy, R, R_c and the gain are upper bounds on {bounded_channels} channels whose tau_c is bounded "
                          "('bound') or refused ('cap': the chain gain is the sidereal-day cap, no ground-filter credit)")
    frag.notes.append("floor basis 'off era p90' is the measured floor (the 90th percentile of a verified off era's shelf); "
                      "'kept half' (about mu_0) and 'bulk left side' (the bulk's left-side scale about its median) are the "
                      "sigma-implied stated substitutes; a refused floor (no null population) dashes the floor, its basis "
                      "and the coarse frontier")
    frag.notes.append("R_c (eta_c) is the coarse rule's frontier minimum on the same residual convention, beside the fine point")
    if counts["off_era"]:
        frag.notes.append(f"{counts['off_era']} channels are evaluated on a verified off era ('(off)' after the state): "
                          "the point is a false-alarm operating point, not a masking policy")
    for reason, channels in dashed.items():
        frag.notes.append(f"dashed {reason}: {', '.join(channels)}")
    return frag
