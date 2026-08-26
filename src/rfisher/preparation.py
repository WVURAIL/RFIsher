"""Evidence gates for prepared residual-score histogram families."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
import datetime as dt
import hashlib
import json
import math
from numbers import Integral, Real
from types import MappingProxyType

import numpy as np

from . import selection_policy
from .thresholds import (ALWAYS_MASKED_Q16, MAX_MULTIPLIER_Q16,
                         MIN_RETAINED_FRAMES, MULTIPLIER_ONE,
                         ResidualScoreHistogram, ThresholdOptimization,
                         build_q16_residual_score_histogram,
                         optimize_threshold)


class PreparationRefused(RuntimeError):
    """Raised when a prepared family lacks required evidence."""


def rho_from_cfar_rank(cfar_rank: int) -> int:
    """Convert the detector's zero-based rank to one-based rho."""
    if isinstance(cfar_rank, bool) or not isinstance(cfar_rank, Integral):
        raise TypeError("cfar_rank must be an integer")
    rank = int(cfar_rank)
    if rank < 0:
        raise ValueError("cfar_rank must be non-negative")
    return rank + 1


def candidate_rho_values(minimum_valid_bulk_count: int) -> tuple[int, ...]:
    """Return every one-based rank supported by all accepted frames."""
    if (isinstance(minimum_valid_bulk_count, bool)
            or not isinstance(minimum_valid_bulk_count, Integral)):
        raise TypeError("minimum_valid_bulk_count must be an integer")
    size = int(minimum_valid_bulk_count)
    if size <= 0:
        raise ValueError("minimum_valid_bulk_count must be positive")
    return tuple(range(1, size + 1))


def candidate_multiplier_q16_values(
        required_multiplier_q16,
) -> tuple[int, ...]:
    """Return the exact deployable empirical decision staircase."""
    if isinstance(required_multiplier_q16, (str, bytes)):
        raise TypeError("required_multiplier_q16 must be a sequence of integers")
    try:
        values = tuple(required_multiplier_q16)
    except TypeError as exc:
        raise TypeError(
            "required_multiplier_q16 must be a sequence of integers") from exc
    if not values:
        raise ValueError("required_multiplier_q16 must not be empty")
    floor = int(selection_policy.value("preparation.minimum_multiplier_q16"))
    candidates = {floor}
    for raw in values:
        if isinstance(raw, bool) or not isinstance(raw, Integral):
            raise TypeError(
                "required_multiplier_q16 must contain only integers")
        value = int(raw)
        if not 1 <= value <= ALWAYS_MASKED_Q16:
            raise ValueError(
                "required_multiplier_q16 contains an invalid decision boundary")
        if value <= MAX_MULTIPLIER_Q16:
            candidates.add(value)
    return tuple(sorted(candidates))


@dataclass(frozen=True)
class EraHalfSupport:
    """Independent support recorded for one calendar half of an era."""

    frame_count: int
    acquisition_count: int
    observed_months: int
    span_days: float

    def __post_init__(self):
        for name in ("frame_count", "acquisition_count", "observed_months"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, Integral):
                raise TypeError(f"{name} must be an integer")
            if int(value) < 0:
                raise ValueError(f"{name} must be non-negative")
            object.__setattr__(self, name, int(value))
        if (isinstance(self.span_days, bool)
                or not isinstance(self.span_days, Real)):
            raise TypeError("span_days must be a number")
        span = float(self.span_days)
        if not math.isfinite(span) or span < 0.0:
            raise ValueError("span_days must be non-negative and finite")
        object.__setattr__(self, "span_days", span)


@dataclass(frozen=True)
class StabilityAssessment:
    """Deterministic early/late drift screen for a candidate surface."""

    status: str
    reason: str
    early_support: EraHalfSupport
    late_support: EraHalfSupport
    points_checked: int
    points_skipped: int
    maximum_cost_ratio: float | None
    maximum_systematic_residual_ratio: float | None
    maximum_masked_fraction_difference: float | None
    worst_cost_point: tuple[int, float] | None
    worst_systematic_point: tuple[int, float] | None
    worst_cost_multiplier_q16: int | None
    worst_systematic_multiplier_q16: int | None
    cost_ratio_limit: float | None
    systematic_residual_ratio_limit: float | None
    minimum_observed_months: int
    minimum_span_days: float
    minimum_half_retained_frames: int | None

    @property
    def passed(self) -> bool:
        return self.status == "passed"


