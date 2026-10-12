"""The fixed forecast inputs. A new cosmology, telescope or anchor means a new table.

    cosmology   Planck 2018 as in the CHIME Overview, with its linear P(k) table
    experiment  CHIME as in the CHIME Overview, for one retained year
"""
import copy
from importlib import resources

import radiofisher as rf
from radiofisher.units import HRS_MHZ

from . import pk_cache

RETAINED_HOURS = 8760.0  # one retained year: 365 days of kept data
PK_TABLE = "pk_planck2018.dat"


def pk_table_path():
    return resources.files("rfisher.data").joinpath(PK_TABLE)


def cosmology() -> dict:
    """The fiducial cosmology with its power spectrum attached.

    The P(k) table must have been built for exactly this cosmology
    (pk_cache.build_pk_cache); a mismatch stops the forecast.
    """
    cosmo = pk_cache.with_explicit_physical_densities(copy.deepcopy(rf.chime.cosmo))
    path = pk_table_path()
    if not pk_cache.cache_matches(path, cosmo):
        raise ValueError(f"{path} was not built for this cosmology; rebuild it with "
                         "rfisher.pk_cache.build_pk_cache (needs the optional camb)")
    return rf.load_power_spectrum(cosmo, str(path))


def experiment(hours: float = RETAINED_HOURS) -> dict:
    """CHIME as in the CHIME Overview, observing for ``hours`` of retained data."""
    expt = copy.deepcopy(rf.chime.CHIME)
    expt["ttot"] = hours * HRS_MHZ
    return expt


def background(cosmo: dict):
    """H(z), r(z), D(z), f(z) for RadioFisher."""
    return rf.background_evolution_splines(cosmo)
