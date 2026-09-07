r"""``tab:calibration:nulls``: the current-era null calibration of every channel.

One row per channel, read from the ledger's ``null`` section: the null
calibration on the *calibration block* of the current era (the null
population's block: the floor, the widths that score both blocks and the
kept-half scale are read there; see :mod:`rfisher_results.archive.nulls` and
``run.py`` step 7). The replay on the evaluation block (``null_evaluation``)
belongs to the blocked-evaluation table. Only the exchangeability check reads
held-out frames: the evaluation block's coarse-quiet frames.

No channel of the 2026-09-07 run has a selected operating point (the
within-era drift screen refused every channel), so the rank the
exchangeability check runs at is the least-residual *diagnostic* point's
(``null.exchangeability_rank_basis`` = ``diagnostic point``); the rank column
marks it with a dagger and a note says so. A selected rank prints without it.

Columns (ledger key under ``null.`` unless stated)::

    ch                 channel number
    $N$                era_frames: frames of the calibration block. The coarse null is read
                       from these frames only where the channel has no verified off era; where
                       it has one the coarse row is that population (coarse_frames, printed as
                       the floor's own count), which is why $N$ and the floor's frame count
                       differ on channel 35 (6,152 against 11,199)
    $|\mathcal B|$     bulk_size: bulk bins of the fine null; when fine_bulk_size is smaller
                       (the nominal window excluded because the anchor is suspect) it follows
                       in parentheses
    source             null_source shortened -- ``off era`` (verified transmitter-off era),
                       ``off era (not null-like)`` (the same, failing the null-like check),
                       ``bulk (mixture)`` (bulk of the mixture, declared), ``off epoch not
                       null-like; bulk (mixture)`` (older ledgers); mixture_declared appends
                       ``(mixture)`` when the source text does not already say so
    off null-like      off_null_like -- ``yes`` / ``no`` where a recorded off population exists
                       (off_frames > 0; the population is then the null, so its centre and
                       width are the coarse columns), the dash otherwise
    centre             coarse_centre: median of F/mu_0 over the null population, against 1
                       (the packed-weight prediction)
    $\hat\sigma_c$     coarse_core_sigma: left-side robust scale of F/mu_0 about the centre
                       (the i.i.d. model gives 0.00239)
    $W_c$ raw / core   coarse_raw_width_factor / coarse_core_width_factor: measured over
                       i.i.d. width, standard deviation and robust core
    $W_f$ raw / core   fine_raw_width_factor / fine_core_width_factor: the same for the
                       fine per-bin statistic on the bulk bins
    $W_{\rm kept}$ (n) kept_width_factor with kept_frames: the register's kept-half scale
                       about mu_0 (frames with F/mu_0 <= 1) over the i.i.d. width; undefined
                       below 30 kept frames (the count still prints)
    spread             kept_spread: largest over smallest of the three kept-half probe
                       estimates (the register's 32 / 5 / 0.3 % probes); the kept half states
                       the floor only when this is at most kept_spread_limit (3) and the bulk
                       centre is within 2 % of mu_0
    tail \%            coarse_tail_fraction: fraction of frames beyond three core widths
                       above the centre, in percent
    i.i.d. \%          coarse_tail_fraction_iid: the same fraction under the F model
    exch.              exch_measured / exch_predicted: designated-bin exceedance against the
                       bulk's rank rho on the evaluation block's quiet frames, against the
                       combinatorial (|B|+1-rho)/(|B|+1); the dash when no rank existed
                       (exchangeability_rank_basis empty: the selector refused) or the block
                       had fewer than 30 quiet frames (notes: ``exchangeability skipped``)
    $\rho$ ($n_q$)     exch_rho with exch_frames (quiet frames tested); the dagger marks a
                       diagnostic rank (exchangeability_rank_basis ``diagnostic point``)
    floor dB           floor_db; the dash when the floor is refused
    basis              floor_evidence with floor_basis and floor_frames --
                       ``measured: off era p90 (n)`` (n frames with a shelf estimate),
                       ``stated: kept half about mu_0 (n)`` (n kept frames),
                       ``stated: bulk left side, not H_0 (n)`` (n = the block's frames), or
                       ``refused`` (floor_basis ``none``: the bulk centre is beyond 0.1 of
                       mu_0, so the block carries no null population); an older ledger without
                       floor_basis has it inferred from floor_population
    plate              the channel's histogram plate, ``\ref{fig:archive:plate:chNN}``

Every printed value is added to the fragment as ``ch08.nulls.<column>.chNN``
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

from .core import DASH, Channel, Fragment, Run, booktabs, fmt, fmt_int, tex

NAME = "calibration_nulls"
LABEL = "tab:calibration:nulls"
KEY = "ch08.nulls"
PLATE_LABEL = "fig:archive:plate:ch{channel:02d}"
CENTRE_TOLERANCE_DB = 0.1
DAGGER = r"^\dagger"                      # inside the rank cell's math mode: a diagnostic rank, not a selected one
DIAGNOSTIC_RANK = "diagnostic point"      # null.exchangeability_rank_basis when no point was selected

COLUMNS = (  # (header cell, alignment)
    ("ch", "l"), ("$N$", "r"), (r"$|\mathcal{B}|$", "r"), ("source", "l"), ("off null-like", "l"),
    (r"centre $F/\mu_0$", "r"), (r"$\hat\sigma_c$", "r"),
    (r"$W_c^{\mathrm{raw}}$", "r"), (r"$W_c^{\mathrm{core}}$", "r"), (r"$W_f^{\mathrm{raw}}$", "r"), (r"$W_f^{\mathrm{core}}$", "r"),
    (r"$W_{\mathrm{kept}}$ ($n$)", "r"), ("spread", "r"), (r"tail \%", "r"), (r"i.i.d.\ \%", "r"),
    (r"exch.\ meas./pred.", "r"), (r"$\rho$ ($n_q$)", "r"), ("floor dB", "r"), ("basis", "l"), ("plate", "l"),
)
HEADER = [h for h, _ in COLUMNS]
ALIGN = "".join(a for _, a in COLUMNS)

_SOURCE_SHORT = {
    "verified transmitter-off era": "off era",
    "verified transmitter-off era (not null-like)": "off era (not null-like)",
    "bulk of the mixture (declared)": "bulk (mixture)",
    "recorded off epoch, not null-like": "off epoch not null-like",
    "independently identified quiet subset": "quiet subset",
    "reference-bin surrogate": "reference surrogate",
    "model-only null": "model-only",
}
_BASIS_TEXT = {  # floor_basis -> (plain rendering, LaTeX cell text)
    "off era p90": ("off era p90", "off era p90"),
    "kept half about mu_0": ("kept half about mu_0", r"kept half about $\mu_0$"),
    "bulk left side (not H0)": ("bulk left side, not H0", r"bulk left side, not $H_0$"),
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


def _row(c: Channel, frag: Fragment) -> list[str]:
    n = c.null
    ch = c.channel
    where = {"channel": ch}

    def add(column: str, value, text: str, *, precision: int | None = None, kind: str = "float", status: str = "measured"):
        if text != DASH:
            frag.add(f"{KEY}.{column}.ch{ch:02d}", value, precision=precision, kind=kind, status=status,
                     renderings=(text,), row=where, column=column)
        return text

    cells = [str(ch)]
    cells.append(_math(add("era_frames", n.get("era_frames"), fmt_int(n.get("era_frames")), precision=0, kind="int")))
    cells.append(_bulk(n, add))
    src = source_text(n.get("null_source"), n.get("mixture_declared"))
    cells.append(tex(add("null_source", src, src, kind="text")))
    off = off_null_like_text(n.get("off_null_like"))
    cells.append(add("off_null_like", off, off, kind="text"))
    cells.append(_math(add("coarse_centre", n.get("coarse_centre"), fmt(n.get("coarse_centre"), 4), precision=4)))
    sigma = fmt(n.get("coarse_core_sigma"), 3, sig=True)
    cells.append(_math(add("coarse_core_sigma", n.get("coarse_core_sigma"), sigma)))
    for key in ("coarse_raw_width_factor", "coarse_core_width_factor", "fine_raw_width_factor", "fine_core_width_factor"):
        text, precision = width_factor(n.get(key))
        cells.append(_math(add(key, n.get(key), text, precision=precision)))
    kept_text, kept_precision = width_factor(n.get("kept_width_factor"))
    add("kept_width_factor", n.get("kept_width_factor"), kept_text, precision=kept_precision)
    kept_frames = add("kept_frames", n.get("kept_frames"), fmt_int(n.get("kept_frames")), precision=0, kind="int")
    cells.append(_math(kept_text) if kept_frames == DASH else f"{_math(kept_text)} ({_math(kept_frames)})")
    cells.append(_math(add("kept_spread", n.get("kept_spread"), fmt(n.get("kept_spread"), 1), precision=1)))
    for key in ("coarse_tail_fraction", "coarse_tail_fraction_iid"):
        value = n.get(key)
        pct = 100.0 * float(value) if _finite(value) else None
        cells.append(_math(add(f"{key}_pct", pct, fmt(pct, 2), precision=2)))
    cells.extend(_exchangeability(n, add))
    cells.extend(_floor(n, add))
    label = PLATE_LABEL.format(channel=ch)
    plate = rf"Fig.~\ref{{{label}}}"
    add("plate", label, plate, kind="text")
    cells.append(plate)
    return cells


def _bulk(n, add) -> str:
    """``bulk_size``, with ``fine_bulk_size`` in parentheses when the fine null was read on fewer bins."""
    bulk = n.get("bulk_size")
    cell = _math(add("bulk_size", bulk, fmt_int(bulk), precision=0, kind="int"))
    fine = n.get("fine_bulk_size")
    if _finite(bulk) and _finite(fine) and int(fine) != int(bulk):
        cell += f" ({_math(add('fine_bulk_size', fine, fmt_int(fine), precision=0, kind='int'))})"
    return cell


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


def _chs(channels) -> str:
    return ", ".join(str(ch) for ch in channels)


def _notes(run: Run, frag: Fragment) -> None:
    """What the table dashes or marks, and why."""
    present = [c for c in run.channels if c.has("null")]
    absent = [c.channel for c in run.channels if not c.has("null")]
    if absent:
        frag.notes.append(f"no null section (every cell dashed): channels {_chs(absent)}")

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
    no_kept = select(lambda n: not _finite(n.get("kept_width_factor")))
    if no_kept:
        frag.notes.append("kept-half width factor and spread dashed (fewer than 30 kept frames; the count is printed): "
                          f"channels {_chs(no_kept)}")
    no_off = select(lambda n: off_null_like_text(n.get("off_null_like")) == DASH)
    if no_off:
        frag.notes.append(f"off null-like dashed: no recorded off population on channels {_chs(no_off)}")
    not_null_like = select(lambda n: off_null_like_text(n.get("off_null_like")) == "no")
    if not_null_like:
        frag.notes.append("off population not null-like (centre beyond 2% of mu_0 or core width factor above 5: a carrier "
                          "persists after the recorded sign-off); the measured off-era p90 floor is kept on channels "
                          f"{_chs(not_null_like)}")
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
        frag.notes.append("floor stated from the bulk's left-side scale about its median (not an H0 population: the kept-half "
                          "probes disagree beyond spread 3 or the bulk centre is not at mu_0; the frame count is the block's) "
                          f"on channels {_chs(bulk_floor)}")
    kept_floor = select(lambda n: _finite(n.get("floor_db")) and floor_basis(n) == "kept half about mu_0")
    if kept_floor:
        frag.notes.append(f"floor stated from the kept half about mu_0 (the register's convention) on channels {_chs(kept_floor)}")
    reduced = select(lambda n: _finite(n.get("bulk_size")) and _finite(n.get("fine_bulk_size")) and
                     int(n["fine_bulk_size"]) != int(n["bulk_size"]))
    if reduced:
        frag.notes.append("fine null read on fewer bulk bins (in parentheses) because the nominal window is excluded on a "
                          f"suspect anchor: channels {_chs(reduced)}")
    frag.notes.append(f"plate references use the label pattern {PLATE_LABEL}")


def build(run: Run) -> Fragment:
    frag = Fragment(NAME, LABEL, "")
    rows = [_row(c, frag) for c in run.channels]
    frag.tex = booktabs(HEADER, rows, ALIGN)
    _sentence_numbers(run, frag)
    _notes(run, frag)
    return frag
