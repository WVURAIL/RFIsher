"""Descriptive digital voltage moments with explicit pairwise support.

No gain, delay, quantization, noise-bias or missing-packet correction is implied.
Different pair supports need not produce a positive-semidefinite matrix.
"""
from __future__ import annotations

import numpy as np


def decode_excess8(packed):
    """Native CHIME byte: high nibble real, low imaginary, each excess-8."""
    packed = np.asarray(packed)
    if packed.dtype != np.uint8:
        raise TypeError("packed samples must be uint8")
    real = (packed >> 4).astype(np.float64) - 8
    imag = (packed & 15).astype(np.float64) - 8
    return real + 1j * imag


def pair_moments(samples, support=None):
    """Sufficient sums for E[x_i conj(x_j)] on each pair's common support.

    `support` is a declared selection, not necessarily verified packet validity.
    Nonfinite samples are excluded independently for each input. All returned
    arrays have axes [input_i, input_j]; sum_x and power_x refer to input_i.
    """
    x = np.asarray(samples)
    if x.ndim != 2 or x.shape[1] == 0 or not np.iscomplexobj(x):
        raise ValueError("samples must be complex [time,input] with at least one input")
    if support is None:
        valid = np.isfinite(x)
    else:
        support = np.asarray(support)
        if support.shape != x.shape or support.dtype != np.bool_:
            raise ValueError("support must be boolean with the samples' shape")
        valid = support & np.isfinite(x)
    x = np.where(valid, x, 0).astype(np.complex128)
    mask = valid.astype(np.float64)
    return {
        "count": np.rint(mask.T @ mask).astype(np.int64),
        "sum_x": x.T @ mask,
        "power_x": (x.real**2 + x.imag**2).T @ mask,
        "cross": x.T @ x.conj(),
    }


def summarize_moments(moments):
    """Population moments, not unbiased estimates or confidence intervals.

    Raw coherency includes the mean; centered coherency subtracts the pair's
    own means and uses paired centered auto powers. Undefined results are NaN.
    Pool sufficient sums before calling this function to combine time blocks.
    """
    n = np.asarray(moments["count"])
    sx = np.asarray(moments["sum_x"], dtype=np.complex128)
    px = np.asarray(moments["power_x"], dtype=np.float64)
    cross = np.asarray(moments["cross"], dtype=np.complex128)
    if (n.ndim != 2 or n.shape[0] != n.shape[1] or not n.size
            or any(a.shape != n.shape for a in (sx, px, cross))
            or not np.issubdtype(n.dtype, np.integer) or np.any(n < 0)
            or not np.array_equal(n, n.T)
            or not all(np.isfinite(a).all() for a in (sx, px, cross))
            or np.any(px < 0)):
        raise ValueError("invalid pairwise moment dimensions or values")
    with np.errstate(divide="ignore", invalid="ignore"):
        mean_x = np.where(n > 0, sx / n, np.nan + 1j*np.nan)
        visibility = np.where(n > 0, cross / n, np.nan + 1j*np.nan)
        covariance = visibility - mean_x * mean_x.T.conj()
        auto = px / np.where(n > 0, n, np.nan)
        centered_auto = auto - np.abs(mean_x)**2
        tolerance = 64*np.finfo(float).eps * np.maximum(auto, 1.)
        if np.any(centered_auto < -tolerance):
            raise ValueError("moments have negative centered auto power")
        centered_auto = np.maximum(centered_auto, 0.)
        denominator = np.sqrt(px * px.T)
        coherency = np.where((n > 0) & (denominator > 0),
                             cross / denominator, np.nan + 1j*np.nan)
        cd = np.sqrt(centered_auto * centered_auto.T)
        centered_coherency = np.where((n > 0) & (cd > 0),
                                      covariance / cd, np.nan + 1j*np.nan)
    return {"visibility": visibility, "mean_x": mean_x,
            "covariance": covariance, "coherency": coherency,
            "centered_coherency": centered_coherency}
