"""The transmitter population's spectral face: one panel per channel.

Reads the ``census_psd.csv`` a pilot-proxy export produces (columns
``channel, offset_khz, db_rel_median``: the time-averaged spectrum within
+-15 kHz of each pilot, dB relative to the channel median) and renders all
23 channels, 14 to 36 in physical-channel order, on one canvas. The same
table shape serves the archive-average export and the per-era export the
dissertation's chapter 3 stub calls for; which one was rendered is stated in
the panel key from the ``provenance`` argument.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle

from . import style

CHANNELS = tuple(range(14, 37))
FINE_SPAN_KHZ = 1.526          # K = 128 fine span, half-width
REFERENCE_KHZ = 6.1036         # reference bins
TITLE = "Time-averaged spectrum around each pilot: main lobe, companions, and references"


def load_census_psd(path: Path | str) -> dict[int, tuple[np.ndarray, np.ndarray]]:
    """Per channel, (offset_khz, db_rel_median) sorted by offset."""
    series: dict[int, list[tuple[float, float]]] = defaultdict(list)
    with Path(path).open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            series[int(row["channel"])].append((float(row["offset_khz"]), float(row["db_rel_median"])))
    out = {}
    for ch, pts in series.items():
        pts.sort()
        out[ch] = (np.asarray([p[0] for p in pts]), np.asarray([p[1] for p in pts]))
    return out


def _panel(ax, x, y, ch):
    ax.axvspan(-FINE_SPAN_KHZ, FINE_SPAN_KHZ, facecolor=style.LIGHT_BLUE, edgecolor="none")
    for ref in (-REFERENCE_KHZ, REFERENCE_KHZ):
        ax.axvline(ref, color=style.CONDITIONAL, ls=(0, (3, 2)), lw=0.7)
    ax.plot(x, y, color=style.INK, lw=0.6)
    ax.axvline(0, color=style.MUTED, lw=0.45)
    ax.text(0.05, 0.90, rf"\textbf{{ch {ch}}}", transform=ax.transAxes, ha="left", va="top", fontsize=6.6)
    ax.set_xlim(-15, 15)
    ax.grid(True, color=style.GRID, lw=0.35)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(labelsize=5.6, length=2, pad=1.5)


def figure_census_psd(csv_path: Path | str, *, out: Path, provenance: str,
                      channels: tuple[int, ...] = CHANNELS) -> Path:
    """All channels on one canvas: 4 rows x 6 columns, the 24th cell the key."""
    series = load_census_psd(csv_path)
    missing = [ch for ch in channels if ch not in series]
    if missing:
        raise ValueError(f"census_psd.csv lacks channels {missing}")
    ncol, nrow = 6, 4
    fig = plt.figure(figsize=(style.TEXT_WIDTH, 4.55))
    gs = fig.add_gridspec(nrow, ncol, left=0.06, right=0.992, bottom=0.085, top=0.905,
                          wspace=0.32, hspace=0.42)
    for i, ch in enumerate(channels):
        ax = fig.add_subplot(gs[i // ncol, i % ncol])
        x, y = series[ch]
        _panel(ax, x, y, ch)
        if i % ncol == 0:
            ax.set_ylabel("dB rel. median", fontsize=6.2)
        if i // ncol == nrow - 1 or i + ncol >= len(channels):
            ax.set_xlabel("offset [kHz]", fontsize=6.2)
    key = fig.add_subplot(gs[(len(channels)) // ncol, (len(channels)) % ncol])
    key.set_axis_off()
    key.add_patch(Rectangle((0.02, 0.74), 0.16, 0.14, transform=key.transAxes,
                            facecolor=style.LIGHT_BLUE, edgecolor="none"))
    key.text(0.24, 0.81, rf"fine span $\pm{FINE_SPAN_KHZ}$ kHz", transform=key.transAxes, va="center", fontsize=5.9)
    key.plot([0.02, 0.18], [0.57, 0.57], transform=key.transAxes, color=style.CONDITIONAL, ls=(0, (3, 2)), lw=1.0)
    key.text(0.24, 0.57, rf"references $\pm{REFERENCE_KHZ:.2f}$ kHz", transform=key.transAxes, va="center", fontsize=5.9)
    key.plot([0.02, 0.18], [0.36, 0.36], transform=key.transAxes, color=style.INK, lw=0.9)
    key.text(0.24, 0.36, "averaged spectrum", transform=key.transAxes, va="center", fontsize=5.9)
    key.text(0.02, 0.06, provenance, transform=key.transAxes, va="bottom", fontsize=5.4, color=style.MUTED, wrap=True)
    fig.suptitle(TITLE, fontsize=8.6, y=0.975)
    with style.stable_pdf_subset_tags():
        return style.save(fig, Path(out), title="Time-averaged spectra around DTV pilots, all channels")
