"""The residual chain of chapter 9 for one channel: shelf statistics, the
correlation time, and the coherence gain that turns a frame-stage residual
into ``r_proxy``.

eq:tolerance:chain: ``p_kept = 10^((S_kept - S_delay)/10)``,
``r_proxy = p_kept n_coh``, ``n_coh = min(tau_c, T_sid) / T_frame``, with
``tau_c`` the measured value or its upper bound where it is usable and the
sidereal-day cap where it is refused. Under the unity-transfer closure
``r_var = r_sys = r_proxy``. The chapter books the delay-filter credit
``S_delay`` at zero everywhere except the worlds table.

No post-processing credit is taken. All surviving shelf power is booked at
one coherence time on every band, ``((1.0, n_coh(tau)),)``
(:func:`booked_components`). The day / acquisition / frame variance split of
:func:`rfisher.residual.shelf_statistics` is not booked and not reported:
booking its intra-day and fast shares separately would be a ground-filter
credit (author decision 2026-09-23, design addendum section 5, milestone
M6b). What was ``r_sys_no_split`` is therefore ``r_sys`` itself.

Everything here is :mod:`rfisher.residual`'s: ``shelf_statistics`` (the
on-air shelf and the kept-frame floor where a verified off epoch exists) and
``correlation_time`` (the same-day structure function with its measured /
bounded-above / refused outcome and its day-block bootstrap). This module
only assembles them and exposes the gain

    G = n_coh(tau)

so that the selector's per-frame systematic residual can be
``p_i * G`` (``selection.systematic_residuals(..., gain=G)``): ``r_sys`` at a
point is then ``G`` times the kept-frame mean of the shelf-or-floor linear
level, which is ``r_proxy`` at that point.

Population. ``rfisher.residual`` selects the transmitter-on population by
calendar month strings (``off_through`` / ``off_from``) from the product's
``valid`` frames. Chapter 9 evaluates the chain "on its current era", so
:func:`residual_chain_on_frames` restricts the population to a frame mask
(the current era; the previous on era for a channel whose current era is
off) by writing a temporary copy of the product whose ``valid`` flag is
cleared outside the mask and running the unchanged ``rfisher.residual``
functions on it; the population is recorded on the result. The archive-wide
form :func:`residual_chain` remains for comparison. The chain's own floor
term (the off-epoch percentile inside the restricted population, usually
absent) is not the selector's floor; that is the null section's.
"""
from __future__ import annotations

import math
import os
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

from rfisher import residual

from .products import Product

FRAME_SECONDS = residual.CHIME_FRAME_SECONDS


@dataclass(frozen=True)
class ChainResult:
    channel: int
    freq_id: int
    population: str                    # how the transmitter-on population was chosen
    n_valid: int
    n_kept: int                        # kept at the survey flag (F <= mu_0)
    n_off_frames: int                  # the null population behind the floor
    on_shelf_db: float                 # on-air shelf level
    floor_db: float                    # kept-frame / off-era floor (NaN when none)
    floor_percentile: float
    tau_c_seconds: float
    tau_c_low: float
    tau_c_high: float
    tau_quality: str                   # 'measured' | 'bounded_above' | 'refused'
    tau_reason: str
    n_coh_intraday: float              # min(tau_c, T_sid) / T_frame at the booked tau
    components: tuple[tuple[float, float], ...]   # ((1.0, n_coh),): all surviving power at one coherence time
    gain: float                        # G = n_coh at the booked tau
    delay_key: str
    delay_suppression_db: float

    @property
    def tau_c_minutes(self) -> float:
        return self.tau_c_seconds / 60.0 if math.isfinite(self.tau_c_seconds) else math.nan

    @property
    def tau_outcome(self) -> str:
        """The chapter 8 vocabulary: measured interval, one-sided bound, or refused (cap)."""
        return {"measured": "measured", "bounded_above": "bound", "refused": "refused (cap)"}.get(self.tau_quality, self.tau_quality)

    def as_row(self) -> dict:
        return {
            "channel": self.channel, "freq_id": self.freq_id, "chain_population": self.population,
            "n_valid": self.n_valid, "n_kept_flag": self.n_kept, "n_off_frames": self.n_off_frames,
            "on_shelf_db": self.on_shelf_db, "chain_floor_db": self.floor_db,
            "tau_c_minutes": self.tau_c_minutes, "tau_c_low_minutes": self.tau_c_low / 60.0 if math.isfinite(self.tau_c_low) else math.nan,
            "tau_c_high_minutes": self.tau_c_high / 60.0 if math.isfinite(self.tau_c_high) else math.nan,
            "tau_quality": self.tau_quality, "tau_outcome": self.tau_outcome, "tau_reason": self.tau_reason,
            "n_coh_intraday": self.n_coh_intraday, "chain_gain": self.gain,
            "delay_key": self.delay_key, "delay_suppression_db": self.delay_suppression_db,
        }


def booked_components(corr: residual.CorrelationTime) -> tuple[tuple[float, float], ...]:
    """All surviving shelf power at one coherence time: ``((1.0, n_coh(tau)),)``.

    ``tau`` is ``corr.tau_for_budget``: the measured correlation time or its
    upper bound where it is usable, the sidereal-day cap where it is refused.
    The variance split is not booked on any band, so no ground-filter credit
    is taken. On a refused channel this is what
    :func:`rfisher.residual.surviving_components` books.
    """
    return ((1.0, float(residual.n_coh_from_correlation_time(corr.tau_for_budget))),)


