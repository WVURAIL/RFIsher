"""CHIME's baseline density n(x), built from the array layout.

RadioFisher's CHIME density (src/radiofisher/data/nx_CHIME_800.dat) counts every pair of
feeds, including the pairs within one cylinder. CHIME's 21 cm analyses drop those
intra-cylinder baselines, which carry noise cross-talk and a strong response to diffuse
Galactic emission (CHIME Collaboration 2025, arXiv:2511.19620; the stacking analysis of
the CHIME Overview, Sec. IV.5). The tolerance table therefore uses the inter-cylinder
pairs only (``inputs.experiment``). The Overview reproduction keeps RadioFisher's
density, as the Overview's own forecast does.

Layout: 4 cylinders 22 m apart east-west, 256 feeds per cylinder 0.3048 m apart
north-south. As in RadioFisher's file, x = u / nu[MHz] = |d| / 300 m, n(x) = n(u) nu^2 is
per unit x^2 and counts unordered pairs, and the grid is that file's. Built from all
pairs this reproduces RadioFisher's file exactly.

    python -m rfisher.baselines      # rewrites src/rfisher/data/nx_CHIME_inter.dat
"""
from importlib import resources
from pathlib import Path

import numpy as np
import radiofisher as rf
from radiofisher.units import FORECAST_LIGHT_SPEED_KM_S

CYLINDERS, CYLINDER_SPACING_M = 4, 22.0
FEEDS, FEED_SPACING_M = 256, 0.3048
METERS_PER_X = FORECAST_LIGHT_SPEED_KM_S / 1000            # x = d / 300 m, the speed of light RadioFisher's file uses
INTER_FILE = "nx_CHIME_inter.dat"


def radiofisher_file() -> Path:
    """RadioFisher's CHIME density: every pair of feeds."""
    return Path(rf.chime.CHIME["n(x)"])


def inter_file() -> Path:
    """The packaged inter-cylinder density."""
    return Path(str(resources.files("rfisher.data").joinpath(INTER_FILE)))


def density(x, inter_only: bool = True) -> np.ndarray:
    """Compute n(x) from the array layout at the supplied bin centers x.

    The bins are uniform and start at zero.
    """
    x = np.asarray(x, dtype=float)
    dx = x[1] - x[0]
    edges = np.r_[x - dx / 2, x[-1] + dx / 2]
    e = np.arange(-(CYLINDERS - 1), CYLINDERS)
    n = np.arange(-(FEEDS - 1), FEEDS)
    E, N = np.meshgrid(e, n, indexing="ij")
    pairs = np.outer(CYLINDERS - np.abs(e), FEEDS - np.abs(n)).astype(float)   # ordered pairs per offset
    d = np.hypot(E * CYLINDER_SPACING_M, N * FEED_SPACING_M) / METERS_PER_X
    keep = (d > 0) & (E != 0) if inter_only else d > 0
    counts, _ = np.histogram(d[keep], bins=edges, weights=pairs[keep])
    return counts / (2 * np.pi * x * dx) / 2


def build(path=None) -> Path:
    """Write the inter-cylinder density on RadioFisher's grid."""
    x = np.loadtxt(radiofisher_file())[:, 0]
    path = Path(path) if path is not None else Path(__file__).parent / "data" / INTER_FILE
    np.savetxt(path, np.c_[x, density(x, inter_only=True)])
    return path


if __name__ == "__main__":  # pragma: no cover
    print(build())
