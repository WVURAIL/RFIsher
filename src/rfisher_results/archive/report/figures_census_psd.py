"""``fig:census:psd`` from the per-channel window spectra: all 23 channels on one canvas.

``render(run, out_dir)`` draws the figure (PDF and PNG) in the dissertation style
(:mod:`rfisher_results.style`; the caller applies ``style.configure()`` first,
``configure(require_tex=False)`` for a preview). ``build(run)`` is the report builder: a
:class:`core.Fragment` whose ``tex`` is a one-row-per-channel booktabs table of everything the
figure draws, and whose numbers carry every value printed on a panel or in the table.

**fig:census:psd** (chapter 3; ``fig_census_psd_all23``): one panel per channel 14--36 in
physical-channel order, 6 rows x 4 columns, the 24th cell the reading note; the shared legend runs
across the foot. Each panel is the *era-mean* spectrum of the channel's coarse channel within the
census window ``|offset| <= 15 kHz``, in dB over the window median, against RF offset from the
*nominal* (synthesized) pilot, so a carrier's displacement from zero is its measured off-nominal
offset. This replaces the two superseded archive-average plates (``fig:census:psd`` for channels
27--36 and ``fig:census:psd:lower`` for 14--26) with one current-era figure.

  source          ``channels/chNN/spectra_window.json`` (``rfisher_results.archive.psd`` window
                  spectra v1): ``rf_offset_hz``, ``mean_db``, ``baseline_db``, the ``dominant``,
                  ``near`` and ``in_span`` lobes, ``centre_line_rf_offset_hz``, ``frames``,
                  ``detected_frames``, ``disposition`` and the file's ``provenance`` string
  era             the ``provenance`` string names the era the mean was taken over and whether it is
                  the channel's current era or the previous *on* era (channels whose current era is
                  off: the mean of an off era measures nothing). Each panel says which. An
                  unparsable or absent provenance falls back to the ledger's ``era`` section and the
                  fragment notes say so
  spectrum        ``mean_db`` (INK) over ``baseline_db``, the sliding-median baseline (PENDING,
                  dashed): a feature is a feature by its excess over that baseline
  spans           the ``K = 128`` capture span ``+-f_s/2K = +-1525.9`` Hz shaded, with the
                  ``K = 256`` span ``+-762.9`` Hz nested inside it, so a lobe's skirt past the
                  narrower span is read off the shading (channel 23)
  references      the ``K = 128`` reference placements ``+-2 f_s/K = +-6103.5`` Hz, dashed
  in-span lobe    ``in_span.refined_offset_hz`` at ``in_span.db``, a filled dot on a stem
                  (MEASURED); absent where no in-span feature stands over the baseline
  dominant lobe   ``dominant.refined_offset_hz`` at ``dominant.db``, an open ring (MODEL). Where it
                  is the in-span lobe (22 of the 23 channels) the ring nests around the dot; where
                  it is not, the ring stands alone and the panel prints its offset in kHz
                  (channel 33: a co-channel carrier at ``-3.7`` kHz, outside the capture span)
  centre line     ``centre_line_rf_offset_hz`` where it falls inside the window (channels 14 and
                  28): the coarse channel's own centre bin, the detector's forbidden tone, dotted
                  in PENDING. It is instrumental, not a member of the transmitter population
  x axis          linear inside the capture span, logarithmic outside (symmetric log, ``linthresh``
                  the span half-width): a lobe hundreds of hertz off nominal and a carrier
                  kilohertz away are both legible on one 1.2-in panel. The axis is monotone; only the
                  window edge and zero are labelled (a reference tick would collide with the edge's
                  label), and the span and reference ticks are minor and named in the legend
  y axis          per panel, dB over that channel's window median: the panel peaks span 5.9 to
                  42.3 dB across the band, and one shared scale would flatten the quiet channels

**The table** (``tables/figures_census_psd.tex``, one row per channel): ``ch``; ``era`` (which era
and its months); ``frames``; ``disposition``; ``lobe [Hz]`` and ``lobe [dB]`` (the in-span lobe);
``dominant [Hz]`` and ``dominant [dB]``; ``marks`` (dominant out of span, centre line in the
window, no in-span lobe, no spectrum file, era from the ledger). An absent or undefined value draws
nothing, prints the dash, and is named in the fragment's notes.

Numbers are keyed ``ch03.census_psd.<name>.chNN``; band-level values drop the channel suffix
(``ch03.census_psd.span_half_width_hz``, ``ch03.census_psd.count.<name>``).
"""
from __future__ import annotations

