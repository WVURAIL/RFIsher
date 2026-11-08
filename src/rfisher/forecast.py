"""DTV channel setup and integration boundaries for RadioFisher.

RadioFisher owns the BAO derivative, quadrature, and covariance integrands.
RFIsher selects the study inputs and attaches the residual template, by
default a flat unit power. A template is a function f(k, mu, cn, cs) that
returns the residual power in mK^2 at each mode. A template with a sharp
edge in k or mu needs that edge in the quadrature (quadrature_segments).
"""
import numpy as np
import radiofisher as rf
from radiofisher import quadrature

from . import inputs, residual
from .bands import Band

RADIAL_ORDER = 8
ANGULAR_ORDER = 16
STEP = 1e-7             # central-difference step for the BAO template [Mpc^-1]
K_RANGE = (1e-7, 1.0)   # integration range in k [Mpc^-1]


def prepare(band: Band, cosmo=None, expt=None, fns=None, template=residual.unit_power) -> dict:
    """Prepare this channel with the direct BAO derivative and a residual template."""
    if not callable(template):
        raise TypeError("the residual template must be a function f(k, mu, cn, cs)")
    cosmo = inputs.cosmology() if cosmo is None else cosmo
    expt = inputs.experiment() if expt is None else expt
    fns = inputs.background(cosmo) if fns is None else fns
    c, e, Vfac, _, _ = rf.prepare_bin(
        band.z_min, band.z_max, cosmo, expt, fns, *K_RANGE,
        bao_derivative="direct", bao_step=STEP,
    )
    e["P_res"] = template
    return {"cosmo": c, "expt": e, "Vfac": Vfac, "band": band,
            "knots": np.genfromtxt(e["n(x)_file"])[:, 0]}


def radial_edges(p: dict) -> np.ndarray:
    """RadioFisher's spectral, instrumental, and mode-cut breakpoints."""
    return quadrature.radial_edges(
        p["cosmo"], p["expt"], p["knots"],
        kmin=K_RANGE[0], kmax=K_RANGE[1], bao_step=STEP,
    )


def angular_edges(k: float, p: dict) -> np.ndarray:
    """Instrument and foreground breakpoints of the clean forecast."""
    return quadrature.angular_edges(k, p["cosmo"], p["expt"], p["knots"])


def quadrature_segments(p: dict, radial_order: int, angular_order: int, *, edges=None):
    """Shared RadioFisher quadrature nodes and integration weights."""
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


def radiofisher(band: Band, template=residual.unit_power, telescope: str = inputs.DEFAULT_TELESCOPE) -> dict:
    """The RadioFisher backend: F, its names and the bin details a table row records.

    Another backend is any function of (band, template, telescope) that
    returns F with a '_Pres' row and column, names and z_center. Its
    normalization may be None.
    """
    F, names, p = channel_fisher(band, expt=inputs.experiment(telescope=telescope), template=template)
    return {"F": F, "names": names, "z_center": float(p["cosmo"]["z"]),
            "normalization": (residual.normalization(p["cosmo"], p["expt"])
                              if template is residual.unit_power else None)}


BACKENDS = {"radiofisher": radiofisher}
DEFAULT_BACKEND = "radiofisher"
