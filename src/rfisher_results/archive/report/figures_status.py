"""``fig:conclusions:status`` and ``fig:calibration:containment`` from the ledger, with one compact
data table beside them.

``render(run, out_dir)`` draws both figures (PDF and PNG each) in the dissertation style
(:mod:`rfisher_results.style`; the caller applies ``style.configure()`` first,
``configure(require_tex=False)`` for a preview). ``build(run)`` is the report builder: a
:class:`core.Fragment` whose ``tex`` is a one-row-per-channel booktabs table of everything the two
figures draw, and whose numbers carry every value printed on either figure or in the table.

**fig:conclusions:status** (chapter 11; ``fig_conclusions_status``): one cell per channel 14--36 in
a 3 x 8 grid (the 24th cell is the key), coloured by the screening class, with the closing condition
as a short label and the survey flag rate as a small annotation; off-era cells add the month the
transmitter went off. The legend names the five classes with their counts; the footnote says how
many selections are diagnostic and how many refused, so the map is read as evidence classes, not
as selected operating points (no channel in this run has one).

  cell colour      screening.screening_class: recovery candidate (CONDITIONAL), measurement-bound on
                   floor (MODEL), measurement-bound on tau_c (GOLD), occupancy-wall excision
                   candidate (FAILURE), off-era (PENDING); a class outside these five, or a channel
                   without a screening record, is drawn unfilled with a dashed edge and named in the
                   legend
  closing label    screening.closing_condition, shortened by SHORT_CLOSING (an unknown string is
                   wrapped and escaped, never dropped)
  flag rate        screening.survey_flag_rate_era, two decimals
  off from         screening.off_from on off-era cells (screening.off_era_current)
  footnote         counts by selection outcome: selection.status == 'feasible' (a selected point),
                   selection.claim_status == 'diagnostic', selection.status == 'refused' (the refused
                   channels listed; selection.refusal in the notes), and channels without a record

**fig:calibration:containment** (chapter 8; ``fig_calibration_containment``): channels on the x
axis; the anchor and the in-span lobe of the averaged spectrum against the fine spans +-f_s/2K for
K = 64, 128, 256 drawn as nested shaded bands; a strip above with E_128 and E_256 per channel; the
K*-binding channel and the sentinel marked from ``tables/kstar.csv``; a dagger where the containment
window is aliased; a dashed connector where the fine anchor disagrees with the lobe.

  anchor           anchor.anchor_rf_offset_hz (filled circle) with the block-bootstrap bar
                   anchor.boot_rf_hz_q16 .. q84; on an off-era channel anchor.source ==
                   'previous_era' (the previous on era's anchor is the anchor of record) and the
                   marker is a filled diamond in PENDING
  previous anchor  anchor_previous.anchor_rf_offset_hz (open circle), omitted where it is the
                   anchor of record itself (off-era channels)
  in-span lobe     containment.in_span_refined_offset_hz (cross), only when
                   containment.in_span_recovered
  anchor suspect   containment.anchor_suspect with containment.anchor_lobe_offset_bins and
                   selection.anchor_source (the selector's anchor, the lobe bin on a suspect
                   channel): the anchor-to-lobe connector is dashed in FAILURE
  E strip          containment.e_128, containment.e_256, three decimals, in FAILURE when below
                   e_min (run.provisional.e_min, default DEFAULT_E_MIN)
  spans            f_s / 2K with f_s = 390625 Hz (archive.products.SAMPLE_RATE_HZ)
  marks            tables/kstar.csv row at e_min: k_star, failing_k, binding_channel ('binds K*'),
                   binding_e, sentinels ('sentinel'); containment.window_aliased_hz > 0 ('aliased',
                   the dagger)

**The table** (``tables/figures_status.tex``, one row per channel): ``ch``; ``screening class``;
``closing condition`` (the short form); ``flag rate``; ``anchor [Hz]``; ``prev. era [Hz]``;
``lobe [Hz]``; ``E_128``; ``E_256``; ``marks`` (anchor from previous era, anchor suspect with its
bin offset, binds K*, sentinel, aliased). An absent or undefined value draws nothing, prints the
dash, and is named in the fragment's notes: no screening record, an anchor whose offset is
undefined, no bootstrap quantiles, no previous era, no recovered lobe, an undefined E_K, no
kstar.csv row at e_min.

Numbers are keyed ``ch11.status_map.<column>.chNN`` and ``ch08.containment_map.<column>.chNN``;
band-level values drop the channel suffix (``ch08.containment_map.k_star``,
``ch11.status_map.count.<class>``).
"""
from __future__ import annotations

import csv
import math
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import matplotlib
matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle

