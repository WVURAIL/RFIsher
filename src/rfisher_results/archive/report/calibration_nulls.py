r"""``tab:calibration:nulls``: the current-era null calibration of every channel.

One row per channel, read from the ledger's ``null`` section: the null
calibration on the *calibration block* of the current era (the null
population's block: the floor, the widths that score both blocks and the
kept-half scale are read there; see :mod:`rfisher_results.archive.nulls` and
``run.py`` step 7). The replay on the evaluation block (``null_evaluation``)
belongs to the blocked-evaluation table. Only the exchangeability check reads
held-out frames: the evaluation block's coarse-quiet frames.

**Two panels, one fragment.** The chapter-8 stub names sixteen columns, and
sixteen columns of this content measure 1{,}005 pt against a 470 pt text
block: too wide to print upright and too wide to shrink (a sideways table has
650 pt, so the scale would fall to 0.65). Trimming cannot help, because
nothing the stub asks for may be dropped. The fragment is therefore *stacked*:
two ``tabular`` blocks one above the other inside a single stacking box, each
keyed by the channel column, separated by a ``\medskip`` and a short
``\emph{...}`` panel caption. Panel 1 carries the null population, its centre
and its width factors (456 pt); panel 2 carries the bulk, the exchangeability
check, the floor and the plate (444 pt). Both fit the upright text block, so
the chapter needs neither ``sidewaystable`` nor ``resizebox``; it supplies one
``table`` environment, one caption and one label for the pair.

Columns printed, in panel order (ledger key under ``null.`` unless stated)::

  panel 1 -- the null population, its centre against mu_0 and its width factors
    ch                 channel number
    $N$                era_frames: frames of the calibration block. The coarse null is read
                       from these frames only where the channel has no verified off era; where
                       it has one the coarse row is that population (coarse_frames, printed as
                       the floor's own count), which is why $N$ and the floor's frame count
                       differ on channel 35 (6,152 against 11,199)
    source             null_source shortened -- ``off era`` (verified transmitter-off era),
                       ``bulk (mixture)`` (bulk of the mixture, declared), ``off epoch not
                       null-like; bulk (mixture)`` (older ledgers); mixture_declared appends
                       ``(mixture)`` when the source text does not already say so. An off
                       population that fails the null-like check is marked with an asterisk
                       rather than spelt out (the check itself is in the ledger table)
    $F/\mu_0$          coarse_centre: median of F/mu_0 over the null population, against 1
                       (the packed-weight prediction)
    $\hat\sigma_c$     coarse_core_sigma: left-side robust scale of F/mu_0 about the centre
                       (the i.i.d. model gives 0.00239)
    $W_c$ raw / core   coarse_raw_width_factor / coarse_core_width_factor: measured over
                       i.i.d. width, standard deviation and robust core
    $W_f$ raw / core   fine_raw_width_factor / fine_core_width_factor: the same for the
                       fine per-bin statistic on the bulk bins
    tail \%            coarse_tail_fraction: fraction of frames beyond three core widths
                       above the centre, in percent

  panel 2 -- the bulk, the exchangeability check, the floor and the plate
    ch                 channel number (the panels share it)
    $|\mathcal B|$     bulk_size: bulk bins of the fine null, the denominator of the
                       combinatorial prediction beside it
    meas./pred.        exch_measured / exch_predicted: designated-bin exceedance against the
                       bulk's rank rho on the evaluation block's quiet frames, against the
                       combinatorial (|B|+1-rho)/(|B|+1); the dash when no rank existed
                       (exchangeability_rank_basis empty: the selector refused) or the block
                       had fewer than 30 quiet frames (notes: ``exchangeability skipped``)
    $\rho$ ($n_q$)     exch_rho with exch_frames (quiet frames tested); the dagger marks a
                       diagnostic rank (exchangeability_rank_basis ``diagnostic point``)
    floor dB           floor_db; the dash when the floor is refused
    basis ($n$)        floor_evidence with floor_basis and floor_frames --
                       ``measured: off era p90 (n)`` (n frames with a shelf estimate),
                       ``stated: kept half (n)`` (n kept frames, the half about mu_0),
                       ``stated: bulk left side (n)`` (n = the block's frames; not an H_0
                       population), or ``refused`` (floor_basis ``none``: the bulk centre is
                       beyond 0.1 of mu_0, so the block carries no null population); an older
                       ledger without floor_basis has it inferred from floor_population
    plate              the channel's diagnostic plate in appendix C,
                       ``\ref{fig:archive:atlas:NN}`` (the label that appendix defines)

Columns the builder used to print beyond the stub go to
``tab:archive:calibration_nulls`` (:func:`build_ledger`, the
``calibration_nulls_ledger`` fragment, destined for Appendix C beside the
channel's plate): the off population's null-like check, the fine null's
bulk-bin count where it is smaller than the coarse bulk, and the kept-half
width factor with its frame count and probe spread. One number stays out of
both tables: ``coarse_tail_fraction_iid`` is 0.14 % on every channel -- a
constant of the F model, not a per-channel measurement -- and belongs in the
chapter's caption, so it is emitted per channel and once as a run constant
without a column of its own.

Every printed value is added to its fragment as ``ch08.nulls.<column>.chNN``
(``exch_rank_basis`` and ``floor_basis`` are text numbers beside the rank and
the floor). The chapter-5 sentence numbers (``ch05.nulls.*``) are computed
from the same rows: the number and fraction of channels whose coarse centre
lies within ``CENTRE_TOLERANCE_DB`` of mu_0 (|coarse_centre_db| <= 0.1), the
range of the coarse robust-core width factor among those channels, the range
of the fine robust-core width factor among those channels and over every
channel.
"""
from __future__ import annotations