import json
import math
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import matplotlib
matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import MaxNLocator

from ... import style
from . import core
from .core import DASH, Fragment, Run, booktabs, fmt, fmt_int, tex

NAME = "figures_census_psd"
LABEL = "fig:census:psd"
SUPERSEDED_LABEL = "fig:census:psd:lower"
FIGURE = "fig_census_psd_all23"
SPECTRA_JSON = "spectra_window.json"
TITLE = "The transmitter population's spectral face: the era-mean spectrum around each pilot"
PDF_TITLE = "Era-mean spectra around the DTV pilots, all channels"

SAMPLE_RATE_HZ = 390625.0                        # archive.products.SAMPLE_RATE_HZ (not imported: it needs pilot_proxy)
NFFT = 16384                                     # archive.products.NFFT: the stored spectrum's length
PSD_BIN_HZ = SAMPLE_RATE_HZ / NFFT               # 23.84 Hz
SPAN_K = 128                                     # the campaign's tap length: the capture span
INNER_K = 256                                    # the narrower candidate span, nested inside it
REFERENCE_OFFSET_BINS = 2                        # references at +-2 bins of the K-tap grid
WINDOW_HZ = 15_000.0                             # archive.psd.WINDOW_HZ: the census window

NCOL, NROW = 4, 6                                # 24 cells: 23 panels and the reading note
LINSCALE = 1.15                                  # decades of x given to the linear (in-span) region
HEADROOM = 0.72                                  # share of the panel height the spectrum may use
SUPPORTED = "supported"
SENTINEL = "supported with sentinel"


def span_half_width_hz(k: int) -> float:
    """``f_s / 2K``: the unambiguous half-span of a K-tap window."""
    return SAMPLE_RATE_HZ / (2.0 * k)


def reference_offset_hz(k: int) -> float:
    """``+-2 f_s / K``: the reference placement of a K-tap window."""
    return REFERENCE_OFFSET_BINS * SAMPLE_RATE_HZ / k


def _finite(value) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _f(value) -> float:
    return float(value) if _finite(value) else math.nan


def _array(values) -> np.ndarray:
    return np.asarray([math.nan if v is None else float(v) for v in values], dtype=float)


# ------------------------------------------------------------------ the data
@dataclass(frozen=True)
class Lobe:
    """One marked feature of the era mean: where it is and how far it stands up."""

    offset_hz: float
    refined_offset_hz: float
    db: float
    excess_db: float

    @property
    def khz(self) -> float:
        return self.refined_offset_hz / 1000.0


@dataclass(frozen=True)
class ChannelSpectrum:
    """What one panel draws (empty arrays and NaN where the file has nothing)."""

    channel: int
    path: Path
    present: bool
    missing_reason: str
    provenance: str
    era_source: str                      # 'current' | 'previous' | ''
    era_months: str                      # '2023-12..2026-08'
    era_state: str                       # 'proxy-low'
    era_off: bool                        # the channel's current era is off
    era_from_ledger: bool
    freq_id: int | None
    frames: float
    detected_frames: float
    disposition: str
    reasons: str
    centre_line_rf_offset_hz: float
    offset_hz: np.ndarray
    mean_db: np.ndarray
    baseline_db: np.ndarray
    dominant: Lobe | None
    near: Lobe | None
    in_span: Lobe | None

    @property
    def drawable(self) -> bool:
        return self.present and self.offset_hz.size > 0

    @property
    def centre_line_in_window(self) -> bool:
        return _finite(self.centre_line_rf_offset_hz) and abs(self.centre_line_rf_offset_hz) <= WINDOW_HZ

    @property
    def dominant_out_of_span(self) -> bool:
        return self.dominant is not None and abs(self.dominant.refined_offset_hz) > span_half_width_hz(SPAN_K)

    @property
    def dominant_is_in_span_lobe(self) -> bool:
        """The two markers coincide: the same bin of the era mean (22 of the 23 channels)."""
        if self.dominant is None or self.in_span is None:
            return False
        return abs(self.dominant.refined_offset_hz - self.in_span.refined_offset_hz) <= PSD_BIN_HZ / 2.0

    @property
    def era_word(self) -> str:
        if self.era_source == "previous":
            return "previous era (now off)" if self.era_off else "previous era"
        if self.era_source == "current":
            return "current era"
        return "era unstated"

    @property
    def era_short(self) -> str:
        if self.era_source == "previous":
            return "previous (off)" if self.era_off else "previous"
        return self.era_source or DASH


