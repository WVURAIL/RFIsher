#!/usr/bin/env python3
"""Dissertation figures owned by RFIsher.

These render the tolerance-layer dissertation figures -- the observing-time
versus masking curves, the channel-33 residual-policy comparison, the
convergence panels, and the two-walls plane -- in the dissertation's exact
style (Latin Modern through LaTeX, the WVU semantic palette, pinned PDF
metadata). The dissertation bundle vendors the resulting PDFs; this module
and the tables under ``data/`` are their editable source.

One table is still a legacy bridge recovered from the published artwork
(see data/README.md): the convergence family. The two-walls sweep is
regenerated directly from the survey products by make_two_walls.py (bridge
retired); the convergence family's direct regeneration is the agreed
replacement path, and until then its bridge status is recorded, not hidden.

    python3 figures.py --out out/
"""
from __future__ import annotations

import argparse
import contextlib
import csv
from collections import defaultdict
import hashlib
from pathlib import Path
import string

import numpy as np
import matplotlib.pyplot as plt

import style

DATA = Path(__file__).resolve().parent / "data"


def _stable_subset_prefix(charset) -> str:
    """Return a repeatable PDF font-subset tag."""
    glyphs = "\0".join(sorted(str(name) for name in charset))
    value = int.from_bytes(
        hashlib.sha256(glyphs.encode("utf-8")).digest()[:8], "big")
    letters = []
    for _ in range(6):
        value, index = divmod(value, 26)
        letters.append(string.ascii_uppercase[index])
    return "".join(letters) + "+"


@contextlib.contextmanager
def _stable_pdf_subset_tags():
    """Use content-based tags where Matplotlib exposes its PDF hook."""
    from matplotlib.backends.backend_pdf import PdfFile

    original = vars(PdfFile).get("_get_subset_prefix")
    if original is None:
        yield
        return
    PdfFile._get_subset_prefix = staticmethod(_stable_subset_prefix)
    try:
        yield
    finally:
        PdfFile._get_subset_prefix = original


def _save_pdf(fig, path: Path, *, title: str) -> Path:
    with _stable_pdf_subset_tags():
        return style.save(fig, path, title=title)


def read_csv(name: str):
    with (DATA / name).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fig_bao_time_vs_masking(out: Path) -> Path:
    rows=read_csv("bao_time_vs_masking.csv")
    labels={"dilation":r"$\sigma(D_A)\leq2\%$ in the $z=1.40$--$1.50$ bin",
            "bin_amplitude":r"BAO amplitude $S/N=5$ in the $z=1.40$--$1.50$ bin",
            "survey_amplitude":r"BAO amplitude $S/N=5$, full survey"}
    colors={"dilation":style.MEASURED,"bin_amplitude":style.MODEL,"survey_amplitude":style.CONDITIONAL}
    fig,ax=plt.subplots(figsize=(style.TEXT_WIDTH,3.35))
    for key in ("dilation","bin_amplitude","survey_amplitude"):
        sub=[r for r in rows if r["series"]==key]
        x=np.array([float(r["masked_fraction"]) for r in sub]); y=np.array([float(r["time_year"]) for r in sub]); o=np.argsort(x)
        ax.plot(100*x[o],y[o],color=colors[key],label=labels[key])
        ax.scatter([0],[y[o][0]],color=colors[key],s=20,zorder=4,edgecolor="white",linewidth=.5)
    ax.scatter([50],[np.interp(.5,np.array([float(r["masked_fraction"]) for r in rows if r["series"]=="dilation"]),
                                  np.array([float(r["time_year"]) for r in rows if r["series"]=="dilation"]))],
               color=style.MEASURED,s=24,zorder=4,edgecolor="white",linewidth=.5)
    ax.text(2,.36,"pilot-proxy-derived\nsurvey point",fontsize=7.1,color=style.MUTED)
    dil_x=np.array([float(r["masked_fraction"]) for r in rows if r["series"]=="dilation"])
    dil_y=np.array([float(r["time_year"]) for r in rows if r["series"]=="dilation"])
    dil_o=np.argsort(dil_x)
    ax.annotate(r"50\% masked",xy=(50,np.interp(.5,dil_x[dil_o],dil_y[dil_o])),xytext=(54,.95),fontsize=7.0,color=style.MUTED,
                arrowprops=dict(arrowstyle="->",color=style.MUTED,lw=.7))
    ax.set_yscale("log"); ax.set_xlim(-5,102); ax.set_ylim(.018,20)
    ax.set_xlabel(r"Masked fraction of the DTV band [\%]"); ax.set_ylabel(r"Required observing time [on-sky yr]")
    style.clean_axes(ax); ax.legend(loc="upper left",fontsize=7.2)
    ax.set_title(r"Noise tolerance: observing time to reach BAO targets versus uniform DTV masking",pad=5)
    return _save_pdf(fig,out/"fig_bao_time_vs_masking.pdf",title="BAO observing time versus DTV masking")