import math
from typing import Sequence

from .core import DASH, Channel, Fragment, Run, booktabs, fmt, fmt_int, tex

NAME = "calibration_nulls"
LABEL = "tab:calibration:nulls"
LEDGER_NAME = "calibration_nulls_ledger"
LEDGER_LABEL = "tab:archive:calibration_nulls"
KEY = "ch08.nulls"
# the label appendix C actually defines for each channel's diagnostic plate
PLATE_LABEL = "fig:archive:atlas:{channel:d}"
CENTRE_TOLERANCE_DB = 0.1
DAGGER = r"^\dagger"                      # inside the rank cell's math mode: a diagnostic rank, not a selected one
DIAGNOSTIC_RANK = "diagnostic point"      # null.exchangeability_rank_basis when no point was selected
NOT_NULL_LIKE = " (not null-like)"        # spelt out in the number, an asterisk in the source cell
ASTERISK = r"$^{\ast}$"

PANEL1_COLUMNS = (  # (header cell, alignment) -- the null population, its centre and its widths
    ("ch", "l"), ("$N$", "r"), ("source", "l"), (r"$F/\mu_0$", "r"), (r"$\hat\sigma_c$", "r"),
    (r"$W_c^{\mathrm{raw}}$", "r"), (r"$W_c^{\mathrm{core}}$", "r"),
    (r"$W_f^{\mathrm{raw}}$", "r"), (r"$W_f^{\mathrm{core}}$", "r"), (r"tail \%", "r"),
)
PANEL2_COLUMNS = (  # the bulk, the exchangeability check, the floor and the plate
    ("ch", "l"), (r"$|\mathcal{B}|$", "r"), ("meas./pred.", "r"), (r"$\rho$ ($n_q$)", "r"),
    ("floor dB", "r"), ("basis ($n$)", "l"), ("plate", "l"),
)
LEDGER_COLUMNS = (  # the appendix ledger: the evidence behind the source and the kept-half floor
    ("ch", "l"), ("off null-like", "l"), (r"fine $|\mathcal{B}|$", "r"),
    (r"$W_{\mathrm{kept}}$ ($n$)", "r"), ("spread", "r"),
)
PANEL1_CAPTION = r"\emph{Panel 1: the null population, its centre against $\mu_0$ and its width factors.}"
PANEL2_CAPTION = r"\emph{Panel 2: the bulk, the exchangeability rate at the rank $\rho$, the floor and the plate.}"


def _headers(columns) -> list[str]:
    return [h for h, _ in columns]


def _align(columns) -> str:
    return "".join(a for _, a in columns)


PANEL1_HEADER, PANEL1_ALIGN = _headers(PANEL1_COLUMNS), _align(PANEL1_COLUMNS)
PANEL2_HEADER, PANEL2_ALIGN = _headers(PANEL2_COLUMNS), _align(PANEL2_COLUMNS)
LEDGER_HEADER, LEDGER_ALIGN = _headers(LEDGER_COLUMNS), _align(LEDGER_COLUMNS)

