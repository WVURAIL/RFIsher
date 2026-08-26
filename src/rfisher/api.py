"""High-level one-call API: the entry point for users of the tool.

Minimal usage (with the CHIME Fisher bank shipped in the package):

    from rfisher import api

    fc = api.load()                              # shipped CHIME bank; no backend
    mask = {17: 0.33, 30: 0.97, 31: 0.24}        # ATSC channel -> masked frac
    print(api.required_time(fc, mask))           # hours/years/penalty to 5sigma

Anything more elaborate (custom experiments, new banks, direct hook
evaluation) drops down to the underlying modules: scenarios, fisherbank,
forecast, survey.
"""
from __future__ import annotations

import warnings
from numbers import Integral
from pathlib import Path

import numpy as np

from . import forecast as _forecast
from . import scenarios as _scenarios
from . import survey as _survey
from ._validation import (nonnegative_scalar as _nonnegative_scalar,
                          positive_scalar as _positive_scalar)
from .fisherbank import ARTIFACT_FORECAST, FisherBank
from .resources import bank_file


def load(bank: str | Path | None = None, *, cosmology: str | None = None,
         rf_dir=None) -> _forecast.Forecast:
    """Load a Fisher bank and return a Forecast ready for scenario queries.
    The marginalisation style follows the bank's config: per-bin BAO
    amplitudes (Amiri et al. 2022 Appendix A) for 'chime2022', shared
    amplitude (Bull et al. 2015) otherwise. With ``rf_dir=None``, the per-bin
    path does not import RadioFisher. Passing ``rf_dir`` explicitly loads and
    retains that backend for subsequent direct evaluations."""
    if bank is not None and cosmology is not None:
        raise ValueError("provide either bank= or cosmology=, not both")
    source = bank if bank is not None else bank_file(cosmology or "planck2018")
    b = FisherBank(source, expected_artifact_kind=ARTIFACT_FORECAST)
    style = "perbin_A" if b.meta["config"] == "chime2022" else "shared_A"
    rf = None
    resolved_rf_dir = None
    if style == "shared_A" or rf_dir is not None:
        from .backend import import_radiofisher
        rf, resolved_rf_dir = import_radiofisher(rf_dir)
    return _forecast.Forecast(b, rf, style=style, rf_dir=resolved_rf_dir)


def scenario_from(mask=None, uniform=None, band: _scenarios.FrequencyBand =
                  _scenarios.DTV_BAND,
                  excise_threshold: float | None = None,
                  mode: str = "time", residuals=None,
                  residual: float = 0.0,
                  residual_excise_threshold: float = np.inf
                  ) -> _scenarios.Scenario:
    """Build a Scenario from either a {channel: masked_fraction} dict or a
    uniform masked fraction over an explicit :class:`FrequencyBand`.

    ``mask`` also accepts a prebuilt :class:`rfisher.scenarios.Scenario`
    (from :func:`scenarios.legacy_rate_table_scenario`,
    :func:`scenarios.survey_product_scenario`,
    :func:`scenarios.at_threshold`, ...),
    which passes through unchanged. A Scenario already carries its own
    policy, so combining one with the other arguments here would silently
    ignore half of it; that combination is refused.

    ``residuals`` ({channel: r}) is available with a per-channel ``mask``;
    ``residual`` adds one uniform ratio to a frequency-band scenario.

    For a per-channel ``mask``, omitting ``excise_threshold`` uses the
    per-channel default (0.5). Uniform scenarios are retained-time
    stress tests by default and therefore do not excise; pass an explicit
    ``excise_threshold`` to apply excision to a uniform scenario. This keeps
    the retained-time masking-cost convention while ensuring that a
    supplied threshold is never ignored.
    """
    if (mask is None) == (uniform is None):
        raise ValueError("provide exactly one of mask= or uniform=")
    if isinstance(mask, _scenarios.Scenario):
        overridden = (excise_threshold is not None or residuals is not None
                      or float(residual) != 0.0 or mode != "time"
                      or np.isfinite(residual_excise_threshold))
        if overridden:
            raise ValueError(
                "mask= is already a Scenario carrying its own policy; build "
                "the overrides into the Scenario instead of passing them "
                "alongside it")
        return mask
    residual = _scenarios._residual(residual, "residual")
    if residuals is not None and residual != 0.0:
        raise ValueError("provide at most one of residuals= or residual=")
    if mask is not None:
        res = (dict(residuals) if residuals is not None else
               ({c: residual for c in mask} if residual else {}))
        threshold = (_scenarios.DEFAULT_EXCISE_THRESHOLD
                     if excise_threshold is None else excise_threshold)
        return _scenarios.Scenario("user", "user scenario",
                                   fractions=dict(mask),
                                   excise_threshold=threshold,
                                   mode=mode, residuals=res,
                                   residual_excise_threshold=residual_excise_threshold)
    if residuals is not None:
        raise ValueError(
            "residuals= is channel-specific and requires mask=; use the "
            "scalar residual= argument with uniform=")
    return _scenarios.uniform(
        uniform, band, mode=mode, residual=residual,
        excise_threshold=excise_threshold,
        residual_excise_threshold=residual_excise_threshold)


