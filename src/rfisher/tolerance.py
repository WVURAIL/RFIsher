"""Convert a channel's clean Fisher matrix and residual response into a tolerance.

The fitted parameters are the BAO amplitude A, the damping variance
s_NL = sigma_nl**2 (Mpc squared), the dilations alpha_perp and alpha_par,
f sigma_8, and b sigma_8. The other parameters are held at their fiducial
values. The fitted block is inverted to obtain the clean covariance C.
The extra '_Pres' column B gives the residual's projection onto each
parameter, so C B is the first-order bias for unit additive power in mK^2.

Next, the two dilations give the volume-averaged distance used by the
CHIME Overview:

    ln alpha_V = 2/3 ln alpha_perp + 1/3 ln alpha_par
    sigma_dv = sqrt(w C w), where w = (2/3, 1/3) on the dilations
    response_dv = (w . bias) / sigma_dv, per unit additive power
    a_tol = 1 / |response_dv|

At a_tol, the modeled bias equals one clean standard deviation. Since
alpha_V = D_V_fid / D_V, the physical distance shift has the opposite sign,
delta ln D_V / sigma_dv = -a * response_dv. Schema v3 stores the
ln(alpha_V) projection in bias_dv_per_unit_a.

target_tolerance gives the same tolerance for any linear combination of
fitted parameters. It also accepts the projection B from another Fisher
code in place of the '_Pres' column.
"""
import numpy as np
import radiofisher as rf

FITTED = ("A", "s_NL", "aperp", "apar", "fs8", "bs8")
DILATIONS = ("aperp", "apar")
DV_WEIGHTS = np.array([2 / 3, 1 / 3])
RESIDUAL = "_Pres"
TARGETS = {"dv": {"aperp": 2 / 3, "apar": 1 / 3}, "aperp": {"aperp": 1.0},
           "apar": {"apar": 1.0}, "fs8": {"fs8": 1.0}}


def target_tolerance(F: np.ndarray, names: list, weights, fitted=FITTED, *,
                     residual=RESIDUAL, bias_projection=None) -> dict:
    """Clean error, bias, response and tolerance of sum(weights[p] * p) over fitted parameters.

    weights is a name in TARGETS or a mapping of fitted parameter to
    coefficient. B comes from the residual column of F or, for another
    Fisher code, from bias_projection in the order of names.
    """
    fitted = tuple(fitted)
    weights = TARGETS[weights] if isinstance(weights, str) else dict(weights)
    if not weights:
        raise ValueError("the target needs at least one weighted parameter")
    unknown = set(weights) - set(fitted)
    if unknown:
        raise ValueError(f"target parameters {sorted(unknown)} are not fitted")
    result = rf.summarize_fisher(F, names, fitted, residual=residual, bias_projection=bias_projection)
    if result.bias is None:
        raise ValueError("the tolerance requires a residual bias projection")
    vector = np.array([float(weights.get(p, 0.0)) for p in fitted])
    target = result.project(vector, ("target",))
    sigma, bias = float(target.sigma[0]), float(target.bias[0])
    response = bias / sigma
    return {"weights": {p: float(w) for p, w in weights.items()}, "sigma": sigma,
            "bias_per_unit_a": bias, "response": response,
            "a_tol": float(1 / abs(response)) if response else float("inf"),
            "condition": result.condition}


def tolerance(F: np.ndarray, names: list) -> dict:
    """Clean D_V uncertainty, signed dilation projection, response and tolerance."""
    result = rf.summarize_fisher(F, names, FITTED, residual=RESIDUAL)
    if result.bias is None:
        raise ValueError("the DTV tolerance requires a residual bias projection")
    dilation_indices = [FITTED.index(p) for p in DILATIONS]
    dilation_projection = np.eye(len(FITTED))[dilation_indices]
    dilations = result.project(dilation_projection, DILATIONS)
    distance = result.project(DV_WEIGHTS @ dilation_projection, ("ln_alpha_V",))
    sigma_dv = float(distance.sigma[0])
    bias_ln_alpha_v = float(distance.bias[0])
    response_dv = bias_ln_alpha_v / sigma_dv
    return {"sigma_dv": sigma_dv, "bias_dv_per_unit_a": bias_ln_alpha_v, "response_dv": response_dv,
            "a_tol": float(1 / abs(response_dv)) if response_dv else float("inf"),
            "dilations": {"sigma": dilations.sigma.tolist(), "bias_per_unit_a": dilations.bias.tolist(),
                          "response": (dilations.bias / dilations.sigma).tolist(),
                          "covariance": dilations.covariance.tolist(),
                          "correlation": float(dilations.covariance[0, 1] / np.prod(dilations.sigma))},
            "condition": result.condition}
