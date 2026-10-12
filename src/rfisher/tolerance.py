"""From a channel's Fisher matrix to its tolerance.

The forecast fits six parameters: the BAO amplitude A, the damping sigma_NL,
the two dilations alpha_perp and alpha_par, f sigma_8 and b sigma_8. The rest
are held at their fiducial values. Inverting the fitted block gives the clean
covariance C. The '_Pres' column B holds the residual's projection onto each
parameter, so the first-order bias of a unit-strength residual is C B.

    response_i = bias_i / sigma_i      per unit strength, for alpha_perp, alpha_par
    a_tol      = 1 / max |response_i|  the strength at which the larger bias equals sigma
"""
import numpy as np

FITTED = ("A", "sigma_NL", "aperp", "apar", "fs8", "bs8")
DILATIONS = ("aperp", "apar")
RESIDUAL = "_Pres"


def tolerance(F: np.ndarray, names: list) -> dict:
    """Clean dilation uncertainties, bias per unit strength, response and tolerance."""
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
    response = bias[ix] / sigma
    binding = int(np.argmax(np.abs(response)))
    return {"sigma": sigma.tolist(), "bias_per_unit_a": bias[ix].tolist(),
                "response": response.tolist(), "a_tol": float(1 / np.abs(response).max()),
                "binding": DILATIONS[binding], "correlation": float(cov[0, 1] / np.prod(sigma)),
                "dilation_covariance": cov.tolist(), "condition": float(eig[-1] / eig[0])}