def residual_chain(product_path: Path | str, *, off_through: str | None = None, off_from: str | None = None,
                   delay_key: str = residual.DEFAULT_DELAY_KEY) -> ChainResult:
    """Shelf statistics, correlation time and the booked coherence gain of one channel."""
    path = str(product_path)
    stats = residual.shelf_statistics(path, off_through=off_through, off_from=off_from)
    corr = residual.correlation_time(path, off_through=off_through, off_from=off_from)
    components = booked_components(corr)
    gain = float(sum(share * n_coh for share, n_coh in components))
    tau = float(corr.tau_c) if corr.tau_c is not None else math.nan
    if off_through and off_from:
        population = f"transmitter-on frames outside the off epochs through {off_through} and from {off_from}"
    elif off_through:
        population = f"transmitter-on frames after the off epoch through {off_through}"
    elif off_from:
        population = f"transmitter-on frames before the off epoch from {off_from}"
    else:
        population = "transmitter-on frames of the whole archive (no declared off epoch)"
    return ChainResult(
        channel=int(stats.channel), freq_id=int(stats.freq_id), population=population,
        n_valid=int(stats.n_valid), n_kept=int(stats.n_kept), n_off_frames=int(stats.n_off_frames),
        on_shelf_db=float(stats.on_shelf_db), floor_db=float(stats.floor_db), floor_percentile=float(stats.floor_percentile),
        tau_c_seconds=tau, tau_c_low=float(corr.tau_lo) if corr.tau_lo is not None else math.nan,
        tau_c_high=float(corr.tau_hi) if corr.tau_hi is not None else math.nan,
        tau_quality=str(corr.quality), tau_reason=str(corr.reason or ""),
        n_coh_intraday=float(residual.n_coh_from_correlation_time(tau if math.isfinite(tau) else residual.MAX_TAU_C_SECONDS)),
        components=components, gain=gain, delay_key=delay_key,
        delay_suppression_db=float(residual.DELAY_SUPPRESSION_DB[delay_key]),
    )


LARGE_UNUSED_KEYS = ("psd_frame_db_i16",)


def masked_valid(valid: np.ndarray, frames: np.ndarray) -> np.ndarray:
    """The product's ``valid`` array with frames outside ``frames`` cleared, in the array's own shape and dtype."""
    valid = np.asarray(valid)
    flat = valid.reshape(-1).astype(bool) & np.asarray(frames, dtype=bool).reshape(-1)
    return flat.reshape(valid.shape).astype(valid.dtype)


ZEROED_WHEN_INVALID = ("p_ref_sum_u64", "p_ref_lower_u64", "p_ref_upper_u64", "reject_mask")
NAN_WHEN_INVALID = ("coarse_power_ratio", "normalized_coarse_power_ratio_db", "normalized_pilot_excess", "pilot_excess_db",
                    "estimated_data_shelf_snr_db")


def invalidate_frames(arrays: dict, frames) -> dict:
    """Make the frames outside ``frames`` invalid under the v5 product contract.

    The contract ties the flags together (``valid`` iff ``p_ref_sum != 0``;
    ``reject_mask`` equals the exact decision on valid frames; the derived
    per-frame ratios are NaN where the reference sum is zero), so an
    era-restricted copy clears the reference terms and the flag together and
    blanks the derived fields on the excluded frames.
    """
    keep = np.asarray(frames, dtype=bool).reshape(-1)
    out = dict(arrays)
    out["valid"] = masked_valid(arrays["valid"], keep)
    drop = ~keep
    for key in ZEROED_WHEN_INVALID:
        if key in out:
            a = np.array(out[key], copy=True)
            a.reshape(-1)[drop] = 0
            out[key] = a
    for key in NAN_WHEN_INVALID:
        if key in out:
            a = np.array(out[key], dtype=np.float64, copy=True)
            a.reshape(-1)[drop] = np.nan
            out[key] = a
    return out


def residual_chain_on_frames(product: Product, frames, *, population: str, off_through: str | None = None,
                             off_from: str | None = None, delay_key: str = residual.DEFAULT_DELAY_KEY) -> ChainResult:
    """The chain on a frame mask: ``valid`` is cleared outside ``frames`` in a temporary copy of the product."""
    frames = np.asarray(frames, dtype=bool)
    if frames.shape != (product.n_frames,):
        raise ValueError(f"frames must have shape ({product.n_frames},); got {frames.shape}")
    arrays = {}
    with np.load(product.path, allow_pickle=False) as z:
        for key in z.files:
            if key in LARGE_UNUSED_KEYS:
                continue
            arrays[key] = z[key]
    arrays = invalidate_frames(arrays, frames)
    valid = np.asarray(arrays["valid"]).reshape(-1).astype(bool)
    fd, tmp = tempfile.mkstemp(prefix=f"chain_{product.path.stem}_", suffix=".npz")
    os.close(fd)
    try:
        np.savez(tmp, **arrays)
        result = residual_chain(tmp, off_through=off_through, off_from=off_from, delay_key=delay_key)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    return replace(result, population=f"{population}: {int(valid.sum())} valid frames")