_PROVENANCE = re.compile(r"^\s*(current|previous)\s+era\s+(\S+)\s*\(([^)]*)\)\s*(.*)$")


def parse_provenance(text: str) -> tuple[str, str, str, bool]:
    """``(source, months, state, current_era_is_off)`` from the spectra file's provenance string."""
    match = _PROVENANCE.match(str(text or ""))
    if not match:
        return "", "", "", False
    source, months, state, tail = match.groups()
    return source, months, state, source == "previous" or "current era is off" in tail


def _lobe(payload) -> Lobe | None:
    if not isinstance(payload, dict):
        return None
    offset = _f(payload.get("offset_hz"))
    refined = _f(payload.get("refined_offset_hz"))
    if not _finite(refined):
        refined = offset
    if not _finite(refined):
        return None
    return Lobe(offset, refined, _f(payload.get("db")), _f(payload.get("excess_db")))


def spectrum_path(run: Run, channel: int) -> Path:
    return Path(run.results_dir) / "channels" / f"ch{channel:02d}" / SPECTRA_JSON


def _empty(channel: int, path: Path, reason: str, ledger: core.Channel | None) -> ChannelSpectrum:
    era = ledger.era if ledger is not None else {}
    months = "..".join(str(era.get(k, "")) for k in ("current_first_month", "current_last_month")) if era else ""
    return ChannelSpectrum(
        channel=channel, path=path, present=False, missing_reason=reason, provenance="",
        era_source="current" if era else "", era_months=months if era else "", era_state=str(era.get("current_state", "") or ""),
        era_off=False, era_from_ledger=bool(era), freq_id=ledger.freq_id if ledger is not None else None,
        frames=math.nan, detected_frames=math.nan, disposition="", reasons="",
        centre_line_rf_offset_hz=math.nan, offset_hz=np.empty(0), mean_db=np.empty(0), baseline_db=np.empty(0),
        dominant=None, near=None, in_span=None)


def load_spectrum(run: Run, ledger: core.Channel) -> ChannelSpectrum:
    """One channel's window spectrum, or an empty record naming why there is none."""
    channel = ledger.channel
    path = spectrum_path(run, channel)
    if not path.is_file():
        return _empty(channel, path, f"{SPECTRA_JSON} absent", ledger)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return _empty(channel, path, f"{SPECTRA_JSON} unreadable ({type(exc).__name__})", ledger)
    entry = (payload.get("channels") or {}).get(str(channel))
    if not isinstance(entry, dict):
        return _empty(channel, path, f"{SPECTRA_JSON} carries no channel {channel}", ledger)
    provenance = str(payload.get("provenance", "") or "")
    source, months, state, off = parse_provenance(provenance)
    from_ledger = False
    if not source and ledger.era:
        source, from_ledger = "current", True
        months = "..".join(str(ledger.era.get(k, "")) for k in ("current_first_month", "current_last_month"))
        state = str(ledger.era.get("current_state", "") or "")
    offset = _array(entry.get("rf_offset_hz", ()))
    mean = _array(entry.get("mean_db", ()))
    baseline = _array(entry.get("baseline_db", ()))
    n = min(offset.size, mean.size, baseline.size)
    return ChannelSpectrum(
        channel=channel, path=path, present=True, missing_reason="", provenance=provenance,
        era_source=source, era_months=months, era_state=state, era_off=off, era_from_ledger=from_ledger,
        freq_id=entry.get("freq_id"), frames=_f(entry.get("frames")), detected_frames=_f(entry.get("detected_frames")),
        disposition=str(entry.get("disposition", "") or ""), reasons=str(entry.get("reasons", "") or ""),
        centre_line_rf_offset_hz=_f(entry.get("centre_line_rf_offset_hz")),
        offset_hz=offset[:n], mean_db=mean[:n], baseline_db=baseline[:n],
        dominant=_lobe(entry.get("dominant")), near=_lobe(entry.get("near")), in_span=_lobe(entry.get("in_span")))


