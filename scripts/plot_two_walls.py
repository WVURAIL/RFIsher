#!/usr/bin/env python3
"""The two ways a channel fails, drawn as the two walls of one plane.

Every masking policy for a channel is a point in the (f, r) plane: the
fraction of time it discards, and the residual it leaves in what it keeps.
Tolerance is a box in that plane, and its two edges are two different
failures:

    the bias wall      r > r_tol      the kept data are too dirty
    the occupancy wall f -> 1         nothing is kept at all

The detector's threshold eta traces a curve between them: eta = 1 (positive
excess) is the minimum-r, maximum-f end; raising eta walks toward keep-
everything. A channel is salvageable iff its curve enters the box. The two
impossibility arguments of the introduction are the two walls: no detector
sees below the sensitivity floor (the bias wall's position is fixed), and no
detector reschedules a transmitter (the occupancy wall is where the channel
puts it).

The two failures are nearly mutually exclusive in any one era, because both
are driven by the same variable pulled in opposite directions: duty cycle.
And a heavily occupied channel starves the null sample, so failing the
occupancy wall also destroys the measurement of the bias wall: ch34 keeps 355
frames, ch36 keeps 34, and their r values are bounds from starved estimates.

    python3 scripts/plot_two_walls.py --out out/
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np


from rfisher import residual
from rfisher import selection_policy
from rfisher.plots import (
    CRITICAL, GRID, INK, INK2, MUTED, SERIES, SURFACE, _save, setup_style)
import matplotlib.pyplot as plt

# Stable zeta = 1 tolerances on the binding dilation, alpha_perp, per z bin
# (one home: rfisher.tolerances). The figure shows the first-measured block.
from rfisher.tolerances import TOL_APERP, TOL_FS8
CHANNELS = tuple(sorted(TOL_FS8))
# fs8 tolerance relative to alpha_perp's, per bin, drawn as a band because
# the ratio differs between the two z bins the five channels occupy.
_FS8_RATIOS = tuple(TOL_FS8[ch] / TOL_APERP[ch] for ch in CHANNELS)
FS8_REL = (min(_FS8_RATIOS), max(_FS8_RATIOS))

FINE_DB = float(selection_policy.value("transfer.fine_stage_credit_db"))
REPORT_TOLERANCE_TARGET = str(selection_policy.value(
    "archive_reference.operating_point_tolerance_target"))
_TOLERANCE_TABLES = {"aperp": TOL_APERP, "fs8": TOL_FS8}
if REPORT_TOLERANCE_TARGET not in _TOLERANCE_TABLES:
    raise RuntimeError("report tolerance target is not defined")
REPORT_TOLERANCES = _TOLERANCE_TABLES[REPORT_TOLERANCE_TARGET]
PRIMARY_ZETA = float(selection_policy.value(
    "science.systematic_budget.primary_zeta"))
_TARGET_LABELS = {"aperp": "transverse dilation", "fs8": "growth rate"}
REPORT_TOLERANCE_LABEL = _TARGET_LABELS[REPORT_TOLERANCE_TARGET]
(_LINEAR_START, _LINEAR_STOP, _LINEAR_COUNT,
 _GEOMETRIC_START, _GEOMETRIC_STOP, _GEOMETRIC_COUNT) = (
    selection_policy.value("archive_reference.two_walls_eta_grid"))
ERA_POINTS = Path(__file__).resolve().parent / "dissertation" / "data" \
    / "bao_era_points.csv"
from rfisher import products
PATHS = products.paths(channels=CHANNELS)
# Story channels in color: ch33 (the one basis-sensitive feasible channel),
# ch32 and ch35 (the reconciliation's two instructive removals), ch29 (the
# tau_c-hostage contrast); everything else gray.
COLORS = {32: SERIES[0], 33: SERIES[1], 35: SERIES[2], 29: SERIES[3]}
GRAY = MUTED


def era_point(channel):
    with ERA_POINTS.open(newline="", encoding="utf-8") as handle:
        rows = csv.DictReader(handle)
        row = next(r for r in rows if int(r["channel"]) == channel)
    return float(row["masked_fraction"]), float(row["r_over_rtol"])


def channel_curve(ch, p):
    """(f, r/tol) along the threshold family, with provenance flags.

    Floor and residual booking follow the package's one discipline
    (kept_frame_floor / surviving_components inside threshold_sweep).
    """
    floor_db, evidence = residual.kept_frame_floor(p)
    etas = np.concatenate([
        np.linspace(_LINEAR_START, _LINEAR_STOP, int(_LINEAR_COUNT)),
        np.geomspace(_GEOMETRIC_START, _GEOMETRIC_STOP,
                     int(_GEOMETRIC_COUNT)),
    ])
    sweep = residual.threshold_sweep(p, etas=etas, floor_db=floor_db)
    tol = REPORT_TOLERANCES[ch]
    pts = [(row["f"], row["r_masked"] / 10 ** (FINE_DB / 10) / tol,
            row["eta"]) for row in sweep]
    corr = residual.correlation_time(p)
    return dict(ch=ch, pts=pts, stated_floor=(evidence == "stated"),
                tau_bound=(corr.quality != "measured"))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path("out"))
    args = ap.parse_args(argv)

    curves = [channel_curve(ch, p) for ch, p in PATHS.items()]

    setup_style()
    fig, ax = plt.subplots(figsize=(7.6, 4.8))

    # the admissible box: under the bias wall, left of the occupancy wall
    ax.axhspan(1e-3, 1.0, xmin=0, xmax=1, color=GRID, alpha=0.5, zorder=0, lw=0)
    ax.axhline(1.0, color=INK, lw=1.3, zorder=5)
    ax.axvline(1.0, color=INK, lw=1.3, zorder=5)
    ax.annotate("the bias wall: kept data too dirty "
                rf"($r = r_{{\rm tol}}$, {REPORT_TOLERANCE_LABEL}, "
                rf"$\zeta = {PRIMARY_ZETA:g}$)",
                xy=(0.02, 1.0), xytext=(0, 5), textcoords="offset points",
                fontsize=9, color=INK, va="bottom")
    ax.annotate("the occupancy wall: nothing left to keep",
                xy=(0.994, 4e-3), xytext=(-10, 0), textcoords="offset points",
                fontsize=9, color=INK, ha="right", va="bottom", rotation=90)
    ax.annotate("tolerable", xy=(0.03, 0.55), fontsize=10, color=INK2,
                style="italic")

    # where fs8's wall would sit, relative to alpha_perp's
    ax.axhspan(*FS8_REL, color=CRITICAL, alpha=0.10, zorder=0, lw=0)
    ax.annotate(r"the $f\sigma_8$ wall falls in this band "
                "(10-25x lower, bin-dependent)",
                xy=(0.02, FS8_REL[0] * 1.15), fontsize=8.5, color=CRITICAL,
                va="bottom")

    for cur in curves:
        ch, pts = cur["ch"], cur["pts"]
        if not pts:
            continue
        c = COLORS.get(ch, GRAY)
        f = np.array([p[0] for p in pts])
        rr = np.array([p[1] for p in pts])
        order = np.argsort([p[2] for p in pts])
        f, rr = f[order], rr[order]
        dashed = cur["stated_floor"] or cur["tau_bound"]
        ax.plot(f, rr, color=c, lw=2.0, zorder=4,
                ls=(0, (4, 2)) if dashed else "-",
                solid_capstyle="round")
        ax.plot([f[0]], [rr[0]], "o", ms=8, color=c, zorder=6,
                markeredgecolor=SURFACE, markeredgewidth=1.5)
        lab_x, lab_y = f[0], rr[0]
        big = ch in COLORS
        off = {30: (6, -13), 34: (6, 6), 28: (6, 7), 31: (6, -14)}.get(ch, (6, 7))
        ax.annotate(f"ch{ch}", xy=(lab_x, lab_y), xytext=off,
                    textcoords="offset points",
                    fontsize=9.5 if big else 8, color=c,
                    fontweight="semibold" if big else "normal")

    # Calibrated eta_mu = 1 on the post-sign-on channel-35 era.
    c35 = next(c for c in curves if c["ch"] == 35)
    pt = era_point(35) if c35["pts"] else None
    if pt is not None:
        f_fwd, r_fwd = pt
        c35_color = COLORS.get(35, GRAY)
        ax.plot([f_fwd], [r_fwd], "X", ms=9, color=c35_color, zorder=6,
                markeredgecolor=SURFACE, markeredgewidth=1.2)
        ax.annotate("ch35 after sign-on (2021-11 onward):\ncalibrated "
                    f"endpoint remains {r_fwd:.0f}x above the bias wall",
                    xy=(f_fwd, r_fwd), xytext=(0.42, 6e-3), fontsize=8.5,
                    color=c35_color,
                    arrowprops=dict(arrowstyle="-", color=c35_color, lw=0.8,
                                    shrinkA=2, shrinkB=3))

    ax.annotate("Filled dots mark positive excess ($\\eta = 1$): minimum "
                "residual, maximum cost.  Raising $\\eta$ walks each curve "
                "right-to-left toward keep-everything.",
                xy=(0.5, -0.14), xycoords="axes fraction", ha="center",
                fontsize=8.5, color=INK2)

    ax.set_yscale("log")
    ax.set_xlim(0, 1.04)
    ax.set_ylim(2e-3, 3e4)
    ax.set_xlabel("Masked fraction of observing time, $f$")
    ax.set_ylabel(r"Residual over tolerance, "
                  r"$r \, / \, r_{\rm tol}$ (transverse dilation)   [fine stage]")
    ax.set_title("Two ways to fail, one plane: every threshold is a point, "
                 "every channel a curve")
    return _save(fig, args.out / "fig_bao_two_walls.png")


if __name__ == "__main__":
    raise SystemExit(main())