@dataclass(frozen=True)
class CalibrationEvidence:
    """Evidence state for one conditioning operation."""

    state: str
    method: str
    source: str
    detail: str = ""
    artifact_sha256: str | None = None
    bounds: tuple[float | None, float | None] | None = None
    units: str | None = None

    def __post_init__(self):
        allowed = {"measured", "bounded", "conditional", "unmeasured",
                   "refused"}
        if self.state not in allowed:
            raise ValueError(f"unknown calibration evidence state {self.state!r}")
        if not self.method.strip():
            raise ValueError("calibration evidence needs a method")
        if not self.source.strip():
            raise ValueError("calibration evidence needs a source")
        digest = self.artifact_sha256
        if digest is not None and (
                len(digest) != 64
                or any(ch not in "0123456789abcdef" for ch in digest)):
            raise ValueError("artifact_sha256 must be a lowercase SHA-256 digest")
        if self.state in {"measured", "bounded"} and digest is None:
            raise ValueError(
                f"{self.state} evidence needs an artifact SHA-256 digest")
        if self.bounds is not None:
            if len(self.bounds) != 2:
                raise ValueError("bounds must contain lower and upper values")
            checked = []
            for value in self.bounds:
                if value is None:
                    checked.append(None)
                elif isinstance(value, bool) or not isinstance(value, Real):
                    raise TypeError("bounds must contain numbers or None")
                elif not math.isfinite(float(value)):
                    raise ValueError("bounds must be finite")
                else:
                    checked.append(float(value))
            if checked == [None, None]:
                raise ValueError("at least one bound must be supplied")
            if (checked[0] is not None and checked[1] is not None
                    and checked[0] > checked[1]):
                raise ValueError("lower bound cannot exceed upper bound")
            object.__setattr__(self, "bounds", tuple(checked))
        if self.state == "bounded":
            if self.bounds is None or not self.units:
                raise ValueError("bounded evidence needs bounds and units")


def _ratio(left: float, right: float) -> float:
    if left == 0.0 and right == 0.0:
        return 1.0
    if left <= 0.0 or right <= 0.0:
        return math.inf
    return max(left, right) / min(left, right)