def _zbin_index(fc: _forecast.Forecast, zbin) -> int:
    """Validate a redshift-bin index against the bank's bin count.

    An out-of-range index would otherwise select no Fisher matrices at all
    and surface as significance 0 / required time inf, indistinguishable
    from a physically hopeless scenario."""
    if isinstance(zbin, (bool, np.bool_)) or not isinstance(zbin, Integral):
        raise ValueError(f"zbin must be an integer bin index, got {zbin!r}")
    zbin = int(zbin)
    nbins = fc.bank.nbins
    if not 0 <= zbin < nbins:
        raise ValueError(
            f"zbin must be in [0, {nbins - 1}] for this bank's {nbins} "
            f"redshift bins, got {zbin}")
    return zbin


def _warn_if_outside_bank(fc: _forecast.Forecast,
                          sc: _scenarios.Scenario) -> None:
    """Warn when every masked slice misses the bank's frequency coverage.

    A disjoint scenario legitimately costs nothing (penalty exactly 1), but
    the same answer comes out of a units mistake (band edges in GHz, a
    channel number from another band plan). The warning tells the two apart
    without changing any number."""
    bank = getattr(fc, "bank", None)
    if bank is None:
        return
    slices = list(sc._physical_slices())
    if not slices:
        return
    zs = np.asarray(bank.zs, dtype=float)
    nu_lo, nu_hi = _survey.zbin_freq_range(float(zs[0]), float(zs[-1]))
    if any(min(hi, nu_hi) > max(lo, nu_lo) for lo, hi, _, _ in slices):
        return
    channels = sorted(set(sc.fractions) | set(sc.residuals))
    bands = sorted(b.name for b in
                   set(sc.frequency_fractions) | set(sc.frequency_residuals))
    parts = []
    if channels:
        parts.append(f"channels {channels}")
    if bands:
        parts.append(f"bands {bands}")
    warnings.warn(
        f"scenario {sc.name!r} masks {' and '.join(parts)} entirely outside "
        f"the bank's {nu_lo:.1f}-{nu_hi:.1f} MHz coverage; the penalty is "
        "exactly 1 by construction — check frequency units and band choice",
        UserWarning, stacklevel=3)


def required_time(fc: _forecast.Forecast, mask=None, uniform=None,
                  band: _scenarios.FrequencyBand = _scenarios.DTV_BAND,
                  target: float = 5.0,
                  zbin: int | None = None, mode: str = "time",
                  excise_threshold: float | None = None,
                  duty: float = 1.0, residuals=None, residual: float = 0.0,
                  residual_excise_threshold: float = np.inf,
                  hours_per_year: float = _survey.OVERVIEW_ONSKY_YEAR_HOURS) -> dict:
    """Observing time needed to reach a BAO detection target.

    target : detection significance A/sigma_A (e.g. 5.0)
    zbin   : None for the full survey, or a bin index for that bin alone
    duty   : 1.0 quotes uninterrupted years; use
             survey.DUTY_2019_PRACTICE (0.152)
             for calendar years at demonstrated CHIME practice.
    hours_per_year : defaults to the CHIME Overview's on-sky normalization
                     (1 yr = 8,760 on-sky hours), the convention every
                     quoted time in this repository uses. Pass
                     survey.MEAN_CALENDAR_YEAR_HOURS for 365.25-day mean
                     calendar years.
    Returns a dict with on-sky hours, on-sky years at `duty`, and the
    penalty relative to the uncontaminated baseline (same target, same bins).
    """
    target = _positive_scalar(target, "target")
    duty = _positive_scalar(duty, "duty")
    hours_per_year = _positive_scalar(hours_per_year, "hours_per_year")
    sc = scenario_from(mask, uniform, band, excise_threshold, mode,
                       residuals=residuals, residual=residual,
                       residual_excise_threshold=residual_excise_threshold)
    _warn_if_outside_bank(fc, sc)
    zbin = None if zbin is None else _zbin_index(fc, zbin)
    bins = None if zbin is None else [zbin]
    metric = lambda s: (lambda t: fc.significance(s, t, bins=bins))
    hours = fc.required_hours_metric(metric(sc), target)
    clean = fc.required_hours_metric(metric(_scenarios.clean()), target)
    years = (float(_survey.hours_to_years(hours, duty, hours_per_year))
             if np.isfinite(hours) else np.inf)
    return dict(hours=float(hours), years=years, duty=duty,
                hours_per_year=hours_per_year,
                penalty_vs_clean=float(hours / clean) if np.isfinite(hours) else np.inf,
                target_sigma=target,
                zbin="survey" if zbin is None else zbin)