def spectra(run: Run) -> list[ChannelSpectrum]:
    """One record per ledger channel, in physical-channel order."""
    return [load_spectrum(run, ch) for ch in run.channels]


def short_disposition(disposition: str) -> str:
    """The panel's word for a disposition: ``supported with sentinel`` is ``supported (sentinel)``."""
    if not disposition:
        return "disposition unstated"
    if disposition == SENTINEL:
        return "supported (sentinel)"
    return disposition.replace(" with sentinel", " (sentinel)")


def era_counts(rows: Sequence[ChannelSpectrum]) -> dict[str, int]:
    """Panels by what they draw: the current era, the previous on era, and the ones with no spectrum."""
    return {"current": sum(1 for r in rows if r.drawable and r.era_source == "current"),
            "previous": sum(1 for r in rows if r.drawable and r.era_source == "previous"),
            "sentinel": sum(1 for r in rows if r.drawable and r.disposition == SENTINEL),
            "dominant_out_of_span": sum(1 for r in rows if r.drawable and r.dominant_out_of_span),
            "centre_line_in_window": sum(1 for r in rows if r.drawable and r.centre_line_in_window),
            "no_in_span_lobe": sum(1 for r in rows if r.drawable and r.in_span is None),
            "no_spectrum": sum(1 for r in rows if not r.drawable)}


# ------------------------------------------------------------------ the figure
def _fit_pt(text: str, base_pt: float, width_in: float, *, ratio: float = 0.50, floor: float = 4.0) -> float:
    """Shrink a one-line label until its char-count estimate fits ``width_in``; never grows it."""
    estimate = len(text) * ratio * base_pt / 72.0
    if estimate <= width_in or estimate <= 0:
        return base_pt
    return max(floor, base_pt * width_in / estimate)


def _panel_titles(ax, s: ChannelSpectrum, width_in: float) -> None:
    months = s.era_months.replace("..", "--") if s.era_months else ""
    head = rf"\textbf{{ch {s.channel}}}" + (f" {tex(months)}" if months else "")
    plain = f"ch {s.channel} {months}"
    ax.text(0.5, 1.155, head, transform=ax.transAxes, ha="center", va="bottom", color=style.INK,
            fontsize=_fit_pt(plain, 6.0, width_in))
    line = f"{s.era_word}; {short_disposition(s.disposition)}" if s.present else f"{s.era_word}; no spectrum"
    colour = style.MODEL if s.disposition and s.disposition != SUPPORTED else style.MUTED
    ax.text(0.5, 1.012, tex(line), transform=ax.transAxes, ha="center", va="bottom", color=colour,
            fontsize=_fit_pt(line, 5.2, width_in))


