"""The forecast values recorded at RFIsher e041d5e, reproduced as exact floats.

The goldens cover three packaged cosmologies, four masking scenarios and three
on-sky times through the API (significance, required time, per-bin errors and
the masking-cost curve), the output of ``rfisher forecast``, and one Bull-2015
bank on the shared-amplitude path through RadioFisher. The packaged banks
evaluate without RadioFisher: bound and unbound loads agreed exactly when the
goldens were recorded.

The floats are exact under the numpy and scipy series the goldens were
recorded with (numpy 2.5, scipy 1.18: the release interpreter, and CI on
Python 3.12 and 3.14). An older series, such as the newest numpy that still
supports Python 3.10, differs in the last bit of some values, so there every
float is held to a relative 1e-12 instead. Exact floats also need an OpenBLAS
kernel that reproduces them: Haswell and Zen do, while Sandybridge and Nehalem
change the last bit of some values, so CI pins OPENBLAS_CORETYPE=Haswell.
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import scipy

from rfisher.forecast.radiofisher_bao import api
from rfisher.forecast.radiofisher_bao import scenarios as sc
from rfisher.forecast.radiofisher_bao.bank.backend import find_radiofisher_dir

ROOT = Path(__file__).resolve().parents[2]
GOLDENS = json.loads((ROOT / "tests" / "golden" / "forecast_goldens.json")
                     .read_text(encoding="utf-8"))
YEARS = tuple(GOLDENS["grid"]["years"])
MASK = {int(k): v for k, v in GOLDENS["grid"]["mask"].items()}
RESIDUALS = {int(k): v for k, v in GOLDENS["grid"]["residuals"].items()}
BULL = "bull2015_planck2013_epsfg1e-6"


def _series(version):
    return version.split(".")[:2]


EXACT = (_series(np.__version__) == _series(GOLDENS["numerics"]["numpy"])
         and _series(scipy.__version__) == _series(GOLDENS["numerics"]["scipy"]))


def same(got, recorded):
    """Equal as recorded: exact floats, or floats within 1e-12 off the series."""
    if EXACT:
        return got == recorded
    if isinstance(recorded, dict) and set(recorded) == {"repr", "hex"}:
        if not isinstance(got, dict) or set(got) != {"repr", "hex"}:
            return False
        a, b = float(got["repr"]), float(recorded["repr"])
        return a == b or math.isclose(a, b, rel_tol=1e-12, abs_tol=0.0)
    if isinstance(recorded, dict):
        return (isinstance(got, dict) and set(got) == set(recorded)
                and all(same(got[k], recorded[k]) for k in recorded))
    if isinstance(recorded, list):
        return (isinstance(got, list) and len(got) == len(recorded)
                and all(same(a, b) for a, b in zip(got, recorded)))
    return got == recorded


def fx(x):
    x = float(x)
    return ({"repr": repr(x), "hex": x.hex()} if math.isfinite(x)
            else {"repr": repr(x), "hex": repr(x)})


def safe(fn, *a, **kw):
    try:
        return fx(fn(*a, **kw))
    except Exception as exc:
        return {"raises": type(exc).__name__, "message": str(exc)}


def evaluate(fc, nbins):
    grid = {
        "S1_clean": dict(mask=sc.clean()),
        "S2_uniform_dtv_0.3": dict(uniform=0.3),
        "S3_mask_default_excision": dict(mask=dict(MASK)),
        "S4_mask_with_residuals": dict(mask=dict(MASK),
                                       residuals=dict(RESIDUALS)),
    }
    out = {}
    for name, kw in grid.items():
        cell = {"significance": {}, "required_time": None,
                "per_bin_error_dv_1yr": [], "per_bin_error_fs8_1yr": []}
        for y in YEARS:
            cell["significance"][repr(y)] = fx(api.significance(fc, y, **kw))
        rt = api.required_time(fc, **kw)
        cell["required_time"] = {k: (fx(v) if isinstance(v, float) else v)
                                 for k, v in sorted(rt.items())}
        for ib in range(nbins):
            cell["per_bin_error_dv_1yr"].append(
                safe(api.per_bin_error, fc, 1.0, ib, param="dv", **kw))
            cell["per_bin_error_fs8_1yr"].append(
                safe(api.per_bin_error, fc, 1.0, ib, param="fs8", **kw))
        out[name] = cell
    fr, yrs = api.masking_cost_curve(fc)
    out["masking_cost_curve_dtv"] = {"fracs": [fx(f) for f in fr],
                                     "years": [fx(v) for v in yrs]}
    return out


def _floats(stdout):
    """The command's JSON with every float as an exact record, and its text."""
    decoded = json.loads(stdout)
    return {"text": stdout if EXACT else None,
            "values": {k: (fx(v) if isinstance(v, float) else v)
                       for k, v in decoded.items()}}


def run_command(argv):
    code = ("import sys; from rfisher.cli import forecast_main as m; "
            f"sys.exit(m({argv!r}))")
    completed = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, capture_output=True,
        text=True, env={**os.environ, "PYTHONPATH": str(ROOT / "src")})
    return {"argv": argv, "returncode": completed.returncode,
            "stdout": completed.stdout}


@pytest.mark.parametrize("cosmology", GOLDENS["grid"]["cosmologies"])
def test_packaged_bank_forecasts_are_the_recorded_floats(cosmology):
    assert GOLDENS["binding"][cosmology] == "identical"
    fc = api.load(cosmology=cosmology)
    assert fc.style == "perbin_A"
    assert same(evaluate(fc, len(fc.bank.zc)), GOLDENS["results"][cosmology])


@pytest.mark.parametrize("key", sorted(key for key in GOLDENS["cli"]
                                       if not key.startswith("bull")))
def test_the_forecast_command_prints_the_recorded_json(key):
    got = run_command(GOLDENS["cli"][key]["argv"])
    recorded = GOLDENS["cli"][key]
    assert got["returncode"] == recorded["returncode"] == 0
    assert same(_floats(got["stdout"]), _floats(recorded["stdout"]))


def test_the_shared_amplitude_path_is_the_recorded_floats():
    try:
        find_radiofisher_dir()
    except FileNotFoundError:
        pytest.skip("the Bull-2015 path needs RadioFisher; set RADIOFISHER_DIR")
    fc = api.load(bank=ROOT / "data" / "fisher_bank_bull2015_planck2013_epsfg1e-6.npz")
    assert fc.style == "shared_A"
    assert same(evaluate(fc, len(fc.bank.zc)), GOLDENS["results"][BULL])
    recorded = GOLDENS["cli"]["bull2015_bank_uniform0.3"]
    got = run_command(recorded["argv"])
    assert got["returncode"] == recorded["returncode"] == 0
    assert same(_floats(got["stdout"]), _floats(recorded["stdout"]))