_SOURCE_SHORT = {
    "verified transmitter-off era": "off era",
    "verified transmitter-off era (not null-like)": "off era (not null-like)",
    "bulk of the mixture (declared)": "bulk (mixture)",
    "recorded off epoch, not null-like": "off epoch not null-like",
    "independently identified quiet subset": "quiet subset",
    "reference-bin surrogate": "reference surrogate",
    "model-only null": "model-only",
}
_BASIS_TEXT = {  # floor_basis -> (plain rendering, LaTeX cell text; the cell is the short form, the notes spell it out)
    "off era p90": ("off era p90", "off era p90"),
    "kept half about mu_0": ("kept half about mu_0", "kept half"),
    "bulk left side (not H0)": ("bulk left side, not H0", "bulk left side"),
}


def _finite(value) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def source_text(null_source, mixture_declared) -> str:
    """The null source, shortened; ``(mixture)`` appended when declared but not said."""
    if not null_source:
        return DASH
    pieces = [p.strip() for p in str(null_source).split(";") if p.strip()]
    text = "; ".join(_SOURCE_SHORT.get(p, p) for p in pieces)
    if mixture_declared and "mixture" not in text:
        text += " (mixture)"
    return text


def source_cell(text: str) -> str:
    """The source as printed: ``(not null-like)`` becomes an asterisk (the note carries the check)."""
    if text == DASH:
        return DASH
    if NOT_NULL_LIKE in text:
        return tex(text.replace(NOT_NULL_LIKE, "")) + ASTERISK
    return tex(text)


def off_null_like_text(value) -> str:
    """``yes`` / ``no`` for a recorded off population's null-like check; the dash when there is none."""
    if value is None or value == "":
        return DASH
    if isinstance(value, str):
        return "yes" if value.strip().lower() in ("true", "yes", "1") else "no"
    return "yes" if bool(value) else "no"


def floor_basis(n) -> str:
    """``floor_basis`` as recorded, or inferred from ``floor_population`` on an older ledger."""
    basis = str(n.get("floor_basis") or "")
    if basis:
        return basis
    if str(n.get("floor_evidence") or "") == "refused":
        return "none"
    population = str(n.get("floor_population") or "")
    if population.startswith("verified off era"):
        return "off era p90"
    if "kept half" in population:
        return "kept half about mu_0"
    if "bulk" in population:
        return "bulk left side (not H0)"
    return ""


def _math(text: str) -> str:
    """A numeric cell in math mode (the chapters' convention: ``{,}`` groups, hyphen as minus); the dash stays text."""
    return text if text == DASH else f"${text}$"


def width_factor(value) -> tuple[str, int | None]:
    """A width factor: two decimals below 100, an integer with thousands groups above."""
    if not _finite(value):
        return DASH, None
    x = float(value)
    if abs(x) >= 100.0:
        return fmt_int(x), 0
    return fmt(x, 2), 2


def stack(panels: Sequence[tuple[str, str]]) -> str:
    r"""The panels one above the other in a single box: caption, ``tabular``, ``\medskip``, caption, ``tabular``.

    The chapter's ``table`` environment holds one caption and one label for the
    pair; the stacking box exists so the fragment measures as the widest panel
    rather than as their sum.
    """
    lines = [r"\begin{tabular}{@{}l@{}}"]
    for i, (caption, body) in enumerate(panels):
        if i:
            lines.append(r"\\[\medskipamount]")          # a \medskip between the panels
        lines.append(caption + r"\\[2pt]")
        lines.append(body.rstrip("\n"))
    lines.append(r"\end{tabular}")
    return "\n".join(lines) + "\n"


def _adder(frag: Fragment, ch: int):
    """``add(column, value, text, ...) -> text``: record a number for this channel unless the cell is dashed."""
    where = {"channel": ch}

    def add(column: str, value, text: str, *, precision: int | None = None, kind: str = "float", status: str = "measured"):
        if text != DASH:
            frag.add(f"{KEY}.{column}.ch{ch:02d}", value, precision=precision, kind=kind, status=status,
                     renderings=(text,), row=where, column=column)
        return text

    return add


