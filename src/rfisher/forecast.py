"""DTV channel setup and integration boundaries for RadioFisher.

RadioFisher owns the BAO derivative, quadrature, and covariance integrands.
RFIsher selects the study inputs and adds the coherent residual's wedge edge
so the shared integration resolves its discontinuity.
"""
import numpy as np
import radiofisher as rf
from radiofisher import quadrature
from radiofisher.instrument import mode_limits

from . import inputs, residual
from .bands import Band

RADIAL_ORDER = 8
ANGULAR_ORDER = 16
STEP = 1e-7             # central-difference step for the BAO template [Mpc^-1]
K_RANGE = (1e-7, 1.0)   # integration range in k [Mpc^-1]


def prepare(band: Band, cosmo=None, expt=None, fns=None) -> dict:
    """Prepare this channel with the direct BAO derivative and unit DTV residual."""
    cosmo = inputs.cosmology() if cosmo is None else cosmo
    expt = inputs.experiment() if expt is None else expt
    fns = inputs.background(cosmo) if fns is None else fns
    c, e, Vfac, _, _ = rf.prepare_bin(
        band.z_min, band.z_max, cosmo, expt, fns, *K_RANGE,
        bao_derivative="direct", bao_step=STEP,
    )
    g = residual.geometry(c, e)
    e["P_res"] = residual.coherent_shelf(g)
    kfg, knl = mode_limits(c, e)
    return {"cosmo": c, "expt": e, "Vfac": Vfac, "geometry": g, "band": band,
            "kfg": kfg, "knl": knl, "nu": e["nu_line"] / (1 + c["z"]),
            "knots": np.genfromtxt(e["n(x)_file"])[:, 0]}


def radial_edges(p: dict) -> np.ndarray:
    """RadioFisher's spectral, instrumental, and mode-cut breakpoints."""
    return quadrature.radial_edges(
        p["cosmo"], p["expt"], p["knots"],
        kmin=K_RANGE[0], kmax=K_RANGE[1], bao_step=STEP,
    )


def angular_edges(k: float, p: dict) -> np.ndarray:
    """Add the DTV wedge edge to RadioFisher's angular breakpoints."""
    edges = quadrature.angular_edges(k, p["cosmo"], p["expt"], p["knots"])
    wedge = residual.wedge_mu(k, p["geometry"])
    return edges if wedge is None else np.unique(np.r_[edges, wedge])


def quadrature_segments(p: dict, radial_order: int, angular_order: int, *, edges=None):
    """Shared RadioFisher nodes with this study's residual boundary."""
    return quadrature.quadrature_segments(
        radial_edges(p) if edges is None else edges,
        lambda k: angular_edges(k, p), radial_order, angular_order,
    )


def integrate(p: dict, radial_order: int = RADIAL_ORDER, angular_order: int = ANGULAR_ORDER):
    """Integrate this channel using RadioFisher's shared weighted reduction."""
    return quadrature.integrate_segments(
        quadrature_segments(p, radial_order, angular_order),
        p["cosmo"], p["expt"], p["Vfac"],
    )


def channel_fisher(band: Band, **kwargs):
    """Fisher matrix (with the '_Pres' bias row) and parameter names for one channel."""
    orders = {key: kwargs.pop(key) for key in ("radial_order", "angular_order") if key in kwargs}
    p = prepare(band, **kwargs)
    F, names = integrate(p, **orders)
    return F, names, p
