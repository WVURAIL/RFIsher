"""Explicit record inputs keep their frozen identity unless a run declares otherwise."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from capture_golden import record_input, sha256
from rfisher.records.chime_atsc_2026 import capture_handoff as ch
from rfisher.records.chime_atsc_2026 import capture_release, phase_limit, robustness, table_of_record


@pytest.mark.parametrize("name", sorted(ch.RECORD_SHA256))
def test_frozen_pin_checks_the_bytes_and_logs_the_input(name, tmp_path, capsys):
    path = record_input(name)
    rel = "frame_analysis/" + name
    rows = ch.table_rows(None, rel, path)
    provenance = json.loads(capsys.readouterr().err)
    assert provenance == {"record_input": str(path), "table": rel, "sha256": sha256(path), "mode": "frozen"}
    changed = tmp_path / name
    changed.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ch.HandoffError, match="sha256 differs from the frozen"):
        ch.table_rows(None, rel, changed)
    assert ch.table_rows(None, rel, changed, in_run=True) == rows
    provenance = json.loads(capsys.readouterr().err)
    assert provenance["sha256"] == sha256(changed) and provenance["mode"] == "in_run"
    changed.write_text("wrong,columns\n1,2\n")
    with pytest.raises(ch.HandoffError, match="columns differ"):
        ch.table_rows(None, rel, changed, in_run=True)


def test_missing_record_input_has_a_clear_error(tmp_path):
    with pytest.raises(ch.HandoffError, match="cannot read"):
        ch.table_rows(None, "frame_analysis/table_of_record.csv", tmp_path / "missing.csv")


@pytest.mark.parametrize("module", [robustness, phase_limit])
def test_record_commands_require_an_explicit_in_run_declaration(module, capture_handoff_dir, tmp_path, capsys):
    changed = tmp_path / "record.csv"
    changed.write_bytes(record_input("table_of_record.csv").read_bytes() + b"\n")
    out = tmp_path / "out"
    args = ["--handoff", str(capture_handoff_dir), "--record-table", str(changed), str(out)]
    with pytest.raises(ch.HandoffError, match="sha256 differs"):
        module.main(args)
    assert not out.exists()
    if module is phase_limit:
        out.mkdir()
    assert module.main([*args, "--in-run-record-table"]) == 0
    logs = [json.loads(line) for line in capsys.readouterr().err.splitlines()]
    assert logs[-1]["mode"] == "in_run" and logs[-1]["sha256"] == sha256(changed)


@pytest.mark.parametrize("altered", ["table_of_record.csv", "table_of_record_before_amendment8.csv"])
def test_release_rejects_either_changed_input_before_writing(altered, capture_handoff_dir, tmp_path):
    inputs = {name: record_input(name) for name in ch.RECORD_SHA256}
    changed = tmp_path / altered
    changed.write_bytes(inputs[altered].read_bytes() + b"\n")
    inputs[altered] = changed
    rel, run = tmp_path / "rel", tmp_path / "run"
    args = ["--handoff", str(capture_handoff_dir), "--record-table", str(inputs["table_of_record.csv"]),
            "--input-table", str(inputs["table_of_record_before_amendment8.csv"]), "--rel", str(rel),
            "--run", str(run), "--evidence", "unused", "--releases", "unused", "--duration-reference", "unused",
            "--tables-only", "--credit-reading", "r3"]
    with pytest.raises(ch.HandoffError, match="sha256 differs"):
        capture_release.main(args)
    assert not rel.exists() and not run.exists()


def test_custom_specs_do_not_require_an_unused_gain_table(capture_handoff_dir, tmp_path):
    out = tmp_path / "table.csv"
    assert table_of_record.main(["--handoff", str(capture_handoff_dir), "--out", str(out),
                                "pilot=frame_residual_20260916162300.csv:20260916162300"]) == 0
    assert out.is_file()


def test_custom_bao_path_is_explicit_and_logged(capture_handoff_dir, tmp_path, monkeypatch, capsys):
    custom = tmp_path / "custom.csv"
    custom.write_bytes(record_input("gain_bao.csv").read_bytes() + b"\n")
    monkeypatch.chdir(tmp_path)
    assert table_of_record.main(["--handoff", str(capture_handoff_dir), "--out", "table.csv", "bao=custom.csv"]) == 0
    provenance = json.loads(capsys.readouterr().err)
    assert provenance["record_input"] == "custom.csv"
    assert provenance["mode"] == "in_run" and provenance["sha256"] == sha256(custom)
    assert Path("table.csv").is_file()


def test_default_specs_reject_changed_gain_table(capture_handoff_dir, tmp_path):
    changed = tmp_path / "gain.csv"
    changed.write_bytes(record_input("gain_bao.csv").read_bytes() + b"\n")
    out = tmp_path / "table.csv"
    with pytest.raises(ch.HandoffError, match="sha256 differs"):
        table_of_record.main(["--handoff", str(capture_handoff_dir), "--gain-bao", str(changed), "--out", str(out)])
    assert not out.exists()
