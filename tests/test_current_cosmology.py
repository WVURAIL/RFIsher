"""The new default is distinct from both historical reproduction fiducials."""
from pathlib import Path
import runpy
import sys
import numpy as np
import pytest
from scipy.integrate import simpson
from rfisher import cosmologies, resources, pkcache
from rfisher.fisherbank import FisherBank


def test_default_bank_matches_published_2026_inputs_and_verified_cache():
    bank = FisherBank(resources.bank_file())
    assert bank.meta['cosmology'] == cosmologies.DEFAULT_COSMOLOGY == 'cmbspa2026'
    provenance = bank.meta['provenance']['cosmology']
    c = provenance['parameters']
    expected = dict(h=.6832, ombh2=.022506, omch2=.11755, ns=.9742, sigma_8=.8117, mnu=.06)
    for key, value in expected.items():
        assert c[key] == pytest.approx(value, rel=0, abs=1e-16)
    assert provenance['reference']['arxiv'] == '2608.31136v1'
    assert provenance['reference']['statistic'] == 'posterior means'
    cached = pkcache.inspect_pk_cache(resources.filesystem_data_file('cache_pk_chime2022_cmbspa2026.dat'))
    assert cached['cosmology'] == c
    for historical in ['planck2018', 'pact2025']:
        reference = FisherBank(resources.bank_file(historical))
        assert not np.array_equal(reference.F_grid, bank.F_grid)


def test_backend_factory_keeps_foreman_hi_model_while_updating_cosmology():
    from rfisher.backend import import_radiofisher
    try:
        rf, root = import_radiofisher()
    except (FileNotFoundError, ModuleNotFoundError):
        pytest.skip('requires the RadioFisher fork checkout')
    if not hasattr(rf, 'get_cosmology'):
        pytest.fail('RadioFisher fork lacks the current cosmology factory')
    current = cosmologies.get(None, rf, root)
    foreman = cosmologies.get('planck2018', rf, root)
    for field in ['Tb_model', 'bias_HI_model', 'omega_HI_model', 'astrophysical_model_profile']:
        assert current[field] == foreman[field]
    assert current['h'] != foreman['h']
    assert current['omega_M_0']+current['omega_lambda_0'] == 1.
    expected_om = (current['ombh2']+current['omch2']+current['omnuh2'])/current['h']**2
    assert current['omega_M_0'] == pytest.approx(expected_om)
    with pytest.raises(ValueError):
        cosmologies.get('not-a-cosmology', rf, root)


def test_current_power_spectrum_has_the_published_sigma8_normalization():
    """Independent top-hat integral of the actual CAMB table, in Mpc units."""
    path = resources.filesystem_data_file('cache_pk_chime2022_cmbspa2026.dat')
    metadata = pkcache.inspect_pk_cache(path)
    k, power = np.loadtxt(path).T
    c = metadata['cosmology']
    x = k*8/c['h']
    window = 3*(np.sin(x)-x*np.cos(x))/x**3
    variance = simpson(k**3*power*window**2, x=np.log(k))/(2*np.pi**2)
    assert np.sqrt(variance) == pytest.approx(c['sigma_8'], rel=3e-4)


@pytest.mark.parametrize('name', [None, 'planck2018', 'cmbspa2026'])
def test_research_builder_never_writes_new_cosmology_to_historical_name(monkeypatch, name):
    from rfisher import fisherbank
    seen = {}
    def build(output, **kwargs):
        seen.update(output=Path(output), **kwargs)
    monkeypatch.setattr(fisherbank, 'build_bank', build)
    args = ['build_bank.py', '--nt', '2']
    if name:
        args += ['--cosmology', name]
    monkeypatch.setattr(sys, 'argv', args)
    runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/build_bank.py'), run_name='__main__')
    expected = name or cosmologies.DEFAULT_COSMOLOGY
    assert seen['cosmology'] == expected
    assert seen['output'].name == resources.BANK_NAMES[expected]


def test_current_fiducial_rejects_a_backend_without_the_factory(monkeypatch):
    from rfisher import survey
    seed = dict(h=.67, omega_M_0=.3, omega_b_0=.05, mnu=.06)
    monkeypatch.setattr(survey, 'chime2022_cosmo', lambda *a: seed)
    monkeypatch.setattr(cosmologies, 'with_astrophysical_profile', lambda c, *a, **kw: c)
    with pytest.raises(RuntimeError, match='get_cosmology'):
        cosmologies.get('cmbspa2026', object(), None)
