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
``((32.0, 1.0), (5.0, 1.96), (0.3, 2.9677))``: two-sided tail fractions
(32% outside +-1 sigma, 5% outside +-1.96, 0.3% outside +-2.9677) paired with
their Gaussian deviates. :func:`rfisher.residual.null_scale` and ppcal's
``null_scale_about`` apply those fractions as one-sided percentiles
(``np.percentile(x, 32)``), which places the 32nd percentile at -1 sigma
instead of the 15.87th. On an ideal null that estimator returns 0.84 of the
coarse width and 0.82 of the fine width and a probe spread near 2 where a
Gaussian tail gives 1 (verified by simulation, 200k draws). This module uses
the one-sided percentiles ``p / 2`` the deviates belong to
(``15.87 / 2.5 / 0.15``), recovering both widths to 0.3% with spread 1.01,
and reports the as-coded estimate beside it so the two can be compared where
the earlier numbers were quoted; the sigma-implied floor moves up by about
0.8 dB under the corrected probes. The register entry, not this module,
is where that decision lives.

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
    stated_as_coded_db: float = math.nan   # the sigma-implied value under the register's as-coded probes

    def as_dict(self) -> dict:
        return {"floor_db": self.db, "floor_evidence": self.evidence, "floor_population": self.population,
                "floor_frames": self.frames, "floor_percentile": self.percentile,
                "floor_stated_as_coded_db": self.stated_as_coded_db}


def floor_estimate(product: Product, off_era: np.ndarray | None, coarse: NullWidths) -> FloorEstimate:
    """Off-era 90th-percentile shelf where a verified off era exists, else the sigma-implied substitute."""
    offset = float(product.view.shelf_offset_db)
    stated = 10.0 * math.log10(coarse.core_sigma) + offset if math.isfinite(coarse.core_sigma) and coarse.core_sigma > 0 else math.nan
    stated_coded = 10.0 * math.log10(coarse.as_coded_sigma) + offset if math.isfinite(coarse.as_coded_sigma) and coarse.as_coded_sigma > 0 else math.nan
    if off_era is not None and np.asarray(off_era, dtype=bool).any():
        mask = np.asarray(off_era, dtype=bool) & product.selected
        shelf = product.shelf_db[mask]
        shelf = shelf[np.isfinite(shelf)]
        if shelf.size >= FLOOR_MIN_FRAMES:
            return FloorEstimate(float(np.percentile(shelf, FLOOR_PERCENTILE)), "measured",
                                 f"verified off era: {shelf.size} frames with a shelf estimate of {int(mask.sum())}",
                                 int(shelf.size), stated_as_coded_db=stated_coded)
        return FloorEstimate(stated, "stated", f"off era has only {shelf.size} frames with a shelf estimate; sigma-implied substitute",
                             int(shelf.size), stated_as_coded_db=stated_coded)
    if math.isfinite(stated):
        return FloorEstimate(stated, "stated", "no verified off era; sigma-implied substitute from the coarse null core width",
                             0, stated_as_coded_db=stated_coded)
    return FloorEstimate(math.nan, "refused", "no off era and no measurable null width", 0)


@dataclass(frozen=True)
class NullCalibration:
    channel: int
    freq_id: int
    era_label: str
    era_frames: int
    null_source: str                     # 'verified transmitter-off era' | 'bulk of the mixture (declared)'
    mixture_declared: bool
    coarse: NullWidths
    fine: NullWidths
    fine_designated_median: float        # median T over the designated window, all era frames (for the plates)
    floor: FloorEstimate
    exchangeability: Exchangeability | None
    bulk_size: int
    quiet_frames: int
    detected_frames: int
    notes: tuple[str, ...] = field(default_factory=tuple)

    def as_row(self) -> dict:
        row = {"channel": self.channel, "freq_id": self.freq_id, "era": self.era_label, "era_frames": self.era_frames,
               "null_source": self.null_source, "mixture_declared": self.mixture_declared, "bulk_size": self.bulk_size,
               "quiet_frames": self.quiet_frames, "detected_frames": self.detected_frames,
               "fine_designated_median": self.fine_designated_median}
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
    if off_era is not None and (np.asarray(off_era, dtype=bool) & product.selected).sum() >= MIN_NULL_FRAMES:
        null_frames = np.asarray(off_era, dtype=bool) & product.selected
        source, mixture = "verified transmitter-off era", False
    else:
        null_frames = era
        source, mixture = "bulk of the mixture (declared)", True
        notes.append("coarse null read from the bulk of the era's mixture: centre = median, scale = left side")
    coarse = describe_null(q[null_frames], COARSE_DOF)
    if fine_t is None:
        fine_t = fine_power_ratio(product.fine_terms_all())
    bulk = np.asarray(bulk_mask, dtype=bool)
    fine = describe_null(fine_t[era][:, bulk], FINE_DOF)
    designated = [(int(anchor_bin) + k) % fine_t.shape[1] for k in range(-2, 3)]
    fine_designated_median = float(np.median(fine_t[era][:, designated])) if era.any() else math.nan
    floor = floor_estimate(product, off_era, coarse)
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
