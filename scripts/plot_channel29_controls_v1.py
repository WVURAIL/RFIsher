#!/usr/bin/env python3
"""Render verified frozen channel29 control results without fitting or selecting."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np

SPEC = importlib.util.spec_from_file_location("_channel29_runner", Path(__file__).with_name("calibrate_channel29_controls_v1.py"))
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)
from rfisher_results.validation.channel29_controls import normalized_ratio

BLUE, ORANGE, RED, GREY = "#2476a8", "#d68424", "#b53e4b", "#626d77"
LABELS = {"null": "Null", "intermittent_m50": "25% duty\n-50 dB",
          "intermittent_m44": "25% duty\n-44 dB", "intermittent_m10": "25% duty\n-10 dB",
          "variable_50pct": "50% duty\nvariable power"}
ORDER = list(LABELS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--pdf", type=Path, required=True)
    args = parser.parse_args()
    release, pdf = args.release.resolve(), args.pdf.resolve()
    plan = runner.load_plan(release)
    receipt = runner.load_receipt(release, plan)
    cal = runner.read(receipt["calibration"]["path"])
    ev = runner.read(release / "evaluation.json")
    stress = runner.read(release / "stress.json")
    # The plot refuses changed source measurements; it does not refit the bound.
    for report in (ev, stress):
        if report["plan_sha256"] != plan["plan_sha256"] or report["receipt_sha256"] != receipt["receipt_sha256"]:
            raise ValueError("report identities differ")
        for path, digest in report["source_shards"].items():
            if runner.sha(release / path) != digest:
                raise ValueError("report source shard changed")
    if pdf.exists():
        raise FileExistsError(pdf)
    pdf.parent.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.labelcolor": "#25333d", "text.color": "#25333d",
                         "axes.titleweight": "bold", "axes.titlesize": 12,
                         "pdf.fonttype": 42, "ps.fonttype": 42})
    upper = cal["absolute_retained_set_upper"]
    floor = runner.FLOOR_LINEAR
    evaluation = ev["evaluation"]
    success = evaluation["successes"]
    lower = evaluation["joint_success_probability_lower"]
    target_met = ev["evaluation_target_demonstrated"]
    with PdfPages(pdf) as pages:
        fig, axes = plt.subplots(2, 1, figsize=(10, 8.2), gridspec_kw={"height_ratios": [1.1, 1]}, sharex=True)
        fig.subplots_adjust(left=.10, right=.97, top=.77, bottom=.23, hspace=.24)
        fig.text(.10, .955, "Channel 29 | Calibration for intermittent signals", fontsize=18, weight="bold")
        fig.text(.10, .916, "Fresh digital controls through the full 2,048-stream packed coarse detector", fontsize=11)
        fig.text(.10, .86, f"Joint evaluation: {success}/100 blocks | 95% lower limit: {lower:.2%} | 95% target: {'met' if target_met else 'not met'}",
                 fontsize=11, color=BLUE if target_met else RED)
        x = np.arange(len(ORDER))
        rows = list(ev["measurements"].values())
        for i, case in enumerate(ORDER):
            truth = np.array([r[case]["truth"] if r[case]["truth"] is not None else np.nan for r in rows])
            retention = np.array([r[case]["retention"] * 100 for r in rows])
            # Deterministic display offsets do not change any calculation.
            jitter = np.linspace(-.18, .18, len(rows))
            axes[0].scatter(i + jitter, truth / 1e-6, s=12, color=BLUE, alpha=.5, linewidth=0)
            axes[1].scatter(i + jitter, retention, s=12, color=BLUE, alpha=.5, linewidth=0)
            axes[0].plot([i-.22, i+.22], [np.nanmedian(truth)/1e-6]*2, color="#163b56", lw=2)
            axes[1].plot([i-.22, i+.22], [np.median(retention)]*2, color="#163b56", lw=2)
        axes[0].axhline(floor/1e-6, color=GREY, ls="--", label=f"Original floor assignment: {floor:.3g}")
        if upper is not None:
            axes[0].axhline(upper/1e-6, color=ORANGE, lw=2, label=f"Fitted candidate bound: {upper:.3g}")
        axes[0].set_ylabel("Retained injected data power\n/ thermal power (× 10⁻⁶)")
        axes[0].set_ylim(bottom=-.5)
        axes[0].legend(loc="lower left", bbox_to_anchor=(0, 1.01), fontsize=9, frameon=False)
        axes[1].plot(x, [100*32/96, 25, 25, 25, 25], "_", color=RED, ms=25, mew=2, label="Minimum support: 32 kept frames")
        axes[1].set_ylabel("Retained frames (%)")
        axes[1].set_ylim(0, 102)
        axes[1].set_xticks(x, [LABELS[c] for c in ORDER])
        axes[1].legend(loc="lower right", fontsize=9, frameon=False)
        for ax in axes:
            ax.grid(axis="y", alpha=.16)
            ax.set_xlim(-.5, 4.5)
        fig.text(.10, .068, "Dots are independent evaluation blocks; the five cases share samples within each block.\n"
                 "The fixed 100-block calibration targets 97% content at 95% confidence. All failures remain included.\n"
                 "Conditional on this waveform, noise, ADC and case family. This is not a measured telescope residual.", fontsize=9, color=GREY, linespacing=1.6)
        pages.savefig(fig)
        plt.close(fig)

        fig, axes = plt.subplots(2, 1, figsize=(10, 8.2), gridspec_kw={"height_ratios": [1, 1.1]})
        fig.subplots_adjust(left=.11, right=.97, top=.80, bottom=.23, hspace=.42)
        fig.text(.11, .955, "Steady weak signals need a different bound", fontsize=19, weight="bold")
        fig.text(.11, .910, "Descriptive pooling of every evaluation frame from each fixed on-population", fontsize=11)
        names = ["on_m50", "on_m44", "on_m10"]
        pooled = {}
        for name in names:
            pop_rows = [b[name] for b in ev["populations"].values()]
            n = sum(r["frames"] for r in pop_rows)
            kept = sum(r["kept"] for r in pop_rows)
            pooled[name] = {"frames": n, "kept": kept, "truth": pop_rows[0]["injected_shelf_linear"]}
        positions = np.arange(3)
        retention = [100*pooled[n]["kept"]/pooled[n]["frames"] for n in names]
        axes[0].bar(positions, retention, color=[RED, BLUE, GREY], width=.5)
        for i, name in enumerate(names):
            r = pooled[name]
            axes[0].text(i, retention[i]+2, f"{r['kept']:,}/{r['frames']:,} kept", ha="center", fontsize=10)
        axes[0].set_ylim(0, 105)
        axes[0].set_ylabel("Retained frames (%)")
        axes[0].set_xticks(positions, ["Steady -50 dB", "Steady -44 dB", "Steady -10 dB"])
        axes[0].axhline(25, ls=":", color=GREY, label="25% planning reference (pooled; not a block test)")
        axes[0].legend(loc="upper right", fontsize=8.8, frameon=False)
        for i, name in enumerate(names):
            r = pooled[name]
            if r["kept"]:
                axes[1].bar(i, r["truth"]/1e-6, color=RED if i == 0 else BLUE, width=.5)
                axes[1].text(i, r["truth"]/1e-6+1.3, f"{r['truth']:.3g}", ha="center", fontsize=10)
            else:
                axes[1].text(i, 2, "No retained frames", ha="center", fontsize=10, color=GREY)
        axes[1].axhline(floor/1e-6, ls="--", color=GREY, label="Original assigned floor")
        if upper is not None:
            axes[1].axhline(upper/1e-6, color=ORANGE, lw=2, label="Bound for the intermittent primary family")
        axes[1].set_ylabel("Retained injected ATSC data power\n/ thermal power (× 10⁻⁶)")
        axes[1].set_xticks(positions, ["Steady -50 dB", "Steady -44 dB", "Steady -10 dB"])
        axes[1].set_ylim(0, 47)
        axes[1].legend(loc="upper right", fontsize=9, frameon=False)
        for ax in axes:
            ax.grid(axis="y", alpha=.16)
            ax.set_xlim(-.55, 2.55)
        fig.text(.11, .092, "The steady -50 dB control has known retained truth above the fitted intermittent-population bound.\n"
                 "All on-populations are shown. This pooling supplies no new joint block-coverage claim or refit.\n"
                 "Transmitter duty cycle and amplitude history are part of the calibration's scope, even with baseline references.",
                 fontsize=9, color=GREY, linespacing=1.6)
        pages.savefig(fig)
        plt.close(fig)

        fig, axes = plt.subplots(2, 1, figsize=(10, 8.2), gridspec_kw={"height_ratios": [1.4, 1]})
        fig.subplots_adjust(left=.10, right=.97, top=.78, bottom=.22, hspace=.55)
        fig.text(.10, .955, "Reference contamination can hide a signal", fontsize=19, weight="bold")
        fig.text(.10, .911, "Three predeclared diagnostic controls outside the primary calibration guarantee", fontsize=11)
        names = ["clean_m35", "blind_m35_ref01", "ref_only01"]
        labels = ["-35 dB ATSC; baseline references", "-35 dB ATSC + reference tones", "Reference tones only"]
        colours = [BLUE, RED, GREY]
        controls = stress["populations"]
        arrays = []
        for name in names:
            with np.load(release / "stress/block-0000" / (name + ".npz"), allow_pickle=False) as z:
                arrays.append(normalized_ratio(z["coarse_marginals_u64"]))
        finite = np.concatenate([a[np.isfinite(a)] for a in arrays])
        bins = np.linspace(min(finite.min(), plan["policy"]["eta"]) - .005,
                           max(finite.max(), plan["policy"]["eta"]) + .005, 55)
        for name, label, colour, values in zip(names, labels, colours, arrays):
            values = values[np.isfinite(values)]
            axes[0].hist(values, bins=bins, density=True, histtype="step", color=colour,
                         lw=1.8, label=f"{label}: {controls[name]['kept']}/128 kept")
        axes[0].axvline(plan["policy"]["eta"], color=ORANGE, lw=2, label="Frozen cutoff (keep to left)")
        axes[0].set_xlabel("Normalized coarse target / reference power ratio Q")
        axes[0].set_ylabel("Probability density")
        axes[0].legend(frameon=False, fontsize=9, loc="lower center", bbox_to_anchor=(.5, 1.03), ncol=2)
        for i, (name, colour) in enumerate(zip(names, colours)):
            row = controls[name]
            truth = row["truth_kept_mean"]
            if truth is None:
                axes[1].text(i, 2., "No kept frames", ha="center", va="bottom", fontsize=9, color=colour)
            else:
                axes[1].bar(i, truth/floor, width=.45, color=colour, alpha=.9)
                axes[1].text(i, truth/floor+.3 if truth else 2., f"{truth/floor:.2f} × floor", ha="center", fontsize=9)
        axes[1].axhline(1, color=GREY, ls="--", label="Original assigned floor")
        if upper is not None:
            axes[1].axhline(upper/floor, color=ORANGE, label="Fitted candidate bound")
        axes[1].set_ylabel("Retained injected data power\n/ original floor assignment")
        axes[1].set_xticks(range(3), ["ATSC", "ATSC + reference tones", "Reference tones only"])
        axes[1].set_xlim(-.5, 2.5)
        axes[1].set_ylim(0, max(2, max((r["truth_kept_mean"] or 0)/floor for r in controls.values())*1.2))
        axes[1].legend(loc="upper left", frameon=False, fontsize=9)
        for ax in axes: ax.grid(axis="y", alpha=.16)
        fig.text(.10, .066, "Reference tones add 0.1 times the uncontaminated thermal projection power in each reference.\n"
                 "ATSC data truth excludes those tones; zero ATSC power does not mean interference-free. No stress refit.\n"
                 "These controls test a ratio failure mode; they do not identify its prevalence in CHIME data.", fontsize=9, color=GREY, linespacing=1.6)
        pages.savefig(fig)
        plt.close(fig)
    record = {"pdf": str(pdf), "sha256": runner.sha(pdf), "plan_sha256": plan["plan_sha256"],
              "inputs": {name: runner.sha(release / name) for name in ("calibration.json", "evaluation.json", "stress.json")},
              "plot_source": {"path": str(Path(__file__).resolve()), "sha256": runner.sha(__file__)},
              "scope": "Presentation only; no inference, tuning or source deletion"}
    runner.write_new(pdf.with_suffix(".manifest.json"), record)
    print(json.dumps(record))


if __name__ == "__main__":
    main()
