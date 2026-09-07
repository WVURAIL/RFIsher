"""Null calibration of one channel's current era: centres, widths, tails,
exchangeability and the floor (chapter 8 tab:calibration:nulls; chapter 5
sec:estimator:statistics).

Two statistics, two nulls.

- Coarse: ``Q = F / mu_0`` per frame. Under the i.i.d. model
  ``F ~ F(524288, 1048576)``, mean 1.000002, standard deviation 0.239%. The
  null population is, in order of strength (ch08 §253-263): a verified
  transmitter-off era; an independently identified quiet subset; a
  reference-bin surrogate; a model-only null; or unavailable. Without an off
  era this module reads the null off the bulk of the era's mixture and says
  so: centre = median of the bulk, scale = left-side deviation about that
  median, the mixture assumption declared beside the number.
- Fine: ``T[f]`` on the bulk bins ``B`` (independent, non-designated, guard
  and census excluded). Every frame's bulk bins are null by construction, so
  the fine null is read from all era frames. Under the i.i.d. model
  ``T ~ F(4096, 8192)``, mean 1.00024, standard deviation 2.71%.

Width factors are the measured width over the i.i.d. width, in two forms: raw
(standard deviation) and robust core (left-side scale about the median from
three quantile probes, the median of the three). Tail fraction: values beyond
three core widths above the centre. The i.i.d. widths are evaluated from the
F distributions, not typed in.

Probe convention. The register value ``floor.null_scale_probes`` is
``((32.0, 1.0), (5.0, 1.96), (0.3, 2.9677))`` and
:func:`rfisher.residual.null_scale` applies the percentiles to the *kept*
frames about ``mu_0``: the kept sample is the lower half of a symmetric null,
so its 32nd percentile is the null's 16th, one sigma below the centre. That
is the convention this module follows for the sigma-implied floor
(:func:`kept_half_null`: frames with ``Q <= 1`` on the block, scale about
``mu_0``), and it recovers an ideal null's width to 1% (simulated). The bulk
description of the whole era (:func:`describe_null`, centre = median,
left-side scale about the median) needs the full-null percentiles the same
deviates sit at (``15.87 / 2.5 / 0.15``, ``CORE_PROBES``); applying the
register's percentiles to a full null instead would return 0.84 of the width.
Both descriptions are reported; the floor uses the kept half, because on a
channel whose transmitter is present in most frames the bulk's median lies
above ``mu_0`` and its left-side scale is the detections' lower tail, not the
receiver's null (channel 33: bulk width factor 25, kept-half width factor
near the i.i.d. value).

Off population. A recorded off epoch is a null population only when its
coarse statistic looks like one: centre within ``OFF_CENTRE_TOLERANCE`` of
``mu_0`` and a robust-core width factor at most ``OFF_WIDTH_LIMIT``
(:func:`null_like`). A post-sign-off epoch that still carries a carrier
(channel 20: centre 1.12, width factor 21) fails the check, its floor is then
``stated`` from the kept half of the block, and the current era is not an
off era for screening.

Exchangeability (ch08 §275-283): on quiet frames a null bin tested against
the rank ``rho`` of the bulk exceeds it at the combinatorial rate
``(|B| + 1 - rho) / (|B| + 1)``. The bin under test must lie outside the
bulk: within one frame exactly ``|B| - rho`` of the bulk's own bins exceed
the rank of the others whatever their distribution, so a leave-one-out
test says nothing. The bins tested here are the designated window ``D`` of
the measured anchor, which on coarse-quiet frames should carry no pilot and
is exactly the set the decision ``max_D T > eta T_(rho)`` reads: the per-bin
rate checks that quiet frames are quiet and that a designated bin is
exchangeable with the bulk, and the rate of the maximum over ``D`` is the
fine rule's own exceedance rate at ``eta = 1`` on those frames.

Floor (ch08 §206-239): where the channel has a verified off era, the 90th
percentile of the finite shelf estimates over that era's frames, ``measured``
when at least 30 frames support it (register ``floor.minimum_null_frames``);
otherwise the sigma-implied substitute ``10 log10(sigma_core) + offset``,
labelled ``stated``. Never the minimum detected shelf.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np
from scipy import stats

from . import blocks
from .products import Product, fine_power_ratio

COARSE_DOF = (524288, 1048576)
FINE_DOF = (4096, 8192)
# one-sided lower percentiles and the Gaussian deviates they sit at
CORE_PROBES = ((15.87, 1.0), (2.5, 1.96), (0.15, 2.9677))
# the register's pairs as rfisher.residual.null_scale applies them (one-sided at p)
AS_CODED_PROBES = ((32.0, 1.0), (5.0, 1.96), (0.3, 2.9677))
TAIL_WIDTHS = 3.0
FLOOR_PERCENTILE = 90.0
FLOOR_MIN_FRAMES = 30
MIN_NULL_FRAMES = 30
# an off population is null-like when its coarse centre is within this of mu_0 (2% = 0.086 dB, about eight
# i.i.d. widths) and its robust-core width factor is at most this; provisional policy values, recorded per row
OFF_CENTRE_TOLERANCE = 0.02
OFF_WIDTH_LIMIT = 5.0


def iid_width(dof: tuple[int, int]) -> tuple[float, float]:
    """(mean, standard deviation) of the F distribution with these degrees of freedom."""
    mean, var = stats.f.stats(dof[0], dof[1], moments="mv")
    return float(mean), float(np.sqrt(var))


def core_scale(values, centre: float, probes=CORE_PROBES) -> tuple[float, float]:
    """Left-side robust scale about ``centre``: median over probes of (centre - q_p) / z; and the probe spread."""
    x = np.asarray(values, dtype=float)
    x = x[np.isfinite(x)]
    if x.size < MIN_NULL_FRAMES:
        return math.nan, math.nan
    ests = [(centre - float(np.percentile(x, p))) / z for p, z in probes]
    ests = [e for e in ests if e > 0.0]
    if not ests:
        return math.nan, math.nan
    return float(np.median(ests)), float(max(ests) / min(ests))


@dataclass(frozen=True)
class NullWidths:
    """One statistic's null description."""

    frames: int                    # frames (coarse) or frame x bulk-bin samples (fine)
    centre: float                  # median
    centre_db: float               # 10 log10(centre)
    iid_mean: float
    iid_sigma: float
    raw_sigma: float
    raw_width_factor: float        # raw_sigma / iid_sigma
    core_sigma: float
    core_width_factor: float
    core_spread: float             # probe spread under the corrected probes
    as_coded_sigma: float          # rfisher.residual.null_scale convention, for comparison
    as_coded_spread: float
    tail_fraction: float           # fraction beyond centre + 3 core widths
    tail_fraction_iid: float       # the same for the i.i.d. model

    def as_dict(self, prefix: str) -> dict:
        return {f"{prefix}_{k}": v for k, v in self.__dict__.items()}


