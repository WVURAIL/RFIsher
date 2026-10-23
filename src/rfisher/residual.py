"""The assumed DTV residual-power template: a flat 6 MHz shelf.

The template assigns the same visibility on every baseline that measures a
Fourier cell, at the delay of its direction, so its power sits inside the
horizon wedge. Per Fourier mode, relative to RadioFisher's one-year noise
power C_N:

    dP / C_N = a * N_nu * N_meas(k_perp) * f_w(k_perp)   for |k_par| <= k_w(k_perp)
             = 0                                          otherwise

  a        residual strength: |V_DTV|^2 / sigma_V^2 on one baseline in one frame, times the assumed effective temporal gain
  N_nu     channels across the band (6 MHz / 0.39 MHz). A flat shelf puts all
           its power in one line-of-sight mode (Parseval)
  N_meas   baselines measuring the same Fourier cell, n(u) A_eff / lambda^2
           (RadioFisher's own baseline density and area per receiver)
  k_w      m k_perp + pi / L, with m = r (1+z) / r_nu the horizon slope and L
           the band's depth. Averaging the source delay over baseline
           orientations spreads the one mode over |k_par| <= k_w, so each mode
           there carries f_w = pi / (L k_w) of it

The template is the unit-strength residual; first-order bias is proportional to a.
It sets the support of the unmodeled residual, not a cut on retained sky modes.
It does not estimate gamma, temporal coherence, or post-processing suppression.
"""
import numpy as np
from radiofisher.instrument import collecting_area_m2, wavelength_m
from scipy.optimize import brentq


def geometry(cosmo: dict, expt: dict) -> dict:
    """The quantities the template needs, from a prepared RadioFisher bin."""
    z = cosmo["z"]
    nu = expt["nu_line"] / (1 + z)
    lam = wavelength_m(nu)
    aeff = collecting_area_m2(expt)
    return {"z": z, "r": cosmo["r"], "nu": nu, "lam": lam, "nx": expt["n(x)"], "acell": aeff / lam**2,
                "L": cosmo["rnu"] * expt["dnutot"] / expt["nu_line"],
                "n_nu": expt["dnutot"] / expt["dnu"], "m": cosmo["r"] * (1 + z) / cosmo["rnu"]}


def n_meas(kperp, g):
    """Baselines measuring one Fourier cell at k_perp."""
    return g["nx"](kperp * g["r"] / (2 * np.pi) / g["nu"]) / g["nu"] ** 2 * g["acell"]


def wedge_kpar(kperp, g):
    """k_w: the largest |k_par| the residual reaches at this k_perp."""
    return g["m"] * kperp + np.pi / g["L"]


def coherent_shelf(g: dict):
    """The unit-strength residual dP(k, mu, C_N, C_S) for RadioFisher's P_res hook."""
    def dP(k, u, cn, cs):
        k, u, cn = np.broadcast_arrays(k, u, cn)
        kpar = k * u
        kperp = k * np.sqrt(np.clip(1 - u * u, 0, 1))
        kw = wedge_kpar(kperp, g)
        return cn * g["n_nu"] * n_meas(kperp, g) * (np.pi / (g["L"] * kw)) * (np.abs(kpar) <= kw)
    return dP


def wedge_mu(k: float, g: dict):
    """mu at which |k_par| = k_w for this k (the template's edge), or None."""
    def f(mu):
        return k * mu - g["m"] * k * np.sqrt(1 - mu * mu) - np.pi / g["L"]
    if f(0.) >= 0 or f(1.) <= 0:
        return None
    return brentq(f, 0., 1., xtol=1e-14)
