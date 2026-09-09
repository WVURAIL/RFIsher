"""Strict alignment and descriptive complex-data checks for transfer inputs.

Neither a fitted gain nor a difference between two reductions is an injected
signal response. Covariance must be propagated separately from a coherent mean.
"""
from __future__ import annotations

import numpy as np


def frequency_coverage(centre, width, *, target=(470., 608.)):
    """Nominal channel-edge coverage in MHz; not a measured passband response."""
    centre, width = np.asarray(centre, float), np.asarray(width, float)
    low, high = target
    if (centre.ndim != 1 or not centre.size or width.shape != centre.shape
            or not np.all(np.isfinite(centre)) or not np.all(np.isfinite(width))
            or np.any(width <= 0) or len(np.unique(centre)) != centre.size
            or not np.isfinite([low, high]).all() or low >= high):
        raise ValueError("invalid frequency coordinates or target band")
    left, right = centre-width/2, centre+width/2
    # Union length, so overlapping channel edges cannot inflate coverage.
    intervals = sorted((max(a, low), min(b, high)) for a, b in zip(left, right)
                       if min(b, high) > max(a, low))
    overlap, end = 0., -np.inf
    for a, b in intervals:
        overlap += max(0., b-max(a, end))
        end = max(end, b)
    return {"nominal_edges_mhz": [float(left.min()), float(right.max())],
            "target_mhz": [low, high], "target_overlap_mhz": float(overlap),
            "covers_entire_target": bool(np.isclose(overlap, high-low, rtol=0, atol=1e-9)),
            "channels": int(centre.size)}


def paired_complex_summary(before, after, weight_before, weight_after):
    """Equal-cell diagnostics on common finite, positive-weight support.

    The weight magnitudes are NOT treated as independent-sample precision:
    both reductions may use the same data. The output has no error bars and
    cannot establish signal loss, noise covariance or a physical residual.
    """
    before, after = np.asarray(before), np.asarray(after)
    wa, wb = np.asarray(weight_before), np.asarray(weight_after)
    if not before.size or any(x.shape != before.shape for x in (after, wa, wb)):
        raise ValueError("paired data and weights must have identical nonempty shapes")
    if not np.iscomplexobj(before) or not np.iscomplexobj(after):
        raise ValueError("complex data are required")
    if np.iscomplexobj(wa) or np.iscomplexobj(wb):
        raise ValueError("weights must be real")
    va = np.isfinite(before) & np.isfinite(wa) & (wa > 0)
    vb = np.isfinite(after) & np.isfinite(wb) & (wb > 0)
    valid = va & vb
    result = {"total_cells": int(before.size), "common_valid_cells": int(valid.sum()),
              "before_only_valid_cells": int((va & ~vb).sum()),
              "after_only_valid_cells": int((vb & ~va).sum()),
              "weighting": "equal cells on common support; no independence or variance assumption",
              "least_squares_gain": None, "difference_energy_over_before": None,
              "after_energy_over_before": None}
    if valid.any():
        a, b = before[valid].astype(complex), after[valid].astype(complex)
        denominator = float(np.vdot(a, a).real)
        if denominator > 0:
            gain = np.vdot(a, b)/denominator
            result.update(least_squares_gain=[float(gain.real), float(gain.imag)],
                          difference_energy_over_before=float(np.vdot(b-a, b-a).real/denominator),
                          after_energy_over_before=float(np.vdot(b, b).real/denominator))
    return result


def propagate_linear_moments(operator, mean, covariance):
    """Return A mu and A C A^H for a fixed linear operator.

    C is E[(x-mu)(x-mu)^H], not E[xx^H]. Signal and noise inputs need separate
    calls. A data-fitted cleaner needs injection through its fitting procedure;
    applying a single saved matrix alone does not measure that response.
    """
    a, mu, cov = (np.asarray(x, dtype=complex) for x in (operator, mean, covariance))
    if (a.ndim != 2 or 0 in a.shape or mu.shape != (a.shape[1],)
            or cov.shape != (a.shape[1], a.shape[1])
            or not all(np.isfinite(x).all() for x in (a, mu, cov))):
        raise ValueError("invalid operator, mean or covariance dimensions/values")
    scale = float(np.max(np.abs(cov)))
    tolerance = 1e-12 * scale
    if not np.allclose(cov, cov.conj().T, rtol=0, atol=tolerance):
        raise ValueError("covariance must be Hermitian")
    if np.linalg.eigvalsh(cov).min() < -tolerance:
        raise ValueError("covariance must be positive semidefinite")
    return a @ mu, a @ cov @ a.conj().T


