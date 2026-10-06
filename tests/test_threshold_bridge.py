"""The threshold-calibration bridge's scenario evaluator reproduces its recorded zero-residual scenario.

scripts/threshold_calibration_bridge/ holds byte copies of the package's two producers. The bridge itself needs the
native paired-mode forecast and a RadioFisher checkout outside this repository, so only its recorded identity is
checked. The evaluator is rerun on the 24 input rows of the package's CLEAN_LIMIT_CURRENT.json (vendored with the
sha256 of the REGIONS.json they come from) and must give the recorded rows and candidates exactly.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts" / "threshold_calibration_bridge"
GOLDEN = ROOT / "tests" / "golden" / "threshold_bridge"


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _inputs():
    return json.loads((GOLDEN / "clean_limit_inputs.json").read_text())


def _evaluator():
    spec = importlib.util.spec_from_file_location("evaluate_scenario", SCRIPTS / "evaluate_scenario.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_copies_are_the_recorded_sources():
    inputs = _inputs()
    assert _sha(SCRIPTS / "threshold_bridge.py") == inputs["threshold_bridge_sha256"] == inputs["regions_source_sha256"]
    assert _sha(SCRIPTS / "evaluate_scenario.py") == inputs["evaluator_sha256"]
    assert _sha(GOLDEN / "CLEAN_LIMIT_CURRENT.json") == inputs["clean_limit_sha256"]


def test_the_zero_residual_scenario_is_reproduced():
    inputs = _inputs()
    recorded = json.loads((GOLDEN / "CLEAN_LIMIT_CURRENT.json").read_text())
    assert recorded["provenance"]["regions_sha256"] == inputs["regions_sha256"]
    assert recorded["provenance"]["evaluator_sha256"] == inputs["evaluator_sha256"]
    assert (recorded["model"], recorded["shape"], recorded["budget_calendar_years"]) == (
        "independent_averaging_covariance", "noise_shaped", 10)
    assert recorded["declared_constant_coefficient"] == recorded["declared_score_coefficient"] == 0
    evaluator = _evaluator()
    rows = [evaluator.evaluate(r, 0.0, 0.0) for r in inputs["rows"]]
    assert json.loads(json.dumps(rows)) == recorded["rows"]
    assert json.loads(json.dumps(evaluator.summarize_budget(rows))) == recorded["candidates"]
    assert all(c["passes_by_budget_on_evaluated_grid"] for c in recorded["candidates"])
    assert len({r["channel"] for r in rows}) == 24