def _panel(ax, s: ChannelSpectrum, *, width_in: float, show_x: bool, show_y: bool) -> None:
    half_span = span_half_width_hz(SPAN_K) / 1000.0
    half_inner = span_half_width_hz(INNER_K) / 1000.0
    reference = reference_offset_hz(SPAN_K) / 1000.0
    window = WINDOW_HZ / 1000.0
    ax.axvspan(-half_span, half_span, facecolor=style.LIGHT_BLUE, edgecolor="none", zorder=0)
    ax.axvspan(-half_inner, half_inner, facecolor=style.MEASURED, alpha=0.14, edgecolor="none", zorder=0)
    for ref in (-reference, reference):
        ax.axvline(ref, color=style.CONDITIONAL, ls=(0, (3, 2)), lw=0.6, zorder=1)
    ax.axvline(0.0, color=style.MUTED, lw=0.4, zorder=1)
    if s.centre_line_in_window:
        ax.axvline(s.centre_line_rf_offset_hz / 1000.0, color=style.PENDING, ls=(0, (1, 1.5)), lw=0.8, zorder=2)

    if s.drawable:
        khz = s.offset_hz / 1000.0
        ax.plot(khz, s.baseline_db, color=style.PENDING, ls=(0, (2.2, 1.4)), lw=0.5, zorder=3)
        ax.plot(khz, s.mean_db, color=style.INK, lw=0.55, zorder=4)
        low = min(-1.0, float(np.nanmin(s.mean_db)) - 0.3)
        peak = max(float(np.nanmax(s.mean_db)), 3.0)
    else:
        low, peak = -1.0, 3.0
    high = low + (peak - low) / HEADROOM
    ax.set_ylim(low, high)

    if s.in_span is not None:
        ax.plot([s.in_span.khz, s.in_span.khz], [low, s.in_span.db], color=style.MEASURED, lw=0.5, alpha=0.55, zorder=5)
        ax.plot(s.in_span.khz, s.in_span.db, marker="o", color=style.MEASURED, ms=2.4, ls="none", zorder=7)
    if s.dominant is not None:
        ax.plot(s.dominant.khz, s.dominant.db, marker="o", mfc="none", mec=style.MODEL, mew=0.8, ms=4.6, ls="none", zorder=6)
        if not s.dominant_is_in_span_lobe:
            # anchored away from the panel edge, so a carrier near the window rim keeps its label on the canvas
            ax.text(s.dominant.khz, s.dominant.db + 0.05 * (high - low), rf"${fmt(s.dominant.khz, 1, plus=True)}$ kHz",
                    ha=("left" if s.dominant.khz < 0 else "right"), va="bottom", fontsize=4.9, color=style.MODEL, zorder=7)
    if not s.drawable:
        ax.text(0.5, 0.42, tex(s.missing_reason or "no spectrum"), transform=ax.transAxes, ha="center", va="center",
                fontsize=4.9, color=style.FAILURE)

    ax.set_xscale("symlog", linthresh=half_span, linscale=LINSCALE)
    ax.set_xlim(-window, window)
    # only the window edge and zero are labelled: on the symmetric-log axis the reference tick sits
    # within a label's width of the edge, and the references name themselves in the legend
    ax.set_xticks([-window, 0.0, window])
    ax.set_xticks([-reference, -half_span, -half_inner, half_inner, half_span, reference], minor=True)
    ax.set_xticklabels([rf"$-{window:g}$", "0", f"${window:g}$"])
    ax.tick_params(axis="x", labelbottom=show_x)             # the tick labels only under the foot of each column
    ax.yaxis.set_major_locator(MaxNLocator(3))
    ax.grid(True, axis="y", color=style.GRID, lw=0.3, zorder=0)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(labelsize=5.4, length=1.9, width=0.5, pad=1.2)
    ax.tick_params(which="minor", length=1.1, width=0.4)
    if show_y:
        ax.set_ylabel("dB over median", fontsize=5.4, labelpad=1.6)


def _note_cell(ax, rows: Sequence[ChannelSpectrum], width_in: float) -> None:
    counts = era_counts(rows)
    lines = ["Each panel is that channel's own era mean.",
             f"{counts['current']} panels are the current era; "
             f"{counts['previous']} are the previous on era (the current era is off)."]
    if counts["no_spectrum"]:
        lines.append(f"{counts['no_spectrum']} channels have no stored window spectrum.")
    lines += ["x: linear inside the K = 128 span, logarithmic outside.",
              "y: dB over that channel's window median, one scale per panel."]
    cols = max(16, int(width_in * 72.0 / (0.62 * 4.9)))
    text = "\n".join("\n".join(textwrap.wrap(line, cols)) for line in lines)
    ax.set_axis_off()
    ax.text(0.0, 1.0, tex(text), transform=ax.transAxes, ha="left", va="top", fontsize=4.9, color=style.MUTED,
            linespacing=1.35)


