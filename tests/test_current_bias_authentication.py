"""Named fiducials and their citations remain authenticated in bias workflows."""
from copy import deepcopy
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from rfisher import resources
from rfisher.backend import find_radiofisher_dir
from rfisher.fisherbank import ARTIFACT_BIAS_RESPONSE, FisherBank

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "rfisher_test_current_bias_authentication", ROOT / "scripts/bias_tolerance.py")
bt = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bt)


def _backend():
    try:
        return find_radiofisher_dir()
    except FileNotFoundError:
        pytest.skip("cosmology authentication needs the RadioFisher checkout")


@pytest.mark.parametrize("cosmology", list(resources.BANK_NAMES))
def test_named_cosmology_identity_reconstructs_its_reference(cosmology):
    rf_dir = _backend()
    bank = FisherBank(resources.bank_file(cosmology))
    identity, _ = bt._evaluation_identity(bank, rf_dir=rf_dir)
    assert identity["cosmology"] == bank.meta["provenance"]["cosmology"]


@pytest.mark.parametrize("cosmology", ["planck2018", "cmbspa2026"])
def test_forged_reference_is_rejected(cosmology):
    rf_dir = _backend()
    bank = FisherBank(resources.bank_file(cosmology))
    bank.meta["provenance"]["cosmology"]["reference"] = {"arxiv": "forged"}
    with pytest.raises(ValueError, match="cosmology build/evaluation identity differs"):
        bt._evaluation_identity(bank, rf_dir=rf_dir)


def test_current_cosmology_cannot_drop_its_published_reference():
    rf_dir = _backend()
    bank = FisherBank(resources.bank_file("cmbspa2026"))
    del bank.meta["provenance"]["cosmology"]["reference"]
    with pytest.raises(ValueError, match="cosmology build/evaluation identity differs"):
        bt._evaluation_identity(bank, rf_dir=rf_dir)


@pytest.mark.parametrize("cosmology", ["planck2018", "pact2025"])
def test_legacy_optional_reference_can_be_absent(cosmology):
    rf_dir = _backend()
    bank = FisherBank(resources.bank_file(cosmology))
    del bank.meta["provenance"]["cosmology"]["reference"]
    identity, _ = bt._evaluation_identity(bank, rf_dir=rf_dir)
    assert "reference" not in identity["cosmology"]


@pytest.mark.parametrize("cosmology", [*resources.BANK_NAMES, "unknown"])
def test_bias_loader_accepts_only_registered_chime_cosmologies(
        tmp_path, monkeypatch, cosmology):
    metadata = deepcopy(FisherBank(resources.DEFAULT_BANK).meta)
    metadata["cosmology"] = cosmology
    metadata["expt_overrides"]["P_res"] = 1.0
    metadata["provenance"]["experiment"]["settings"]["P_res"] = 1.0
    bank = SimpleNamespace(meta=metadata, artifact_kind=ARTIFACT_BIAS_RESPONSE,
                           paramnames=["A", "_Pres"])
    path = tmp_path / "response.npz"
    path.touch()
    monkeypatch.setattr(bt, "FisherBank", lambda _: bank)
    monkeypatch.setattr(bt, "_evaluation_identity", lambda *a, **kw: ({}, {}))
    if cosmology == "unknown":
        with pytest.raises(ValueError, match="supported named cosmology"):
            bt.load_bias_bank(path)
    else:
        assert bt.load_bias_bank(path) is bank