def fig_bao_the_case(out: Path) -> Path:
    rows=read_csv("bao_policy_case.csv")
    rtol=float(rows[0]["residual_tolerance"])
    channel=int(rows[0]["channel"])
    tau=float(rows[0]["correlation_time_limit_minutes"])
    display={
        "keep_everything":r"keep everything",
        "mad_1p8":r"MAD $1.8\times$ (incumbent)",
        "spectral_kurtosis":r"spectral kurtosis (incumbent)",
        "pilot_proxy":r"pilot proxy",
    }
    colors={
        "keep_everything":style.MEASURED,
        "mad_1p8":style.PURPLE,
        "spectral_kurtosis":style.CONDITIONAL,
        "pilot_proxy":style.MODEL,
    }
    methods=[
        (display[r["policy_key"]],float(r["residual_multiple"]),float(r["time_multiple"]),colors[r["policy_key"]])
        for r in rows
    ]
    fig,ax=plt.subplots(figsize=(style.TEXT_WIDTH,3.0))
    y=np.arange(len(methods))[::-1]+1
    for yy,(name,mult,time,c) in zip(y,methods):
        x=mult*rtol
        ax.hlines(yy,rtol,x,color=c,alpha=.35,lw=1.1); ax.scatter([x],[yy],s=28,color=c,edgecolor="white",linewidth=.6,zorder=4)
        ax.text(rtol*.78,yy,name,ha="right",va="center",fontsize=7.2,color=style.MUTED)
        ax.text(x*1.08,yy+.16,rf"${mult:,.0f}\times$ over",fontsize=7.0,color=c)
        ax.text(1.15e1,yy,rf"${time:.1f}\times$ time",ha="right",va="center",fontsize=7.1,color=style.MUTED)
    ax.axvline(rtol,color=style.INK,lw=1.0); ax.text(rtol*.94,4.52,r"bias tolerance" + "\n" + rf"$r_{{\rm tol}}={rtol/1e-3:.1f}\times10^{{-3}}$",ha="right",fontsize=6.9)
    ax.scatter([rtol*.60],[0],marker="<",s=35,color=style.MEASURED); ax.text(rtol*.50,0,r"excise the channel",ha="right",va="center",fontsize=7.2,color=style.MUTED); ax.text(rtol*.55,.25,r"no residual",ha="center",fontsize=6.8,color=style.MEASURED)
    ax.set_xscale("log"); ax.set_xlim(7e-4,15); ax.set_ylim(-.55,4.8); ax.set_yticks([])
    ax.set_xlabel(r"Residual DTV power surviving to the power spectrum, in units of system noise")
    style.clean_axes(ax,grid="x"); ax.set_title(rf"Channel {channel}: full residual chain at the measured floor and $\tau_c\leq{tau:g}$ min",pad=5)
    return _save_pdf(fig,out/"fig_bao_the_case.pdf",title=f"Channel {channel} residual-policy comparison")


def fig_bao_convergence(out: Path) -> Path:
    rows=read_csv("bao_convergence.csv")
    fig,axes=plt.subplots(1,2,figsize=(style.TEXT_WIDTH,2.75),constrained_layout=True)
    sub=[r for r in rows if r["panel"]=="clean_sigma"]
    x=np.array([float(r["time_year"]) for r in sub]); y=np.array([float(r["value"]) for r in sub]); o=np.argsort(x)
    ax=axes[0]; ax.plot(x[o],y[o],color=style.INK)
    ax.annotate(r"falls $20\times$" + "\n" + r"over this range",xy=(2,np.interp(2,x[o],y[o])),xytext=(2.9,2.5e-3),fontsize=7.0,color=style.MUTED,
                arrowprops=dict(arrowstyle="->",color=style.MUTED,lw=.7))
    ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlabel(r"Integration time [on-sky yr]"); ax.set_ylabel(r"$\sigma(f\sigma_8)$, clean survey")
    style.clean_axes(ax); style.panel_label(ax,"a"); ax.set_title(r"integration does what it should",pad=4)
    names={"keep_everything":r"keep everything","mad":r"MAD $1.8\times$","spectral_kurtosis":r"spectral kurtosis","pilot_proxy":r"pilot proxy"}
    colors={"keep_everything":style.MEASURED,"mad":style.PURPLE,"spectral_kurtosis":style.CONDITIONAL,"pilot_proxy":style.MODEL}
    ax=axes[1]
    for key in names:
        sub=[r for r in rows if r["panel"]=="bias_sigma" and r["series"]==key]
        xx=np.array([float(r["time_year"]) for r in sub]); yy=np.array([float(r["value"]) for r in sub]); o=np.argsort(xx)
        ax.plot(xx[o],yy[o],color=colors[key],label=names[key])
    ax.axhline(1,color=style.INK,lw=1.0); ax.text(.065,1.2,r"$\zeta=1$, published criterion",fontsize=6.9)
    ax.text(9,28,r"best of the four," + "\n" + r"still $24\times$ over",fontsize=6.9,color=style.MODEL)
    ax.set_xscale("log"); ax.set_yscale("log"); ax.set_ylim(1e-3,1e6)
    ax.set_xlabel(r"Integration time [on-sky yr]"); ax.set_ylabel(r"$|\Delta f\sigma_8|/\sigma(f\sigma_8)$")
    style.clean_axes(ax); style.panel_label(ax,"b"); ax.set_title(r"noise-normalized residual family",pad=4); ax.legend(loc="lower left",fontsize=6.8)
    return _save_pdf(fig,out/"fig_bao_convergence.pdf",title="Time scaling under the current residual normalization")