def _row(c: Channel, frag: Fragment) -> tuple[list[str], list[str]]:
    """One channel's panel-1 and panel-2 cells; every chapter-table number is added here."""
    n = c.null
    ch = c.channel
    add = _adder(frag, ch)

    one = [str(ch)]
    one.append(_math(add("era_frames", n.get("era_frames"), fmt_int(n.get("era_frames")), precision=0, kind="int")))
    src = source_text(n.get("null_source"), n.get("mixture_declared"))
    add("null_source", src, src, kind="text")
    one.append(source_cell(src))
    one.append(_math(add("coarse_centre", n.get("coarse_centre"), fmt(n.get("coarse_centre"), 4), precision=4)))
    sigma = fmt(n.get("coarse_core_sigma"), 3, sig=True)
    one.append(_math(add("coarse_core_sigma", n.get("coarse_core_sigma"), sigma)))
    for key in ("coarse_raw_width_factor", "coarse_core_width_factor", "fine_raw_width_factor", "fine_core_width_factor"):
        text, precision = width_factor(n.get(key))
        one.append(_math(add(key, n.get(key), text, precision=precision)))
    for key in ("coarse_tail_fraction", "coarse_tail_fraction_iid"):
        value = n.get(key)
        pct = 100.0 * float(value) if _finite(value) else None
        # the i.i.d. fraction is a constant of the F model: emitted, then stated in the caption, never a column
        cell = _math(add(f"{key}_pct", pct, fmt(pct, 2), precision=2))
        if key == "coarse_tail_fraction":
            one.append(cell)

    two = [str(ch)]
    two.append(_math(add("bulk_size", n.get("bulk_size"), fmt_int(n.get("bulk_size")), precision=0, kind="int")))
    two.extend(_exchangeability(n, add))
    two.extend(_floor(n, add))
    label = PLATE_LABEL.format(channel=ch)
    plate = rf"Fig.~\ref{{{label}}}"
    add("plate", label, plate, kind="text")
    two.append(plate)
    return one, two


def _ledger_row(c: Channel, frag: Fragment) -> list[str]:
    """One channel's ledger row: the null-like check, the fine bulk and the kept half."""
    n = c.null
    add = _adder(frag, c.channel)

    off = off_null_like_text(n.get("off_null_like"))
    cells = [str(c.channel), add("off_null_like", off, off, kind="text")]
    cells.append(_fine_bulk(n, add))
    kept_text, kept_precision = width_factor(n.get("kept_width_factor"))
    add("kept_width_factor", n.get("kept_width_factor"), kept_text, precision=kept_precision)
    kept_frames = add("kept_frames", n.get("kept_frames"), fmt_int(n.get("kept_frames")), precision=0, kind="int")
    cells.append(_math(kept_text) if kept_frames == DASH else f"{_math(kept_text)} ({_math(kept_frames)})")
    cells.append(_math(add("kept_spread", n.get("kept_spread"), fmt(n.get("kept_spread"), 1), precision=1)))
    return cells


def _fine_bulk(n, add) -> str:
    """``fine_bulk_size`` where the fine null was read on fewer bins than the coarse bulk; the dash otherwise."""
    bulk, fine = n.get("bulk_size"), n.get("fine_bulk_size")
    if not (_finite(bulk) and _finite(fine)) or int(fine) == int(bulk):
        return DASH
    return _math(add("fine_bulk_size", fine, fmt_int(fine), precision=0, kind="int"))


def _exchangeability(n, add) -> tuple[str, str]:
    """The exceedance cell (measured / predicted) and the rank cell (rho with the dagger, quiet frames)."""
    measured, predicted, rho = n.get("exch_measured"), n.get("exch_predicted"), n.get("exch_rho")
    if not (_finite(measured) and _finite(predicted) and _finite(rho)):
        return DASH, DASH
    m = add("exch_measured", measured, fmt(measured, 3), precision=3)
    p = add("exch_predicted", predicted, fmt(predicted, 3), precision=3)
    r = add("exch_rho", rho, fmt_int(rho, thousands=False), precision=0, kind="int")
    basis = str(n.get("exchangeability_rank_basis") or "")
    if basis:
        add("exch_rank_basis", basis, basis, kind="text")
    rank = f"${r}{DAGGER if basis == DIAGNOSTIC_RANK else ''}$"
    frames = n.get("exch_frames")
    if _finite(frames):
        rank += f" ({_math(add('exch_frames', frames, fmt_int(frames), precision=0, kind='int'))})"
    return f"{_math(m)} / {_math(p)}", rank


