"""CHIME survey definition and redshift binning, mirroring how
``full_experiment.py`` drives the 'yCHIME' (cylinder interferometer) case.
"""
from __future__ import annotations

import copy
from pathlib import Path

import numpy as np

from ._validation import (nonnegative_scalar, positive_scalar)
from .constants import HI_REST_FREQUENCY_MHZ

HRS_MHZ = 3.6e9                  # 1 hour in MHz^-1 (radiofisher.units)
MEAN_CALENDAR_YEAR_HOURS = 8766.0  # 365.25 days
OVERVIEW_ONSKY_YEAR_HOURS = 8760.0  # 365 days, Overview normalization

# Literature-anchored time accounting (see paper, duty-cycle paragraph):
# * OVERVIEW_ONSKY_YEAR_HOURS: the CHIME Overview normalization: t_tot =
#   "1 yr" means 8,760 on-sky hours with no duty factor (Amiri et al. 2022,
#   ApJS 261, 29, Table 2 / Appendix A; 365*24 in Foreman's chime2021 code).
# * DUTY_2019_PRACTICE: empirical cosmology-quality fraction of the 2019
#   CHIME dataset (Amiri et al. 2025, arXiv:2511.19620): 94 of 309 sidereal
#   days retained x ~0.5 night-only ~= 0.152. Their additional 38.7% masking
#   of surviving night data INCLUDES RFI flagging and must not be applied on
#   top of the masking scenarios here (double counting); including it gives
#   0.093. The Overview's daily-processing rule ("any day with less than 70%
#   coverage after masking is discarded", Amiri et al. 2022) is the
#   mechanism behind the day-retention factor; the 102-night dataset of the
#   2023 detection (ApJ 947, 16) corroborates the ~100-night/year scale.
DUTY_2019_PRACTICE = 0.152


def chime_experiment(rf, rf_dir: str | Path, ttot_hours: float = 1e4,
                     epsilon_fg: float = 1e-6, k_nl0: float = 0.14,
                     nx_file: str | Path | None = None) -> dict:
    """Return the CHIME experiment dict configured like full_experiment's
    'yCHIME' entry (mode 'icyl'), with an absolute n(u) file path so we can
    run from any working directory."""
    expt = copy.deepcopy(rf.experiments.CHIME)
    expt["mode"] = "icyl"
    expt["ttot"] = ttot_hours * HRS_MHZ
    expt["epsilon_fg"] = epsilon_fg
    expt["k_nl0"] = k_nl0
    if nx_file is None:
        from .resources import SYNTHETIC_BASELINE_NAME, filesystem_data_file
        nx_file = filesystem_data_file(SYNTHETIC_BASELINE_NAME)
    expt["n(x)"] = str(nx_file)
    return expt


def chime_zbins(rf, expt: dict, dz: float = 0.1):
    """Equal-dz redshift bins over the CHIME band (400-800 MHz)."""
    # CHIME is a single instrument (no ``overlap`` experiment component), so
    # the backend's supported binning helper consumes its experiment directly.
    zs, zc = rf.zbins_equal_spaced(expt, dz=dz)
    return np.asarray(zs), np.asarray(zc)


# ----------------------------------------------------------------------
# CHIME Overview configuration (Amiri et al. 2022, ApJS 261, 29, App. A;
# implemented in sjforeman/RadioFisher branch chime-update, chime2021/)
# ----------------------------------------------------------------------

def _import_experiments_chime(rf_dir: str | Path):
    import importlib
    import sys
    chime_dir = str(Path(rf_dir) / "chime2021")
    for p in (str(rf_dir), chime_dir):
        if p not in sys.path:
            sys.path.insert(0, p)
    module = importlib.import_module("experiments_CHIME")
    module_file = Path(module.__file__).resolve()
    expected = Path(chime_dir).resolve()
    try:
        module_file.relative_to(expected)
    except ValueError as exc:
        raise RuntimeError(
            "experiments_CHIME checkout mismatch: requested data from "
            f"{expected}, but Python already imported {module_file}. Start a "
            "fresh process with one RadioFisher checkout.") from exc
    return module


