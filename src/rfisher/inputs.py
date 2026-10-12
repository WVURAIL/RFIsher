"""The fixed forecast inputs. A new cosmology, telescope or anchor means a new table.

    cosmology   a named fiducial with its linear P(k) table:
                planck2018  the CHIME Overview's (Planck 2018 CMB only), the default
                cmbspa2026  SPT-3G + ACT + Planck CMB, lensing and DESI DR2 BAO
                            (Omori et al. 2026, arXiv:2608.31136v1, Table 8,
                            posterior means, flat LambdaCDM)
    experiment  CHIME as in the CHIME Overview, for one retained year

Everything but the cosmological parameters (HI models, sigma_NL, the growth
index, the experiment) is the CHIME Overview's in every cosmology.
"""
import copy
from importlib import resources

import radiofisher as rf
from radiofisher.units import HRS_MHZ

from . import pk_cache

RETAINED_HOURS = 8760.0  # one retained year: 365 days of kept data
DEFAULT_COSMOLOGY = "planck2018"
CMBSPA2026 = {"h": 0.6832, "ombh2": 0.022506, "omch2": 0.11755, "sigma_8": 0.8117, "ns": 0.9742, "mnu": 0.06}
PK_TABLES = {"planck2018": "pk_planck2018.dat", "cmbspa2026": "pk_cmbspa2026.dat"}
PK_TABLE = PK_TABLES[DEFAULT_COSMOLOGY]


def pk_table_path(name: str = DEFAULT_COSMOLOGY):
    return resources.files("rfisher.data").joinpath(PK_TABLES[name])


def parameters(name: str = DEFAULT_COSMOLOGY) -> dict:
    """The named fiducial's parameters, without its power spectrum."""
    cosmo = copy.deepcopy(rf.chime.cosmo)
    if name == "cmbspa2026":
        c = dict(CMBSPA2026)
        c["omnuh2"] = c["mnu"] / pk_cache.NEUTRINO_MASS_DENSITY_EV
        h2 = c["h"] ** 2
        c["omega_b_0"], c["omega_cdm_0"], c["omega_nu_0"] = c["ombh2"] / h2, c["omch2"] / h2, c["omnuh2"] / h2
        c["omega_M_0"] = c["omega_b_0"] + c["omega_cdm_0"] + c["omega_nu_0"]
        c["omega_lambda_0"] = 1 - c["omega_M_0"]
        cosmo.update(c, w0=-1.0, wa=0.0)
    elif name != "planck2018":
        raise ValueError(f"unknown cosmology {name!r}; choose one of {sorted(PK_TABLES)}")
    return pk_cache.with_explicit_physical_densities(cosmo)


def cosmology(name: str = DEFAULT_COSMOLOGY) -> dict:
    """The named fiducial with its power spectrum attached.

    The P(k) table must have been built for exactly this cosmology
    (pk_cache.build_pk_cache); a mismatch stops the forecast.
    """
    cosmo = parameters(name)
    path = pk_table_path(name)
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
