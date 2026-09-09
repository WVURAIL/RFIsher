#!/usr/bin/env python3
"""Render two presentation-only pages from the frozen channel29 comparison."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import numpy as np

BLUE = "#236CA3"
GOLD = "#B98718"
INK = "#202F3C"
MUTED = "#596876"
LIGHT = "#E7ECF0"
TEAL = "#498583"
PERCENTS = (25, 50, 75, 90)
MARKERS = ("^", "s", "D", "v")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def finite(value):
    return value is not None and np.isfinite(value)


def compact(value, digits=2):
    return f"{value:.{digits}f}" if finite(value) else "undefined"


def page(title, subtitle, number):
    fig = plt.figure(figsize=(11.7, 8.3), facecolor="white")
    fig.text(0.065, 0.965, "RETROSPECTIVE ARCHIVE DIAGNOSTIC", color=MUTED,
             size=9, weight="bold", va="top")
    fig.text(0.065, 0.925, title, color=INK, size=20, weight="bold", va="top")
    fig.text(0.065, 0.878, subtitle, color=MUTED, size=9.5, va="top")
    fig.text(0.065, 0.036,
             "Previously inspected archive; no new holdout, physical residual bound, calibrated floor or accepted policy.",
             color=MUTED, size=8.2, va="bottom")
    fig.text(0.935, 0.036, f"{number} / 2", ha="right", color=MUTED, size=8.2)
    return fig


def style(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.grid(axis="y", alpha=0.2, color=MUTED, which="major")
    ax.set_axisbelow(True)
    ax.xaxis.label.set_color(INK)
    ax.yaxis.label.set_color(INK)


def cell(policy, floor):
    if policy["status"] == "unavailable":
        return "unavailable threshold"
    eva = policy["evaluation"]
    if eva["kept"] == 0:
        return "0 kept; mean/cost undefined"
    return (f"{100 * eva['retention']:.1f}% | "
            f"{eva['allowance'] / floor:.2f}x | "
            f"{eva['mask_only_cost_restore_one_retained_year']:.2f}x")


def draw_table(ax, rows, columns, *, widths=None, size=8.6):
    ax.axis("off")
    table = ax.table(cellText=rows, colLabels=columns, cellLoc="center",
                     colLoc="center", loc="upper left", bbox=[0, 0, 1, 1],
                     colWidths=widths)
    table.auto_set_font_size(False)
    table.set_fontsize(size)
    for (row, col), item in table.get_celld().items():
        item.set_edgecolor("white")
        item.set_linewidth(1.2)
        item.PAD = 0.07
        if row == 0:
            item.set_facecolor(INK)
            item.set_text_props(color="white", weight="bold")
        else:
            item.set_facecolor("#F1F4F6" if row % 2 else "#E7EDF1")
            item.set_text_props(color=INK)
            if col == 0:
                item.set_text_props(weight="bold")
    return table


def tradeoffs(plan, policies):
    floor = float(plan["floor_linear"])
    ranks = list(plan["ranks"])
    by_id = {p["id"]: p for p in policies}
    fig = page("Channel 29: fine and coarse masking tradeoffs",
               f"Same chronological blocks: {plan['calibration_frames']:,} calibration frames and "
               f"{plan['evaluation_frames']:,} evaluation frames. All 21 fixed policies are reported.", 1)
    left = fig.add_axes([0.085, 0.485, 0.43, 0.30])
    right = fig.add_axes([0.605, 0.485, 0.33, 0.30])
    for ax in (left, right):
        style(ax)
        ax.set_xlim(-2, 104)
        ax.set_yscale("log")
        ax.axvline(25, color=MUTED, ls="--", lw=1, zorder=0)
        ax.set_xlabel("Evaluation frames retained (%)", fontsize=9)
    left.set_ylabel("Assigned kept-set mean / original floor", fontsize=9)
    right.set_ylabel("Mask-only time factor", fontsize=9)
    left.set_title("Same coarse-derived residual accounting", loc="left", size=10, weight="bold", pad=9)
    right.set_title("Time to restore retained exposure", loc="left", size=10, weight="bold", pad=9)
    left.axhline(1, color=MUTED, ls=":", lw=1.2)
    left.text(0.02, 0.045, "Original stated floor = 1x", transform=left.transAxes,
              size=8, color=MUTED, bbox={"facecolor":"white", "edgecolor":"none", "alpha":0.85, "pad":2})
    groups = [("coarse", None, BLUE, "o")] + [
        ("fine", rank, GOLD, marker) for rank, marker in zip(ranks, MARKERS)]
    all_y, all_cost = [], []
    for kind, rank, color, marker in groups:
        members = [p for p in policies if p["kind"] == kind and p["rank"] == rank]
        members.sort(key=lambda p: p["percent"])
        usable = [p for p in members if p["status"] != "unavailable" and p["evaluation"]["kept"]]
        x = [100*p["evaluation"]["retention"] for p in usable]
        y = [p["evaluation"]["allowance"]/floor for p in usable]
        cost = [p["evaluation"]["mask_only_cost_restore_one_retained_year"] for p in usable]
        all_y.extend(y)
        all_cost.extend(cost)
        for ax, vals in ((left, y), (right, cost)):
            ax.plot(x, vals, color=color, lw=0.8, alpha=0.4, zorder=2)
            ax.scatter(x, vals, c=color, marker=marker, s=42,
                       edgecolors="white", linewidths=0.45, zorder=3)
    keep = by_id["keep_all"]["evaluation"]
    for ax, value in ((left, keep["allowance"]/floor),
                      (right, keep["mask_only_cost_restore_one_retained_year"])):
        ax.scatter([100], [value], marker="*", s=110, color=INK, zorder=4)
    all_y.append(keep["allowance"]/floor)
    all_cost.append(keep["mask_only_cost_restore_one_retained_year"])
    left.set_ylim(0.82, max(all_y)*1.65)
    right.set_ylim(0.85, max(all_cost)*1.32)
    handles = [Line2D([], [], marker="o", ls="", color=BLUE, label="Coarse")]
    handles += [Line2D([], [], marker=marker, ls="", color=GOLD,
                       label=f"Fine rank {rank}") for rank, marker in zip(ranks, MARKERS)]
    handles += [Line2D([], [], marker="*", ls="", color=INK, markersize=9, label="Keep all")]
    fig.legend(handles=handles, loc="center", bbox_to_anchor=(0.5, 0.818),
               ncol=6, frameon=False, fontsize=8.5, handletextpad=0.4, columnspacing=1.4)
    fig.text(0.085, 0.402,
             "Dashed line: provisional 25% planning retention. Points may overlap; the table preserves every setting.",
             size=8.4, color=MUTED)
    fig.text(0.065, 0.355,
             "Each cell: evaluation retention | assigned mean / floor | mask-only time factor", size=10, color=INK, weight="bold")
    rows = [["Coarse"]+[cell(by_id[f"coarse_q{q}"], floor) for q in PERCENTS]]
    rows += [[f"Fine rank {rank}"]+[cell(by_id[f"fine_r{rank}_q{q}"], floor) for q in PERCENTS] for rank in ranks]
    table_ax = fig.add_axes([0.065, 0.170, 0.87, 0.161])
    draw_table(table_ax, rows, ["Policy", "q25: nominal 25%", "q50: nominal 50%",
                               "q75: nominal 75%", "q90: nominal 90%"],
               widths=[0.15,0.2125,0.2125,0.2125,0.2125], size=8.2)
    fig.text(0.065, 0.14, f"Keep all: {cell(by_id['keep_all'], floor)}. "
             f"Original floor = {floor:.6g} (linear shelf / thermal units).", color=INK, size=8.7)
    fig.text(0.065, 0.103,
             "q labels specify calibration quantiles, not guaranteed evaluation retention. Cost restores one retained on-sky year;\n"
             "it does not refit noise covariance or cleaner transfer. No hypothetical filter suppression is credited on this page.",
             color=MUTED, size=8.2, linespacing=1.35)
    return fig


def overlap_page(plan, policies, overlaps):
    ranks = list(plan["ranks"])
    by_id = {p["id"]:p for p in policies}
    selected = {x["policy"]:x for x in overlaps if x["block"] == "evaluation"}
    coarse = by_id["coarse_q50"]["evaluation"]
    n = int(plan["evaluation_frames"])
    fig = page("Do fine and coarse policies keep the same frames?",
               f"Evaluation block, nominal q50 policies. Coarse q50 keeps {coarse['kept']:,} / {n:,} frames "
               f"({100*coarse['retention']:.2f}%).", 2)
    ax = fig.add_axes([0.165, 0.57, 0.77, 0.21])
    style(ax)
    ax.grid(axis="y", visible=False)
    ax.set_xlim(0, 100)
    ax.set_xlabel("Fraction of the same evaluation frames (%)", fontsize=9)
    ax.set_yticks(range(len(ranks)), [f"Fine rank {r}" for r in ranks])
    ax.invert_yaxis()
    pieces = [("both_kept", "Both keep", TEAL),
              ("left_only_kept", "Coarse only", BLUE),
              ("right_only_kept", "Fine only", GOLD),
              ("both_dropped", "Both drop", "#D7DFE5")]
    offsets = np.zeros(len(ranks))
    rows = [selected[f"fine_r{rank}_q50"] for rank in ranks]
    for key, label, color in pieces:
        values = np.array([row[key]/n*100 for row in rows])
        ax.barh(range(len(ranks)), values, left=offsets, height=0.62,
                color=color, edgecolor="white", linewidth=0.7)
        for i, width in enumerate(values):
            if width >= 8:
                ax.text(offsets[i]+width/2, i, f"{width:.1f}%", ha="center", va="center",
                        fontsize=8.2, color=INK if key == "both_dropped" else "white")
        offsets += values
    fig.legend(handles=[Patch(facecolor=c, label=l) for _,l,c in pieces],
               loc="center", bbox_to_anchor=(0.54,0.814), ncol=4, frameon=False,
               fontsize=9, columnspacing=2)
    table_rows = []
    for rank, row in zip(ranks,rows):
        p=by_id[f"fine_r{rank}_q50"]
        status = " (unavailable)" if p["status"] == "unavailable" else ""
        table_rows.append([f"Fine {rank}{status}", f"{row['both_kept']:,}",
                           f"{row['left_only_kept']:,}", f"{row['right_only_kept']:,}",
                           f"{row['both_dropped']:,}",
                           f"{100*row['kept_jaccard']:.1f}%" if row['kept_jaccard'] is not None else "undefined"])
    draw_table(fig.add_axes([0.065,0.365,0.87,0.137]), table_rows,
               ["q50 policy", "Both keep", "Coarse only", "Fine only", "Both drop", "Kept-set Jaccard"],
               widths=[0.17,0.16,0.16,0.16,0.16,0.19], size=9)
    fig.text(0.065,0.332,
             "Jaccard = both-kept / kept-by-either. This is paired frame overlap, not a significance test or independent trials.",
             color=MUTED, size=8.4)
    floor=float(plan["floor_linear"])
    q50_fine=[by_id[f"fine_r{r}_q50"]["evaluation"] for r in ranks]
    available=[v["allowance"]/floor for v in q50_fine if v["kept"]]
    span=(f"{min(available):.2f}x to {max(available):.2f}x" if available else "undefined: no retained fine frames")
    fig.text(0.065,0.277,"How to interpret the accounting",color=INK,size=12,weight="bold")
    fig.text(0.065,0.24,
             f"Coarse q50 assigned mean: {compact(coarse['allowance']/floor if coarse['allowance'] is not None else None)}x the original floor. "
             f"Fine q50 assigned means: {span}.\n"
             "Every mask is priced using the same per-frame coarse-derived shelf assignment and original stated floor.\n"
             "Selecting frames by that same coarse statistic directly favors a lower coarse-derived assigned mean.\n"
             "This comparison cannot establish which detector leaves less physical interference.",
             size=9.1,color=INK,linespacing=1.6,va="top")
    fig.text(0.065,0.112,
             "A different retained set is a policy difference, not a measured transfer advantage. The failed tighter retained-control\n"
             "bound remains excluded. Physical comparison still needs matched in-band visibilities, reference-quality evidence\n"
             "and injections through the actual cleaner. The no-filter dilation case remains unpriced, with no saved response.",
             size=8.4,color=MUTED,linespacing=1.35,va="top")
    return fig


def main(args):
    for name in ("analysis", "output", "manifest"):
        if not getattr(args,name).is_absolute():
            raise ValueError(f"--{name} must be an absolute path")
    if args.output.exists() or args.manifest.exists():
        raise ValueError("PDF and figure manifest must be new paths")
    paths={name:args.analysis/f"{name}.json" for name in ("plan","results","thresholds","overlaps")}
    plan, results, thresholds, overlaps=(json.loads(paths[name].read_text()) for name in paths)
    if results["plan_sha256"] != sha(paths["plan"]) or results["thresholds_sha256"] != sha(paths["thresholds"]):
        raise ValueError("Frozen result identities do not match")
    if thresholds["plan_sha256"] != sha(paths["plan"]):
        raise ValueError("Threshold plan identity differs")
    policies=results["policies"]
    if len(policies)!=21 or len({p["id"] for p in policies})!=21:
        raise ValueError("Expected all 21 fixed comparison policies")
    expected={"keep_all"}|{f"coarse_q{q}" for q in PERCENTS}|{
        f"fine_r{rank}_q{q}" for rank in plan["ranks"] for q in PERCENTS}
    if {p["id"] for p in policies} != expected or len(plan["ranks"])!=4:
        raise ValueError("Policy family differs")
    for row in overlaps:
        if row["block"]=="evaluation" and sum(row[k] for k in ("both_kept","left_only_kept","right_only_kept","both_dropped"))!=plan["evaluation_frames"]:
            raise ValueError("Paired overlap denominator differs")
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.manifest.parent.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({"font.family":"DejaVu Sans","pdf.fonttype":42,
                         "axes.titlecolor":INK,"axes.labelsize":10})
    with PdfPages(args.output, metadata={"Title":"Channel 29 fine/coarse policy comparison",
                                        "Author":"RFIsher", "Subject":"Retrospective archive diagnostic"}) as pdf:
        for fig in (tradeoffs(plan,policies),overlap_page(plan,policies,overlaps)):
            pdf.savefig(fig)
            plt.close(fig)
    manifest={"schema":"channel29-policy-figures-v1", "created_utc":datetime.now(timezone.utc).isoformat(),
              "pages":2, "policy_count":21, "presentation_only":True,
              "no_filter_suppression_credited":True,"physical_recovery_certified":False,
              "source_files":{str(p):sha(p) for p in list(paths.values())+[args.analysis/'comparison.csv',Path(__file__).resolve()]},
              "output_pdf":str(args.output),"output_pdf_sha256":sha(args.output),
              "visual_quality_assurance":"Pending external render and page inspection."}
    args.manifest.write_text(json.dumps(manifest,indent=2)+"\n")
    print(json.dumps({"pdf":str(args.output),"pages":2,"sha256":sha(args.output)},indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--manifest",type=Path,required=True)
    main(parser.parse_args())