def chime2022_experiment(rf, rf_dir: str | Path,
                         ttot_hours: float = OVERVIEW_ONSKY_YEAR_HOURS) -> dict:
    """CHIME as forecast in the Overview paper: as-built 4x256 geometry,
    Tsys_tot = 55 K, S_sky = 31,000 deg^2, BAO-shift-only USE flags,
    epsilon_fg = 0, Simon Foreman's as-built n(u)."""
    exps = _import_experiments_chime(rf_dir)
    expt = copy.deepcopy(exps.CHIME)
    expt["Tsys_tot(z)"] = exps.CHIME["Tsys_tot(z)"]  # deepcopy keeps lambda ref
    expt["ttot"] = ttot_hours * HRS_MHZ
    expt["n(x)"] = str(Path(rf_dir) / "chime2021" / expt["n(x)"])
    return expt


# ----------------------------------------------------------------------
# CHIME 2025 auto-spectrum configuration (Amiri et al. 2025,
# arXiv:2511.19620): the field, band, and integration time behind the
# published 12.4 sigma detection of the 21 cm signal in auto-correlation
# at z ~ 1. 94 nights of the 2019 dataset, 385 h of effective integration,
# 0.5 mJy/beam per frequency channel, a 200 ns DAYENU cut and a 280 ns
# mask, over 2,200 deg^2 and 608.2-707.8 MHz.
#
# Everything else -- as-built 4x256 geometry, Tsys_tot = 55 K, epsilon_fg =
# 0, BAO-shift-only USE flags, Foreman's as-built n(u) -- is the Overview
# configuration, so the two configurations differ only in field, band, and
# time. This is a forecast of that field, not a reconstruction of their
# pipeline: the sky area and integration time are theirs, but the noise
# comes from the Overview's own instrument model.
# ----------------------------------------------------------------------

CHIME2025_SAREA_DEG2 = 2200.0
CHIME2025_NUMIN_MHZ = 608.2
CHIME2025_NUMAX_MHZ = 707.8
CHIME2025_TTOT_HOURS = 385.0
CHIME2025_NZBINS = 3               # three dz ~ 0.1 bins across the band
CHIME2025_NIGHTS = 94
CHIME2025_SENSITIVITY_MJY_PER_BEAM = 0.5
CHIME2025_TAU_CUT_NS = 200.0       # DAYENU high-pass delay
CHIME2025_TAU_MASK_NS = 280.0      # first delay actually retained
CHIME2025_DETECTION_SIGMA = 12.4   # F-test S/N, the headline number
CHIME2025_DETECTION_SIGMA_CHI2 = 13.0        # delta-chi^2 based
CHIME2025_DETECTION_SIGMA_AMPLITUDE = 13.6   # single-amplitude fit
# The spatial mask of Section 5.2 (transit masks of >10 Jy sources plus the
# Galactic mask) removes about a third of the field before the power
# spectrum is formed, so the 12.4 sigma comes from ~1,470 of the 2,200
# deg^2. A masked pixel is lost volume at unchanged depth.
CHIME2025_SPATIAL_MASK_FRACTION = 0.33
FILTER_RESIDUAL_TABLE = "chime2025_fig10_filter_residual.csv"
CHIME2025_KMIN_H = 0.4             # detection band, h/Mpc
CHIME2025_KMAX_H = 1.5
CHIME2025_Z_REFERENCE = 1.16       # redshift their k_par floor is quoted at

# Seven calendar years of archive at the 2019 dataset's measured
# cosmology-quality duty cycle: 7 x 8,766 h x 0.152 = 9,327 h, i.e. 1.06
# Overview on-sky years. The collaboration has stated the full archive is
# what it will analyze next.
ARCHIVE_CALENDAR_YEARS = 7.0


# ----------------------------------------------------------------------
# What the present pipeline accepts of the archive. The 2025 analysis keeps
# formed beams with |y| < 0.4, y being the sine of the north-south zenith
# angle, i.e. declinations within 23.6 deg of CHIME's latitude: about
# 10,760 deg^2 of the Overview's 31,000, of which the Section 5.2 spatial
# mask then removes about a third, leaving ~7,200. A declination cut discards volume
# without buying depth on what is kept -- every strip transits for the
# same time whether or not its neighbours are analysed -- so the
# accepted-sky archive holds Sarea / t_tot (RadioFisher's per-voxel noise)
# fixed and scales t_tot with the area, rather than spending 9,327 h on a
# third of the sky and coming out deeper than the full archive.
# ----------------------------------------------------------------------

