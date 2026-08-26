"""Auditable decisions used by threshold preparation and selection."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from types import MappingProxyType
from typing import Any


SCHEMA = "rfisher-threshold-decisions-v1"

DECISION_BASES = frozenset({
    "instrument",
    "derivation",
    "literature",
    "empirical",
    "policy",
    "implementation",
})

DECISION_STATUSES = frozenset({
    "derived",
    "locked",
    "provisional",
    "open",
    "conditional",
    "historical",
})


class PolicyNotOperational(ValueError):
    """Raised when unresolved decisions are used for an operational claim."""


@dataclass(frozen=True)
class Decision:
    """One numerical or methodological choice and its justification."""

    id: str
    value: Any
    units: str
    basis: str
    status: str
    rationale: str
    evidence: tuple[str, ...] = ()
    sensitivity_values: tuple[Any, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "value", _freeze(self.value))
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "sensitivity_values",
                           _freeze(tuple(self.sensitivity_values)))
        if not self.id or any(part == "" for part in self.id.split(".")):
            raise ValueError("decision id must use non-empty dotted parts")
        if self.basis not in DECISION_BASES:
            raise ValueError(f"unknown decision basis {self.basis!r}")
        if self.status not in DECISION_STATUSES:
            raise ValueError(f"unknown decision status {self.status!r}")
        if not self.rationale.strip():
            raise ValueError(f"decision {self.id!r} needs a rationale")
        if self.status not in ("open", "historical") and not self.evidence:
            raise ValueError(f"decision {self.id!r} needs evidence")
        try:
            encoded = json.dumps(self.value, allow_nan=False)
            json.loads(encoded)
            encoded = json.dumps(self.sensitivity_values, allow_nan=False)
            json.loads(encoded)
        except (TypeError, ValueError) as exc:
            raise TypeError(f"decision {self.id!r} is not JSON serializable") from exc

    def record(self) -> dict[str, Any]:
        """Return a JSON-ready record."""
        return asdict(self)


def _freeze(value):
    """Freeze nested values so the decision digest cannot drift."""
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, dict):
        return tuple(sorted((key, _freeze(item))
                            for key, item in value.items()))
    return value


def _json_ready(value):
    """Convert frozen containers to their canonical JSON form."""
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    return value


def _d(id, value, units, basis, status, rationale, *evidence,
       sensitivity_values=()):
    return Decision(
        id=id,
        value=value,
        units=units,
        basis=basis,
        status=status,
        rationale=rationale,
        evidence=tuple(evidence),
        sensitivity_values=tuple(sensitivity_values),
    )


_DECISION_LIST = (
    _d(
        "science.systematic_budget.primary_zeta", 1.0, "sigma", "policy",
        "provisional",
        "The paper uses a permissive screening budget of one statistical "
        "standard deviation; a collaboration must set its own total budget.",
        "https://doi.org/10.1111/j.1365-2966.2007.12731.x",
        sensitivity_values=(0.5, 0.3, 0.1),
    ),
    _d(
        "science.systematic_budget.sensitivity_zeta", [0.5, 0.3, 0.1],
        "sigma", "policy", "locked",
        "These values expose progressively tighter systematic budgets and "
        "have direct root-mean-square error interpretations.",
        "dissertation/chapters/ch09_tolerance.tex",
    ),
    _d(
        "science.response_stability.time_fraction", 0.10, "fraction",
        "policy", "provisional",
        "The Fisher response is re-evaluated at plus and minus ten percent in "
        "integration time to expose interpolation and cancellation failures.",
        "scripts/bias_tolerance.py",
        sensitivity_values=(0.05, 0.10, 0.20),
    ),
    _d(
        "science.response_stability.maximum_tolerance_ratio", 1.20, "ratio",
        "policy", "provisional",
        "A response is refused when its inferred tolerance moves by more than "
        "twenty percent across the time perturbations.",
        "scripts/bias_tolerance.py",
        sensitivity_values=(1.10, 1.20, 1.50),
    ),
    _d(
        "science.response_solver.maximum_condition_number", 1.0e12,
        "condition number", "literature", "provisional",
        "Modes beyond this condition number are treated as numerically "
        "unresolved. The limit is conservative relative to the released "
        "banks but remains a material numerical choice.",
        "https://doi.org/10.1137/1.9780898718027",
        "src/rfisher/forecast.py",
        sensitivity_values=(1.0e10, 1.0e12, 1.0e14),
    ),
    _d(
        "science.response_solver.relative_nullspace_cutoff",
        1.4901161193847656e-08, "relative singular scale", "literature",
        "provisional",
        "The square root of float64 machine epsilon separates numerical "
        "null-space overlap from roundoff. This is standard numerical "
        "screening rather than a science-derived tolerance.",
        "https://doi.org/10.1137/1.9780898718027",
        "src/rfisher/forecast.py",
        sensitivity_values=(2.220446049250313e-16,
                            1.4901161193847656e-08, 1.0e-6),
    ),
    _d(
        "science.response_solver.minimum_volume_fraction", 1.0e-6,
        "retained bin fraction", "empirical", "provisional",
        "Forecast slices below this retained-volume fraction are treated as "
        "carrying no useful information. The cutoff avoids nearly empty "
        "matrices but remains a sensitivity choice.",
        "src/rfisher/forecast.py",
        sensitivity_values=(0.0, 1.0e-8, 1.0e-6, 1.0e-4),
    ),
    _d(
        "science.response_solver.default_estimator", "perbin_appendix_a",
        "estimator", "literature", "locked",
        "The paper default evaluates each redshift bin with the Appendix-A "
        "parameter set. The combined multibin estimator remains an explicit "
        "alternative.",
        "scripts/bias_tolerance.py",
        "dissertation/chapters/ch09_tolerance.tex",
    ),
    _d(
        "science.response_solver.default_time_scaling",
        "noise_normalized_at_each_time", "time model", "policy",
        "provisional",
        "The default treats one response unit as contemporaneous thermal "
        "power. The fixed-physical alternative tests a persistent residual "
        "defined at a reference time.",
        "scripts/bias_tolerance.py",
        sensitivity_values=("noise_normalized_at_each_time",
                            "fixed_physical_at_reference_time"),
    ),
    _d(
        "era.summary", "monthly_median_unit_level_db", "method",
        "literature", "provisional",
        "Monthly medians reduce the transient tail before station-state "
        "change detection; the monthly cadence is a project choice.",
        "https://doi.org/10.1214/aoms/1177730491",
        "pilot-proxy/analysis/ppcal/eras.py",
    ),
    _d(
        "era.split_method", "recursive_max_abs_z_times_step", "method",
        "empirical", "provisional",
        "The strongest admissible rank-and-level split is taken first. The "
        "scan is not a single Mann-Whitney test and needs holdout validation.",
        "https://doi.org/10.2307/2346729",
        "pilot-proxy/analysis/ppcal/eras.py",
    ),
    _d(
        "era.minimum_observed_months", 6, "months per side", "empirical",
        "provisional",
        "Six months prevents short seasonal excursions from becoming a new "
        "station-state era; no universal value exists.",
        "pilot-proxy/analysis/validate_eras.py",
        sensitivity_values=(4, 6, 9, 12),
    ),
    _d(
        "era.minimum_span_days", 270.0, "days per side", "empirical",
        "provisional",
        "The span requires most of a year on each side of a split while "
        "allowing archive gaps; it is an empirical guardrail.",
        "pilot-proxy/analysis/validate_eras.py",
        sensitivity_values=(180.0, 270.0, 365.25),
    ),
    _d(
        "era.minimum_step_db", 2.0, "dB", "empirical", "provisional",
        "A two-decibel level change targets transmitter-state changes rather "
        "than ordinary propagation variation.",
        "pilot-proxy/analysis/validate_eras.py",
        sensitivity_values=(1.0, 2.0, 3.0),
    ),
    _d(
        "era.rank_z_threshold", 4.0, "normal-score units", "empirical",
        "provisional",
        "The threshold is conservative for one comparison but is not a "
        "globally calibrated change-point false-alarm probability.",
        "https://doi.org/10.1214/aoms/1177730491",
        "https://doi.org/10.2307/2346729",
        sensitivity_values=(3.0, 4.0, 5.0),
    ),
    _d(
        "era.maximum_segments", 5, "eras per channel", "policy",
        "provisional",
        "The cap prevents recursive over-segmentation in one archive; it is "
        "not selected by a formal penalty.",
        "https://doi.org/10.1080/01621459.2012.737745",
        sensitivity_values=(3, 5, 7),
    ),
    _d(
        "era.selection", "latest", "era", "policy", "locked",
        "Only the latest station state represents the channel configuration "
        "for which a new threshold is being chosen.",
        "docs/architecture.md",
    ),
    _d(
        "era.instrument_state_intersection", None, "method", "policy", "open",
        "Station-state eras must eventually be intersected with receiver and "
        "detector configuration eras before an operational export.",
    ),
    _d(
        "floor.upper_percentile", 90.0, "percentile", "policy",
        "provisional",
        "The upper percentile makes the undetected-shelf substitution a "
        "one-sided bound; its exact coverage is not calibrated.",
        "src/rfisher/residual.py",
        sensitivity_values=(75.0, 90.0, 95.0),
    ),
    _d(
        "floor.minimum_null_frames", 30, "frames", "empirical",
        "provisional",
        "Below thirty null frames the tail percentile is treated as too thin "
        "to call measured and falls back to a stated detector-scale bound.",
        "src/rfisher/residual.py",
        sensitivity_values=(30, 50, 100),
    ),
    _d(
        "floor.quiet_era_max_level_db", 1.0, "dB", "empirical",
        "provisional",
        "A qualifying quiet era must remain close to the detector null; the "
        "one-decibel boundary is archive-specific.",
        "pilot-proxy/analysis/ppcal/era_view.py",
        sensitivity_values=(0.5, 1.0, 1.5),
    ),
    _d(
        "floor.null_scale_probes",
        [[32.0, 1.0], [5.0, 1.96], [0.3, 2.9677]],
        "lower-half percentile and normal deviate", "literature",
        "provisional",
        "Three lower-tail quantiles diagnose whether the kept sample has a "
        "Gaussian-like null scale without using its contaminated upper tail.",
        "src/rfisher/residual.py",
    ),
    _d(
        "floor.mu0_agreement_db", 1.5, "dB", "empirical", "provisional",
        "The reported kept-frame floor is called weight-norm determined only "
        "when it agrees with the exact edge prediction inside this band.",
        "src/rfisher/residual.py",
        sensitivity_values=(0.5, 1.0, 1.5),
    ),
    _d(
        "floor.minimum_shelf_split_frames", 11, "frames", "empirical",
        "provisional",
        "The nested shelf decomposition starts only above ten selected frames; "
        "this is a minimal execution guard, not a precision guarantee.",
        "src/rfisher/residual.py",
        sensitivity_values=(11, 30, 100),
    ),
    _d(
        "correlation.measurement_population",
        "valid_positive_excess_frames_with_finite_shelf", "frame rule",
        "policy", "provisional",
        "The current shelf-persistence screen uses the archived positive-"
        "excess decision as a measurement cutoff; this is not an independent "
        "false-alarm-calibrated population.",
        "src/rfisher/residual.py",
    ),
    _d(
        "correlation.acquisition_summary", "mean_linear_shelf_power", "method",
        "derivation", "derived",
        "Power must be averaged in linear units before a variance or "
        "structure function is formed.",
        "src/rfisher/residual.py",
    ),
    _d(
        "correlation.minimum_frames_per_acquisition", 2, "frames",
        "empirical", "provisional",
        "At least two frames are required to estimate the within-acquisition "
        "noise contribution.",
        "src/rfisher/residual.py",
        sensitivity_values=(2, 4, 8),
    ),
    _d(
        "correlation.sidereal_day_seconds", 86164.0905, "seconds",
        "instrument", "locked",
        "The common-mode decomposition is keyed to one mean sidereal day.",
        "https://iers-conventions.obspm.fr/content/chapter1/icc1.pdf",
    ),
    _d(
        "correlation.primary_trim_percentile", 90.0, "percentile",
        "empirical", "provisional",
        "The upper transient tail is removed before measuring the stationary "
        "shelf component; the primary cut is tested against two probes.",
        "src/rfisher/residual.py",
        sensitivity_values=(75.0, 90.0, 95.0),
    ),
    _d(
        "correlation.trim_probes", [75.0, 90.0, 95.0], "percentiles",
        "empirical", "provisional",
        "The probes expose tail-dominated estimates rather than assigning a "
        "universal trim.",
        "src/rfisher/residual.py",
    ),
    _d(
        "correlation.maximum_trim_spread", 2.0, "ratio", "policy",
        "provisional",
        "A factor-of-two change is the current refusal boundary for both the "
        "timescale and surviving power; it is a materiality choice.",
        "src/rfisher/residual.py",
        sensitivity_values=(1.5, 2.0, 3.0),
    ),
    _d(
        "correlation.minimum_selected_frames", 100, "frames per trim",
        "empirical", "provisional",
        "Each trim probe needs a basic frame population before the nested "
        "variance calculation is attempted.",
        "src/rfisher/residual.py",
        sensitivity_values=(100, 200, 500),
    ),
    _d(
        "correlation.minimum_sidereal_days", 100, "days", "empirical",
        "provisional",
        "The day-block interval needs broad day coverage; raw pair counts "
        "alone are not independent support.",
        "https://doi.org/10.1214/aos/1176347265",
        sensitivity_values=(50, 100, 200),
    ),
    _d(
        "correlation.minimum_same_day_pairs", 200, "pairs", "empirical",
        "provisional",
        "This is a gross support guard only because acquisitions recur in "
        "many pairs.",
        "src/rfisher/residual.py",
        sensitivity_values=(100, 200, 500),
    ),
    _d(
        "correlation.lag_edges_seconds",
        [0.0, 300.0, 900.0, 1800.0, 2700.0, 3600.0, 5400.0, 7200.0,
         14400.0, 28800.0],
        "seconds", "empirical", "provisional",
        "The bins follow the available acquisition cadence and stay within "
        "one sidereal day; cadence-matched coverage remains required.",
        "src/rfisher/residual.py",
    ),
    _d(
        "correlation.minimum_pairs_per_lag_bin", 40, "pairs", "empirical",
        "provisional",
        "The current populated-bin gate is not an effective sample size "
        "because observations recur across pairs.",
        "src/rfisher/residual.py",
        sensitivity_values=(20, 40, 80),
    ),
    _d(
        "correlation.minimum_populated_lag_bins", 3, "lag bins", "empirical",
        "provisional",
        "Three populated bins are the minimum used for an interpolated "
        "crossing; this does not establish model adequacy.",
        "src/rfisher/residual.py",
    ),
    _d(
        "correlation.plateau_start_seconds", 7200.0, "seconds", "empirical",
        "provisional",
        "Pairs beyond two hours define the current structure-function "
        "plateau; finite cadence can create false breaks.",
        "https://doi.org/10.1111/j.1365-2966.2010.16328.x",
        sensitivity_values=(5400.0, 7200.0, 10800.0),
    ),
    _d(
        "correlation.crossing_fraction", 1.0 - 1.0 / math.e, "plateau share",
        "literature", "provisional",
        "The crossing is an e-folding persistence time only for an "
        "approximately single-exponential autocorrelation.",
        "https://doi.org/10.1103/PhysRev.36.823",
    ),
    _d(
        "correlation.bootstrap_unit", "sidereal_day", "block", "literature",
        "locked",
        "Whole-day resampling preserves within-day ordering and the physical "
        "common-mode boundary.",
        "https://doi.org/10.1214/aos/1176347265",
    ),
    _d(
        "correlation.bootstrap_replicates", 200, "replicates", "empirical",
        "provisional",
        "Two hundred reproduces the current screen but is not selected from "
        "a target interval-endpoint accuracy.",
        "https://doi.org/10.1111/1468-0262.00092",
        sensitivity_values=(200, 2000, 10000),
    ),
    _d(
        "correlation.bootstrap_seed", 20260807, "integer seed",
        "implementation", "locked",
        "A fixed seed makes the released interval reproducible.",
        "src/rfisher/residual.py",
    ),
    _d(
        "correlation.bootstrap_interval_percentiles", [16.0, 84.0],
        "percentiles", "policy", "provisional",
        "The interval is a one-standard-deviation-style diagnostic rather "
        "than an operational coverage guarantee.",
        "src/rfisher/residual.py",
        sensitivity_values=([2.5, 97.5], [16.0, 84.0]),
    ),
    _d(
        "correlation.minimum_bootstrap_successes", 20, "replicates",
        "empirical", "provisional",
        "At least twenty finite estimates and ten percent of requested "
        "replicates are required before an interval is reported.",
        "src/rfisher/residual.py",
        sensitivity_values=(20, 50, 100),
    ),
    _d(
        "correlation.minimum_bootstrap_success_fraction", 0.10, "fraction",
        "empirical", "provisional",
        "The fractional convergence guard supplements the absolute count.",
        "src/rfisher/residual.py",
        sensitivity_values=(0.10, 0.50, 0.90),
    ),
    _d(
        "correlation.refusal_cap_seconds", 86164.0905, "seconds", "policy",
        "provisional",
        "A refusal receives no common-mode credit and carries all shelf power "
        "at the sidereal-day ceiling as a conservative screening bound.",
        "src/rfisher/residual.py",
    ),
    _d(
        "correlation.cadence_matched_coverage", None, "validation", "empirical",
        "open",
        "Cadence-matched simulation must show that gaps and finite duration do "
        "not create the reported structure-function break.",
        "https://doi.org/10.1111/j.1365-2966.2010.16328.x",
    ),
    _d(
        "correlation.variance_scaling", "rectangular_coherent_block", "model",
        "policy", "provisional",
        "The released screen maps persistence to tau divided by frame time. "
        "This is a coherent-block model, not a general autocorrelation result.",
        "src/rfisher/residual.py",
        sensitivity_values=("rectangular_coherent_block",
                            "integrated_autocorrelation"),
    ),
    _d(
        "correlation.integrated_autocorrelation_validation", None,
        "validation", "literature", "open",
        "Operational variance scaling needs an integrated autocorrelation or "
        "direct block-sum measurement.",
        "https://doi.org/10.2307/2983611",
        "https://doi.org/10.1214/ss/1177011137",
    ),
    _d(
        "transfer.nominal_pilot_below_shelf_db", 11.3, "dB", "literature",
        "provisional",
        "The ATSC convention converts pilot power to aggregate data-shelf "
        "power; receiver-specific departures need measurement.",
        "pilot-proxy/docs/RERUN_PARAMETER_REGISTER.md",
    ),
    _d(
        "transfer.pilot_capture_efficiency", 1.0, "fraction", "policy",
        "conditional",
        "Unity is the current closure assumption until receiver capture "
        "efficiency is measured.",
        "pilot-proxy/docs/RERUN_PARAMETER_REGISTER.md",
        sensitivity_values=(0.8, 0.9, 1.0),
    ),
    _d(
        "transfer.systematic_gain", 1.0, "science residual per shelf proxy",
        "policy", "conditional",
        "Unity is a screening closure, not a measured shelf-to-visibility "
        "systematic transfer.",
        "docs/contamination-residuals.md",
    ),
    _d(
        "transfer.variance_gain", 1.0, "science variance per shelf proxy",
        "policy", "conditional",
        "Unity is a screening closure, not a measured shelf-to-visibility "
        "variance transfer.",
        "docs/contamination-residuals.md",
    ),
    _d(
        "transfer.fine_stage_credit_db", 10.0, "dB", "empirical",
        "provisional",
        "Ten decibels is a rounded screening scenario. The earlier equal-norm "
        "row-sum study measured 9.32 and 9.77 dB at two false-alarm levels, "
        "but did not certify the complete current detector.",
        "pilot-proxy/docs/evidence/fine_gain_mc_2026-08-19/README.md",
        sensitivity_values=(9.32, 9.77, 10.0),
    ),
    _d(
        "transfer.delay_suppression.default_key", "none", "scenario key",
        "policy", "locked",
        "The default claims no delay-filter credit because the forecast does "
        "not model that foreground-removal stage. This is conservative for "
        "the residual budget.",
        "src/rfisher/residual.py",
    ),
    _d(
        "preparation.residual_score_definition",
        "minimum_q16_multiplier_that_keeps_the_frame",
        "exact decision boundary", "derivation", "derived",
        "The required multiplier follows from the deployed integer cross-"
        "multiplication and represents zero-reference cases without a "
        "floating division.",
        "pilot-proxy/src/pilot_proxy/fine_decision.py",
    ),
    _d(
        "preparation.designated_set_calibration", None, "method", "empirical",
        "open",
        "The per-channel latest-era pilot anchor and designated width need a "
        "held-out calibration before the score can be exported.",
    ),
    _d(
        "preparation.usable_bulk_definition",
        "independent_nondesignated_bins_excluding_guard_and_census",
        "bin rule", "derivation", "derived",
        "The reference order statistic must exclude the tested signal region, "
        "its guard, and declared persistent lines.",
        "pilot-proxy/src/pilot_proxy/fine_decision.py",
    ),
    _d(
        "preparation.candidate_rho_grid",
        "all_one_based_ranks_through_minimum_valid_bulk_count",
        "rank grid", "derivation", "derived",
        "Every rank supported by every accepted frame is evaluated, so rank "
        "selection has no coarse-grid approximation or invalid-frame branch.",
        "src/rfisher/preparation.py",
    ),
    _d(
        "preparation.rank_index_mapping",
        "rho_equals_zero_based_cfar_rank_plus_one",
        "index conversion", "derivation", "derived",
        "The detector stores a zero-based array index, while the order "
        "statistic is written as a one-based rank.",
        "src/rfisher/preparation.py",
    ),
    _d(
        "preparation.minimum_multiplier_q16", 1, "Q16 integer",
        "implementation", "locked",
        "One is the smallest positive multiplier accepted by the deployed "
        "integer decision. It is eta = 1 / 65536, not eta = 1.",
        "pilot-proxy/src/pilot_proxy/fine_decision.py",
    ),
    _d(
        "preparation.candidate_multiplier_grid",
        "q16_one_and_unique_required_q16_change_points",
        "Q16 multiplier grid", "derivation", "derived",
        "The mask changes only when the integer multiplier reaches a frame's "
        "required value. Those deployable values give the exact empirical "
        "staircase without a geometric grid.",
        "src/rfisher/preparation.py",
    ),
    _d(
        "preparation.minimum_reference_sweep_frames", 50, "frames",
        "empirical", "historical",
        "The raw coarse reference sweep predates the prepared-family boundary "
        "and returns no rows below fifty source frames.",
    ),
    _d(
        "archive_reference.coarse_eta_fine_segment", [1.0, 1.1, 0.01],
        "start, stop, step", "implementation", "historical",
        "The legacy coarse report samples the knee densely for reproducibility; "
        "this grid is not used by prepared threshold selection.",
        "scripts/optimal_thresholds.py",
    ),
    _d(
        "archive_reference.coarse_eta_mid_segment", [1.1, 2.0, 0.05],
        "start, stop, step", "implementation", "historical",
        "The legacy coarse report uses this intermediate segment only to "
        "reproduce its published sweep.",
        "scripts/optimal_thresholds.py",
    ),
    _d(
        "archive_reference.coarse_eta_geometric_segment", [2.0, 300.0, 16],
        "start, stop, points", "implementation", "historical",
        "The legacy coarse report uses a sparse geometric tail after the "
        "threshold knee; prepared selection uses empirical change points.",
        "scripts/optimal_thresholds.py",
    ),
    _d(
        "archive_reference.raw_eta_grid", [1.0, 1.05, 500.0, 24],
        "explicit point, geometric start, stop, points", "implementation",
        "historical",
        "The raw threshold diagnostic retains this sparse grid only for "
        "report reproducibility; prepared selection uses exact empirical "
        "change points.",
        "src/rfisher/residual.py",
    ),
    _d(
        "archive_reference.positive_excess_eta", 1.0, "multiplier",
        "derivation", "derived",
        "At eta equal to one, the coarse rule is exactly the positive-excess "
        "test F greater than mu0 used by the historical reports.",
        "src/rfisher/residual.py",
    ),
    _d(
        "archive_reference.two_walls_eta_grid",
        [1.0, 1.8, 17, 2.0, 300.0, 12],
        "linear start, stop, points; geometric start, stop, points",
        "implementation", "historical",
        "The two-walls figure retains its original display grid for figure "
        "reproducibility; it is not a prepared selector grid.",
        "scripts/plot_two_walls.py",
    ),
    _d(
        "archive_reference.calibrated_eta_geometric_segment",
        [1.0, 1.01, 60.0, 90], "explicit point, start, stop, points",
        "implementation", "historical",
        "The era calibration export retains its original geometric sweep for "
        "table reproducibility; it is not an operational candidate grid.",
        "scripts/calibrated_thresholds.py",
    ),
    _d(
        "archive_reference.recent_calendar_years", 3, "inclusive years",
        "policy", "historical",
        "Legacy reports show a three-calendar-year occupancy diagnostic; the "
        "latest-era prepared family supersedes this summary.",
        "scripts/optimal_thresholds.py",
    ),
    _d(
        "archive_reference.earliest_recent_year", 2018, "calendar year",
        "instrument", "historical",
        "The legacy recent-occupancy diagnostic does not request years before "
        "the retained survey archive begins.",
        "scripts/optimal_thresholds.py",
    ),
    _d(
        "archive_reference.minimum_diagnostic_cohort_frames", 100, "frames",
        "empirical", "historical",
        "The prototype anchor and recent-occupancy diagnostics decline thinner "
        "cohorts; this is not a precision-derived operational support rule.",
        "scripts/fine_operating_point.py",
    ),
    _d(
        "archive_reference.designated_half_width_bins", 2, "fine bins",
        "instrument", "historical",
        "The prototype designated window matches its two-bin guard convention; "
        "the operational width still requires designated-set calibration.",
        "scripts/fine_operating_point.py",
    ),
    _d(
        "archive_reference.fine_rank_lower_fraction", 0.5, "bulk fraction",
        "policy", "historical",
        "The prototype scans only the upper half of bulk ranks to reproduce "
        "its report; prepared selection scans every supported rank.",
        "scripts/fine_operating_point.py",
    ),
    _d(
        "archive_reference.fine_anchor_estimator",
        "rejected_minus_quiet_median_excess_with_median_fallback",
        "method", "empirical", "historical",
        "The prototype locates the designated line from rejected-minus-quiet "
        "median excess when both cohorts are supported and otherwise uses a "
        "median peak. Operational anchor calibration remains open.",
        "scripts/fine_operating_point.py",
    ),
    _d(
        "archive_reference.fine_tie_multiplier_target", 1.0, "multiplier",
        "policy", "historical",
        "The fine prototype prefers the plateau point nearest unity to stay "
        "inside its sampled staircase. Prepared selection uses the registered "
        "residual-first tie order instead.",
        "scripts/fine_operating_point.py",
    ),
    _d(
        "archive_reference.fine_tie_round_digits", 9, "decimal digits",
        "implementation", "historical",
        "The prototype rounds the distance from unity before later tie keys "
        "for deterministic reproduction of its floating grid.",
        "scripts/fine_operating_point.py",
    ),
    _d(
        "archive_reference.operating_point_tolerance_target", "aperp",
        "forecast parameter", "policy", "historical",
        "The coarse, fine, and two-walls reports use the binding transverse-"
        "dilation tolerance. The prepared selector instead receives a "
        "declared science tolerance directly.",
        "scripts/optimal_thresholds.py",
        "scripts/fine_operating_point.py",
        "scripts/plot_two_walls.py",
    ),
    _d(
        "archive_reference.floor_projection_tolerance_target", "fs8",
        "forecast parameter", "policy", "historical",
        "The floor-projection diagnostic uses the growth-rate tolerance to "
        "show the most restrictive residual lever in its selected cohort.",
        "scripts/floor_projection.py",
    ),
    _d(
        "archive_reference.floor_projection_channels", [32, 33, 34, 35, 36],
        "physical channels", "policy", "historical",
        "The diagnostic focuses on the five upper-band channels used in its "
        "original floor and persistence comparison. It is not a survey-wide "
        "selection cohort.",
        "scripts/floor_projection.py",
    ),
    _d(
        "archive_reference.floor_projection_scenarios",
        ["coarse", "fine", "fine_plus_bao_peak1", "fine_plus_bao_peak2"],
        "ordered report scenarios", "policy", "historical",
        "These four columns reproduce the floor-projection comparison from "
        "the current coarse rule through the two delay-filter bounds.",
        "scripts/floor_projection.py",
    ),
    _d(
        "archive_reference.floor_projection_persistence_reference_channel",
        33, "physical channel", "empirical", "historical",
        "Channel 33 supplies the measured upper bound used by the report's "
        "cross-channel persistence what-if.",
        "scripts/floor_projection.py",
    ),
    _d(
        "archive_reference.forecast_year_grid", [1.0, 2.0, 3.0, 5.0, 8.0],
        "on-sky years", "implementation", "historical",
        "These are the integration-time samples used by the released three-"
        "scenario table; they do not define a threshold operating knob.",
        "scripts/three_worlds.py",
    ),
    _d(
        "archive_reference.three_worlds_parameters",
        ["aperp", "apar", "fs8"], "forecast parameters", "policy",
        "historical",
        "The released three-scenario table reports the two dilation "
        "parameters and the growth-rate combination used in the chapter.",
        "scripts/three_worlds.py",
    ),
    _d(
        "archive_reference.three_worlds_response_grid",
        [0.0, 6.0, 19, 3.5, 5.83, 8],
        "log10-hour start, stop, points for two segments", "implementation",
        "historical",
        "The merged 27-point grid reproduces the response-bank interpolation "
        "check used by the released table.",
        "scripts/three_worlds.py",
    ),
    _d(
        "archive_reference.three_worlds_channels", [29, 32, 33, 35],
        "physical channels", "policy", "historical",
        "These channels reproduce the released comparison cohort; the table "
        "is not a survey-wide threshold export.",
        "scripts/three_worlds.py",
    ),
    _d(
        "archive_reference.three_worlds_scenarios",
        ["none", "peak1", "peak2", "deployed"],
        "ordered response scenarios", "policy", "historical",
        "The released table compares no delay-filter credit, two acoustic-"
        "preserving bounds, and the deployed-cut scenario in this order.",
        "scripts/three_worlds.py",
    ),
    _d(
        "archive_reference.bias_year_grid", [0.25, 1.0, 5.0, 10.0],
        "on-sky years", "implementation", "historical",
        "These samples reproduce the standalone bias-tolerance report; they "
        "do not set an operating threshold.",
        "scripts/bias_tolerance.py",
    ),
    _d(
        "preparation.equal_exposure_frames", True, "requirement",
        "derivation", "derived",
        "Count fractions equal exposure fractions only when every accepted "
        "frame carries the same exposure.",
        "src/rfisher/thresholds.py",
    ),
    _d(
        "preparation.additive_residuals", True, "requirement", "derivation",
        "derived",
        "Histogram prefix sums are sufficient only when correlation and "
        "transfer corrections do not need refitting after masking.",
        "src/rfisher/thresholds.py",
    ),
    _d(
        "stability.split", "latest_era_calendar_midpoint", "method",
        "policy", "locked",
        "Calendar time, rather than frame count, avoids hiding drift when "
        "archive cadence changes.",
        "scripts/fine_operating_point.py",
    ),
    _d(
        "stability.surface", "all_candidate_rho_q16_pairs", "method",
        "derivation", "derived",
        "Every selector-evaluable point needs a supported early/late drift "
        "check so the selected point cannot evade validation.",
        "src/rfisher/preparation.py",
    ),
    _d(
        "stability.minimum_half_retained_frames", None,
        "retained frames per half", "empirical", "open",
        "Early and late residual estimates need their own precision-based "
        "support rule; the pooled selector floor is not that derivation.",
        sensitivity_values=(15, 30, 50, 100),
    ),
    _d(
        "stability.maximum_cost_ratio", None, "early/late ratio", "policy",
        "open",
        "A practical-equivalence margin must be tied to the largest cost "
        "change that cannot alter the science decision.",
        "https://doi.org/10.1007/BF01068419",
        sensitivity_values=(1.02, 1.05, 1.10),
    ),
    _d(
        "stability.maximum_systematic_residual_ratio", None,
        "early/late ratio", "policy", "open",
        "A practical-equivalence margin must come from transfer uncertainty "
        "or a science-materiality allocation; no universal ratio exists.",
        "https://doi.org/10.1007/BF01068419",
        sensitivity_values=(1.05, 1.10, 1.20),
    ),
    _d(
        "stability.uncertainty_validation", None, "validation", "literature",
        "open",
        "The current early/late ratio screen has no confidence interval. An "
        "operational stability claim needs block-based uncertainty whose "
        "interval lies inside the declared margins.",
        "https://doi.org/10.1214/aos/1176347265",
        "https://doi.org/10.1007/BF01068419",
    ),
    _d(
        "selection.minimum_retained_frames", 30, "frames", "empirical",
        "provisional",
        "The current selector declines candidates supported by fewer than "
        "thirty retained frames; the value needs sensitivity testing.",
        "src/rfisher/thresholds.py",
        sensitivity_values=(30, 50, 100),
    ),
    _d(
        "selection.cost_plateau_ratio", 1.02, "cost ratio", "policy",
        "provisional",
        "Candidates within two percent of minimum cost are treated as "
        "practically tied before residual margin breaks the tie.",
        "src/rfisher/thresholds.py",
        sensitivity_values=(1.00, 1.01, 1.02, 1.05),
    ),
    _d(
        "selection.tie_break",
        ["systematic_residual", "masked_fraction", "rho", "multiplier_q16"],
        "lexicographic order", "policy", "locked",
        "The order favors science margin, then exposure, then the simpler "
        "rank and multiplier when forecast cost is practically tied.",
        "src/rfisher/thresholds.py",
    ),
    _d(
        "selection.tolerance_equality_is_feasible", True, "rule",
        "derivation", "derived",
        "The tolerance defines a closed upper bound, so equality passes.",
        "src/rfisher/thresholds.py",
    ),
    _d(
        "detection.false_alarm_probability", None, "probability per decision",
        "policy", "open",
        "The clean-frame loss allocation must be chosen before a null "
        "threshold can be derived.",
        "https://doi.org/10.1098/rsta.1933.0009",
    ),
    _d(
        "detection.minimum_injection_recovery", None, "probability",
        "policy", "open",
        "Detection power must be checked with declared injections after the "
        "false-alarm allocation is fixed.",
        "https://doi.org/10.1021/ac60259a007",
    ),
    _d(
        "archive_diagnostic.eta_ladder", [1.0, 1.1, 1.2, 1.4, 2.0, 5.0],
        "multipliers", "implementation", "historical",
        "This sparse ladder supports the existing calibration report only; it "
        "is not the prepared threshold candidate family.",
        "pilot-proxy/analysis/ppcal/calib.py",
    ),
    _d(
        "archive_diagnostic.null_center_agreement_db", 0.20, "dB",
        "empirical", "provisional",
        "The report calls a null available when its robust centre remains "
        "within this archive-specific band of the analytic constant.",
        "pilot-proxy/analysis/ppcal/calib.py",
        sensitivity_values=(0.10, 0.20, 0.30),
    ),
    _d(
        "archive_diagnostic.minimum_lower_tail_frames", 20, "frames",
        "empirical", "provisional",
        "The legacy lower-tail scale diagnostic refuses thinner samples; the "
        "value is not a precision calculation.",
        "pilot-proxy/analysis/ppcal/calib.py",
        sensitivity_values=(20, 30, 50),
    ),
    _d(
        "archive_diagnostic.detection_floor_false_alarm_probability", 0.001,
        "one-sided probability", "policy", "historical",
        "The report marker uses this nominal Gaussian-tail probability and is "
        "not an independently measured false-alarm rate.",
        "pilot-proxy/analysis/ppcal/calib.py",
    ),
    _d(
        "archive_diagnostic.detection_floor_normal_deviate",
        3.090232306167813, "standard deviations", "derivation", "derived",
        "This is the inverse standard-normal CDF at one minus the diagnostic "
        "false-alarm probability.",
        "pilot-proxy/analysis/ppcal/calib.py",
    ),
    _d(
        "archive_diagnostic.kept_tail_percentile", 99.0, "percentile",
        "policy", "historical",
        "The existing report summarizes the upper kept-frame tail at p99; it "
        "does not enter the prepared selector.",
        "pilot-proxy/analysis/ppcal/calib.py",
    ),
    _d(
        "archive_disposition.excision_masked_fraction", 0.50, "fraction",
        "policy", "historical",
        "The legacy report excises above fifty-percent masking. The forecast "
        "selector prices masking continuously instead.",
        "pilot-proxy/analysis/ppcal/state.py",
    ),
    _d(
        "archive_disposition.light_masking_fraction", 0.10, "fraction",
        "policy", "historical",
        "Ten percent only labels legacy report rows as light or heavy masking; "
        "it is not a scientific feasibility boundary.",
        "pilot-proxy/analysis/ppcal/state.py",
    ),
    _d(
        "archive_disposition.carrier_dominated_level_db", 3.0, "dB",
        "empirical", "provisional",
        "The archive has an empty population gap between one and 5.3 dB, so "
        "three decibels separates null-centred and carrier-centred modes.",
        "pilot-proxy/analysis/ppcal/state.py",
        sensitivity_values=(1.0, 2.0, 3.0, 5.0),
    ),
    _d(
        "archive_disposition.fallback_eta", 1.4, "multiplier", "policy",
        "historical",
        "This global fallback reproduces report rows when no channel threshold "
        "is available. It cannot support an operational disposition.",
        "pilot-proxy/analysis/ppcal/state.py",
    ),
    _d(
        "archive_diagnostic.maximum_threshold_bracket_ratio", 1.10, "ratio",
        "policy", "provisional",
        "The report calls a threshold identified when its coherence bracket "
        "moves it by less than ten percent; this is a materiality choice.",
        "pilot-proxy/analysis/ppcal/state.py",
        sensitivity_values=(1.05, 1.10, 1.20),
    ),
)

DECISIONS = MappingProxyType({item.id: item for item in _DECISION_LIST})
if len(DECISIONS) != len(_DECISION_LIST):
    raise RuntimeError("threshold decision ids must be unique")


_OPERATIONAL_PREFIXES = (
    "science.", "era.", "floor.", "correlation.", "transfer.",
    "preparation.", "stability.", "selection.", "detection.",
)
OPERATIONAL_REQUIRED_IDS = tuple(sorted(
    item.id for item in _DECISION_LIST
    if item.id.startswith(_OPERATIONAL_PREFIXES) and item.status != "historical"
))


def decision(id: str) -> Decision:
    """Return one decision by stable id."""
    try:
        return DECISIONS[id]
    except KeyError as exc:
        raise KeyError(f"unknown threshold decision {id!r}") from exc


def value(id: str):
    """Return one decision value."""
    return decision(id).value


def era_kwargs() -> dict[str, Any]:
    """Arguments for the current station-state era segmenter."""
    return {
        "min_months": int(value("era.minimum_observed_months")),
        "min_days": float(value("era.minimum_span_days")),
        "min_step_db": float(value("era.minimum_step_db")),
        "z_crit": float(value("era.rank_z_threshold")),
        "max_eras": int(value("era.maximum_segments")),
    }


def quiet_floor_kwargs() -> dict[str, Any]:
    """Arguments for a latest-era quiet-floor measurement."""
    return {
        "level_threshold_db": float(value("floor.quiet_era_max_level_db")),
        "percentile": float(value("floor.upper_percentile")),
        "minimum_frames": int(value("floor.minimum_null_frames")),
    }


def snapshot(ids=None) -> dict[str, Any]:
    """Return a deterministic, JSON-ready decision snapshot."""
    selected = sorted(DECISIONS if ids is None else tuple(ids))
    return {
        "schema": SCHEMA,
        "decisions": [_json_ready(decision(id).record()) for id in selected],
    }


def canonical_json(ids=None) -> str:
    """Return the canonical serialized decision snapshot."""
    return json.dumps(
        snapshot(ids), sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False)


def sha256(ids=None) -> str:
    """Digest the canonical decision snapshot."""
    payload = canonical_json(ids).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def blockers(ids=None, *, allow_provisional: bool = False,
             allow_conditional: bool = False) -> tuple[Decision, ...]:
    """Return decisions that cannot support the requested claim."""
    selected = sorted(DECISIONS if ids is None else tuple(ids))
    accepted = {"derived", "locked"}
    if allow_provisional:
        accepted.add("provisional")
    if allow_conditional:
        accepted.add("conditional")
    return tuple(decision(id) for id in selected
                 if decision(id).status not in accepted)


def require_operational(ids=OPERATIONAL_REQUIRED_IDS, *,
                        allow_provisional: bool = False,
                        allow_conditional: bool = False) -> None:
    """Refuse an operational claim while required decisions are unresolved."""
    unresolved = blockers(
        ids,
        allow_provisional=allow_provisional,
        allow_conditional=allow_conditional,
    )
    if unresolved:
        joined = ", ".join(f"{item.id} ({item.status})" for item in unresolved)
        raise PolicyNotOperational(f"unresolved threshold decisions: {joined}")


__all__ = [
    "SCHEMA", "DECISION_BASES", "DECISION_STATUSES", "DECISIONS",
    "OPERATIONAL_REQUIRED_IDS", "Decision", "PolicyNotOperational",
    "decision", "value", "era_kwargs", "quiet_floor_kwargs", "snapshot",
    "canonical_json", "sha256", "blockers",
    "require_operational",
]
