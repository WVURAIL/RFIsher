import copy

import pytest
import radiofisher as rf
from radiofisher.units import HRS_MHZ

from rfisher import inputs, pk_cache


def test_the_power_spectrum_tables_belong_to_their_cosmologies():
    assert inputs.DEFAULT_COSMOLOGY == "cmbspa2026"
    overview = pk_cache.with_explicit_physical_densities(copy.deepcopy(rf.chime.cosmo))
    assert pk_cache.cache_matches(inputs.pk_table_path("planck2018"), overview)
    assert pk_cache.inspect_pk_cache(inputs.pk_table_path("planck2018"))["cosmology"]["h"] == rf.chime.cosmo["h"]
    assert pk_cache.cache_matches(inputs.pk_table_path(), inputs.parameters())


def test_a_different_cosmology_is_refused(monkeypatch):
    monkeypatch.setattr(inputs, "CMBSPA2026", dict(inputs.CMBSPA2026, h=0.70))
    with pytest.raises(ValueError, match="not built for this cosmology"):
        inputs.cosmology()


def test_a_damaged_table_is_refused(tmp_path):
    damaged = tmp_path / "pk.dat"
    lines = inputs.pk_table_path().read_text().splitlines()
    lines[5] = lines[5].replace("e", "E", 1)
    damaged.write_text("\n".join(lines) + "\n")
    with pytest.raises(ValueError, match="digest"):
        pk_cache.inspect_pk_cache(damaged)
    assert not pk_cache.cache_matches(damaged, inputs.parameters())


def test_densities_are_all_or_none():
    with pytest.raises(ValueError):
        pk_cache.physical_densities(dict(rf.chime.cosmo, ombh2=0.02))


def test_one_retained_year():
    assert inputs.experiment()["ttot"] == 8760.0 * HRS_MHZ
    assert inputs.experiment(100.0)["ttot"] == 100.0 * HRS_MHZ


def test_the_latest_cosmology_has_its_own_table():
    c = inputs.parameters("cmbspa2026")
    assert (c["h"], c["ombh2"], c["omch2"], c["ns"], c["sigma_8"]) == (0.6832, 0.022506, 0.11755, 0.9742, 0.8117)
    assert c["omega_M_0"] + c["omega_lambda_0"] == pytest.approx(1.0)
    assert pk_cache.cache_matches(inputs.pk_table_path("cmbspa2026"), c)
    assert not pk_cache.cache_matches(inputs.pk_table_path("planck2018"), c)


def test_an_unknown_cosmology_is_refused():
    with pytest.raises(ValueError, match="unknown cosmology"):
        inputs.parameters("planck2013")
