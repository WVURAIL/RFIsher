"""Study receipts must survive interruptions without accepting changed results."""

import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "nonlinear_runner", Path(__file__).parents[1] / "tools" / "check_nonlinear_bias.py"
)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def test_result_rejects_changed_numerical_payload(tmp_path):
    path = tmp_path / "fit.json"
    runner.write(path, {"execution_sha256": "execution", "theta": [1.0, 49.0, 1.0, 1.0]})
    assert runner.load_bound(path, "execution")["theta"][1] == 49.0
    value = json.loads(path.read_text())
    value["theta"][1] = 50.0
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="payload"):
        runner.load_bound(path, "execution")


def test_result_rejects_another_execution_or_point_filename(tmp_path):
    path = tmp_path / "point_a.json"
    runner.write(path, {"execution_sha256": "execution", "theta": [1.0]})
    with pytest.raises(ValueError, match="another execution"):
        runner.load_bound(path, "other")
    copied = tmp_path / "point_b.json"
    copied.write_bytes(path.read_bytes())
    with pytest.raises(ValueError, match="filename"):
        runner.load_bound(copied, "execution")


def test_completed_result_is_not_overwritten_and_orphan_temp_does_not_block(tmp_path):
    path = tmp_path / "fit.json"
    (tmp_path / "fit.json.interrupted.tmp").write_text("partial")
    runner.write(path, {"execution_sha256": "execution", "theta": [1.0]})
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        runner.write(path, {"execution_sha256": "execution", "theta": [2.0]})
    assert path.read_bytes() == before


def test_snapshot_verifies_non_executed_frozen_inputs_too(tmp_path):
    path = tmp_path / "paper" / "data.json"
    path.parent.mkdir()
    path.write_text('{"guard": 1}')
    protocol = {"provenance": {"files": {"paper/data.json": {"sha256": runner.file_sha256(path)}}}}
    assert runner.verify_frozen_sources(protocol, tmp_path)["paper/data.json"] == runner.file_sha256(path)
    path.write_text('{"guard": 2}')
    with pytest.raises(ValueError, match="snapshot"):
        runner.verify_frozen_sources(protocol, tmp_path)
