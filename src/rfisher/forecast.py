"""One channel's Fisher matrix, with the residual's bias row.

RadioFisher sets up the bin (prepare_bin) and supplies the integrand of every
parameter at any (k, mu) (fisher_integrands). RFIsher integrates them itself:
Gauss-Legendre in k and mu, split at every place the integrand has a kink
(P(k) table knots, baseline-density knots, the foreground and nonlinear cuts,
and the residual's wedge edge), so the result is converged. RadioFisher's own
Simpson grid in fisher() is not accurate enough for the bias row.

The derivative of the BAO template is taken directly at each k
(central difference, step 1e-7 Mpc^-1, zero below 0.03 Mpc^-1) instead of
being interpolated from RadioFisher's k grid.
"""
import contextlib
import io
import itertools

import numpy as np
import radiofisher as rf
from numpy.polynomial.legendre import leggauss

from . import inputs, residual
from .bands import Band

RADIAL_ORDER = 8        # Gauss-Legendre nodes per k segment
ANGULAR_ORDER = 16      # Gauss-Legendre nodes per mu segment
STEP = 1e-7             # central-difference step for the BAO template [Mpc^-1]
K_RANGE = (1e-7, 1.0)   # integration range in k [Mpc^-1]


def prepare(band: Band, cosmo=None, expt=None, fns=None) -> dict:
    """RadioFisher's bin set-up for this channel, with the unit residual attached."""
    cosmo = inputs.cosmology() if cosmo is None else cosmo
    expt = inputs.experiment() if expt is None else expt
    fns = inputs.background(cosmo) if fns is None else fns
    c, e, Vfac, _, _ = rf.prepare_bin(band.z_min, band.z_max, cosmo, expt, fns, *K_RANGE)
    fbao = c["fbao"]

    def dfbao_dk(k):
        k = np.asarray(k)
        return np.where(k <= .03, 0., (fbao(k + STEP / 2) - fbao(k - STEP / 2)) / STEP)

    c["dfbao_dk"] = dfbao_dk
    g = residual.geometry(c, e)
    e["P_res"] = residual.coherent_shelf(g)
    return {"cosmo": c, "expt": e, "Vfac": Vfac, "geometry": g, "band": band,
                "kfg": 2 * np.pi * e["nu_line"] / (e["survey_dnutot"] * c["rnu"]) * e.get("kfg_fac", 1.),
                "knl": e["k_nl0"] * (1 + c["z"]) ** (2 / (2 + c["ns"])),
                "nu": e["nu_line"] / (1 + c["z"]),
                "knots": np.genfromtxt(e["n(x)_file"])[:, 0]}


def radial_edges(p: dict) -> np.ndarray:
    """Where the integrand in k has kinks: segment boundaries for the k integral."""
    c = p["cosmo"]
    template = np.asarray(c["fbao"].x)
    pk = np.asarray(c["pk_nobao"].x)
    h = STEP / 2
    active = template[(template + h >= .03) & (template - h <= 1.)]
    baseline = 2 * np.pi * p["nu"] * p["knots"] / c["r"]
    parts = [np.array([K_RANGE[0], .03, 1., p["knl"], p["kfg"]]), template, pk, active - h,
             active + h, baseline, np.sqrt(baseline ** 2 + p["kfg"] ** 2)]
    if p["expt"]["use"]["alpha_pk_shift"]:
        parts.extend([pk - 5e-8, pk + 5e-8])
    e = np.unique(np.concatenate(parts))
    return e[(e >= K_RANGE[0]) & (e <= K_RANGE[1])]


def angular_edges(k: float, p: dict) -> np.ndarray:
    """Where the integrand in mu has kinks at this k."""
    xratio = 2 * np.pi * p["nu"] * p["knots"] / (p["cosmo"]["r"] * k)
    xratio = xratio[(xratio > 0) & (xratio < 1)]
    mu = np.sqrt(np.maximum(0, 1 - xratio * xratio))
    edge = p["kfg"] / k
    e = np.unique(np.r_[0., 1., mu, edge if 0 < edge < 1 else []])
    mw = residual.wedge_mu(k, p["geometry"])
    return e if mw is None else np.unique(np.r_[e, mw])


def integrate(p: dict, radial_order: int = RADIAL_ORDER, angular_order: int = ANGULAR_ORDER):
    """F_ij = Vfac * 2 * Int k^2 d_i d_j dk dmu over mu in [0, 1] (the integrand is even)."""
    qk, wk = leggauss(radial_order)
    qu, wu = leggauss(angular_order)
    edges = radial_edges(p)
    total, names = None, None
    with contextlib.redirect_stdout(io.StringIO()):
        for left, right in itertools.pairwise(edges):
            for k, kw in zip((left + right) / 2 + (right - left) * .5 * qk, (right - left) * .5 * wk):
                e = angular_edges(k, p)
                w = np.diff(e)
                m = (e[:-1] + e[1:]) / 2
                mu = (m[:, None] + w[:, None] * .5 * qu).ravel()
                uw = (w[:, None] * .5 * wu).ravel()
                deriv, names = rf.fisher_integrands(np.array([k]), mu, p["cosmo"], p["expt"])
                D = np.asarray(deriv)[:, :, 0]
                v = 2 * k * k * kw * ((D * uw) @ D.T)
                total = v if total is None else total + v
    return p["Vfac"] * total, list(names)


def channel_fisher(band: Band, **kwargs):
    """Fisher matrix (with the '_Pres' bias row) and parameter names for one channel."""
    orders = {key: kwargs.pop(key) for key in ("radial_order", "angular_order") if key in kwargs}
    p = prepare(band, **kwargs)
    F, names = integrate(p, **orders)
    return F, names, p