from ... import style
from . import core
from .core import DASH, Fragment, Run, booktabs, fmt, tex

NAME = "figures_status"
LABELS = ("fig:conclusions:status", "fig:calibration:containment")
CHANNELS = tuple(range(14, 37))

SAMPLE_RATE_HZ = 390625.0                       # archive.products.SAMPLE_RATE_HZ (not imported: it needs pilot_proxy)
SPANS = (64, 128, 256)
DEFAULT_E_MIN = 0.9
E_DECIMALS = 3                                  # E_K printed to three decimals (the sentinel's 0.008 survives)
FOOTNOTE_WIDTH = 135                            # characters per footnote line at 5.6 pt across the text width

RECOVERY = "recovery candidate"
BOUND_FLOOR = "measurement-bound on floor"
BOUND_TAU = "measurement-bound on tau_c"
WALL = "occupancy-wall excision candidate"
OFF_ERA = "off-era"
CLASSES = (RECOVERY, BOUND_FLOOR, BOUND_TAU, WALL, OFF_ERA)
CLASS_COLOUR = {RECOVERY: style.CONDITIONAL, BOUND_FLOOR: style.MODEL, BOUND_TAU: style.GOLD,
                WALL: style.FAILURE, OFF_ERA: style.PENDING}
CLASS_TEX = {RECOVERY: "recovery candidate", BOUND_FLOOR: "measurement-bound on floor",
             BOUND_TAU: r"measurement-bound on $\tau_c$", WALL: "occupancy-wall excision candidate", OFF_ERA: "off-era"}
UNSCREENED = "no screening record"

SHORT_CLOSING = {
    "none: excision, with the pilot bin kept as a monitoring tap": "excision;\nmonitoring tap",
    "era transition: the next sign-on": "next sign-on",
    "measured floor from a verified off state": "measured floor\n(verified off)",
    "transfer gate: the online exact-replay agreement": "transfer gate\n(exact replay)",
    "measured correlation time": "measured $\\tau_c$",
    "none: no admissible operating point": "no admissible\npoint",
}


def span_half_width_hz(k: int) -> float:
    """``f_s / 2K``: the unambiguous half-span of a K-tap window."""
    return SAMPLE_RATE_HZ / (2.0 * k)


def short_closing(condition: str) -> str:
    """The cell label for a closing condition: the table's short form, or the string wrapped and escaped."""
    if not condition:
        return DASH
    if condition in SHORT_CLOSING:
        return SHORT_CLOSING[condition]
    return "\n".join(tex(line) for line in textwrap.wrap(condition, 16)[:3])


def _finite(value) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _slug(text: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in text).strip("_")


def _f(value) -> float:
    return float(value) if _finite(value) else math.nan


# ------------------------------------------------------------------ the data
@dataclass(frozen=True)
class ChannelStatus:
    """What the two figures draw for one channel (NaN / '' where the ledger has nothing)."""

    channel: int
    screened: bool
    screening_class: str
    closing_condition: str
    survey_flag_rate: float
    off_era: bool
    off_from: str
    claim_status: str
    selection_status: str
    refusal: str
    anchored: bool
    anchor_rf_offset_hz: float
    anchor_source: str
    boot_q16: float
    boot_q84: float
    previous_present: bool
    previous_rf_offset_hz: float
    lobe_recovered: bool
    lobe_rf_offset_hz: float
    anchor_suspect: bool
    anchor_lobe_offset_bins: float
    selector_anchor_source: str
    e_128: float
    e_256: float
    window_aliased_hz: float

    @property
    def anchor_from_previous_era(self) -> bool:
        return self.anchor_source == "previous_era"

    @property
    def aliased(self) -> bool:
        return _finite(self.window_aliased_hz) and self.window_aliased_hz > 0.0

    @property
    def has_boot(self) -> bool:
        return _finite(self.boot_q16) and _finite(self.boot_q84)

    @property
    def selected(self) -> bool:
        """The selector selected a point (``selection.status == 'feasible'``)."""
        return self.selection_status == "feasible"

    @property
    def diagnostic(self) -> bool:
        return self.claim_status == "diagnostic"

    @property
    def refused(self) -> bool:
        return self.selection_status == "refused"


@dataclass(frozen=True)
class KStarMarks:
    """The ``tables/kstar.csv`` row the figure marks from."""

    path: Path
    e_min: float
    k_star: int | None
    failing_k: int | None
    binding_channel: int | None
    binding_e: float
    sentinels: tuple[int, ...]


