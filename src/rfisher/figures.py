"""Per-channel plates and the all-channel summary, drawn from a channel table.

Each plate answers two questions for one channel:
  (a) where in Fourier space the residual sits, at the tolerated strength;
  (b) how the bias of D_V grows with the residual's strength, and where it
      reaches the clean sigma.
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from . import forecast, inputs, residual
from .bands import Band

INK, MUTED, GRID, SURF = "#1c2126", "#5a6168", "#e4e6e2", "#ffffff"
LINE = "#2a78d6"
GRID_DARK = "#9aa0a6"
NU21 = 1420.406
COSMOLOGY_LABELS = {"planck2018": "Planck 2018"}
STYLE = {"font.size": 10.5, "axes.edgecolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED,
         "axes.labelcolor": INK, "figure.facecolor": SURF, "axes.facecolor": SURF, "text.color": INK,
         "axes.titlesize": 11, "axes.titleweight": "bold", "axes.titlelocation": "left"}


def _tidy(ax):
    ax.grid(True, color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


def _band(row) -> Band:
    return Band(row["channel"], row["low_mhz"], row["high_mhz"], row["role"])


def residual_map(ax, row, shared):
    """dP / C_N at a = a_tol over (k_perp, k_par), with the cuts RadioFisher applies."""
    p = forecast.prepare(_band(row), *shared)
    g = p["geometry"]
    kperp = np.logspace(-2.3, 0, 300)
    kpar = np.logspace(-3, 0, 300)
    KP, KL = np.meshgrid(kperp, kpar)
    kw = residual.wedge_kpar(KP, g)
    ratio = row["a_tol"] * g["n_nu"] * residual.n_meas(KP, g) * np.pi / (g["L"] * kw)
    ratio = np.where(KL <= kw, ratio, np.nan)
    ratio = np.where(np.hypot(KP, KL) > p["knl"], np.nan, ratio)
    ratio = np.where(KL < p["kfg"], np.nan, ratio)
    with np.errstate(divide="ignore"):
        im = ax.pcolormesh(kperp, kpar, np.log10(ratio), cmap="Blues", vmin=-6, vmax=0, shading="auto")
    ax.plot(kperp, residual.wedge_kpar(kperp, g), color=INK, lw=1.2)
    ax.axhline(p["kfg"], color=MUTED, ls="--", lw=1)
    t = np.linspace(0, np.pi / 2, 200)
    ax.plot(p["knl"] * np.cos(t), p["knl"] * np.sin(t), color=MUTED, ls=":", lw=1.2)
    ax.text(0.35, p["kfg"] * 1.25, "foreground cut", color=MUTED, fontsize=8.5, ha="center")
    ax.text(0.011, residual.wedge_kpar(0.011, g) * 1.3, "wedge edge", color=INK, fontsize=8.5)
    ax.text(p["knl"] * 1.08, p["knl"] * 0.45, "nonlinear\ncut", color=MUTED, fontsize=8.5)
    ax.text(0.011, p["kfg"] * 3, "residual inside the wedge", color="white", fontsize=8.5)
    ax.set(xscale="log", yscale="log", xlim=(kperp[0], 1), ylim=(kpar[0], 1),
           xlabel="k⊥ (Mpc⁻¹)", ylabel="k∥ (Mpc⁻¹)",
           title="(a) Where the residual sits, at the tolerated strength")
    cb = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.03)
    cb.set_label("log₁₀ residual ÷ noise power", color=INK)
    cb.outline.set_edgecolor(MUTED)


def bias_line(ax, row):
    """|bias| / sigma of D_V = a |response_dv|, against strength a."""
    a = np.logspace(-8, -1, 200)
    q = row["response_dv"]
    ax.plot(a, a * abs(q), color=LINE, lw=2.2,
            label=f"D_V: bias {'+' if q > 0 else '−'}{abs(q):,.0f} σ per unit a")
    ax.axhline(1, color=INK, ls="--", lw=1.1)
    ax.axvline(row["a_tol"], color=MUTED, lw=1)
    ax.plot(row["a_tol"], 1, "o", color=INK, ms=6)
    ax.annotate(f"a_tol = {row['a_tol']:.2g}", (row["a_tol"], 1), xytext=(8, -22), textcoords="offset points",
                fontsize=9.5)
    ax.text(a[0] * 1.6, 1.35, "bias = σ", fontsize=9)
    ax.text(0.97, 0.04, f"σ(D_V)/D_V = {100 * row['sigma_dv']:.2f}%, one year, clean",
            transform=ax.transAxes, ha="right", fontsize=9, color=MUTED)
    ax.set(xscale="log", yscale="log", xlim=(a[0], a[-1]), ylim=(1e-5, 1e3),
           xlabel="residual strength a", ylabel="|bias| ÷ σ of D_V",
           title="(b) Bias grows in proportion to strength")
    ax.legend(frameon=False, fontsize=9, loc="upper left")


def plate(row, out: Path, shared) -> Path:
    with plt.rc_context(STYLE):
        fig, axes = plt.subplots(1, 2, figsize=(13, 5.4), constrained_layout=True)
        residual_map(axes[0], row, shared)
        bias_line(axes[1], row)
        _tidy(axes[1])
        kind = "control channel (no DTV)" if row["role"] == "control" else "DTV channel"
        fig.suptitle(f"Channel {row['channel']}  ·  {row['low_mhz']:.0f}–{row['high_mhz']:.0f} MHz  ·  "
                     f"z = {row['z_center']:.3f}  ·  {kind}", x=0.01, ha="left", fontsize=13, fontweight="bold")
        path = out / f"channel_{row['channel']:02d}.png"
        fig.savefig(path, dpi=110)
        plt.close(fig)
    return path


def summary(table, out: Path) -> Path:
    rows = sorted(table["channels"], key=lambda r: r["channel"])
    ch = np.array([r["channel"] for r in rows])
    z = np.array([r["z_center"] for r in rows])
    with plt.rc_context(STYLE):
        fig, axes = plt.subplots(1, 3, figsize=(17, 5), constrained_layout=True)
        ax = axes[0]
        ax.plot(ch, [r["a_tol"] for r in rows], "o", color=LINE, ms=8)
        ax.set(yscale="log", xlabel="channel", ylabel="tolerance a_tol", xticks=ch[::2],
               title="(a) Tolerated residual strength per channel")
        ax = axes[1]
        ax.plot(z, [r["response_dv"] for r in rows], "o-", color=LINE, lw=1.6, ms=5)
        ax.axhline(0, color=MUTED, lw=1)
        ax.set(xlabel="redshift z", ylabel="bias ÷ σ of D_V per unit strength",
               title="(b) Response of D_V (signed)")
        ax = axes[2]
        ax.plot(z, [100 * r["sigma_dv"] for r in rows], "o-", color=LINE, lw=1.6, ms=5)
        ax.set(xlabel="redshift z", ylabel="clean σ(D_V)/D_V, one year (%)",
               title="(c) Clean uncertainty of D_V")
        for ax in axes:
            _tidy(ax)
        fig.suptitle(f"RFIsher channel table: one RadioFisher forecast per 6 MHz channel, coherent DTV residual, "
                     f"one retained year, D_V ({table['inputs']['cosmology']})", x=0.01, ha="left", fontsize=13,
                     fontweight="bold")
        path = out / "summary.png"
        fig.savefig(path, dpi=110)
        plt.close(fig)
    return path


def draw_all(table, out, channels=None) -> list[Path]:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    cosmo = inputs.cosmology(table["inputs"]["cosmology"])
    shared = (cosmo, inputs.experiment(), inputs.background(cosmo))
    paths = [summary(table, out)]
    for row in table["channels"]:
        if channels is None or row["channel"] in channels:
            paths.append(plate(row, out, shared))
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
            top = ax.secondary_xaxis("top", functions=(lambda z: NU21 / np.maximum(1 + np.asarray(z, float), 1e-9),
                                                       lambda nu: NU21 / np.maximum(np.asarray(nu, float), 1e-9) - 1))
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


def cosmology_figure(refs: dict, out) -> Path:
    """The 6 MHz forecast in two cosmologies: the error bars side by side, and their ratio."""
    out = Path(out)
    (base, a), (new, b) = list(refs.items())
    za = np.array([r["z_center"] for r in a["channels"]["bins"]])
    sa, sb = np.array(a["channels"]["sigma_dv"]), np.array(b["channels"]["sigma_dv"])
    with plt.rc_context(STYLE):
        fig, axes = plt.subplots(1, 2, figsize=(15, 5.4), constrained_layout=True)
        ax = axes[0]
        ax.errorbar(za - 0.004, np.ones(len(za)), yerr=sa, fmt="none", capsize=3, color=GRID_DARK, lw=1.6, label=base)
        ax.errorbar(za + 0.004, np.ones(len(za)), yerr=sb, fmt="none", capsize=3, color=LINE, lw=1.6, label=new)
        ax.set(xlim=(1.30, 2.03), ylim=(0.982, 1.018), xlabel="redshift z", ylabel="D_V / D_V(fiducial)",
               title="(a) 6 MHz bins over the DTV range, one clean year")
        ax.legend(frameon=False, loc="upper left")
        ax = axes[1]
        ax.plot(za, sb / sa, "o-", color=LINE, lw=1.6, ms=5)
        ax.axhline(1, color=MUTED, lw=1)
        ax.set(xlim=(1.30, 2.03), xlabel="redshift z", ylabel=f"σ(D_V) {new} ÷ σ(D_V) {base}",
               title="(b) Change in the error per channel")
        for ax in axes:
            top = ax.secondary_xaxis("top", functions=(lambda z: NU21 / np.maximum(1 + np.asarray(z, float), 1e-9),
                                                       lambda nu: NU21 / np.maximum(np.asarray(nu, float), 1e-9) - 1))
            top.set_xlabel("frequency (MHz)")
            top.tick_params(colors=MUTED)
            _tidy(ax)
        fig.suptitle(f"CHIME Overview forecast in 6 MHz bins: {base} and {new}", x=0.01, ha="left",
                     fontsize=13, fontweight="bold")
        path = out / "overview_cosmology.png"
        fig.savefig(path, dpi=110)
        plt.close(fig)
    return path
