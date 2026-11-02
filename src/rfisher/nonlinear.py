"""Fit a finite-amplitude BAO model to an expected covariance.

These checks complement the published linear tables. With the retained
RadioFisher derivative switches, the model is phenomenological, and only
the BAO feature shifts with the dilations. The full Alcock-Paczynski
transformation of the signal is not modeled. In the Fisher matrix, the
coordinate s_NL is the damping variance in Mpc squared.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from radiofisher import summarize_fisher
from scipy.optimize import minimize

from .tolerance import DV_WEIGHTS, FITTED

PARAMETERS = tuple(FITTED)
DILATION_FLAGS = {
    "alpha_volume": False,
    "alpha_rsd_angle": False,
    "alpha_rsd_shift": False,
    "alpha_bao_shift": True,
    "alpha_pk_shift": False,
}








def check_conventions(prepared):
    c, e = prepared["cosmo"], prepared["expt"]
    if any(e["use"].get(k) != v for k, v in DILATION_FLAGS.items()):
        raise ValueError("finite model supports only the declared BAO-shift dilation switches")
    if c["aperp"] != 1 or c["apar"] != 1:
        raise ValueError("the finite model requires unit fiducial dilations")
    if c["fbao"]._kind != "linear" or np.any(np.asarray(c["fbao"].fill_value) != 0):
        raise ValueError("finite model requires the saved linear BAO template with zero fill")
    return np.array(
        [c["A"], c["sigma_nl"] ** 2, 1.0, 1.0, c["f"] * c["D"] * c["sigma_8"], c["bHI"] * c["D"] * c["sigma_8"]]
    )


@dataclass
class FiniteBAOModel:
    k: np.ndarray
    mu: np.ndarray
    weight: np.ndarray
    signal_fraction: np.ndarray
    residual_fraction: np.ndarray
    derivatives: np.ndarray
    theta0: np.ndarray
    template_k: np.ndarray
    template_f: np.ndarray

    def __post_init__(self):
        self.mu2 = self.mu**2
        self.kmu2 = self.k**2 * self.mu2
        self.fid_wiggle = np.interp(self.k, self.template_k, self.template_f, left=0.0, right=0.0)
        self.fid_rsd = self.theta0[5] + self.theta0[4] * self.mu2
        self.template_slope = np.diff(self.template_f) / np.diff(self.template_k)
        self.fisher = np.zeros((6, 6))
        self.bias_row = np.zeros(6)
        # The sums are taken in blocks of 65536 modes, so refinement does not amplify the summation error.
        for begin in range(0, len(self.k), 65536):
            block = slice(begin, begin + 65536)
            d, w = self.derivatives[block], self.weight[block]
            self.fisher += (d.T * w) @ d
            self.bias_row += d.T @ (w * self.residual_fraction[block])
        result = summarize_fisher(self.fisher, PARAMETERS, PARAMETERS, bias_projection=self.bias_row)
        self.covariance = result.covariance
        self.scale = result.sigma
        self.linear_shift = result.bias
        distance = result.project(np.r_[0., 0., DV_WEIGHTS, 0., 0.], ("ln_alpha_V",))
        self.sigma_dv = float(distance.sigma[0])
        self.a_tol = self.sigma_dv / abs((2 * self.linear_shift[2] + self.linear_shift[3]) / 3)

    def domain(self):
        minimum = float(np.min(self.template_f))
        if minimum >= 0:
            raise ValueError("BAO template lacks the negative branch needed for the frozen amplitude domain")
        return [(0.0, (1.0 - 1e-8) / -minimum), (0.0, None), (0.5, 1.5), (0.5, 1.5), (0.0, None), (0.0, None)]

    def signal_ratio(self, theta, jacobian=False):
        """Cs(theta)/Cs(fid), with only the BAO template shifted by dilations."""
        A, s, ap, ar, fs, bs = np.asarray(theta, float)
        if not np.all(np.isfinite(theta)) or min(s, ap, ar, fs, bs) < 0 or ap == 0 or ar == 0:
            raise ValueError("invalid finite signal parameters")
        alpha = np.sqrt(ap * ap * (1 - self.mu2) + ar * ar * self.mu2)
        shifted = np.where(self.k > 0.03, self.k * alpha, self.k)
        wiggle = np.interp(shifted, self.template_k, self.template_f, left=0.0, right=0.0)
        bao = 1 + A * wiggle
        rsd = bs + fs * self.mu2
        if np.any(bao <= 0):
            raise ValueError("nonpositive finite signal factor")
        ratio = (
            (rsd / self.fid_rsd) ** 2
            * np.exp(-self.kmu2 * (s - self.theta0[1]))
            * bao
            / (1 + self.theta0[0] * self.fid_wiggle)
        )
        if not jacobian:
            return ratio
        ix = np.searchsorted(self.template_k, shifted, side="right") - 1
        valid = (ix >= 0) & (ix < len(self.template_slope)) & (self.k > 0.03)
        slope = np.zeros_like(shifted)
        slope[valid] = self.template_slope[ix[valid]]
        base = np.exp(-self.kmu2 * (s - self.theta0[1])) / self.fid_rsd**2 / (1 + self.theta0[0] * self.fid_wiggle)
        jac = np.array(
            [
                base * rsd**2 * wiggle,
                -self.kmu2 * ratio,
                base * rsd**2 * A * slope * self.k * ap * (1 - self.mu2) / alpha,
                base * rsd**2 * A * slope * self.k * ar * self.mu2 / alpha,
                base * 2 * rsd * self.mu2 * bao,
                base * 2 * rsd * bao,
            ]
        ).T
        return ratio, jac

    def objective(self, theta, strength):
        """Expected Gaussian NLL difference and its exact finite-model gradient."""
        if not np.isfinite(strength) or strength < 0:
            raise ValueError("residual strength must be finite and nonnegative")
        ratio, ratio_jac = self.signal_ratio(theta, jacobian=True)
        t = self.signal_fraction * (ratio - 1.0)
        eps = strength * self.residual_fraction
        if np.any(t <= -1) or not np.all(np.isfinite(t)):
            raise ValueError("nonpositive or nonfinite modeled covariance")
        # The clean divergence log1p(t) - t/(1+t) starts at second order, so a series is used for |t| < 1e-4.
        clean = np.log1p(t) - t / (1 + t)
        small = np.abs(t) < 1e-4
        z = t[small]
        clean[small] = z * z * (0.5 + z * (-2 / 3 + z * (0.75 + z * (-0.8 + z * 5 / 6))))
        value = np.sum(self.weight * (clean - eps * t / (1 + t)))
        common = self.weight * (t - eps) / (1 + t) ** 2 * self.signal_fraction
        gradient = ratio_jac.T @ common
        return float(value), gradient

    def curvature(self, theta, strength):
        """Local exact Hessian of the quadrature objective between template knots."""
        A, _s, ap, ar, fs, bs = np.asarray(theta, float)
        rsd = bs + fs * self.mu2
        if np.any(rsd <= 0):
            raise ValueError("curvature unavailable at the zero-signal boundary")
        alpha = np.sqrt(ap * ap * (1 - self.mu2) + ar * ar * self.mu2)
        shifted = np.where(self.k > 0.03, self.k * alpha, self.k)
        wiggle = np.interp(shifted, self.template_k, self.template_f, left=0.0, right=0.0)
        bao = 1 + A * wiggle
        ix = np.searchsorted(self.template_k, shifted, side="right") - 1
        valid = (ix >= 0) & (ix < len(self.template_slope)) & (self.k > 0.03)
        slope = np.zeros_like(shifted)
        slope[valid] = self.template_slope[ix[valid]]
        kp = self.k * ap * (1 - self.mu2) / alpha
        kr = self.k * ar * self.mu2 / alpha
        logj = np.array(
            [wiggle / bao, -self.kmu2, A * slope * kp / bao, A * slope * kr / bao, 2 * self.mu2 / rsd, 2 / rsd]
        ).T
        ratio = self.signal_ratio(theta)
        sf = self.signal_fraction * ratio
        t = self.signal_fraction * (ratio - 1)
        eps = strength * self.residual_fraction
        h = (t - eps) / (1 + t) ** 2
        hp = (1 - t + 2 * eps) / (1 + t) ** 3
        second = self.weight * h * sf
        H = (logj.T * (second + self.weight * hp * sf**2)) @ logj
        terms = {
            (0, 0): -((wiggle / bao) ** 2),
            (0, 2): slope * kp / bao**2,
            (0, 3): slope * kr / bao**2,
            (2, 2): A * slope / bao * self.k * ((1 - self.mu2) / alpha - ap**2 * (1 - self.mu2) ** 2 / alpha**3)
            - (A * slope * kp / bao) ** 2,
            (3, 3): A * slope / bao * self.k * (self.mu2 / alpha - ar**2 * self.mu2**2 / alpha**3)
            - (A * slope * kr / bao) ** 2,
            (2, 3): -A * slope / bao * self.k * ap * ar * (1 - self.mu2) * self.mu2 / alpha**3
            - A**2 * slope**2 * kp * kr / bao**2,
            (4, 4): -2 * self.mu2**2 / rsd**2,
            (4, 5): -2 * self.mu2 / rsd**2,
            (5, 5): -2 / rsd**2,
        }
        for (i, j), term in terms.items():
            change = float(second @ term)
            H[i, j] += change
            if i != j:
                H[j, i] += change
        return H

    def derivative_check(self, relative_step=1e-8):
        """Check all six derivatives in the metric defined by the clean Fisher matrix."""
        analytic = self.derivatives
        numeric = np.empty_like(analytic)
        for i in range(6):
            step = relative_step * max(abs(self.theta0[i]), 0.1)
            hi, lo = self.theta0.copy(), self.theta0.copy()
            hi[i] += step
            lo[i] -= step
            numeric[:, i] = self.signal_fraction * (self.signal_ratio(hi) - self.signal_ratio(lo)) / (2 * step)
        error = np.sqrt(
            np.sum(self.weight[:, None] * (numeric - analytic) ** 2, axis=0)
            / np.sum(self.weight[:, None] * analytic**2, axis=0)
        )
        _, exact = self.signal_ratio(self.theta0, jacobian=True)
        exact = self.signal_fraction[:, None] * exact
        exact_error = np.sqrt(
            np.sum(self.weight[:, None] * (exact - analytic) ** 2, axis=0)
            / np.sum(self.weight[:, None] * analytic**2, axis=0)
        )
        return {
            "parameters": list(PARAMETERS),
            "numeric_relative_l2": error.tolist(),
            "piecewise_gradient_relative_l2": exact_error.tolist(),
            "step": relative_step,
        }

    def fit(self, strength, start=None, maxiter=600):
        start = self.theta0.copy() if start is None else np.asarray(start, float)
        bounds = self.domain()
        scaled_bounds = [
            ((lo - self.theta0[i]) / self.scale[i], None if hi is None else (hi - self.theta0[i]) / self.scale[i])
            for i, (lo, hi) in enumerate(bounds)
        ]

        lower = np.array([lo for lo, _ in bounds])
        upper = np.array([np.inf if hi is None else hi for _, hi in bounds])

        def physical_theta(z):
            # Reconstructing an exact scaled bound can round just outside it.
            return np.clip(self.theta0 + self.scale * z, lower, upper)

        def evaluate(z):
            value, gradient = self.objective(physical_theta(z), strength)
            return value, gradient * self.scale

        z0 = (start - self.theta0) / self.scale
        for i, (lo, hi) in enumerate(scaled_bounds):
            z0[i] = np.clip(z0[i], lo + 1e-10, np.inf if hi is None else hi - 1e-10)
        fitted = minimize(
            evaluate,
            z0,
            method="L-BFGS-B",
            jac=True,
            bounds=scaled_bounds,
            options={"ftol": 1e-15, "gtol": 1e-9, "maxiter": maxiter, "maxls": 50},
        )
        theta = physical_theta(fitted.x)
        value, gradient = self.objective(theta, strength)
        hit = [
            PARAMETERS[i]
            for i, (lo, hi) in enumerate(bounds)
            if theta[i] - lo <= 1e-7 * max(1.0, abs(theta[i]))
            or (hi is not None and hi - theta[i] <= 1e-7 * max(1.0, abs(theta[i])))
        ]
        logdv = -(2 * np.log(theta[2]) + np.log(theta[3])) / 3
        return {
            "strength": float(strength),
            "theta": theta.tolist(),
            "shift": (theta - self.theta0).tolist(),
            "log_dv_shift": float(logdv),
            "fractional_dv_shift": float(np.expm1(logdv)),
            "objective": value,
            "optimizer_success": bool(fitted.success),
            "message": str(fitted.message),
            "iterations": int(fitted.nit),
            "evaluations": int(fitted.nfev),
            "active_bounds": hit,
            "scaled_gradient_max": float(np.max(np.abs(gradient * self.scale))),
            "gradient": gradient.tolist(),
            "fisher_metric_gradient_norm": float(
                np.linalg.norm(np.linalg.solve(np.linalg.cholesky(self.fisher), gradient))
            ),
            "shift_minus_fisher_in_sigma": ((theta - self.theta0 - strength * self.linear_shift) / self.scale).tolist(),
        }
