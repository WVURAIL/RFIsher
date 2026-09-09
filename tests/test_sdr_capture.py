"""Finite-record arithmetic checks; these do not qualify an RF path."""
import numpy as np
import pytest

from rfisher_results.validation.sdr_capture import (
    db_ratio, hann_periodogram, joint_tone_line, narrow_feature, projection,
)


def test_projection_preserves_complex_amplitude_and_frequency_sign():
    rate, n, f = 2000000., 20000, 100000.
    amplitude = 0.2 - 0.3j
    x = amplitude * np.exp(2j * np.pi * f * np.arange(n) / rate)
    assert projection(x, rate, f) == pytest.approx(amplitude, abs=1e-13)
    assert abs(projection(x, rate, -f)) < 1e-12


def test_hann_density_has_exact_weighted_parseval_normalization():
    rng = np.random.default_rng(86)
    x = rng.normal(size=2001) + 1j * rng.normal(size=2001)
    rate = 2000000.
    f, density = hann_periodogram(x, rate)
    w = np.hanning(x.size)
    expected = np.sum(np.abs(x * w) ** 2) / np.sum(w ** 2)
    assert np.sum(density) * rate / len(x) == pytest.approx(expected, rel=1e-13)
    assert np.all(np.diff(f) > 0)
    assert density.min() >= 0


def test_joint_fit_recovers_tone_and_line_with_nonorthogonal_windows():
    rate, n = 2000000., 12789
    t = np.arange(n) / rate
    a0, a1 = 0.007 + 0.003j, 0.23 - 0.11j
    f0, f1 = 100000., 309947.25
    x = a0 * np.exp(2j * np.pi * f0 * t) + a1 * np.exp(2j * np.pi * f1 * t)
    result = joint_tone_line(x, rate, f0, f1)
    assert complex(*result['joint_tone_coefficient']) == pytest.approx(a0, abs=1e-12)
    assert complex(*result['joint_line_coefficient']) == pytest.approx(a1, abs=1e-12)
    assert result['reconstruction_error'] < 1e-15
    assert result['single_tone_projection_power'] != pytest.approx(abs(a0)**2, rel=1e-4)
    # An independently evaluated finite geometric series predicts the leakage.
    z = np.exp(2j * np.pi * (f1 - f0) / rate)
    geometric = (1 - z**n) / (n * (1 - z))
    assert result['modeled_line_leakage_to_tone_projection_power'] == pytest.approx(
        abs(a1 * geometric)**2, rel=1e-9)


def test_orthogonal_tone_and_line_need_no_projection_adjustment():
    rate, n = 2000000., 60000
    t = np.arange(n) / rate
    x = .01 * np.exp(2j*np.pi*100000*t) + .2j * np.exp(2j*np.pi*309900*t)
    result = joint_tone_line(x, rate, 100000, 309900)
    assert abs(result['joint_vs_single_power_change_db']) < 1e-9
    assert result['modeled_line_leakage_to_tone_projection_power'] < 1e-24


def test_fitted_peak_resolves_known_between_bin_tone_without_power_claim():
    rate, n, freq = 2000000., 10000, 100073.25
    x = .1 * np.exp(2j*np.pi*freq*np.arange(n)/rate)
    result = narrow_feature(x, rate, 100000.)
    assert result['fitted_frequency_hz'] == pytest.approx(freq, abs=.02)
    assert result['fft_bin_spacing_hz'] == 200
    assert result['fitted_projection_power'] == pytest.approx(.01, rel=1e-7)
    assert result['band_power_plus_minus_2000_hz'] == pytest.approx(.01, rel=1e-6)


def test_zero_record_returns_zero_powers_without_invented_decibels():
    x = np.zeros(10000, dtype=complex)
    result = narrow_feature(x, 2000000., 100000.)
    assert result['fitted_projection_power'] == 0
    assert result['peak_to_adjacent_median_db'] is None
    joint = joint_tone_line(x, 2000000., 100000., 309900.)
    assert joint['joint_vs_single_power_change_db'] is None
    assert joint['single_tone_projection_power'] == 0


@pytest.mark.parametrize('samples', [np.ones(5, dtype=complex), np.ones((10, 1), dtype=complex),
                                   np.ones(10), np.full(10, np.nan + 0j)])
def test_malformed_or_nonfinite_samples_are_refused(samples):
    with pytest.raises(ValueError):
        projection(samples, 2000000., 100000.)


@pytest.mark.parametrize('rate', [0, -1, np.inf, np.nan])
def test_bad_rate_is_refused(rate):
    with pytest.raises(ValueError):
        hann_periodogram(np.ones(32, dtype=complex), rate)


def test_aliasing_and_near_singular_joint_design_are_refused():
    x = np.ones(10000, dtype=complex)
    with pytest.raises(ValueError):
        projection(x, 2000000., 1000000.)
    with pytest.raises(ValueError):
        joint_tone_line(x, 2000000., 100000., 100001.)
    with pytest.raises(ValueError):
        narrow_feature(x, 2000000., 999999.)


def test_decibel_ratios_do_not_clip_nonpositive_power():
    assert db_ratio(0, 1) is None
    assert db_ratio(1, 0) is None
    assert db_ratio(-1, 1) is None
    assert db_ratio(100, 1) == 20