def describe_null(values, dof: tuple[int, int]) -> NullWidths:
    x = np.asarray(values, dtype=float).ravel()
    x = x[np.isfinite(x)]
    mean, sigma = iid_width(dof)
    if x.size < MIN_NULL_FRAMES:
        nan = math.nan
        return NullWidths(int(x.size), nan, nan, mean, sigma, nan, nan, nan, nan, nan, nan, nan, nan, nan)
    centre = float(np.median(x))
    raw = float(np.std(x))
    core, spread = core_scale(x, centre)
    coded, coded_spread = core_scale(x, centre, probes=AS_CODED_PROBES)
    tail = float(np.mean(x > centre + TAIL_WIDTHS * core)) if math.isfinite(core) else math.nan
    median_iid = float(stats.f.ppf(0.5, *dof))
    tail_iid = float(stats.f.sf(median_iid + TAIL_WIDTHS * sigma, *dof))
    return NullWidths(int(x.size), centre, 10.0 * math.log10(centre), mean, sigma, raw, raw / sigma, core, core / sigma,
                      spread, coded, coded_spread, tail, tail_iid)


@dataclass(frozen=True)
class KeptHalfNull:
    """The register's kept-frame null scale: frames with ``Q <= 1``, left-side scale about ``mu_0``."""

    frames: int
    core_sigma: float
    width_factor: float          # core_sigma / iid_sigma
    spread: float                # largest over smallest probe estimate

    def as_dict(self, prefix: str = "kept") -> dict:
        return {f"{prefix}_{k}": v for k, v in self.__dict__.items()}


def kept_half_null(q, dof: tuple[int, int] = COARSE_DOF, probes=AS_CODED_PROBES) -> KeptHalfNull:
    """Scale of the null from the kept half about ``mu_0`` (``Q = F / mu_0 <= 1``), the register's convention."""
    x = np.asarray(q, dtype=float).ravel()
    x = x[np.isfinite(x) & (x <= 1.0)]
    _, sigma = iid_width(dof)
    if x.size < MIN_NULL_FRAMES:
        return KeptHalfNull(int(x.size), math.nan, math.nan, math.nan)
    ests = [(1.0 - float(np.percentile(x, p))) / z for p, z in probes]
    ests = [e for e in ests if e > 0.0]
    if not ests:
        return KeptHalfNull(int(x.size), math.nan, math.nan, math.nan)
    core = float(np.median(ests))
    return KeptHalfNull(int(x.size), core, core / sigma, float(max(ests) / min(ests)))


