"""From a channel's Fisher matrix to its tolerance.

The forecast fits six parameters: the BAO amplitude A, the damping sigma_NL,
the two dilations alpha_perp and alpha_par, f sigma_8 and b sigma_8. The rest
are held at their fiducial values. Inverting the fitted block gives the clean
covariance C. The '_Pres' column B holds the residual's projection onto each
parameter, so the first-order bias of a unit-strength residual is C B.

The two dilations are combined into the one number the CHIME Overview reports,
the volume-averaged distance D_V:

    ln alpha_V = 2/3 ln alpha_perp + 1/3 ln alpha_par

    sigma_dv    = sqrt(w C w),  w = (2/3, 1/3) on the dilations
    response_dv = (w . bias) / sigma_dv     per unit strength
    a_tol       = 1 / |response_dv|         the strength at which the bias equals sigma
"""
import sys
import types

import numpy as np

FITTED = ("A", "sigma_NL", "aperp", "apar", "fs8", "bs8")
DILATIONS = ("aperp", "apar")
DV_WEIGHTS = np.array([2 / 3, 1 / 3])
RESIDUAL = "_Pres"


def tolerance(F: np.ndarray, names: list) -> dict:
    """Clean D_V uncertainty, its bias per unit strength, the response and the tolerance."""
    names = list(names)
    keep = [names.index(p) for p in FITTED]
    if any(F[i, i] <= 0 for i in keep):
        raise ValueError("a fitted parameter has no information")
    Ff = F[np.ix_(keep, keep)]
    B = F[keep, names.index(RESIDUAL)]
    scale = np.sqrt(np.diag(Ff))
    S = Ff / np.outer(scale, scale)
    eig = np.linalg.eigvalsh(S)
    if eig[0] <= 0 or eig[-1] / eig[0] > 1e8:
        raise ValueError("invalid or ill-conditioned fitted Fisher matrix")
    v = np.linalg.solve(S, B / scale)
    C = np.linalg.solve(S, np.eye(len(FITTED))) / np.outer(scale, scale)
    bias = v / scale
    ix = [FITTED.index(p) for p in DILATIONS]
    cov = C[np.ix_(ix, ix)]
    sigma = np.sqrt(np.diag(cov))
    sigma_dv = float(np.sqrt(DV_WEIGHTS @ cov @ DV_WEIGHTS))
    bias_dv = float(DV_WEIGHTS @ bias[ix])
    response_dv = bias_dv / sigma_dv
    return {"sigma_dv": sigma_dv, "bias_dv_per_unit_a": bias_dv, "response_dv": response_dv,
            "a_tol": float(1 / abs(response_dv)) if response_dv else float("inf"),
            "dilations": {"sigma": sigma.tolist(), "bias_per_unit_a": bias[ix].tolist(),
                          "response": (bias[ix] / sigma).tolist(), "covariance": cov.tolist(),
                          "correlation": float(cov[0, 1] / np.prod(sigma))},
            "condition": float(eig[-1] / eig[0])}


class _CallableModule(types.ModuleType):
    """The package exports the function tolerance() under this module's name, so the
    module is callable: rfisher.tolerance(F, names) calls the function, and
    rfisher.tolerance.FITTED and the other constants stay reachable."""

    def __call__(self, F: np.ndarray, names: list) -> dict:
        return tolerance(F, names)


sys.modules[__name__].__class__ = _CallableModule
