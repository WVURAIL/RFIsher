"""The tolerance-selected operating point ``(rho*, eta*)`` of one channel, and
its held-out evaluation.

Calibration block -> :func:`rfisher.residual_scores.build_residual_score_bundle`
(exact per-frame Q16 requirements per rank from the retained fine terms, for
the designated set ``D`` of the measured anchor and the bulk ``B``) ->
per-frame systematic residuals -> :func:`rfisher.preparation.prepare_threshold_family`
(the exact candidate grids, the within-era drift screen) ->
:func:`rfisher.preparation.select_prepared_threshold` (chapter 6
eq:detection:frontier and the cost ``C = (1 + r_var) / (1 - f)`` over points
with ``r_sys <= r_tol``, the 2% plateau, the lexicographic tie-break).
Evaluation block -> a second bundle on the same anchor and bulk, replayed at
the selected ``(rho*, eta*_q16)``: a frame is kept when the selected
multiplier is at least its required value.

Per-frame systematic residual (the ``shelf-or-floor linear`` convention):
``10^(shelf_db / 10)`` on frames with a finite shelf estimate (positive
normalized excess), the channel floor otherwise; ``r_sys`` is the kept-frame
mean, so it is ``r_proxy`` under the unity-transfer closure. Variance
residuals are not available from the products; ``r_var = 0`` and the cost
reduces to the masking term, as chapter 9 says it does.

Provisional values (design section 6, all ``open`` in the decision register,
recorded on every result): drift screen limits 30 frames / cost ratio 1.05 /
systematic ratio 1.10. The calendar-support minimums (6 observed months and
270 days per half of the calibration block) are the register's.

Frames whose acquisition has no recorded sample interval have no
reproducible time and are excluded from both blocks (the bundle requires
finite frame times); the count is recorded.

Outputs: :class:`SelectionResult` (one per channel) with the selected point,
the plateau (members of ``P`` at ``rho*``: count and eta range), the refusal
or status, and the evaluation-block replay (masked fraction, retained
residual, ``R = r_sys / r_tol``, and, where the block is a verified off era,
the empirical false-alarm rate) with acquisition block bootstraps.

Claim status. ``select_prepared_threshold`` refuses a family whose
within-era drift screen did not pass. As coded in :mod:`rfisher.preparation`,
that screen refuses the whole family when any selector-evaluable candidate
(30 or more kept frames pooled) retains fewer than the declared minimum in
one calendar half, so a sparse small-eta candidate that no selector would
choose refuses every channel with an uneven split. Whether that is the
intended rule is a register decision (``stability.*``). When it refuses,
this module still runs the numerical selector on the prepared pooled
histograms and reports the point with ``claim_status = 'diagnostic'`` and the
refusal beside it; a point is ``screening`` or ``operational`` only when the
screen passed. The stability assessment is recorded on every result.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import numpy as np

from rfisher.preparation import (
    CalibrationEvidence, PreparationRefused, select_prepared_threshold,
)
from rfisher.residual_scores import ResidualScoreRefused, build_residual_score_bundle
from rfisher.thresholds import ALWAYS_MASKED_Q16, Q16_SCALE, optimize_threshold

from . import blocks
from .products import Product, sha256_of

DESIGNATED_HALF_WIDTH = 2               # D = {(f_a + k) mod 256 : |k| <= 2}
PLATEAU_RATIO = 1.02                    # P = {C <= 1.02 C_min}

# design section 6: provisional stability-screen values (register ids stability.*)
PROVISIONAL_MIN_HALF_RETAINED = 30
PROVISIONAL_MAX_COST_RATIO = 1.05
PROVISIONAL_MAX_SYSTEMATIC_RATIO = 1.10


@dataclass(frozen=True)
class Floor:
    """The channel floor the residual convention falls back to on kept frames."""

    db: float
    evidence: str            # 'measured' | 'stated' | 'refused'
    population: str          # e.g. 'off era 2024-12..2026-04, 11168 frames' or 'sigma-implied substitute'

    @property
    def linear(self) -> float:
        return 10.0 ** (self.db / 10.0) if math.isfinite(self.db) else math.nan


@dataclass(frozen=True)
class Plateau:
    members: int             # points within 2% of the minimum cost at rho*
    eta_low: float
    eta_high: float
    rho_values: tuple[int, ...]   # every rho represented in P (flat-in-rho surfaces report the lowest)


@dataclass(frozen=True)
class Replay:
    """The selected point replayed on a frame block."""

    frames: int
    kept: int
    masked_fraction: float
    retained_residual: float          # kept-frame mean systematic residual
    tolerance_fraction: float         # R = r_sys / r_tol
    survey_flag_rate: float           # occupancy indicator: fraction with F > mu_0
    masked_fraction_bootstrap: dict | None
    retained_residual_bootstrap: dict | None
    false_alarm_rate: float           # masked fraction when the block is a verified off era; NaN otherwise
    false_alarm_basis: str
    unmasked_residual: float = math.nan   # mean systematic residual over every frame of the block (keep-everything)


@dataclass(frozen=True)
class SelectionResult:
    channel: int
    freq_id: int
    era_label: str
    anchor_bin: int
    bulk_size: int
    r_tol: float
    floor: Floor
    calibration_frames: int
    evaluation_frames: int
    frames_without_time: int
    status: str                       # 'feasible' | 'no feasible point' | 'no evaluable point' | 'refused'
    refusal: str
    claim_status: str                 # 'operational' | 'screening' | 'diagnostic' (screen refused) | ''
    rho: int | None
    rank_fraction: float
    eta_q16: int | None
    eta: float
    masked_fraction: float            # calibration block, at the selected point
    systematic_residual: float
    tolerance_fraction: float
    cost: float
    plateau: Plateau | None
    evaluation: Replay | None
    unmasked_residual: float = math.nan   # calibration block, keep-everything residual
    points: tuple = ()                    # every evaluated (rho, eta) pair of the calibration surface, as dicts
    diagnostic: dict = field(default_factory=dict)   # the point replayed on the evaluation block and its basis
    anchor_sentinel: str = ""             # the containment sentinel's reasons when the anchor is suspect
    stability: dict = field(default_factory=dict)
    provisional: dict = field(default_factory=dict)
    source_id: str = ""
    policy_sha256: str = ""

    def as_row(self) -> dict:
        row = {
            "channel": self.channel, "freq_id": self.freq_id, "era": self.era_label,
            "anchor_bin": self.anchor_bin, "bulk_size": self.bulk_size, "r_tol": self.r_tol,
            "floor_db": self.floor.db, "floor_evidence": self.floor.evidence, "floor_population": self.floor.population,
            "calibration_frames": self.calibration_frames, "evaluation_frames": self.evaluation_frames,
            "frames_without_time": self.frames_without_time,
            "status": self.status, "refusal": self.refusal, "claim_status": self.claim_status,
            "rho": self.rho, "q_rho": self.rank_fraction, "eta_q16": self.eta_q16, "eta": self.eta,
            "masked_fraction_calibration": self.masked_fraction, "r_sys_calibration": self.systematic_residual,
            "R_calibration": self.tolerance_fraction, "cost": self.cost,
            "plateau_members": self.plateau.members if self.plateau else None,
            "plateau_eta_low": self.plateau.eta_low if self.plateau else math.nan,
            "plateau_eta_high": self.plateau.eta_high if self.plateau else math.nan,
        }
        ev = self.evaluation
        mf = (ev.masked_fraction_bootstrap or {}) if ev else {}
        rr = (ev.retained_residual_bootstrap or {}) if ev else {}
        d = self.diagnostic
        row.update({
            "diagnostic_basis": d.get("basis", ""), "diagnostic_rho": d.get("rho"), "diagnostic_eta_q16": d.get("eta_q16"),
            "diagnostic_eta": d.get("eta", math.nan), "diagnostic_masked_fraction": d.get("masked_fraction", math.nan),
            "diagnostic_r_sys": d.get("r_sys", math.nan), "diagnostic_R": d.get("R", math.nan), "diagnostic_cost": d.get("cost", math.nan),
            "anchor_sentinel": self.anchor_sentinel,
            "stability_status": self.stability.get("status", ""), "stability_reason": self.stability.get("reason", ""),
            "stability_points_checked": self.stability.get("points_checked"), "stability_points_skipped": self.stability.get("points_skipped"),
            "chain_gain": self.provisional.get("chain_gain", math.nan), "residual_convention": self.provisional.get("residual_convention", ""),
        })
        row.update({
            "r_sys_unmasked_calibration": self.unmasked_residual,
            "masked_fraction_evaluation": ev.masked_fraction if ev else math.nan,
            "masked_fraction_evaluation_q16": mf.get("q0.16", math.nan), "masked_fraction_evaluation_q84": mf.get("q0.84", math.nan),
            "r_sys_evaluation": ev.retained_residual if ev else math.nan,
            "r_sys_evaluation_q16": rr.get("q0.16", math.nan), "r_sys_evaluation_q84": rr.get("q0.84", math.nan),
            "bootstrap_blocks_evaluation": mf.get("blocks", 0),
            "r_sys_unmasked_evaluation": ev.unmasked_residual if ev else math.nan,
            "kept_evaluation": ev.kept if ev else 0,
            "R_evaluation": ev.tolerance_fraction if ev else math.nan,
            "survey_flag_rate_evaluation": ev.survey_flag_rate if ev else math.nan,
            "false_alarm_rate": ev.false_alarm_rate if ev else math.nan,
            "false_alarm_basis": ev.false_alarm_basis if ev else "",
        })
        return row


def systematic_residuals(product: Product, rows: np.ndarray, floor: Floor, gain: float = 1.0) -> np.ndarray:
    """Floor-bounded shelf residual per frame row, times the chain gain.

    A frame with a shelf estimate carries ``max(10^(shelf/10), floor)``; a
    frame without one carries the floor. The floor is the level the mask can
    be held to, so no frame's residual falls below it (a flagged frame whose
    excess is not resolved above the floor is booked at the floor, not below
    an unflagged one). ``gain`` is ``G = sum_k phi_k n_coh,k`` from
    :mod:`.chain` (1.0 gives the frame-stage residual); with it the
    kept-frame mean is ``r_proxy``.
    """
    shelf = product.shelf_db[rows]
    finite = np.isfinite(shelf)
    out = np.full(rows.shape, floor.linear, dtype=float)
    out[finite] = np.fmax(10.0 ** (shelf[finite] / 10.0), floor.linear)     # fmax: an undefined floor does not bound
    if not np.isfinite(out).all():
        raise ValueError("systematic residuals need a finite floor for frames without a shelf estimate")
    if not (math.isfinite(gain) and gain > 0.0):
        raise ValueError("the chain gain must be a positive finite number")
    return out * float(gain)


def _evidence(state: str, method: str, source: str, artifact_sha256: str | None = None, detail: str = "") -> CalibrationEvidence:
    return CalibrationEvidence(state=state, method=method, source=source, detail=detail,
                               artifact_sha256=artifact_sha256 if state in ("measured", "bounded") else None)


def kept_at(required_q16: np.ndarray, eta_q16: int) -> np.ndarray:
    """A frame is kept when the selected multiplier is at least its requirement."""
    req = np.asarray(required_q16)
    return (req <= int(eta_q16)) & (req != ALWAYS_MASKED_Q16)


def _plateau(points, selected) -> Plateau | None:
    if selected is None:
        return None
    feasible = [p for p in points if p.feasible]
    if not feasible:
        return None
    c_min = min(p.cost for p in feasible)
    near = [p for p in feasible if p.cost <= PLATEAU_RATIO * c_min]
    at_rho = [p for p in near if p.rho == selected.rho]
    return Plateau(members=len(at_rho),
                   eta_low=min(p.eta for p in at_rho) if at_rho else math.nan,
                   eta_high=max(p.eta for p in at_rho) if at_rho else math.nan,
                   rho_values=tuple(sorted({p.rho for p in near})))


def select_operating_point(product: Product, calibration: np.ndarray, evaluation: np.ndarray, *,
                           anchor_bin: int, bulk_mask: np.ndarray, r_tol: float, floor: Floor, era_label: str,
                           gain: float = 1.0, latest_era: bool = True, off_era: bool = False,
                           correlation: CalibrationEvidence | None = None,
                           transfer: CalibrationEvidence | None = None,
                           min_half_retained: int = PROVISIONAL_MIN_HALF_RETAINED,
                           max_cost_ratio: float = PROVISIONAL_MAX_COST_RATIO,
                           max_systematic_ratio: float = PROVISIONAL_MAX_SYSTEMATIC_RATIO,
                           minimum_observed_months: int | None = None, minimum_span_days: float | None = None,
                           bootstrap_replicates: int = blocks.DEFAULT_REPLICATES,
                           bootstrap_seed: int = blocks.DEFAULT_SEED) -> SelectionResult:
    """Select on the calibration block, replay on the evaluation block."""
    cal = np.asarray(calibration, dtype=bool) & product.selected
    eva = np.asarray(evaluation, dtype=bool) & product.selected
    timed = np.isfinite(product.frame_time)
    without_time = int(((cal | eva) & ~timed).sum())
    cal &= timed
    eva &= timed
    product_sha = sha256_of(product.path)
    provisional = {"stability.minimum_half_retained_frames": min_half_retained,
                   "stability.maximum_cost_ratio": max_cost_ratio,
                   "stability.maximum_systematic_residual_ratio": max_systematic_ratio,
                   "residual_convention": "floor-bounded shelf linear x chain gain, variance 0", "chain_gain": float(gain)}
    base = dict(channel=product.geometry.physical_channel, freq_id=product.geometry.freq_id, era_label=era_label,
                anchor_bin=int(anchor_bin), bulk_size=int(np.asarray(bulk_mask, dtype=bool).sum()), r_tol=float(r_tol),
                floor=floor, calibration_frames=int(cal.sum()), evaluation_frames=int(eva.sum()),
                frames_without_time=without_time, provisional=provisional)
    empty = dict(claim_status="", rho=None, rank_fraction=math.nan, eta_q16=None, eta=math.nan,
                 masked_fraction=math.nan, systematic_residual=math.nan, tolerance_fraction=math.nan,
                 cost=math.nan, plateau=None, evaluation=None)
    if not cal.any():
        return SelectionResult(status="refused", refusal="calibration block has no usable frames", **base, **empty)
    if not math.isfinite(floor.linear) and not np.isfinite(product.shelf_db[cal]).all():
        return SelectionResult(status="refused", refusal="no floor for frames without a shelf estimate", **base, **empty)
    try:
        bundle = build_residual_score_bundle(product.path, cal, anchor_bin=int(anchor_bin),
                                             designated_half_width=DESIGNATED_HALF_WIDTH, bulk_mask=np.asarray(bulk_mask, dtype=bool))
    except ResidualScoreRefused as exc:
        return SelectionResult(status="refused", refusal=f"bundle: {exc}", **base, **empty)
    rows = bundle.source_row_index
    residuals = systematic_residuals(product, rows, floor, gain)
    base["unmasked_residual"] = float(residuals.mean()) if residuals.size else math.nan
    score = _evidence("measured", "exact fine-power terms", product.path.name, product_sha,
                      "Q16 requirements from fine_power_u64")
    correlation = correlation or _evidence("conditional", "correlation time pending", "chapter 8 tau_c estimator not yet run on v5")
    transfer = transfer or _evidence("conditional", "unity transfer closure", "g_var = g_sys = 1 (chapter 9)")
    try:
        family = bundle.prepare_threshold_family(
            residuals, variance_residuals=np.zeros(bundle.frame_count), era_label=era_label, latest_era=latest_era,
            additive_residuals=True, score=score, correlation=correlation, transfer=transfer,
            max_cost_ratio=max_cost_ratio, max_systematic_residual_ratio=max_systematic_ratio,
            minimum_half_retained_frames=min_half_retained,
            minimum_observed_months=minimum_observed_months, minimum_span_days=minimum_span_days)
    except (ValueError, TypeError) as exc:
        return SelectionResult(status="refused", refusal=f"preparation: {exc}", **base, **empty)
    st = family.stability
    stability = {"status": st.status, "reason": st.reason, "points_checked": st.points_checked,
                 "points_skipped": st.points_skipped, "maximum_cost_ratio": st.maximum_cost_ratio,
                 "maximum_systematic_residual_ratio": st.maximum_systematic_residual_ratio}
    refusal = ""
    try:
        selection = select_prepared_threshold(family, float(r_tol), allow_screening=True)
        claim, opt = selection.claim_status, selection.optimization
    except PreparationRefused as exc:
        refusal = str(exc)
        claim, opt = "diagnostic", optimize_threshold(family.histograms_by_rho, float(r_tol))
    points = tuple(_point_row(pt) for pt in opt.points)
    provisional = dict(base.get("provisional", {}))
    if opt.selected is None:
        # no feasible point: the least-residual point of the surface is replayed on the evaluation block as a
        # declared diagnostic (an off era's false-alarm rate needs a point), never as a selection
        status = {"no_feasible_threshold": "no feasible point", "no_evaluable_threshold": "no evaluable point"}.get(opt.status, opt.status)
        evaluable = [pt for pt in opt.points if math.isfinite(pt.systematic_residual)]
        diag_point = min(evaluable, key=lambda pt: pt.systematic_residual) if evaluable else None
        diagnostic, replay = {}, None
        if diag_point is not None:
            diagnostic = {"basis": "least residual on the calibration surface (no feasible point)", **_point_row(diag_point)}
            diagnostic["R"] = diagnostic.pop("tolerance_fraction")
            if eva.any():
                replay = replay_on_block(product, eva, anchor_bin=int(anchor_bin), bulk_mask=bulk_mask, rho=diag_point.rho,
                                         eta_q16=diag_point.multiplier_q16, r_tol=float(r_tol), floor=floor, gain=gain,
                                         off_era=off_era, replicates=bootstrap_replicates, seed=bootstrap_seed)
        return SelectionResult(status=status, refusal=refusal, stability=stability, source_id=bundle.source_id,
                               policy_sha256=family.policy_sha256, points=points, diagnostic=diagnostic,
                               **{**base, "provisional": provisional}, **{**empty, "claim_status": claim, "evaluation": replay})
    sel = opt.selected
    replay = None
    if eva.any():
        replay = replay_on_block(product, eva, anchor_bin=int(anchor_bin), bulk_mask=bulk_mask, rho=sel.rho,
                                 eta_q16=sel.multiplier_q16, r_tol=float(r_tol), floor=floor, gain=gain, off_era=off_era,
                                 replicates=bootstrap_replicates, seed=bootstrap_seed)
    diagnostic = {"basis": "selected point", **_point_row(sel)}
    diagnostic["R"] = diagnostic.pop("tolerance_fraction")
    return SelectionResult(
        status="feasible", refusal=refusal, claim_status=claim, rho=int(sel.rho),
        rank_fraction=float(sel.rank_fraction), eta_q16=int(sel.multiplier_q16), eta=float(sel.eta),
        masked_fraction=float(sel.masked_fraction), systematic_residual=float(sel.systematic_residual),
        tolerance_fraction=float(sel.tolerance_fraction), cost=float(sel.cost),
        plateau=_plateau(opt.points, sel), evaluation=replay, stability=stability, points=points, diagnostic=diagnostic,
        source_id=bundle.source_id, policy_sha256=family.policy_sha256, **{**base, "provisional": provisional})


POINT_COLUMNS = ("rho", "rank_fraction", "eta_q16", "eta", "frames", "kept", "masked_fraction", "r_sys",
                 "tolerance_fraction", "cost", "feasible")

# where a real operating point lives: the fraction of each era half a candidate must keep for its
# early/late ratios to describe the drift a selected point would see, rather than a sparse tail
DRIFT_KEPT_FRACTIONS = (0.0, 0.01, 0.05, 0.2)


def drift_diagnostic(bundle, residuals: np.ndarray, frame_time: np.ndarray, *,
                     min_half: int = PROVISIONAL_MIN_HALF_RETAINED,
                     kept_fractions: Sequence[float] = DRIFT_KEPT_FRACTIONS) -> dict:
    """Why the within-era drift screen refused, measured on the candidates a selector could choose.

    :func:`rfisher.preparation.assess_histogram_stability` refuses the whole
    family at the first candidate whose pooled kept count reaches the
    thirty-frame floor while one calendar half falls below ``min_half``. Every
    eta sweep crosses that band, so the refusal names a point keeping a few
    tenths of a percent of the block, which no selector would choose, and its
    message says "insufficient support" whatever the data does.

    This records both facts: the candidate the screen refused on (with the
    frames it keeps in each half), and the worst early/late cost and
    systematic-residual ratios over the candidates that keep at least a stated
    fraction of *each* half. The second is the drift a selected point would
    actually see; where it exceeds the declared limits the refusal is the
    right verdict for the wrong stated reason.
    """
    from rfisher.preparation import MIN_RETAINED_FRAMES, _ratio, _surface
    from rfisher.thresholds import build_q16_residual_score_histogram

    times = np.asarray(frame_time, dtype=float)
    if times.size == 0 or not np.isfinite(times).any():
        return {"drift_status": "no timed frames"}
    mid = 0.5 * (np.nanmin(times) + np.nanmax(times))
    early_mask, late_mask = times <= mid, times > mid
    n_early, n_late = int(early_mask.sum()), int(late_mask.sum())
    if not (n_early and n_late):
        return {"drift_status": "calendar split leaves one half empty"}
    requirements = bundle.requirements_by_rho()
    bulk_size = max(requirements)
    refused = None
    rows: list[tuple[float, float, float]] = []
    for rho in sorted(requirements):
        values = tuple(requirements[rho])
        grid = tuple(sorted({int(v) for v in values if int(v) != ALWAYS_MASKED_Q16}))
        if not grid:
            continue
        early = build_q16_residual_score_histogram(
            tuple(v for v, k in zip(values, early_mask) if k), residuals[early_mask], grid, bulk_size=bulk_size)
        late = build_q16_residual_score_histogram(
            tuple(v for v, k in zip(values, late_mask) if k), residuals[late_mask], grid, bulk_size=bulk_size)
        e_surface, l_surface = _surface(early), _surface(late)
        for index, eta in enumerate(early.candidate_eta):
            e, l = e_surface[index], l_surface[index]
            e_kept = 0 if e is None else e[0]
            l_kept = 0 if l is None else l[0]
            if e_kept + l_kept < MIN_RETAINED_FRAMES:
                continue
            if e is None or l is None or e_kept < min_half or l_kept < min_half:
                if refused is None:
                    refused = {"drift_refused_rho": int(rho), "drift_refused_eta": float(eta),
                               "drift_refused_early_kept": int(e_kept), "drift_refused_late_kept": int(l_kept),
                               "drift_refused_kept_fraction": (e_kept + l_kept) / (n_early + n_late)}
                continue
            rows.append((min(e_kept / n_early, l_kept / n_late), _ratio(e[4], l[4]), _ratio(e[2], l[2])))
    out = {"drift_status": "measured" if rows else "no evaluable candidate",
           "drift_early_frames": n_early, "drift_late_frames": n_late, **(refused or {})}
    if rows:
        arr = np.asarray(rows, dtype=float)
        for fraction in kept_fractions:
            keep = arr[arr[:, 0] >= float(fraction)]
            tag = f"{float(fraction):g}".replace(".", "p")
            if keep.size:
                out[f"drift_candidates_at_{tag}"] = int(keep.shape[0])
                out[f"drift_max_cost_ratio_at_{tag}"] = float(keep[:, 1].max())
                out[f"drift_max_systematic_ratio_at_{tag}"] = float(keep[:, 2].max())
    return out


def _point_row(pt) -> dict:
    return {"rho": int(pt.rho), "rank_fraction": float(pt.rank_fraction), "eta_q16": int(pt.multiplier_q16), "eta": float(pt.eta),
            "frames": int(pt.frame_count), "kept": int(pt.kept_frames), "masked_fraction": float(pt.masked_fraction),
            "r_sys": float(pt.systematic_residual), "tolerance_fraction": float(pt.tolerance_fraction),
            "cost": float(pt.cost), "feasible": bool(pt.feasible)}


MAX_POINTS_PER_RHO = 200


def thin_points(points: Sequence[dict], selected: tuple | None = None, *, max_per_rho: int = MAX_POINTS_PER_RHO) -> list[dict]:
    """At most ``max_per_rho`` points per rank: evenly spaced in eta, always keeping the first, the last,
    the least-residual point of the rank and the selected point. The full surface (about 1.3 million pairs
    per channel) stays in memory for the summary; only this is written."""
    by_rho: dict[int, list[dict]] = {}
    for row in points:
        by_rho.setdefault(int(row["rho"]), []).append(row)
    out: list[dict] = []
    for rho in sorted(by_rho):
        rows = sorted(by_rho[rho], key=lambda r: r["eta_q16"])
        keep = set()
        n = len(rows)
        if n <= max_per_rho:
            keep = set(range(n))
        else:
            keep.update(int(round(i * (n - 1) / (max_per_rho - 1))) for i in range(max_per_rho))
        finite = [i for i, r in enumerate(rows) if math.isfinite(r["r_sys"])]
        if finite:
            keep.add(min(finite, key=lambda i: rows[i]["r_sys"]))
        if selected is not None:
            keep.update(i for i, r in enumerate(rows) if (r["rho"], r["eta_q16"]) == tuple(selected))
        out.extend(rows[i] for i in sorted(keep))
    return out


def write_operating_points(result: SelectionResult, path: Path | str, *, max_per_rho: int = MAX_POINTS_PER_RHO) -> Path:
    """The calibration surface, thinned per rank (:func:`thin_points`), with the selected point marked."""
    import csv
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    selected = (result.rho, result.eta_q16) if result.rho is not None else None
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["channel", *POINT_COLUMNS, "selected"], lineterminator="\n")
        writer.writeheader()
        for row in thin_points(result.points, selected, max_per_rho=max_per_rho):
            writer.writerow({"channel": result.channel, **{k: (repr(v) if isinstance(v, float) else v) for k, v in row.items()},
                             "selected": (row["rho"], row["eta_q16"]) == selected})
    return path


def surface_summary(result: SelectionResult) -> dict:
    """The least residual and the least cost on the evaluated surface, and how far the residual is from tolerance."""
    pts = [p for p in result.points if math.isfinite(p["r_sys"])]
    if not pts:
        return {"surface_points": len(result.points), "min_r_sys": math.nan, "min_r_sys_rho": None, "min_r_sys_eta": math.nan,
                "min_r_sys_masked_fraction": math.nan, "min_R": math.nan, "feasible_points": 0}
    best = min(pts, key=lambda p: p["r_sys"])
    return {"surface_points": len(result.points), "min_r_sys": best["r_sys"], "min_r_sys_rho": best["rho"], "min_r_sys_eta": best["eta"],
            "min_r_sys_masked_fraction": best["masked_fraction"], "min_R": best["r_sys"] / result.r_tol if result.r_tol else math.nan,
            "feasible_points": sum(1 for p in pts if p["feasible"])}


def replay_on_block(product: Product, block: np.ndarray, *, anchor_bin: int, bulk_mask, rho: int, eta_q16: int,
                    r_tol: float, floor: Floor, off_era: bool, replicates: int, seed: int, gain: float = 1.0) -> Replay:
    """Apply a selected ``(rho, eta_q16)`` to another block of the same channel."""
    bundle = build_residual_score_bundle(product.path, np.asarray(block, dtype=bool), anchor_bin=int(anchor_bin),
                                         designated_half_width=DESIGNATED_HALF_WIDTH, bulk_mask=np.asarray(bulk_mask, dtype=bool))
    rows = bundle.source_row_index
    if int(rho) > bundle.supported_rho_count:
        raise ValueError(f"rank {rho} is not supported on the evaluation block (bulk {bundle.supported_rho_count})")
    required = np.asarray(bundle.requirements_by_rho()[int(rho)], dtype=object)
    kept = kept_at(required, int(eta_q16))
    residual = systematic_residuals(product, rows, floor, gain)
    n = rows.size
    f = 1.0 - kept.sum() / n
    r_sys = float(residual[kept].mean()) if kept.any() else math.nan
    flag = product.rejected[rows]
    units = product.frame_unit_index[rows]
    sel = np.ones(n, dtype=bool)
    mf_bs = rr_bs = None
    if np.unique(units).size >= blocks.MIN_BLOCKS_PER_HALF:
        mf_bs = blocks.block_bootstrap(units, sel, lambda w: blocks.weighted_fraction(w, ~kept),
                                       replicates=replicates, seed=seed).as_dict()

        def kept_mean(w):
            ww = w * kept
            return float((ww * residual).sum() / ww.sum()) if ww.sum() > 0 else math.nan
        rr_bs = blocks.block_bootstrap(units, sel, kept_mean, replicates=replicates, seed=seed).as_dict()
    return Replay(frames=int(n), kept=int(kept.sum()), masked_fraction=float(f), retained_residual=r_sys,
                  tolerance_fraction=r_sys / r_tol if math.isfinite(r_sys) else math.nan,
                  survey_flag_rate=float(flag.mean()), masked_fraction_bootstrap=mf_bs, retained_residual_bootstrap=rr_bs,
                  false_alarm_rate=float(f) if off_era else math.nan,
                  false_alarm_basis="verified off era: every frame is null" if off_era else "not measurable: no verified off state in this block",
                  unmasked_residual=float(residual.mean()) if n else math.nan)


def eta_display(eta_q16: int) -> float:
    """Floating display value of an exact Q16 multiplier (display only)."""
    return int(eta_q16) / Q16_SCALE


def write_selection_rows(results: Sequence[SelectionResult], path: Path | str) -> Path:
    import csv
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [r.as_row() for r in results]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]) if rows else [], lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: ("" if (isinstance(v, float) and not math.isfinite(v)) or v is None
                                 else repr(v) if isinstance(v, float) else v) for k, v in row.items()})
    return path