def channel_status(c: core.Channel) -> ChannelStatus:
    scr, an, ct, prev, sel = c.screening, c.anchor, c.containment, c.section("anchor_previous"), c.selection
    off = bool(scr.get("off_era_current", False)) if c.has("screening") else str(an.get("source", "")) == "previous_era"
    return ChannelStatus(
        channel=c.channel, screened=c.has("screening"),
        screening_class=str(scr.get("screening_class", "") or ""), closing_condition=str(scr.get("closing_condition", "") or ""),
        survey_flag_rate=_f(scr.get("survey_flag_rate_era")), off_era=off, off_from=str(scr.get("off_from", "") or ""),
        claim_status=str(sel.get("claim_status", "") or ""), selection_status=str(sel.get("status", "") or ""),
        refusal=str(sel.get("refusal", "") or ""),
        anchored=c.has("anchor") and _finite(an.get("anchor_rf_offset_hz")),
        anchor_rf_offset_hz=_f(an.get("anchor_rf_offset_hz")), anchor_source=str(an.get("source", "") or ""),
        boot_q16=_f(an.get("boot_rf_hz_q16")), boot_q84=_f(an.get("boot_rf_hz_q84")),
        previous_present=c.has("anchor_previous") and _finite(prev.get("anchor_rf_offset_hz")),
        previous_rf_offset_hz=_f(prev.get("anchor_rf_offset_hz")),
        lobe_recovered=bool(ct.get("in_span_recovered", False)) and _finite(ct.get("in_span_refined_offset_hz")),
        lobe_rf_offset_hz=_f(ct.get("in_span_refined_offset_hz")),
        anchor_suspect=bool(ct.get("anchor_suspect", False)), anchor_lobe_offset_bins=_f(ct.get("anchor_lobe_offset_bins")),
        selector_anchor_source=str(sel.get("anchor_source", "") or ""),
        e_128=_f(ct.get("e_128")), e_256=_f(ct.get("e_256")), window_aliased_hz=_f(ct.get("window_aliased_hz")))


def run_e_min(run: Run) -> float:
    prov = run.run.get("provisional", {})
    e_min = prov.get("e_min") if isinstance(prov, dict) else None
    return float(e_min) if _finite(e_min) else DEFAULT_E_MIN


def kstar_marks(run: Run, e_min: float) -> KStarMarks | None:
    """The kstar.csv row at ``e_min``, or None when the table (or the row) is absent."""
    path = run.results_dir / "tables" / "kstar.csv"
    if not path.is_file():
        return None
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if not _finite(row.get("e_min")) or abs(float(row["e_min"]) - e_min) > 1e-9:
                continue

            def _int(text):
                return int(float(text)) if text not in (None, "") and _finite(text) else None

            sentinels = tuple(int(s) for s in str(row.get("sentinels", "")).split(";") if s.strip())
            return KStarMarks(path, e_min, _int(row.get("k_star")), _int(row.get("failing_k")), _int(row.get("binding_channel")),
                              _f(row.get("binding_e")), sentinels)
    return None


def statuses(run: Run) -> list[ChannelStatus]:
    return [channel_status(c) for c in run.channels]


def class_counts(rows: Sequence[ChannelStatus]) -> dict[str, int]:
    """Counts by class: the five known classes first (always present), then any other class, then the unscreened."""
    counts = {cls: 0 for cls in CLASSES}
    for r in rows:
        key = r.screening_class if r.screened and r.screening_class else UNSCREENED
        counts[key] = counts.get(key, 0) + 1
    if UNSCREENED in counts:                      # keep the unscreened last
        counts[UNSCREENED] = counts.pop(UNSCREENED)
    return counts


def selection_summary(rows: Sequence[ChannelStatus]) -> dict[str, list[int]]:
    """Channels by selection outcome: selected (a feasible point), diagnostic, refused, and without a selection record."""
    return {"selected": [r.channel for r in rows if r.selected], "diagnostic": [r.channel for r in rows if r.diagnostic],
            "refused": [r.channel for r in rows if r.refused],
            "unrecorded": [r.channel for r in rows if not (r.selected or r.diagnostic or r.refused)]}


def _list(chs) -> str:
    return ", ".join(str(c) for c in chs)


def footnote(rows: Sequence[ChannelStatus]) -> str:
    """The status map's footnote: how many selections are diagnostic, how many refused, so the map is not read as selections."""
    n = len(rows)
    s = selection_summary(rows)
    lead = ("No channel has a selected operating point: " if not s["selected"]
            else f"{len(s['selected'])} of {n} channels have a selected operating point; ")
    parts = [f"{len(s['diagnostic'])} of {n} selections are diagnostic (the drift screen refused)"]
    if s["refused"]:
        parts.append(f"{len(s['refused'])} refused on the calibration surface (ch {_list(s['refused'])})")
    if s["unrecorded"]:
        parts.append(f"{len(s['unrecorded'])} without a selection record")
    text = lead + ", ".join(parts[:-1]) + (" and " if len(parts) > 1 else "") + parts[-1]
    text += "; the classes rest on occupancy, floor and correlation-time evidence, not on a feasible point."
    return "\n".join(textwrap.wrap(text, FOOTNOTE_WIDTH))


