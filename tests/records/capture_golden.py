"""The golden capture handoff and helpers for the capture record tests."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path

import numpy as np
from numpy.lib import NumpyVersion

GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "handoff" / "capture"
SOURCE = json.loads((GOLDEN / "SOURCE.json").read_text())


def sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def quiet(fn, args):
    """Run a record's main in process; return its stdout."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert not fn(args)
    return buf.getvalue()


# The capture records are byte for byte under the numerics of record (numpy 2.3 and later: the r5.2 interpreter's
# 2.3.5, 2.5 in the release's and CI's 3.12 and 3.14 jobs). An older numpy (the 3.10 job's 2.2) gives the same tables
# but other last digits in the unrounded json; there the tables are still compared byte for byte and only the
# comparison of the other files is skipped.
RECORD_NUMERICS = NumpyVersion(np.__version__) >= "2.3.0"
TABLE_SUFFIXES = (".csv",)
DURATION = GOLDEN.parents[1] / "records" / "survey_duration_2026-09-24"


def assert_frozen(got, expected, detail=None):
    if got == expected:
        return
    if not RECORD_NUMERICS:
        import pytest
        if isinstance(expected, dict):
            tables = sorted(k for k in expected if str(k).endswith(TABLE_SUFFIXES) and got.get(k) != expected[k])
            assert not tables, f"tables differ under numpy {np.__version__}: {tables}"
        differ = sorted(k for k in expected if got.get(k) != expected[k]) if isinstance(expected, dict) else "the file"
        pytest.skip(f"byte identity is asserted under numpy >= 2.3, the numerics of record; numpy {np.__version__} "
                    f"differs in {differ}")
    assert got == expected, detail


def duration_reference(tmp_path) -> Path:
    """The survey-duration run's values the duration reading checks its banks against: the vendored ones, or, under
    other numerics, the same cells recomputed from the same banks by the reading's own formulas."""
    if RECORD_NUMERICS:
        return DURATION
    import csv
    import shutil

    from rfisher import policy
    from rfisher.forecast.radiofisher_bao import filter_scenarios
    from rfisher.forecast.radiofisher_bao import response as bt
    from rfisher.forecast.radiofisher_bao.bank.experiments import OVERVIEW_ONSKY_YEAR_HOURS as HPY
    from rfisher.records.chime_atsc_2026 import capture_units as U

    out = Path(tmp_path) / "duration_reference"
    out.mkdir()
    shutil.copy(DURATION / "ruling_factors.csv", out / "ruling_factors.csv")
    frac = float(policy.value("science.response_stability.time_fraction"))
    limit = float(policy.value("science.response_stability.maximum_tolerance_ratio"))
    scenario = next(s for s in filter_scenarios.SCENARIOS if s.name == "none")
    bank = bt.load_response_bank(bt.packaged_response_banks() / scenario.bank, build_command="see scripts/three_worlds.py",
                                 expected_kfg_fac=scenario.kfg_fac, expected_epsilon_fg=0.0)
    names = list(bank.paramnames)
    years = (1.0, 2.0, 3.0, 5.0, 8.0, 10.0)
    bins = {b for ch in range(14, 37) for b in U.bin_overlaps(ch)}

    def cell(ib, y, p):
        t = y * HPY; dth, sig = bt.bias_per_unit_residual(bank.F(ib, t), names)
        drift, nsign = bt.response_stability(bank, ib, t, names, p, frac=frac)
        return float(sig[p] / abs(dth[p])), bool(drift <= limit and nsign == 1)
    for name in ("bin_sigma_lambda.csv", "channel_lambda.csv"):
        with open(DURATION / name, newline="") as fh:
            reader = csv.DictReader(fh); fields = reader.fieldnames; rows = list(reader)
        for r in rows:
            if r["world"] != "none":
                continue
            if name == "bin_sigma_lambda.csv" and float(r["years"]) in years and int(r["bin"]) in bins:
                lam, acc = cell(int(r["bin"]), float(r["years"]), r["param"])
                r["lam_raw"], r["accepted"] = repr(lam), str(acc)
            elif name == "channel_lambda.csv":
                for y in years:
                    r[f"lamraw_{y:g}yr"] = repr(min(cell(b, y, p)[0] for b in U.bin_overlaps(int(r["channel"]))
                                                    for p in ("aperp", "apar")))
        with open(out / name, "w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    return out
