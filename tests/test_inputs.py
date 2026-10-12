import copy

import pytest
import radiofisher as rf
from radiofisher.units import HRS_MHZ

from rfisher import inputs, pk_cache


def test_the_power_spectrum_table_belongs_to_the_cosmology():
    cosmo = pk_cache.with_explicit_physical_densities(copy.deepcopy(rf.chime.cosmo))
    assert pk_cache.cache_matches(inputs.pk_table_path(), cosmo)
    meta = pk_cache.inspect_pk_cache(inputs.pk_table_path())
    assert meta["cosmology"]["h"] == rf.chime.cosmo["h"]


def test_a_different_cosmology_is_refused(monkeypatch):
    other = dict(rf.chime.cosmo, h=0.70)
    monkeypatch.setattr(rf.chime, "cosmo", other)
    with pytest.raises(ValueError, match="not built for this cosmology"):
        inputs.cosmology()


def test_a_damaged_table_is_refused(tmp_path):
    damaged = tmp_path / "pk.dat"
    lines = inputs.pk_table_path().read_text().splitlines()
    lines[5] = lines[5].replace("e", "E", 1)
    damaged.write_text("\n".join(lines) + "\n")
    with pytest.raises(ValueError, match="digest"):
        pk_cache.inspect_pk_cache(damaged)
    cosmo = pk_cache.with_explicit_physical_densities(copy.deepcopy(rf.chime.cosmo))
    assert not pk_cache.cache_matches(damaged, cosmo)


def test_densities_are_all_or_none():
    with pytest.raises(ValueError):
        pk_cache.physical_densities(dict(rf.chime.cosmo, ombh2=0.02))


def test_one_retained_year():
    assert inputs.experiment()["ttot"] == 8760.0 * HRS_MHZ
    assert inputs.experiment(100.0)["ttot"] == 100.0 * HRS_MHZ
