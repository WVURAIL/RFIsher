"""Finite BAO-only expected-covariance fits, separate from published linear tables.

The retained RadioFisher derivative switches define a phenomenological BAO-only
model. They do not define the full Alcock-Paczynski signal model. The coordinate
named ``sigma_NL`` in the Fisher matrix is damping variance, in Mpc squared.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import itertools
import json
import platform
import uuid
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import scipy
from numpy.polynomial.legendre import leggauss
from scipy.optimize import minimize

from . import forecast
from .tolerance import FITTED

PARAMETERS = tuple(FITTED)
DILATION_FLAGS = {
    "alpha_volume": False,
    "alpha_rsd_angle": False,
    "alpha_rsd_shift": False,
    "alpha_bao_shift": True,
    "alpha_pk_shift": False,
}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def array_digest(values):
    h = hashlib.sha256()
    for key, value in sorted(values.items()):
        a = np.ascontiguousarray(value)
        h.update(json.dumps([key, a.dtype.str, a.shape]).encode())
        h.update(a.tobytes())
    return h.hexdigest()


def _settings(values, allowed_functions):
    def plain(value):
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, dict):
            return {k: plain(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [plain(v) for v in value]
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        raise ValueError("unsupported setting in finite-model cache identity")

    result = {}
    for key, value in values.items():
        if callable(value):
            if key not in allowed_functions:
                raise ValueError("unbound callable setting: " + key)
        else:
            result[key] = plain(value)
    return result


def _source_bindings():
    from radiofisher import baofisher as rf

    paths = [*Path(__file__).parent.glob("*.py"), *Path(rf.__file__).parent.glob("*.py")]
    return {p.parent.name + "/" + p.name: sha256(p) for p in sorted(paths)}


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
        # Bound dot-product length so refinement does not amplify summation error.
        for begin in range(0, len(self.k), 65536):
            block = slice(begin, begin + 65536)
            d, w = self.derivatives[block], self.weight[block]
            self.fisher += (d.T * w) @ d
            self.bias_row += d.T @ (w * self.residual_fraction[block])
        diagonal = np.sqrt(np.diag(self.fisher))
        scaled = self.fisher / np.outer(diagonal, diagonal)
        if np.linalg.cond(scaled) > 1e8 or np.linalg.eigvalsh(scaled)[0] <= 0:
            raise ValueError("ill-conditioned fitted Fisher matrix")
        self.covariance = np.linalg.solve(scaled, np.eye(6)) / np.outer(diagonal, diagonal)
        self.scale = np.sqrt(np.diag(self.covariance))
        self.linear_shift = self.covariance @ self.bias_row
        self.sigma_dv = float(np.sqrt(np.array([2 / 3, 1 / 3]) @ self.covariance[2:4, 2:4] @ np.array([2 / 3, 1 / 3])))
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
        # Stable clean divergence: log1p(t)-t/(1+t) starts at second order.
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
        """All-six derivative agreement in the clean Fisher metric."""
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

        def evaluate(z):
            theta = self.theta0 + self.scale * z
            value, gradient = self.objective(theta, strength)
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
        theta = self.theta0 + self.scale * fitted.x
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


def check_retained_modes(fisher, bias_row, full):
    """Check retention in the full quadrature's natural covariance scales."""
    scale = np.sqrt(np.diag(full))
    errors = {
        "fisher_max_normalized": float(np.max(np.abs((fisher - full[:6, :6]) / np.outer(scale[:6], scale[:6])))),
        "bias_max_normalized": float(np.max(np.abs((bias_row - full[:6, 6]) / (scale[:6] * scale[6])))),
        "tolerance": 1e-12,
    }
    if (
        not np.all(np.isfinite(list(errors.values())))
        or max(errors["fisher_max_normalized"], errors["bias_max_normalized"]) > errors["tolerance"]
    ):
        raise ValueError("discarding infinite-noise modes changes the Fisher matrix or bias row")
    return errors