# ------------------------------------------------------------------ figure 1
def _cell(ax, x0: float, y0: float, r: ChannelStatus) -> None:
    w, h = 1.0, 1.0
    colour = CLASS_COLOUR.get(r.screening_class) if r.screened else None
    if colour is None:
        ax.add_patch(Rectangle((x0, y0), w, h, facecolor=style.PANEL, edgecolor=style.MUTED, lw=0.8, ls=(0, (2, 1.5))))
    else:
        ax.add_patch(Rectangle((x0, y0), w, h, facecolor=colour, alpha=0.16, edgecolor="none"))
        ax.add_patch(Rectangle((x0, y0), w, h, facecolor="none", edgecolor=colour, lw=0.9))
        ax.add_patch(Rectangle((x0, y0 + h - 0.11), w, 0.11, facecolor=colour, edgecolor="none"))
    ax.text(x0 + 0.06, y0 + h - 0.17, f"ch {r.channel}", ha="left", va="top", fontsize=7.0, fontweight="bold", color=style.INK)
    flag = fmt(r.survey_flag_rate, 2) if r.screened else DASH
    ax.text(x0 + w - 0.06, y0 + h - 0.18, f"flag {flag}", ha="right", va="top", fontsize=5.4, color=style.MUTED)
    label = short_closing(r.closing_condition) if r.screened else UNSCREENED.replace(" record", "\nrecord")
    ax.text(x0 + w / 2, y0 + 0.40, label, ha="center", va="center", fontsize=5.9, color=style.INK, linespacing=1.1)
    if r.screened and r.off_era:
        ax.text(x0 + w / 2, y0 + 0.09, f"off from {r.off_from}" if r.off_from else "off era", ha="center", va="bottom",
                fontsize=5.2, color=style.MUTED)


def _key_cell(ax, x0: float, y0: float) -> None:
    ax.add_patch(Rectangle((x0, y0), 1.0, 1.0, facecolor="none", edgecolor=style.GRID, lw=0.8))
    ax.text(x0 + 0.5, y0 + 0.5, "colour: class\ntop right: survey\nflag rate (era)\ntext: closing\ncondition",
            ha="center", va="center", fontsize=5.0, color=style.MUTED, linespacing=1.15)


def figure_status_map(rows: Sequence[ChannelStatus], *, ncol: int = 8, nrow: int = 3):
    fig = plt.figure(figsize=(style.TEXT_WIDTH, 3.0))
    ax = fig.add_axes([0.015, 0.29, 0.97, 0.70])
    ax.set_axis_off()
    ax.set_xlim(-0.02, ncol + 0.02)
    ax.set_ylim(-0.02, nrow + 0.02)
    for i, r in enumerate(rows):
        row, col = divmod(i, ncol)
        _cell(ax, col, nrow - 1 - row, r)
    n = len(rows)
    if n < ncol * nrow:
        row, col = divmod(n, ncol)
        _key_cell(ax, col, nrow - 1 - row)
    counts = class_counts(rows)
    handles = [Patch(facecolor=CLASS_COLOUR[cls], alpha=0.55, edgecolor=CLASS_COLOUR[cls], label=f"{CLASS_TEX[cls]} ({counts[cls]})")
               for cls in CLASSES]
    for cls, count in counts.items():
        if cls not in CLASS_COLOUR:              # an unknown class, or the unscreened: the dashed cell
            handles.append(Patch(facecolor=style.PANEL, edgecolor=style.MUTED, ls=(0, (2, 1.5)), label=f"{tex(cls)} ({count})"))
    fig.legend(handles=handles, loc="lower center", ncol=3, bbox_to_anchor=(0.5, 0.115), fontsize=6.6,
               handlelength=1.4, handleheight=0.9, columnspacing=1.4, borderaxespad=0.0)
    fig.text(0.5, 0.012, footnote(rows), ha="center", va="bottom", fontsize=5.6, color=style.MUTED, linespacing=1.25)
    return fig


# ------------------------------------------------------------------ figure 2
BAND_TINT = {64: (style.LIGHT_GRAY, 1.0), 128: (style.LIGHT_BLUE, 1.0), 256: (style.MEASURED, 0.16)}


