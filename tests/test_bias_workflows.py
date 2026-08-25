"""Fail-closed prerequisites for optional coherent-bias research scripts."""
from __future__ import annotations

import csv
import importlib.util
import io
import os
import subprocess
import sys
import types
from pathlib import Path

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]


def _load_three_worlds():
    spec = importlib.util.spec_from_file_location(
        "three_worlds", ROOT / "scripts" / "three_worlds.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _source_environment():
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src")
    return environment


@pytest.mark.parametrize(
    ("script", "arguments", "expected_fragment"),
    [
        ("bias_tolerance.py", ["--bank", "missing.npz"],
         "fisher_bank_chime2022_pres_dense.npz"),
        ("plot_convergence.py", ["--bank", "missing.npz"],
         "fisher_bank_chime2022_pres_dense.npz"),
        ("three_worlds.py", ["--bank-dir", "missing"],
         "fisher_bank_chime2022_pres_dense.npz"),
    ],
)
def test_bias_workflows_fail_with_exact_build_prerequisite(
        tmp_path, script, arguments, expected_fragment):
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), *arguments],
        cwd=tmp_path, env=_source_environment(), text=True,
        capture_output=True, check=False)

    assert completed.returncode == 2
    assert "Bias-response banks are deliberately not shipped" in completed.stderr
    assert "--config chime2022 --cosmology planck2018" in completed.stderr
    assert "--p-res 1.0" in completed.stderr
    if script in ("plot_convergence.py", "three_worlds.py"):
        assert "--epsilon-fg 0" in completed.stderr
    assert expected_fragment in completed.stderr


def test_three_worlds_help_lists_all_four_strict_v2_prerequisites():
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "three_worlds.py"), "--help"],
        cwd=ROOT, env=_source_environment(), text=True,
        capture_output=True, check=False)

    assert completed.returncode == 0
    assert completed.stdout.count("--epsilon-fg 0") == 4
    for suffix in ("pres_dense.npz", "pres_kfg22_dense.npz",
                   "pres_kfg44_dense.npz", "pres_kfg80_dense.npz"):
        assert suffix in completed.stdout


def test_three_worlds_rejects_a_nonzero_foreground_bank(
        tmp_path, monkeypatch):
    module = _load_three_worlds()
    path = tmp_path / "bank.npz"
    path.touch()
    bank = types.SimpleNamespace(
        artifact_kind=module.bt.ARTIFACT_BIAS_RESPONSE,
        paramnames=[module.bt.PRES],
        meta={
            "config": "chime2022",
            "cosmology": "planck2018",
            "astrophysical_model_profile": "chime_overview_2022",
            "expt_overrides": {"P_res": 1.0},
            "foreground_settings": {"epsilon_fg": 1e-6},
            "provenance": {"experiment": {"settings": {"P_res": 1.0}}},
        },
    )
    monkeypatch.setattr(module.bt, "FisherBank", lambda _path: bank)

    with pytest.raises(ValueError, match=r"epsilon_fg must equal 0\.0"):
        module.bt.load_bias_bank(path, expected_kfg_fac=None,
                                 expected_epsilon_fg=0.0)


def _world_bank(module, response=1.0, t_grid=None):
    return types.SimpleNamespace(
        t_grid=(module.EXPECTED_DENSE_GRID.copy()
                if t_grid is None else t_grid),
        meta={
            "expt_overrides": {"P_res": response},
            "provenance": {"experiment": {"settings": {
                "P_res": response}}},
        },
    )


def test_three_worlds_rejects_a_named_response_bank():
    module = _load_three_worlds()
    with pytest.raises(ValueError, match="scalar P_res=1.0"):
        module.validate_world_bank(
            _world_bank(module, {"family": "low_kparallel"}))


def test_three_worlds_rejects_a_nondense_grid():
    module = _load_three_worlds()
    with pytest.raises(ValueError, match="27-point --dense-knee"):
        module.validate_world_bank(
            _world_bank(module, t_grid=np.logspace(0.0, 6.0, 19)))


def test_three_worlds_records_bank_identity(tmp_path):
    module = _load_three_worlds()
    path = tmp_path / "bank.npz"
    path.write_bytes(b"bank")
    bank = types.SimpleNamespace(
        t_grid=module.EXPECTED_DENSE_GRID,
        meta={
            "schema_version": 2,
            "foreground_settings": {"kfg_fac": 44.0, "epsilon_fg": 0},
            "provenance": {
                "experiment": {"settings": {"P_res": 1.0}},
                "baonoise": {"git_commit": "a" * 40,
                              "working_tree_sha256": "b" * 64},
                "radiofisher": {"git_commit": "c" * 40,
                                "working_tree_sha256": "d" * 64},
            },
        },
    )

    identity = module.bank_identity(path, bank)

    assert identity["bank_file"] == "bank.npz"
    assert identity["bank_sha256"] == (
        "4381dc2ab14285160c808659aee005d51255add7264b318d07c7417292c7442c")
    assert identity["bank_kfg_fac"] == 44.0
    assert identity["bank_epsilon_fg"] == 0
    assert identity["bank_p_res"] == 1.0
    assert identity["bank_grid_points"] == 27


def test_three_worlds_failed_write_keeps_the_existing_file(tmp_path):
    module = _load_three_worlds()
    path = tmp_path / "worlds.csv"
    path.write_text("original\n", encoding="utf-8")

    with pytest.raises(ValueError, match="dict contains fields"):
        module.write_rows(path, [{"value": 1}, {"extra": 2}])

    assert path.read_text(encoding="utf-8") == "original\n"