def null_like(coarse: NullWidths, *, centre_tolerance: float = OFF_CENTRE_TOLERANCE,
              width_limit: float = OFF_WIDTH_LIMIT) -> tuple[bool, str]:
    """Whether a coarse population reads as a null: centre near mu_0 and a modest core width."""
    if not (math.isfinite(coarse.centre) and math.isfinite(coarse.core_width_factor)):
        return False, "too few frames to describe"
    reasons = []
    if abs(coarse.centre - 1.0) > centre_tolerance:
        reasons.append(f"centre {coarse.centre:.4f} is more than {centre_tolerance:g} from mu_0")
    if coarse.core_width_factor > width_limit:
        reasons.append(f"core width factor {coarse.core_width_factor:.1f} exceeds {width_limit:g}")
    if reasons:
        return False, "; ".join(reasons)
    return True, f"centre {coarse.centre:.4f}, core width factor {coarse.core_width_factor:.2f}"


def off_population_check(product: Product, off_mask) -> tuple[bool, NullWidths | None, str]:
    """Describe a recorded off population and say whether it is null-like (None when there is no population)."""
    if off_mask is None:
        return False, None, "no recorded off epoch"
    frames = np.asarray(off_mask, dtype=bool) & product.selected
    if frames.sum() < MIN_NULL_FRAMES:
        return False, None, f"off population has {int(frames.sum())} frames < {MIN_NULL_FRAMES}"
    widths = describe_null(product.statistic[frames], COARSE_DOF)
    ok, reason = null_like(widths)
    return ok, widths, reason


@dataclass(frozen=True)
class Exchangeability:
    rho: int
    bulk_size: int
    frames: int
    test_bins: tuple[int, ...]
    trials: int
    measured_rate: float               # per-bin exceedance of the designated bins against T_(rho) of the bulk
    predicted_rate: float              # (|B| + 1 - rho) / (|B| + 1)
    max_over_test_rate: float          # fraction of frames with max_D T > T_(rho): the fine rule at eta = 1

    def as_dict(self) -> dict:
        return {"exch_rho": self.rho, "exch_bulk": self.bulk_size, "exch_frames": self.frames,
                "exch_test_bins": ";".join(str(b) for b in self.test_bins), "exch_trials": self.trials,
                "exch_measured": self.measured_rate, "exch_predicted": self.predicted_rate,
                "exch_max_over_designated": self.max_over_test_rate}


def exchangeability_rate(fine_t: np.ndarray, bulk_mask: np.ndarray, rho: int, test_bins) -> Exchangeability:
    """Exceedance rate of bins outside the bulk against the rank ``rho`` of the bulk.

    ``fine_t`` is ``(frames, 256)`` over quiet frames; ``test_bins`` are the
    bins under test (the designated window). A test bin exceeds when ``T`` is
    strictly larger than the ``rho``-th smallest bulk value of its frame (ties
    do not exceed, the conservative direction for a decision ``> eta T_(rho)``).
    """
    t = np.asarray(fine_t, dtype=float)
    bulk = np.flatnonzero(np.asarray(bulk_mask, dtype=bool))
    tests = tuple(int(b) for b in test_bins)
    n = bulk.size
    if t.ndim != 2 or n < 1 or not (1 <= int(rho) <= n) or not tests:
        raise ValueError("exchangeability needs (frames, bins) values, a non-empty bulk, 1 <= rho <= |B| and test bins")
    if set(tests) & set(bulk.tolist()):
        raise ValueError("test bins must lie outside the bulk")
    t_rho = np.sort(t[:, bulk], axis=1)[:, int(rho) - 1]             # (frames,)
    tested = t[:, tests]                                              # (frames, len(tests))
    exceed = tested > t_rho[:, None]
    return Exchangeability(int(rho), int(n), int(t.shape[0]), tests, int(exceed.size),
                           float(exceed.mean()) if exceed.size else math.nan, (n + 1 - int(rho)) / (n + 1),
                           float(exceed.any(axis=1).mean()) if exceed.size else math.nan)


