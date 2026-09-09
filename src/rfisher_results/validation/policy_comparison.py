"""Pure diagnostics for fixed coarse/fine policies on one common population.

Fine requirements must already use the logical sentinel 2**64. A serialized
zero-as-sentinel encoding must be decoded by the caller before these helpers;
a logical requirement zero means the lowest deployable multiplier (one).
No helper reads observations, selects a policy using evaluation data, or
constructs confidence intervals or physical recovery claims.
"""

from __future__ import annotations

from fractions import Fraction
import math
from numbers import Integral, Real

import numpy as np

from rfisher.thresholds import ALWAYS_MASKED_Q16, MAX_MULTIPLIER_Q16

__all__ = [
    "fine_quantile_threshold",
    "coarse_quantile_threshold",
    "fine_keep",
    "overlap_2x2",
    "same_mask_summary",
]


def _quantile(quantile, percent):
    if (quantile is None) == (percent is None):
        raise ValueError("provide exactly one exact quantile or integer percent")
    if percent is not None:
        if isinstance(percent, (bool, np.bool_)) or not isinstance(percent, Integral):
            raise TypeError("percent must be an integer")
        value = Fraction(int(percent), 100)
    elif isinstance(quantile, Fraction):
        value = quantile
    elif isinstance(quantile, Integral) and not isinstance(quantile, (bool, np.bool_)):
        value = Fraction(int(quantile), 1)
    elif isinstance(quantile, tuple) and len(quantile) == 2:
        numerator, denominator = quantile
        if any(
            isinstance(x, (bool, np.bool_)) or not isinstance(x, Integral)
            for x in quantile
        ):
            raise TypeError("quantile numerator and denominator must be integers")
        if denominator <= 0:
            raise ValueError("quantile denominator must be positive")
        value = Fraction(int(numerator), int(denominator))
    else:
        raise TypeError(
            "quantile must be Fraction, integer endpoint, or (numerator, denominator)"
        )
    if not 0 <= value <= 1:
        raise ValueError("quantile must lie in [0, 1]")
    return value


def _requirements(values):
    # Object conversion preserves mixed Python integers/uint64, including
    # the logical 2**64 sentinel that cannot fit in uint64 itself.
    array = np.asarray(values, dtype=object)
    if array.ndim != 1:
        raise ValueError("fine requirements must be one-dimensional")
    checked = []
    for value in array:
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral):
            raise TypeError("fine requirements must contain only integers")
        integer = int(value)
        if not 0 <= integer <= ALWAYS_MASKED_Q16:
            raise ValueError("fine requirement is outside the logical deployed range")
        checked.append(integer)
    return checked


def _eta(value):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral):
        raise TypeError("eta_q16 must be an integer")
    integer = int(value)
    if not 1 <= integer <= MAX_MULTIPLIER_Q16:
        raise ValueError("eta_q16 must be a legal positive uint64 multiplier")
    return integer


def _mask(values, name):
    array = np.asarray(values, dtype=object)
    if array.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    if any(not isinstance(x, (bool, np.bool_)) for x in array):
        raise TypeError(f"{name} must contain booleans, not numeric weights")
    return np.asarray(array, dtype=bool)


def _nonnegative(values, name, *, positive=False):
    array = np.asarray(values, dtype=object)
    if array.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    if any(isinstance(x, (bool, np.bool_)) or not isinstance(x, Real) for x in array):
        raise TypeError(f"{name} must contain real numbers")
    numeric = np.asarray(array, dtype=np.float64)
    if not np.all(np.isfinite(numeric)) or np.any(
        numeric <= 0 if positive else numeric < 0
    ):
        rule = "positive" if positive else "nonnegative"
        raise ValueError(f"{name} must contain finite {rule} values")
    return numeric


def _sum(values):
    try:
        value = math.fsum(float(x) for x in values)
    except OverflowError as exc:
        raise ValueError(
            "diagnostic total is not representable as a finite float"
        ) from exc
    if not math.isfinite(value):
        raise ValueError("diagnostic total is not finite")
    return value


def fine_keep(requirements, eta_q16):
    """Return exact requirements <= eta, explicitly excluding the logical sentinel."""
    checked, eta = _requirements(requirements), _eta(eta_q16)
    return np.fromiter(
        (x != ALWAYS_MASKED_Q16 and x <= eta for x in checked),
        dtype=bool,
        count=len(checked),
    )