@pytest.mark.parametrize(
    "channel, off_from, quality, capped",
    [(32, "2023-02", "refused", True),
     (35, None, "bounded_above", False)],
)
def test_three_worlds_uses_the_on_era_for_signoff_channels(
        monkeypatch, channel, off_from, quality, capped):
    module = _load_three_worlds()
    calls = []

    monkeypatch.setattr(
        module.R, "kept_frame_floor", lambda path: (-40.0, "measured"))
    monkeypatch.setattr(module, "eta1_population", lambda path, ch: (80, 100))
    monkeypatch.setattr(module, "floor_details",
                        lambda path, ch: ("test era", 80))
    monkeypatch.setattr(module, "file_sha256", lambda path: "a" * 64)

    def sweep(path, **kwargs):
        calls.append(("sweep", kwargs["off_from"]))
        return [{"r_masked": 2.0}]

    def correlation(path, **kwargs):
        calls.append(("correlation", kwargs["off_from"]))
        return types.SimpleNamespace(quality=quality, reason="test reason")

    monkeypatch.setattr(module.R, "threshold_sweep", sweep)
    monkeypatch.setattr(module.R, "correlation_time", correlation)

    result = module.channel_r_eta1("product.npz", channel)

    assert result == {
        "r_fine": pytest.approx(0.2),
        "residual_status": "evaluated",
        "n_eta1_kept": 80,
        "n_eta1_valid": 100,
        "product_file": "product.npz",
        "product_sha256": "a" * 64,
        "floor_epoch": "test era",
        "floor_frames": 80,
        "floor_db": -40.0,
        "floor_evidence": "measured",
        "tau_quality": quality,
        "tau_reason": "test reason",
    }
    assert (result["tau_quality"] == "refused") is capped
    assert calls == [("sweep", off_from), ("correlation", off_from)]


def test_three_worlds_reports_an_empty_eta1_population(monkeypatch):
    module = _load_three_worlds()
    monkeypatch.setattr(
        module.R, "kept_frame_floor", lambda path: (-40.0, "measured"))
    monkeypatch.setattr(
        module, "eta1_population", lambda path, ch: (16, 8359))
    monkeypatch.setattr(module.R, "threshold_sweep", lambda path, **kwargs: [])
    monkeypatch.setattr(
        module.R, "correlation_time",
        lambda path, **kwargs: types.SimpleNamespace(
            quality="measured", reason=""))
    monkeypatch.setattr(module, "floor_details",
                        lambda path, ch: ("test era", 80))
    monkeypatch.setattr(module, "file_sha256", lambda path: "a" * 64)

    assert module.channel_r_eta1("product.npz", 32) == {
        "r_fine": None,
        "residual_status": "insufficient_kept_frames",
        "n_eta1_kept": 16,
        "n_eta1_valid": 8359,
        "product_file": "product.npz",
        "product_sha256": "a" * 64,
        "floor_epoch": "test era",
        "floor_frames": 80,
        "floor_db": -40.0,
        "floor_evidence": "measured",
        "tau_quality": "measured",
        "tau_reason": "",
    }


def test_three_worlds_serializes_refused_verdicts_as_blank():
    module = _load_three_worlds()
    result = {
        "n_eta1_kept": 16, "n_eta1_valid": 8359,
        "product_file": "568.npz", "product_sha256": "a" * 64,
        "floor_epoch": "from 2023-02", "floor_frames": 80,
        "floor_db": -40.0, "floor_evidence": "measured",
        "tau_quality": "bounded_above", "tau_reason": "shortest lag",
    }
    bank_info = {
        "bank_file": "bank.npz", "bank_sha256": "b" * 64,
        "bank_schema": 2, "bank_source_commit": "c" * 40,
        "bank_source_sha256": "d" * 64,
        "bank_backend_commit": "e" * 40,
        "bank_backend_sha256": "f" * 64, "bank_kfg_fac": "",
        "bank_epsilon_fg": 0, "bank_p_res": 1.0,
        "bank_grid_points": 27,
    }
    row = module.unavailable_row(
        "none", 0.0, 32, False, "insufficient_kept_frames",
        result, {p: 0.1 for p in module.PARAMS}, bank_info)
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=list(row))
    writer.writeheader()
    writer.writerow(row)
    saved = next(csv.DictReader(io.StringIO(stream.getvalue())))

    assert saved["residual_status"] == "insufficient_kept_frames"
    assert saved["n_eta1_kept"] == "16"
    assert saved["n_eta1_valid"] == "8359"
    assert saved["min_eta1_kept"] == "30"
    assert saved["r_fine"] == ""
    assert saved["floor_evidence"] == "measured"
    assert saved["product_sha256"] == "a" * 64
    assert saved["bank_sha256"] == "b" * 64
    assert saved["tau_quality"] == "bounded_above"
    assert all(saved[f"pass_{p}"] == "" for p in module.PARAMS)


def test_bias_workflow_rejects_an_ordinary_forecast_bank():
    forecast_bank = ROOT / "src" / "rfisher" / "data" \
        / "fisher_bank_chime2022.npz"
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "bias_tolerance.py"),
         "--bank", str(forecast_bank)],
        cwd=ROOT, env=_source_environment(), text=True,
        capture_output=True, check=False)

    assert completed.returncode == 2
    assert "artifact_kind must be 'bias_response'" in completed.stderr
    assert "--p-res 1.0 --dense-knee" in completed.stderr
