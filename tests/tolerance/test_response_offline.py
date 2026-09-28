"""The response library paths that need no RadioFisher backend."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from rfisher.forecast.radiofisher_bao import response
from rfisher.forecast.radiofisher_bao.bank import banks

# The synthetic strict-v2 bank writer of the bank schema tests.
_SPEC = importlib.util.spec_from_file_location(
    "bank_schema_fixture",
    Path(__file__).resolve().parents[1] / "forecast" / "test_fisherbank_schema.py")
_FIXTURE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_FIXTURE)
_write_bank = _FIXTURE._write_bank

NAMES = ["A", "aperp", "apar", "fs8", "b_HI", "_Pres"]


def _fisher(coupling=0.5):
    matrix = np.diag([4.0, 9.0, 16.0, 25.0, 0.0, 1.0])
    ip = NAMES.index("_Pres")
    for name, value in (("aperp", coupling), ("apar", -coupling),
                        ("fs8", 2 * coupling)):
        i = NAMES.index(name)
        matrix[i, ip] = matrix[ip, i] = value
    return matrix


class _Bank:
    def __init__(self, coupling):
        self.coupling = coupling

    def F(self, ib, t_hours):
        return _fisher(self.coupling(t_hours))


def test_the_split_drops_the_response_row_excluded_and_empty_rows():
    Ftt, FtA, kept = response.split(_fisher(), NAMES)
    assert kept == ["A", "aperp", "apar", "fs8"]         # b_HI excluded, empty
    assert Ftt.shape == (4, 4) and FtA.tolist() == [0.0, 0.5, -0.5, 1.0]


def test_the_bias_per_unit_residual_is_minus_the_covariance_times_the_coupling():
    b, sigma = response.bias_per_unit_residual(_fisher(), NAMES)
    assert b["aperp"] == pytest.approx(0.5 / 9.0)
    assert b["apar"] == pytest.approx(-0.5 / 16.0)
    assert sigma["fs8"] == pytest.approx(1.0 / 5.0)
    assert sigma["aperp"] / abs(b["aperp"]) == pytest.approx(6.0)


def test_a_singular_system_falls_back_to_the_pseudo_inverse():
    matrix = _fisher()
    matrix[NAMES.index("A"), NAMES.index("aperp")] = 6.0
    matrix[NAMES.index("aperp"), NAMES.index("A")] = 6.0
    matrix[NAMES.index("aperp"), NAMES.index("aperp")] = 9.0
    matrix[NAMES.index("A"), NAMES.index("A")] = 4.0
    b, sigma = response.bias_per_unit_residual(matrix, NAMES)
    assert set(b) == {"A", "aperp", "apar", "fs8"}
    assert all(np.isfinite(value) for value in sigma.values())


def test_the_stability_test_reports_drift_and_signs():
    steady = _Bank(lambda t: 0.5)
    assert response.response_stability(steady, 0, 10.0, NAMES, "aperp") \
        == pytest.approx((1.0, 1))
    growing = _Bank(lambda t: 0.5 * t / 10.0)
    drift, signs = response.response_stability(growing, 0, 10.0, NAMES,
                                               "aperp", frac=0.1)
    assert drift == pytest.approx(1.1 / 0.9) and signs == 1
    flipping = _Bank(lambda t: t - 10.0 if t != 10.0 else 0.25)
    assert response.response_stability(flipping, 0, 10.0, NAMES, "aperp")[1] \
        == 2
    assert response.response_stability(steady, 0, 10.0, NAMES, "missing") \
        == (np.inf, 0)
    assert response.response_stability(_Bank(lambda t: 0.0), 0, 10.0, NAMES,
                                       "aperp") == (np.inf, 0)


def test_a_missing_bank_names_its_build_command(tmp_path):
    with pytest.raises(ValueError, match="required bias-response bank is "
                                         "missing") as refused:
        response.load_response_bank(tmp_path / "absent.npz")
    assert response.DEFAULT_BUILD_COMMAND in str(refused.value)
    assert "Only the four filter-scenario response banks are packaged" \
        in str(refused.value)


def test_a_file_that_is_not_a_bank_is_refused(tmp_path):
    path = tmp_path / "junk.npz"
    path.write_bytes(b"not a bank")
    with pytest.raises(ValueError, match="not a valid strict-v2 Fisher bank"):
        response.load_response_bank(path)


def _response_bank(tmp_path, **overrides):
    def mutate(arrays, meta):
        meta["expt_overrides"] = {"P_res": 1.0, **overrides}
        meta["foreground_settings"] = {"epsilon_fg": 0.0}
        meta["provenance"]["experiment"]["settings"] = {"P_res": 1.0}
    return _write_bank(tmp_path / "response.npz",
                       kind=banks.ARTIFACT_BIAS_RESPONSE,
                       names=("A", "sigma_NL", "_Pres"), mutate=mutate)


def test_a_forecast_bank_is_not_a_response_bank(tmp_path):
    with pytest.raises(ValueError, match="artifact_kind must be "
                                         "'bias_response'"):
        response.load_response_bank(_write_bank(tmp_path / "forecast.npz"))


@pytest.mark.parametrize("expected,match", [
    ({"expected_kfg_fac": 80.0}, "kfg_fac must equal 80.0"),
    ({"expected_epsilon_fg": 1e-6}, "epsilon_fg must equal"),
])
def test_a_response_bank_of_another_scenario_is_refused(tmp_path, expected,
                                                        match):
    path = _response_bank(tmp_path)
    with pytest.raises(ValueError, match=match):
        response.load_response_bank(path, **expected)


def test_authentication_refuses_a_bank_of_another_source_manifest(tmp_path):
    bank = banks.FisherBank(_response_bank(tmp_path))
    bank.meta["provenance"]["baonoise"]["source_manifest"] = {
        "include": ["pyproject.toml", "src/rfisher/*.py"], "exclude": []}
    with pytest.raises(ValueError, match="RFIsher source manifest"):
        response.evaluation_identity(bank)
    bank.meta["provenance"]["baonoise"]["source_manifest"] = {
        key: list(value) for key, value in
        banks.BANK_SOURCE_MANIFEST.items()}
    bank.meta["provenance"]["radiofisher"]["source_manifest"] = {
        "include": ["other.py"], "exclude": []}
    with pytest.raises(ValueError, match="RadioFisher scientific-source"):
        response.evaluation_identity(bank)


def test_the_report_schema_is_frozen_and_the_banks_are_packaged():
    assert response.REPORT_SCHEMA == "baonoise-bias-tolerance-v1"
    assert response.packaged_response_banks() == Path(
        banks.__file__).resolve().parents[3] / "data" / "response_banks"
    assert response.DEFAULT_RESPONSE_BANK \
        == "fisher_bank_chime2022_pres_dense.npz"


@pytest.mark.parametrize("argv", [
    ["--zeta", "0"], ["--years", "-1"], ["--stability-fraction", "1"],
    ["--max-drift", "0.5"],
    ["--time-scaling", "fixed_physical_at_reference_time"],
    ["--reference-years", "1"],
])
def test_the_report_command_refuses_invalid_numbers(argv):
    with pytest.raises(SystemExit):
        response.bias_main(argv)


def test_the_report_command_refuses_invalid_bins_and_parameters(
        monkeypatch, tmp_path):
    class Bank:
        nbins = 2
        meta = {"expt_overrides": {"P_res": 1.0}}

    monkeypatch.setattr(response, "load_response_bank",
                        lambda *a, **k: Bank())
    with pytest.raises(SystemExit):
        response.bias_main(["--bins", "5"])
    with pytest.raises(SystemExit):
        response.bias_main(["--bins", "0", "--params", "aperp", "aperp"])