def compare_beamformed_files(before_path, after_path, *, position_atol_deg=1e-10):
    """Refuse reductions with different coordinates or sidereal-day membership.

    The position tolerance accommodates float64 roundoff only; it is not a
    fitted astrometric allowance. Matching days does not imply matching weights.
    """
    import h5py

    if not 0 <= position_atol_deg <= 1e-10:
        raise ValueError("position tolerance may accommodate roundoff only")
    issues = []
    expected_axes = ["object_id", "pol", "freq", "ew"]
    result = {"before": str(before_path), "after": str(after_path),
              "position_atol_deg": position_atol_deg, "refusal_reasons": issues,
              "physical_transfer_measured": False, "diagnostics": None}
    with h5py.File(before_path, "r") as before, h5py.File(after_path, "r") as after:
        for label, h in (("before", before), ("after", after)):
            for key in ["beam", "weight", "position", *[f"index_map/{a}" for a in expected_axes]]:
                if key not in h:
                    issues.append(f"{label}: missing {key}")
            if "lsd" not in h.attrs:
                issues.append(f"{label}: missing sidereal-day membership")
        if issues:
            return result
        if any(str(h.attrs.get("__memh5_subclass", "")) != "draco.core.containers.FitFormedBeamEW"
               for h in (before, after)):
            issues.append("unsupported container class")
        for label, h in (("before", before), ("after", after)):
            for name in ("beam", "weight"):
                axes = [x.decode() if isinstance(x, bytes) else str(x)
                        for x in h[name].attrs.get("axis", [])]
                if axes != expected_axes:
                    issues.append(f"{label}: unexpected {name} axes")
                shape = tuple(len(h[f"index_map/{a}"]) for a in expected_axes)
                if h[name].shape != shape:
                    issues.append(f"{label}: {name} shape does not match coordinates")
            if len(np.unique(h.attrs["lsd"])) != len(h.attrs["lsd"]):
                issues.append(f"{label}: duplicate sidereal day")
        for axis in expected_axes:
            a, b = before[f"index_map/{axis}"][:], after[f"index_map/{axis}"][:]
            if not np.array_equal(a, b):
                issues.append(f"different {axis} coordinates")
            if len(np.unique(a)) != len(a) or len(np.unique(b)) != len(b):
                issues.append(f"duplicate {axis} coordinates")
        days_a, days_b = set(map(int, before.attrs["lsd"])), set(map(int, after.attrs["lsd"]))
        result.update(before_only_days=sorted(days_a-days_b), after_only_days=sorted(days_b-days_a))
        if days_a != days_b:
            issues.append("different sidereal-day membership; re-stack a common cohort")
        a, b = before["position"][:], after["position"][:]
        if a.shape != b.shape or a.dtype.names != b.dtype.names or not {"ra", "dec"} <= set(a.dtype.names or ()):
            issues.append("incompatible position coordinates")
        else:
            offsets = {name: float(np.max(np.abs(a[name]-b[name]))) for name in ("ra", "dec")}
            result["maximum_position_difference_deg"] = offsets
            if any(not np.isfinite(x) or x > position_atol_deg for x in offsets.values()):
                issues.append("different source positions")
        if issues:
            return result
        a, b, wa, wb = before["beam"][:], after["beam"][:], before["weight"][:], after["weight"][:]
        result["weights_equal"] = bool(np.array_equal(wa, wb))
        result["diagnostics"] = paired_complex_summary(a, b, wa, wb)
        result["by_polarization_and_ew"] = []
        for ip, pol in enumerate(before["index_map/pol"][:]):
            for ie, ew in enumerate(before["index_map/ew"][:]):
                sl = (slice(None), ip, slice(None), ie)
                result["by_polarization_and_ew"].append({
                    "pol": pol.decode() if isinstance(pol, bytes) else str(pol), "ew": float(ew),
                    **paired_complex_summary(a[sl], b[sl], wa[sl], wb[sl])})
    return result