def _floor(n, add) -> tuple[str, str]:
    """The floor cell and its basis cell (evidence: basis (frames)); a refused floor is the dash and ``refused``."""
    evidence = str(n.get("floor_evidence") or "")
    if not evidence:
        return DASH, DASH
    if evidence == "refused" or not _finite(n.get("floor_db")):
        add("floor_evidence", evidence, evidence, kind="text", status="refused")
        return DASH, tex(evidence)
    status = "measured" if evidence == "measured" else "derived"
    floor = _math(add("floor_db", n.get("floor_db"), fmt(n.get("floor_db"), 1), precision=1, status=status))
    add("floor_evidence", evidence, evidence, kind="text")
    basis = floor_basis(n)
    text = tex(evidence)
    if basis and basis != "none":
        plain, latex = _BASIS_TEXT.get(basis, (basis, tex(basis)))
        add("floor_basis", basis, plain, kind="text")
        text += f": {latex}"
    frames = n.get("floor_frames")
    if _finite(frames) and int(frames) > 0:
        text += f" ({_math(add('floor_frames', frames, fmt_int(frames), precision=0, kind='int'))})"
    return floor, text


def _sentence_numbers(run: Run, frag: Fragment) -> None:
    """The ch05 sentence: channels within 0.1 dB of mu_0 and the width-factor ranges."""
    described = [c for c in run.channels if _finite(c.null.get("coarse_centre_db"))]
    frag.add("ch05.nulls.centre_tolerance_db", CENTRE_TOLERANCE_DB, precision=1, status="derived", column="criterion")
    # the denominator of the ch05 sentence is every channel with a finite centre, including the eight whose
    # calibration block carries no null population (their "centre" is the carrier's), not channels with a usable null
    frag.add("ch05.nulls.channels", len(described), precision=0, kind="int", column="channels described")
    if not described:
        frag.notes.append("ch05 sentence numbers: no channel carries a coarse centre, so no fraction is computed")
        return
    near = [c for c in described if abs(float(c.null["coarse_centre_db"])) <= CENTRE_TOLERANCE_DB]
    fraction = len(near) / len(described)
    frag.add("ch05.nulls.within_0p1db_count", len(near), precision=0, kind="int", column="within 0.1 dB")
    frag.add("ch05.nulls.within_0p1db_fraction", fraction, precision=2, status="derived", column="within 0.1 dB",
             renderings=(f"{len(near)}/{len(described)}", f"{len(near)} of {len(described)}"))
    frag.add("ch05.nulls.within_0p1db_channels", ", ".join(str(c.channel) for c in near), kind="text",
             renderings=(", ".join(str(c.channel) for c in near),), column="within 0.1 dB")

    def add_range(name: str, values: list[float], column: str) -> None:
        finite = [float(v) for v in values if _finite(v)]
        if not finite:
            frag.notes.append(f"ch05 sentence numbers: no finite {name}, range not emitted")
            return
        lo, hi = min(finite), max(finite)
        frag.add(f"ch05.nulls.{name}_low", lo, precision=2, column=column)
        frag.add(f"ch05.nulls.{name}_high", hi, precision=2, column=column)
        frag.add(f"ch05.nulls.{name}_range", f"{fmt(lo, 2)}--{fmt(hi, 2)}", kind="range", status="derived", column=column,
                 renderings=(f"{fmt(lo, 2)}-{fmt(hi, 2)}", f"{fmt(lo, 2)}-{fmt(hi, 2)}x", f"{fmt(lo, 1)}-{fmt(hi, 1)}",
                             f"{fmt(lo, 1)}-{fmt(hi, 1)}x"))

    if near:
        add_range("coarse_core_width_factor", [c.null.get("coarse_core_width_factor") for c in near], "within 0.1 dB")
        add_range("fine_core_width_factor", [c.null.get("fine_core_width_factor") for c in near], "within 0.1 dB")
    else:
        frag.notes.append("ch05 sentence numbers: no channel within 0.1 dB of mu_0, so no width-factor range among them")
    add_range("fine_core_width_factor_all", [c.null.get("fine_core_width_factor") for c in described], "all channels")


