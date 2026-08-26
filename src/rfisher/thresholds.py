"""Select detector thresholds from calibrated residual-score histograms."""
from __future__ import annotations

from bisect import bisect_left
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
from numbers import Integral, Real

import numpy as np

from .selection_policy import value as _policy_value

MIN_RETAINED_FRAMES = int(
    _policy_value("selection.minimum_retained_frames"))
COST_PLATEAU = float(_policy_value("selection.cost_plateau_ratio"))
MULTIPLIER_Q = 16
MULTIPLIER_ONE = 1 << MULTIPLIER_Q
MAX_MULTIPLIER_Q16 = (1 << 64) - 1
ALWAYS_MASKED_Q16 = 1 << 64

__all__ = ["MIN_RETAINED_FRAMES", "COST_PLATEAU", "MULTIPLIER_Q",
           "MULTIPLIER_ONE", "MAX_MULTIPLIER_Q16", "ALWAYS_MASKED_Q16",
           "ResidualScoreHistogram", "ThresholdPoint",
           "ThresholdOptimization", "build_residual_score_histogram",
           "build_q16_residual_score_histogram",
           "optimize_threshold"]


def _float_tuple(values, name: str, *,
                 positive: bool = False) -> tuple[float, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{name} must be a sequence of numbers")
    try:
        items = tuple(values)
    except TypeError as exc:
        raise TypeError(f"{name} must be a sequence of numbers") from exc
    out = []
    for value in items:
        if isinstance(value, bool) or not isinstance(value, Real):
            raise TypeError(f"{name} must contain only numbers")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"{name} must contain only finite values")
        if positive and number <= 0.0:
            raise ValueError(f"{name} must contain only positive values")
        if not positive and number < 0.0:
            raise ValueError(f"{name} must contain only non-negative values")
        out.append(number)
    return tuple(out)