def fine_quantile_threshold(requirements, *, quantile=None, percent=None):
    """Choose sorted[ceil(q*(n-1))] entirely in integer arithmetic.

    All requirements, including always-masked sentinels, participate. A
    sentinel at the selected order statistic refuses the threshold. Ties
    determine actual calibration retention; requested retention is not a
    guarantee about another cohort. Inputs are never modified.
    """
    q = _quantile(quantile, percent)
    checked = _requirements(requirements)
    result = {
        "status": "unavailable",
        "reason": None,
        "eta_q16": None,
        "quantile_numerator": q.numerator,
        "quantile_denominator": q.denominator,
        "frames": len(checked),
        "sentinel_frames": checked.count(ALWAYS_MASKED_Q16),
        "selected_index": None,
        "selected_requirement": None,
        "calibration_kept": None,
        "calibration_retention": None,
        "method": "exact higher order statistic; all logical requirements included",
    }
    if not checked:
        result["reason"] = "empty calibration population"
        return result
    index = (q.numerator * (len(checked) - 1) + q.denominator - 1) // q.denominator
    selected = sorted(checked)[index]
    result.update(selected_index=index, selected_requirement=selected)
    if selected == ALWAYS_MASKED_Q16 or selected > MAX_MULTIPLIER_Q16:
        result["reason"] = (
            "selected order statistic cannot be kept by a deployable multiplier"
        )
        return result
    eta = max(1, selected)
    kept = sum(x != ALWAYS_MASKED_Q16 and x <= eta for x in checked)
    result.update(
        status="selected",
        eta_q16=eta,
        calibration_kept=kept,
        calibration_retention=kept / len(checked),
    )
    return result


def coarse_quantile_threshold(scores, *, quantile=None, percent=None):
    """Use the existing float NumPy higher quantile; exact replay is the caller's job."""
    q = _quantile(quantile, percent)
    values = _nonnegative(scores, "coarse scores")
    result = {
        "status": "unavailable",
        "reason": None,
        "eta": None,
        "eta_numerator": None,
        "eta_denominator": None,
        "quantile_numerator": q.numerator,
        "quantile_denominator": q.denominator,
        "frames": len(values),
        "calibration_kept": None,
        "calibration_retention": None,
        "method": "numpy.quantile(float(q), method='higher'); caller must replay exact rational powers",
    }
    if not len(values):
        result["reason"] = "empty calibration population"
        return result
    eta = float(np.quantile(values, float(q), method="higher"))
    if eta <= 0:
        result["reason"] = "selected coarse threshold is not positive"
        return result
    numerator, denominator = eta.as_integer_ratio()
    kept = int(np.count_nonzero(values <= eta))
    result.update(
        status="selected",
        eta=eta,
        eta_numerator=numerator,
        eta_denominator=denominator,
        calibration_kept=kept,
        calibration_retention=kept / len(values),
    )
    return result


def overlap_2x2(left, right):
    """Return paired Boolean counts; matrix rows=left, columns=right, order drop/keep."""
    left, right = _mask(left, "left mask"), _mask(right, "right mask")
    if left.shape != right.shape:
        raise ValueError("paired masks must describe the same frame population")
    dd = int(np.count_nonzero(~left & ~right))
    dk = int(np.count_nonzero(~left & right))
    kd = int(np.count_nonzero(left & ~right))
    kk = int(np.count_nonzero(left & right))
    union = dk + kd + kk
    return {
        "frames": len(left),
        "matrix": [[dd, dk], [kd, kk]],
        "row_policy": "left",
        "column_policy": "right",
        "axis_order": ["drop", "keep"],
        "both_dropped": dd,
        "right_only_kept": dk,
        "left_only_kept": kd,
        "both_kept": kk,
        "left_kept": kd + kk,
        "right_kept": dk + kk,
        "agreement_fraction": (dd + kk) / len(left) if len(left) else None,
        "kept_jaccard": kk / union if union else None,
    }


def same_mask_summary(mask, residuals, exposures=None):
    """Summarize one fixed mask with strictly finite residuals and positive exposure.

    Residual means are bookkeeping summaries of the supplied array. Neither
    masking nor exposure rescales or calibrates a physical residual. Missing
    residuals are refused even on dropped frames; callers must explicitly
    report missing evidence instead of silently changing the population.
    """
    keep = _mask(mask, "mask")
    residual = _nonnegative(residuals, "residuals")
    exposure = (
        np.ones(len(keep), dtype=np.float64)
        if exposures is None
        else _nonnegative(exposures, "exposures", positive=True)
    )
    if residual.shape != keep.shape or exposure.shape != keep.shape:
        raise ValueError(
            "mask, residual and exposure arrays must have identical shapes"
        )
    n, kept = len(keep), int(np.count_nonzero(keep))
    total_exposure, kept_exposure = _sum(exposure), _sum(exposure[keep])
    kept_residual_sum = _sum(residual[keep])
    weighted_sum = _sum(
        float(r) * float(w) for r, w in zip(residual[keep], exposure[keep])
    )
    return {
        "status": "available" if kept else "no retained frames",
        "frames": n,
        "kept": kept,
        "dropped": n - kept,
        "retention": kept / n if n else None,
        "total_exposure": total_exposure,
        "kept_exposure": kept_exposure,
        "exposure_retention": kept_exposure / total_exposure
        if total_exposure
        else None,
        "mask_only_exposure_cost": total_exposure / kept_exposure
        if kept_exposure
        else None,
        "kept_residual_sum": kept_residual_sum,
        "kept_residual_mean": kept_residual_sum / kept if kept else None,
        "kept_exposure_weighted_residual_sum": weighted_sum,
        "kept_exposure_weighted_residual_mean": weighted_sum / kept_exposure
        if kept_exposure
        else None,
        "scientific_certification": False,
        "physical_confidence_claim": False,
        "scope": "Same-mask descriptive bookkeeping; exposure cost restores the supplied total exposure, without refitting covariance or physical transfer",
    }
