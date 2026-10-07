"""The capture ruling's units: the release's ``a18_units`` as one namespace.

Release r5.2 kept one module of conversions for the producer and its copies
(``a18_units.py``; DECISIONS.md items 1, 3, 4, 6, 7, 8 and 15). Its science
half, the BAO-band coherence gain and the bin fill, is
:mod:`rfisher.forecast.radiofisher_bao.coherence_gain` and is re-exported here;
the per-bin tolerances the bin fill reads are the vendored references
(:func:`lam_bin`, :func:`lam_bin_none`, :mod:`rfisher.tolerance.reference`); its
detector half stays here, unchanged, because the ruling applies it in the
middle of its computation:

- :func:`to_power` and :func:`gate_power`: the capture statistic A (a net
  cross-frame amplitude) and its detection gate as the per-frame covariance
  ratio A^2 N n_b (item 1);
- :func:`gmin_models` and :func:`admissible_min_G`: the least G any tau
  allows for an n-frame reading (item 3);
- :func:`every_policy_blockers`: the item 6 rule on the policies' readings;
- the detector tables ``NB`` (baselines per class) and ``NFRAMES`` (frames
  per dump), which :meth:`CaptureHandoff.check_constants` holds equal to the
  handoff's manifest;
- ``SHORT_BINS``, the bins that hold fewer frames than their dump, and
  :func:`nframes`, the frames of a channel's reading in one dump.

pilot-proxy publishes the same detector functions (M4); the copy here is kept
until a byte-level proof lets one go.
"""
import functools

import numpy as np

from rfisher.forecast.radiofisher_bao import coherence_gain
from rfisher.forecast.radiofisher_bao.coherence_gain import (  # noqa: F401
    CAP, COSD_BAO, K_BAO, NU21, OMEGA, ZS, bin_overlaps, chi_mpch, gain_bao,
    gain_zero, invert_gain, z_center)
from rfisher.forecast.radiofisher_bao.coherence_gain import TF as _TF_GAIN
from rfisher.tolerance import reference

NFFT = 16384                      # samples per frame, N of item 1
TSAMP = 2.56e-6
TF = NFFT * TSAMP                 # T_frame, s
assert TF == _TF_GAIN
ALLOW_DB = 3.0
ALLOW_R = 10 ** (ALLOW_DB / 10)   # item 7: the code's test is R > 10^0.3 (about 2), not R > 2
# item 1: n_b, the class's baseline count
NB = {(0, 1): 1020, (0, 32): 896, (0, 64): 768, (0, 128): 512, (0, 255): 4, (1, 0): 768, (2, 0): 512, (3, 0): 256}
# frames per dump (stacks axis 0 of the reduced dumps)
NFRAMES = {"20260916162300": 11, "20260917040230": 33, "20260917090230": 33, "20260917140230": 33}
for _e in ("20260917160208", "20260917160223", "20260917160238", "20260917160308", "20260917160408", "20260917160608",
           "20260917161008", "20260917161408", "20260917161808", "20260917162208"):
    NFRAMES[_e] = 4
# bins that hold fewer frames than their dump (DECISIONS.md item 87, audit A4): {(dump, freq_id): (channel, frames)}, from a
# header-only scan of stacks.npy axis 0 of every reduced dump, datasets/pilot_reduce_<dump>/<freq_id>.npz (280 bins per dump;
# output/d2-frame-count-2026-10-01/scratch/frames_scan.json, sha256 2e36330bb22e974ddd1af180eb66a61f28bf458b7e6e883615cbc7dce5f47791,
# written by scan_frames.py beside it). Every other bin of every dump holds its dump's NFRAMES.
SHORT_BINS = {("20260917090230", 511): (35, 27), ("20260917090230", 703): (23, 27), ("20260917090230", 759): (19, 27)}
WORLDS = ("200ns", "none")       # item 15: the deployed 200 ns delay filter with its credit S (the record's), or no filter


@functools.lru_cache(maxsize=None)
def lam_bin():
    """Deployed per-bin tolerances of the single-bin channels (primary basis, dilation, zeta 1)."""
    return dict(reference.coarse_world_bins())


@functools.lru_cache(maxsize=None)
def lam_bin_none():
    """Item 15: the no-filter per-bin tolerances, the exact-time reference's conditional_reference_amplitude (the binding
    dilation component of each bin, one on-sky year)."""
    d = reference.exact_time_conditions(); assert d["target_time_years"] == 1.0 and d["zeta"] == 1.0
    return {b: x["value"] for b, x in reference.exact_time_bins().items()}


def fill_factor(ch, lam_dep, world="200ns"):
    """The bin fill in the deployed (200 ns) world or, item 15, the no-filter world, on the vendored references."""
    return coherence_gain.fill_factor(ch, lam_dep, lam_bin() if world == "200ns" else lam_bin_none())


def to_power(a, cls, n_frame=NFFT):
    """Item 1: the per-frame covariance ratio A^2 N n_b of a net class amplitude. A reading at or below zero is not
    squared (it is not measured, and squaring would turn a deficit into an excess)."""
    return a * a * n_frame * NB[cls] if a > 0 else a


def gate_power(gate, cls, n_frame=NFFT):
    """Item 1: the detection gate (3 s) becomes (3 s)^2 N n_b."""
    return gate * gate * n_frame * NB[cls]


# ---- item 3: the admissible minimum G
@functools.lru_cache(maxsize=None)
def gmin_models(n):
    """Lowest power-form R(tau)/R(G = 1) over tau for a cross-frame amplitude over n frames, per autocorrelation model.
    The estimator uses only products of distinct frames, so a residual with autocorrelation rho(d) responds as
    resp = mean_{i != j} rho(|i - j|); the true power is A^2 / resp and G = max(tau / T_frame, 1)."""
    d = np.arange(1, n); wts = 2 * (n - d) / (n * (n - 1)); out = {}
    for model in ("exp", "block"):
        best = np.inf
        for tf in np.logspace(-2, 4, 6001):
            rho = np.exp(-d / tf) if model == "exp" else np.clip(1 - d / tf, 0, None)
            resp = float(np.sum(wts * rho))
            if resp <= 0: continue
            best = min(best, max(tf, 1.0) / resp)
        out[model] = best
    return out


def nframes(epoch, ch):
    """The frames of channel ch's reading in one dump: the fewest over its in-band bins (NFRAMES unless one is short)."""
    return min([NFRAMES[epoch]] + [n for (e, _), (c, n) in SHORT_BINS.items() if e == epoch and c == ch])


def admissible_min_G(n):
    """The lower of the two models (item 3): 8.41 for 11 frames, 21.06 for 33, 4.06 for 4."""
    return min(gmin_models(n).values())


def every_policy_blockers(pols, order):
    """Item 6: excision needs every policy that keeps at least one dump over the allowance. pols holds only the policies
    that keep a dump (a policy that keeps none is listed and excluded before this); any of them that is not measured
    above the control floor on the range may pass, its most favorable value, and blocks the excision."""
    return [p for p in order if p in pols and not pols[p]["measured"]]


def constants():
    """The detector constants as the handoff manifest records them."""
    return {"NFFT": NFFT, "TSAMP": TSAMP, "CAP": CAP, "NB": {f"{c[0]},{c[1]}": n for c, n in NB.items()},
            "NFRAMES": dict(NFRAMES), "measurement_allowance_db": ALLOW_DB, "detection_gate_sigma": 3.0}