def _count_tuple(values) -> tuple[int, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError("counts must be a sequence of integers")
    try:
        items = tuple(values)
    except TypeError as exc:
        raise TypeError("counts must be a sequence of integers") from exc
    out = []
    for value in items:
        if isinstance(value, bool) or not isinstance(value, Integral):
            raise TypeError("counts must contain only integers")
        count = int(value)
        if count < 0:
            raise ValueError("counts must be non-negative")
        out.append(count)
    return tuple(out)


def _q16_tuple(values, name: str) -> tuple[int, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{name} must be a sequence of integers")
    try:
        items = tuple(values)
    except TypeError as exc:
        raise TypeError(f"{name} must be a sequence of integers") from exc
    out = []
    for value in items:
        if isinstance(value, bool) or not isinstance(value, Integral):
            raise TypeError(f"{name} must contain only integers")
        q16 = int(value)
        if not 1 <= q16 <= MAX_MULTIPLIER_Q16:
            raise ValueError(
                f"{name} must be between 1 and {MAX_MULTIPLIER_Q16}")
        out.append(q16)
    return tuple(out)


def _science_tolerance(value) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError("science_tolerance must be a number")
    tolerance = float(value)
    if not math.isfinite(tolerance) or tolerance <= 0.0:
        raise ValueError("science_tolerance must be positive and finite")
    return tolerance


def _positive_integer(value, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError(f"{name} must be an integer")
    number = int(value)
    if number <= 0:
        raise ValueError(f"{name} must be positive")
    return number


@dataclass(frozen=True)
class ResidualScoreHistogram:
    """A complete score histogram for one candidate rank.

    Ranks are one-based. Every accepted frame must have the same duration and
    exposure, so count fractions are also exposure fractions. All ranks in one
    optimization must describe the same accepted frame population and common
    usable bulk.

    ``counts[j]`` covers scores above the previous boundary and at or below
    ``candidate_eta[j]``. For an exact family,
    ``candidate_multiplier_q16[j]`` is authoritative and ``candidate_eta`` is
    only its floating display value. The final count is the overflow above the
    last boundary. Residual arrays contain calibrated additive totals in the
    same bins. Their prefix sum divided by the retained count must be the
    calibrated residual for that retained population. A calibration that must
    be rerun after masking cannot use this compressed form.
    """

    bulk_size: int
    candidate_eta: tuple[float, ...]
    counts: tuple[int, ...]
    systematic_residual_sums: tuple[float, ...]
    variance_residual_sums: tuple[float, ...] | None = None
    candidate_multiplier_q16: tuple[int, ...] | None = None

    def __post_init__(self):
        bulk_size = _positive_integer(self.bulk_size, "bulk_size")
        eta = _float_tuple(self.candidate_eta, "candidate_eta", positive=True)
        counts = _count_tuple(self.counts)
        systematic = _float_tuple(
            self.systematic_residual_sums, "systematic_residual_sums")
        variance = (None if self.variance_residual_sums is None else
                    _float_tuple(self.variance_residual_sums,
                                 "variance_residual_sums"))
        q16 = (None if self.candidate_multiplier_q16 is None else
               _q16_tuple(self.candidate_multiplier_q16,
                          "candidate_multiplier_q16"))

        if not eta:
            raise ValueError("candidate_eta must not be empty")
        if len(counts) != len(eta) + 1:
            raise ValueError("counts must include one overflow bin")
        if len(systematic) != len(counts):
            raise ValueError("systematic_residual_sums must match counts")
        if variance is not None and len(variance) != len(counts):
            raise ValueError("variance_residual_sums must match counts")
        if q16 is not None:
            if len(q16) != len(eta):
                raise ValueError("candidate_multiplier_q16 must match candidate_eta")
            if any(right <= left for left, right in zip(q16, q16[1:])):
                raise ValueError("candidate_multiplier_q16 must be strictly increasing")
            expected = tuple(value / MULTIPLIER_ONE for value in q16)
            if eta != expected:
                raise ValueError("candidate_eta must exactly match Q16 multipliers")
        elif any(right <= left for left, right in zip(eta, eta[1:])):
            raise ValueError("candidate_eta must be strictly increasing")
        if sum(counts) == 0:
            raise ValueError("the histogram must contain at least one frame")
        for index, count in enumerate(counts):
            if count == 0 and systematic[index] != 0.0:
                raise ValueError("an empty bin cannot carry systematic residual")
            if count == 0 and variance is not None and variance[index] != 0.0:
                raise ValueError("an empty bin cannot carry variance residual")

        object.__setattr__(self, "bulk_size", bulk_size)
        object.__setattr__(self, "candidate_eta", eta)
        object.__setattr__(self, "counts", counts)
        object.__setattr__(self, "systematic_residual_sums", systematic)
        object.__setattr__(self, "variance_residual_sums", variance)
        object.__setattr__(self, "candidate_multiplier_q16", q16)

    @property
    def frame_count(self) -> int:
        return sum(self.counts)


@dataclass(frozen=True)
class ThresholdPoint:
    """One evaluated ``(rho, eta)`` pair."""

    rho: int
    bulk_size: int
    rank_fraction: float
    eta: float
    multiplier_q16: int | None
    frame_count: int
    kept_frames: int
    masked_frames: int
    masked_fraction: float
    systematic_residual: float
    variance_residual: float | None
    tolerance_fraction: float
    cost: float
    feasible: bool


@dataclass(frozen=True)
class ThresholdOptimization:
    """The evaluated surface and its selected point, when one is feasible."""

    science_tolerance: float
    frame_count: int
    bulk_size: int
    points: tuple[ThresholdPoint, ...]
    selected: ThresholdPoint | None
    status: str


def build_residual_score_histogram(
        scores: Sequence[float],
        systematic_residuals: Sequence[float],
        candidate_eta: Sequence[float],
    *,
    bulk_size: int,
    variance_residuals: Sequence[float] | None = None,
) -> ResidualScoreHistogram:
    """Bin prepared per-frame scores and calibrated residual contributions."""
    bulk_size = _positive_integer(bulk_size, "bulk_size")
    eta = _float_tuple(candidate_eta, "candidate_eta", positive=True)
    if not eta:
        raise ValueError("candidate_eta must not be empty")
    if any(right <= left for left, right in zip(eta, eta[1:])):
        raise ValueError("candidate_eta must be strictly increasing")

    score = np.asarray(scores)
    systematic = np.asarray(systematic_residuals)
    variance = (None if variance_residuals is None else
                np.asarray(variance_residuals))
    for values, name in ((score, "scores"),
                         (systematic, "systematic_residuals")):
        if values.ndim != 1:
            raise ValueError(f"{name} must be one-dimensional")
        if not np.issubdtype(values.dtype, np.number):
            raise TypeError(f"{name} must contain only numbers")
        if np.issubdtype(values.dtype, np.complexfloating):
            raise TypeError(f"{name} must contain only real numbers")
    if variance is not None:
        if variance.ndim != 1:
            raise ValueError("variance_residuals must be one-dimensional")
        if not np.issubdtype(variance.dtype, np.number):
            raise TypeError("variance_residuals must contain only numbers")
        if np.issubdtype(variance.dtype, np.complexfloating):
            raise TypeError("variance_residuals must contain only real numbers")
    if score.size == 0:
        raise ValueError("scores must not be empty")
    if systematic.shape != score.shape:
        raise ValueError("systematic_residuals must match scores")
    if variance is not None and variance.shape != score.shape:
        raise ValueError("variance_residuals must match scores")

    score = score.astype(float, copy=False)
    systematic = systematic.astype(float, copy=False)
    variance = None if variance is None else variance.astype(float, copy=False)
    if not np.isfinite(score).all() or (score < 0.0).any():
        raise ValueError("scores must be non-negative and finite")
    if not np.isfinite(systematic).all() or (systematic < 0.0).any():
        raise ValueError("systematic_residuals must be non-negative and finite")
    if variance is not None and (
            not np.isfinite(variance).all() or (variance < 0.0).any()):
        raise ValueError("variance_residuals must be non-negative and finite")

    bins = np.searchsorted(np.asarray(eta), score, side="left")
    size = len(eta) + 1
    counts = np.bincount(bins, minlength=size)
    systematic_sums = np.bincount(
        bins, weights=systematic, minlength=size)
    variance_sums = (None if variance is None else
                     np.bincount(bins, weights=variance, minlength=size))
    return ResidualScoreHistogram(
        bulk_size=bulk_size,
        candidate_eta=eta,
        counts=tuple(int(value) for value in counts),
        systematic_residual_sums=tuple(float(value)
                                       for value in systematic_sums),
        variance_residual_sums=(
            None if variance_sums is None else
            tuple(float(value) for value in variance_sums)),
    )


def build_q16_residual_score_histogram(
        required_multiplier_q16: Sequence[int],
        systematic_residuals: Sequence[float],
        candidate_multiplier_q16: Sequence[int],
        *,
        bulk_size: int,
        variance_residuals: Sequence[float] | None = None,
) -> ResidualScoreHistogram:
    """Bin exact per-frame Q16 decision boundaries.

    ``ALWAYS_MASKED_Q16`` is the overflow sentinel for a frame that cannot be
    kept by any deployable multiplier. A frame is kept when the selected
    multiplier is at least its required value.
    """
    bulk_size = _positive_integer(bulk_size, "bulk_size")
    candidates = _q16_tuple(
        candidate_multiplier_q16, "candidate_multiplier_q16")
    if not candidates:
        raise ValueError("candidate_multiplier_q16 must not be empty")
    if any(right <= left for left, right in zip(candidates, candidates[1:])):
        raise ValueError("candidate_multiplier_q16 must be strictly increasing")
    if isinstance(required_multiplier_q16, (str, bytes)):
        raise TypeError("required_multiplier_q16 must be a sequence of integers")
    try:
        requirements = tuple(required_multiplier_q16)
    except TypeError as exc:
        raise TypeError(
            "required_multiplier_q16 must be a sequence of integers") from exc
    if not requirements:
        raise ValueError("required_multiplier_q16 must not be empty")
    checked = []
    for value in requirements:
        if isinstance(value, bool) or not isinstance(value, Integral):
            raise TypeError("required_multiplier_q16 must contain only integers")
        requirement = int(value)
        if not 1 <= requirement <= ALWAYS_MASKED_Q16:
            raise ValueError(
                "required_multiplier_q16 contains an invalid decision boundary")
        checked.append(requirement)

    systematic = np.asarray(systematic_residuals)
    variance = (None if variance_residuals is None else
                np.asarray(variance_residuals))
    for values, name in ((systematic, "systematic_residuals"),
                         (variance, "variance_residuals")):
        if values is None:
            continue
        if values.ndim != 1:
            raise ValueError(f"{name} must be one-dimensional")
        if not np.issubdtype(values.dtype, np.number):
            raise TypeError(f"{name} must contain only numbers")
        if np.issubdtype(values.dtype, np.complexfloating):
            raise TypeError(f"{name} must contain only real numbers")
        if values.size != len(checked):
            raise ValueError(f"{name} must match required_multiplier_q16")
        values = values.astype(float, copy=False)
        if not np.isfinite(values).all() or (values < 0.0).any():
            raise ValueError(f"{name} must be non-negative and finite")
        if name == "systematic_residuals":
            systematic = values
        else:
            variance = values

    bins = np.fromiter(
        (bisect_left(candidates, value) for value in checked),
        dtype=np.int64, count=len(checked))
    size = len(candidates) + 1
    counts = np.bincount(bins, minlength=size)
    systematic_sums = np.bincount(
        bins, weights=systematic, minlength=size)
    variance_sums = (None if variance is None else
                     np.bincount(bins, weights=variance, minlength=size))
    return ResidualScoreHistogram(
        bulk_size=bulk_size,
        candidate_eta=tuple(value / MULTIPLIER_ONE for value in candidates),
        candidate_multiplier_q16=candidates,
        counts=tuple(int(value) for value in counts),
        systematic_residual_sums=tuple(float(value)
                                       for value in systematic_sums),
        variance_residual_sums=(
            None if variance_sums is None else
            tuple(float(value) for value in variance_sums)),
    )


def _same_total(left: float, right: float) -> bool:
    scale = max(abs(left), abs(right), 1.0)
    return math.isclose(left, right, rel_tol=1e-10, abs_tol=1e-12 * scale)


def _within_tolerance(residual: float, tolerance: float) -> bool:
    return residual <= tolerance


def optimize_threshold(
        histograms_by_rho: Mapping[int, ResidualScoreHistogram],
        science_tolerance: float,
) -> ThresholdOptimization:
    """Select ``(rho, eta)`` from histograms and a science tolerance.

    Preparation owns frame rejection, era selection, stability, correlation,
    residual calibration, and equal-exposure frame construction. Mapping keys
    are one-based ranks. This function derives masking and retained residuals
    only from the prepared histograms. Each rank may use its own candidate
    ``eta`` grid. Points within two percent of the minimum cost prefer lower
    systematic residual, less masking, lower ``rho``, then the lower exact
    multiplier (or lower ``eta`` for a legacy floating histogram).
    """
    tolerance = _science_tolerance(science_tolerance)
    if not isinstance(histograms_by_rho, Mapping):
        raise TypeError("histograms_by_rho must be a mapping")
    if not histograms_by_rho:
        raise ValueError("histograms_by_rho must not be empty")

    histograms = []
    for rho, histogram in histograms_by_rho.items():
        if isinstance(rho, bool) or not isinstance(rho, Integral):
            raise TypeError("rho keys must be integers")
        if int(rho) <= 0:
            raise ValueError("rho keys must be positive")
        if not isinstance(histogram, ResidualScoreHistogram):
            raise TypeError("mapping values must be ResidualScoreHistogram")
        histograms.append((int(rho), histogram))
    histograms.sort(key=lambda item: item[0])

    frame_count = histograms[0][1].frame_count
    bulk_size = histograms[0][1].bulk_size
    has_variance = histograms[0][1].variance_residual_sums is not None
    systematic_total = sum(histograms[0][1].systematic_residual_sums)
    variance_total = (None if not has_variance else
                      sum(histograms[0][1].variance_residual_sums))
    for _, histogram in histograms[1:]:
        if histogram.frame_count != frame_count:
            raise ValueError("all ranks must describe the same frame population")
        if histogram.bulk_size != bulk_size:
            raise ValueError("all ranks must use the same bulk size")
        if (histogram.variance_residual_sums is not None) != has_variance:
            raise ValueError("all ranks must use the same variance-residual basis")
        if not _same_total(sum(histogram.systematic_residual_sums),
                           systematic_total):
            raise ValueError("all ranks must have the same systematic residual total")
        if has_variance and not _same_total(
                sum(histogram.variance_residual_sums), variance_total):
            raise ValueError("all ranks must have the same variance residual total")

    points = []
    for rho, histogram in histograms:
        if rho > histogram.bulk_size:
            raise ValueError("rho cannot exceed the histogram bulk size")
        kept = 0
        systematic_sum = 0.0
        variance_sum = 0.0
        for index, eta in enumerate(histogram.candidate_eta):
            kept += histogram.counts[index]
            systematic_sum += histogram.systematic_residual_sums[index]
            if has_variance:
                variance_sum += histogram.variance_residual_sums[index]
            if kept < MIN_RETAINED_FRAMES:
                continue
            masked = frame_count - kept
            masked_fraction = masked / frame_count
            systematic_residual = systematic_sum / kept
            variance_residual = (variance_sum / kept if has_variance else None)
            cost_residual = 0.0 if variance_residual is None else variance_residual
            cost = (1.0 + cost_residual) / (1.0 - masked_fraction)
            points.append(ThresholdPoint(
                rho=rho,
                bulk_size=bulk_size,
                rank_fraction=rho / (bulk_size + 1),
                eta=eta,
                multiplier_q16=(
                    None if histogram.candidate_multiplier_q16 is None else
                    histogram.candidate_multiplier_q16[index]),
                frame_count=frame_count,
                kept_frames=kept,
                masked_frames=masked,
                masked_fraction=masked_fraction,
                systematic_residual=systematic_residual,
                variance_residual=variance_residual,
                tolerance_fraction=systematic_residual / tolerance,
                cost=cost,
                feasible=_within_tolerance(systematic_residual, tolerance),
            ))

    feasible = [point for point in points if point.feasible]
    if feasible:
        minimum_cost = min(point.cost for point in feasible)
        near = [point for point in feasible
                if point.cost <= COST_PLATEAU * minimum_cost]
        selected = min(
            near,
            key=lambda point: (point.systematic_residual,
                               point.masked_fraction, point.rho,
                               (point.multiplier_q16
                                if point.multiplier_q16 is not None
                                else point.eta)))
    else:
        selected = None
    if selected is not None:
        status = "selected"
    elif points:
        status = "no_feasible_threshold"
    else:
        status = "no_evaluable_threshold"
    return ThresholdOptimization(
        science_tolerance=tolerance,
        frame_count=frame_count,
        bulk_size=bulk_size,
        points=tuple(points),
        selected=selected,
        status=status,
    )