def significance(fc: _forecast.Forecast, years: float, mask=None,
                 uniform=None, band: _scenarios.FrequencyBand =
                 _scenarios.DTV_BAND, zbin: int | None = None,
                 mode: str = "time", excise_threshold: float | None = None,
                 duty: float = 1.0, residuals=None, residual: float = 0.0,
                 residual_excise_threshold: float = np.inf,
                 hours_per_year: float = _survey.OVERVIEW_ONSKY_YEAR_HOURS) -> float:
    """BAO detection significance after `years` on-sky years at `duty`.

    ``hours_per_year`` defaults to the Overview's on-sky normalization
    (1 yr = 8,760 on-sky hours); pass survey.MEAN_CALENDAR_YEAR_HOURS for
    365.25-day mean calendar years."""
    years = _nonnegative_scalar(years, "years")
    duty = _positive_scalar(duty, "duty")
    hours_per_year = _positive_scalar(hours_per_year, "hours_per_year")
    sc = scenario_from(mask, uniform, band, excise_threshold, mode,
                       residuals=residuals, residual=residual,
                       residual_excise_threshold=residual_excise_threshold)
    _warn_if_outside_bank(fc, sc)
    zbin = None if zbin is None else _zbin_index(fc, zbin)
    bins = None if zbin is None else [zbin]
    t = float(_survey.years_to_hours(years, duty, hours_per_year))
    return fc.significance(sc, t, bins=bins)


def per_bin_error(fc: _forecast.Forecast, years: float, zbin: int,
                  param: str = "dv", mask=None, uniform=None,
                  band: _scenarios.FrequencyBand = _scenarios.DTV_BAND,
                  mode: str = "time", excise_threshold: float | None = None,
                  duty: float = 1.0, residuals=None, residual: float = 0.0,
                  residual_excise_threshold: float = np.inf,
                  hours_per_year: float = _survey.OVERVIEW_ONSKY_YEAR_HOURS
                  ) -> float:
    """Marginalised error on one per-bin parameter after `years` on-sky
    years, for redshift bin `zbin` analyzed alone.

    The detection-significance functions above price everything in the BAO
    amplitude; tolerances on other observables need the per-bin errors the
    forecast already computes. ``param`` selects one:

    * ``'fs8'``   : the growth measurement f sigma_8
    * ``'aperp'`` : the transverse BAO scale (D_A / r_d)
    * ``'apar'``  : the radial BAO scale (H r_d)
    * ``'dv'``    : the volume distance D_V, the (2/3, 1/3) log-combination
      of aperp and apar (:meth:`Forecast.sigma_dv_bin`)

    Pure pass-through to :meth:`Forecast.sigma_param_bin` /
    :meth:`Forecast.sigma_dv_bin`; ``inf`` means the bin carries no
    information on that parameter under the scenario."""
    years = _nonnegative_scalar(years, "years")
    duty = _positive_scalar(duty, "duty")
    hours_per_year = _positive_scalar(hours_per_year, "hours_per_year")
    sc = scenario_from(mask, uniform, band, excise_threshold, mode,
                       residuals=residuals, residual=residual,
                       residual_excise_threshold=residual_excise_threshold)
    _warn_if_outside_bank(fc, sc)
    zbin = _zbin_index(fc, zbin)
    t = float(_survey.years_to_hours(years, duty, hours_per_year))
    if param == "dv":
        return fc.sigma_dv_bin(sc, t, zbin)
    return fc.sigma_param_bin(sc, t, zbin, param)


