#!/usr/bin/env python3
"""What the discarded k_par window is worth: BAO significance vs delay cut.

CHIME's z ~ 1 auto-spectrum detection removes foregrounds with a DAYENU
high-pass filter at tau_cut = 200 ns and then discards everything below the
280 ns mask, so the measurement begins at k_par = 0.35 h/Mpc. The BAO
wiggles live at k ~ 0.05-0.3 h/Mpc, i.e. below that floor. This script
prices the window: for a hard delay cut at tau_cut, what BAO detection
significance and what BAO dilation errors survive?

Three configurations:

  chime2025            the published field: 2,200 deg^2, 608.2-707.8 MHz
                       (three dz ~ 0.1 bins), 385 h effective, Tsys = 55 K.
  archive7yr           the Overview fiducial (31,000 deg^2, 400-800 MHz) at
                       seven calendar years x the 2019 duty cycle = 1.06
                       on-sky years.
  archive7yr_accepted  the same archive on the sky the present cuts accept:
                       |y| < 0.4 less the 33% spatial mask (7,200 deg^2), at
                       the same per-voxel depth.
  chime2025_masked     the published field after its own spatial mask
                       (1,470 deg^2, 258 h, same depth); tables only.

The archive is also run with the soft cut: the digitised Fig. 10 filter
response, scaled in tau / tau_cut, normalised to its plateau and squared,
multiplying the signal (expt['kpar_transfer_fn']) instead of the hard
kpar_min_fn excision. One dashed line on the figure; `cut` column in the
tables.

The cut runs through the RadioFisher fork's expt['kpar_min_fn'] hook and
direct rf.fisher() calls, not the shipped Fisher banks: k_par,min is a
dimension the banks do not carry.

Calibration. The noise model is checked against the published 12.4 sigma:
with tau_cut = 200 ns, the total power-spectrum S/N over 0.4 < k < 1.5
h/Mpc for chime2025. The statistic is sqrt(F_pk,pk) with deriv_pk =
P_sig / (P_sig + P_N), i.e. exactly sum over modes of (P_sig / sigma_P)^2
with sigma_P = (P_sig + P_N) sqrt(2 / N_modes): a true total S/N of a
single P(k) amplitude, not the BAO-wiggle amplitude. It depends on
sigma_NL only because RadioFisher's signal is Kaiser x exp(-mu^2 k^2
sigma_NL^2), a broadband damping of the whole 21 cm power rather than of
the wiggles, and the delay cut leaves exactly the mu ~ 1 modes that term
acts on at k > 0.4 h/Mpc. Two traps therefore sit in the comparison: the
k_NL cutoff, which lands on the published k_par floor and would delete the
band (CALIBRATION_K_NL0), and sigma_NL itself (CALIBRATION_SIGMA_NL_GRID).
The calibration reports the noise check uncut, the sigma_NL that
reproduces 12.4 sigma under the cut, and how much the BAO thresholds move
between that value and the fiducial.

Outputs, all under --out:
    taucut_calibration.csv    the calibration against 12.4 sigma
    taucut_sweep.csv          A/sigma(A), sigma(alpha_par), sigma(alpha_perp)
                              at the fiducial sigma_NL and at the matched one
    taucut_sweep_perbin.csv   the per-redshift-bin alpha errors
    taucut_thresholds.csv     3 and 5 sigma crossings read off the grid
    fig_taucut_bao.png/.pdf   the figure (fiducial sigma_NL)
    fig_taucut_bao_caption.txt

    python3 scripts/run_taucut_sweep.py --out out/
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import io
import multiprocessing as mp
import os
import time
from pathlib import Path

import numpy as np

from rfisher import cosmologies, forecast, pkcache, survey
from rfisher.backend import import_radiofisher, require_backend_capabilities
from rfisher.resources import filesystem_data_file

# The delay grid of the proposal's figure, in ns, dense through 100-200 ns
# where the archive curves cross 5 and 3 sigma so the crossings are read
# off rather than interpolated. 200 is the published DAYENU cut; 280 is
# the first delay the published analysis retains.
TAU_NS_DEFAULT = (30.0, 50.0, 75.0, 100.0, 110.0, 125.0, 140.0, 150.0,
                  160.0, 175.0, 200.0, 280.0, 400.0)

# Marked on the figure: the proposal's "current / realistic / stretch".
# The published DAYENU cut is 200 ns; 280 ns is the first delay the
# published analysis retains, so it is marked as "current" in the
# proposal's own language and 200 ns is marked separately.
TAU_NS_MARKERS = ((280.0, "current"), (100.0, "realistic"),
                  (50.0, "stretch"))

THRESHOLDS = (5.0, 3.0)

# The soft cut is drawn for the full-sky archive only: one extra line that
# shows the hard cut is the conservative one.
SOFT_CUT_CONFIGS = ("archive7yr",)

# Legend labels for the two-panel Fig. 10-format figure, where the top
# panel carries the context and the legend must fit beside the curves.
SHORT_LABELS = {
    "chime2025": "Published field (2,200 deg$^2$, 385 h)",
    "archive7yr": "Archive, full sky (31,000 deg$^2$)",
    "archive7yr_accepted": "Archive, accepted sky (7,206 deg$^2$)",
    "chime2025_masked": "Published field after mask (1,474 deg$^2$)",
}

# RadioFisher's non-linear cutoff, k_NL,0 = 0.14 Mpc^-1, rises as
# (1+z)^(2/(2+ns)) and reaches 0.35 h/Mpc at z = 1.16 -- numerically the
# same place as the published 280 ns mask. Left in place it would delete
# the entire 0.4-1.5 h/Mpc band the detection lives in, and the
# calibration would compare against nothing. Push it above the band for
# the calibration step only; the integral is bounded at 1.5 h/Mpc by kmax
# regardless. The BAO sweep restores the default cutoff, where it costs
# nothing: BAO information is damped away long before k_NL.
CALIBRATION_K_NL0 = 10.0            # Mpc^-1

# sigma_NL = 7 Mpc is the fiducial BAO-smearing scale of the Overview
# forecast, valid where BAO information lives (k <~ 0.2 Mpc^-1). The scan
# measures the calibration statistic's sensitivity to it and locates the
# value that reproduces 12.4 sigma; the "undamped" value is small enough
# that exp(-mu^2 k^2 sigma_NL^2) is 1 over the whole band.
CALIBRATION_SIGMA_NL_GRID = (3.0, 4.0, 5.0, 6.0, 7.0)
CALIBRATION_SIGMA_NL_UNDAMPED = 1e-3

_CTX: dict = {}


# ------------------------------------------------------------------ setup
def _make_configs(rf, rf_dir, chime2025_ttot_hours=None):
    """Experiment factory and redshift binning for each configuration."""
    if chime2025_ttot_hours is None:
        chime2025_ttot_hours = survey.CHIME2025_TTOT_HOURS
    chime2025 = survey.chime2025_experiment(
        rf, rf_dir, ttot_hours=chime2025_ttot_hours)
    zs2025, zc2025 = survey.chime2025_zbins(rf, chime2025)
    zs_arch, zc_arch = survey.chime2022_zbins()
    accepted_deg2 = survey.accepted_sky_area_deg2()
    kept = 1.0 - survey.CHIME2025_SPATIAL_MASK_FRACTION
    masked_deg2 = survey.CHIME2025_SAREA_DEG2 * kept
    masked_hours = chime2025_ttot_hours * kept
    return {
        "chime2025": {
            "label": f"CHIME 2025 as published "
                     f"({survey.CHIME2025_SAREA_DEG2:,.0f} deg$^2$, "
                     f"{chime2025_ttot_hours:,.0f} h)",
            "make_expt": lambda: survey.chime2025_experiment(
                rf, rf_dir, ttot_hours=chime2025_ttot_hours),
            "zs": np.asarray(zs2025), "zc": np.asarray(zc2025),
            "ttot_hours": chime2025_ttot_hours,
            "sarea_deg2": survey.CHIME2025_SAREA_DEG2,
        },
        "archive7yr": {
            "label": f"Seven-year archive, full sky "
                     f"({survey.OVERVIEW_SAREA_DEG2:,.0f} deg$^2$, "
                     f"{survey.archive_hours() / survey.OVERVIEW_ONSKY_YEAR_HOURS:.2f} "
                     f"on-sky yr)",
            "make_expt": lambda: survey.chime2022_experiment(
                rf, rf_dir, ttot_hours=survey.archive_hours()),
            "zs": np.asarray(zs_arch), "zc": np.asarray(zc_arch),
            "ttot_hours": survey.archive_hours(),
            "sarea_deg2": survey.OVERVIEW_SAREA_DEG2,
        },
        "archive7yr_accepted": {
            "label": f"Seven-year archive, $|y| < {survey.ACCEPTED_NS_SINE_MAX}$ "
                     f"less {100 * survey.CHIME2025_SPATIAL_MASK_FRACTION:.0f}% "
                     f"mask ({accepted_deg2:,.0f} deg$^2$, same depth)",
            "make_expt": lambda: survey.archive_accepted_experiment(
                rf, rf_dir),
            "zs": np.asarray(zs_arch), "zc": np.asarray(zc_arch),
            "ttot_hours": survey.accepted_archive_hours(),
            "sarea_deg2": accepted_deg2,
        },
        "chime2025_masked": {
            "label": f"CHIME 2025 after its spatial mask "
                     f"({masked_deg2:,.0f} deg$^2$, {masked_hours:,.0f} h)",
            "make_expt": lambda: survey.chime2025_masked_experiment(
                rf, rf_dir),
            "zs": np.asarray(zs2025), "zc": np.asarray(zc2025),
            "ttot_hours": masked_hours,
            "sarea_deg2": masked_deg2,
            "figure": False,
        },
    }


def _init_context(rf_dir=None, cosmology="planck2018",
                  chime2025_ttot_hours=None):
    rf, rf_dir = import_radiofisher(rf_dir)
    require_backend_capabilities(
        rf, {"kpar_min_fn", "kpar_transfer_fn",
             "astrophysical_model_profiles", "explicit_physical_densities"},
        rf_dir=rf_dir)
    ctag = f"_{cosmology}" if cosmology != "planck2018" else ""
    cosmo = pkcache.load_fiducial_cosmology(
        rf, filesystem_data_file(f"cache_pk_chime2022{ctag}.dat"),
        cosmo=cosmologies.get(cosmology, rf, rf_dir))
    cosmo_fns = rf.background_evolution_splines(cosmo)
    _CTX.update(rf=rf, rf_dir=rf_dir, cosmo=cosmo, cosmo_fns=cosmo_fns,
                configs=_make_configs(rf, rf_dir, chime2025_ttot_hours),
                cosmology=cosmology)
    return rf, rf_dir


def kpar_min_h(tau_ns: float, z: float) -> float:
    """k_par,min [h/Mpc] at redshift z for a delay cut of tau_ns."""
    rf, cosmo = _CTX["rf"], _CTX["cosmo"]
    fn = rf.delay_cut_kpar_min(
        tau_ns * 1e-9, _CTX["cosmo_fns"][0], survey.HI_REST_FREQUENCY_MHZ)
    return float(fn(z) / cosmo["h"])


# ----------------------------------------------------------------- worker
def _one_fisher(task):
    """Worker: one (config, tau, zbin) Fisher matrix, BAO or calibration."""
    config, tau_ns, ibin, kind, sigma_nl = task
    rf, cosmo, cosmo_fns = _CTX["rf"], _CTX["cosmo"], _CTX["cosmo_fns"]
    if sigma_nl is not None:
        cosmo = dict(cosmo, sigma_nl=float(sigma_nl))
    cfg = _CTX["configs"][config]
    expt = cfg["make_expt"]()
    kwargs = {}
    if kind.startswith("calib"):
        if kind != "calib_nl_default":
            expt["k_nl0"] = CALIBRATION_K_NL0
        h = cosmo["h"]
        kwargs = dict(kmin=survey.CHIME2025_KMIN_H * h,
                      kmax=survey.CHIME2025_KMAX_H * h)
    if kind == "bao_soft" and tau_ns > 0.0:
        expt["kpar_transfer_fn"] = survey.delay_transfer(
            rf, expt, cosmo_fns, tau_ns * 1e-9)
    else:
        expt["kpar_min_fn"] = survey.delay_cut(
            rf, expt, cosmo_fns, tau_ns * 1e-9)
    zs = cfg["zs"]
    with contextlib.redirect_stdout(io.StringIO()):
        F, paramnames = rf.fisher(zs[ibin], zs[ibin + 1], cosmo, expt,
                                  cosmo_fns, **kwargs)
    return (config, tau_ns, ibin, kind, sigma_nl, np.asarray(F),
            list(paramnames))


def _run(tasks, nproc, verbose=True):
    nproc = nproc or max(1, (os.cpu_count() or 2) - 2)
    started = time.time()
    results = []
    if nproc > 1:
        with mp.get_context("fork").Pool(nproc) as pool:
            for k, res in enumerate(pool.imap_unordered(_one_fisher, tasks)):
                results.append(res)
                if verbose and (k + 1) % 50 == 0:
                    print(f"[taucut] {k + 1}/{len(tasks)} "
                          f"({(time.time() - started) / 60:.1f} min)",
                          flush=True)
    else:
        results = [_one_fisher(task) for task in tasks]
    if verbose:
        print(f"[taucut] {len(tasks)} Fisher evaluations in "
              f"{(time.time() - started) / 60:.1f} min", flush=True)
    return results


# ---------------------------------------------------------------- metrics
def _sigma(F, names, param):
    """Marginalised error on one parameter of a combined Fisher matrix.

    forecast._variance_from_fisher carries this project's null-space and
    conditioning discipline (an unconstrained direction must come back as
    infinite, not as a small number from a blind pseudoinverse). Reusing it
    keeps every sigma in the repository on one definition."""
    coefficients = np.zeros(len(names))
    coefficients[names.index(param)] = 1.0
    variance = forecast._variance_from_fisher(F, coefficients)
    return float(np.sqrt(variance)) if np.isfinite(variance) else np.inf


def _quadrature(sigmas):
    """Combine independent per-bin errors on a common parameter."""
    inverse = sum(1.0 / s**2 for s in sigmas if np.isfinite(s) and s > 0.0)
    return float(1.0 / np.sqrt(inverse)) if inverse > 0.0 else np.inf


def bao_metrics(rf, paramnames, F_list):
    """sigma(A), and per-bin/combined sigma(alpha_par), sigma(alpha_perp).

    Marginalisation is the repository's established shared_A convention
    (Bull et al. 2015): A and sigma_NL shared across bins, {b_HI, f, aperp,
    apar} expanded per bin, {Tb, sigma_8, n_s} fixed. The survey-level
    alpha errors combine the per-bin ones in quadrature, which is what an
    independent-bin fit to a common dilation gives."""
    Ftot, names = rf.combined_fisher_matrix(
        F_list, names=list(paramnames), exclude=list(forecast.EXCLUDE),
        expand=list(forecast.EXPAND))
    Ftot = 0.5 * (Ftot + Ftot.T)
    nbins = len(F_list)
    per_bin = []
    for i in range(nbins):
        per_bin.append({
            "sigma_apar": _sigma(Ftot, names, f"apar{i}"),
            "sigma_aperp": _sigma(Ftot, names, f"aperp{i}"),
        })
    sigma_A = _sigma(Ftot, names, "A")
    return {
        "sigma_A": sigma_A,
        "significance": (1.0 / sigma_A) if np.isfinite(sigma_A)
                        and sigma_A > 0.0 else 0.0,
        "sigma_apar": _quadrature([b["sigma_apar"] for b in per_bin]),
        "sigma_aperp": _quadrature([b["sigma_aperp"] for b in per_bin]),
        "per_bin": per_bin,
    }


def read_off_threshold(taus, significances, target):
    """Bracket a downward crossing of ``target`` on the sweep grid.

    Returns (tau_above, sig_above, tau_below, sig_below, tau_interp): the
    largest grid delay still at or above the target, the next grid delay
    below it, and a log-log interpolation between the two for reference.
    The bracket is what to quote; the interpolation is a convenience.
    ``tau_above`` is None when the curve never reaches the target,
    ``tau_below`` is None when it never drops below it on the grid."""
    order = np.argsort(taus)
    taus = np.asarray(taus, dtype=float)[order]
    sig = np.asarray(significances, dtype=float)[order]
    above = np.flatnonzero(sig >= target)
    if above.size == 0:
        return None, None, None, None, None
    i = int(above[-1])
    if i + 1 >= taus.size:
        return float(taus[i]), float(sig[i]), None, None, None
    t0, s0, t1, s1 = taus[i], sig[i], taus[i + 1], sig[i + 1]
    if s1 > 0.0 and s0 > 0.0:
        interp = float(np.exp(np.interp(
            np.log(target), [np.log(s1), np.log(s0)],
            [np.log(t1), np.log(t0)])))
    else:
        interp = None
    return float(t0), float(s0), float(t1), float(s1), interp


# ----------------------------------------------------------------- figure
def fig_fig10_format(curves, labels, no_cut, soft_curves, delay_floor_of_tau,
                     kpar_of_delay, residual_table, markers, tau_cut_ns,
                     tau_mask_ns, z_reference, outfile, floor=0.1,
                     delay_max_ns=450.0):
    """Two panels on the delay axis of Amiri et al. 2025 Fig. 10.

    Top: their filter's RMS residual against the delay of a mode, with the
    same gray (below the cut) and pink (transition) shading. Bottom: BAO
    significance against the *retained delay floor*, which is the same
    quantity: a hard cut that keeps modes above delay tau_min sits at
    tau_min = 1.4 tau_cut on the sweep grid. Sharing the axis makes the
    figure read as "here is what the filter keeps; here is what the BAO is
    worth at that delay". The top axis is k_par at z = 1.16 for a mode of
    that delay, as in the paper."""
    import matplotlib.pyplot as plt
    from matplotlib.ticker import NullFormatter
    from rfisher.plots import (BASELINE, CRITICAL, INK, INK2, MUTED, SERIES,
                               _save, setup_style)

    setup_style()
    fig, (top, bot) = plt.subplots(
        2, 1, figsize=(7.4, 7.2), sharex=True,
        gridspec_kw={"height_ratios": [1.0, 2.2], "hspace": 0.08})
    gray, pink = "#d9d9d9", "#f6c9c9"
    for ax in (top, bot):
        ax.axvspan(0.0, tau_cut_ns, color=gray, alpha=0.55, lw=0)
        ax.axvspan(tau_cut_ns, tau_mask_ns, color=pink, alpha=0.55, lw=0)

    # -- top: the paper's filter response -----------------------------
    ratio, response = residual_table
    delay = ratio * tau_cut_ns
    top.plot(delay, response, color=INK, lw=1.6)
    top.set_ylim(0.0, 1.0)
    top.set_yticks([0.0, 0.3, 0.5, 0.7, 0.9])
    top.set_ylabel("RMS filter residual")
    top.text(tau_cut_ns + 4, 0.97,
             r"$\tau_{\rm cut}$" + f" = {tau_cut_ns:.0f} ns",
             color=INK2, fontsize=9, ha="left", va="top", rotation=90)
    top.text(tau_mask_ns + 6, 0.1, f"kept above {tau_mask_ns:.0f} ns",
             color=INK2, fontsize=9, ha="left", va="bottom")
    top.text(2, 0.92, "Amiri et al. 2025, Fig. 10 (digitised)",
             color=MUTED, fontsize=8.5, ha="left", va="top")
    top.grid(True, axis="y")

    # -- bottom: what the BAO is worth at that floor -------------------
    colors = {name: SERIES[i] for i, name in enumerate(curves)}
    ceiling_max = max([v for v in no_cut.values() if np.isfinite(v)]
                      or [1.0])
    for name, curve in curves.items():
        tau = delay_floor_of_tau(np.asarray(curve["tau"], dtype=float))
        sig = np.asarray(curve["significance"], dtype=float)
        color = colors[name]
        live = np.isfinite(sig) & (sig > floor) & (tau <= delay_max_ns)
        bot.plot(tau[live], sig[live], color=color, marker="o", ms=4.0,
                 label=labels.get(name, name))
        dead = ~live & (tau <= delay_max_ns)
        if np.any(dead):
            bot.plot(tau[dead], np.full(dead.sum(), floor), color=color,
                     marker="v", ms=5.0, mfc="none", ls="none")
        ceiling = no_cut.get(name)
        if ceiling and np.isfinite(ceiling):
            bot.axhline(ceiling, color=color, lw=1.0, ls=(0, (4, 3)),
                        alpha=0.5)
            bot.text(delay_max_ns - 4, ceiling * 1.08, "no cut",
                     color=color, fontsize=8.5, ha="right", va="bottom")
        soft = (soft_curves or {}).get(name)
        if soft:
            stau = delay_floor_of_tau(np.asarray(soft["tau"], dtype=float))
            ssig = np.asarray(soft["significance"], dtype=float)
            alive = np.isfinite(ssig) & (ssig > floor) & (stau <= delay_max_ns)
            bot.plot(stau[alive], ssig[alive], color=color, lw=1.4,
                     ls=(0, (6, 2)), marker="s", ms=3.0, mfc="none",
                     label=f"{labels.get(name, name)}, soft cut")
    bot.set_yscale("log")
    bot.set_ylim(floor * 0.75, ceiling_max * 2.2)
    ymin, ymax = bot.get_ylim()
    for level, text in ((5.0, r"5$\sigma$"), (3.0, r"3$\sigma$")):
        bot.axhline(level, color=MUTED, lw=1.0)
        bot.text(3, level, f" {text}", color=INK2, fontsize=9,
                 va="bottom", ha="left")
    for tau, label in markers:
        bot.axvline(tau, color=BASELINE, lw=1.0, ls=":")
        if tau == tau_mask_ns:
            continue                      # labelled with the mask line
        bot.text(tau, ymin * 1.15, f" {tau:.0f} ns {label}", color=INK2,
                 fontsize=8.5, va="bottom", ha="left", rotation=90)
    bot.axvline(tau_mask_ns, color=CRITICAL, lw=1.1, ls="--", alpha=0.8)
    bot.text(tau_mask_ns, ymax * 0.9, f" {tau_mask_ns:.0f} ns kept today",
             color=CRITICAL, fontsize=8.5, va="top", ha="left", rotation=90)
    bot.set_xlim(0.0, delay_max_ns)
    bot.set_xlabel(r"retained delay floor $\tau_{\min}$ [ns]"
                   r"  (hard cut: $1.4\,\tau_{\rm cut}$)")
    bot.set_ylabel(r"BAO detection significance $A/\sigma_A$")
    bot.legend(loc="lower right", fontsize=8.4, bbox_to_anchor=(1.0, 0.10),
               handlelength=2.2)

    # -- shared top axis: k_par of a mode at that delay, z = 1.16 -------
    scale = kpar_of_delay(1.0)
    secondary = top.secondary_xaxis(
        "top", functions=(lambda t: np.asarray(t, dtype=float) * scale,
                          lambda k: np.asarray(k, dtype=float) / scale))
    secondary.set_xlabel(
        r"$k_\parallel$ at $z = %.2f$ [$h\,$Mpc$^{-1}$]" % z_reference)
    ticks_k = [0.1, 0.2, 0.3, 0.4, 0.5]
    secondary.set_xticks([k for k in ticks_k if k / scale <= delay_max_ns])
    secondary.xaxis.set_minor_formatter(NullFormatter())
    fig.suptitle("The discarded delay window, on the paper's own axis",
                 y=0.985, fontsize=12)
    return _save(fig, Path(outfile))


# ------------------------------------------------------------------- main
def _write_csv(path: Path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields,
                                lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    print(f"[taucut] wrote {path}")


def _fmt(value, digits=6):
    if value is None:
        return ""
    return "inf" if not np.isfinite(value) else f"{value:.{digits}g}"


def _sweep(configs, sweep_taus, sigma_nl, nproc, zref, cut="hard",
           only=None):
    """Run every (config, tau, zbin) at one sigma_NL and reduce to rows."""
    kind = "bao_soft" if cut == "soft" else "bao"
    names = [c for c in configs if only is None or c in only]
    tasks = [(config, tau, i, kind, sigma_nl)
             for config in names for tau in sweep_taus
             for i in range(len(configs[config]["zc"]))]
    results = _run(tasks, nproc)
    grouped: dict = {}
    schema: dict = {}
    for config, tau_ns, ibin, _kind, _s, F, paramnames in results:
        grouped.setdefault((config, tau_ns), {})[ibin] = F
        schema.setdefault((config, tau_ns), paramnames)

    label = _CTX["cosmo"]["sigma_nl"] if sigma_nl is None else sigma_nl
    rf = _CTX["rf"]
    sweep_rows, per_bin_rows = [], []
    curves: dict = {}
    for config in names:
        cfg = configs[config]
        nbins = len(cfg["zc"])
        curves[config] = {"tau": [], "significance": [], "no_cut": None}
        for tau in sweep_taus:
            matrices = grouped[(config, tau)]
            metrics = bao_metrics(rf, schema[(config, tau)],
                                  [matrices[i] for i in range(nbins)])
            sweep_rows.append({
                "config": config,
                "cut": cut,
                "sigma_nl_mpc": _fmt(label, 4),
                "tau_cut_ns": _fmt(tau, 4),
                "kpar_min_mpc": _fmt(
                    kpar_min_h(tau, zref) * _CTX["cosmo"]["h"], 5),
                "kpar_min_h_at_z1p16": _fmt(kpar_min_h(tau, zref), 5),
                "ttot_hours": _fmt(cfg["ttot_hours"], 6),
                "sarea_deg2": _fmt(cfg["sarea_deg2"], 6),
                "nzbins": nbins,
                "sigma_A": _fmt(metrics["sigma_A"]),
                "significance": _fmt(metrics["significance"]),
                "sigma_apar": _fmt(metrics["sigma_apar"]),
                "sigma_aperp": _fmt(metrics["sigma_aperp"]),
            })
            for i, entry in enumerate(metrics["per_bin"]):
                per_bin_rows.append({
                    "config": config,
                    "cut": cut,
                    "sigma_nl_mpc": _fmt(label, 4),
                    "tau_cut_ns": _fmt(tau, 4),
                    "zbin": f"{cfg['zs'][i]:.4f}-{cfg['zs'][i + 1]:.4f}",
                    "z_center": _fmt(cfg["zc"][i], 5),
                    "kpar_min_h": _fmt(kpar_min_h(tau, cfg["zc"][i]), 5),
                    "sigma_apar": _fmt(entry["sigma_apar"]),
                    "sigma_aperp": _fmt(entry["sigma_aperp"]),
                })
            if tau > 0.0:
                curves[config]["tau"].append(tau)
                curves[config]["significance"].append(metrics["significance"])
            else:
                curves[config]["no_cut"] = metrics["significance"]
    return sweep_rows, per_bin_rows, curves


def _threshold_rows(curves, sigma_nl_label, cut="hard"):
    rows = []
    for config, curve in curves.items():
        for target in THRESHOLDS:
            t0, s0, t1, s1, interp = read_off_threshold(
                curve["tau"], curve["significance"], target)
            rows.append({
                "config": config,
                "cut": cut,
                "sigma_nl_mpc": _fmt(sigma_nl_label, 4),
                "target_sigma": _fmt(target, 3),
                "no_cut_significance": _fmt(curve["no_cut"], 5),
                "tau_last_at_or_above_ns": _fmt(t0, 4),
                "significance_there": _fmt(s0, 5),
                "tau_first_below_ns": _fmt(t1, 4),
                "significance_below": _fmt(s1, 5),
                "tau_loglog_interp_ns": _fmt(interp, 4),
            })
    return rows


def _print_table(title, curves, sweep_taus):
    print(f"\n-- {title} --")
    names = list(curves)
    print(f"{'tau [ns]':>9}  " + "  ".join(f"{c:>20s}" for c in names))
    for tau in sweep_taus:
        label = "no cut" if tau == 0.0 else f"{tau:.0f}"
        values = []
        for name in names:
            if tau == 0.0:
                values.append(f"{curves[name]['no_cut']:20.3f}")
            else:
                j = curves[name]["tau"].index(tau)
                values.append(f"{curves[name]['significance'][j]:20.3f}")
        print(f"{label:>9}  " + "  ".join(values))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="out", help="output directory")
    ap.add_argument("--rf-dir", default=None)
    ap.add_argument("--cosmology", default="planck2018")
    ap.add_argument("--nproc", type=int, default=None)
    ap.add_argument("--tau-ns", type=float, nargs="+", default=None,
                    help=f"delay grid [ns] (default {list(TAU_NS_DEFAULT)})")
    ap.add_argument("--chime2025-ttot-hours", type=float, default=None,
                    help="override the published field's integration time "
                         "[h] (default 385)")
    ap.add_argument("--no-soft", action="store_true",
                    help="skip the soft-cut sweep of the archive")
    ap.add_argument("--no-sensitivity", action="store_true",
                    help="skip the second sweep at the sigma_NL that "
                         "reproduces the published 12.4 sigma")
    ap.add_argument("--no-figure", action="store_true")
    args = ap.parse_args(argv)

    out = Path(args.out)
    tau_grid = tuple(args.tau_ns) if args.tau_ns else TAU_NS_DEFAULT
    rf, rf_dir = _init_context(args.rf_dir, args.cosmology,
                               args.chime2025_ttot_hours)
    configs = _CTX["configs"]
    zref = survey.CHIME2025_Z_REFERENCE
    fiducial_sigma_nl = float(_CTX["cosmo"]["sigma_nl"])

    # ---------------------------------------------------- 1. calibration
    fiducial_cases = [
        ("calib_nl_lifted", survey.CHIME2025_TAU_CUT_NS, None),
        ("calib_nl_lifted", 0.0, None),
        ("calib_nl_default", survey.CHIME2025_TAU_CUT_NS, None),
        ("calib_undamped", survey.CHIME2025_TAU_CUT_NS,
         CALIBRATION_SIGMA_NL_UNDAMPED),
    ]
    sigma_nl_cases = [
        ("calib_sigma_nl_scan", survey.CHIME2025_TAU_CUT_NS, value)
        for value in CALIBRATION_SIGMA_NL_GRID
    ]
    calibration_configs = ("chime2025", "chime2025_masked")
    nbins2025 = len(configs["chime2025"]["zc"])
    tasks = [(config, tau, i, kind, sigma_nl)
             for config in calibration_configs
             for kind, tau, sigma_nl in fiducial_cases + sigma_nl_cases
             for i in range(nbins2025)]
    results = _run(tasks, args.nproc)

    sn2: dict = {}
    per_bin_sn: dict = {}
    for config, tau_ns, ibin, kind, sigma_nl, F, paramnames in results:
        ipk = paramnames.index("pk")
        key = (config, kind, tau_ns, sigma_nl)
        sn2[key] = sn2.get(key, 0.0) + float(F[ipk, ipk])
        per_bin_sn[key + (ibin,)] = float(F[ipk, ipk])

    published = survey.CHIME2025_DETECTION_SIGMA
    amplitude = survey.CHIME2025_DETECTION_SIGMA_AMPLITUDE
    calibration_rows = []
    for config in calibration_configs:
      for kind, tau, sigma_nl in fiducial_cases + sigma_nl_cases:
        key = (config, kind, tau, sigma_nl)
        total = np.sqrt(sn2[key])
        calibration_rows.append({
            "config": config,
            "case": kind,
            "tau_cut_ns": _fmt(tau, 4),
            "sigma_nl_mpc": _fmt(
                fiducial_sigma_nl if sigma_nl is None else sigma_nl, 4),
            "k_nl0_mpc": _fmt(0.14 if kind == "calib_nl_default"
                              else CALIBRATION_K_NL0, 4),
            "kpar_min_h_at_z1p16": _fmt(kpar_min_h(tau, zref), 4),
            "k_range_h": f"{survey.CHIME2025_KMIN_H}-{survey.CHIME2025_KMAX_H}",
            "total_sn": _fmt(total, 4),
            "published_sn": _fmt(published, 4),
            "ratio_to_published": _fmt(total / published, 4),
            "ratio_to_amplitude_sn": _fmt(total / amplitude, 4),
            **{f"sn_zbin{i}": _fmt(np.sqrt(per_bin_sn[key + (i,)]), 4)
               for i in range(nbins2025)},
        })

    def matched_sigma_nl(config, target):
        """sigma_NL reproducing ``target`` under the cut, by log-linear
        interpolation across the scan (S/N falls steeply and monotonically
        with sigma_NL over this grid)."""
        scan = np.array([np.sqrt(sn2[(config, "calib_sigma_nl_scan",
                                      survey.CHIME2025_TAU_CUT_NS, value)])
                         for value in CALIBRATION_SIGMA_NL_GRID])
        grid = np.array(CALIBRATION_SIGMA_NL_GRID, dtype=float)
        order = np.argsort(np.log(scan))
        return round(float(np.interp(np.log(target), np.log(scan)[order],
                                     grid[order])), 1)

    cal = {}
    for config in calibration_configs:
        head = np.sqrt(sn2[(config, "calib_nl_lifted",
                            survey.CHIME2025_TAU_CUT_NS, None)])
        cal[config] = {
            "headline": head,
            "uncut": np.sqrt(sn2[(config, "calib_nl_lifted", 0.0, None)]),
            "undamped": np.sqrt(sn2[(config, "calib_undamped",
                                     survey.CHIME2025_TAU_CUT_NS,
                                     CALIBRATION_SIGMA_NL_UNDAMPED)]),
            "match_f": matched_sigma_nl(config, published),
            "match_amp": matched_sigma_nl(config, amplitude),
            "ttot_factor": float(published / head),
        }
        for target, tag in ((published, "F"), (amplitude, "amplitude")):
            calibration_rows.append({
                "config": config,
                "case": f"calib_summary_{tag}",
                "tau_cut_ns": _fmt(survey.CHIME2025_TAU_CUT_NS, 4),
                "sigma_nl_mpc": _fmt(matched_sigma_nl(config, target), 4),
                "k_nl0_mpc": _fmt(CALIBRATION_K_NL0, 4),
                "kpar_min_h_at_z1p16": _fmt(
                    kpar_min_h(survey.CHIME2025_TAU_CUT_NS, zref), 4),
                "k_range_h": f"{survey.CHIME2025_KMIN_H}-"
                             f"{survey.CHIME2025_KMAX_H}",
                "total_sn": _fmt(target, 4),
                "published_sn": _fmt(published, 4),
                "ratio_to_published": _fmt(target / published, 4),
                "ratio_to_amplitude_sn": _fmt(target / amplitude, 4),
                **{f"sn_zbin{i}": "" for i in range(nbins2025)},
            })
    _write_csv(out / "taucut_calibration.csv", calibration_rows,
               list(calibration_rows[0]))

    # The headline calibration is the field as specified (2,200 deg^2).
    headline = cal["chime2025"]["headline"]
    uncut = cal["chime2025"]["uncut"]
    undamped = cal["chime2025"]["undamped"]
    ratio, uncut_ratio = headline / published, uncut / published
    sigma_nl_match = cal["chime2025"]["match_f"]
    ttot_factor = cal["chime2025"]["ttot_factor"]

    print(f"\n[calibration] total P(k) S/N, 0.4 < k < 1.5 h/Mpc, tau_cut = "
          f"200 ns, k_NL lifted (published F-based {published}, "
          f"amplitude-based {amplitude}):")
    for config in calibration_configs:
        c = cal[config]
        print(f"  {config:18s} sigma_NL = {fiducial_sigma_nl:.0f} Mpc: "
              f"{c['headline']:6.2f} ({c['headline'] / published:.2f}x)   "
              f"undamped: {c['undamped']:6.2f} "
              f"({c['undamped'] / published:.2f}x)   uncut: "
              f"{c['uncut']:6.2f} ({c['uncut'] / published:.2f}x)   "
              f"sigma_NL matching 12.4 / 13.6: {c['match_f']:.1f} / "
              f"{c['match_amp']:.1f} Mpc")
    print(f"[calibration] t_tot rescale that would force the as-specified "
          f"field onto 12.4 under the cut: x{ttot_factor:.1f}; not applied\n",
          flush=True)

    # ---------------------------------------------------------- 2. sweep
    sweep_taus = (0.0,) + tuple(tau_grid)      # 0 ns = the no-cut reference
    sweep_rows, per_bin_rows, curves = _sweep(
        configs, sweep_taus, None, args.nproc, zref)
    threshold_rows = _threshold_rows(curves, fiducial_sigma_nl)
    _print_table(f"A/sigma(A), sigma_NL = {fiducial_sigma_nl:.0f} Mpc "
                 "(fiducial)", curves, sweep_taus)

    curves_soft = None
    if not args.no_soft:
        rows_s, per_bin_s, curves_soft = _sweep(
            configs, sweep_taus, None, args.nproc, zref, cut="soft",
            only=SOFT_CUT_CONFIGS)
        sweep_rows += rows_s
        per_bin_rows += per_bin_s
        threshold_rows += _threshold_rows(curves_soft, fiducial_sigma_nl,
                                          cut="soft")
        _print_table(f"A/sigma(A), sigma_NL = {fiducial_sigma_nl:.0f} Mpc, "
                     "SOFT cut (Fig. 10 transfer on the signal)",
                     curves_soft, sweep_taus)

    curves_matched = None
    if not args.no_sensitivity:
        rows_m, per_bin_m, curves_matched = _sweep(
            configs, sweep_taus, sigma_nl_match, args.nproc, zref)
        sweep_rows += rows_m
        per_bin_rows += per_bin_m
        threshold_rows += _threshold_rows(curves_matched, sigma_nl_match)
        _print_table(f"A/sigma(A), sigma_NL = {sigma_nl_match:.1f} Mpc "
                     "(matched to the published detection)",
                     curves_matched, sweep_taus)

    _write_csv(out / "taucut_sweep.csv", sweep_rows, list(sweep_rows[0]))
    _write_csv(out / "taucut_sweep_perbin.csv", per_bin_rows,
               list(per_bin_rows[0]))
    _write_csv(out / "taucut_thresholds.csv", threshold_rows,
               list(threshold_rows[0]))

    print("\n-- thresholds read off the grid --")
    for row in threshold_rows:
        print(f"  {row['config']:20s} {row['cut']:4s} "
              f"sigma_NL={row['sigma_nl_mpc']:>4s}  "
              f"{row['target_sigma']}sigma: last at/above "
              f"{row['tau_last_at_or_above_ns'] or '-':>4s} ns "
              f"({row['significance_there'] or '-'}), first below "
              f"{row['tau_first_below_ns'] or '-':>4s} ns "
              f"({row['significance_below'] or '-'}); interp "
              f"{row['tau_loglog_interp_ns'] or '-'}")

    # --------------------------------------------------------- 3. figure
    caption = _caption(headline, ratio, uncut, uncut_ratio, undamped,
                       sigma_nl_match, ttot_factor, fiducial_sigma_nl,
                       curves, curves_matched, threshold_rows, cal,
                       curves_soft)
    (out / "fig_taucut_bao_caption.txt").write_text(caption)
    print(f"[taucut] wrote {out / 'fig_taucut_bao_caption.txt'}")
    if not args.no_figure:
        from rfisher import plots
        shown = [name for name, cfg in configs.items()
                 if cfg.get("figure", True)]
        path = plots.fig_taucut_significance(
            {name: {"tau": c["tau"], "significance": c["significance"]}
             for name, c in curves.items() if name in shown},
            {name: cfg["label"] for name, cfg in configs.items()},
            {name: c["no_cut"] for name, c in curves.items()
             if name in shown},
            soft_curves=({name: {"tau": c["tau"],
                                 "significance": c["significance"]}
                          for name, c in curves_soft.items()}
                         if curves_soft else None),
            kpar_min_of_tau=lambda tau: kpar_min_h(tau, zref),
            markers=TAU_NS_MARKERS,
            published_tau_ns=survey.CHIME2025_TAU_CUT_NS,
            z_reference=zref,
            outfile=out / "fig_taucut_bao.png")
        print(f"[taucut] wrote {path} (+ .pdf)")
        transition = rf.DELAY_TRANSITION_FACTOR
        path = fig_fig10_format(
            {name: {"tau": c["tau"], "significance": c["significance"]}
             for name, c in curves.items() if name in shown},
            {name: SHORT_LABELS.get(name, cfg["label"])
             for name, cfg in configs.items()},
            {name: c["no_cut"] for name, c in curves.items()
             if name in shown},
            ({name: {"tau": c["tau"], "significance": c["significance"]}
              for name, c in curves_soft.items()} if curves_soft else None),
            delay_floor_of_tau=lambda tau: transition * np.asarray(tau),
            kpar_of_delay=lambda delay: kpar_min_h(delay / transition, zref),
            residual_table=survey.filter_residual_table(),
            markers=TAU_NS_MARKERS,
            tau_cut_ns=survey.CHIME2025_TAU_CUT_NS,
            tau_mask_ns=survey.CHIME2025_TAU_MASK_NS,
            z_reference=zref,
            outfile=out / "fig_taucut_bao_fig10.png")
        print(f"[taucut] wrote {path} (+ .pdf)")
    return 0


def _caption(headline, ratio, uncut, uncut_ratio, undamped, sigma_nl_match,
             ttot_factor, sigma_nl_fiducial, curves, curves_matched,
             threshold_rows, cal=None, curves_soft=None):
    published = survey.CHIME2025_DETECTION_SIGMA
    amplitude = survey.CHIME2025_DETECTION_SIGMA_AMPLITUDE
    archive_h = survey.archive_hours()
    accepted = survey.accepted_sky_area_deg2()
    band = survey.accepted_declination_band_deg2()
    kept = 1.0 - survey.CHIME2025_SPATIAL_MASK_FRACTION

    def bracket(config, target, sigma_nl, cut="hard"):
        for row in threshold_rows:
            if (row["config"] == config
                    and row.get("cut", "hard") == cut
                    and float(row["target_sigma"]) == target
                    and float(row["sigma_nl_mpc"]) == float(sigma_nl)):
                if not row["tau_last_at_or_above_ns"]:
                    return "never reached"
                if not row["tau_first_below_ns"]:
                    return f">= {row['tau_last_at_or_above_ns']} ns"
                return (f"{row['tau_last_at_or_above_ns']}-"
                        f"{row['tau_first_below_ns']} ns")
        return "n/a"

    def sig(config, tau):
        c = curves[config]
        return c["significance"][c["tau"].index(tau)]

    lines = [
        "Figure: what the discarded k_par window is worth.",
        "",
        "BAO detection significance A/sigma(A) versus the delay cut tau_cut "
        "for three configurations. CHIME as published in the 2025 "
        "auto-correlation detection: 2,200 deg^2, 608.2-707.8 MHz in three "
        "dz ~ 0.11 bins, 385 h of effective integration from 94 nights, 0.5 "
        "mJy/beam per frequency channel, Tsys_tot = 55 K. The seven-year "
        "archive on the full Overview sky: 31,000 deg^2, 400-800 MHz in 15 "
        f"bins, seven calendar years at the 2019 cosmology-quality duty "
        f"cycle = {archive_h:,.0f} h = "
        f"{archive_h / survey.OVERVIEW_ONSKY_YEAR_HOURS:.2f} on-sky years. "
        "The same archive on the sky the present pipeline accepts: |y| < "
        f"0.4 (declinations {survey.CHIME_LATITUDE_DEG - 23.58:.1f}-"
        f"{survey.CHIME_LATITUDE_DEG + 23.58:.1f} deg, {band:,.0f} deg^2) "
        f"less the {100 * (1 - kept):.0f}% spatial mask of the paper's "
        f"Section 5.2, {accepted:,.0f} deg^2, at the same per-voxel depth, "
        "i.e. t_tot scaled with the area: a declination cut or a spatial "
        "mask loses volume without deepening what it keeps. The same mask "
        f"applies to the published field itself ({survey.CHIME2025_SAREA_DEG2 * kept:,.0f} "
        "of its 2,200 deg^2 enter the power spectrum); that variant is "
        "tabulated, not drawn. The dashed archive line is the soft cut: the "
        "paper's Fig. 10 filter response, digitised from the vector figure, "
        "scaled in tau / tau_cut, normalised to its high-delay plateau and "
        "squared, multiplying the signal in place of the hard excision. "
        "Applied to the signal alone it is a conservative bound, since the "
        "filter attenuates the noise as well; the hard and soft lines "
        "bracket the transition zone. The "
        "published analysis filters at tau_cut = 200 ns and discards "
        "everything below the 280 ns mask, so it begins at k_par = 0.35 "
        "h/Mpc; the top axis gives k_par,min at z = 1.16 for each tau_cut, "
        "including that 1.4x transition factor. Contamination residuals "
        "are zero: this prices the modes the cut removes, not the leakage "
        "left in the modes it keeps.",
        "",
        "Companion figure (fig_taucut_bao_fig10): the same curves on the "
        "delay axis of the paper's Fig. 10, two panels sharing it. The top "
        "panel is their filter's RMS residual against the delay of a mode, "
        "with the same gray (below the 200 ns cut) and pink (200-280 ns "
        "transition) shading; the bottom panel is the BAO significance "
        "against the retained delay floor tau_min = 1.4 tau_cut, which is "
        "the same quantity as their axis: the delay above which modes are "
        "kept. Thresholds on that axis are the tau_cut brackets times 1.4 "
        "(full-sky archive 5 sigma at 175-196 ns, accepted sky 140-154 ns, "
        "soft cut 196-210 ns), and 'current' is 280 ns as in the text.",
        "",
        "Thresholds, read off the grid as the bracket [last delay at or "
        "above, first delay below], sigma_NL = "
        f"{sigma_nl_fiducial:.0f} Mpc:",
    ]
    for config in curves:
        lines.append(
            f"  {config:20s} 5 sigma: {bracket(config, 5.0, sigma_nl_fiducial):>14s}"
            f"   3 sigma: {bracket(config, 3.0, sigma_nl_fiducial):>14s}"
            f"   no cut: {curves[config]['no_cut']:.2f}")
    if curves_soft:
        for config in curves_soft:
            lines.append(
                f"  {config + ' (soft)':20s} 5 sigma: "
                f"{bracket(config, 5.0, sigma_nl_fiducial, 'soft'):>14s}"
                f"   3 sigma: {bracket(config, 3.0, sigma_nl_fiducial, 'soft'):>14s}"
                f"   no cut: {curves_soft[config]['no_cut']:.2f}")
    lines += [
        "",
        "Noise-model calibration. The total power-spectrum S/N over 0.4 < k "
        "< 1.5 h/Mpc with tau_cut = 200 ns is sqrt(F_pk,pk) = sqrt(sum over "
        "modes of (P_sig / sigma_P)^2), a single-amplitude total S/N and not "
        f"the wiggle amplitude; the paper's amplitude-based {amplitude} "
        f"sigma is the closer analogue to it, its F-based {published} the "
        f"headline. At the fiducial sigma_NL = "
        f"{sigma_nl_fiducial:.0f} Mpc it gives {headline:.1f} against "
        f"{published} ({ratio:.2f}x); with the small-scale "
        f"damping removed it gives {undamped:.0f} ({undamped / published:.1f}x); "
        f"sigma_NL = {sigma_nl_match:.1f} Mpc reproduces {published}"
        + (f" ({cal['chime2025']['match_amp']:.1f} Mpc for {amplitude}; on "
           f"the masked field {cal['chime2025_masked']['match_f']:.1f} and "
           f"{cal['chime2025_masked']['match_amp']:.1f} Mpc)"
           if cal else "")
        + ". The "
        "statistic is sensitive to sigma_NL because RadioFisher applies "
        "exp(-mu^2 k^2 sigma_NL^2) to the whole 21 cm power and the delay "
        "cut leaves only the mu ~ 1 modes that term acts on; it is a "
        "measurement of small-scale damping, not of the noise. The noise "
        f"normalisation is checked uncut: the same band with no delay cut "
        f"gives {uncut:.1f} ({uncut_ratio:.2f}x), within 1.5x, so t_tot is "
        f"not rescaled (x{ttot_factor:.1f} would be needed under the cut). "
        "The BAO sweep runs at the fiducial sigma_NL; at the matched value "
        "the thresholds move by",
    ]
    if curves_matched is not None:
        for config in curves:
            lines.append(
                f"  {config:20s} 5 sigma: "
                f"{bracket(config, 5.0, sigma_nl_fiducial):>14s} -> "
                f"{bracket(config, 5.0, sigma_nl_match):>14s}"
                f"   3 sigma: {bracket(config, 3.0, sigma_nl_fiducial):>14s}"
                f" -> {bracket(config, 3.0, sigma_nl_match):>14s}")
    else:
        lines.append("  (sensitivity sweep not run)")
    lines += [
        "RadioFisher's k_NL cutoff (0.14 Mpc^-1 at z = 0) lands at 0.35 "
        "h/Mpc at z = 1.16 and deletes the entire detection band; it is "
        "lifted for the calibration step only and restored for the sweep.",
        "",
        "Key values (A/sigma(A), fiducial):",
    ]
    grid = set.intersection(*(set(c["tau"]) for c in curves.values()))
    for tau in (50.0, 100.0, 125.0, 150.0, 200.0, 280.0):
        if tau not in grid:
            continue
        lines.append(f"  tau_cut {tau:5.0f} ns  " + "   ".join(
            f"{config} {sig(config, tau):6.2f}" for config in curves))
    lines += [
        "",
        "Sources: Amiri et al. 2025 (arXiv:2511.19620v2) for the field "
        "(Eq. 46), 94 nights, 385 h (Fig. 5), 0.5 mJy/beam, the |y| < 0.4 "
        "selection, the Section 5.2 spatial mask, the 200 ns cut, the "
        "280 ns mask and Fig. 10 (Sec. 5.3), and the 12.4 / 13.0 / 13.6 "
        "sigma of Table 3; Amiri et al. 2022 (ApJS 261, 29) Appendix A "
        "for the instrument model, Tsys_tot = 55 K, the BAO-shift-only "
        "Fisher settings and the fiducial cosmology.",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
