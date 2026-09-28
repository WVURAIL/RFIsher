"""The experiment registry against a synthetic RadioFisher ``chime2021`` checkout."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from rfisher.forecast.radiofisher_bao.bank import banks, experiments

CHIME_SOURCE = '''
def _tsys(z):
    return 55.0


CHIME = {"mode": "icyl", "Tsys_tot(z)": _tsys, "n(x)": "nx_as_built.dat",
         "Sarea": 9.4, "epsilon_fg": 0.0}
cosmo = {"h": 0.6732, "omega_M_0": 0.31}
'''


def _checkout(root: Path) -> Path:
    (root / "chime2021").mkdir(parents=True)
    (root / "chime2021" / "experiments_CHIME.py").write_text(CHIME_SOURCE)
    return root


@pytest.fixture
def fresh_import(monkeypatch):
    """Isolate the module cache and path the registry's import writes to."""
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.delitem(sys.modules, "experiments_CHIME", raising=False)
    yield
    sys.modules.pop("experiments_CHIME", None)


def test_the_overview_experiment_comes_from_the_checkout(tmp_path, fresh_import):
    root = _checkout(tmp_path / "RadioFisher")
    expt = experiments.chime2022_experiment(None, root, ttot_hours=2.0)
    assert expt["ttot"] == 2.0 * experiments.HRS_MHZ
    assert expt["n(x)"] == str(root / "chime2021" / "nx_as_built.dat")
    module = sys.modules["experiments_CHIME"]
    assert expt["Tsys_tot(z)"] is module.CHIME["Tsys_tot(z)"]
    cosmo = experiments.chime2022_cosmo(None, root)
    assert cosmo == {"h": 0.6732, "omega_M_0": 0.31}
    assert cosmo is not module.cosmo


def test_a_second_checkout_in_one_process_is_refused(tmp_path, fresh_import):
    first = _checkout(tmp_path / "first")
    second = _checkout(tmp_path / "second")
    experiments.chime2022_experiment(None, first)
    with pytest.raises(RuntimeError, match="checkout mismatch"):
        experiments.chime2022_experiment(None, second)


def test_a_recorded_overview_experiment_is_reconstructed(tmp_path, fresh_import):
    root = _checkout(tmp_path / "RadioFisher")
    overrides = {"P_res": 1.0}
    reference = experiments.chime2022_experiment(None, root, ttot_hours=1.0)
    reference.update(overrides)
    meta = {"config": "chime2022", "expt_overrides": overrides,
            "provenance": {"experiment": {
                "settings": banks.experiment_settings_payload(reference, root)}}}
    expt = experiments.experiment_from_bank_metadata(None, root, meta,
                                                     ttot_hours=3.0)
    assert expt["ttot"] == 3.0 * experiments.HRS_MHZ and expt["P_res"] == 1.0


@pytest.mark.parametrize("meta,match", [
    ([], "must be an object"),
    ({"config": "chime2022"}, "no recorded experiment settings"),
    ({"config": "chime2022", "expt_overrides": [],
      "provenance": {"experiment": {"settings": {}}}}, "must be objects"),
    ({"config": "bull2015", "expt_overrides": {},
      "provenance": {"experiment": {"settings": {"k_nl0": 0.14}}}},
     "missing recorded epsilon_fg or k_nl0"),
    ({"config": "wedge", "expt_overrides": {},
      "provenance": {"experiment": {"settings": {}}}},
     "unsupported recorded experiment configuration"),
])
def test_an_unreconstructable_record_is_refused(meta, match):
    with pytest.raises(ValueError, match=match):
        experiments.experiment_from_bank_metadata(None, "/unused", meta, 1.0)


def test_the_registry_names_the_supported_configurations():
    assert experiments.SUPPORTED_CONFIGS == {"bull2015", "chime2022"}
    assert experiments.SUPPORTED_COSMOLOGIES["chime2022"] == {
        None, "planck2018", "pact2025", "cmbspa2026"}
    assert (experiments.CHIME_FREQUENCY_MIN_MHZ,
            experiments.CHIME_FREQUENCY_MAX_MHZ) == (400.0, 800.0)
    assert experiments.zbin_freq_range(1.0, 1.1) == (
        experiments.HI_REST_FREQUENCY_MHZ / 2.1,
        experiments.HI_REST_FREQUENCY_MHZ / 2.0)