CHIME_LATITUDE_DEG = 49.3207
OVERVIEW_SAREA_DEG2 = 31000.0
ACCEPTED_NS_SINE_MAX = 0.4         # |y| < 0.4 in the 2025 analysis
DEG2_PER_SR = (180.0 / np.pi) ** 2


def accepted_declination_band_deg2(
        y_max: float = ACCEPTED_NS_SINE_MAX,
        latitude_deg: float = CHIME_LATITUDE_DEG) -> float:
    """Sky area [deg^2] of the declination band a transit telescope at
    ``latitude_deg`` sees within north-south zenith angles |sin za| < y_max."""
    y_max = positive_scalar(y_max, "y_max")
    if y_max > 1.0:
        raise ValueError("y_max is a sine and must not exceed 1")
    half_width = np.degrees(np.arcsin(y_max))
    dec_lo = max(-90.0, latitude_deg - half_width)
    dec_hi = min(90.0, latitude_deg + half_width)
    steradians = 2.0 * np.pi * (np.sin(np.radians(dec_hi))
                                - np.sin(np.radians(dec_lo)))
    return float(steradians * DEG2_PER_SR)


def accepted_sky_area_deg2(
        y_max: float = ACCEPTED_NS_SINE_MAX,
        latitude_deg: float = CHIME_LATITUDE_DEG,
        mask_fraction: float = CHIME2025_SPATIAL_MASK_FRACTION) -> float:
    """Sky the present pipeline actually forms a power spectrum from: the
    |y| < y_max declination band less the spatial mask of Section 5.2."""
    mask_fraction = nonnegative_scalar(mask_fraction, "mask_fraction")
    if mask_fraction >= 1.0:
        raise ValueError("mask_fraction must be below 1")
    return accepted_declination_band_deg2(y_max, latitude_deg) \
        * (1.0 - mask_fraction)


def chime2025_masked_experiment(
        rf, rf_dir: str | Path,
        mask_fraction: float = CHIME2025_SPATIAL_MASK_FRACTION) -> dict:
    """The published field after its spatial mask, at unchanged depth:
    Sarea and t_tot both scaled by (1 - mask_fraction)."""
    mask_fraction = nonnegative_scalar(mask_fraction, "mask_fraction")
    if mask_fraction >= 1.0:
        raise ValueError("mask_fraction must be below 1")
    kept = 1.0 - mask_fraction
    expt = chime2025_experiment(
        rf, rf_dir, ttot_hours=CHIME2025_TTOT_HOURS * kept)
    expt["Sarea"] = CHIME2025_SAREA_DEG2 * kept / DEG2_PER_SR
    return expt


def filter_residual_table(path: str | Path | None = None):
    """The digitised Fig. 10 filter response: (tau / tau_cut, RMS residual).

    Rows are the vertices of the paper's median curve; the file header
    records the extraction and the high-delay plateau."""
    from .resources import data_file

    source = Path(path) if path is not None else data_file(
        FILTER_RESIDUAL_TABLE)
    with source.open("r") as stream:
        rows = [line for line in stream
                if line.strip() and not line.lstrip().startswith("#")]
    # The first non-comment line is the column header.
    try:
        table = np.loadtxt(rows[1:], delimiter=",", ndmin=2)
    except ValueError as exc:
        raise ValueError(f"{source} is not a two-column response table") \
            from exc
    if table.shape[1] != 2 or table.shape[0] < 2:
        raise ValueError(f"{source} is not a two-column response table")
    ratio, response = table[:, 0], table[:, 1]
    if np.any(np.diff(ratio) <= 0.0) or ratio[0] < 0.0:
        raise ValueError(f"{source}: tau / tau_cut must increase from >= 0")
    if np.any(response < 0.0):
        raise ValueError(f"{source}: RMS residual must be non-negative")
    return ratio, response


def delay_transfer(rf, expt: dict, cosmo_fns, tau_cut_seconds: float,
                   table=None):
    """Return the ``expt['kpar_transfer_fn']`` hook for the soft delay cut.

    The measured filter response (Fig. 10, at 200 ns) is scaled in
    tau / tau_cut to ``tau_cut_seconds``, normalised to its plateau and
    squared, and multiplies the signal power. Signal only: the same
    filter attenuates the noise too, so this brackets the hard cut from
    the conservative side rather than replacing it."""
    from .backend import require_backend_capabilities

    require_backend_capabilities(rf, {"kpar_transfer_fn"})
    ratio, response = filter_residual_table() if table is None else table
    return rf.delay_transfer_fn(
        positive_scalar(tau_cut_seconds, "tau_cut_seconds"),
        cosmo_fns[0], expt["nu_line"], ratio, response)