def build_model(prepared, cache_dir, radial_order=8, angular_order=16, chunk_segments=64):
    """Reuse the forecast quadrature, checkpointing independent radial segments."""
    from radiofisher import baofisher as rf

    theta0 = check_conventions(prepared)
    c, e = prepared["cosmo"], prepared["expt"]
    pres = e.get("P_res")
    if (
        getattr(pres, "__module__", None) != "rfisher.residual"
        or getattr(pres, "__qualname__", None) != "coherent_shelf.<locals>.dP"
        or len(pres.__closure__ or ()) != 1
        or pres.__closure__[0].cell_contents is not prepared["geometry"]
        or prepared["geometry"]["nx"] is not e["n(x)"]
    ):
        raise ValueError("finite check requires the bound standard coherent-shelf residual")
    df = c["dfbao_dk"]
    if (
        getattr(df, "__module__", None) != "rfisher.forecast"
        or getattr(df, "__qualname__", None) != "prepare.<locals>.dfbao_dk"
        or len(df.__closure__ or ()) != 1
        or df.__closure__[0].cell_contents is not c["fbao"]
    ):
        raise ValueError("finite check requires the matched forecast derivative hook")
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    edges = forecast.radial_edges(prepared)
    qk, wk = leggauss(radial_order)
    qu, wu = leggauss(angular_order)
    identity = {
        "channel": prepared["band"].channel,
        "radial_order": radial_order,
        "angular_order": angular_order,
        "chunk_segments": chunk_segments,
        "source_sha256": sha256(__file__),
        "theta0": theta0.tolist(),
        "template_sha256": array_digest({"x": c["fbao"].x, "y": c["fbao"].y}),
        "pk_sha256": array_digest({"x": c["pk_nobao"].x, "y": c["pk_nobao"].y}),
        "baseline_sha256": sha256(e["n(x)_file"]),
        "radial_edges_sha256": array_digest({"edges": edges}),
        "use": e["use"],
        "z": c["z"],
        "Tb": c["Tb"],
        "r": c["r"],
        "rnu": c["rnu"],
        "Vfac": prepared["Vfac"],
        "thermal": {"ttot": e["ttot"], "Tsys": float(rf.Tsys_tot(c["z"], e)), "epsilon_fg": e["epsilon_fg"]},
        "sources": _source_bindings(),
        "runtime": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__},
        "cosmo_settings": _settings({k: v for k, v in c.items() if k != "btot"}, {"fbao", "pk_nobao", "dfbao_dk"}),
        "experiment_settings": _settings(e, {"n(x)", "Tsys_tot(z)", "P_res"}),
        "residual_geometry": _settings(prepared["geometry"], {"nx"}),
        "interpolation": {
            name: {
                "kind": value._kind,
                "fill": np.asarray(value.fill_value).tolist(),
                "bounds_error": value.bounds_error,
            }
            for name, value in [("fbao", c["fbao"]), ("pk_nobao", c["pk_nobao"]), ("nx", e["n(x)"])]
        },
        "baseline_function_sha256": array_digest({"x": e["n(x)"].x, "y": e["n(x)"].y}),
        "angular_knots_sha256": array_digest({"knots": prepared["knots"]}),
    }
    identity = _settings(identity, set())
    identity_path = cache_dir / "identity.json"
    if identity_path.exists():
        if json.loads(identity_path.read_text()) != identity:
            raise ValueError("quadrature cache identity differs")
    else:
        identity_path.write_text(json.dumps(identity, indent=2) + "\n")
    cache_identity_hash = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    parts, full = [], np.zeros((7, 7))
    for begin in range(0, len(edges) - 1, chunk_segments):
        path = cache_dir / f"{begin:05d}.npz"
        if path.exists():
            with np.load(path, allow_pickle=False) as z:
                record = {k: z[k] for k in z.files}
            digest = str(record.pop("sha256"))
            if digest != array_digest(record):
                raise ValueError("quadrature checkpoint payload mismatch")
            if (
                str(record["cache_identity"]) != cache_identity_hash
                or int(record["begin"]) != begin
                or int(record["end"]) != min(begin + chunk_segments, len(edges) - 1)
            ):
                raise ValueError("quadrature checkpoint identity/segment mismatch")
        else:
            rows, total = [], np.zeros((7, 7))
            with contextlib.redirect_stdout(io.StringIO()):
                for left, right in itertools.pairwise(edges[begin : min(begin + chunk_segments + 1, len(edges))]):
                    for k, kw in zip((left + right) / 2 + (right - left) / 2 * qk, (right - left) / 2 * wk):
                        a = forecast.angular_edges(k, prepared)
                        width = np.diff(a)
                        mid = (a[:-1] + a[1:]) / 2
                        mu = (mid[:, None] + width[:, None] / 2 * qu).ravel()
                        weight = prepared["Vfac"] * 2 * k * k * kw * (width[:, None] / 2 * wu).ravel()
                        derivs, names = rf.fisher_integrands(np.array([k]), mu, c, e)
                        indices = [names.index(name) for name in [*PARAMETERS, "_Pres"]]
                        d = np.asarray(derivs)[indices, :, 0].T
                        total += (d.T * weight) @ d
                        q = c["r"] * k * np.sqrt(1 - mu * mu)
                        y = c["rnu"] * k * mu
                        cs = rf.Csignal(q, y, c, e)
                        cn = rf.Cnoise(q, y, c, e)
                        cf = rf.Cfg(q, y, c, e)
                        active = cn < 1e100
                        if active.any():
                            rows.append(
                                np.column_stack(
                                    [
                                        np.full(active.sum(), k),
                                        mu[active],
                                        weight[active],
                                        (cs / (cs + cn + cf))[active],
                                        d[active, 6],
                                        d[active, :6],
                                    ]
                                )
                            )
            record = {
                "rows": np.concatenate(rows) if rows else np.empty((0, 11)),
                "full_fisher": total,
                "cache_identity": np.array(cache_identity_hash),
                "begin": np.array(begin),
                "end": np.array(min(begin + chunk_segments, len(edges) - 1)),
            }
            temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
            with temporary.open("xb") as f:
                np.savez_compressed(f, **record, sha256=array_digest(record))
            temporary.replace(path)
        full += record["full_fisher"]
        parts.append(record["rows"])
    data = np.concatenate(parts)
    model = FiniteBAOModel(
        data[:, 0],
        data[:, 1],
        data[:, 2],
        data[:, 3],
        data[:, 4],
        data[:, 5:],
        theta0,
        np.asarray(c["fbao"].x),
        np.asarray(c["fbao"].y),
    )
    model.retention_check = check_retained_modes(model.fisher, model.bias_row, full)
    return model, identity
