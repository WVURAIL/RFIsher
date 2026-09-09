"""Exact selector and retained-truth accounting for channel 29 digital controls.

The injected shelf is a known pre-quantization data-power ratio. It is not a
measured post-filter visibility residual. Cases share null frames within one
block; only complete independently seeded blocks are statistical replicates.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping

import numpy as np

ETA_NUMERATOR = 4508969069674235
ETA_DENOMINATOR = 4503599627370496
TARGET_NORM_SQ = 6372
REFERENCE_NORM_SUM_SQ = 12713
FLOOR_LINEAR = 2.1551920577866108e-5
SHELF_CONVERSION = 10.0 ** (11.3 / 10) * 3051.7578125 / 6000000
PRIMARY_CASES = {
    "null": (("off", 96),),
    "intermittent_m50": (("off", 96), ("on_m50", 32)),
    "intermittent_m44": (("off", 96), ("on_m44", 32)),
    "intermittent_m10": (("off", 96), ("on_m10", 32)),
    "variable_50pct": (("off", 64), ("on_m50", 32), ("on_m44", 16), ("on_m10", 16)),
}


def canonical_digest(value, digest_key):
    payload = {k: v for k, v in value.items() if k != digest_key}
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode()).hexdigest()


def frame_seed(protocol_sha256, stage, block, population, index):
    payload = ["channel29-residual-controls-v1", protocol_sha256, stage,
               int(block), population, int(index), 2048, 29]
    digest = hashlib.sha256(json.dumps(
        payload, separators=(",", ":"), ensure_ascii=True,
    ).encode()).digest()
    return int.from_bytes(digest[:8], "big")


def exact_kept(powers):
    """Python integers avoid uint64 overflow in the frozen rational comparison."""
    p = np.asarray(powers)
    if p.ndim != 2 or p.shape[1] != 3 or p.dtype != np.uint64:
        raise ValueError("powers must be uint64 [frames,3]")
    return np.asarray([
        int(lo) + int(hi) != 0 and
        int(t) * REFERENCE_NORM_SUM_SQ * ETA_DENOMINATOR <=
        TARGET_NORM_SQ * (int(lo) + int(hi)) * ETA_NUMERATOR
        for t, lo, hi in p
    ], dtype=bool)


def normalized_ratio(powers):
    p = np.asarray(powers)
    exact_kept(p)  # validate, including integer type
    numerator = p[:, 0].astype(float) * REFERENCE_NORM_SUM_SQ
    denominator = (p[:, 1].astype(float) + p[:, 2].astype(float)) * TARGET_NORM_SQ
    return np.divide(numerator, denominator, out=np.full(len(p), np.nan),
                     where=denominator != 0)


def maximum_kept_shelf():
    # Evaluate the tiny difference as integers before converting to float.
    return SHELF_CONVERSION * (ETA_NUMERATOR - ETA_DENOMINATOR) / ETA_DENOMINATOR


def population_measurement(powers, *, shelf_db, clip_fraction):
    """Count all generated frames, with invalid references counted as unkept.

    The generated thermal model has no telescope health/map selection. Clipping
    is reported, never used to remove inconvenient samples after generation.
    """
    p = np.asarray(powers)
    keep = exact_kept(p)
    clip = np.asarray(clip_fraction, dtype=float)
    if clip.shape != (len(p),) or not np.all(np.isfinite(clip)) or np.any((clip < 0) | (clip > 1)):
        raise ValueError("invalid clipping fractions")
    if shelf_db is not None and (not math.isfinite(shelf_db) or isinstance(shelf_db, bool)):
        raise ValueError("shelf level must be finite or null")
    truth = 0.0 if shelf_db is None else 10.0 ** (shelf_db / 10.0)
    if not math.isfinite(truth):
        raise ValueError("nonfinite truth")
    if maximum_kept_shelf() >= FLOOR_LINEAR:
        raise ValueError("floor-constant assignment algebra no longer holds")
    q = normalized_ratio(p)
    finite = q[np.isfinite(q)]
    return {
        "frames": len(p), "kept": int(keep.sum()),
        "retention": float(keep.mean()) if len(p) else None,
        "invalid_reference_frames": int(np.count_nonzero(~np.isfinite(q))),
        "injected_shelf_linear": truth,
        "truth_kept_sum": int(keep.sum()) * truth,
        "assigned_kept_mean": FLOOR_LINEAR if keep.any() else None,
        "truth_kept_mean": truth if keep.any() else None,
        "kept_prefix_counts": {str(n): int(keep[:n].sum()) for n in (16, 32, 64, 96) if n <= len(keep)},
        "q_mean": float(finite.mean()) if len(finite) else None,
        "q_std": float(finite.std(ddof=1)) if len(finite) > 1 else None,
        "clip_fraction_mean": float(clip.mean()) if len(clip) else None,
        "clip_fraction_max": float(clip.max()) if len(clip) else None,
    }


def assemble_cases(populations: Mapping):
    """Build the frozen five-case family without treating its cases as independent."""
    if set(populations) != {"off", "on_m50", "on_m44", "on_m10"}:
        raise ValueError("unexpected primary populations")
    expected = {"off": (96, 0.0), "on_m50": (32, 1e-5),
                "on_m44": (32, 10**-4.4), "on_m10": (32, .1)}
    for name, (count, truth) in expected.items():
        row = populations[name]
        if row["frames"] != count or not math.isclose(row["injected_shelf_linear"], truth, rel_tol=1e-12, abs_tol=0):
            raise ValueError("population size or injected truth changed")
    rows = {}
    for case, parts in PRIMARY_CASES.items():
        n = sum(count for name, count in parts)
        kept = sum(populations[name]["kept_prefix_counts"][str(count)] for name, count in parts)
        truth_sum = sum(populations[name]["kept_prefix_counts"][str(count)] * populations[name]["injected_shelf_linear"] for name, count in parts)
        rows[case] = {
            "kept": kept, "claim": FLOOR_LINEAR if kept else None,
            "truth": truth_sum / kept if kept else None,
            "frames": n, "retention": kept / n,
            "supported": kept >= 32,
        }
    return rows