def accepted_archive_hours(area_deg2: float | None = None) -> float:
    """Archive hours that hold the full-sky archive's per-voxel depth on
    ``area_deg2`` of sky under RadioFisher's Sarea / t_tot noise scaling."""
    if area_deg2 is None:
        area_deg2 = accepted_sky_area_deg2()
    area_deg2 = positive_scalar(area_deg2, "area_deg2")
    return archive_hours() * area_deg2 / OVERVIEW_SAREA_DEG2


def archive_accepted_experiment(rf, rf_dir: str | Path,
                                area_deg2: float | None = None) -> dict:
    """The seven-year archive restricted to the sky the present cuts accept:
    the Overview instrument, band and duty cycle over ``area_deg2``
    (default: the |y| < 0.4 declination band less the 33% spatial mask),
    at fixed per-voxel depth."""
    if area_deg2 is None:
        area_deg2 = accepted_sky_area_deg2()
    expt = chime2022_experiment(
        rf, rf_dir, ttot_hours=accepted_archive_hours(area_deg2))
    expt["Sarea"] = positive_scalar(area_deg2, "area_deg2") / DEG2_PER_SR
    return expt


def chime2025_experiment(rf, rf_dir: str | Path,
                         ttot_hours: float = CHIME2025_TTOT_HOURS) -> dict:
    """CHIME as published in the 2025 auto-correlation detection: the
    Overview instrument over 2,200 deg^2 and 608.2-707.8 MHz."""
    expt = chime2022_experiment(rf, rf_dir, ttot_hours=ttot_hours)
    expt["Sarea"] = CHIME2025_SAREA_DEG2 * (np.pi / 180.0) ** 2
    expt["survey_numax"] = CHIME2025_NUMAX_MHZ
    expt["survey_dnutot"] = CHIME2025_NUMAX_MHZ - CHIME2025_NUMIN_MHZ
    return expt


def chime2025_zbins(rf, expt: dict, bins: int = CHIME2025_NZBINS):
    """Equal-width redshift bins spanning the published band exactly.

    608.2-707.8 MHz is z = 1.0068-1.3354, so three equal bins are dz =
    0.1095 each. Splitting the band rather than laying dz = 0.1 bins from
    its low edge keeps the survey volume right, which is what the forecast
    is actually sensitive to."""
    zs, zc = rf.zbins_equal_spaced(expt, bins=bins)
    return np.asarray(zs), np.asarray(zc)


def archive_hours(years: float = ARCHIVE_CALENDAR_YEARS,
                  duty: float = DUTY_2019_PRACTICE) -> float:
    """On-sky hours in `years` calendar years at a given duty cycle."""
    return float(years_to_hours(years, duty=duty,
                                hours_per_year=MEAN_CALENDAR_YEAR_HOURS))


def delay_cut(rf, expt: dict, cosmo_fns, tau_cut_seconds: float,
              transition: float | None = None):
    """Return the ``expt['kpar_min_fn']`` hook for a hard delay-domain cut.

    ``tau_cut_seconds`` is the high-pass filter delay; the backend applies
    the transition-zone factor (1.4 by default, CHIME's 200 ns cut against
    its 280 ns mask) before converting delay to k_par. A zero cut is a
    valid no-op, so a no-cut reference runs through exactly the same
    code path as every masked point."""
    from .backend import require_backend_capabilities

    require_backend_capabilities(rf, {"kpar_min_fn"})
    if transition is None:
        transition = rf.DELAY_TRANSITION_FACTOR
    return rf.delay_cut_kpar_min(
        nonnegative_scalar(tau_cut_seconds, "tau_cut_seconds"),
        cosmo_fns[0], expt["nu_line"], transition=transition)