def figure_containment(rows: Sequence[ChannelStatus], *, e_min: float, marks: KStarMarks | None):
    n = len(rows)
    fig = plt.figure(figsize=(style.TEXT_WIDTH, 3.95))
    gs = fig.add_gridspec(2, 1, height_ratios=[0.19, 1.0], left=0.095, right=0.985, bottom=0.235, top=0.935, hspace=0.06)
    top = fig.add_subplot(gs[0])
    ax = fig.add_subplot(gs[1], sharex=top)
    x = list(range(n))
    ymax = span_half_width_hz(SPANS[0]) * 1.10

    # the spans, nested
    for k in SPANS:
        half = span_half_width_hz(k)
        colour, alpha = BAND_TINT[k]
        ax.axhspan(-half, half, facecolor=colour, alpha=alpha, edgecolor="none", zorder=0)
        ax.axhline(half, color=style.MUTED, lw=0.4, zorder=1)
        ax.axhline(-half, color=style.MUTED, lw=0.4, zorder=1)
        ax.text(-0.42, half * 0.97, rf"$K={k}$: $\pm{half:.0f}$ Hz", ha="left", va="top", fontsize=5.8, color=style.MUTED, zorder=3)
    ax.axhline(0.0, color=style.MUTED, lw=0.5, zorder=1)

    # the K* marks
    binding = marks.binding_channel if marks else None
    sentinels = marks.sentinels if marks else ()
    for i, r in enumerate(rows):
        if binding is not None and r.channel == binding:
            ax.axvspan(i - 0.5, i + 0.5, facecolor=style.FAILURE, alpha=0.10, edgecolor="none", zorder=0)
            ax.text(i, -ymax * 0.97, r"binds $K^\star$", rotation=90, ha="center", va="bottom", fontsize=5.8, color=style.FAILURE, zorder=3)
        if r.channel in sentinels:
            ax.axvspan(i - 0.5, i + 0.5, facecolor=style.PENDING, alpha=0.22, edgecolor="none", zorder=0)
            ax.text(i, -ymax * 0.97, "sentinel", rotation=90, ha="center", va="bottom", fontsize=5.8, color=style.INK, zorder=3)

    # the points
    for i, r in enumerate(rows):
        if r.anchored and r.lobe_recovered:
            if r.anchor_suspect:
                ax.plot([i, i], [r.anchor_rf_offset_hz, r.lobe_rf_offset_hz], color=style.FAILURE, lw=0.9, ls=(0, (2, 1.2)), zorder=2)
            else:
                ax.plot([i, i], [r.anchor_rf_offset_hz, r.lobe_rf_offset_hz], color=style.MUTED, lw=0.5, zorder=2)
        if r.previous_present and not r.anchor_from_previous_era:
            ax.plot(i, r.previous_rf_offset_hz, marker="o", mfc="none", mec=style.MUTED, mew=0.8, ms=4.6, ls="none", zorder=3)
        if r.lobe_recovered:
            ax.plot(i, r.lobe_rf_offset_hz, marker="x", color=style.MODEL, ms=4.6, mew=1.0, ls="none", zorder=4)
        if r.anchored:
            if r.has_boot:
                lo, hi = max(r.anchor_rf_offset_hz - r.boot_q16, 0.0), max(r.boot_q84 - r.anchor_rf_offset_hz, 0.0)
                ax.errorbar(i, r.anchor_rf_offset_hz, yerr=[[lo], [hi]], fmt="none", ecolor=style.MEASURED, elinewidth=0.8, capsize=1.6, zorder=4)
            if r.anchor_from_previous_era:
                ax.plot(i, r.anchor_rf_offset_hz, marker="D", color=style.PENDING, ms=4.4, ls="none", zorder=5)
            else:
                ax.plot(i, r.anchor_rf_offset_hz, marker="o", color=style.MEASURED, ms=4.4, ls="none", zorder=5)
        if r.aliased:
            ax.text(i, ymax * 0.97, r"$\dagger$", ha="center", va="top", fontsize=7.0, color=style.MUTED, zorder=3)

    ax.set_xlim(-0.5, n - 0.5)
    ax.set_ylim(-ymax, ymax)
    ax.set_xticks(x)
    ax.set_xticklabels([str(r.channel) for r in rows])
    ax.set_xlabel("ATSC channel")
    ax.set_ylabel("RF offset from synthesis [Hz]")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(labelsize=7.0)

    # the E strip
    top.set_xlim(-0.5, n - 0.5)
    top.set_ylim(-0.5, 1.5)
    top.set_yticks([1, 0])
    top.set_yticklabels([r"$E_{128}$", r"$E_{256}$"], fontsize=6.6)
    top.tick_params(axis="x", which="both", bottom=False, labelbottom=False)
    top.tick_params(axis="y", length=0)
    for s in ("top", "right", "bottom", "left"):
        top.spines[s].set_visible(False)
    for i, r in enumerate(rows):
        for yy, value in ((1, r.e_128), (0, r.e_256)):
            fail = _finite(value) and value < e_min
            if fail:
                top.add_patch(Rectangle((i - 0.5, yy - 0.5), 1.0, 1.0, facecolor=style.FAILURE, alpha=0.12, edgecolor="none"))
            top.text(i, yy, fmt(value, E_DECIMALS), ha="center", va="center", fontsize=5.3, color=style.FAILURE if fail else style.INK)
    if marks and marks.k_star is not None:
        bind = f"; ch {marks.binding_channel} binds" if marks.binding_channel is not None else ""
        sent = f"; sentinel ch {', '.join(str(s) for s in marks.sentinels)}" if marks.sentinels else ""
        title = rf"$K^\star = {marks.k_star}$ at $E_{{\min}} = {marks.e_min:g}${bind}{sent}"
    else:
        title = rf"$E_{{\min}} = {e_min:g}$; no $K^\star$ table in this run"
    top.set_title(title, fontsize=7.4, pad=2.0)

    handles = [
        Line2D([0], [0], marker="o", color=style.MEASURED, ls="none", ms=4.4, label="anchor (current era) with q16--q84 bootstrap bar"),
        Line2D([0], [0], marker="D", color=style.PENDING, ls="none", ms=4.4, label="anchor read from the previous era (off-era channel)"),
        Line2D([0], [0], marker="o", mfc="none", mec=style.MUTED, ls="none", ms=4.6, label="previous-era anchor"),
        Line2D([0], [0], marker="x", color=style.MODEL, ls="none", ms=4.6, mew=1.0, label="in-span lobe of the averaged spectrum"),
    ]
    if any(r.anchor_suspect for r in rows):
        handles.append(Line2D([0], [0], color=style.FAILURE, lw=0.9, ls=(0, (2, 1.2)),
                              label="fine anchor disagrees with the lobe (suspect; selector uses the lobe)"))
    if any(r.aliased for r in rows):
        handles.append(Line2D([0], [0], marker=r"$\dagger$", color=style.MUTED, ls="none", ms=6.0,
                              label="containment window aliased at the coarse-channel edge"))
    fig.legend(handles=handles, loc="lower center", ncol=2, bbox_to_anchor=(0.5, 0.0), fontsize=6.1, handlelength=1.6,
               columnspacing=1.2, borderaxespad=0.0)
    return fig


