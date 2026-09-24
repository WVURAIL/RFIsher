import numpy as np
import pytest

from rfisher_results.validation.visibility_response import (
    complex_moments_to_real, linear_parameter_response,
    quadratic_contamination, quadratic_moments,
)


def test_improper_complex_moments_keep_real_imaginary_correlations():
    real_cov = np.array([[2., .4], [.4, .5]])
    mean, covariance = complex_moments_to_real([1+2j], [[2.5]], [[1.5+.8j]])
    np.testing.assert_allclose(mean, [1, 2])
    np.testing.assert_allclose(covariance, real_cov)
    with pytest.raises(ValueError, match="positive semidefinite"):
        complex_moments_to_real([0j], [[1]], [[2]])


def test_mean_and_covariance_contamination_are_not_interchangeable():
    kernels = np.array([np.eye(2), np.diag([1., -1.])])
    out = quadratic_contamination([0, 0], np.eye(2), [2, 0],
                                  np.diag([1., 2.]), kernels)
    np.testing.assert_allclose(out["coherent_mean_bias"], [4, 4])
    np.testing.assert_allclose(out["centered_covariance_bias"], [1, -1])
    np.testing.assert_allclose(out["statistic_bias"], [5, 3])
    assert out["observed_statistic_covariance"][0, 0] == 26


def test_quadratic_prediction_against_independent_gaussian_draws():
    rng = np.random.default_rng(14285)
    mu = np.array([.7, -.2, .5])
    base = np.array([[1., .1, .3], [.2, .8, -.1], [.3, 0., .6]])
    cov = base @ base.T
    kernels = np.array([np.eye(3), [[1., .2, 0.], [.2, -.5, .3], [0., .3, .2]]])
    x = rng.multivariate_normal(mu, cov, size=250000)
    q = np.einsum("ni,aij,nj->na", x, kernels, x)
    predicted = quadratic_moments(mu, cov, kernels)
    np.testing.assert_allclose(q.mean(0), predicted["mean"], atol=.02, rtol=0)
    np.testing.assert_allclose(np.cov(q.T), predicted["covariance"], rtol=.025, atol=.02)


def test_growth_is_fit_as_a_nuisance_without_a_separate_veto():
    jac = np.array([[1, 0, 1], [0, 1, 1], [0, 0, 1], [1, -1, .5]])
    truth = np.array([.02, -.03, .4])
    out = linear_parameter_response(jac, np.eye(4), jac @ truth,
                                    np.eye(4) * 2,
                                    parameter_names=["alpha_parallel", "alpha_perp", "growth"])
    np.testing.assert_allclose(out["bias"], truth, atol=1e-14)
    np.testing.assert_allclose(out["covariance"], out["fit_covariance"] * 2)
    with pytest.raises(ValueError, match="positive definite"):
        linear_parameter_response(np.ones((4, 2)), np.eye(4), np.zeros(4),
                                  np.eye(4), parameter_names=["a", "b"])


@pytest.mark.parametrize("value", [np.nan, np.inf, 1j])
def test_invalid_inputs_are_refused(value):
    with pytest.raises(ValueError):
        quadratic_moments([value], [[1]], [[[1]]])


def test_finite_inputs_cannot_silently_produce_infinite_moments():
    with np.errstate(over="ignore", invalid="ignore"):
        with pytest.raises(ValueError, match="overflowed"):
            quadratic_moments([1e308], [[1]], [[[1]]])


def test_contamination_difference_cannot_silently_overflow():
    with np.errstate(over="ignore", invalid="ignore"):
        with pytest.raises(ValueError, match="difference overflowed"):
            quadratic_contamination([1e154, 0], np.zeros((2, 2)), [0, 1e154],
                                    np.zeros((2, 2)), [np.diag([1., -1.])])
