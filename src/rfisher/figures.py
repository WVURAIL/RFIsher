"""Unit-power response and tolerance figures from the saved channel table."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from radiofisher.units import NU21_MHZ

from . import inputs
from . import wvu_palette as wvu

INK, MUTED, GRID, SURF = wvu.INK, wvu.MUTED, wvu.tint(wvu.SENECA_GRAY, 0.3), wvu.WHITE
LINE = wvu.BLUE
GRID_DARK = wvu.SENECA_GRAY
COSMOLOGY_LABELS = {"planck2018": "Planck 2018"}
STYLE = {**wvu.plot_rcparams(), "font.size": 10.5, "axes.edgecolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED,
         "axes.labelcolor": INK, "figure.facecolor": SURF, "axes.facecolor": SURF, "text.color": INK,
         "axes.titlesize": 11, "axes.titleweight": "bold", "axes.titlelocation": "left"}


def _tidy(ax):
    ax.grid(True, color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)






def bias_line(ax, row, hours=inputs.RETAINED_HOURS):
    """|bias| / sigma of D_V = a |response_dv|, against strength a."""
    exposure = "one year" if hours == inputs.RETAINED_HOURS else f"{hours:,.0f} retained hours"
    a = row["a_tol"] * np.logspace(-3, 1, 200)
    q = row["response_dv"]
    ax.plot(a, a * abs(q), color=LINE, lw=2.2,
            label=f"D_V: bias {'−' if q > 0 else '+'}{abs(q):,.0f} σ per unit a")
    ax.axhline(1, color=INK, ls="--", lw=1.1)
    ax.axvline(row["a_tol"], color=MUTED, lw=1)
    ax.plot(row["a_tol"], 1, "o", color=INK, ms=6)
    ax.annotate(f"a_tol = {row['a_tol']:.2g}", (row["a_tol"], 1), xytext=(8, -22), textcoords="offset points",
                fontsize=9.5)
    ax.text(a[0] * 1.6, 1.35, "bias = σ", fontsize=9)
    ax.text(0.97, 0.04, f"σ(D_V)/D_V = {100 * row['sigma_dv']:.2f}%, {exposure}, clean",
            transform=ax.transAxes, ha="right", fontsize=9, color=MUTED)
    ax.set(xscale="log", yscale="log", xlim=(a[0], a[-1]), ylim=(1e-5, 1e3),
           xlabel="additive DTV power (mK²)", ylabel="|bias| ÷ σ of D_V",
           title="(b) Bias grows in proportion to strength")
    ax.legend(frameon=False, fontsize=9, loc="upper left")


def plate(row, out: Path, hours) -> Path:
    with plt.rc_context(STYLE):
        fig, ax = plt.subplots(figsize=(8, 5), constrained_layout=True)
        bias_line(ax, row, hours)
        _tidy(ax)
        fig.suptitle(f"Channel {row['channel']}: {row['low_mhz']:.0f}–{row['high_mhz']:.0f} MHz")
        path = out / f"channel_{row['channel']:02d}.png"
        fig.savefig(path, dpi=110)
        plt.close(fig)
    return path


def summary(table, out: Path) -> Path:
    hours = table["inputs"]["retained_hours"]
    exposure = "one year" if hours == inputs.RETAINED_HOURS else f"{hours:,.0f} retained hours"
    rows = sorted(table["channels"], key=lambda r: r["channel"])
    ch = np.array([r["channel"] for r in rows])
    z = np.array([r["z_center"] for r in rows])
    with plt.rc_context(STYLE):
        fig, axes = plt.subplots(1, 3, figsize=(17, 5), constrained_layout=True)
        ax = axes[0]
        ax.plot(ch, [r["a_tol"] for r in rows], "o", color=LINE, ms=8)
        ax.set(yscale="log", xlabel="channel", ylabel="power tolerance (mK²)", xticks=ch[::2],
               title="(a) Tolerated residual strength per channel")
        ax = axes[1]
        ax.plot(z, [-r["response_dv"] for r in rows], "o-", color=LINE, lw=1.6, ms=5)
        ax.axhline(0, color=MUTED, lw=1)
        ax.set(xlabel="redshift z", ylabel="bias ÷ σ of D_V per mK²",
               title="(b) Response of D_V (signed)")
        ax = axes[2]
        ax.plot(z, [100 * r["sigma_dv"] for r in rows], "o-", color=LINE, lw=1.6, ms=5)
        ax.set(xlabel="redshift z", ylabel=f"clean σ(D_V)/D_V, {exposure} (%)",
               title="(c) Clean uncertainty of D_V")
        for ax in axes:
            _tidy(ax)
        fig.suptitle(f"RFIsher channel table: one RadioFisher forecast per 6 MHz channel, flat additive DTV power, "
                     f"{hours:,.0f} retained hours, D_V ({table['inputs']['cosmology']})", x=0.01, ha="left", fontsize=13,
                     fontweight="bold")
        path = out / "summary.png"
        fig.savefig(path, dpi=110)
        plt.close(fig)
    return path


def draw_all(table, out, channels=None) -> list[Path]:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    paths = [summary(table, out)]
    for row in table["channels"]:
        if channels is None or row["channel"] in channels:
            paths.append(plate(row, out, table["inputs"]["retained_hours"]))
    return paths


def overview_figure(ref: dict, out) -> Path:
    """The CHIME Overview forecast as published (15 bins) and with 6 MHz bins over the DTV range."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    panels = (("(a) As in the Overview: 15 bins", ref["overview_bins"], (0.75, 2.55)),
              ("(b) 6 MHz bins over the DTV range (channels 14 to 37)", ref["channels"], (1.30, 2.03)))
    with plt.rc_context(STYLE):
        fig, axes = plt.subplots(1, 2, figsize=(15, 5.4), sharey=True, constrained_layout=True)
        for ax, (title, fc, xlim) in zip(axes, panels):
            zc = [b["z_center"] for b in fc["bins"]]
            ax.errorbar(zc, np.ones(len(zc)), yerr=fc["sigma_dv"], fmt="none", capsize=3, color=LINE, lw=1.6)
            ax.set(xlim=xlim, ylim=(0.982, 1.018), xlabel="redshift z", title=title)
            top = ax.secondary_xaxis("top", functions=(lambda z: NU21_MHZ / np.maximum(1 + np.asarray(z, float), 1e-9),
                                                       lambda nu: NU21_MHZ / np.maximum(np.asarray(nu, float), 1e-9) - 1))
            top.set_xlabel("frequency (MHz)")
            top.tick_params(colors=MUTED)
            _tidy(ax)
        axes[0].set_ylabel("D_V / D_V(fiducial)")
        label = COSMOLOGY_LABELS.get(ref["cosmology"], ref["cosmology"])
        fig.suptitle(f"CHIME Overview forecast, one clean year ({label}, CHIME, {inputs.RETAINED_HOURS:,.0f} h)",
                     x=0.01, ha="left", fontsize=13, fontweight="bold")
        path = out / "overview_reference.png"
        fig.savefig(path, dpi=110)
        plt.close(fig)
    return path