@dataclass(frozen=True)
class FloorEstimate:
    db: float
    evidence: str                  # 'measured' | 'stated' | 'refused'
    population: str
    frames: int
    percentile: float = FLOOR_PERCENTILE
    stated_kept_half_db: float = math.nan   # the sigma-implied value from the kept half about mu_0 (the register's convention)
    stated_bulk_db: float = math.nan        # the same from the bulk's left-side core width, for comparison

    def as_dict(self) -> dict:
        return {"floor_db": self.db, "floor_evidence": self.evidence, "floor_population": self.population,
                "floor_frames": self.frames, "floor_percentile": self.percentile,
                "floor_stated_kept_half_db": self.stated_kept_half_db, "floor_stated_bulk_db": self.stated_bulk_db}


def _sigma_implied_db(sigma: float, offset: float) -> float:
    return 10.0 * math.log10(sigma) + offset if math.isfinite(sigma) and sigma > 0 else math.nan


def floor_estimate(product: Product, off_era: np.ndarray | None, coarse: NullWidths,
                   kept: KeptHalfNull | None = None) -> FloorEstimate:
    """Off-era 90th-percentile shelf where a verified off era exists, else the sigma-implied substitute.

    The substitute is ``10 log10(sigma) + offset`` with ``sigma`` the kept-half
    scale about ``mu_0`` (the register's convention); the bulk's core width
    gives the comparison value ``stated_bulk_db``.
    """
    offset = float(product.view.shelf_offset_db)
    kept_db = _sigma_implied_db(kept.core_sigma, offset) if kept is not None else math.nan
    bulk_db = _sigma_implied_db(coarse.core_sigma, offset)
    stated, basis = (kept_db, f"kept half about mu_0, {kept.frames} frames") if math.isfinite(kept_db) else (bulk_db, "bulk core width")
    if off_era is not None and np.asarray(off_era, dtype=bool).any():
        mask = np.asarray(off_era, dtype=bool) & product.selected
        shelf = product.shelf_db[mask]
        shelf = shelf[np.isfinite(shelf)]
        if shelf.size >= FLOOR_MIN_FRAMES:
            return FloorEstimate(float(np.percentile(shelf, FLOOR_PERCENTILE)), "measured",
                                 f"verified off era: {shelf.size} frames with a shelf estimate of {int(mask.sum())}",
                                 int(shelf.size), stated_kept_half_db=kept_db, stated_bulk_db=bulk_db)
        return FloorEstimate(stated, "stated", f"off era has only {shelf.size} frames with a shelf estimate; sigma-implied substitute ({basis})",
                             int(shelf.size), stated_kept_half_db=kept_db, stated_bulk_db=bulk_db)
    if math.isfinite(stated):
        return FloorEstimate(stated, "stated", f"no verified off era; sigma-implied substitute ({basis})",
                             kept.frames if (kept is not None and math.isfinite(kept_db)) else 0,
                             stated_kept_half_db=kept_db, stated_bulk_db=bulk_db)
    return FloorEstimate(math.nan, "refused", "no off era and no measurable null width", 0)


@dataclass(frozen=True)
class NullCalibration:
    channel: int
    freq_id: int
    era_label: str
    era_frames: int
    null_source: str                     # 'verified transmitter-off era' | 'bulk of the mixture (declared)' | 'recorded off epoch, not null-like ...'
    mixture_declared: bool
    coarse: NullWidths
    fine: NullWidths
    fine_designated_median: float        # median T over the designated window, all era frames (for the plates)
    floor: FloorEstimate
    exchangeability: Exchangeability | None
    bulk_size: int
    quiet_frames: int
    detected_frames: int
    kept: KeptHalfNull | None = None     # the register's kept-half null scale on the block
    off_null_like: bool | None = None    # None: no recorded off population
    off_check: str = ""
    off_coarse: NullWidths | None = None # the off population's own description (when one exists)
    notes: tuple[str, ...] = field(default_factory=tuple)

    def as_row(self) -> dict:
        row = {"channel": self.channel, "freq_id": self.freq_id, "era": self.era_label, "era_frames": self.era_frames,
               "null_source": self.null_source, "mixture_declared": self.mixture_declared, "bulk_size": self.bulk_size,
               "quiet_frames": self.quiet_frames, "detected_frames": self.detected_frames,
               "fine_designated_median": self.fine_designated_median,
               "off_null_like": self.off_null_like, "off_check": self.off_check,
               "off_centre": self.off_coarse.centre if self.off_coarse is not None else math.nan,
               "off_core_width_factor": self.off_coarse.core_width_factor if self.off_coarse is not None else math.nan,
               "off_frames": self.off_coarse.frames if self.off_coarse is not None else 0,
               "off_centre_tolerance": OFF_CENTRE_TOLERANCE, "off_width_limit": OFF_WIDTH_LIMIT}
        row.update((self.kept or KeptHalfNull(0, math.nan, math.nan, math.nan)).as_dict("kept"))
        row.update(self.coarse.as_dict("coarse"))
        row.update(self.fine.as_dict("fine"))
        row.update(self.floor.as_dict())
        if self.exchangeability is not None:
            row.update(self.exchangeability.as_dict())
        row["notes"] = "; ".join(self.notes)
        return row


