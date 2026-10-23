"""From a channel's Fisher matrix to its tolerance.

The forecast fits six parameters: the BAO amplitude A, the damping variance s_NL = sigma_nl**2 (Mpc squared),
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
import numpy as np

FITTED = ("A", "s_NL", "aperp", "apar", "fs8", "bs8")
DILATIONS = ("aperp", "apar")
DV_WEIGHTS = np.array([2 / 3, 1 / 3])
RESIDUAL = "_Pres"


def tolerance(F: np.ndarray, names: list) -> dict:
    """Clean D_V uncertainty, its bias per unit strength, the response and the tolerance."""
    names = list(names)
    keep = [names.index(p) for p in FITTED]
    if any(F[i, i] <= 0 for i in keep):
        raise ValueError("a fitted parameter has no information")
    fitted_fisher = F[np.ix_(keep, keep)]
    bias_projection = F[keep, names.index(RESIDUAL)]
    scale = np.sqrt(np.diag(fitted_fisher))
    scaled_fisher = fitted_fisher / np.outer(scale, scale)
    eigenvalues = np.linalg.eigvalsh(scaled_fisher)
    if eigenvalues[0] <= 0 or eigenvalues[-1] / eigenvalues[0] > 1e8:
        raise ValueError("invalid or ill-conditioned fitted Fisher matrix")
    scaled_bias = np.linalg.solve(scaled_fisher, bias_projection / scale)
    parameter_covariance = np.linalg.solve(scaled_fisher, np.eye(len(FITTED))) / np.outer(scale, scale)
    bias = scaled_bias / scale
    dilation_indices = [FITTED.index(p) for p in DILATIONS]
    dilation_covariance = parameter_covariance[np.ix_(dilation_indices, dilation_indices)]
    dilation_sigma = np.sqrt(np.diag(dilation_covariance))
    sigma_dv = float(np.sqrt(DV_WEIGHTS @ dilation_covariance @ DV_WEIGHTS))
    bias_dv = float(DV_WEIGHTS @ bias[dilation_indices])
    response_dv = bias_dv / sigma_dv
    return {"sigma_dv": sigma_dv, "bias_dv_per_unit_a": bias_dv, "response_dv": response_dv,
            "a_tol": float(1 / abs(response_dv)) if response_dv else float("inf"),
            "dilations": {"sigma": dilation_sigma.tolist(), "bias_per_unit_a": bias[dilation_indices].tolist(),
                          "response": (bias[dilation_indices] / dilation_sigma).tolist(), "covariance": dilation_covariance.tolist(),
                          "correlation": float(dilation_covariance[0, 1] / np.prod(dilation_sigma))},
            "condition": float(eigenvalues[-1] / eigenvalues[0])}
