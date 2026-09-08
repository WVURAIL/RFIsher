"""The masking-cost curve, marked at what this run's masks would cost.

Chapter 9's Figure ``fig:tolerance:time`` is the algebraic cost map of
Eq. ``tolerance:teff``: the observing time to reach a fixed BAO target against
the masked fraction of the DTV band, at zero residual, under the band
averaging of Eq. ``tolerance:wbar``. The three curves are the *forecast's*
output and are unchanged by the archive run; what the run supplies is where on
them this band's masks fall.

The stub asks for the historical annotations to go and for two marks in their
place: the band-level masked fraction at the per-channel operating points, and
the survey flag rate shown only as an occupancy reference. Both are read from
the ledger, frame-weighted over the channels the handover keeps, so the mark is
the cost of a policy rather than an average over channels of different size.

Inputs. ``scripts/dissertation/data/bao_masking_cost_curve.csv``
(``series, masked_fraction, time_year``) and its reference file, which carry
the forecast curves; the run's ``selection.diagnostic_masked_fraction``,
``screening.survey_flag_rate_era`` and ``era.current_frames``, and the
screening class, which says which channels the handover keeps.

Numbers: ``ch09.masking_cost.*`` --- the two marked fractions, their costs
``1/(1-f)``, the observing time each series needs there, and the channels the
average runs over.
"""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import numpy as np

from .core import Fragment, Run, booktabs, fmt, fmt_int

NAME = "figures_masking_cost"
LABEL = "fig:tolerance:time"
FIGURE = "fig_bao_time_vs_masking"
CURVE_CSV = Path(__file__).resolve().parents[4] / "scripts" / "dissertation" / "data" / "bao_masking_cost_curve.csv"
REFERENCE_CSV = CURVE_CSV.with_name("bao_masking_cost_reference.csv")
EXCISION = "occupancy-wall excision candidate"
SERIES = ("dilation", "bin_amplitude", "survey_amplitude")
SERIES_LABEL = {"dilation": r"$\sigma(D_A) \leq 2\%$, $z = 1.40$--$1.50$ bin",
                "bin_amplitude": r"BAO amplitude $S/N = 5$, $z = 1.40$--$1.50$ bin",
                "survey_amplitude": r"BAO amplitude $S/N = 5$, full survey"}


def _num(value) -> float:
    try:
        return float(value) if value is not None else math.nan
    except (TypeError, ValueError):
        return math.nan


def read_curves(path: Path | str = CURVE_CSV) -> dict[str, np.ndarray]:
    """``{series: (n, 2) array of (masked fraction, years)}``, ordered by masked fraction."""
    rows: dict[str, list[tuple[float, float]]] = {}
    with Path(path).open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rows.setdefault(row["series"], []).append((float(row["masked_fraction"]), float(row["time_year"])))
    return {k: np.array(sorted(v)) for k, v in rows.items()}


@dataclass(frozen=True)
class BandMask:
    """One policy's band-level masked fraction, frame-weighted over the channels it applies to."""

    name: str
    masked_fraction: float
    frames: int
    channels: tuple[int, ...]

    @property
    def cost(self) -> float:
        if math.isnan(self.masked_fraction):
            return math.nan
        return 1.0 / (1.0 - self.masked_fraction) if self.masked_fraction < 1.0 else math.inf


def band_masks(run: Run) -> tuple[BandMask, BandMask]:
    """The reported points' band mask and the survey flag's, over the channels the handover keeps.

    A channel the handover excises leaves the average entirely (chapter 9
    prices excision against the bin's volume, not its noise), so both marks
    run over the same kept channels and are comparable.
    """
    kept, flag_rows, point_rows = [], [], []
    for c in run.channels:
        if str(c.screening.get("screening_class") or "") == EXCISION:
            continue
        frames = _num(c.era.get("current_frames"))
        if not (math.isfinite(frames) and frames > 0):
            continue
        kept.append(c.channel)
        flag = _num(c.screening.get("survey_flag_rate_era"))
        point = _num(c.selection.get("diagnostic_masked_fraction")) if c.has("selection") else math.nan
        if math.isfinite(flag):
            flag_rows.append((frames, flag))
        if math.isfinite(point):
            point_rows.append((frames, point))

    def weighted(rows, name):
        if not rows:
            return BandMask(name, math.nan, 0, tuple(kept))
        w = np.array([r[0] for r in rows], dtype=float)
        f = np.array([r[1] for r in rows], dtype=float)
        return BandMask(name, float((w * f).sum() / w.sum()), int(w.sum()), tuple(kept))

    return weighted(point_rows, "reported points"), weighted(flag_rows, "survey flag")