def legend_handles(rows: Sequence[ChannelSpectrum]) -> list:
    half_span, half_inner = span_half_width_hz(SPAN_K), span_half_width_hz(INNER_K)
    reference = reference_offset_hz(SPAN_K)
    handles = [
        Line2D([0], [0], color=style.INK, lw=1.0, label="era-mean spectrum"),
        Line2D([0], [0], color=style.PENDING, ls=(0, (2.2, 1.4)), lw=1.0, label="sliding-median baseline"),
        Patch(facecolor=style.LIGHT_BLUE, edgecolor="none", label=rf"$K = {SPAN_K}$ span $\pm{half_span / 1000:.3f}$ kHz"),
        Patch(facecolor=style.MEASURED, alpha=0.14, edgecolor="none",
              label=rf"$K = {INNER_K}$ span $\pm{half_inner / 1000:.3f}$ kHz"),
        Line2D([0], [0], color=style.CONDITIONAL, ls=(0, (3, 2)), lw=1.0,
               label=rf"$K = {SPAN_K}$ references $\pm{reference / 1000:.2f}$ kHz"),
        Line2D([0], [0], marker="o", color=style.MEASURED, ls="none", ms=2.8, label="in-span lobe"),
        Line2D([0], [0], marker="o", mfc="none", mec=style.MODEL, mew=0.8, ls="none", ms=4.6,
               label="dominant lobe of the window"),
    ]
    if any(r.centre_line_in_window for r in rows):
        handles.append(Line2D([0], [0], color=style.PENDING, ls=(0, (1, 1.5)), lw=1.0,
                              label="coarse-channel centre line (instrumental)"))
    return handles


def figure_census_psd(rows: Sequence[ChannelSpectrum], *, ncol: int = NCOL, nrow: int = NROW):
    """Every channel on one canvas: ``nrow`` x ``ncol`` panels, the last free cell the reading note."""
    left, right, bottom, top, wspace, hspace = 0.068, 0.988, 0.088, 0.945, 0.26, 0.58
    fig = plt.figure(figsize=(style.TEXT_WIDTH, 7.4))
    gs = fig.add_gridspec(nrow, ncol, left=left, right=right, bottom=bottom, top=top, wspace=wspace, hspace=hspace)
    width_in = style.TEXT_WIDTH * (right - left) / (ncol + (ncol - 1) * wspace)
    for i, s in enumerate(rows):
        row, col = divmod(i, ncol)
        # not shared: shared axes share one ticker, so a shared x would label every panel, not the foot of the column
        ax = fig.add_subplot(gs[row, col])
        _panel(ax, s, width_in=width_in, show_x=(row == nrow - 1 or i + ncol >= len(rows)), show_y=(col == 0))
        _panel_titles(ax, s, width_in)
    if len(rows) < nrow * ncol:
        row, col = divmod(len(rows), ncol)
        _note_cell(fig.add_subplot(gs[row, col]), rows, width_in)
    fig.suptitle(TITLE, fontsize=8.6, y=0.988)
    fig.text(0.5, 0.052, "RF offset from the nominal pilot [kHz]", ha="center", va="bottom", fontsize=6.4)
    fig.legend(handles=legend_handles(rows), loc="lower center", bbox_to_anchor=(0.5, 0.0), ncol=4, fontsize=5.7,
               handlelength=1.7, columnspacing=1.1, labelspacing=0.5, borderaxespad=0.0)
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
    """The figure, PDF and PNG, under ``out_dir``; the paths in order."""
    return _save(figure_census_psd(spectra(run)), Path(out_dir) / FIGURE, PDF_TITLE)


def _marks_text(s: ChannelSpectrum) -> str:
    out = []
    if not s.present:
        out.append(tex(s.missing_reason or "no spectrum"))
    if s.present and s.in_span is None:
        out.append("no in-span lobe")
    if s.dominant_out_of_span:
        out.append("dominant out of span")
    if s.centre_line_in_window:
        out.append(f"centre line ${fmt(s.centre_line_rf_offset_hz / 1000.0, 1, plus=True)}$ kHz")
    if s.era_from_ledger:
        out.append("era from the ledger")
    return "; ".join(out) if out else DASH


