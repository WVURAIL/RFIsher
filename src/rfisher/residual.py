"""Flat additive DTV power in the same covariance units (mK^2) as C_S.

The unit template is one at every forecast mode. Its amplitude is a power,
not a voltage, a power-to-noise ratio, or an integrated total over grid nodes.
Quadrature weights supply the integration measure; refining the grid must not
renormalize the residual. The modeled first-order bias scales linearly with
the supplied power.
"""
import numpy as np

MODEL = "flat-additive-power-v1"
UNITS = "mK^2"

def unit_power(k, mu, cn, cs):
    """Unit additive covariance, independent of noise and quadrature density."""
    return np.ones(np.broadcast_shapes(np.shape(k), np.shape(mu), np.shape(cn), np.shape(cs)))


TEMPLATES = {"flat": unit_power}


def load_template(spec: str):
    """A template from TEMPLATES or written as "package.module:function", for the command line."""
    import importlib

    if spec in TEMPLATES:
        return TEMPLATES[spec]
    module, sep, name = spec.partition(":")
    if not sep or not module or not name:
        raise ValueError(f"template {spec!r} must be one of {sorted(TEMPLATES)} or package.module:function")
    template = getattr(importlib.import_module(module), name)
    if not callable(template):
        raise TypeError(f"{spec} is not a function")
    return template


def template_name(template) -> str:
    """The model name a table records for this template."""
    if template is unit_power:
        return MODEL
    return f"{template.__module__}:{template.__qualname__}"


NORMALIZATION = "flat-temperature-variance-v1"


def normalization(cosmo, expt):
    """Set a=(Tsys*x)^2/M using the analytic volume of supported modes.

    x is the retained shelf-to-background power ratio. Assigning Tsys*x to
    temperature and its squared amplitude to the supported modes defines
    the simple model; it is not an empirical sky calibration.
    """
    from radiofisher import baofisher as rf
    from radiofisher.instrument import mode_limits

    density = expt["n(x)"]
    knots, values = np.asarray(density.x), np.asarray(density.y)
    if np.any(values < 0) or not np.isfinite(values).all():
        raise ValueError("baseline density must be finite and nonnegative")
    kfg, knl = mode_limits(cosmo, expt)
    if not 0 <= kfg < knl:
        raise ValueError("normalization requires positive supported mode volume")
    nu = expt["nu_line"] / (1 + cosmo["z"])
    # The baseline table is piecewise linear and has no physical support
    # outside its knots. Its tiny extrapolation sentinel is not a baseline.
    transverse = np.minimum(2 * np.pi * nu * knots / cosmo["r"],
                            np.sqrt(knl**2 - kfg**2))
    left, right = transverse[:-1], transverse[1:]
    supported = ((values[:-1] > 0) | (values[1:] > 0)) & (right > left)
    lo, hi = left[supported], right[supported]
    integral = np.sum(((knl**2-lo**2)**1.5 - (knl**2-hi**2)**1.5)/3
                      - kfg*(hi**2-lo**2)/2)
    volume = cosmo["r"]**2 * cosmo["rnu"] * integral / (2 * np.pi**2)
    temperature = float(rf.Tsys_tot(cosmo["z"], expt))
    if not np.isfinite(volume) or volume <= 0:
        raise ValueError("normalization requires positive supported mode volume")
    if not np.isfinite(temperature) or temperature <= 0:
        raise ValueError("normalization requires positive system temperature")
    return {"model": NORMALIZATION, "mode_volume": float(volume),
            "temperature_mK": temperature, "power_scale": float(temperature**2 / volume),
            "relation": "a = power_scale * x**2"}
