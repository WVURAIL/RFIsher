"""The CHIME Overview forecast, reproduced: sigma(D_V)/D_V per bin for one clean year.

As the Overview's scripts do it (S. Foreman, RadioFisher chime2021/full_experiment.py
and plot_dv_forecasts.py): RadioFisher's own fisher() for each bin with no residual;
per bin the BAO amplitude A, b sigma_8, f sigma_8 and the two dilations are free,
s_NL is shared by all bins, and everything else is held at the fiducial; the
dilations are combined into D_V. Every baseline counts, as in the Overview (RadioFisher's
as-built density), so this reference is on all baselines while the table is not. Run on the Overview's 15 redshift bins it
reproduces the published forecast; run on the 6 MHz channels it is the clean
reference the tolerance table starts from.
"""
import itertools
import os
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import radiofisher as rf

from . import inputs
from .bands import NU21_MHZ, channels
from .tolerance import DV_WEIGHTS

# The Overview's redshift bins (CHIME Collaboration 2022, Table 2)
OVERVIEW_Z_EDGES = (0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.04, 2.20, 2.355, 2.51)
OVERVIEW_COSMOLOGY = "planck2018"   # the Overview's fiducial, so the reproduction can be checked
PER_BIN = ("A", "bs8", "fs8", "aperp", "apar")
SHARED = ("s_NL",)


def overview_bins() -> list:
    return list(itertools.pairwise(OVERVIEW_Z_EDGES))


def channel_bins() -> list:
    return [(b.z_min, b.z_max) for b in channels()]


def bin_fisher(task):
    """RadioFisher's clean Fisher matrix for one bin ((z_min, z_max), cosmology), as the Overview computed it."""
    (zmin, zmax), name = task
    cosmo = inputs.cosmology(name)
    expt = inputs.experiment(baselines="all")
    F, names = rf.fisher(zmin, zmax, cosmo, expt, inputs.background(cosmo))
    return F, list(names)


def combine(matrices: list, names: list) -> dict:
    """Per-bin sigma(D_V)/D_V and sigma(f sigma_8) from the combined matrix."""
    n = len(matrices)
    if not n:
        raise ValueError("at least one redshift bin is required")
    per = [names.index(p) for p in PER_BIN]
    shared = [names.index(p) for p in SHARED]
    size = n * len(PER_BIN) + len(SHARED)
    F = np.zeros((size, size))
    for i, Fi in enumerate(matrices):
        rows = list(range(i * len(PER_BIN), (i + 1) * len(PER_BIN))) + list(range(size - len(SHARED), size))
        F[np.ix_(rows, rows)] += Fi[np.ix_(per + shared, per + shared)]
    C = np.linalg.inv(F)
    starts = np.arange(n) * len(PER_BIN)
    dilations = starts[:, None] + [PER_BIN.index("aperp"), PER_BIN.index("apar")]
    covariance = C[dilations[:, :, None], dilations[:, None, :]]
    sigma_dv = np.sqrt(np.einsum("i,nij,j->n", DV_WEIGHTS, covariance, DV_WEIGHTS))
    growth = starts + PER_BIN.index("fs8")
    return {"sigma_dv": sigma_dv.tolist(), "sigma_fs8": np.sqrt(C[growth, growth]).tolist()}


def forecast(bins: list, workers: int | None = None, cosmology: str = OVERVIEW_COSMOLOGY) -> dict:
    """The Overview forecast over ``bins`` (a list of (z_min, z_max)) in the named cosmology."""
    bins = list(bins)
    if not bins:
        raise ValueError("at least one redshift bin is required")
    if workers is not None and workers < 1:
        raise ValueError("workers must be positive")
    workers = min(len(bins), workers or os.cpu_count() or 1)
    tasks = [(b, cosmology) for b in bins]
    if workers == 1:
        results = [bin_fisher(task) for task in tasks]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(bin_fisher, tasks))
    names = results[0][1]
    out = combine([F for F, _ in results], names)
    out["cosmology"] = cosmology
    out["bins"] = [{"z_min": lo, "z_max": hi, "z_center": 0.5 * (lo + hi),
                    "nu_low_mhz": NU21_MHZ / (1 + hi), "nu_high_mhz": NU21_MHZ / (1 + lo)} for lo, hi in bins]
    return out


def reference(workers: int | None = None, cosmology: str = OVERVIEW_COSMOLOGY) -> dict:
    """Both binnings in one cosmology: the Overview's 15 bins and the 6 MHz channels."""
    bands = channels()
    dtv = forecast(channel_bins(), workers, cosmology)
    for row, b in zip(dtv["bins"], bands):
        row["channel"] = b.channel
    return {"cosmology": cosmology, "overview_bins": forecast(overview_bins(), workers, cosmology),
            "channels": dtv, "method": __doc__.split("\n\n")[1].replace("\n", " ")}
