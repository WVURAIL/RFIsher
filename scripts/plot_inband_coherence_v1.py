#!/usr/bin/env python3
"""Render two descriptive pages from saved, pair-supported voltage moments.

This script does not read the packed voltage arrays, fit a noise model, or
estimate uncertainty.  All frequency panels use within-frequency input pairs.
The array selection and time blocks must already be declared in ``plan.json``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.colors import LogNorm
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator, PercentFormatter
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from rfisher_results.validation.voltage_coherence import summarize_moments


INK = "#202F3C"
MUTED = "#596876"
COLORS = ("#236CA3", "#B98718", "#498583")
POLICIES = (("all", "All stored samples", "-"),
            ("exclude_00", "Exclude byte 0x00 per input", "--"))
PAIRS = ((0, 1), (0, 16), (16, 17))
MOMENT_KEYS = ("count", "sum_x", "power_x", "cross")


def _sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_study(study):
    """Validate the declared geometry and load only small moment/flag arrays."""
    plan = json.loads((study / "plan.json").read_text())
    frequencies = plan["frequencies"]
    inputs = plan["inputs"]
    blocks = np.asarray(plan["blocks"], dtype=np.int64)
    dt = float(plan["delta_time_seconds"])
    total = int(plan["common_fpga_stop"]) - int(plan["common_fpga_start"])
    if (len(inputs) != 32 or len(frequencies) != 15 or not np.isfinite(dt)
            or dt <= 0 or total <= 0 or blocks.ndim != 2 or blocks.shape[1] != 2
            or len(blocks) < 2 or blocks[0, 0] != 0 or blocks[-1, 1] != total
            or np.any(blocks[:, 1] <= blocks[:, 0])
            or np.any(blocks[1:, 0] != blocks[:-1, 1])):
        raise ValueError("Expected the declared 32-input, 15-frequency contiguous study")
    if ({int(f["freq_id"]) for f in frequencies} != set(range(600, 615))
            or len({int(v["array_index"]) for v in inputs}) != 32):
        raise ValueError("Frequency or input identities differ from the figure contract")
    expected_inputs = [128 * group + offset for group in range(16)
                       for offset in (0, 1)]
    if [int(v["array_index"]) for v in inputs] != expected_inputs:
        raise ValueError("Input slots differ from the predeclared representative selection")
    if (int(plan["event_id"]) != 1153713684
            or plan["selected_plot_pairs"] != [list(pair) for pair in PAIRS]):
        raise ValueError("Event or plotted pairs differ from the predeclared figure contract")
    # All arrays and labels below follow increasing physical center frequency.
    frequencies = sorted(frequencies, key=lambda item: float(item["frequency_mhz"]))
    freq_mhz = np.array([float(f["frequency_mhz"]) for f in frequencies])
    if not np.isfinite(freq_mhz).all() or np.any(np.diff(freq_mhz) <= 0):
        raise ValueError("Frequency centers must be finite and distinct")
    result = {"plan": plan, "frequencies": frequencies, "inputs": inputs,
              "blocks": blocks, "dt": dt, "total": total,
              "frequency_mhz": freq_mhz, "files": [], "pooled": {},
              "block_coherency": {}, "occupancy": {}}
    shape = (len(blocks), len(inputs), len(inputs))
    flags = ("zero_code_count", "digital_zero_count", "component_rail_count")
    loaded = {policy: [] for policy, _, _ in POLICIES}
    block_loaded = {policy: [] for policy, _, _ in POLICIES}
    flag_loaded = {key: [] for key in flags}
    for frequency in frequencies:
        path = study / "data" / f"ch{int(frequency['freq_id']):04d}.npz"
        result["files"].append(path)
        with np.load(path, allow_pickle=False) as saved:
            for policy, _, _ in POLICIES:
                moments = {key: saved[f"{policy}_{key}"] for key in MOMENT_KEYS}
                if any(values.shape != shape for values in moments.values()):
                    raise ValueError(f"Moment shape mismatch in {path}")
                if (np.any(moments["count"] < 0)
                        or np.any(moments["count"] > np.diff(blocks, axis=1)[:, :, None])):
                    raise ValueError(f"Impossible pair support in {path}")
                loaded[policy].append(summarize_moments(
                    {key: values.sum(axis=0) for key, values in moments.items()}))
                block_loaded[policy].append(np.stack([
                    summarize_moments({key: values[b] for key, values in moments.items()})[
                        "coherency"] for b in range(len(blocks))]))
            for key in flags:
                counts = saved[key]
                flag_shape = (len(blocks), 32, 2) if key == "component_rail_count" else (len(blocks), 32)
                bounds = np.diff(blocks, axis=1)
                if key == "component_rail_count":
                    bounds = bounds[:, :, None]
                if (counts.shape != flag_shape or not np.issubdtype(counts.dtype, np.integer)
                        or np.any(counts < 0) or np.any(counts > bounds)):
                    raise ValueError(f"Invalid {key} in {path}")
                flag_loaded[key].append(counts.sum(axis=0))
    for policy, _, _ in POLICIES:
        result["pooled"][policy] = {
            key: np.stack([value[key] for value in loaded[policy]])
            for key in loaded[policy][0]}
        result["block_coherency"][policy] = np.stack(block_loaded[policy])
    for key, counts in flag_loaded.items():
        result["occupancy"][key] = np.stack(counts) / total
    return result


def page(title, subtitle, number):
    fig = plt.figure(figsize=(11.7, 8.3), facecolor="white")
    fig.text(0.065, 0.965, "ONE-EVENT DIGITAL VOLTAGE DIAGNOSTIC", color=MUTED,
             size=9, weight="bold", va="top")
    fig.text(0.065, 0.926, title, color=INK, size=19, weight="bold", va="top")
    fig.text(0.065, 0.884, subtitle, color=MUTED, size=9.3, va="top")
    fig.text(0.065, 0.033, "Development acquisition 1153713684; no physical cleaner-transfer measurement.",
             color=MUTED, size=8.2, va="bottom")
    fig.text(0.94, 0.033, f"{number} / 2", ha="right", color=MUTED, size=8.2)
    return fig


def style(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(colors=MUTED, labelsize=8.5)
    ax.grid(axis="y", alpha=0.18, color=MUTED)
    ax.set_axisbelow(True)
    ax.xaxis.label.set_color(INK)
    ax.yaxis.label.set_color(INK)


def occupancy_panel(ax, frequency, series, title, ylabel):
    style(ax)
    for values, label, color, linestyle in series:
        ax.plot(frequency, values, color=color, ls=linestyle, marker="o", ms=3,
                lw=1.3, label=label)
    ax.set_title(title, loc="left", size=10.5, weight="bold", pad=9)
    ax.set_xlabel("Coarse-bin center (MHz)", size=9)
    ax.set_ylabel(ylabel, size=9)
    ax.yaxis.set_major_formatter(PercentFormatter(xmax=1))
    ax.xaxis.set_major_locator(MaxNLocator(4))
    ax.set_ylim(bottom=0)
    ax.legend(frameon=False, fontsize=8, loc="best", handlelength=1.8)


def overview(data):
    duration = data["total"] * data["dt"]
    frequencies = data["frequency_mhz"]
    fig = page("Input-pair coherence across channel 29",
               f"{data['total']:,} shared samples ({duration:.8f} s) | 32 predeclared inputs | "
               f"{frequencies[0]:.5f}–{frequencies[-1]:.5f} MHz centers", 1)
    gs = fig.add_gridspec(2, 2, left=0.09, right=0.90, top=0.81, bottom=0.23,
                          hspace=0.52, wspace=0.27, height_ratios=(2.0, 1.0))
    pair_i, pair_j = np.triu_indices(32, 1)
    all_values = np.concatenate([np.abs(data["pooled"][policy]["coherency"][:, pair_i, pair_j]).ravel()
                                 for policy, _, _ in POLICIES])
    positive = all_values[np.isfinite(all_values) & (all_values > 0)]
    if not len(positive):
        raise ValueError("A logarithmic heatmap requires at least one positive finite coherency")
    vmin = 10.0 ** np.floor(np.log10(positive.min()))
    vmax_order = 10.0 ** np.floor(np.log10(positive.max()))
    vmax = max(vmin * 10, np.ceil(positive.max() / vmax_order) * vmax_order)
    color_ticks = np.r_[10.0 ** np.arange(np.log10(vmin), np.log10(vmax) + 1e-10), vmax]
    color_ticks = np.unique(color_ticks)
    cmap = plt.get_cmap("viridis").copy()
    cmap.set_bad("#E4E8EB")
    cmap.set_under("white")
    heatmaps = []
    for col, (policy, label, _) in enumerate(POLICIES):
        ax = fig.add_subplot(gs[0, col])
        values = np.abs(data["pooled"][policy]["coherency"][:, pair_i, pair_j])
        # LogNorm cannot represent zero. A separate under-range white color
        # preserves exact zeros without labeling a small positive value zero.
        display_values = np.where(values == 0, vmin / 10, values)
        image = ax.imshow(display_values, aspect="auto", origin="lower", interpolation="nearest",
                          cmap=cmap, norm=LogNorm(vmin=vmin, vmax=vmax), extent=(0.5, 496.5, -0.5, 14.5),
                          rasterized=True)
        heatmaps.append(ax)
        ax.set_title(label, loc="left", size=10.5, weight="bold", pad=9)
        ax.set_xlabel("Pair index (1–496; lexicographic input slots)", size=9)
        ticks = [0, 3, 6, 9, 12, 14]
        ax.set_yticks(ticks, [f"{frequencies[k]:.3f}" for k in ticks])
        ax.set_ylabel("Coarse-bin center (MHz)" if col == 0 else "", size=9)
        ax.tick_params(labelsize=8)
        ax.set_xticks([1, 100, 200, 300, 400, 496])
    position = heatmaps[-1].get_position()
    cax = fig.add_axes([0.917, position.y0, 0.013, position.height])
    cb = fig.colorbar(image, cax=cax, ticks=color_ticks)
    cb.ax.tick_params(labelsize=8)
    cb.ax.set_yticklabels([f"{value:g}" for value in color_ticks])
    cb.set_label(r"Raw $|\gamma_{ij}|$ (log color scale)", size=9)
    occupancy = data["occupancy"]
    occupancy_panel(fig.add_subplot(gs[1, 0]), frequencies,
                    [(occupancy["zero_code_count"].mean(axis=1), "Byte 0x00 (−8 − 8i)", COLORS[0], "-"),
                     (occupancy["digital_zero_count"].mean(axis=1), "Byte 0x88 (0 + 0i)", COLORS[1], "--")],
                    "Stored-code occupancy", "Fraction of complex samples")
    rails = occupancy["component_rail_count"]
    occupancy_panel(fig.add_subplot(gs[1, 1]), frequencies,
                    [(rails[:, :, 0].mean(axis=1), "Real component", COLORS[0], "-"),
                     (rails[:, :, 1].mean(axis=1), "Imaginary component", COLORS[2], "--")],
                    "Component occupancy at either rail (−8 or +7)", "Fraction of component samples")
    fig.text(0.065, 0.159,
             r"$\gamma_{ij}=\sum_t x_i(t)x_j^*(t)\,/\,\sqrt{\sum_t|x_i(t)|^2\,\sum_t|x_j(t)|^2}$"
             "  on each pair's common selected support; no mean subtraction.",
             color=INK, size=9.2)
    coincidence = ("No 0x00 codes occurred in the selected payload; the two policies give identical results."
                   if not np.any(occupancy["zero_code_count"]) else
                   "The two policies use each pair's common support; code exclusion changes the selected sample population.")
    fig.text(0.065, 0.129,
             "Block sums are pooled before normalization. Shared log color scale; gray = undefined, white = exact zero. "
             "Input indices: 128g + {0, 1}, g = 0…15.\n"
             + coincidence + " Rail occupancy alone does not identify clipping.\n"
             "Excluding 0x00 is a sample-code-conditioned sensitivity calculation, not verified packet validity. "
             "Gains, delays and channel response are uncorrected.\n"
             "Nominal coverage 559.96094–565.82031 MHz leaves the upper 0.17969 MHz of channel 29 uncovered.",
             color=MUTED, size=8.0, linespacing=1.42, va="top")
    return fig


def _pair_label(data, pair):
    left, right = (data["inputs"][slot] for slot in pair)
    return f"{int(left['array_index'])} × {int(right['array_index'])}"


def _pair_identity(data, pair):
    left, right = (data["inputs"][slot] for slot in pair)
    return (f"{_pair_label(data, pair)}: "
            f"chan_id {left['chan_id']} × {right['chan_id']}; "
            f"{left['correlator_input']} × {right['correlator_input']}")


def pair_page(data):
    subtitle = ("Three pairs fixed by input-map position. Solid/dashed curves coincide: "
                "the selected payload contains no 0x00 codes."
                if not np.any(data["occupancy"]["zero_code_count"]) else
                "Three pairs fixed by input-map position. Each point is one input pair within one coarse bin; "
                "lines join bin centers.")
    fig = page("Complex coherency and short-block variation",
               subtitle, 2)
    handles = [Line2D([], [], color=color, lw=2, label=f"Input indices { _pair_label(data, pair)}")
               for pair, color in zip(PAIRS, COLORS)]
    handles += [Line2D([], [], color=INK, lw=1.3, ls=linestyle, label=label)
                for _, label, linestyle in POLICIES]
    fig.legend(handles=handles, loc="center", bbox_to_anchor=(0.50, 0.837),
               ncol=3, frameon=False, fontsize=8.3, handlelength=2.2,
               columnspacing=1.8, handletextpad=0.5)
    gs = fig.add_gridspec(2, 2, left=0.09, right=0.935, top=0.773, bottom=0.267,
                          hspace=0.55, wspace=0.23)
    pair_values = np.concatenate([data["pooled"][policy]["coherency"][:, pair[0], pair[1]]
                                  for policy, _, _ in POLICIES for pair in PAIRS])
    components = np.r_[pair_values.real, pair_values.imag]
    component_limit = max(1e-4, np.abs(components[np.isfinite(components)]).max(initial=0)) * 1.15
    for col, (component, label) in enumerate(((np.real, "Real"), (np.imag, "Imaginary"))):
        ax = fig.add_subplot(gs[0, col])
        style(ax)
        ax.axhline(0, color=MUTED, lw=0.7, alpha=0.45)
        for pair, color in zip(PAIRS, COLORS):
            for policy, _, linestyle in POLICIES:
                values = data["pooled"][policy]["coherency"][:, pair[0], pair[1]]
                ax.plot(data["frequency_mhz"], component(values), color=color,
                        ls=linestyle, lw=1.25, marker="o" if policy == "all" else None,
                        ms=3, alpha=0.92)
        ax.set_title(f"{label} part of pooled raw coherency", loc="left", size=10.5,
                      weight="bold", pad=9)
        ax.set_xlabel("Coarse-bin center (MHz)", size=9)
        ax.set_ylabel(r"Re $\gamma_{ij}$" if col == 0 else r"Im $\gamma_{ij}$", size=9)
        ax.xaxis.set_major_locator(MaxNLocator(4))
        ax.set_ylim(-component_limit, component_limit)
    lengths = np.diff(data["blocks"], axis=1).ravel()
    typical_length = int(np.max(lengths))
    tail = lengths < typical_length
    centers = data["blocks"].mean(axis=1) * data["dt"] * 1000
    plotted_freqs = [k for k, f in enumerate(data["frequencies"])
                     if int(f["freq_id"]) in (614, 600)]
    block_values = np.concatenate([
        np.abs(data["block_coherency"][policy][k, :, pair[0], pair[1]])
        for policy, _, _ in POLICIES for k in plotted_freqs for pair in PAIRS])
    finite_block_values = block_values[np.isfinite(block_values)]
    upper_magnitude = min(1.02, max(0.01, finite_block_values.max(initial=0)) * 1.15)
    for col, freq_id in enumerate((614, 600)):
        freq_index = next(k for k, f in enumerate(data["frequencies"])
                          if int(f["freq_id"]) == freq_id)
        ax = fig.add_subplot(gs[1, col])
        style(ax)
        for start, stop in data["blocks"][tail]:
            ax.axvspan(start * data["dt"] * 1000, stop * data["dt"] * 1000,
                       color="#DCE3E8", alpha=0.95, zorder=0)
        for pair, color in zip(PAIRS, COLORS):
            for policy, _, linestyle in POLICIES:
                values = np.abs(data["block_coherency"][policy][freq_index, :, pair[0], pair[1]])
                ax.plot(centers[~tail], values[~tail], color=color, ls=linestyle,
                        lw=1.15, marker="o" if policy == "all" else None, ms=2.4)
                if np.any(tail):
                    ax.plot(centers[tail], values[tail], ls="", marker="D" if policy == "all" else "s",
                            markerfacecolor="none", markeredgecolor=color, markersize=5.5,
                            markeredgewidth=1.2 if policy == "all" else 0.8)
        ax.set_xlim(-4, data["total"] * data["dt"] * 1000 + 7)
        ax.set_ylim(0, upper_magnitude)
        ax.set_xlabel("Time from common FPGA start (ms)", size=9)
        ax.set_ylabel(r"Raw $|\gamma_{ij}|$ per block", size=9)
        ax.set_title(f"Bin {freq_id}: {data['frequency_mhz'][freq_index]:.5f} MHz",
                      loc="left", size=10.5, weight="bold", pad=9)
    tail_text = (f"Final {int(lengths[-1]):,}-sample block is separate: open diamonds (all) / squares (exclude 0x00); shaded time interval."
                 if bool(tail[-1]) else "All declared blocks have the same sample count.")
    fig.text(0.065, 0.205,
             f"Block curves use {typical_length:,} stored samples ({typical_length * data['dt'] * 1000:.5f} ms) "
             "before sample-code selection.\n" + tail_text,
             color=MUTED, size=8.05, linespacing=1.35, va="center")
    for row, pair in enumerate(PAIRS):
        fig.text(0.065, 0.178 - row * 0.021, _pair_identity(data, pair), color=COLORS[row], size=8.0)
    fig.text(0.065, 0.092,
             "Raw coherency includes sample means and instrumental phase. Across-frequency trends are not cross-frequency "
             "voltage correlations.\nBlock variation is descriptive, with unequal selected counts and a shorter tail; "
             "no confidence intervals, independent-block assumption or noise interpretation is applied.",
             color=MUTED, size=8.1, linespacing=1.5, va="top")
    return fig


def main(args):
    for path in (args.study, args.pdf, args.png_dir):
        if not path.is_absolute():
            raise ValueError("All paths must be absolute")
    images = [args.png_dir / f"inband-coherence-page-{number}.png" for number in (1, 2)]
    if args.pdf.exists() or any(path.exists() for path in images):
        raise FileExistsError("Refusing to overwrite an existing PDF or page image")
    data = load_study(args.study)
    args.pdf.parent.mkdir(parents=True, exist_ok=True)
    args.png_dir.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.edgecolor": "#A3AFB8", "axes.labelsize": 9,
                         "pdf.fonttype": 42, "ps.fonttype": 42,
                         "savefig.facecolor": "white"})
    plan_sha = _sha256(args.study / "plan.json")
    with PdfPages(args.pdf, metadata={
        "Title": "Channel 29: one-event digital voltage coherency",
        "Author": "RFIsher descriptive validation",
        "Subject": f"Development event 1153713684; plan SHA-256 {plan_sha}",
        "Keywords": "raw complex cross-products, pairwise support, exploratory, uncalibrated",
    }) as pdf:
        for make_page, image in zip((overview, pair_page), images):
            fig = make_page(data)
            pdf.savefig(fig)
            fig.savefig(image, dpi=180)
            plt.close(fig)
    print(json.dumps({"pdf": str(args.pdf), "pdf_sha256": _sha256(args.pdf),
                      "png_pages": [str(path) for path in images],
                      "plan_sha256": plan_sha, "pages": 2}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", type=Path, required=True)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--png-dir", type=Path, required=True)
    main(parser.parse_args())