# ------------------------------------------------------------------ render / build
def _save(fig, stem: Path, title: str) -> list[Path]:
    stem.parent.mkdir(parents=True, exist_ok=True)
    png = stem.with_suffix(".png")
    fig.savefig(png, format="png", dpi=220)
    with style.stable_pdf_subset_tags():
        pdf = style.save(fig, stem.with_suffix(".pdf"), title=title)
    return [pdf, png]


def render(run: Run, out_dir: Path | str) -> list[Path]:
    """Both figures, PDF and PNG each, under ``out_dir``; the paths in order."""
    out = Path(out_dir)
    rows = statuses(run)
    e_min = run_e_min(run)
    marks = kstar_marks(run, e_min)
    paths = _save(figure_status_map(rows), out / "fig_conclusions_status",
                  f"Evidence map for the {len(rows)} ATSC allocations on their current eras")
    paths += _save(figure_containment(rows, e_min=e_min, marks=marks), out / "fig_calibration_containment",
                   "Anchor containment against the fine spans, all channels")
    return paths


def _marks_text(r: ChannelStatus, marks: KStarMarks | None) -> str:
    out = []
    if r.anchor_from_previous_era:
        out.append("anchor from previous era")
    if r.anchor_suspect:
        bins = fmt(r.anchor_lobe_offset_bins, 1, plus=True)
        out.append(f"anchor suspect (${bins}$ bins)" if bins != DASH else "anchor suspect")
    if marks and marks.binding_channel == r.channel:
        out.append(r"binds $K^\star$")
    if marks and r.channel in marks.sentinels:
        out.append("sentinel")
    if r.aliased:
        out.append("aliased")
    return "; ".join(out) if out else DASH


def _math(text: str) -> str:
    return text if text == DASH else f"${text}$"


