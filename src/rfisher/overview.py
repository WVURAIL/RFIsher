"""The CHIME Overview forecast, reproduced: sigma(D_V)/D_V per bin for one clean year.

As the Overview's scripts do it (S. Foreman, RadioFisher chime2021/full_experiment.py
and plot_dv_forecasts.py): RadioFisher's own fisher() for each bin with no residual;
per bin the BAO amplitude A, b sigma_8, f sigma_8 and the two dilations are free,
sigma_NL is shared by all bins, and everything else is held at the fiducial; the
dilations are combined into D_V. Run on the Overview's 15 redshift bins it
reproduces the published forecast; run on the 6 MHz channels it is the clean
reference the tolerance table starts from.
"""
import contextlib
import io
import itertools
import os
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import radiofisher as rf

from . import inputs
from .bands import NU21_MHZ, channels
from .tolerance import DV_WEIGHTS

# The Overview's redshift bins (Amiri et al. 2022, Table 2)
OVERVIEW_Z_EDGES = (0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.04, 2.20, 2.355, 2.51)
PER_BIN = ("A", "bs8", "fs8", "aperp", "apar")
SHARED = ("sigma_NL",)


def overview_bins() -> list:
    return list(itertools.pairwise(OVERVIEW_Z_EDGES))


def channel_bins() -> list:
    return [(b.z_min, b.z_max) for b in channels()]


def bin_fisher(edges):
    """RadioFisher's clean Fisher matrix for one bin, as the Overview computed it."""
    zmin, zmax = edges
    cosmo = inputs.cosmology()
    with contextlib.redirect_stdout(io.StringIO()):
        F, names = rf.fisher(zmin, zmax, cosmo, inputs.experiment(), inputs.background(cosmo))
    return F, list(names)


def combine(matrices: list, names: list) -> dict:
    """Per-bin sigma(D_V)/D_V and sigma(f sigma_8) from the combined matrix."""
    n = len(matrices)
    per = [names.index(p) for p in PER_BIN]
    shared = [names.index(p) for p in SHARED]
    size = n * len(PER_BIN) + len(SHARED)
    F = np.zeros((size, size))
    for i, Fi in enumerate(matrices):
        rows = list(range(i * len(PER_BIN), (i + 1) * len(PER_BIN))) + list(range(size - len(SHARED), size))
        F[np.ix_(rows, rows)] += Fi[np.ix_(per + shared, per + shared)]
    C = np.linalg.inv(F)
    sigma_dv, sigma_fs8 = [], []
    for i in range(n):
        a = i * len(PER_BIN) + PER_BIN.index("aperp")
        b = i * len(PER_BIN) + PER_BIN.index("apar")
        cov = C[np.ix_([a, b], [a, b])]
        sigma_dv.append(float(np.sqrt(DV_WEIGHTS @ cov @ DV_WEIGHTS)))
        k = i * len(PER_BIN) + PER_BIN.index("fs8")
        sigma_fs8.append(float(np.sqrt(C[k, k])))
    return {"sigma_dv": sigma_dv, "sigma_fs8": sigma_fs8}


def forecast(bins: list, workers: int | None = None) -> dict:
    """The Overview forecast over ``bins`` (a list of (z_min, z_max))."""
    workers = workers or min(len(bins), os.cpu_count() or 1)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(bin_fisher, bins))
    names = results[0][1]
    out = combine([F for F, _ in results], names)
    out["bins"] = [{"z_min": lo, "z_max": hi, "z_center": 0.5 * (lo + hi),
                    "nu_low_mhz": NU21_MHZ / (1 + hi), "nu_high_mhz": NU21_MHZ / (1 + lo)} for lo, hi in bins]
    return out


def reference(workers: int | None = None) -> dict:
    """Both binnings: the Overview's 15 bins (the reproduction) and the 6 MHz channels."""
    bands = channels()
    dtv = forecast(channel_bins(), workers)
    for row, b in zip(dtv["bins"], bands):
        row["channel"] = b.channel
    return {"overview_bins": forecast(overview_bins(), workers), "channels": dtv,
            "method": __doc__.split("\n\n")[1].replace("\n", " ")}
