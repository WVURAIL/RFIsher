"""Independent finite-sample checks for native voltage complex moments.

These checks establish arithmetic and support accounting. They do not establish
independent time samples, calibrated physical units, or packet-validity flags.
"""

import numpy as np
import pytest

from rfisher_results.validation.voltage_coherence import (
    decode_excess8,
    pair_moments,
    summarize_moments,
)


MOMENT_KEYS = ("count", "sum_x", "power_x", "cross")


def _manual_moments(samples, support=None):
    """Scalar pair/time-loop oracle, deliberately independent of matrix algebra."""
    samples = np.asarray(samples)
    if support is None:
        support = np.ones(samples.shape, dtype=bool)
    n_input = samples.shape[1]
    result = {
        "count": np.zeros((n_input, n_input), dtype=np.int64),
        "sum_x": np.zeros((n_input, n_input), dtype=np.complex128),
        "power_x": np.zeros((n_input, n_input), dtype=np.float64),
        "cross": np.zeros((n_input, n_input), dtype=np.complex128),
    }
    for i in range(n_input):
        for j in range(n_input):
            for t in range(samples.shape[0]):
                xi, xj = complex(samples[t, i]), complex(samples[t, j])
                if not (support[t, i] and support[t, j]):
                    continue
                if not (np.isfinite(xi) and np.isfinite(xj)):
                    continue
                result["count"][i, j] += 1
                result["sum_x"][i, j] += xi
                result["power_x"][i, j] += xi.real**2 + xi.imag**2
                result["cross"][i, j] += xi * xj.conjugate()
    return result


def test_all_256_codes_have_exact_excess8_values_and_native_orientation():
    packed = np.arange(256, dtype=np.uint8).reshape(16, 16)
    decoded = decode_excess8(packed)
    expected = np.empty((16, 16), dtype=np.complex128)
    for high in range(16):
        for low in range(16):
            expected[high, low] = complex(high - 8, low - 8)
    np.testing.assert_array_equal(decoded, expected)
    assert decoded.dtype == np.dtype(np.complex128)
    assert decoded[0, 0] == -8 - 8j
    assert decoded[8, 8] == 0j
    assert decoded[15, 15] == 7 + 7j
    np.testing.assert_array_equal(packed.ravel(), np.arange(256, dtype=np.uint8))


@pytest.mark.parametrize("dtype", [np.int8, np.int16, np.float64, np.bool_, object])
def test_decoder_refuses_implicit_dtype_reinterpretation(dtype):
    with pytest.raises((TypeError, ValueError)):
        decode_excess8(np.array([0, 1], dtype=dtype))


def test_decoder_preserves_empty_and_noncontiguous_shapes():
    empty = decode_excess8(np.empty((0, 3), dtype=np.uint8))
    assert empty.shape == (0, 3)
    source = np.arange(256, dtype=np.uint8).reshape(16, 16)
    np.testing.assert_array_equal(
        decode_excess8(source[::2, ::3]), decode_excess8(source)[::2, ::3]
    )


def test_visibility_uses_first_input_times_conjugate_second():
    x = np.array([1, 1j, -1, -1j], dtype=np.complex128)
    samples = np.column_stack((x, 2j * x))
    moments = pair_moments(samples)
    summary = summarize_moments(moments)
    assert moments["cross"][0, 1] == -8j
    assert moments["cross"][1, 0] == 8j
    assert summary["visibility"][0, 1] == -2j
    assert summary["coherency"][0, 1] == -1j
    assert summary["centered_coherency"][0, 1] == -1j
    np.testing.assert_array_equal(summary["mean_x"], 0)


def test_raw_second_moment_and_centered_covariance_are_distinct():
    x = np.array([1, 1j, -1, -1j], dtype=np.complex128)
    samples = np.column_stack((x + 2, 2j * x + 3j))
    result = summarize_moments(pair_moments(samples))
    assert result["visibility"][0, 1] == -8j
    assert result["covariance"][0, 1] == -2j
    assert result["mean_x"][0, 1] == 2
    assert result["mean_x"][1, 0] == 3j
    assert result["coherency"][0, 1] == pytest.approx(-8j / np.sqrt(65))
    assert result["centered_coherency"][0, 1] == -1j


