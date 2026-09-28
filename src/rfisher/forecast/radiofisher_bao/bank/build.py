"""The bank build command: ``rfisher build-bank``.

Everything a build sets beyond ``banks.build_bank``'s own defaults is set
here: the integration-time grid (the log grid, the dense points through the
cosmic-variance knee and any extra times), the residual template carried as
the ``_Pres`` row, the delay-filter mode cut, and the conventional file
names. It lives in the bank subpackage because it determines what a bank
holds.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from .banks import build_bank
from .experiments import SUPPORTED_COSMOLOGIES, resolve_cosmology
from .templates import FAMILIES, make_template, parse_parameter_assignments

# The dense-knee span, in log10(hours). The default reproduces every bank
# built before the span became an option.
DEFAULT_KNEE_RANGE = (3.5, 5.83)
DEFAULT_KNEE_N = 8


def time_grid(tmin: float, tmax: float, nt: int, *, dense_knee: bool = False,
              knee_range=DEFAULT_KNEE_RANGE, knee_n: int = DEFAULT_KNEE_N,
              extra_hours=()) -> np.ndarray:
    """The integration times of a bank, in hours.

    A log grid of ``nt`` points over ``[tmin, tmax]``; with ``dense_knee``,
    ``knee_n`` further points spaced evenly in log10(hours) over
    ``knee_range``; and any ``extra_hours``, each of which must lie inside
    ``[tmin, tmax]``. The extra points never move the base grid.
    """
    if nt < 2:
        raise ValueError("--nt must be at least 2")
    tgrid = np.logspace(np.log10(tmin), np.log10(tmax), nt)
    if dense_knee:
        lo, hi = knee_range
        extra = 10.0 ** np.linspace(lo, hi, knee_n)
        tgrid = np.unique(np.concatenate([tgrid, extra]))
    if len(extra_hours):
        extra = np.asarray(extra_hours, dtype=float)
        if (not np.all(np.isfinite(extra)) or np.any(extra <= 0.0)
                or np.any(extra < tmin) or np.any(extra > tmax)):
            raise ValueError(
                "--extra-time-hours must be finite, positive, and within "
                "[--tmin, --tmax]")
        tgrid = np.unique(np.concatenate([tgrid, extra]))
    return tgrid


def expt_overrides(*, p_res: float | None = None,
                   residual_template: str | None = None,
                   template_parameters=(),
                   kfg_fac: float | None = None) -> dict | None:
    """The experiment overrides of a build, or None when there are none.

    ``p_res`` is a unit-amplitude residual proportional to the thermal noise;
    ``residual_template`` names an analytic family instead, with
    ``template_parameters`` as ``NAME=VALUE`` strings.
    """
    if p_res is not None and residual_template is not None:
        raise ValueError("choose at most one of --p-res and --residual-template")
    overrides = {}
    if p_res is not None:
        overrides["P_res"] = p_res
    if residual_template is not None:
        overrides["P_res"] = make_template(
            residual_template, parse_parameter_assignments(template_parameters))
    elif template_parameters:
        raise ValueError("--template-param requires --residual-template")
    if kfg_fac is not None:
        overrides["kfg_fac"] = kfg_fac
    return overrides or None


def default_bank_name(*, config: str, cosmology: str | None,
                      epsilon_fg: float, p_res: float | None = None,
                      residual_template: str | None = None,
                      kfg_fac: float | None = None,
                      dense_knee: bool = False) -> str:
    """The conventional file name of a bank built with these settings.

    A ``_Pres`` bank carries an extra parameter row and is not
    interchangeable with a plain one, so it never takes a plain name.
    """
    cosmology = resolve_cosmology(config, cosmology)
    ctag = (f"_{cosmology}" if cosmology
            and cosmology != "planck2018" else "")
    if residual_template is not None:
        ptag = f"_pres_{residual_template}"
    else:
        ptag = "_pres" if p_res is not None else ""
    if kfg_fac is not None:
        ptag += f"_kfg{kfg_fac:g}"
    ktag = "_dense" if dense_knee else ""
    fg_tag = (f"{epsilon_fg:.0e}"
              .replace("e-0", "e-").replace("e+0", "e+"))
    return (f"fisher_bank_chime2022{ctag}{ptag}{ktag}.npz"
            if config == "chime2022"
            else f"fisher_bank_bull2015_planck2013_epsfg{fg_tag}{ptag}{ktag}.npz")


def build_parser(prog: str = "rfisher build-bank") -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog=prog,
        description="Build a provenance-complete Fisher bank over a grid of "
                    "integration times (slow).")
    ap.add_argument(
        "-o", "--out", type=Path, required=True,
        help="output file; an existing directory receives the conventional "
             "file name for these settings")
    ap.add_argument("--radiofisher-dir", type=Path)
    ap.add_argument("--config", choices=("bull2015", "chime2022"),
                    default="chime2022")
    ap.add_argument(
        "--cosmology",
        choices=sorted(set().union(*SUPPORTED_COSMOLOGIES.values()) - {None}),
        default=None,
        help="named fiducial (default: planck2013 for bull2015, "
             "cmbspa2026 for chime2022)")
    ap.add_argument("--tmin", type=float, default=1.0, help="hours")
    ap.add_argument("--tmax", type=float, default=1e6, help="hours")
    ap.add_argument("--nt", type=int, default=19, help="time grid points")
    ap.add_argument(
        "--extra-time-hours", action="append", type=float, default=[],
        metavar="HOURS",
        help="insert an additional interpolation-grid time without moving the "
             "base log grid; repeat for multiple points")
    ap.add_argument("--dense-knee", action="store_true",
                    help="add points through the cosmic-variance knee")
    ap.add_argument("--knee-range", nargs=2, type=float,
                    default=DEFAULT_KNEE_RANGE,
                    metavar=("LOG10_LO", "LOG10_HI"),
                    help="log10(hours) span the --dense-knee points cover; the "
                         "default reproduces every bank built before this flag "
                         "existed. Widen it to cover wherever the quantity you "
                         "are refining actually moves.")
    ap.add_argument("--knee-n", type=int, default=DEFAULT_KNEE_N,
                    help="number of --dense-knee points")
    ap.add_argument("--nproc", type=int, default=None)
    ap.add_argument("--epsilon-fg", type=float, default=1e-6)
    ap.add_argument("--k-nl0", type=float, default=0.14)
    ap.add_argument("--kfg-fac", type=float, default=None, metavar="KFG",
                    help="delay-filter mode cut, kfg_fac = tau_cut_s * survey "
                         "bandwidth_Hz (CHIME: 22 for the 55 ns first-peak-"
                         "preserving cut, 44 for 110 ns, 80 for the deployed "
                         "200 ns). This prices cosmological mode loss only. "
                         "Residual suppression is a separate hypothetical "
                         "assumption, not a transfer measured by this bank.")
    residual = ap.add_mutually_exclusive_group()
    residual.add_argument(
        "--p-res", type=float, default=None, metavar="AMPLITUDE",
        help="add a residual-contamination template at this multiple of the "
             "noise power, carried as a '_Pres' row in the Fisher matrix. Use "
             "1.0: the bias is linear in the amplitude, so one build serves "
             "every r, and the response evaluation assumes unit "
             "normalization.")
    residual.add_argument(
        "--residual-template", choices=FAMILIES,
        help="named unit-amplitude analytic P_res family; unlike an empirical "
             "visibility template, these use only the (k,u,P_N,P_signal) "
             "coordinates available to RadioFisher")
    ap.add_argument(
        "--template-param", action="append", default=[], metavar="NAME=VALUE",
        help="override one named analytic-template parameter; repeat as needed")
    return ap


def main(argv=None, prog: str = "rfisher build-bank") -> int:
    ap = build_parser(prog)
    args = ap.parse_args(argv)
    if args.cosmology not in SUPPORTED_COSMOLOGIES[args.config]:
        ap.error(f"--config {args.config} does not support --cosmology "
                 f"{args.cosmology}")
    try:
        tgrid = time_grid(
            args.tmin, args.tmax, args.nt, dense_knee=args.dense_knee,
            knee_range=args.knee_range, knee_n=args.knee_n,
            extra_hours=args.extra_time_hours)
        overrides = expt_overrides(
            p_res=args.p_res, residual_template=args.residual_template,
            template_parameters=args.template_param, kfg_fac=args.kfg_fac)
    except (TypeError, ValueError) as exc:
        ap.error(str(exc))
    cosmology = resolve_cosmology(args.config, args.cosmology)
    out = args.out
    if out.is_dir():
        out = out / default_bank_name(
            config=args.config, cosmology=cosmology,
            epsilon_fg=args.epsilon_fg, p_res=args.p_res,
            residual_template=args.residual_template, kfg_fac=args.kfg_fac,
            dense_knee=args.dense_knee)
    print(f"[bank] {len(tgrid)} time points, {tgrid[0]:.3g}-{tgrid[-1]:.3g} hr"
          + (f", P_res={overrides.get('P_res')}"
             if overrides and "P_res" in overrides else ""))
    build_bank(out, rf_dir=args.radiofisher_dir, t_grid_hours=tgrid,
               nproc=args.nproc, epsilon_fg=args.epsilon_fg, k_nl0=args.k_nl0,
               config=args.config, cosmology=cosmology,
               expt_overrides=overrides)
    return 0