def build(run: Run) -> Fragment:
    """The compact data table behind both figures, with every printed value keyed."""
    rows = statuses(run)
    e_min = run_e_min(run)
    marks = kstar_marks(run, e_min)
    frag = Fragment(NAME, ";".join(LABELS), "")
    frag.inputs = list(run.inputs()) + ([marks.path] if marks else [])
    header = ["ch", "screening class", "closing condition", "flag rate", "anchor [Hz]", "prev.\\ era [Hz]", "lobe [Hz]",
              "$E_{128}$", "$E_{256}$", "marks"]
    body = []
    unscreened, no_anchor, no_boot, no_lobe, no_e, prev_era, suspect, aliased = [], [], [], [], [], [], [], []
    for r in rows:
        ch = r.channel
        row = {"channel": ch}
        pfx_s, pfx_c = "ch11.status_map", "ch08.containment_map"
        if r.screened:
            cls = CLASS_TEX.get(r.screening_class, tex(r.screening_class))
            short = short_closing(r.closing_condition).replace("\n", " ")
            frag.add(f"{pfx_s}.screening_class.{ch}", r.screening_class, kind="text", renderings=(r.screening_class,), row=row, column="class")
            frag.add(f"{pfx_s}.closing_condition.{ch}", r.closing_condition, kind="text",
                     renderings=(r.closing_condition, short.replace("$\\tau_c$", "tau_c")), row=row, column="closing")
            frag.add(f"{pfx_s}.survey_flag_rate_era.{ch}", r.survey_flag_rate, precision=2, row=row, column="flag rate",
                     status="measured" if _finite(r.survey_flag_rate) else "pending")
            if r.off_era:
                frag.add(f"{pfx_s}.off_from.{ch}", r.off_from or None, kind="text", renderings=(r.off_from,) if r.off_from else (),
                         row=row, column="off from", status="measured" if r.off_from else "pending")
        else:
            cls, short = tex(UNSCREENED), DASH
            unscreened.append(ch)
        flag = fmt(r.survey_flag_rate, 2) if r.screened else DASH

        if r.anchored:
            frag.add(f"{pfx_c}.anchor_rf_offset_hz.{ch}", r.anchor_rf_offset_hz, precision=1, row=row, column="anchor")
            frag.add(f"{pfx_c}.anchor_source.{ch}", r.anchor_source or None, kind="text", renderings=(r.anchor_source,) if r.anchor_source else (),
                     row=row, column="marks", status="measured" if r.anchor_source else "pending")
            if r.anchor_from_previous_era:
                prev_era.append(ch)
            if r.has_boot:
                frag.add(f"{pfx_c}.boot_rf_hz_q16.{ch}", r.boot_q16, precision=1, row=row, column="anchor")
                frag.add(f"{pfx_c}.boot_rf_hz_q84.{ch}", r.boot_q84, precision=1, row=row, column="anchor")
            else:
                no_boot.append(ch)
        else:
            no_anchor.append(ch)
        if r.previous_present:
            frag.add(f"{pfx_c}.anchor_previous_rf_offset_hz.{ch}", r.previous_rf_offset_hz, precision=1, row=row, column="prev. era")
        if r.lobe_recovered:
            frag.add(f"{pfx_c}.in_span_refined_offset_hz.{ch}", r.lobe_rf_offset_hz, precision=1, row=row, column="lobe")
        else:
            no_lobe.append(ch)
        if r.anchor_suspect:
            suspect.append(ch)
            frag.add(f"{pfx_c}.anchor_suspect.{ch}", r.selector_anchor_source or "suspect", kind="text",
                     renderings=("anchor suspect",), row=row, column="marks")
            if _finite(r.anchor_lobe_offset_bins):
                frag.add(f"{pfx_c}.anchor_lobe_offset_bins.{ch}", r.anchor_lobe_offset_bins, precision=1, row=row, column="marks")
        for name, value in (("e_128", r.e_128), ("e_256", r.e_256)):
            if _finite(value):
                frag.add(f"{pfx_c}.{name}.{ch}", value, precision=E_DECIMALS, row=row, column=name.replace("e_", "E_"))
            else:
                no_e.append(f"{ch}:{name}")
        if r.aliased:
            aliased.append(ch)
            frag.add(f"{pfx_c}.window_aliased_hz.{ch}", r.window_aliased_hz, precision=1, row=row, column="marks",
                     renderings=("aliased",))
        body.append([str(ch), cls, short, _math(flag), _math(fmt(r.anchor_rf_offset_hz, 1) if r.anchored else DASH),
                     _math(fmt(r.previous_rf_offset_hz, 1) if r.previous_present else DASH),
                     _math(fmt(r.lobe_rf_offset_hz, 1) if r.lobe_recovered else DASH),
                     _math(fmt(r.e_128, E_DECIMALS)), _math(fmt(r.e_256, E_DECIMALS)), _marks_text(r, marks)])
    frag.tex = booktabs(header, body, "lllrrrrrrl")

    counts = class_counts(rows)
    for cls, count in counts.items():
        frag.add(f"ch11.status_map.count.{_slug(cls)}", count, kind="int", status="derived", column="legend")
    summary = selection_summary(rows)
    frag.add("ch11.status_map.channels", len(rows), kind="int", status="derived", column="footnote")
    for outcome in ("selected", "diagnostic", "refused"):
        frag.add(f"ch11.status_map.count.{outcome}", len(summary[outcome]), kind="int", status="derived", column="footnote")
    for k in SPANS:
        frag.add(f"ch08.containment_map.span_half_width_hz.k{k}", span_half_width_hz(k), precision=1, status="derived", column="spans")
    frag.add("ch08.containment_map.e_min", e_min, precision=2, status="derived", column="E strip")
    if marks:
        frag.add("ch08.containment_map.k_star", marks.k_star, kind="int", status="derived" if marks.k_star is not None else "pending",
                 column="title")
        frag.add("ch08.containment_map.failing_k", marks.failing_k, kind="int", status="derived" if marks.failing_k is not None else "pending",
                 column="marks")
        frag.add("ch08.containment_map.binding_channel", marks.binding_channel, kind="int",
                 status="derived" if marks.binding_channel is not None else "pending", column="marks")
        frag.add("ch08.containment_map.binding_e", marks.binding_e, precision=3, status="measured" if _finite(marks.binding_e) else "pending",
                 column="marks")
        frag.add("ch08.containment_map.sentinels", ";".join(str(s) for s in marks.sentinels) or None, kind="text",
                 renderings=tuple(str(s) for s in marks.sentinels), status="derived" if marks.sentinels else "pending", column="marks")

    # the notes: what is not drawn and why
    frag.notes.append(f"labels {LABELS[0]} (cells) and {LABELS[1]} (points): one fragment, two figures; the table carries both")
    frag.notes.append("; ".join(f"{count} {cls}" for cls, count in counts.items())
                      + ("; the unscreened draw a dashed cell and print dashes" if counts.get(UNSCREENED) else ""))
    frag.notes.append(footnote(rows).replace("\n", " ") + " The map prints no rho/eta.")
    for ch in summary["refused"]:
        r = next(r for r in rows if r.channel == ch)
        frag.notes.append(f"ch{ch}: selection refused: {r.refusal or 'no reason recorded'}")
    if summary["unrecorded"]:
        frag.notes.append(f"channels {_list(summary['unrecorded'])}: no selection record (neither selected, diagnostic nor refused)")
    frag.notes.append("flag rate is screening.survey_flag_rate_era to two decimals; off-era cells add screening.off_from")
    if prev_era:
        frag.notes.append(f"channels {_list(prev_era)}: anchor and lobe read from the previous era (anchor.source = 'previous_era'); "
                          "drawn as a filled diamond, the open previous-era marker omitted where it coincides")
    if suspect:
        frag.notes.append(f"channels {_list(suspect)}: containment.anchor_suspect (fine anchor disagrees with the in-span lobe by "
                          "anchor_lobe_offset_bins); the anchor-to-lobe connector is dashed and the selector's anchor is the lobe bin "
                          "(selection.anchor_source)")
    if no_anchor:
        frag.notes.append(f"channels {_list(no_anchor)}: no anchor (section absent or offset undefined): no marker, dash")
    if no_boot:
        frag.notes.append(f"channels {_list(no_boot)}: no bootstrap quantiles (anchor.boot_rf_hz_q16/q84 absent): no error bar")
    if no_lobe:
        frag.notes.append(f"channels {_list(no_lobe)}: no in-span lobe (containment.in_span_recovered false or section absent): no cross, dash")
    if no_e:
        frag.notes.append(f"E undefined (dash): {_list(no_e)}")
    frag.notes.append("previous-era anchor column is the dash where anchor_previous is absent (a single-era channel)")
    if marks:
        frag.notes.append(f"K* marks from {marks.path.name} at e_min = {marks.e_min:g}: K* = {marks.k_star}, binding channel "
                          f"{marks.binding_channel} (E_{marks.failing_k} = {fmt(marks.binding_e, 3)}), sentinels {_list(marks.sentinels) or 'none'}")
    else:
        frag.notes.append(f"tables/kstar.csv absent or lacks an e_min = {e_min:g} row: no binding-channel or sentinel marks, no K* in the title")
    if aliased:
        frag.notes.append(f"channels {_list(aliased)}: containment.window_aliased_hz > 0 (window wraps the coarse-channel edge), the dagger")
    frag.notes.append(f"spans are f_s/2K at f_s = {SAMPLE_RATE_HZ:g} Hz: " + ", ".join(f"K={k} +-{span_half_width_hz(k):.1f} Hz" for k in SPANS))
    return frag