def test_nonuniform_pair_support_uses_matched_autos_and_means():
    samples = np.array(
        [[1 + 1j, 2 - 1j, 10], [2, 20, 3j], [-1j, 4 + 1j, 5],
         [4, -2, 6 - 2j], [7j, 1 + 2j, 9]], dtype=np.complex128,
    )
    support = np.array(
        [[1, 1, 0], [1, 0, 1], [0, 1, 1], [1, 1, 1], [1, 0, 1]],
        dtype=bool,
    )
    expected = _manual_moments(samples, support)
    actual = pair_moments(samples, support)
    for name in MOMENT_KEYS:
        np.testing.assert_array_equal(actual[name], expected[name])
    assert actual["count"].dtype == np.dtype(np.int64)
    assert actual["sum_x"].dtype == np.dtype(np.complex128)
    assert actual["cross"].dtype == np.dtype(np.complex128)
    assert actual["power_x"].dtype == np.dtype(np.float64)
    # Pair (0,1) has only rows 0 and 3; neither full-input auto is admissible.
    assert actual["count"][0, 1] == 2
    assert actual["power_x"][0, 1] == 18
    assert actual["power_x"][1, 0] == 9
    assert actual["cross"][0, 1] == -7 + 3j
    summary = summarize_moments(actual)
    assert summary["visibility"][0, 1] == -3.5 + 1.5j
    assert summary["mean_x"][0, 1] == 2.5 + 0.5j
    assert summary["mean_x"][1, 0] == -0.5j
    assert summary["covariance"][0, 1] == -3.25 + 0.25j
    assert summary["coherency"][0, 1] == pytest.approx((-7 + 3j) / np.sqrt(162))
    assert summary["centered_coherency"][0, 1] == pytest.approx(
        (-3.25 + 0.25j) / np.sqrt(2.5 * 4.25)
    )


def test_nonfinite_values_are_removed_before_multiplication():
    samples = np.array(
        [[1, complex(np.nan, 0), 3], [complex(0, np.inf), 2, 4],
         [5, 6, complex(np.inf, np.nan)], [7, 8, 9]], dtype=np.complex128,
    )
    support = np.array([[1, 1, 1], [1, 1, 0], [1, 1, 1], [1, 0, 1]], dtype=bool)
    expected = _manual_moments(samples, support)
    with np.errstate(invalid="raise", divide="raise", over="raise"):
        actual = pair_moments(samples, support)
        summary = summarize_moments(actual)
    for name in MOMENT_KEYS:
        np.testing.assert_array_equal(actual[name], expected[name])
    assert np.all(np.isfinite(summary["visibility"][actual["count"] > 0]))
    assert np.all(np.isnan(summary["visibility"][actual["count"] == 0]))


@pytest.mark.parametrize("empty_kind", ["no_samples", "all_masked", "all_nonfinite"])
def test_no_pair_support_is_explicitly_unavailable(empty_kind):
    if empty_kind == "no_samples":
        samples = np.empty((0, 3), dtype=np.complex128)
        support = None
    elif empty_kind == "all_masked":
        samples = np.ones((4, 3), dtype=np.complex128)
        support = np.zeros(samples.shape, dtype=bool)
    else:
        samples = np.full((4, 3), complex(np.nan, np.inf), dtype=np.complex128)
        support = None
    actual = pair_moments(samples, support)
    for name in MOMENT_KEYS:
        np.testing.assert_array_equal(actual[name], 0)
    result = summarize_moments(actual)
    for name in ("visibility", "mean_x", "covariance", "coherency", "centered_coherency"):
        assert np.isnan(result[name]).all(), name


def test_zero_voltage_has_support_but_no_defined_normalized_coherence():
    samples = np.zeros((5, 2), dtype=np.complex128)
    moments = pair_moments(samples)
    result = summarize_moments(moments)
    np.testing.assert_array_equal(moments["count"], 5)
    np.testing.assert_array_equal(result["visibility"], 0)
    np.testing.assert_array_equal(result["covariance"], 0)
    assert np.isnan(result["coherency"]).all()
    assert np.isnan(result["centered_coherency"]).all()


def test_constant_nonzero_input_has_raw_coherence_but_no_centered_variance():
    samples = np.tile(np.array([1, -2j], dtype=np.complex128), (7, 1))
    result = summarize_moments(pair_moments(samples))
    np.testing.assert_array_equal(np.abs(result["coherency"]), 1)
    np.testing.assert_array_equal(result["covariance"], 0)
    assert np.isnan(result["centered_coherency"]).all()


