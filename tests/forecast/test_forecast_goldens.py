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
float is held to a relative 1e-12 instead. Exact floats also need the CPU
paths that reproduce them. For OpenBLAS, Haswell and Zen do, while Sandybridge
and Nehalem change the last bit of some values, so CI pins
OPENBLAS_CORETYPE=Haswell. For numpy, the goldens were recorded under its
X86_V3 dispatch on a machine without AVX-512, so CI also pins
NPY_ENABLE_CPU_FEATURES=X86_V3. A failure reports how many values differ and
the largest differences, but the check itself stays exact.
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


def _is_float(value):
    return isinstance(value, dict) and set(value) == {"repr", "hex"}


def differences(got, recorded, path=""):
    """Each (path, got, recorded) where got is not the recorded value."""
    if _is_float(recorded) or not isinstance(recorded, (dict, list)):
        if not same(got, recorded):
            yield path, got, recorded
    elif isinstance(recorded, dict) and isinstance(got, dict):
        for key in sorted(set(recorded) | set(got), key=str):
            yield from differences(got.get(key), recorded.get(key),
                                   f"{path}/{key}")
    elif (isinstance(recorded, list) and isinstance(got, list)
          and len(got) == len(recorded)):
        for i, (a, b) in enumerate(zip(got, recorded)):
            yield from differences(a, b, f"{path}[{i}]")
    else:
        yield path, got, recorded


def _leaves(recorded):
    if isinstance(recorded, dict) and not _is_float(recorded):
        return sum(_leaves(v) for v in recorded.values())
    if isinstance(recorded, list):
        return sum(_leaves(v) for v in recorded)
    return 1


def _gap(got, recorded):
    """Absolute, relative and last-place difference of two recorded floats."""
    a, b = float(got["repr"]), float(recorded["repr"])
    if not (math.isfinite(a) and math.isfinite(b)):
        return (0.0, 0.0, 0.0) if repr(a) == repr(b) else (math.inf,) * 3
    d = abs(a - b)
    return (d, d / abs(b) if b else (0.0 if d == 0 else math.inf),
            d / math.ulp(b))


def report(got, recorded):
    """How far got is from the recorded values, for a failure message only."""
    try:
        from numpy._core import _multiarray_umath as mu
        found = [f for f in mu.__cpu_dispatch__ if mu.__cpu_features__.get(f)]
    except (ImportError, AttributeError):
        found = "unknown"
    lines = [f"numpy {np.__version__}, scipy {scipy.__version__}, "
             f"exact={EXACT}, numpy dispatch {found}, "
             f"OPENBLAS_CORETYPE={os.environ.get('OPENBLAS_CORETYPE')}, "
             f"NPY_ENABLE_CPU_FEATURES="
             f"{os.environ.get('NPY_ENABLE_CPU_FEATURES')}"]
    diffs = list(differences(got, recorded))
    floats = [(p, _gap(g, r)) for p, g, r in diffs
              if _is_float(g) and _is_float(r)]
    lines.append(f"{len(diffs)} of {_leaves(recorded)} recorded values differ: "
                 f"{len(floats)} floats, {len(diffs) - len(floats)} other")
    groups = {}
    for path, gap in floats:
        groups.setdefault(path.split("/")[1] if "/" in path else path,
                          []).append((path, gap))
    for name, items in [("all", floats)] + sorted(groups.items()):
        if not items:
            continue
        worst_abs = max(items, key=lambda item: item[1][0])
        worst_rel = max(items, key=lambda item: item[1][1])
        lines.append(f"  {name}: {len(items)} floats differ, largest absolute "
                     f"{worst_abs[1][0]:.3e} at {worst_abs[0]}, largest "
                     f"relative {worst_rel[1][1]:.3e} ({worst_rel[1][2]:.1f} "
                     f"ulp) at {worst_rel[0]}")
    for path, g, r in diffs[:5]:
        lines.append(f"  {path}: got {g!r}, recorded {r!r}")
    return "\n".join(lines)


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
    got = evaluate(fc, len(fc.bank.zc))
    recorded = GOLDENS["results"][cosmology]
    assert same(got, recorded), report(got, recorded)


@pytest.mark.parametrize("key", sorted(key for key in GOLDENS["cli"]
                                       if not key.startswith("bull")))
def test_the_forecast_command_prints_the_recorded_json(key):
    got = run_command(GOLDENS["cli"][key]["argv"])
    recorded = GOLDENS["cli"][key]
    assert got["returncode"] == recorded["returncode"] == 0
    got, recorded = _floats(got["stdout"]), _floats(recorded["stdout"])
    assert same(got, recorded), report(got, recorded)


def test_the_shared_amplitude_path_is_the_recorded_floats():
    try:
        find_radiofisher_dir()
    except FileNotFoundError:
        pytest.skip("the Bull-2015 path needs RadioFisher; set RADIOFISHER_DIR")
    fc = api.load(bank=ROOT / "data" / "fisher_bank_bull2015_planck2013_epsfg1e-6.npz")
    assert fc.style == "shared_A"
    got = evaluate(fc, len(fc.bank.zc))
    recorded = GOLDENS["results"][BULL]
    assert same(got, recorded), report(got, recorded)
    recorded = GOLDENS["cli"]["bull2015_bank_uniform0.3"]
    got = run_command(recorded["argv"])
    assert got["returncode"] == recorded["returncode"] == 0
    got, recorded = _floats(got["stdout"]), _floats(recorded["stdout"])
    assert same(got, recorded), report(got, recorded)