def fig_bao_two_walls(out: Path) -> Path:
    rows=read_csv("bao_two_walls.csv"); groups=defaultdict(list)
    for r in rows: groups[int(r["channel"])].append(r)
    fig,ax=plt.subplots(figsize=(style.TEXT_WIDTH,4.15))
    ax.axhspan(2e-3,.10,facecolor=style.LIGHT_RED,alpha=.75,zorder=0)
    ax.axhspan(.10,1,facecolor=style.LIGHT_GRAY,alpha=.65,zorder=0)
    ax.axhline(1,color=style.INK,lw=1.05); ax.axvline(1,color=style.INK,lw=1.05)
    ax.text(.02,1.25,r"bias wall: kept data too dirty",fontsize=7.0,color=style.INK)
    ax.text(.02,.14,r"dilation-tolerable screening region",fontsize=6.8,color=style.MUTED)
    ax.text(.02,.035,r"$f\sigma_8$ wall (bin-dependent)",fontsize=6.8,color=style.FAILURE)
    ax.text(1.012,.0045,r"occupancy wall",rotation=90,va="bottom",fontsize=6.8,color=style.INK)
    # Story channels keep their role colors; every other channel draws gray.
    # Dashing follows the table's own evidence column (stated floors dash),
    # and only story channels and channels entering the tolerable box are
    # labelled -- 23 curves cannot all carry endpoint labels.
    colors={29:style.GOLD,31:style.PENDING,32:style.MEASURED,33:style.MODEL,35:style.CONDITIONAL}
    for ch in sorted(groups):
        vals=sorted(groups[ch],key=lambda r:int(r["order"])); x=np.array([float(r["masked_fraction"]) for r in vals]); y=np.clip(np.array([float(r["r_over_rtol"]) for r in vals]),2e-3,5e4)
        bound=(vals[0].get("evidence","measured")=="stated"
               or vals[0].get("tau_bound","0")=="1")
        c=colors.get(ch,style.PENDING); ls=(0,(4,2)) if bound else "-"
        lw=1.35 if ch in colors else 1.05
        ax.plot(x,y,color=c,ls=ls,lw=lw)
        ax.scatter([x[-1]],[y[-1]],s=22 if ch in colors else 12,color=c,edgecolor="white",linewidth=.5,zorder=4)
        if ch in colors or y[-1]<1.0:
            dx=.012 if x[-1]<.96 else .008
            ax.text(min(x[-1]+dx,1.035),y[-1]*1.12,rf"ch{ch}",fontsize=6.6,color=c,ha="left")
    era = next(r for r in read_csv("bao_era_points.csv")
               if int(r["channel"]) == 35)
    era_point = (float(era["masked_fraction"]), float(era["r_over_rtol"]))
    ax.scatter([era_point[0]],[era_point[1]],marker="x",s=35,color=style.CONDITIONAL,lw=1.2,zorder=5)
    ax.annotate(rf"ch35 after sign-on: calibrated endpoint remains ${era_point[1]:.0f}\times$ above the bias wall",xy=era_point,xytext=(.30,.018),fontsize=6.8,color=style.CONDITIONAL,
                arrowprops=dict(arrowstyle="->",color=style.CONDITIONAL,lw=.7))
    ax.set_yscale("log"); ax.set_xlim(0,1.045); ax.set_ylim(2e-3,5e4)
    ax.set_xlabel(r"Masked fraction of observing time, $f$"); ax.set_ylabel(r"Residual over tolerance, $r_{\rm proxy}/r_{\rm tol}$")
    style.clean_axes(ax); ax.set_title(r"Two ways to fail, one plane: every threshold is a point and every channel a curve",pad=5)
    ax.text(.5,-.16,r"Solid curves: measured floor and correlation information. Dashed curves: stated floor or bounded $\tau_c$.",transform=ax.transAxes,ha="center",fontsize=6.8,color=style.MUTED)
    return _save_pdf(fig,out/"fig_bao_two_walls.pdf",title="Bias and occupancy walls across threshold sweeps")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path,
                    default=Path(__file__).resolve().parent / "out")
    args = ap.parse_args(argv)
    style.configure(require_tex=True)
    outputs = [
        fig_bao_time_vs_masking(args.out),
        fig_bao_the_case(args.out),
        fig_bao_convergence(args.out),
        fig_bao_two_walls(args.out),
    ]
    for path in outputs:
        print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
