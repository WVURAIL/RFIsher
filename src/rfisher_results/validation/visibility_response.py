"""Explicit visibility moments and a fixed, idealized science response.

Inputs are already masked 10-second visibilities in declared physical units.
No delay filter, calibration, telescope response, or masking bound is inferred.
Real/imaginary covariance is retained because selected data need not be proper
complex Gaussian. Quadratic means are exact from moments; their covariance
uses a Gaussian closure and must be checked by independent injections.
"""
from __future__ import annotations

import numpy as np


def _real(value, name):
    array = np.asarray(value)
    if np.iscomplexobj(array) or not np.isfinite(array).all():
        raise ValueError(f"{name} must be finite and real")
    return array.astype(float)


def _covariance(value, size, name, *, positive=False):
    cov = _real(value, name)
    if cov.shape != (size, size):
        raise ValueError(f"{name} has the wrong dimensions")
    scale = np.max(np.abs(cov), initial=0.)
    if not np.allclose(cov, cov.T, rtol=0., atol=1e-12 * scale):
        raise ValueError(f"{name} must be symmetric")
    eigenvalues = np.linalg.eigvalsh(cov)
    if eigenvalues.min() < -1e-12 * scale:
        raise ValueError(f"{name} must be positive semidefinite")
    if positive and eigenvalues.min() <= 1e-12 * scale:
        raise ValueError(f"{name} must be positive definite and well conditioned")
    return cov / 2 + cov.T / 2


def complex_moments_to_real(mean, covariance, pseudocovariance):
    """Return moments in [Re(v_0..v_n), Im(v_0..v_n)] order.

    C = E[(v-mu)(v-mu)^H] and P = E[(v-mu)(v-mu)^T]. P is required;
    callers may supply zero only when propriety is a justified assumption.
    Both matrices are centered moments, not uncentered second moments.
    """
    mu, cov, pseudo = (np.asarray(x, complex) for x in
                       (mean, covariance, pseudocovariance))
    if (mu.ndim != 1 or not mu.size or cov.shape != (mu.size, mu.size)
            or pseudo.shape != cov.shape
            or not all(np.isfinite(x).all() for x in (mu, cov, pseudo))):
        raise ValueError("invalid complex moment dimensions or values")
    scale = max(np.max(np.abs(cov)), np.max(np.abs(pseudo)))
    if not np.allclose(cov, cov.conj().T, rtol=0, atol=1e-12 * scale):
        raise ValueError("complex covariance must be Hermitian")
    if not np.allclose(pseudo, pseudo.T, rtol=0, atol=1e-12 * scale):
        raise ValueError("pseudocovariance must be symmetric")
    real_cov = .5 * np.block([
        [np.real(cov + pseudo), np.imag(pseudo - cov)],
        [np.imag(pseudo + cov), np.real(cov - pseudo)],
    ])
    real_cov = _covariance(real_cov, 2 * mu.size, "joint real/imaginary covariance")
    return np.r_[mu.real, mu.imag], real_cov


def quadratic_moments(mean, covariance, kernels):
    """Moments of fixed statistics q_a = x.T Q_a x for real Gaussian x.

    Kernels include all declared weighting and normalization. They must be
    fixed independently of this realization. Return separate coherent-mean
    and covariance contributions; the latter is not coherent mean power.
    Non-Gaussian selected data require measured fourth moments or validation
    of this closure. There is no finite-sample confidence interval here.
    """
    mu = _real(mean, "mean")
    if mu.ndim != 1 or not mu.size:
        raise ValueError("mean must be a nonempty vector")
    cov = _covariance(covariance, mu.size, "covariance")
    q = _real(kernels, "kernels")
    if q.ndim != 3 or q.shape[1:] != cov.shape or not q.shape[0]:
        raise ValueError("kernels must have shape (statistics, coordinates, coordinates)")
    for kernel in q:
        if not np.allclose(kernel, kernel.T, rtol=0,
                           atol=1e-12 * np.max(np.abs(kernel), initial=0.)):
            raise ValueError("quadratic kernels must be symmetric")
    covariance_term = np.einsum("aij,ji->a", q, cov)
    mean_term = np.einsum("i,aij,j->a", mu, q, mu)
    qc = q @ cov
    qm = q @ mu
    statistic_covariance = (2 * np.einsum("aij,bji->ab", qc, qc)
                            + 4 * qm @ cov @ qm.T)
    if not all(np.isfinite(x).all() for x in (covariance_term, mean_term,
                                               statistic_covariance, covariance_term + mean_term)):
        raise ValueError("quadratic moments overflowed; rescale the visibility units")
    return {"mean": covariance_term + mean_term,
            "coherent_mean_term": mean_term,
            "centered_covariance_term": covariance_term,
            "covariance": statistic_covariance}