def masking_cost_curve(fc: _forecast.Forecast, fracs=None,
                       band: _scenarios.FrequencyBand = _scenarios.DTV_BAND,
                       target: float = 5.0, zbin: int | None = None,
                       duty: float = 1.0,
                       hours_per_year: float = _survey.OVERVIEW_ONSKY_YEAR_HOURS):
    """(fracs, years) arrays: required on-sky years (Overview
    normalization, 1 yr = 8,760 on-sky hours) vs uniform masked fraction
    of `band`, the masking-cost curve."""
    target = _positive_scalar(target, "target")
    duty = _positive_scalar(duty, "duty")
    hours_per_year = _positive_scalar(hours_per_year, "hours_per_year")
    if fracs is None:
        fracs = np.concatenate([np.arange(0.0, 0.96, 0.05), [0.97]])
    fracs = np.asarray(fracs, dtype=float)
    yrs = np.array([required_time(fc, uniform=float(f), band=band,
                                  target=target, zbin=zbin,
                                  duty=duty, hours_per_year=hours_per_year)["years"]
                    for f in fracs])
    return fracs, yrs


def threshold_curve(fc: _forecast.Forecast, operating_points: dict,
                    target: float = 5.0, zbin: int | None = None,
                    duty: float = 1.0, mode: str = "time",
                    excise_threshold: float = _scenarios.DEFAULT_EXCISE_THRESHOLD,
                    residual_excise_threshold: float = np.inf,
                    hours_per_year: float = _survey.OVERVIEW_ONSKY_YEAR_HOURS) -> dict:
    """Required time as a function of detector threshold, the closed loop.

    Years are on-sky years at the Overview normalization (1 yr = 8,760
    on-sky hours) unless ``hours_per_year`` says otherwise.

    ``operating_points`` maps a threshold (any orderable label, e.g. eta) to
    ``{channel: (masked_fraction, residual_ratio)}``. Both halves of the cost
    move with the threshold in opposite directions, so unlike
    :func:`masking_cost_curve` this has an interior minimum: the threshold that
    minimises total time to the target.

    Returns ``{'thresholds': [...], 'years': [...], 'penalty': [...],
    'best_threshold': ..., 'best_years': ...}``. A threshold whose residual
    makes the target unreachable yields ``inf`` rather than being dropped, so
    the caller can see where the wall is.
    """
    target = _positive_scalar(target, "target")
    duty = _positive_scalar(duty, "duty")
    hours_per_year = _positive_scalar(hours_per_year, "hours_per_year")
    thresholds = sorted(operating_points)
    zbin = None if zbin is None else _zbin_index(fc, zbin)
    bins = None if zbin is None else [zbin]
    clean_hours = fc.required_hours_metric(
        lambda t: fc.significance(_scenarios.clean(), t, bins=bins), target)

    years, penalty = [], []
    for threshold in thresholds:
        sc = _scenarios.at_threshold(
            operating_points[threshold], threshold_label=threshold, mode=mode,
            excise_threshold=excise_threshold,
            residual_excise_threshold=residual_excise_threshold)
        h = fc.required_hours_metric(
            lambda t, scenario=sc: fc.significance(
                scenario, t, bins=bins), target)
        years.append(float(_survey.hours_to_years(h, duty, hours_per_year))
                     if np.isfinite(h) else np.inf)
        penalty.append(float(h / clean_hours) if np.isfinite(h) else np.inf)

    years = np.asarray(years)
    ibest = int(np.argmin(years)) if np.any(np.isfinite(years)) else -1
    best_threshold = thresholds[ibest] if ibest >= 0 else None
    if isinstance(best_threshold, np.generic):
        best_threshold = best_threshold.item()
    return dict(thresholds=np.asarray(thresholds), years=years,
                penalty=np.asarray(penalty),
                best_threshold=best_threshold,
                best_years=(float(years[ibest]) if ibest >= 0 else np.inf),
                target_sigma=target,
                zbin="survey" if zbin is None else int(zbin))