def calibrate_null(product: Product, era: np.ndarray, *, anchor_bin: int, bulk_mask: np.ndarray, era_label: str,
                   off_era: np.ndarray | None = None, rho: int | None = None, quiet_block: np.ndarray | None = None,
                   fine_t: np.ndarray | None = None) -> NullCalibration:
    """Null calibration on the era's frames.

    ``off_era`` marks frames of a verified transmitter-off era (the coarse null
    population and the floor come from it); without it the coarse null is
    read from the bulk of the era's mixture. ``rho`` and ``quiet_block`` (the
    evaluation block's frames, restricted here to coarse-quiet ones) drive
    the exchangeability check. ``fine_t`` may be supplied as the (N, 256)
    fine statistic of every frame to avoid reading the terms twice.
    """
    era = np.asarray(era, dtype=bool) & product.selected
    notes = []
    q = product.statistic
    kept = kept_half_null(q[era])
    off_ok, off_widths, off_reason = off_population_check(product, off_era)
    off_null = None if off_widths is None else off_ok
    if off_ok:
        null_frames = np.asarray(off_era, dtype=bool) & product.selected
        source, mixture = "verified transmitter-off era", False
    else:
        null_frames = era
        source, mixture = "bulk of the mixture (declared)", True
        if off_widths is not None:
            source = "recorded off epoch, not null-like; bulk of the mixture (declared)"
            notes.append(f"recorded off population is not null-like ({off_reason}); floor stated, not measured")
            off_era = None
        notes.append("coarse null read from the bulk of the era's mixture: centre = median, scale = left side")
    coarse = describe_null(q[null_frames], COARSE_DOF)
    if fine_t is None:
        fine_t = fine_power_ratio(product.fine_terms_all())
    bulk = np.asarray(bulk_mask, dtype=bool)
    fine = describe_null(fine_t[era][:, bulk], FINE_DOF)
    designated = [(int(anchor_bin) + k) % fine_t.shape[1] for k in range(-2, 3)]
    fine_designated_median = float(np.median(fine_t[era][:, designated])) if era.any() else math.nan
    floor = floor_estimate(product, off_era, coarse, kept)
    exch = None
    quiet = era & ~product.rejected if quiet_block is None else np.asarray(quiet_block, dtype=bool) & product.selected & ~product.rejected
    if rho is not None and quiet.sum() >= MIN_NULL_FRAMES:
        exch = exchangeability_rate(fine_t[quiet], bulk, int(rho), designated)
    elif rho is not None:
        notes.append(f"exchangeability skipped: {int(quiet.sum())} quiet frames < {MIN_NULL_FRAMES}")
    return NullCalibration(
        channel=product.geometry.physical_channel, freq_id=product.geometry.freq_id, era_label=era_label,
        era_frames=int(era.sum()), null_source=source, mixture_declared=mixture, coarse=coarse, fine=fine,
        fine_designated_median=fine_designated_median, floor=floor, exchangeability=exch, bulk_size=int(bulk.sum()),
        quiet_frames=int((era & ~product.rejected).sum()), detected_frames=int((era & product.rejected).sum()),
        kept=kept, off_null_like=off_null, off_check=off_reason if off_widths is not None else "", off_coarse=off_widths,
        notes=tuple(notes))


def write_null_rows(results: Sequence[NullCalibration], path) -> None:
    import csv
    from pathlib import Path
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [r.as_row() for r in results]
    keys = sorted({k for r in rows for k in r}, key=lambda k: list(rows[0]).index(k) if k in rows[0] else 10_000)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=keys, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: ("" if (isinstance(v, float) and not math.isfinite(v)) or v is None
                                 else repr(v) if isinstance(v, float) else v) for k, v in row.items()})


__all__ = ["NullWidths", "Exchangeability", "FloorEstimate", "NullCalibration", "describe_null", "core_scale",
           "exchangeability_rate", "floor_estimate", "calibrate_null", "write_null_rows", "iid_width",
           "CORE_PROBES", "AS_CODED_PROBES", "COARSE_DOF", "FINE_DOF"]

# keep the import used for callers that resample the null statistics by acquisition
_ = blocks
