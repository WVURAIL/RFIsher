"""Finite-record SDR diagnostics in saved complex-IQ units.

No physical power, independent noise, or ATSC pilot/reference identity is
inferred. The tone-plus-line fit is a descriptive two-sinusoid model.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import minimize_scalar


def _samples(samples, sample_rate_hz):
    x = np.asarray(samples)
    if x.ndim != 1 or x.size < 8 or not np.iscomplexobj(x):
        raise ValueError("at least eight one-dimensional complex samples required")
    if not np.isfinite(x).all():
        raise ValueError("nonfinite capture sample")
    if not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("positive finite sample rate required")
    return x.astype(np.complex128, copy=False)


def projection(samples, sample_rate_hz, frequency_hz):
    """Unwindowed coefficient at a fixed frequency; local first-sample phase."""
    x = _samples(samples, sample_rate_hz)
    if not np.isfinite(frequency_hz) or abs(frequency_hz) >= sample_rate_hz / 2:
        raise ValueError("frequency must lie strictly within complex Nyquist range")
    t = np.arange(x.size, dtype=np.float64) / sample_rate_hz
    return complex(np.mean(x * np.exp(-2j * np.pi * frequency_hz * t)))


def hann_periodogram(samples, sample_rate_hz):
    """Two-sided density, normalized so integral equals Hann-weighted power."""
    x = _samples(samples, sample_rate_hz)
    w = np.hanning(x.size)
    f = np.fft.fftshift(np.fft.fftfreq(x.size, 1 / sample_rate_hz))
    density = np.fft.fftshift(np.abs(np.fft.fft(x * w)) ** 2)
    density /= sample_rate_hz * np.dot(w, w)
    return f, density


def db_ratio(numerator, denominator):
    if numerator <= 0 or denominator <= 0:
        return None
    value = float(10 * np.log10(numerator / denominator))
    return value if np.isfinite(value) else None


def narrow_feature(samples, sample_rate_hz, center_hz, refine=True):
    """Peak in predeclared +/-500 Hz; adjacent spectrum is a diagnostic only.

    Peak frequency is fitted to the Hann-windowed amplitude. Bin spacing is
    recorded separately and is not a confidence interval on fitted frequency.
    Weak-window peak estimates need not identify an actual coherent line.
    """
    x = _samples(samples, sample_rate_hz)
    if abs(center_hz) + 5000 >= sample_rate_hz / 2:
        raise ValueError("feature and diagnostic sidebands must fit inside Nyquist range")
    f, density = hann_periodogram(x, sample_rate_hz)
    offset = np.abs(f - center_hz)
    search = np.flatnonzero(offset <= 500)
    band = offset <= 2000
    side = (offset >= 3000) & (offset <= 5000)
    if search.size < 1 or not np.any(side):
        raise ValueError("record too short for fixed frequency diagnostics")
    peak = int(search[np.argmax(density[search])])
    frequency = float(f[peak])
    df = sample_rate_hz / x.size
    if refine and density[peak] > 0:
        t = np.arange(x.size, dtype=np.float64) / sample_rate_hz
        windowed = x * np.hanning(x.size)
        low = max(center_hz - 500, frequency - df)
        high = min(center_hz + 500, frequency + df)
        def negative_power(freq):
            return -abs(np.mean(windowed * np.exp(-2j * np.pi * freq * t))) ** 2
        fitted = minimize_scalar(negative_power, bounds=(low, high), method="bounded",
                                 options={"xatol": 1e-5})
        if not fitted.success:
            raise RuntimeError("bounded feature fit failed")
        frequency = float(fitted.x)
    background = float(np.median(density[side]))
    coefficient = projection(x, sample_rate_hz, frequency)
    fixed = projection(x, sample_rate_hz, center_hz)
    prominence = db_ratio(float(density[peak]), background)
    return {
        "fixed_frequency_hz": float(center_hz), "fitted_frequency_hz": frequency,
        "fitted_offset_hz": frequency - center_hz,
        "fft_bin_spacing_hz": df, "samples": int(x.size),
        "fixed_projection_power": abs(fixed) ** 2,
        "fitted_projection_power": abs(coefficient) ** 2,
        "band_power_plus_minus_2000_hz": float(np.sum(density[band]) * df),
        "median_adjacent_density": background,
        "peak_to_adjacent_median_db": prominence,
        "prominence_at_least_10_db": prominence is not None and prominence >= 10,
        "interpretation": "Descriptive fitted peak; adjacent spectrum is not an independently established noise reference",
    }


def joint_tone_line(samples, sample_rate_hz, tone_hz, line_hz):
    """Separate two fixed-frequency complex sinusoids by exact least squares.

    The line's predicted contribution to the single-tone projector is g*a_line.
    The power difference includes a coherent cross term; it is not a measured
    interference fraction or a bound on all broadband leakage.
    """
    x = _samples(samples, sample_rate_hz)
    if abs(tone_hz - line_hz) < sample_rate_hz / x.size:
        raise ValueError("features must be separated by at least one record FFT bin")
    b0 = projection(x, sample_rate_hz, tone_hz)
    b1 = projection(x, sample_rate_hz, line_hz)
    t = np.arange(x.size, dtype=np.float64) / sample_rate_hz
    g = np.mean(np.exp(2j * np.pi * (line_hz - tone_hz) * t))
    gram = np.array([[1, g], [g.conjugate(), 1]], dtype=np.complex128)
    a0, a1 = np.linalg.solve(gram, np.array([b0, b1]))
    leakage = g * a1
    original, adjusted = abs(b0) ** 2, float(abs(a0) ** 2)
    return {
        "tone_frequency_hz": float(tone_hz), "line_frequency_hz": float(line_hz),
        "single_tone_coefficient": [b0.real, b0.imag],
        "joint_tone_coefficient": [float(a0.real), float(a0.imag)],
        "joint_line_coefficient": [float(a1.real), float(a1.imag)],
        "single_tone_projection_power": original,
        "joint_tone_projection_power": adjusted,
        "signed_projection_power_change": adjusted - original,
        "joint_vs_single_power_change_db": db_ratio(adjusted, original),
        "modeled_line_leakage_to_tone_projection_power": float(abs(leakage) ** 2),
        "modeled_leakage_vs_single_tone_db": db_ratio(float(abs(leakage) ** 2), original),
        "projector_coupling_amplitude": float(abs(g)),
        "gram_condition_number": float(np.linalg.cond(gram)),
        "reconstruction_error": float(abs((a0 + leakage) - b0)),
    }