def quadratic_contamination(clean_mean, clean_covariance, observed_mean,
                            observed_covariance, kernels):
    """Compare clean and contaminated ensembles under the same fixed kernels.

    The covariance difference need not be positive semidefinite: conditioning
    on a mask can alter thermal noise. Pass both complete conditional moments.
    Independent residual/noise assumptions are never supplied implicitly.
    """
    clean = quadratic_moments(clean_mean, clean_covariance, kernels)
    observed = quadratic_moments(observed_mean, observed_covariance, kernels)
    result = {"statistic_bias": observed["mean"] - clean["mean"],
            "coherent_mean_bias": (observed["coherent_mean_term"]
                                   - clean["coherent_mean_term"]),
            "centered_covariance_bias": (observed["centered_covariance_term"]
                                        - clean["centered_covariance_term"]),
            "clean_statistic_covariance": clean["covariance"],
            "observed_statistic_covariance": observed["covariance"]}
    if not all(np.isfinite(value).all() for value in result.values()):
        raise ValueError("contamination difference overflowed; rescale the visibility units")
    return result


def linear_parameter_response(jacobian, fit_covariance, statistic_bias,
                              observed_covariance, *, parameter_names):
    """Bias and sampling covariance of an unregularized linearized fit.

    J maps parameter changes to the expected science statistic. All nuisance
    columns (including growth) participate in the fit. The caller must supply
    the response appropriate to the same mask, support, units and exposure.
    This is a fixed idealized response at the visibility boundary, not a claim
    that downstream cleaning is part of the allowed mitigation method.
    """
    jac = _real(jacobian, "jacobian")
    if jac.ndim != 2 or not all(jac.shape):
        raise ValueError("jacobian must be a nonempty matrix")
    nstat, nparam = jac.shape
    if (len(parameter_names) != nparam or len(set(parameter_names)) != nparam
            or any(not isinstance(n, str) or not n.strip() for n in parameter_names)):
        raise ValueError("provide one distinct name for every fitted parameter")
    fit_cov = _covariance(fit_covariance, nstat, "fit covariance", positive=True)
    actual_cov = _covariance(observed_covariance, nstat, "observed covariance")
    bias = _real(statistic_bias, "statistic bias")
    if bias.shape != (nstat,):
        raise ValueError("statistic bias has the wrong dimensions")
    weighted_jac = np.linalg.solve(fit_cov, jac)
    fisher = jac.T @ weighted_jac
    _covariance(fisher, nparam, "Fisher matrix", positive=True)
    response = np.linalg.solve(fisher, weighted_jac.T)
    parameter_bias = response @ bias
    parameter_covariance = response @ actual_cov @ response.T
    formal_covariance = np.linalg.solve(fisher, np.eye(nparam))
    if not all(np.isfinite(x).all() for x in (response, parameter_bias, parameter_covariance,
                                               formal_covariance)):
        raise ValueError("parameter response overflowed; rescale the fit units")
    return {"parameter_names": tuple(parameter_names), "response": response,
            "bias": parameter_bias, "covariance": parameter_covariance,
            "fit_covariance": formal_covariance,
            "sigma": np.sqrt(np.maximum(0., np.diag(parameter_covariance)))}