def _math(text: str) -> str:
    return text if text == DASH else f"${text}$"


def build(run: Run) -> Fragment:
    """The data table behind the figure, with every value a panel prints keyed."""
    rows = spectra(run)
    frag = Fragment(NAME, LABEL, "")
    frag.inputs = list(run.inputs()) + [s.path for s in rows if s.present]
    header = ["ch", "era", "frames", "disposition", "lobe [Hz]", "lobe [dB]", "dominant [Hz]", "dominant [dB]", "marks"]
    body = []
    missing, no_lobe, out_of_span, centre, from_ledger, previous, sentinels = [], [], [], [], [], [], []
    pfx = "ch03.census_psd"
    for s in rows:
        ch = s.channel
        row = {"channel": ch}
        if not s.present:
            missing.append(ch)
        if s.era_from_ledger:
            from_ledger.append(ch)
        if s.era_source == "previous":
            previous.append(ch)
        if s.present:
            frag.add(f"{pfx}.era.{ch}", s.provenance or f"{s.era_word} {s.era_months}", kind="text",
                     renderings=tuple(t for t in (s.provenance, s.era_months, s.era_word) if t), row=row, column="era")
            frag.add(f"{pfx}.era_state.{ch}", s.era_state or None, kind="text",
                     renderings=(s.era_state,) if s.era_state else (), row=row, column="era",
                     status="measured" if s.era_state else "pending")
            frag.add(f"{pfx}.disposition.{ch}", s.disposition or None, kind="text",
                     renderings=tuple({s.disposition, short_disposition(s.disposition)}) if s.disposition else (),
                     row=row, column="disposition", status="derived" if s.disposition else "pending")
            frag.add(f"{pfx}.frames.{ch}", s.frames, kind="int", row=row, column="frames",
                     status="measured" if _finite(s.frames) else "pending")
            frag.add(f"{pfx}.detected_frames.{ch}", s.detected_frames, kind="int", row=row, column="frames",
                     status="measured" if _finite(s.detected_frames) else "pending")
            if s.disposition == SENTINEL:
                sentinels.append(ch)
        if s.in_span is not None:
            frag.add(f"{pfx}.in_span_offset_hz.{ch}", s.in_span.refined_offset_hz, precision=1, row=row, column="lobe [Hz]")
            frag.add(f"{pfx}.in_span_db.{ch}", s.in_span.db, precision=1, row=row, column="lobe [dB]")
            frag.add(f"{pfx}.in_span_excess_db.{ch}", s.in_span.excess_db, precision=1, row=row, column="lobe [dB]")
        elif s.present:
            no_lobe.append(ch)
        if s.dominant is not None:
            frag.add(f"{pfx}.dominant_offset_hz.{ch}", s.dominant.refined_offset_hz, precision=1, row=row, column="dominant [Hz]")
            frag.add(f"{pfx}.dominant_db.{ch}", s.dominant.db, precision=1, row=row, column="dominant [dB]")
            frag.add(f"{pfx}.dominant_excess_db.{ch}", s.dominant.excess_db, precision=1, row=row, column="dominant [dB]")
        if s.dominant_out_of_span:
            out_of_span.append(ch)
            frag.add(f"{pfx}.dominant_offset_khz.{ch}", s.dominant.khz, precision=1, row=row, column="dominant [Hz]",
                     renderings=(f"{s.dominant.khz:+.1f} kHz",))
        if s.centre_line_in_window:
            centre.append(ch)
            frag.add(f"{pfx}.centre_line_rf_offset_hz.{ch}", s.centre_line_rf_offset_hz, precision=1, row=row, column="marks")
        era_cell = f"{s.era_short} {tex(s.era_months.replace('..', '--'))}".strip() if s.era_months else tex(s.era_short)
        body.append([str(ch), era_cell, _math(fmt_int(s.frames)), tex(short_disposition(s.disposition)) if s.present else DASH,
                     _math(fmt(s.in_span.refined_offset_hz, 1) if s.in_span else DASH),
                     _math(fmt(s.in_span.db, 1) if s.in_span else DASH),
                     _math(fmt(s.dominant.refined_offset_hz, 1) if s.dominant else DASH),
                     _math(fmt(s.dominant.db, 1) if s.dominant else DASH), _marks_text(s)])
    frag.tex = booktabs(header, body, "llrlrrrrl")

    counts = era_counts(rows)
    frag.add(f"{pfx}.channels", len(rows), kind="int", status="derived", column="panels")
    for name, value in counts.items():
        frag.add(f"{pfx}.count.{name}", value, kind="int", status="derived", column="panels")
    frag.add(f"{pfx}.span_half_width_hz", span_half_width_hz(SPAN_K), precision=1, status="derived", column="spans")
    frag.add(f"{pfx}.inner_span_half_width_hz", span_half_width_hz(INNER_K), precision=1, status="derived", column="spans")
    frag.add(f"{pfx}.reference_offset_hz", reference_offset_hz(SPAN_K), precision=1, status="derived", column="references")
    frag.add(f"{pfx}.window_hz", WINDOW_HZ, precision=0, status="derived", column="window")

    frag.notes.append(f"label {LABEL}: one 23-panel figure over the per-channel era means; it replaces the superseded "
                      f"archive-average plates {LABEL} (channels 27--36) and {SUPERSEDED_LABEL} (channels 14--26)")
    frag.notes.append(f"{counts['current']} panels draw the channel's current era and {counts['previous']} the previous on era "
                      f"(channels {_list(previous) or 'none'}: the current era is off, so its mean measures nothing); "
                      "every panel says which era it draws")
    frag.notes.append("the y scale is per panel (dB over that channel's window median): the panel peaks span "
                      f"{fmt(_peak(rows, min), 1)}--{fmt(_peak(rows, max), 1)} dB and one shared scale would flatten the quiet channels")
    frag.notes.append(f"the x axis is linear inside the K = {SPAN_K} span and logarithmic outside it (symmetric log, linthresh "
                      f"{fmt(span_half_width_hz(SPAN_K), 1)} Hz), so a lobe hundreds of hertz off nominal and a carrier "
                      "kilohertz away are both legible; only the window edge and zero are labelled, and the span and "
                      "reference ticks are minor and named in the legend")
    if sentinels:
        frag.notes.append(f"channels {_list(sentinels)}: disposition '{SENTINEL}' (the panel prints 'supported (sentinel)')")
    if out_of_span:
        frag.notes.append(f"channels {_list(out_of_span)}: the dominant lobe of the window lies outside the K = {SPAN_K} span; "
                          "the ring stands apart from the in-span dot and the panel prints its offset in kHz")
    frag.notes.append("on every other channel the dominant lobe is the in-span lobe: the ring nests around the dot")
    if centre:
        frag.notes.append(f"channels {_list(centre)}: the coarse channel's own centre bin falls inside the +-15 kHz window "
                          "(dotted, instrumental, a forbidden tone for the reference placement, not a member of the population)")
    if no_lobe:
        frag.notes.append(f"channels {_list(no_lobe)}: no in-span lobe stands over the baseline: no dot, no stem, dashes")
    if missing:
        frag.notes.append(f"channels {_list(missing)}: no window spectrum ({'; '.join(sorted({s.missing_reason for s in rows if not s.present}))}): "
                          "the panel draws the spans and the note alone, and the row is dashes")
    if from_ledger:
        frag.notes.append(f"channels {_list(from_ledger)}: the spectra file carries no parsable provenance; the era months are the "
                          "ledger's current era instead")
    frag.notes.append("the figure prints no per-frame peak counts, no excess spectrum and no census rows: the panels are the "
                      "era means alone")
    return frag


def _list(values) -> str:
    return ", ".join(str(v) for v in values)


def _peak(rows: Sequence[ChannelSpectrum], pick) -> float:
    peaks = [float(np.nanmax(s.mean_db)) for s in rows if s.drawable and np.isfinite(s.mean_db).any()]
    return pick(peaks) if peaks else math.nan