def build(run: Run, *, curves: Mapping[str, np.ndarray] | None = None) -> Fragment:
    """The marked points of the cost curve, and the numbers the figure prints."""
    cs = dict(curves) if curves is not None else read_curves()
    point, flag = band_masks(run)
    frag = Fragment(NAME, LABEL, "")
    frag.inputs = [Path(CURVE_CSV), Path(REFERENCE_CSV), *run.inputs()]
    header = ["mark", "$f$", "$1/(1-f)$", *[SERIES_LABEL[s] for s in SERIES]]
    rows = []
    for mark in (point, flag):
        cells = [mark.name, fmt(mark.masked_fraction, 3), fmt(mark.cost, 1)]
        for s in SERIES:
            years = float(np.interp(mark.masked_fraction, cs[s][:, 0], cs[s][:, 1])) if s in cs else math.nan
            cells.append(fmt(years, 3))
            frag.add(f"ch09.masking_cost.years.{s}.{mark.name.replace(' ', '_')}", years, precision=3,
                     row={"mark": mark.name}, column=s)
        rows.append(cells)
        key = mark.name.replace(" ", "_")
        frag.add(f"ch09.masking_cost.masked_fraction.{key}", mark.masked_fraction, precision=3,
                 row={"mark": mark.name}, column="f")
        frag.add(f"ch09.masking_cost.cost.{key}", mark.cost, precision=1, row={"mark": mark.name}, column="cost")
        frag.add(f"ch09.masking_cost.frames.{key}", mark.frames, kind="int", row={"mark": mark.name}, column="frames")
    frag.tex = booktabs(header, rows, "lrr" + "r" * len(SERIES))
    frag.add("ch09.masking_cost.channels", len(point.channels), kind="int", column="channels")
    frag.add("ch09.masking_cost.channel_list", ", ".join(str(c) for c in point.channels), kind="text",
             renderings=(", ".join(str(c) for c in point.channels),), column="channels")
    frag.notes.append(
        f"the curves are the forecast's and are unchanged by this run; the marks are its own, frame-weighted over the "
        f"{len(point.channels)} channels the handover keeps ({fmt_int(point.frames)} current-era frames) and excluding the "
        f"excision candidates, which chapter 9 prices against the bin's volume rather than its noise")
    if not math.isfinite(point.masked_fraction):
        frag.notes.append("no channel reports a point: the reported-point mark is undefined")
    return frag


def render(run: Run, out_dir: Path | str) -> list[Path]:
    """The figure: the three forecast curves with this run's two marks, no historical annotations."""
    import matplotlib.pyplot as plt

    from ... import style

    cs = read_curves()
    point, flag = band_masks(run)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    colors = {"dilation": style.MEASURED, "bin_amplitude": style.MODEL, "survey_amplitude": style.CONDITIONAL}
    fig, ax = plt.subplots(figsize=(style.TEXT_WIDTH, 3.35))
    for s in SERIES:
        if s not in cs:
            continue
        ax.plot(100 * cs[s][:, 0], cs[s][:, 1], color=colors[s], label=SERIES_LABEL[s])
    # the scales first: an annotation placed before them is clipped by the final limits
    ax.set_yscale("log")
    ax.set_xlim(-5, 102)
    ax.set_ylim(0.018, 20)
    for mark, dashed, label, y in ((point, False, "band mask at the reported points", 0.85),
                                   (flag, True, "survey flag rate (occupancy reference)", 0.28)):
        if not math.isfinite(mark.masked_fraction):
            continue
        x = 100 * mark.masked_fraction
        colour = style.MUTED if dashed else style.INK
        ax.axvline(x, color=colour, lw=0.9, ls=(0, (2, 2)) if dashed else "-", zorder=1)
        for s in SERIES:
            if s in cs:
                ax.scatter([x], [float(np.interp(mark.masked_fraction, cs[s][:, 0], cs[s][:, 1]))],
                           color=colors[s], s=22, zorder=4, edgecolor="white", linewidth=0.5)
        ax.annotate(f"{label}\n$f = {mark.masked_fraction:.3f}$, cost ${mark.cost:.1f}\\times$",
                    xy=(x, y), xycoords=("data", "axes fraction"), xytext=(-4, 0), textcoords="offset points",
                    fontsize=6.8, color=colour, ha="right", va="center", linespacing=1.35)
    ax.set_xlabel(r"Masked fraction of the DTV band [\%]")
    ax.set_ylabel(r"Required observing time [on-sky yr]")
    style.clean_axes(ax)
    ax.legend(loc="upper left", fontsize=7.2)
    ax.set_title(r"Masking cost: observing time to reach BAO targets versus uniform DTV masking", pad=5)
    pdf = style.save(fig, out / f"{FIGURE}.pdf", title="BAO observing time versus DTV masking")
    png = out / f"{FIGURE}.png"
    fig.savefig(png, dpi=200)
    plt.close(fig)
    return [Path(pdf), png]