def _limit(value, name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a number or None")
    result = float(value)
    if not math.isfinite(result) or result < 1.0:
        raise ValueError(f"{name} must be finite and at least one")
    return result


def _ranked(histograms, name: str) -> dict[int, ResidualScoreHistogram]:
    if not isinstance(histograms, Mapping):
        raise TypeError(f"{name} must be a mapping")
    if not histograms:
        raise ValueError(f"{name} must not be empty")
    out = {}
    for rho, histogram in histograms.items():
        if isinstance(rho, bool) or not isinstance(rho, Integral):
            raise TypeError(f"{name} keys must be integers")
        if int(rho) <= 0:
            raise ValueError(f"{name} keys must be positive")
        if not isinstance(histogram, ResidualScoreHistogram):
            raise TypeError(f"{name} values must be ResidualScoreHistogram")
        out[int(rho)] = histogram
    return out


def _surface(histogram: ResidualScoreHistogram):
    has_variance = histogram.variance_residual_sums is not None
    kept = 0
    systematic = 0.0
    variance = 0.0
    out = []
    total = histogram.frame_count
    for index, eta in enumerate(histogram.candidate_eta):
        kept += histogram.counts[index]
        systematic += histogram.systematic_residual_sums[index]
        if has_variance:
            variance += histogram.variance_residual_sums[index]
        if kept == 0:
            out.append(None)
            continue
        kept_fraction = kept / total
        systematic_mean = systematic / kept
        variance_mean = variance / kept if has_variance else None
        cost = ((1.0 + (0.0 if variance_mean is None else variance_mean))
                / kept_fraction)
        out.append((kept, kept_fraction, systematic_mean, variance_mean, cost))
    return tuple(out)


def assess_histogram_stability(
        early_histograms: Mapping[int, ResidualScoreHistogram],
        late_histograms: Mapping[int, ResidualScoreHistogram],
        *,
        early_support: EraHalfSupport,
        late_support: EraHalfSupport,
        max_cost_ratio: float | None,
        max_systematic_residual_ratio: float | None,
        minimum_observed_months: int | None = None,
        minimum_span_days: float | None = None,
        minimum_half_retained_frames: int | None = None,
) -> StabilityAssessment:
    """Screen early/late point estimates using one frozen calibration.

    The screen is independent of science tolerance. It is not a statistical
    equivalence test; operational use also needs block-based uncertainty.
    """
    early = _ranked(early_histograms, "early_histograms")
    late = _ranked(late_histograms, "late_histograms")
    if set(early) != set(late):
        raise ValueError("early and late histograms must use the same ranks")
    if not isinstance(early_support, EraHalfSupport):
        raise TypeError("early_support must be EraHalfSupport")
    if not isinstance(late_support, EraHalfSupport):
        raise TypeError("late_support must be EraHalfSupport")
    if any(hist.frame_count != early_support.frame_count
           for hist in early.values()):
        raise ValueError("early support frame count does not match histograms")
    if any(hist.frame_count != late_support.frame_count
           for hist in late.values()):
        raise ValueError("late support frame count does not match histograms")
    for rho in sorted(early):
        early_hist = early[rho]
        late_hist = late[rho]
        if early_hist.bulk_size != late_hist.bulk_size:
            raise ValueError("early and late histograms must use the same bulk")
        if early_hist.candidate_eta != late_hist.candidate_eta:
            raise ValueError("early and late histograms must use the same eta grid")
        if (early_hist.candidate_multiplier_q16
                != late_hist.candidate_multiplier_q16):
            raise ValueError("early and late histograms must use the same Q16 grid")
        if ((early_hist.variance_residual_sums is None)
                != (late_hist.variance_residual_sums is None)):
            raise ValueError("early and late histograms need the same variance basis")

    min_months = int(
        selection_policy.value("era.minimum_observed_months")
        if minimum_observed_months is None else minimum_observed_months)
    min_days = float(
        selection_policy.value("era.minimum_span_days")
        if minimum_span_days is None else minimum_span_days)
    if min_months <= 0:
        raise ValueError("minimum_observed_months must be positive")
    if not math.isfinite(min_days) or min_days <= 0.0:
        raise ValueError("minimum_span_days must be positive and finite")
    if minimum_half_retained_frames is None:
        min_half = None
    else:
        if (isinstance(minimum_half_retained_frames, bool)
                or not isinstance(minimum_half_retained_frames, Integral)):
            raise TypeError("minimum_half_retained_frames must be an integer")
        min_half = int(minimum_half_retained_frames)
        if min_half <= 0:
            raise ValueError("minimum_half_retained_frames must be positive")
    cost_limit = _limit(max_cost_ratio, "max_cost_ratio")
    systematic_limit = _limit(
        max_systematic_residual_ratio,
        "max_systematic_residual_ratio")

    base = dict(
        early_support=early_support,
        late_support=late_support,
        points_checked=0,
        points_skipped=0,
        maximum_cost_ratio=None,
        maximum_systematic_residual_ratio=None,
        maximum_masked_fraction_difference=None,
        worst_cost_point=None,
        worst_systematic_point=None,
        worst_cost_multiplier_q16=None,
        worst_systematic_multiplier_q16=None,
        cost_ratio_limit=cost_limit,
        systematic_residual_ratio_limit=systematic_limit,
        minimum_observed_months=min_months,
        minimum_span_days=min_days,
        minimum_half_retained_frames=min_half,
    )
    for label, support in (("early", early_support), ("late", late_support)):
        if support.observed_months < min_months:
            return StabilityAssessment(
                status="refused_insufficient_support",
                reason=(f"{label} half has {support.observed_months} observed "
                        f"months; need {min_months}"), **base)
        if support.span_days < min_days:
            return StabilityAssessment(
                status="refused_insufficient_support",
                reason=(f"{label} half spans {support.span_days:g} days; "
                        f"need {min_days:g}"), **base)
    if cost_limit is None or systematic_limit is None or min_half is None:
        return StabilityAssessment(
            status="refused_unconfigured",
            reason=("both drift limits and the per-half retained-frame floor "
                    "must be declared"),
            **base)

    cost_rows = []
    systematic_rows = []
    mask_rows = []
    skipped = 0
    for rho in sorted(early):
        early_hist = early[rho]
        late_hist = late[rho]
        early_surface = _surface(early_hist)
        late_surface = _surface(late_hist)
        for index, eta in enumerate(early_hist.candidate_eta):
            epoint = early_surface[index]
            lpoint = late_surface[index]
            early_kept = 0 if epoint is None else epoint[0]
            late_kept = 0 if lpoint is None else lpoint[0]
            if early_kept + late_kept < MIN_RETAINED_FRAMES:
                skipped += 1
                continue
            if (epoint is None or lpoint is None
                    or early_kept < min_half or late_kept < min_half):
                unsupported = dict(base)
                unsupported["points_skipped"] = skipped
                return StabilityAssessment(
                    status="refused_insufficient_support",
                    reason=(f"candidate rho={rho}, eta={eta:g} retains fewer "
                            f"than {min_half} frames in one era half"),
                    **unsupported)
            key = (rho, eta)
            q16 = (None if early_hist.candidate_multiplier_q16 is None else
                   early_hist.candidate_multiplier_q16[index])
            cost_rows.append((_ratio(epoint[4], lpoint[4]), key, q16))
            systematic_rows.append(
                (_ratio(epoint[2], lpoint[2]), key, q16))
            mask_rows.append((abs(epoint[1] - lpoint[1]), key))

    if not cost_rows:
        base["points_skipped"] = skipped
        return StabilityAssessment(
            status="refused_insufficient_support",
            reason="no selector-evaluable candidate has supported era halves",
            **base)
    worst_cost, worst_cost_point, worst_cost_q16 = max(
        cost_rows, key=lambda item: item[0])
    worst_systematic, worst_systematic_point, worst_systematic_q16 = max(
        systematic_rows, key=lambda item: item[0])
    worst_mask, _ = max(mask_rows, key=lambda item: item[0])
    measured = dict(base)
    measured.update(
        points_checked=len(cost_rows),
        points_skipped=skipped,
        maximum_cost_ratio=float(worst_cost),
        maximum_systematic_residual_ratio=float(worst_systematic),
        maximum_masked_fraction_difference=float(worst_mask),
        worst_cost_point=worst_cost_point,
        worst_systematic_point=worst_systematic_point,
        worst_cost_multiplier_q16=worst_cost_q16,
        worst_systematic_multiplier_q16=worst_systematic_q16,
    )
    failures = []
    if worst_cost > cost_limit:
        failures.append(
            f"cost ratio {worst_cost:.6g} exceeds {cost_limit:.6g} at "
            f"rho={worst_cost_point[0]}, eta={worst_cost_point[1]:g}")
    if worst_systematic > systematic_limit:
        failures.append(
            f"systematic-residual ratio {worst_systematic:.6g} exceeds "
            f"{systematic_limit:.6g} at rho={worst_systematic_point[0]}, "
            f"eta={worst_systematic_point[1]:g}")
    if failures:
        return StabilityAssessment(
            status="refused_drift", reason="; ".join(failures), **measured)
    return StabilityAssessment(
        status="passed",
        reason="supported point estimates are within both declared drift limits",
        **measured)


def _one_dimensional_numeric(values, name: str, *, positive=False):
    array = np.asarray(values)
    if array.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    if not np.issubdtype(array.dtype, np.number):
        raise TypeError(f"{name} must contain only numbers")
    if np.issubdtype(array.dtype, np.complexfloating):
        raise TypeError(f"{name} must contain only real numbers")
    array = array.astype(float, copy=False)
    if not np.isfinite(array).all():
        raise ValueError(f"{name} must be finite")
    if positive and (array <= 0.0).any():
        raise ValueError(f"{name} must be positive")
    return array


def _half_support(times, acquisitions) -> EraHalfSupport:
    months = {
        (stamp.year, stamp.month)
        for stamp in (dt.datetime.fromtimestamp(float(value), dt.timezone.utc)
                      for value in times)
    }
    return EraHalfSupport(
        frame_count=int(times.size),
        acquisition_count=len(set(acquisitions)),
        observed_months=len(months),
        span_days=float((times.max() - times.min()) / 86400.0),
    )


def prepare_threshold_family(
        required_multiplier_q16_by_rho,
        systematic_residuals,
        *,
        frame_times,
        acquisition_ids,
        exposure_seconds,
        source_id: str,
        era_label: str,
        latest_era: bool,
        additive_residuals: bool,
        score: CalibrationEvidence,
        correlation: CalibrationEvidence,
        transfer: CalibrationEvidence,
        max_cost_ratio: float | None,
        max_systematic_residual_ratio: float | None,
        minimum_half_retained_frames: int | None,
        variance_residuals=None,
        minimum_observed_months: int | None = None,
        minimum_span_days: float | None = None,
) -> PreparedThresholdFamily:
    """Build a complete family from accepted latest-era Q16 boundaries.

    Era discovery and invalid-frame bookkeeping stay outside this function.
    This boundary derives the candidate grids, calendar split, support counts,
    histograms, and deterministic drift screen from the supplied frame rows.
    """
    requirements = _ranked_requirements(required_multiplier_q16_by_rho)
    bulk_size = max(requirements)
    if tuple(sorted(requirements)) != candidate_rho_values(bulk_size):
        raise ValueError("requirements must contain every supported rank")
    systematic = _one_dimensional_numeric(
        systematic_residuals, "systematic_residuals")
    if (systematic < 0.0).any():
        raise ValueError("systematic_residuals must be non-negative")
    variance = (None if variance_residuals is None else
                _one_dimensional_numeric(
                    variance_residuals, "variance_residuals"))
    if variance is not None and (variance < 0.0).any():
        raise ValueError("variance_residuals must be non-negative")
    times = _one_dimensional_numeric(frame_times, "frame_times")
    exposure = _one_dimensional_numeric(
        exposure_seconds, "exposure_seconds", positive=True)
    try:
        acquisitions = tuple(acquisition_ids)
    except TypeError as exc:
        raise TypeError("acquisition_ids must be a sequence") from exc
    size = systematic.size
    if size == 0:
        raise ValueError("frame rows must not be empty")
    for values, name in ((variance, "variance_residuals"),
                         (times, "frame_times"),
                         (exposure, "exposure_seconds")):
        if values is not None and values.size != size:
            raise ValueError(f"{name} must match systematic_residuals")
    if len(acquisitions) != size:
        raise ValueError("acquisition_ids must match systematic_residuals")
    try:
        set(acquisitions)
    except TypeError as exc:
        raise TypeError("acquisition_ids must contain hashable values") from exc
    if any(len(values) != size for values in requirements.values()):
        raise ValueError("all ranks must describe the same frame population")
    if not np.equal(exposure, exposure[0]).all():
        raise ValueError("accepted frames must have equal exposure")
    start = float(times.min())
    stop = float(times.max())
    if stop <= start:
        raise ValueError("frame_times must span more than one instant")
    early_mask = times <= 0.5 * (start + stop)
    late_mask = ~early_mask
    if not early_mask.any() or not late_mask.any():
        raise ValueError("calendar split must leave frames in both halves")

    pooled = {}
    early = {}
    late = {}
    for rho, values in requirements.items():
        q16 = candidate_multiplier_q16_values(values)
        pooled[rho] = build_q16_residual_score_histogram(
            values, systematic, q16, bulk_size=bulk_size,
            variance_residuals=variance)
        early[rho] = build_q16_residual_score_histogram(
            tuple(value for value, keep in zip(values, early_mask) if keep),
            systematic[early_mask], q16, bulk_size=bulk_size,
            variance_residuals=(None if variance is None else
                                variance[early_mask]))
        late[rho] = build_q16_residual_score_histogram(
            tuple(value for value, keep in zip(values, late_mask) if keep),
            systematic[late_mask], q16, bulk_size=bulk_size,
            variance_residuals=(None if variance is None else
                                variance[late_mask]))

    early_support = _half_support(
        times[early_mask], tuple(value for value, keep
                                 in zip(acquisitions, early_mask) if keep))
    late_support = _half_support(
        times[late_mask], tuple(value for value, keep
                                in zip(acquisitions, late_mask) if keep))
    stability = assess_histogram_stability(
        early, late,
        early_support=early_support,
        late_support=late_support,
        max_cost_ratio=max_cost_ratio,
        max_systematic_residual_ratio=max_systematic_residual_ratio,
        minimum_observed_months=minimum_observed_months,
        minimum_span_days=minimum_span_days,
        minimum_half_retained_frames=minimum_half_retained_frames,
    )
    return PreparedThresholdFamily(
        histograms_by_rho=pooled,
        source_id=source_id,
        era_label=era_label,
        latest_era=latest_era,
        valid_frames_only=True,
        equal_exposure_frames=True,
        additive_residuals=additive_residuals,
        stability=stability,
        score=score,
        correlation=correlation,
        transfer=transfer,
    )


def _ranked_requirements(values):
    if not isinstance(values, Mapping):
        raise TypeError("required_multiplier_q16_by_rho must be a mapping")
    if not values:
        raise ValueError("required_multiplier_q16_by_rho must not be empty")
    out = {}
    for rho, requirements in values.items():
        if isinstance(rho, bool) or not isinstance(rho, Integral):
            raise TypeError("requirement keys must be integers")
        if int(rho) <= 0:
            raise ValueError("requirement keys must be positive")
        try:
            items = tuple(requirements)
        except TypeError as exc:
            raise TypeError("rank requirements must be sequences") from exc
        candidate_multiplier_q16_values(items)
        out[int(rho)] = items
    return out


@dataclass(frozen=True)
class PreparedThresholdFamily:
    """Histogram family plus the evidence required to interpret it."""

    histograms_by_rho: Mapping[int, ResidualScoreHistogram]
    source_id: str
    era_label: str
    latest_era: bool
    valid_frames_only: bool
    equal_exposure_frames: bool
    additive_residuals: bool
    stability: StabilityAssessment
    score: CalibrationEvidence
    correlation: CalibrationEvidence
    transfer: CalibrationEvidence
    policy_json: str = field(default_factory=selection_policy.canonical_json)
    policy_sha256: str = field(default_factory=selection_policy.sha256)

    def __post_init__(self):
        histograms = _ranked(self.histograms_by_rho, "histograms_by_rho")
        bulk_size = next(iter(histograms.values())).bulk_size
        expected_ranks = candidate_rho_values(bulk_size)
        if tuple(sorted(histograms)) != expected_ranks:
            raise ValueError(
                "prepared families must contain every supported rank")
        for histogram in histograms.values():
            if histogram.bulk_size != bulk_size:
                raise ValueError("prepared histograms need one common bulk size")
            q16 = histogram.candidate_multiplier_q16
            if q16 is None:
                raise ValueError("prepared histograms need exact Q16 multipliers")
            if q16[0] != int(selection_policy.value(
                    "preparation.minimum_multiplier_q16")):
                raise ValueError("prepared multiplier grids must start at Q16 one")
        object.__setattr__(self, "histograms_by_rho",
                           MappingProxyType(dict(sorted(histograms.items()))))
        if not self.source_id.startswith("sha256:"):
            raise ValueError("source_id must be a sha256 content identifier")
        source_digest = self.source_id.removeprefix("sha256:")
        if (len(source_digest) != 64
                or any(ch not in "0123456789abcdef" for ch in source_digest)):
            raise ValueError("source_id must contain a lowercase SHA-256 digest")
        if not self.era_label.strip():
            raise ValueError("era_label must not be empty")
        for name in ("latest_era", "valid_frames_only",
                     "equal_exposure_frames", "additive_residuals"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be boolean")
        if not isinstance(self.stability, StabilityAssessment):
            raise TypeError("stability must be StabilityAssessment")
        for name in ("score", "correlation", "transfer"):
            if not isinstance(getattr(self, name), CalibrationEvidence):
                raise TypeError(f"{name} must be CalibrationEvidence")
        if not isinstance(self.policy_json, str):
            raise TypeError("policy_json must be a string")
        try:
            policy = json.loads(self.policy_json)
        except json.JSONDecodeError as exc:
            raise ValueError("policy_json must contain valid JSON") from exc
        if policy.get("schema") != selection_policy.SCHEMA:
            raise ValueError("policy_json uses an unknown schema")
        if (len(self.policy_sha256) != 64
                or any(ch not in "0123456789abcdef" for ch in self.policy_sha256)):
            raise ValueError("policy_sha256 must be a lowercase SHA-256 digest")
        stored_sha256 = hashlib.sha256(self.policy_json.encode("utf-8")).hexdigest()
        if self.policy_sha256 != stored_sha256:
            raise ValueError("policy_sha256 does not match policy_json")

    def refusals(self, *, allow_screening: bool = False) -> tuple[str, ...]:
        """Return every reason this family cannot support selection."""
        out = []
        if (self.policy_sha256 != selection_policy.sha256()
                or self.policy_json != selection_policy.canonical_json()):
            out.append("threshold decision snapshot does not match this release")
        if not self.latest_era:
            out.append("the histogram does not describe the latest era")
        if not self.valid_frames_only:
            out.append("invalid frames were not removed during preparation")
        if not self.equal_exposure_frames:
            out.append("frame counts are not equal-exposure counts")
        if not self.additive_residuals:
            out.append("residual calibration is mask-dependent and non-additive")
        if not self.stability.passed:
            out.append(f"within-era stability {self.stability.status}: "
                       f"{self.stability.reason}")
        if not allow_screening:
            unresolved = selection_policy.blockers(
                selection_policy.OPERATIONAL_REQUIRED_IDS)
            if unresolved:
                joined = ", ".join(
                    f"{item.id} ({item.status})" for item in unresolved)
                out.append(f"unresolved operating decisions: {joined}")
        accepted = ({"measured", "bounded", "conditional"}
                    if allow_screening else {"measured", "bounded"})
        if self.score.state not in accepted:
            out.append(f"score evidence is {self.score.state}")
        if self.correlation.state not in accepted:
            out.append(f"correlation evidence is {self.correlation.state}")
        if self.transfer.state not in accepted:
            out.append(f"science transfer evidence is {self.transfer.state}")
        return tuple(out)

    @property
    def status(self) -> str:
        if not self.refusals():
            return "operational"
        if not self.refusals(allow_screening=True):
            return "screening"
        return "refused"

    def metadata(self) -> dict:
        """Return the policy identity and evidence state for serialization."""
        return {
            "source_id": self.source_id,
            "era_label": self.era_label,
            "status": self.status,
            "latest_era": self.latest_era,
            "valid_frames_only": self.valid_frames_only,
            "equal_exposure_frames": self.equal_exposure_frames,
            "additive_residuals": self.additive_residuals,
            "policy_sha256": self.policy_sha256,
            "policy": json.loads(self.policy_json),
            "stability": asdict(self.stability),
            "score": asdict(self.score),
            "correlation": asdict(self.correlation),
            "transfer": asdict(self.transfer),
        }


@dataclass(frozen=True)
class PreparedThresholdSelection:
    """Numerical selection plus the claim and provenance that permit it."""

    claim_status: str
    source_id: str
    policy_sha256: str
    optimization: ThresholdOptimization

    @property
    def selected(self):
        return self.optimization.selected

    @property
    def points(self):
        return self.optimization.points

    @property
    def status(self):
        return self.optimization.status


def select_prepared_threshold(
        family: PreparedThresholdFamily,
        science_tolerance: float,
        *,
        allow_screening: bool = False,
) -> PreparedThresholdSelection:
    """Run the numerical selector only after preparation evidence passes."""
    if not isinstance(family, PreparedThresholdFamily):
        raise TypeError("family must be PreparedThresholdFamily")
    reasons = family.refusals(allow_screening=allow_screening)
    if reasons:
        raise PreparationRefused("; ".join(reasons))
    optimization = optimize_threshold(
        family.histograms_by_rho, science_tolerance)
    return PreparedThresholdSelection(
        claim_status="screening" if allow_screening else "operational",
        source_id=family.source_id,
        policy_sha256=family.policy_sha256,
        optimization=optimization,
    )


__all__ = [
    "PreparationRefused", "rho_from_cfar_rank", "candidate_rho_values",
    "candidate_multiplier_q16_values",
    "EraHalfSupport", "StabilityAssessment", "CalibrationEvidence",
    "PreparedThresholdFamily", "PreparedThresholdSelection",
    "assess_histogram_stability", "prepare_threshold_family",
    "select_prepared_threshold",
]
