"""Fail-closed prerequisites of the response report (``rfisher tolerance bias``)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
COMMAND = [sys.executable, "-m", "rfisher.cli", "tolerance", "bias"]


def _source_environment():
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src")
    return environment


@pytest.mark.parametrize(
    ("command", "arguments", "expected_fragment"),
    [
        ("tolerance bias", ["--bank", "missing.npz"],
         "fisher_bank_chime2022_pres_dense.npz"),
    ],
)
def test_bias_workflows_fail_with_exact_build_prerequisite(
        tmp_path, command, arguments, expected_fragment):
    completed = subprocess.run(
        [*COMMAND, *arguments],
        cwd=tmp_path, env=_source_environment(), text=True,
        capture_output=True, check=False)

    assert completed.returncode == 2
    assert "Only the four filter-scenario response banks are packaged" \
        in completed.stderr
    assert "--config chime2022 --cosmology planck2018" in completed.stderr
    assert "--p-res 1.0" in completed.stderr
    assert expected_fragment in completed.stderr


def test_bias_workflow_rejects_an_ordinary_forecast_bank():
    forecast_bank = ROOT / "src" / "rfisher" / "data" \
        / "fisher_bank_chime2022.npz"
    completed = subprocess.run(
        [*COMMAND, "--bank", str(forecast_bank)],
        cwd=ROOT, env=_source_environment(), text=True,
        capture_output=True, check=False)

    assert completed.returncode == 2
    assert "artifact_kind must be 'bias_response'" in completed.stderr
    assert "--p-res 1.0 --dense-knee" in completed.stderr