def test_no_common_pair_support_does_not_borrow_single_input_counts():
    samples = np.ones((4, 2), dtype=np.complex128)
    support = np.array([[1, 0], [1, 0], [0, 1], [0, 1]], dtype=bool)
    moments = pair_moments(samples, support)
    np.testing.assert_array_equal(moments["count"], [[2, 0], [0, 2]])
    result = summarize_moments(moments)
    assert np.isnan(result["visibility"][0, 1])
    assert np.isnan(result["coherency"][0, 1])
    assert result["coherency"][0, 0] == 1


def test_native_integer_moments_pool_exactly_across_unequal_chunks():
    rng = np.random.default_rng(81367)
    packed = rng.integers(0, 256, size=(37, 5), dtype=np.uint8)
    samples = decode_excess8(packed)
    support = rng.random(samples.shape) > 0.2
    whole = pair_moments(samples, support)
    cuts = [(0, 0), (0, 3), (3, 20), (20, 36), (36, 37)]
    blocks = [pair_moments(samples[a:b], support[a:b]) for a, b in cuts]
    pooled = {name: sum(block[name] for block in blocks) for name in MOMENT_KEYS}
    for name in MOMENT_KEYS:
        np.testing.assert_array_equal(pooled[name], whole[name])
    whole_summary, pooled_summary = map(summarize_moments, (whole, pooled))
    for name in ("visibility", "mean_x", "covariance", "coherency", "centered_coherency"):
        np.testing.assert_array_equal(pooled_summary[name], whole_summary[name])
    # Averages of already normalized block estimates are not pooled moments.
    short = summarize_moments(blocks[1])["coherency"][0, 1]
    long = summarize_moments(blocks[2])["coherency"][0, 1]
    assert abs((short + long) / 2 - whole_summary["coherency"][0, 1]) > 1e-3


def test_gain_and_phase_transform_have_expected_complex_orientation():
    rng = np.random.default_rng(146)
    samples = rng.normal(size=(53, 4)) + 1j * rng.normal(size=(53, 4))
    support = rng.random(samples.shape) > 0.1
    original = summarize_moments(pair_moments(samples, support))
    gains = np.array([2, -3, 4j, -1 - 1j])
    changed = summarize_moments(pair_moments(samples * gains, support))
    multiplier = gains[:, None] * gains.conj()[None, :]
    phase = multiplier / np.abs(multiplier)
    for name in ("visibility", "covariance"):
        np.testing.assert_allclose(changed[name], original[name] * multiplier, atol=1e-12)
    for name in ("coherency", "centered_coherency"):
        np.testing.assert_allclose(changed[name], original[name] * phase, atol=1e-12)
        np.testing.assert_allclose(np.abs(changed[name]), np.abs(original[name]), atol=1e-12)


def test_pairwise_coherencies_are_hermitian_and_bounded_with_missing_support():
    rng = np.random.default_rng(219)
    samples = rng.normal(size=(31, 7)) + 1j * rng.normal(size=(31, 7))
    support = rng.random(samples.shape) > 0.25
    moments = pair_moments(samples, support)
    result = summarize_moments(moments)
    np.testing.assert_array_equal(moments["count"], moments["count"].T)
    np.testing.assert_allclose(moments["cross"], moments["cross"].conj().T, atol=1e-12)
    for name in ("visibility", "covariance", "coherency", "centered_coherency"):
        np.testing.assert_allclose(result[name], result[name].conj().T, atol=1e-12)
    for name in ("coherency", "centered_coherency"):
        assert np.nanmax(np.abs(result[name])) <= 1 + 1e-12
        np.testing.assert_allclose(np.diag(result[name]), 1, atol=1e-12)
    # Pairwise support differs: positive semidefiniteness is intentionally not asserted.


@pytest.mark.parametrize("shape", [(3,), (2, 3, 4)])
def test_samples_must_have_time_and_input_axes(shape):
    with pytest.raises((ValueError, TypeError)):
        pair_moments(np.ones(shape, dtype=np.complex128))


@pytest.mark.parametrize("support", [np.ones((3, 2), dtype=np.int8),
                                     np.ones((2, 3), dtype=bool),
                                     np.ones((3, 1), dtype=bool),
                                     np.ones(3, dtype=bool)])
def test_support_must_be_boolean_and_match_samples_exactly(support):
    with pytest.raises((ValueError, TypeError)):
        pair_moments(np.ones((3, 2), dtype=np.complex128), support)
