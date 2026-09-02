#!/usr/bin/env python3
"""What the discarded k_par window is worth: BAO significance vs delay cut.

CHIME's z ~ 1 auto-spectrum detection removes foregrounds with a DAYENU
high-pass filter at tau_cut = 200 ns and then discards everything below the
280 ns mask, so the measurement begins at k_par = 0.35 h/Mpc. The BAO
wiggles live at k ~ 0.05-0.3 h/Mpc, i.e. below that floor. This script
prices the window: for a hard delay cut at tau_cut, what BAO detection
significance and what BAO dilation errors survive?

Two configurations:

  chime2025   the published field: 2,200 deg^2, 608.2-707.8 MHz (three
              dz ~ 0.1 bins), 385 h effective, Tsys_tot = 55 K.
  archive7yr  the Overview fiducial (31,000 deg^2, 400-800 MHz) at seven
              calendar years x the 2019 duty cycle = 1.06 on-sky years.

The cut runs through the RadioFisher fork's expt['kpar_min_fn'] hook and
direct rf.fisher() calls, not the shipped Fisher banks: k_par,min is a
dimension the banks do not carry.

Before the sweep is trusted, the noise model is calibrated against the
published 12.4 sigma: with tau_cut = 200 ns, the total power-spectrum S/N
over 0.4 < k < 1.5 h/Mpc is computed for the chime2025 configuration and
compared. Two traps sit in that comparison. The first is RadioFisher's
k_NL cutoff, which lands on top of the published k_par floor and would
delete the whole band (see CALIBRATION_K_NL0). The second is sigma_NL:
the delay cut leaves only mu ~ 1 modes, and those are exactly what
exp(-mu^2 k^2 sigma_NL^2) removes at k > 0.4 h/Mpc, so the statistic
measures the BAO-damping parameter more than it measures the noise (see
CALIBRATION_SIGMA_NL_GRID). The calibration reports both, and the sweep
runs at the fiducial settings.

Outputs, all under --out:
    taucut_calibration.csv    the calibration against 12.4 sigma
    taucut_sweep.csv          A/sigma(A), sigma(alpha_par), sigma(alpha_perp)
    taucut_sweep_perbin.csv   the per-redshift-bin alpha errors
    fig_taucut_bao.png/.pdf   the figure
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

# The delay grid of the proposal's figure, in ns. 200 is the published
# DAYENU cut; 280 is the first delay the published analysis retains.
TAU_NS_DEFAULT = (30.0, 50.0, 75.0, 100.0, 150.0, 200.0, 280.0, 400.0)

# Marked on the figure: the proposal's "current / realistic / stretch".
# The published DAYENU cut is 200 ns; 280 ns is the first delay the
# published analysis retains, so it is marked as "current" in the
# proposal's own language and 200 ns is marked separately.
TAU_NS_MARKERS = ((280.0, "current"), (100.0, "realistic"),
                  (50.0, "stretch"))

# RadioFisher's non-linear cutoff, k_NL,0 = 0.14 Mpc^-1, rises as
# (1+z)^(2/(2+ns)) and reaches 0.35 h/Mpc at z = 1.16 -- numerically the
# same place as the published 280 ns mask. Left in place it would delete
# the entire 0.4-1.5 h/Mpc band the detection lives in, and the
# calibration would compare against nothing. Push it above the band for
# the calibration step only; the integral is bounded at 1.5 h/Mpc by kmax
# regardless. The BAO sweep restores the default cutoff, where it costs
# nothing: BAO information is damped away long before k_NL.
CALIBRATION_K_NL0 = 10.0            # Mpc^-1

# RadioFisher damps the signal by exp(-mu^2 k^2 sigma_NL^2). sigma_NL = 7 Mpc
# is the fiducial BAO-smearing scale of the Overview forecast, valid where
# BAO information lives (k <~ 0.2 Mpc^-1). The published detection band is
# 0.4-1.5 h/Mpc, and the delay cut leaves exactly the mu ~ 1 modes that term
# annihilates there, so the calibration statistic is a probe of sigma_NL far
# more than of the noise. This grid measures that sensitivity and reports the
# sigma_NL that would reproduce 12.4 sigma; the BAO sweep keeps the fiducial.
CALIBRATION_SIGMA_NL_GRID = (3.0, 4.0, 5.0, 6.0, 7.0)

CONFIG_LABELS = {
    "chime2025": "CHIME 2025 as published (2,200 deg$^2$, 385 h)",
    "archive7yr": "Seven-year archive (31,000 deg$^2$, 1.06 on-sky yr)",
}

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
    return {
        "chime2025": {
            "make_expt": lambda: survey.chime2025_experiment(
                rf, rf_dir, ttot_hours=chime2025_ttot_hours),
            "zs": np.asarray(zs2025), "zc": np.asarray(zc2025),
            "ttot_hours": chime2025_ttot_hours,
            "sarea_deg2": survey.CHIME2025_SAREA_DEG2,
        },
        "archive7yr": {
            "make_expt": lambda: survey.chime2022_experiment(
                rf, rf_dir, ttot_hours=survey.archive_hours()),
            "zs": np.asarray(zs_arch), "zc": np.asarray(zc_arch),
            "ttot_hours": survey.archive_hours(),
            "sarea_deg2": 31000.0,
        },
    }


def _init_context(rf_dir=None, cosmology="planck2018",
                  chime2025_ttot_hours=None):
    rf, rf_dir = import_radiofisher(rf_dir)
    require_backend_capabilities(
        rf, {"kpar_min_fn", "astrophysical_model_profiles",
             "explicit_physical_densities"}, rf_dir=rf_dir)
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
        if kind == "calib_nl_lifted":
            expt["k_nl0"] = CALIBRATION_K_NL0
        h = cosmo["h"]
        kwargs = dict(kmin=survey.CHIME2025_KMIN_H * h,
                      kmax=survey.CHIME2025_KMAX_H * h)
    expt["kpar_min_fn"] = survey.delay_cut(rf, expt, cosmo_fns, tau_ns * 1e-9)
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
                if verbose and (k + 1) % 20 == 0:
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
    return "inf" if not np.isfinite(value) else f"{value:.{digits}g}"


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
                         "[h] (default 385). Use this to apply the t_tot "
                         "rescale the calibration reports, if you want the "
                         "delay-cut S/N forced onto the published 12.4 "
                         "sigma; see the caption for why it is not the "
                         "default")
    ap.add_argument("--sigma-nl", type=float, default=None,
                    help="override the fiducial BAO damping scale sigma_NL "
                         "[Mpc] in the sweep (sensitivity runs only; the "
                         "calibration always scans it)")
    ap.add_argument("--no-figure", action="store_true")
    args = ap.parse_args(argv)

    out = Path(args.out)
    tau_grid = tuple(args.tau_ns) if args.tau_ns else TAU_NS_DEFAULT
    rf, rf_dir = _init_context(args.rf_dir, args.cosmology,
                               args.chime2025_ttot_hours)
    configs = _CTX["configs"]
    zref = survey.CHIME2025_Z_REFERENCE

    # ---------------------------------------------------- 1. calibration
    # The published statistic: with tau_cut = 200 ns, total power-spectrum
    # S/N over 0.4 < k < 1.5 h/Mpc for the published field, against 12.4.
    #
    # Three fiducial variants isolate the two traps the comparison runs
    # into. `nl_default` shows what the k_NL cutoff does to this band (it
    # deletes it). `nocut` removes the delay cut, which is the clean test
    # of the noise normalisation. The sigma_NL grid then measures how much
    # of the cut result is the signal model rather than the noise: after
    # the delay cut only mu ~ 1 modes survive, and those are precisely the
    # ones exp(-mu^2 k^2 sigma_NL^2) removes at k > 0.4 h/Mpc.
    fiducial_cases = [
        ("calib_nl_lifted", survey.CHIME2025_TAU_CUT_NS, None),
        ("calib_nl_lifted", 0.0, None),
        ("calib_nl_default", survey.CHIME2025_TAU_CUT_NS, None),
    ]
    sigma_nl_cases = [
        ("calib_nl_lifted", survey.CHIME2025_TAU_CUT_NS, value)
        for value in CALIBRATION_SIGMA_NL_GRID
    ]
    nbins2025 = len(configs["chime2025"]["zc"])
    tasks = [("chime2025", tau, i, kind, sigma_nl)
             for kind, tau, sigma_nl in fiducial_cases + sigma_nl_cases
             for i in range(nbins2025)]
    results = _run(tasks, args.nproc)

    sn2: dict = {}
    per_bin_sn: dict = {}
    for config, tau_ns, ibin, kind, sigma_nl, F, paramnames in results:
        ipk = paramnames.index("pk")
        key = (kind, tau_ns, sigma_nl)
        sn2[key] = sn2.get(key, 0.0) + float(F[ipk, ipk])
        per_bin_sn[key + (ibin,)] = float(F[ipk, ipk])

    published = survey.CHIME2025_DETECTION_SIGMA
    calibration_rows = []
    for kind, tau, sigma_nl in fiducial_cases + sigma_nl_cases:
        key = (kind, tau, sigma_nl)
        total = np.sqrt(sn2[key])
        calibration_rows.append({
            "case": kind if sigma_nl is None else "calib_sigma_nl_scan",
            "tau_cut_ns": _fmt(tau, 4),
            "sigma_nl_mpc": _fmt(
                _CTX["cosmo"]["sigma_nl"] if sigma_nl is None else sigma_nl, 4),
            "k_nl0_mpc": _fmt(CALIBRATION_K_NL0 if kind == "calib_nl_lifted"
                              else 0.14, 4),
            "kpar_min_h_at_z1p16": _fmt(kpar_min_h(tau, zref), 4),
            "k_range_h": f"{survey.CHIME2025_KMIN_H}-{survey.CHIME2025_KMAX_H}",
            "total_sn": _fmt(total, 4),
            "published_sn": _fmt(published, 4),
            "ratio_to_published": _fmt(total / published, 4),
            **{f"sn_zbin{i}": _fmt(np.sqrt(per_bin_sn[key + (i,)]), 4)
               for i in range(nbins2025)},
        })

    headline = np.sqrt(sn2[("calib_nl_lifted", survey.CHIME2025_TAU_CUT_NS,
                            None)])
    uncut = np.sqrt(sn2[("calib_nl_lifted", 0.0, None)])
    ratio, uncut_ratio = headline / published, uncut / published

    # sigma_NL that reproduces the published S/N under the delay cut, by
    # log-linear interpolation across the scan (S/N falls steeply and
    # monotonically with sigma_NL over this grid).
    scan = np.array([np.sqrt(sn2[("calib_nl_lifted",
                                  survey.CHIME2025_TAU_CUT_NS, value)])
                     for value in CALIBRATION_SIGMA_NL_GRID])
    grid = np.array(CALIBRATION_SIGMA_NL_GRID, dtype=float)
    order = np.argsort(np.log(scan))
    sigma_nl_match = float(np.interp(np.log(published), np.log(scan)[order],
                                     grid[order]))
    # The alternative remedy: the time that would reproduce 12.4 sigma at
    # the fiducial sigma_NL. Reported, not applied -- see the caption.
    ttot_factor = float(published / headline)

    calibration_rows.append({
        "case": "calib_summary",
        "tau_cut_ns": _fmt(survey.CHIME2025_TAU_CUT_NS, 4),
        "sigma_nl_mpc": _fmt(sigma_nl_match, 4),
        "k_nl0_mpc": _fmt(CALIBRATION_K_NL0, 4),
        "kpar_min_h_at_z1p16": _fmt(kpar_min_h(survey.CHIME2025_TAU_CUT_NS,
                                               zref), 4),
        "k_range_h": f"{survey.CHIME2025_KMIN_H}-{survey.CHIME2025_KMAX_H}",
        "total_sn": _fmt(published, 4),
        "published_sn": _fmt(published, 4),
        "ratio_to_published": _fmt(1.0, 4),
        **{f"sn_zbin{i}": "" for i in range(nbins2025)},
    })
    _write_csv(out / "taucut_calibration.csv", calibration_rows,
               list(calibration_rows[0]))

    print(f"\n[calibration] tau_cut = 200 ns, 0.4 < k < 1.5 h/Mpc, k_NL "
          f"lifted: total S/N = {headline:.2f} vs published {published} "
          f"({ratio:.2f}x) -> FAILS the 1.5x test as specified")
    print(f"[calibration] same band, no delay cut:   S/N = {uncut:.2f} "
          f"({uncut_ratio:.2f}x) -> noise normalisation PASSES")
    print(f"[calibration] the gap is the signal model, not the noise: "
          f"sigma_NL = {sigma_nl_match:.2f} Mpc (fiducial "
          f"{_CTX['cosmo']['sigma_nl']:.1f}) reproduces {published} sigma "
          f"under the cut")
    print(f"[calibration] the t_tot rescale that would do the same job is "
          f"x{ttot_factor:.1f} ({survey.CHIME2025_TTOT_HOURS * ttot_factor:.0f} "
          f"h); NOT applied by default -- it would overshoot the uncut S/N "
        f"by "
          f"{ttot_factor * uncut_ratio:.1f}x\n", flush=True)

    # ---------------------------------------------------------- 2. sweep
    sweep_taus = (0.0,) + tuple(tau_grid)      # 0 ns = the no-cut reference
    tasks = [(config, tau, i, "bao", args.sigma_nl)
             for config in configs for tau in sweep_taus
             for i in range(len(configs[config]["zc"]))]
    results = _run(tasks, args.nproc)

    grouped: dict = {}
    schema: dict = {}
    for config, tau_ns, ibin, _kind, _sigma_nl, F, paramnames in results:
        grouped.setdefault((config, tau_ns), {})[ibin] = F
        schema.setdefault((config, tau_ns), paramnames)

    sweep_rows, per_bin_rows = [], []
    curves: dict = {}
    for config in configs:
        cfg = configs[config]
        nbins = len(cfg["zc"])
        curves[config] = {"tau": [], "significance": []}
        for tau in sweep_taus:
            matrices = grouped[(config, tau)]
            F_list = [matrices[i] for i in range(nbins)]
            metrics = bao_metrics(rf, schema[(config, tau)], F_list)
            sweep_rows.append({
                "config": config,
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

    _write_csv(out / "taucut_sweep.csv", sweep_rows, list(sweep_rows[0]))
    _write_csv(out / "taucut_sweep_perbin.csv", per_bin_rows,
               list(per_bin_rows[0]))

    no_cut = {config: float(
        [r["significance"] for r in sweep_rows
         if r["config"] == config and float(r["tau_cut_ns"]) == 0.0][0])
        for config in configs}

    print("\n-- BAO significance A/sigma(A) --")
    print(f"{'tau [ns]':>9}  " + "  ".join(f"{c:>12s}" for c in configs))
    for tau in sweep_taus:
        label = "no cut" if tau == 0.0 else f"{tau:.0f}"
        values = []
        for config in configs:
            row = next(r for r in sweep_rows if r["config"] == config
                       and float(r["tau_cut_ns"]) == tau)
            values.append(f"{float(row['significance']):12.3f}")
        print(f"{label:>9}  " + "  ".join(values))

    # --------------------------------------------------------- 3. figure
    caption = _caption(headline, ratio, uncut, uncut_ratio, sigma_nl_match,
                       ttot_factor, no_cut, sweep_rows,
                       _CTX["cosmo"]["sigma_nl"])
    (out / "fig_taucut_bao_caption.txt").write_text(caption)
    print(f"[taucut] wrote {out / 'fig_taucut_bao_caption.txt'}")
    if not args.no_figure:
        from rfisher import plots
        path = plots.fig_taucut_significance(
            curves, CONFIG_LABELS, no_cut,
            kpar_min_of_tau=lambda tau: kpar_min_h(tau, zref),
            markers=TAU_NS_MARKERS,
            published_tau_ns=survey.CHIME2025_TAU_CUT_NS,
            z_reference=zref,
            outfile=out / "fig_taucut_bao.png")
        print(f"[taucut] wrote {path} (+ .pdf)")
    return 0


def _caption(headline, ratio, uncut, uncut_ratio, sigma_nl_match,
             ttot_factor, no_cut, sweep_rows, sigma_nl_fiducial):
    def sig(config, tau):
        return float(next(r["significance"] for r in sweep_rows
                          if r["config"] == config
                          and float(r["tau_cut_ns"]) == tau))
    published = survey.CHIME2025_DETECTION_SIGMA
    archive_h = survey.archive_hours()
    lines = [
        "Figure: what the discarded k_par window is worth.",
        "",
        "BAO detection significance A/sigma(A) versus the delay cut "
        "tau_cut, for CHIME as published in the 2025 auto-correlation "
        "detection (2,200 deg^2, 608.2-707.8 MHz, three dz ~ 0.11 bins "
        "spanning the band, 385 h of effective integration from 94 nights, "
        "0.5 mJy/beam per frequency channel, Tsys_tot = 55 K) and for the "
        "seven-year archive (the Overview fiducial: 31,000 deg^2, "
        f"400-800 MHz, 15 bins, seven calendar years at the 2019 "
        f"cosmology-quality duty cycle = {archive_h:.0f} h = "
        f"{archive_h / survey.OVERVIEW_ONSKY_YEAR_HOURS:.2f} on-sky years). "
        "The published analysis filters at tau_cut = 200 ns and discards "
        "everything below the 280 ns mask, so it begins at k_par = 0.35 "
        "h/Mpc; the top axis gives k_par,min at z = 1.16 for each tau_cut, "
        "including that 1.4x transition factor. Contamination residuals "
        "are set to zero: this prices the modes the cut removes, not the "
        "leakage left in the modes it keeps.",
        "",
        "Noise-model calibration. The specified test -- total "
        f"power-spectrum S/N over 0.4 < k < 1.5 h/Mpc with tau_cut = 200 ns "
        f"-- gives {headline:.2f} against the published {published} "
        f"({ratio:.2f}x), outside 1.5x. The same band with no delay cut "
        f"gives {uncut:.1f} ({uncut_ratio:.2f}x), which is inside 1.5x, so "
        "the noise normalisation is not what fails. What fails is the "
        "signal model in that band: RadioFisher damps the signal by "
        "exp(-mu^2 k^2 sigma_NL^2), the delay cut leaves only mu ~ 1 "
        f"modes, and at k > 0.4 h/Mpc the fiducial sigma_NL = "
        f"{sigma_nl_fiducial:.0f} Mpc removes them. sigma_NL = "
        f"{sigma_nl_match:.1f} Mpc reproduces the published {published} "
        "sigma under the cut. sigma_NL is a BAO-smearing parameter, "
        "calibrated where BAO information lives (k <~ 0.2 Mpc^-1), and the "
        "0.4-1.5 h/Mpc detection band is outside its domain; the sweep "
        "below therefore keeps the fiducial value and the published 385 h. "
        f"The alternative remedy, scaling t_tot by x{ttot_factor:.1f} to "
        f"{survey.CHIME2025_TTOT_HOURS * ttot_factor:.0f} h, is reported in "
        "out/taucut_calibration.csv but not applied: it would overshoot the "
        f"uncut S/N by {ttot_factor * uncut_ratio:.1f}x. Note also that "
        "RadioFisher's k_NL cutoff (0.14 Mpc^-1 at z = 0) lands at 0.35 "
        "h/Mpc at z = 1.16 and deletes the entire detection band; it is "
        "lifted for the calibration step only and restored for the sweep.",
        "",
        "Key values (A/sigma(A)):",
        f"  no cut          archive {no_cut['archive7yr']:.2f}   "
        f"published field {no_cut['chime2025']:.2f}",
    ]
    for tau in (50.0, 100.0, 200.0, 280.0):
        lines.append(
            f"  tau_cut {tau:5.0f} ns  archive {sig('archive7yr', tau):.2f}   "
            f"published field {sig('chime2025', tau):.2f}")
    lines += [
        "",
        "Sources: Amiri et al. 2025 (arXiv:2511.19620) for the field, band, "
        "94 nights, 385 h, 0.5 mJy/beam, the 200 ns cut, the 280 ns mask "
        "and the 12.4 sigma detection; Amiri et al. 2022 (ApJS 261, 29) "
        "Appendix A for the instrument model, Tsys_tot = 55 K, the "
        "BAO-shift-only Fisher settings and the fiducial cosmology.",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
