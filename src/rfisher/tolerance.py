"""Convert a channel's clean Fisher matrix and residual response into a tolerance.

The fitted parameters are the BAO amplitude A, damping variance
s_NL = sigma_nl**2 (Mpc squared), dilations alpha_perp and alpha_par,
f sigma_8, and b sigma_8. Hold the other parameters at their fiducial
values. Invert this fitted block to obtain the clean covariance C.
The extra '_Pres' column B gives the residual's projection onto each
parameter, so C B is the first-order bias for unit residual strength.

Next combine the two dilations into the volume-averaged distance used
by the CHIME Overview:

    ln alpha_V = 2/3 ln alpha_perp + 1/3 ln alpha_par
    sigma_dv = sqrt(w C w), where w = (2/3, 1/3) on the dilations
    response_dv = (w . bias) / sigma_dv, per unit strength
    a_tol = 1 / |response_dv|

At a_tol, the modeled bias equals one clean standard deviation. The sign
needs care: alpha_V = D_V_fid / D_V, so the physical distance shift is
delta ln D_V / sigma_dv = -a * response_dv. Schema v2 stores the
ln(alpha_V) projection in bias_dv_per_unit_a.
"""
import numpy as np

FITTED = ("A", "s_NL", "aperp", "apar", "fs8", "bs8")
DILATIONS = ("aperp", "apar")
DV_WEIGHTS = np.array([2 / 3, 1 / 3])
RESIDUAL = "_Pres"


def tolerance(F: np.ndarray, names: list) -> dict:
    """Clean D_V uncertainty, signed dilation projection, response and tolerance."""
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
    bias_ln_alpha_v = float(DV_WEIGHTS @ bias[dilation_indices])
    response_dv = bias_ln_alpha_v / sigma_dv
    return {"sigma_dv": sigma_dv, "bias_dv_per_unit_a": bias_ln_alpha_v, "response_dv": response_dv,
            "a_tol": float(1 / abs(response_dv)) if response_dv else float("inf"),
            "dilations": {"sigma": dilation_sigma.tolist(), "bias_per_unit_a": bias[dilation_indices].tolist(),
                          "response": (bias[dilation_indices] / dilation_sigma).tolist(), "covariance": dilation_covariance.tolist(),
                          "correlation": float(dilation_covariance[0, 1] / np.prod(dilation_sigma))},
            "condition": float(eigenvalues[-1] / eigenvalues[0])}
