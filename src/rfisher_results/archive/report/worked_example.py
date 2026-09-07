r"""``fig:example`` and its table: the worked frame of chapter 6
(``sec:detection:archive``, the ``v5 archive rerun`` stub near line 335).

What the chapter walks through. Two frames of one channel through the fine
decision: an exemplar the designated set resolves, and a companion the coarse
rule would keep. The stub asks for the same two frames regenerated from the v5
product, "and replace the illustrative boundary with the channel's selected
``eta* T_(rho*)``".

**The boundary.** When the run leaves a point standing on the channel --- a
selected ``(rho*, eta*)`` or, failing that, the run's declared diagnostic
``(rho+, eta+)`` --- the figure draws that frame's ``eta T_(rho)``, with
``T_(rho)`` the ``rho``-th *smallest* usable-bulk value (the one-based
ascending rank of ``rfisher.residual_scores.bundle``, whose exact rational
form the deployed comparison uses), and the table prints the boundary, the
pair, its basis, and the fine decision each frame gets from it. The star marks
a selection and the dagger a diagnostic, as the chapter's own tables do.

**On this run's channel 36 there is nothing to draw.** The v5 run selected no
operating point anywhere, and channel 36 is one of the four channels on which
the selector *refused before evaluating a surface at all*: its ledger records
``selection.status = refused``, ``surface_points = 0`` and no diagnostic point
either (``diagnostic_rho`` and ``diagnostic_eta`` are null), because frames
without a shelf estimate have no floor to be booked at. So the figure draws no
boundary and prints the dash for ``rho``, ``eta`` and ``eta T_(rho)``, states
the selector's own refusal text on the panel, and says so in the fragment's
notes. Nothing here substitutes a plausible line for a measured one --- and
the companion frame is itself one of the era's frames with no shelf estimate,
which is the refusal's own cause standing in the picture.

**The frames.** The chapter names channel 36 (``freq_id`` 506) and two
captures. They are located in the v5 product by time, never by row number:

  exemplar   the cohort frame nearest :data:`EXEMPLAR_TIME`
             (2025-07-31 15:52:22 UT), accepted only within
             :data:`TIME_TOLERANCE_S` of it
  companion  the cohort frame of the calendar day :data:`COMPANION_DATE`
             (2025-05-16 UT) with the smallest ``F/mu_0`` --- the chapter
             identifies it as that day's frame below the coarse
             positive-excess boundary

**The cohort** is the channel's current era as the run defines it: frames the
health gate admits (``Product.selected``) that carry a time, whose UTC month
lies between the ledger's ``era.current_first_month`` and
``current_last_month``. The count is checked against the ledger's
``era.current_frames`` and any disagreement is a note rather than a silent
substitution. Without ``pilot_proxy`` the health gate falls back to
valid-only; the fragment prints which gate ran.

**Per frame, from the product** (:class:`~rfisher_results.archive.products.Product`):
``frame_time`` (UT), ``unit_event_id`` and ``frame_in_unit`` (the physical
archive key), ``statistic`` (``F/mu_0``, the coarse decision), ``shelf_db``
(finite only where the normalized excess is positive), and the exact fine
terms ``fine_power_u64`` of that row, from which ``T[f] = 2 S_0[f] /
(S_1[f] + S_2[f])`` is formed by ``products.fine_power_ratio`` --- the
deployed statistic, not a re-derived float. The designated set and the usable
bulk come from the ledger's measured anchor (``anchor.anchor_bin``,
``designated_half_width``) through
:func:`rfisher_results.archive.anchors.designated_set` and
:func:`~rfisher_results.archive.anchors.bulk_mask` at the product's own pad
factor and guard, so the bulk is the same 125 bins the null calibration used.

**The figure** (``fig_worked_example``; two stacked panels sharing one x axis,
6.35 in wide):

  x axis        signed padded-bin offset from the measured anchor,
                ``((f - f_a + 128) mod 256) - 128``, so the designated window
                sits at the centre; the top axis of panel (a) is the same axis
                in RF offset from the anchor (one fine bin is
                ``f_s / (2 K L_F) = 11.92`` Hz, and the campaign's
                ``sense = -1`` makes a positive bin offset a negative RF
                offset)
  y axis        ``T[f]``, logarithmic and shared by both panels so the two
                frames are read against one another
  curve         ``T[f]`` at every padded bin (INK)
  bulk          the usable-bulk bins as dots (PENDING): the null population
                the rank rule is taken over
  designated    the designated bins as filled markers (MEASURED), the maximum
                ringed and labelled with its value and its ratio to the bulk
                median
  window        the designated window ``f_a +- 2`` shaded (LIGHT_BLUE)
  bulk median   the frame's own bulk median, dashed (MODEL); the bulk 90th
                percentile dotted (PENDING)
  boundary      *absent*: a boxed line on panel (a) states the refusal
  panel text    the capture time, the acquisition's event id, ``F/mu_0``
                against the coarse boundary 1, and --- for a frame with no
                shelf estimate --- that it has none

**The table** (``tables/worked_example.tex``, two panels stacked in one box):
panel 1 is one column per frame, one row per printed quantity (time, event id,
frame in unit, ``F/mu_0``, the survey flag, the shelf estimate, ``T`` at each
of the five designated bins, the designated maximum, the exact integer pair
``2 S_0`` and ``S_1 + S_2`` at the anchor, the bulk median and 90th
percentile, the ratio, and the operating-point boundary, dashed); panel 2 is
the cohort and the selector's verdict (era, cohort frames, the ledger's own
count, anchor bin, designated bins, bulk size, frames the coarse rule keeps,
the weakest frame of the cohort and its ``F/mu_0``, the operating-point basis,
rank and multiplier, the selection status, surface points, and the refusal
text). The designated bins and whether the weakest frame is the companion are
keyed but not printed: the five ``T[f]`` rows are labelled by those bins, and
a companion that is not the weakest is a note.

Numbers are keyed ``ch06.worked_example.<name>.<frame>`` with ``frame`` in
``exemplar``/``companion``, and ``ch06.worked_example.<name>`` for a
cohort-level value.
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import matplotlib
matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import FixedFormatter, FixedLocator, NullLocator

from ... import style
from ..anchors import bulk_mask, designated_set
from ..products import FINE_BIN_HZ, FINE_BINS, Product, fine_power_ratio
from .core import DASH, Channel, Fragment, Run, booktabs, fmt, fmt_int, tex

NAME = "worked_example"
LABEL = "fig:example"
FIGURE = "fig_worked_example"
PDF_TITLE = "Fine spectra of two archive frames with the designated window and bulk"
PREFIX = "ch06.worked_example"

CHANNEL = 36                                       # the channel the chapter walks through (freq_id 506)
EXEMPLAR_TIME = dt.datetime(2025, 7, 31, 15, 52, 22, tzinfo=dt.timezone.utc)
COMPANION_DATE = dt.date(2025, 5, 16)
TIME_TOLERANCE_S = 60.0                            # the exemplar must be this close to the stated capture time
LINTHRESH_BINS = 6.0                               # x axis: linear inside +-6 padded bins, logarithmic outside
LINSCALE = 1.15
XTICKS = (-100, -30, -10, -2, 0, 2, 10, 30, 100)   # symlog reads its own ticks badly; these are set by hand
EXEMPLAR, COMPANION = "exemplar", "companion"
FRAME_LABEL = {EXEMPLAR: "exemplar (masked)", COMPANION: "companion (kept by the coarse rule)"}


def _utc(seconds: float) -> dt.datetime:
    return dt.datetime.fromtimestamp(float(seconds), dt.timezone.utc)


def _stamp(seconds: float) -> str:
    return _utc(seconds).strftime("%Y-%m-%d %H:%M:%S") + " UT" if math.isfinite(seconds) else ""


def _month(seconds: float) -> str:
    d = _utc(seconds)
    return f"{d.year:04d}-{d.month:02d}"


# ------------------------------------------------------------------ the frames
@dataclass
class FrameRow:
    """One frame of the example: its identity, its coarse verdict, its fine spectrum."""

    which: str
    row: int
    time: float
    event_id: int
    frame_in_unit: int
    statistic: float                    # F / mu_0
    rejected: bool
    shelf_db: float
    fine: np.ndarray                    # T[f], (256,)
    target_terms: int                   # 2 S_0[f_a]
    reference_terms: int                # S_1[f_a] + S_2[f_a]
    designated: np.ndarray              # T on the designated bins, in bin order
    designated_max: float
    bulk_median: float
    bulk_p90: float
    boundary: float = math.nan          # eta * T_(rho) on this frame's bulk; NaN when the run leaves no point

    @property
    def ratio(self) -> float:
        return self.designated_max / self.bulk_median if self.bulk_median > 0 else math.nan

    @property
    def label(self) -> str:
        return FRAME_LABEL[self.which]


@dataclass
class Example:
    """Everything the figure and the table print, and the reason for anything absent."""

    channel: int
    freq_id: int
    product: Path | None = None
    frames: dict[str, FrameRow] = field(default_factory=dict)
    anchor_bin: int = -1
    sense: int = -1                     # the receiver's spectral sense: +1 bin is -sense in RF
    designated_bins: tuple[int, ...] = ()
    bulk: np.ndarray | None = None
    bulk_size: int = 0
    era_label: str = ""
    cohort_frames: int = 0
    ledger_frames: float = math.nan
    kept_frames: int = 0                # cohort frames the coarse rule keeps (F <= mu_0)
    weakest_time: float = math.nan
    weakest_statistic: float = math.nan
    weakest_is_companion: bool = False
    health_schema: str = ""
    status: str = ""
    refusal: str = ""
    surface_points: float = math.nan
    rho: float = math.nan
    eta: float = math.nan
    point_basis: str = ""               # 'selected' or 'diagnostic'; empty when the run leaves neither
    reasons: list[str] = field(default_factory=list)
    inputs: list[Path] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return EXEMPLAR in self.frames and COMPANION in self.frames

    @property
    def has_point(self) -> bool:
        return math.isfinite(self.rho) and math.isfinite(self.eta) and self.rho >= 1



def _number(value) -> float:
    try:
        return float(value) if value is not None else math.nan
    except (TypeError, ValueError):
        return math.nan


def _channel_record(run: Run, channel: int) -> Channel | None:
    return run.by_channel().get(channel)


def _product_path(run: Run, record: Channel) -> Path | None:
    products_dir = run.run.get("products_dir")
    if not products_dir:
        return None
    path = Path(str(products_dir)) / record.product
    return path if path.is_file() else None


def _cohort_mask(product: Product, record: Channel) -> tuple[np.ndarray, str]:
    """The channel's current era: selected, timed, and inside the ledger's month range."""
    era = record.era
    first, last = str(era.get("current_first_month", "")), str(era.get("current_last_month", ""))
    time = product.frame_time
    timed = np.isfinite(time)
    months = np.array([_month(t) if ok else "" for t, ok in zip(time, timed)])
    mask = product.selected & timed
    if first:
        mask &= months >= first
    if last:
        mask &= months <= last
    label = f"{first}..{last} ({era.get('current_state', '')})" if first and last else ""
    return mask, label


def _boundary(inside: np.ndarray, rho: float, eta: float) -> float:
    """``eta T_(rho)``: the multiplier times the rho-th *smallest* bulk value (the bundle's one-based rank)."""
    if not (math.isfinite(rho) and math.isfinite(eta)) or not 1 <= int(rho) <= inside.size:
        return math.nan
    return float(eta) * float(np.sort(inside)[int(rho) - 1])


def _frame_row(which: str, row: int, product: Product, terms: np.ndarray, anchor: int,
               designated: Sequence[int], bulk: np.ndarray, rho: float = math.nan,
               eta: float = math.nan) -> FrameRow:
    fine = fine_power_ratio(terms[None, :, :])[0]
    values = fine[list(designated)]
    inside = fine[bulk]
    return FrameRow(which=which, row=row, time=float(product.frame_time[row]),
                    event_id=int(product.unit_event_id[product.frame_unit_index[row]]),
                    frame_in_unit=int(product.frame_in_unit[row]),
                    statistic=float(product.statistic[row]), rejected=bool(product.rejected[row]),
                    shelf_db=float(product.shelf_db[row]), fine=fine,
                    target_terms=int(2 * int(terms[0, anchor])),
                    reference_terms=int(int(terms[1, anchor]) + int(terms[2, anchor])),
                    designated=values, designated_max=float(values.max()),
                    bulk_median=float(np.median(inside)), bulk_p90=float(np.percentile(inside, 90)),
                    boundary=_boundary(inside, rho, eta))


def example(run: Run, *, channel: int = CHANNEL) -> Example:
    """Locate the chapter's two frames in the v5 product and read them exactly."""
    record = _channel_record(run, channel)
    if record is None:
        return Example(channel, -1, reasons=[f"the run's ledger carries no channel {channel}"])
    out = Example(channel, int(record.freq_id))
    path = _product_path(run, record)
    if path is None:
        out.reasons.append(f"the run names no readable product for channel {channel} ({record.product})")
        return out
    out.product = path
    out.inputs = [record.path, path]
    selection = record.selection
    out.status = str(selection.get("status", ""))
    out.refusal = str(selection.get("refusal", ""))
    out.surface_points = _number(selection.get("surface_points"))
    out.rho, out.eta = _number(selection.get("rho")), _number(selection.get("eta"))
    out.point_basis = "selected" if math.isfinite(out.rho) and math.isfinite(out.eta) else ""
    if not out.point_basis:
        out.rho, out.eta = _number(selection.get("diagnostic_rho")), _number(selection.get("diagnostic_eta"))
        out.point_basis = "diagnostic" if math.isfinite(out.rho) and math.isfinite(out.eta) else ""
    anchor_section = record.anchor
    out.anchor_bin = int(_number(anchor_section.get("anchor_bin")) if anchor_section else -1)
    half = int(_number(anchor_section.get("designated_half_width")) or 2)
    with Product(path) as product:
        out.health_schema = product.health.schema
        out.sense = int(product.geometry.sense)
        if out.anchor_bin < 0:
            out.anchor_bin = int(product.geometry.nominal_fine_bin)
            out.reasons.append("the ledger records no measured anchor: the nominal fine bin is used")
        out.designated_bins = tuple(sorted(designated_set(out.anchor_bin, half, FINE_BINS)))
        out.bulk = bulk_mask(out.anchor_bin, pad_factor=int(product.fine_pad_factor),
                             guard_fine_bins=int(product.fine_guard_bins),
                             census_excluded_bins=tuple(int(b) for b in product.fine_census_excluded_bins),
                             designated_half_width=half)
        out.bulk_size = int(out.bulk.sum())
        cohort, out.era_label = _cohort_mask(product, record)
        out.cohort_frames = int(cohort.sum())
        out.ledger_frames = _number(record.era.get("current_frames"))
        if not cohort.any():
            out.reasons.append("the product carries no frame of the ledger's current era")
            return out
        statistic = product.statistic
        out.kept_frames = int((~product.rejected & cohort).sum())
        weakest = int(np.argmin(np.where(cohort, statistic, np.inf)))
        out.weakest_time, out.weakest_statistic = float(product.frame_time[weakest]), float(statistic[weakest])
        time = product.frame_time
        # the exemplar: the cohort frame nearest the chapter's stated capture time
        distance = np.where(cohort, np.abs(time - EXEMPLAR_TIME.timestamp()), np.inf)
        rows: dict[str, int] = {}
        nearest = int(np.argmin(distance))
        if math.isfinite(distance[nearest]) and distance[nearest] <= TIME_TOLERANCE_S:
            rows[EXEMPLAR] = nearest
        else:
            out.reasons.append(f"no cohort frame within {fmt(TIME_TOLERANCE_S, 0)} s of "
                               f"{EXEMPLAR_TIME.strftime('%Y-%m-%d %H:%M:%S')} UT: the exemplar frame is not in this product")
        # the companion: the weakest cohort frame of the chapter's stated calendar day
        day = np.array([math.isfinite(t) and _utc(t).date() == COMPANION_DATE for t in time])
        if (day & cohort).any():
            rows[COMPANION] = int(np.argmin(np.where(day & cohort, statistic, np.inf)))
        else:
            out.reasons.append(f"the cohort carries no frame captured {COMPANION_DATE.isoformat()} UT: "
                               "the companion frame is not in this product")
        if rows:
            order = sorted(rows.items(), key=lambda kv: kv[1])
            terms = product.fine_terms(np.array([row for _, row in order]))
            for (which, row), term in zip(order, terms):
                out.frames[which] = _frame_row(which, row, product, term, out.anchor_bin,
                                               out.designated_bins, out.bulk, out.rho, out.eta)
        out.weakest_is_companion = COMPANION in rows and rows[COMPANION] == weakest
    return out


# ------------------------------------------------------------------ the figure
def _offsets(bins: np.ndarray | Sequence[int], anchor: int) -> np.ndarray:
    """Signed padded-bin offset from the anchor, unwrapped to [-128, 128)."""
    return ((np.asarray(bins) - anchor + FINE_BINS // 2) % FINE_BINS) - FINE_BINS // 2


def _panel(ax, ex: Example, frame: FrameRow, *, limits: tuple[float, float]) -> None:
    axis = _offsets(np.arange(FINE_BINS), ex.anchor_bin)
    order = np.argsort(axis)
    half = len(ex.designated_bins) // 2
    ax.axvspan(-half - 0.5, half + 0.5, color=style.LIGHT_BLUE, lw=0, zorder=0)
    ax.set_xscale("symlog", linthresh=LINTHRESH_BINS, linscale=LINSCALE)
    ax.plot(axis[order], frame.fine[order], color=style.INK, lw=0.85, zorder=3)
    ax.plot(_offsets(np.flatnonzero(ex.bulk), ex.anchor_bin), frame.fine[ex.bulk], ls="none", marker="o",
            ms=2.0, mfc=style.PENDING, mec="none", zorder=4)
    designated_offsets = _offsets(np.asarray(ex.designated_bins), ex.anchor_bin)
    ax.plot(designated_offsets, frame.designated, ls="none", marker="o", ms=4.0,
            mfc=style.MEASURED, mec="none", zorder=6)
    peak = designated_offsets[int(np.argmax(frame.designated))]
    ax.plot([peak], [frame.designated_max], ls="none", marker="o", ms=9.0, mfc="none",
            mec=style.MEASURED, mew=1.0, zorder=7)
    ax.axhline(frame.bulk_median, color=style.MODEL, lw=1.0, ls="--", zorder=2)
    ax.axhline(frame.bulk_p90, color=style.PENDING, lw=0.8, ls=":", zorder=2)
    if math.isfinite(frame.boundary):
        ax.axhline(frame.boundary, color=style.FAILURE, lw=1.2, ls="-.", zorder=5)
    ax.annotate(rf"$T_{{\max}}={fmt(frame.designated_max, 2)}$" "\n"
                rf"$={fmt(frame.ratio, 1)}\times$ bulk median",
                xy=(peak, frame.designated_max), xytext=(22, -4), textcoords="offset points",
                ha="left", va="center", fontsize=7.6, color=style.INK,
                arrowprops=dict(arrowstyle="-", color=style.MUTED, lw=0.7, shrinkA=3, shrinkB=7))
    kept = "flagged" if frame.rejected else "kept"
    shelf = "no shelf estimate" if not math.isfinite(frame.shelf_db) else \
        rf"shelf ${fmt(frame.shelf_db, 1)}$ dB"
    ax.text(0.015, 0.955, rf"{tex(_stamp(frame.time))} $\cdot$ event {frame.event_id} $\cdot$ "
                          rf"$F/\mu_0={fmt(frame.statistic, 3)}$ ({kept}) $\cdot$ {shelf}",
            transform=ax.transAxes, ha="left", va="top", fontsize=7.6, color=style.INK)
    ax.set_yscale("log")
    _axes(ax, limits)



def _axes(ax, limits: tuple[float, float]) -> None:
    ax.set_ylim(*limits)
    ax.set_xlim(-FINE_BINS // 2, FINE_BINS // 2 - 1)
    ax.set_ylabel(r"$T[f]$")
    ax.xaxis.set_major_locator(FixedLocator(list(XTICKS)))
    ax.xaxis.set_major_formatter(FixedFormatter([f"${t}$" for t in XTICKS]))
    ax.xaxis.set_minor_locator(NullLocator())
    style.clean_axes(ax, grid=None)


def _point_box(ax, ex: Example) -> None:
    """What the run left standing on this channel: a point and its basis, or the selector's refusal."""
    if ex.has_point:
        star = r"^\star" if ex.point_basis == "selected" else r"^\dagger"
        text = (rf"$\rho{star}={fmt_int(ex.rho)}$, $\eta{star}={fmt(ex.eta, 4)}$ "
                rf"({tex(ex.point_basis)}): boundary $\eta{star} T_{{(\rho{star})}}$ drawn per frame")
    else:
        text = (r"no operating point: $\rho^\star$, $\eta^\star$ and $\eta^\star T_{(\rho^\star)}$ undefined,"
                " so no boundary is drawn" "\n" + tex(f"selector {ex.status or 'returned no point'}"
                                                      + (f" -- {ex.refusal}" if ex.refusal else "")))
    ax.text(0.5, 0.045, text, transform=ax.transAxes, ha="center", va="bottom", fontsize=7.4,
            color=style.FAILURE, linespacing=1.35, multialignment="center",
            bbox=dict(boxstyle="round,pad=0.32", fc=style.PAPER, ec=style.FAILURE, lw=0.6))


def figure_worked_example(ex: Example):
    """The two-panel figure; a missing frame leaves its panel empty and says why."""
    fig, axes = plt.subplots(2, 1, figsize=(style.TEXT_WIDTH, 4.5), sharex=True,
                             gridspec_kw={"hspace": 0.16})
    present = [ex.frames.get(which) for which in (EXEMPLAR, COMPANION)]
    values = np.concatenate([f.fine for f in present if f is not None]) if any(f is not None for f in present) \
        else np.array([0.5, 2.0])
    positive = values[values > 0]
    limits = (float(positive.min()) * 0.55, float(values.max()) * 2.6) if positive.size else (0.1, 10.0)
    for i, (ax, frame) in enumerate(zip(axes, present)):
        style.panel_label(ax, "ab"[i], x=-0.082, y=1.005)
        if frame is None:
            ax.text(0.5, 0.5, tex("this frame is not in the v5 product"), transform=ax.transAxes,
                    ha="center", va="center", fontsize=8.5, color=style.FAILURE)
            ax.set_yscale("log")
            ax.set_xscale("symlog", linthresh=LINTHRESH_BINS, linscale=LINSCALE)
            _axes(ax, limits)
            continue
        _panel(ax, ex, frame, limits=limits)
    _point_box(axes[0], ex)
    axes[-1].set_xlabel(r"padded fine bin offset from the measured anchor, $f-f_a$"
                        rf"\quad(one bin $={fmt(FINE_BIN_HZ, 2)}$ Hz; sense ${ex.sense:+d}$)")
    handles = [
        Line2D([], [], color=style.INK, lw=0.85, label=r"$T[f]$, all $L_F=256$ padded bins"),
        Line2D([], [], ls="none", marker="o", ms=4.0, mfc=style.MEASURED, mec="none",
               label=rf"designated set $\mathcal{{D}}$ ($f_a\pm{len(ex.designated_bins) // 2}$)"),
        Line2D([], [], ls="none", marker="o", ms=2.6, mfc=style.PENDING, mec="none",
               label=rf"usable bulk $\mathcal{{B}}$ ({ex.bulk_size} bins)"),
        Line2D([], [], color=style.MODEL, lw=1.0, ls="--", label="bulk median"),
        Line2D([], [], color=style.PENDING, lw=0.8, ls=":", label="bulk 90th percentile"),
        Patch(facecolor=style.LIGHT_BLUE, edgecolor="none", label="designated window"),
    ]
    if any(f is not None and math.isfinite(f.boundary) for f in present):
        star = r"^\star" if ex.point_basis == "selected" else r"^\dagger"
        handles.append(Line2D([], [], color=style.FAILURE, lw=1.2, ls="-.",
                              label=rf"boundary $\eta{star} T_{{(\rho{star})}}$"))
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, -0.045), ncol=3,
               handlelength=1.9, columnspacing=1.5, borderaxespad=0.0)
    fig.subplots_adjust(left=0.098, right=0.985, top=0.955, bottom=0.185)
    return fig


def _save(fig, stem: Path, title: str) -> list[Path]:
    stem.parent.mkdir(parents=True, exist_ok=True)
    png = stem.with_suffix(".png")
    fig.savefig(png, format="png", dpi=220)
    with style.stable_pdf_subset_tags():
        pdf = style.save(fig, stem.with_suffix(".pdf"), title=title)
    return [pdf, png]


def render(run: Run, out_dir: Path | str) -> list[Path]:
    """The figure, PDF and PNG, under ``out_dir``; the paths in order."""
    return _save(figure_worked_example(example(run)), Path(out_dir) / FIGURE, PDF_TITLE)


# ------------------------------------------------------------------ the table
def _math(text: str) -> str:
    return text if text == DASH else f"${text}$"


def _stack(panels: Sequence[tuple[str, str]]) -> str:
    r"""The panels one above the other in a single box (``calibration_nulls.stack``'s convention)."""
    lines = [r"\begin{tabular}{@{}l@{}}"]
    for i, (caption, body) in enumerate(panels):
        if i:
            lines.append(r"\\[\medskipamount]")
        lines.append(caption + r"\\[2pt]")
        lines.append(body.rstrip("\n"))
    lines.append(r"\end{tabular}")
    return "\n".join(lines) + "\n"


def _frame_panel(ex: Example, frag: Fragment) -> str:
    order = [which for which in (EXEMPLAR, COMPANION)]
    header = ["quantity"] + [tex(FRAME_LABEL[which]) for which in order]

    def add(key: str, which: str, value, *, kind: str = "float", precision: int | None = None,
            status: str = "measured", renderings: Sequence[str] = (), column: str = "") -> None:
        frag.add(f"{PREFIX}.{key}.{which}", value, kind=kind, precision=precision, status=status,
                 renderings=tuple(renderings), row={"frame": which, "quantity": key}, column=column or FRAME_LABEL[which])

    rows: list[list[str]] = []
    midrules: list[int] = []

    def line(label: str, cell) -> None:
        # labels are authored LaTeX (math is the chapter's own notation); only data cells are escaped
        rows.append([label] + [cell(which) for which in order])

    def frame(which: str) -> FrameRow | None:
        return ex.frames.get(which)

    def stamp(which: str) -> str:
        f = frame(which)
        if f is None:
            return DASH
        add("capture_time", which, _stamp(f.time), kind="text", renderings=(_stamp(f.time),))
        return tex(_stamp(f.time))

    def event(which: str) -> str:
        f = frame(which)
        if f is None:
            return DASH
        add("event_id", which, f.event_id, kind="int")
        return _math(fmt_int(f.event_id, thousands=False))

    def in_unit(which: str) -> str:
        f = frame(which)
        if f is None:
            return DASH
        add("frame_in_unit", which, f.frame_in_unit, kind="int")
        return _math(fmt_int(f.frame_in_unit))

    def coarse(which: str) -> str:
        f = frame(which)
        if f is None:
            return DASH
        add("coarse_statistic", which, f.statistic, precision=3)
        return _math(fmt(f.statistic, 3))

    def flag(which: str) -> str:
        f = frame(which)
        if f is None:
            return DASH
        text = "flagged" if f.rejected else "kept"
        add("survey_flag", which, text, kind="text", renderings=(text,))
        return tex(text)

    def shelf(which: str) -> str:
        f = frame(which)
        if f is None or not math.isfinite(f.shelf_db):
            if f is not None:
                add("shelf_db", which, None, status="refused")
            return DASH
        add("shelf_db", which, f.shelf_db, precision=2)
        return _math(fmt(f.shelf_db, 2))

    def designated(index: int):
        def cell(which: str) -> str:
            f = frame(which)
            if f is None:
                return DASH
            value = float(f.designated[index])
            add(f"T_bin{ex.designated_bins[index]}", which, value, precision=3)
            return _math(fmt(value, 3))
        return cell

    def scalar(key: str, attr: str, digits: int):
        def cell(which: str) -> str:
            f = frame(which)
            if f is None:
                return DASH
            value = float(getattr(f, attr))
            add(key, which, value, precision=digits)
            return _math(fmt(value, digits))
        return cell

    def integer(key: str, attr: str):
        def cell(which: str) -> str:
            f = frame(which)
            if f is None:
                return DASH
            value = int(getattr(f, attr))
            add(key, which, value, kind="int")
            return _math(fmt_int(value))
        return cell

    def boundary(which: str) -> str:
        f = frame(which)
        if f is None or not math.isfinite(f.boundary):
            add("operating_point_boundary", which, None, status="refused")
            return DASH
        add("operating_point_boundary", which, f.boundary, precision=3)
        return _math(fmt(f.boundary, 3))

    def masked(which: str) -> str:
        f = frame(which)
        if f is None or not math.isfinite(f.boundary):
            add("fine_decision", which, None, status="refused")
            return DASH
        text = "masked" if f.designated_max > f.boundary else "kept"
        add("fine_decision", which, text, kind="text", renderings=(text,))
        return tex(text)

    line("capture time", stamp)
    line("event id", event)
    line("frame in unit", in_unit)
    midrules.append(len(rows))
    line(r"coarse $F/\mu_0$", coarse)
    line("survey flag", flag)
    line("shelf estimate [dB]", shelf)
    midrules.append(len(rows))
    for index, b in enumerate(ex.designated_bins):
        line(rf"$T[{b}]$", designated(index))
    line(r"designated maximum $T_{\max}$", scalar("designated_max", "designated_max", 3))
    line(r"$2S_0[f_a]$", integer("target_terms", "target_terms"))
    line(r"$S_1[f_a]+S_2[f_a]$", integer("reference_terms", "reference_terms"))
    midrules.append(len(rows))
    line("bulk median", scalar("bulk_median", "bulk_median", 3))
    line("bulk 90th percentile", scalar("bulk_p90", "bulk_p90", 3))
    line(r"$T_{\max}$ / bulk median", scalar("ratio", "ratio", 2))
    midrules.append(len(rows))
    star = _star(ex)
    line(rf"boundary $\eta{star} T_{{(\rho{star})}}$", boundary)
    line("fine decision", masked)
    return booktabs(header, rows, "l" + "r" * len(order), midrules=midrules)


def _cohort_panel(ex: Example, frag: Fragment) -> str:
    header = ["quantity", "value"]
    rows: list[list[str]] = []

    def add(key: str, value, *, kind: str = "float", precision: int | None = None, status: str = "measured",
            renderings: Sequence[str] = ()) -> None:
        frag.add(f"{PREFIX}.{key}", value, kind=kind, precision=precision, status=status,
                 renderings=tuple(renderings), row={"quantity": key}, column="value")

    def text_row(label: str, key: str, value: str) -> None:
        rows.append([label, tex(value) if value else DASH])
        add(key, value or None, kind="text", renderings=(value,) if value else (),
            status="measured" if value else "pending")

    def int_row(label: str, key: str, value) -> None:
        finite = value is not None and math.isfinite(float(value))
        rows.append([label, _math(fmt_int(value)) if finite else DASH])
        if finite:
            add(key, int(value), kind="int")

    text_row("channel", "channel", f"{ex.channel} (freq_id {ex.freq_id})")   # the value is escaped, the label is not
    text_row("era", "era", ex.era_label)
    int_row("cohort frames (current era)", "cohort_frames", ex.cohort_frames)
    int_row("ledger's era frames", "ledger_era_frames", ex.ledger_frames)
    rows.append(["frame-health gate", r"\texttt{" + tex(ex.health_schema) + "}" if ex.health_schema else DASH])
    add("health_schema", ex.health_schema or None, kind="text",
        renderings=(ex.health_schema,) if ex.health_schema else (),
        status="measured" if ex.health_schema else "pending")
    int_row("measured anchor bin", "anchor_bin", ex.anchor_bin)
    designated = ", ".join(str(b) for b in ex.designated_bins)     # the five T rows above are keyed by these bins
    add("designated_bins", designated or None, kind="text", renderings=(designated,) if designated else (),
        status="measured" if designated else "pending")
    int_row(r"usable bulk $|\mathcal{B}|$", "bulk_size", ex.bulk_size)
    int_row("cohort frames the coarse rule keeps", "kept_frames", ex.kept_frames)
    weakest = _stamp(ex.weakest_time) if math.isfinite(ex.weakest_time) else ""
    text_row("weakest cohort frame", "weakest_frame_time", weakest)
    rows.append([r"its $F/\mu_0$", _math(fmt(ex.weakest_statistic, 3))
                 if math.isfinite(ex.weakest_statistic) else DASH])
    if math.isfinite(ex.weakest_statistic):
        add("weakest_statistic", ex.weakest_statistic, precision=3)
    companion = "yes" if ex.weakest_is_companion else "no"          # printed as a note when it is not
    add("weakest_is_companion", companion, kind="text", renderings=(companion,))
    text_row("selection status", "selection_status", ex.status)
    int_row("calibration-surface points evaluated", "surface_points", ex.surface_points)
    star = _star(ex)
    text_row("operating-point basis", "point_basis", ex.point_basis)
    if ex.has_point:
        rows.append([rf"rank $\rho{star}$", _math(fmt_int(ex.rho))])
        add("rho", int(ex.rho), kind="int")
        rows.append([rf"multiplier $\eta{star}$", _math(fmt(ex.eta, 4))])
        add("eta", ex.eta, precision=4)
    else:
        rows.append([rf"rank $\rho{star}$", DASH])
        add("rho", None, status="refused")
        rows.append([rf"multiplier $\eta{star}$", DASH])
        add("eta", None, status="refused")
    text_row("refusal", "refusal", ex.refusal)
    return booktabs(header, rows, "ll")


def _star(ex: Example) -> str:
    r"""The mark the chapter puts on the pair: a star for a selection, a dagger for a diagnostic."""
    return r"^\dagger" if ex.point_basis == "diagnostic" else r"^\star"


def _notes(ex: Example, frag: Fragment) -> None:
    for reason in ex.reasons:
        frag.notes.append(reason)
    if ex.has_point and ex.point_basis == "diagnostic":
        frag.notes.append(
            rf"the boundary drawn is $\eta^\dagger T_{{(\rho^\dagger)}}$ at the run's \emph{{diagnostic}} point "
            rf"($\rho^\dagger={fmt_int(ex.rho)}$, $\eta^\dagger={fmt(ex.eta, 4)}$): the least-residual point of the "
            "evaluated calibration surface, declared a diagnostic and not a selection. No channel of this run carries "
            "a selected point")
    if not ex.has_point:
        frag.notes.append(
            rf"no boundary is drawn and $\rho^\star$, $\eta^\star$ and $\eta^\star T_{{(\rho^\star)}}$ print the dash: "
            f"the selector {ex.status or 'returned no point'} on channel {ex.channel}"
            + (f" ({ex.refusal})" if ex.refusal else "")
            + (f", evaluating {fmt_int(ex.surface_points)} points of the calibration surface"
               if math.isfinite(ex.surface_points) else "")
            + ". The run leaves no selected and no diagnostic point on this channel, so the chapter's illustrative "
              "line has no measured replacement and the figure draws none")
    companion = ex.frames.get(COMPANION)
    if companion is not None and not math.isfinite(companion.shelf_db):
        frag.notes.append("the companion frame carries no shelf estimate (its normalized excess is not positive), "
                          "which is the condition the selector refused on: a frame with no shelf has no floor to be "
                          "booked at")
    if companion is not None and not ex.weakest_is_companion and math.isfinite(ex.weakest_statistic):
        frag.notes.append(
            f"the companion is the weakest frame of {COMPANION_DATE.isoformat()}, not of the cohort: on the v5 "
            f"products the cohort's weakest valid frame is {tex(_stamp(ex.weakest_time))} at "
            rf"$F/\mu_0={fmt(ex.weakest_statistic, 3)}$, against the companion's "
            rf"${fmt(companion.statistic, 3)}$. The chapter's sentence naming this frame the cohort's weakest "
            "belongs to the smaller cohort of the superseded products")
    if math.isfinite(ex.ledger_frames) and int(ex.ledger_frames) != ex.cohort_frames:
        frag.notes.append(f"the cohort reproduced here ({fmt_int(ex.cohort_frames)} frames) differs from the ledger's "
                          f"era count ({fmt_int(ex.ledger_frames)}): the months, the health gate or the time filter "
                          "moved between the run and this render")
    if ex.health_schema and ex.health_schema != "pilotproxy_archive_frame_health_gate_v1":
        frag.notes.append(f"the frame-health gate was {tex(ex.health_schema)}, not the campaign's v1 gate: "
                          "pilot-proxy was not importable and the cohort is valid-only")
    frag.notes.append(f"the figure's x axis is linear inside ${fmt(LINTHRESH_BINS, 0)}$ padded bins of the anchor "
                      "and logarithmic outside it (symmetric log), so the five designated bins and the whole "
                      "256-bin bulk are legible on one 6.35-in panel")
    frag.notes.append(r"$T[f]=2S_0[f]/(S_1[f]+S_2[f])$ is formed from the product's exact \texttt{fine\_power\_u64} "
                      "terms, the integers the frame was scored on; the two rows beneath the designated maximum are "
                      "that pair at the anchor bin")


def build(run: Run) -> Fragment:
    """The table behind the figure: the two frames, then the cohort and the verdict."""
    ex = example(run)
    frag = Fragment(NAME, LABEL, "")
    frag.inputs = list(run.inputs()) + ex.inputs
    frag.tex = _stack([
        (r"\emph{The two frames, from the v5 product.}", _frame_panel(ex, frag)),
        (r"\emph{The cohort they are drawn from, and the selector's verdict on the channel.}",
         _cohort_panel(ex, frag)),
    ])
    _notes(ex, frag)
    return frag