def _iid_tail_constant(run: Run, frag: Fragment) -> None:
    """The i.i.d. tail fraction: a constant of the F model, so it is the caption's number, not a column's."""
    values = {round(100.0 * float(c.null["coarse_tail_fraction_iid"]), 2)
              for c in run.channels if _finite(c.null.get("coarse_tail_fraction_iid"))}
    if not values:
        return
    if len(values) == 1:
        pct = values.pop()
        frag.add(f"{KEY}.coarse_tail_fraction_iid_pct", pct, precision=2, status="derived", column="caption",
                 renderings=(fmt(pct, 2),))
        frag.notes.append(f"the i.i.d. tail fraction beyond three core widths is {fmt(pct, 2)} % on every channel -- a "
                          "constant of the F model, not a per-channel measurement -- so it is stated in the caption and "
                          f"has no column; it is still carried per channel as {KEY}.coarse_tail_fraction_iid_pct.chNN "
                          f"and once as {KEY}.coarse_tail_fraction_iid_pct")
    else:
        frag.notes.append("the i.i.d. tail fraction is not constant across channels on this run "
                          f"({fmt(min(values), 2)}--{fmt(max(values), 2)} %): it is carried per channel as "
                          f"{KEY}.coarse_tail_fraction_iid_pct.chNN but still has no column")


def _chs(channels) -> str:
    return ", ".join(str(ch) for ch in channels)


def _panel_note(frag: Fragment) -> None:
    frag.notes.append("two panels stacked in one box, each keyed by the channel (the sixteen columns the stub names "
                      "measure 1,005 pt in one tabular, against a 470 pt text block and 650 pt sideways): panel 1 is the "
                      "null population, its centre and its width factors, panel 2 the bulk, the exchangeability check, "
                      "the floor and the plate; the chapter supplies one table environment, caption and label for both")
    frag.notes.append("off null-like, the fine null's bulk-bin count and the kept-half width factor, frame count and "
                      f"probe spread are printed in {LEDGER_LABEL} (the {LEDGER_NAME} fragment, Appendix C) beside the "
                      "channel's plate, not here")


def _notes(run: Run, frag: Fragment) -> None:
    """What the chapter table dashes or marks, and why."""
    present = [c for c in run.channels if c.has("null")]
    absent = [c.channel for c in run.channels if not c.has("null")]
    if absent:
        frag.notes.append(f"no null section (every cell of both panels dashed): channels {_chs(absent)}")

    def select(pred):
        return [c.channel for c in present if pred(c.null)]

    no_exch = [c for c in present if not _finite(c.null.get("exch_measured"))]
    no_rank = [c for c in no_exch if not str(c.null.get("exchangeability_rank_basis") or "")]
    skipped = [c for c in no_exch if str(c.null.get("exchangeability_rank_basis") or "")]
    if no_rank:
        why = sorted({str(c.selection.get("status") or "no selection section") for c in no_rank})
        frag.notes.append("exchangeability dashed: no rank to test at (neither a selected nor a diagnostic point; exch_* keys "
                          f"absent; selector status {', '.join(why)}) on channels {_chs(c.channel for c in no_rank)}")
    if skipped:
        reasons = sorted({p.strip() for c in skipped for p in str(c.null.get("notes") or "").split(";")
                          if "exchangeability skipped" in p})
        why = "; ".join(reasons) if reasons else "the check did not run"
        frag.notes.append("exchangeability dashed: a diagnostic rank existed but the evaluation block had too few quiet frames "
                          f"({why}) on channels {_chs(c.channel for c in skipped)}")
    daggered = select(lambda n: _finite(n.get("exch_measured")) and str(n.get("exchangeability_rank_basis") or "") == DIAGNOSTIC_RANK)
    if daggered:
        frag.notes.append("rank column: the dagger marks the rank of the least-residual diagnostic point of the calibration "
                          f"surface, not a selected operating point (no channel has one), on channels {_chs(daggered)}; "
                          "the check runs on the evaluation block's coarse-quiet frames (n_q)")
    not_null_like = select(lambda n: off_null_like_text(n.get("off_null_like")) == "no")
    if not_null_like:
        frag.notes.append("source column: the asterisk marks a recorded off population that is not null-like (centre beyond "
                          "2% of mu_0 or core width factor above 5: a carrier persists after the recorded sign-off); the "
                          f"measured off-era p90 floor is kept on channels {_chs(not_null_like)}")
    refused = select(lambda n: str(n.get("floor_evidence") or "") == "refused" or
                     (str(n.get("floor_evidence") or "") and not _finite(n.get("floor_db"))))
    if refused:
        # the reason is the producer's own, from floor_population, not inferred from the evidence alone
        by_channel = {c.channel: c for c in present}
        why = sorted({str(by_channel[ch].null.get("floor_population") or "no floor_population recorded") for ch in refused})
        frag.notes.append("floor dashed and basis 'refused' (no floor is stated) on channels "
                          f"{_chs(refused)}: {'; '.join(why)}")
    bulk_floor = select(lambda n: _finite(n.get("floor_db")) and floor_basis(n) == "bulk left side (not H0)")
    if bulk_floor:
        frag.notes.append("basis 'bulk left side': the floor is stated from the bulk's left-side scale about its median (not "
                          "an H0 population: the kept-half probes disagree beyond spread 3 or the bulk centre is not at mu_0; "
                          f"the frame count is the block's) on channels {_chs(bulk_floor)}")
    kept_floor = select(lambda n: _finite(n.get("floor_db")) and floor_basis(n) == "kept half about mu_0")
    if kept_floor:
        frag.notes.append("basis 'kept half': the floor is stated from the kept half about mu_0 (the register's convention) "
                          f"on channels {_chs(kept_floor)}")
    frag.notes.append(f"plate references use the label pattern {PLATE_LABEL}")


