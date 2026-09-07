"""The residual chain of chapter 9 for one channel: shelf statistics, the
sidereal decomposition, the correlation time, and the coherence gain that
turns a frame-stage residual into ``r_proxy``.

eq:tolerance:chain: ``p_kept = 10^((S_kept - S_delay)/10)``,
``r_proxy = p_kept (phi_intra n_coh,intra + phi_fast n_coh,fast)``,
``n_coh,intra = min(tau_c, T_sid) / T_frame``, ``n_coh,fast = 1``. Under the
unity-transfer closure ``r_var = r_sys = r_proxy``. The chapter books the
delay-filter credit ``S_delay`` at zero everywhere except the worlds table.

Everything here is :mod:`rfisher.residual`'s: ``shelf_statistics`` (the
on-air shelf, the kept-frame floor where a verified off epoch exists, the
day / acquisition / frame variance split of the trimmed transmitter-on
population, the ground-filter credit), ``correlation_time`` (the same-day
structure function with its measured / bounded-above / refused outcome and
its day-block bootstrap), and ``surviving_components`` (the booking rule: a
refused or unusable correlation time books every surviving share at the
sidereal-day cap and takes no ground-filter credit). This module only
assembles them and exposes the gain

    G = sum_k phi_k n_coh,k

so that the selector's per-frame systematic residual can be
``p_i * G`` (``selection.systematic_residuals(..., gain=G)``): ``r_sys`` at a
point is then ``G`` times the kept-frame mean of the shelf-or-floor linear
level, which is ``r_proxy`` at that point.

Population. ``rfisher.residual`` selects the transmitter-on population by
calendar month strings (``off_through`` / ``off_from``), not by an arbitrary
frame mask, so the shelf statistics and the correlation time are computed
on the archive's on population outside the channel's declared off epoch,
as the superseded chapter 9 numbers were. Callers pass the off-epoch months
the era table established (or :data:`rfisher.residual.SIGN_OFF_FROM` /
``SIGN_ON_OFF_THROUGH``); the population used is recorded on the result.
An era-restricted chain is a follow-up the design names.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from rfisher import residual

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
    intraday_share: float              # phi_intra
    fast_share: float                  # phi_fast
    ground_filter_db: float            # removed share in dB (description only when tau_c refused)
    tau_c_seconds: float
    tau_c_low: float
    tau_c_high: float
    tau_quality: str                   # 'measured' | 'bounded_above' | 'refused'
    tau_reason: str
    n_coh_intraday: float              # min(tau_c, T_sid) / T_frame at the booked tau
    components: tuple[tuple[float, float], ...]   # (share, n_coh) pairs as booked
    gain: float                        # G = sum share * n_coh
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
            "intraday_share": self.intraday_share, "fast_share": self.fast_share,
            "ground_filter_db": self.ground_filter_db,
            "tau_c_minutes": self.tau_c_minutes, "tau_c_low_minutes": self.tau_c_low / 60.0 if math.isfinite(self.tau_c_low) else math.nan,
            "tau_c_high_minutes": self.tau_c_high / 60.0 if math.isfinite(self.tau_c_high) else math.nan,
            "tau_quality": self.tau_quality, "tau_outcome": self.tau_outcome, "tau_reason": self.tau_reason,
            "n_coh_intraday": self.n_coh_intraday, "chain_gain": self.gain,
            "delay_key": self.delay_key, "delay_suppression_db": self.delay_suppression_db,
        }


def residual_chain(product_path: Path | str, *, off_through: str | None = None, off_from: str | None = None,
                   delay_key: str = residual.DEFAULT_DELAY_KEY) -> ChainResult:
    """Shelf statistics, correlation time and the booked coherence gain of one channel."""
    path = str(product_path)
    stats = residual.shelf_statistics(path, off_through=off_through, off_from=off_from)
    corr = residual.correlation_time(path, off_through=off_through, off_from=off_from)
    components = tuple((float(share), float(n_coh)) for share, n_coh in residual.surviving_components(stats, corr))
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
        intraday_share=float(stats.intraday_fraction), fast_share=float(stats.fast_fraction),
        ground_filter_db=float(stats.ground_filter_db),
        tau_c_seconds=tau, tau_c_low=float(corr.tau_lo) if corr.tau_lo is not None else math.nan,
        tau_c_high=float(corr.tau_hi) if corr.tau_hi is not None else math.nan,
        tau_quality=str(corr.quality), tau_reason=str(corr.reason or ""),
        n_coh_intraday=float(residual.n_coh_from_correlation_time(tau if math.isfinite(tau) else residual.MAX_TAU_C_SECONDS)),
        components=components, gain=gain, delay_key=delay_key,
        delay_suppression_db=float(residual.DELAY_SUPPRESSION_DB[delay_key]),
    )
