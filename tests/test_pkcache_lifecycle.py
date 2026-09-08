"""Power-cache generation, units, reuse and regeneration without optional CAMB."""
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from rfisher import pkcache


def _cosmo():
    return dict(h=0.5, ns=0.96, sigma_8=0.8, omega_b_0=0.05, omega_M_0=0.3, mnu=0.06)


@pytest.fixture
def camb(monkeypatch):
    params = SimpleNamespace(InitPower=SimpleNamespace(set_params=Mock()), set_matter_power=Mock())

    def set_cosmology(**kwargs):
        params.omnuh2 = kwargs["omnuh2_active"]

    params.set_cosmology = Mock(side_effect=set_cosmology)
    results = SimpleNamespace(
        get_matter_power_spectrum=Mock(return_value=(np.array([0.1, 1.0]), [0], np.array([[2.0, 8.0]]))),
        get_sigma8_0=Mock(return_value=0.4))
    fake = SimpleNamespace(__version__="synthetic-test", CAMBparams=Mock(return_value=params),
                           model=SimpleNamespace(NonLinear_none="linear"), get_results=Mock(return_value=results))
    monkeypatch.setitem(sys.modules, "camb", fake)
    return params, results


def test_generated_cache_has_correct_h_units_normalization_and_content_identity(tmp_path, camb):
    path = tmp_path / "nested" / "cache.dat"
    cosmo = _cosmo()
    assert pkcache.build_pk_cache(cosmo, path, kmax_h=10, npoints=2) == path
    # k is in Mpc^-1; power is in Mpc^3, with sigma8 squared normalization.
    np.testing.assert_allclose(np.loadtxt(path), [[0.05, 64.0], [0.5, 256.0]])
    metadata = pkcache.inspect_pk_cache(path)
    assert metadata["generator"]["version"] == "synthetic-test"
    assert pkcache.cache_matches(path, cosmo, kmax_h=10, npoints=2)
    assert not pkcache.cache_matches(path, cosmo, kmax_h=20, npoints=2)
    assert not pkcache.cache_matches(path, cosmo, kmax_h=10, npoints=3)
    assert not pkcache.cache_matches(path, {**cosmo, "sigma_8": 0.9}, kmax_h=10, npoints=2)
    camb[0].set_matter_power.assert_called_once_with(redshifts=[0.0], kmax=10, accurate_massive_neutrino_transfers=False)
    camb[1].get_matter_power_spectrum.assert_called_once_with(minkh=1e-4, maxkh=10, npoints=2)
    assert cosmo == _cosmo()


def test_valid_cache_is_reused_and_force_build_regenerates(tmp_path, camb, monkeypatch):
    path = pkcache.build_pk_cache(_cosmo(), tmp_path / "cache.dat")
    backend = SimpleNamespace(load_power_spectrum=Mock(return_value="loaded"))
    generate = Mock(wraps=pkcache.build_pk_cache)
    monkeypatch.setattr(pkcache, "build_pk_cache", generate)
    assert pkcache.load_fiducial_cosmology(backend, path, cosmo=_cosmo()) == "loaded"
    generate.assert_not_called()
    loaded_cosmo, loaded_path = backend.load_power_spectrum.call_args.args
    assert loaded_path == str(path) and "omnuh2" in loaded_cosmo
    assert backend.load_power_spectrum.call_args.kwargs == {"force_load": True}
    pkcache.load_fiducial_cosmology(backend, path, cosmo=_cosmo(), force_build=True)
    generate.assert_called_once()
    path.write_bytes(path.read_bytes() + b"# changed\n")
    pkcache.load_fiducial_cosmology(backend, path, cosmo=_cosmo())
    assert generate.call_count == 2 and pkcache.cache_matches(path, _cosmo())


@pytest.mark.parametrize("existing,state", [(False, "missing"), (True, "stale or unversioned")])
def test_unavailable_generator_explains_cache_state_and_does_not_call_backend(tmp_path, monkeypatch, existing, state):
    path = tmp_path / "cache.dat"
    if existing:
        path.write_text("# pythoncamb#\n0.1 2.0\n", encoding="utf-8")
    monkeypatch.setitem(sys.modules, "camb", None)
    backend = SimpleNamespace(load_power_spectrum=Mock())
    with pytest.raises(ModuleNotFoundError, match=state):
        pkcache.load_fiducial_cosmology(backend, path, cosmo=_cosmo())
    backend.load_power_spectrum.assert_not_called()