def experiment_from_bank_metadata(rf, rf_dir: str | Path, meta: dict,
                                  ttot_hours: float) -> dict:
    """Reconstruct the exact experiment recorded by a strict-v2 bank.

    Canonical survey factories provide callables and checkout-bound resource
    paths that JSON provenance cannot itself recreate. Recorded scalar settings
    and ``expt_overrides`` are then checked against that reconstruction before
    an experiment is returned. Any unexplained setting drift fails closed.
    """
    from .fisherbank import experiment_settings_payload

    ttot_hours = nonnegative_scalar(ttot_hours, "ttot_hours")
    if not isinstance(meta, dict):
        raise ValueError("bank metadata must be an object")
    config = meta.get("config")
    try:
        settings = meta["provenance"]["experiment"]["settings"]
    except (KeyError, TypeError) as exc:
        raise ValueError(
            "bank metadata has no recorded experiment settings") from exc
    overrides = meta.get("expt_overrides")
    if not isinstance(settings, dict) or not isinstance(overrides, dict):
        raise ValueError(
            "bank experiment settings and expt_overrides must be objects")

    if config == "bull2015":
        try:
            epsilon_fg = nonnegative_scalar(
                settings["epsilon_fg"], "recorded epsilon_fg")
            k_nl0 = positive_scalar(settings["k_nl0"], "recorded k_nl0")
        except KeyError as exc:
            raise ValueError(
                "Bull-2015 bank is missing recorded epsilon_fg or k_nl0") from exc

        def canonical(hours):
            return chime_experiment(
                rf, rf_dir, ttot_hours=hours,
                epsilon_fg=epsilon_fg, k_nl0=k_nl0)
    elif config == "chime2022":
        def canonical(hours):
            return chime2022_experiment(rf, rf_dir, ttot_hours=hours)
    else:
        raise ValueError(
            f"unsupported recorded experiment configuration: {config!r}")

    def reconstruct(hours):
        experiment = canonical(hours)
        experiment.update(copy.deepcopy(overrides))
        return experiment

    reference = reconstruct(1.0)
    reconstructed_settings = experiment_settings_payload(reference, rf_dir)
    if reconstructed_settings != settings:
        missing = sorted(set(settings) - set(reconstructed_settings))
        extra = sorted(set(reconstructed_settings) - set(settings))
        changed = sorted(
            key for key in set(settings) & set(reconstructed_settings)
            if settings[key] != reconstructed_settings[key])
        details = []
        if missing:
            details.append(f"unreconstructed keys={missing}")
        if extra:
            details.append(f"unexpected canonical keys={extra}")
        if changed:
            details.append(f"changed keys={changed}")
        raise ValueError(
            "bank experiment settings cannot be reconstructed from its "
            "recorded configuration and expt_overrides: " + "; ".join(details))
    return reconstruct(ttot_hours)


def chime2022_cosmo(rf, rf_dir: str | Path) -> dict:
    """Planck-2018 fiducial cosmology of the Overview forecasts."""
    exps = _import_experiments_chime(rf_dir)
    return copy.deepcopy(exps.cosmo)


def chime2022_zbins():
    """The 15 redshift bins of Amiri et al. (2022) Table 2 (dz=0.1 to
    z=1.8, dz~0.16 above, matching DESI binning)."""
    zs = np.array([0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8,
                   1.9, 2.04, 2.20, 2.355, 2.51])
    return zs, 0.5 * (zs[1:] + zs[:-1])


def zbin_freq_range(zmin: float, zmax: float) -> tuple[float, float]:
    """Frequency interval [MHz] covered by a redshift bin (lo, hi)."""
    return (HI_REST_FREQUENCY_MHZ / (1.0 + zmax),
            HI_REST_FREQUENCY_MHZ / (1.0 + zmin))


def hours_to_years(hours: np.ndarray | float, duty: float = 1.0,
                   hours_per_year: float = MEAN_CALENDAR_YEAR_HOURS):
    """Years on an explicit hour basis, optionally adjusted by ``duty``."""
    duty = positive_scalar(duty, "duty")
    hours_per_year = positive_scalar(hours_per_year, "hours_per_year")
    return np.asarray(hours) / (hours_per_year * duty)


def years_to_hours(years: np.ndarray | float, duty: float = 1.0,
                   hours_per_year: float = MEAN_CALENDAR_YEAR_HOURS):
    """Hours on an explicit year basis, optionally adjusted by ``duty``."""
    duty = positive_scalar(duty, "duty")
    hours_per_year = positive_scalar(hours_per_year, "hours_per_year")
    return np.asarray(years) * hours_per_year * duty