def _ledger_notes(run: Run, frag: Fragment) -> None:
    """What the appendix ledger dashes, and why."""
    present = [c for c in run.channels if c.has("null")]
    absent = [c.channel for c in run.channels if not c.has("null")]
    if absent:
        frag.notes.append(f"no null section (every cell dashed): channels {_chs(absent)}")

    def select(pred):
        return [c.channel for c in present if pred(c.null)]

    no_off = select(lambda n: off_null_like_text(n.get("off_null_like")) == DASH)
    if no_off:
        frag.notes.append(f"off null-like dashed: no recorded off population on channels {_chs(no_off)}")
    not_null_like = select(lambda n: off_null_like_text(n.get("off_null_like")) == "no")
    if not_null_like:
        frag.notes.append("off population not null-like (centre beyond 2% of mu_0 or core width factor above 5: a carrier "
                          "persists after the recorded sign-off); the measured off-era p90 floor is kept, and the source "
                          f"column of {LABEL} carries the asterisk, on channels {_chs(not_null_like)}")
    reduced = select(lambda n: _finite(n.get("bulk_size")) and _finite(n.get("fine_bulk_size")) and
                     int(n["fine_bulk_size"]) != int(n["bulk_size"]))
    if reduced:
        frag.notes.append("fine null read on fewer bulk bins than the coarse bulk because the nominal window is excluded on "
                          f"a suspect anchor: channels {_chs(reduced)}; the dash elsewhere means the two agree")
    no_kept = select(lambda n: not _finite(n.get("kept_width_factor")))
    if no_kept:
        frag.notes.append("kept-half width factor and spread dashed (fewer than 30 kept frames; the count is printed): "
                          f"channels {_chs(no_kept)}")
    frag.notes.append("spread is the largest over the smallest of the register's three kept-half probes (32 / 5 / 0.3 %); "
                      "the kept half states the floor only when it is at most 3 and the bulk centre is within 2% of mu_0")
    frag.notes.append(f"one row per channel, the same shape as {LABEL}: this is the term-by-term evidence behind that "
                      "table's source and floor columns, and belongs beside the channel's plate")


def build(run: Run) -> Fragment:
    """The chapter-8 table: two panels stacked in one box, sharing the channel column."""
    frag = Fragment(NAME, LABEL, "")
    rows = [_row(c, frag) for c in run.channels]
    panel1 = booktabs(PANEL1_HEADER, [one for one, _ in rows], PANEL1_ALIGN)
    panel2 = booktabs(PANEL2_HEADER, [two for _, two in rows], PANEL2_ALIGN)
    frag.tex = stack([(PANEL1_CAPTION, panel1), (PANEL2_CAPTION, panel2)])
    _sentence_numbers(run, frag)
    _iid_tail_constant(run, frag)
    _panel_note(frag)
    _notes(run, frag)
    return frag


def build_ledger(run: Run) -> Fragment:
    """The appendix companion: the per-channel evidence the chapter table no longer prints."""
    frag = Fragment(LEDGER_NAME, LEDGER_LABEL, "")
    frag.tex = booktabs(LEDGER_HEADER, [_ledger_row(c, frag) for c in run.channels], LEDGER_ALIGN)
    _ledger_notes(run, frag)
    return frag


BUILDERS = (build, build_ledger)
