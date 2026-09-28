"""Supported console-command argument routing: the one ``rfisher`` command."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from rfisher import cli
from rfisher.forecast.radiofisher_bao import scenarios
from rfisher.forecast.radiofisher_bao.bank import build
from rfisher.forecast.radiofisher_bao.bank import experiments as survey


@pytest.mark.parametrize(
    "argv,program",
    [(["--version"], "rfisher"),
     (["forecast", "--version"], "rfisher forecast")],
)
def test_cli_version_matches_the_release(argv, program, capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(argv)
    assert excinfo.value.code == 0
    assert capsys.readouterr().out == f"{program} 4.0.0\n"


def test_cli_lists_its_commands_and_refuses_an_unknown_one(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--help"])
    assert excinfo.value.code == 0
    listing = capsys.readouterr().out
    assert "forecast" in listing and "build-bank" in listing
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["rfisher-forecast"])
    assert excinfo.value.code == 2


def test_cli_routes_each_command_to_its_own_parser(monkeypatch):
    seen = []
    monkeypatch.setitem(cli.COMMANDS, "forecast", (
        lambda argv, prog: seen.append((argv, prog)) or 0, "text"))
    assert cli.main(["forecast", "--uniform", "0.5", "--help"]) == 0
    assert seen == [(["--uniform", "0.5", "--help"], "rfisher forecast")]


@pytest.mark.parametrize("config,cosmology", [
    ("bull2015", None),
    ("bull2015", "planck2013"),
    ("chime2022", None),
    ("chime2022", "planck2018"),
    ("chime2022", "pact2025"),
    ("chime2022", "cmbspa2026"),
])
def test_build_cli_routes_supported_config_cosmology_pairs(
        monkeypatch, tmp_path, config, cosmology):
    seen = {}
    monkeypatch.setattr(
        build, "build_bank", lambda output, **kwargs: seen.update(
            output=output, **kwargs))
    argv = ["--out", str(tmp_path / "bank.npz"), "--config", config,
            "--nt", "2"]
    if cosmology is not None:
        argv += ["--cosmology", cosmology]
    assert cli.main(["build-bank"] + argv) == 0
    assert seen["config"] == config
    # The command resolves the configuration's default cosmology itself.
    assert seen["cosmology"] == cosmology or {
        "bull2015": "planck2013", "chime2022": "cmbspa2026"}[config]


@pytest.mark.parametrize("config,cosmology", [
    ("bull2015", "planck2018"),
    ("bull2015", "pact2025"),
    ("chime2022", "planck2013"),
])
def test_build_cli_rejects_mislabeled_pairs(tmp_path, config, cosmology):
    with pytest.raises(SystemExit):
        cli.main(["build-bank"] + [
            "--out", str(tmp_path / "bank.npz"), "--config", config,
            "--cosmology", cosmology])


def test_build_cli_defaults_to_current_chime_configuration(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(
        build, "build_bank", lambda output, **kwargs: seen.update(
            output=output, **kwargs))

    assert cli.main(["build-bank"] + [
        "--out", str(tmp_path / "bank.npz"), "--nt", "2"]) == 0

    assert seen["config"] == "chime2022"
    assert seen["cosmology"] == "cmbspa2026"


def test_build_cli_adds_bull_knee_without_moving_base_grid(monkeypatch,
                                                           tmp_path):
    seen = {}
    monkeypatch.setattr(
        build, "build_bank", lambda output, **kwargs: seen.update(
            output=output, **kwargs))
    knee = 10.0 ** 3.5

    assert cli.main(["build-bank"] + [
        "--out", str(tmp_path / "bank.npz"),
        "--config", "bull2015", "--cosmology", "planck2013",
        "--nt", "27", "--extra-time-hours", repr(knee),
    ]) == 0

    base = np.logspace(0.0, 6.0, 27)
    assert np.array_equal(
        seen["t_grid_hours"], np.unique(np.concatenate([base, [knee]])))
    assert seen["t_grid_hours"].size == 28


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "1e7"])
def test_build_cli_rejects_invalid_extra_time(tmp_path, value):
    with pytest.raises(SystemExit):
        cli.main(["build-bank"] + [
            "--out", str(tmp_path / "bank.npz"),
            "--extra-time-hours", value,
        ])


@pytest.mark.parametrize(
    "cosmology,band_name,expected_band",
    [
        ("planck2018", "dtv", scenarios.DTV_BAND),
        ("planck2018", "chime", scenarios.CHIME_BAND),
        ("pact2025", "dtv", scenarios.DTV_BAND),
        ("pact2025", "chime", scenarios.CHIME_BAND),
    ],
)
def test_forecast_cli_routes_named_bank_and_explicit_band(
        monkeypatch, capsys, cosmology, band_name, expected_band):
    bank_resource = object()
    forecast = object()
    seen = {}

    def select_bank(name):
        seen["cosmology"] = name
        return bank_resource

    def load_bank(source):
        seen["source"] = source
        return forecast

    def required_time(loaded, **kwargs):
        seen["forecast"] = loaded
        seen.update(kwargs)
        return {"hours": 12.5, "years": 0.25}

    monkeypatch.setattr(cli.resources, "bank_file", select_bank)
    monkeypatch.setattr(cli.api, "load", load_bank)
    monkeypatch.setattr(cli.api, "required_time", required_time)

    assert cli.forecast_main([
        "--cosmology", cosmology,
        "--uniform", "0.25",
        "--band", band_name,
        "--target", "4",
        "--duty", "0.5",
        "--hours-per-year", "8760",
    ]) == 0

    assert seen == {
        "cosmology": cosmology,
        "source": bank_resource,
        "forecast": forecast,
        "uniform": 0.25,
        "band": expected_band,
        "target": 4.0,
        "duty": 0.5,
        "hours_per_year": 8760.0,
    }
    assert json.loads(capsys.readouterr().out) == {
        "hours": 12.5, "years": 0.25}


def test_forecast_cli_defaults_to_current_cosmology_and_dtv(monkeypatch, capsys):
    seen = {}
    monkeypatch.setattr(
        cli.resources, "bank_file",
        lambda cosmology: seen.setdefault("cosmology", cosmology))
    monkeypatch.setattr(cli.api, "load", lambda bank: object())

    def required_time(_forecast, **kwargs):
        seen.update(kwargs)
        return {"hours": 1.0}

    monkeypatch.setattr(cli.api, "required_time", required_time)

    assert cli.forecast_main(["--uniform", "0"]) == 0

    assert seen["cosmology"] == "cmbspa2026"
    assert seen["band"] is scenarios.DTV_BAND
    # The Overview on-sky normalization (1 yr = 8,760 on-sky hours) is the
    # convention every quoted time in this repository uses.
    assert seen["hours_per_year"] == survey.OVERVIEW_ONSKY_YEAR_HOURS
    assert json.loads(capsys.readouterr().out) == {"hours": 1.0}


def test_forecast_cli_explicit_bank_bypasses_named_resources(
        monkeypatch, capsys, tmp_path):
    bank_path = tmp_path / "custom.npz"
    seen = {}

    def unexpected_named_bank(_cosmology):
        raise AssertionError("an explicit bank must bypass packaged selection")

    monkeypatch.setattr(cli.resources, "bank_file", unexpected_named_bank)
    monkeypatch.setattr(
        cli.api, "load", lambda source: seen.setdefault("source", source))
    monkeypatch.setattr(
        cli.api, "required_time", lambda _forecast, **_kwargs: {"hours": 1.0})

    assert cli.forecast_main([
        "--bank", str(bank_path), "--uniform", "0"]) == 0

    assert seen["source"] == Path(bank_path)
    assert json.loads(capsys.readouterr().out) == {"hours": 1.0}


def test_forecast_cli_rejects_retired_band_alias():
    with pytest.raises(SystemExit):
        cli.forecast_main(["--uniform", "0.5", "--band", "all"])


def test_forecast_cli_rejects_two_bank_selectors(tmp_path):
    with pytest.raises(SystemExit):
        cli.forecast_main([
            "--bank", str(tmp_path / "bank.npz"),
            "--cosmology", "pact2025",
            "--uniform", "0.5",
        ])
