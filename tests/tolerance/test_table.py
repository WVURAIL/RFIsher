"""The per-bin tolerance table: its layout, its v3 provenance and its reader."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from rfisher.forecast.radiofisher_bao import model as radiofisher_model
from rfisher.forecast.radiofisher_bao import filter_scenarios, response
from rfisher.forecast.radiofisher_bao.bank import banks
from rfisher.science_model import Bin, Parameters, Scenario
from rfisher.tolerance import table

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "projects" / "chime_bao"
COMMITTED = ROOT / "src/rfisher/data/tolerances/filter_scenarios_T1yr.csv"
# The table of both archive releases (author eras 2026-09-23 and no-split r2).
COMMITTED_SHA256 = (
    "3985dd593bbb19904e600e20adbd44248c2449b980bdb27856166c85b298f162")


def _keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _keys(item)


def _inputs():
    return {"sources": {"model.py": "0" * 64}, "profile_sha256": "7" * 64,
            "banks": {"x.npz": {"sha256": "1" * 64,
                                "evaluation_sha256": "2" * 64}}}


def _model(tolerance=0.5, inputs=None):
    inputs = _inputs() if inputs is None else inputs

    def identity(responses=True):
        out = copy.deepcopy(inputs)
        if not responses:
            for entry in out["banks"].values():
                entry.pop("evaluation_sha256", None)
        return out

    return SimpleNamespace(
        parameters=Parameters(("a",), ("c",)), zeta=1.0, target_years=1.0,
        year_grid=(1.0,), maximum_tolerance_ratio=1.2,
        scenarios=(Scenario("none", "rule", 0.0, "x.npz"),),
        load=lambda name: None, bins=lambda: (Bin(0, "z 0.8-0.9", 0.8, 0.9),),
        hours=lambda years: years,
        response=lambda *a: ({"a": 1.0, "c": 1.0},
                             {"a": tolerance, "c": tolerance}),
        accept=lambda *a: (1.0, 1), identity=identity)


def test_the_committed_table_is_the_archive_table():
    assert hashlib.sha256(COMMITTED.read_bytes()).hexdigest() \
        == COMMITTED_SHA256
    record = json.loads(table.sidecar(COMMITTED).read_text())
    assert record["csv_sha256"] == COMMITTED_SHA256
    assert len(table.load(COMMITTED)) == 180


def test_the_committed_provenance_is_identity_v3_without_commits():
    record = json.loads(table.sidecar(COMMITTED).read_text())
    assert record["schema"] == table.IDENTITY_SCHEMA == 3
    assert record["target_years"] == 1.0
    assert not {"git_commit", "git_dirty"} & set(_keys(record))
    assert set(record) == {
        "schema", "target_years", "csv_sha256", "sources", "banks",
        "profile_sha256", "science_register_sha256", "bank_source_sha256"}
    assert set(record["sources"]) == {
        "rfisher/tolerance/rule.py", "rfisher/tolerance/bands.py",
        "rfisher/tolerance/table.py",
        "rfisher/forecast/radiofisher_bao/response.py",
        "rfisher/forecast/radiofisher_bao/filter_scenarios.py",
        "rfisher/forecast/radiofisher_bao/model.py"}
    assert record["bank_source_sha256"] \
        == banks.bank_source_state()["working_tree_sha256"]


def test_a_built_table_has_the_frozen_layout_and_a_v3_sidecar(tmp_path):
    out = tmp_path / "table.csv"
    rows = table.build(_model(), out)
    assert out.read_bytes() == (
        b"world,bin_index,z_lo,z_hi,parameter,tolerance,at_target,"
        b"years_used,years_accepted,years_refused\n"
        b"none,0,0.8,0.9,a,0.5,True,1.0,1,0\n"
        b"none,0,0.8,0.9,c,0.5,True,1.0,1,0\n")
    record = json.loads(table.sidecar(out).read_text())
    assert record["csv_sha256"] == hashlib.sha256(out.read_bytes()).hexdigest()
    assert record["schema"] == 3
    assert "model.py" in record["sources"]
    assert "rfisher/tolerance/rule.py" in record["sources"]
    assert not {"git_commit", "git_dirty"} & set(_keys(record))
    assert table.load(out) == [
        {**{k: str(v) for k, v in row.items()}, **row} for row in rows]


def test_a_rebuild_never_changes_a_table_silently(tmp_path):
    out = tmp_path / "table.csv"
    table.build(_model(0.5), out)
    before = out.read_bytes()
    table.build(_model(0.5), out)                  # same bytes: allowed
    with pytest.raises(ValueError, match="accept_new"):
        table.build(_model(0.25), out)
    assert out.read_bytes() == before
    table.build(_model(0.25), out, accept_new=True)
    assert out.read_bytes() != before


def test_loading_never_opens_a_bank(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("a bank was opened")

    monkeypatch.setattr(response, "load_response_bank", refuse)
    monkeypatch.setattr(banks, "FisherBank", refuse)
    rows = table.load(COMMITTED)
    assert {r["world"] for r in rows} == {"none", "peak1", "peak2", "deployed"}


def test_a_table_without_its_digest_is_refused(tmp_path):
    out = tmp_path / "table.csv"
    table.build(_model(), out)
    out.write_bytes(out.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="csv_sha256"):
        table.load(out)
    table.sidecar(out).unlink()
    with pytest.raises(ValueError, match="no provenance sidecar"):
        table.load(out)


def test_verify_accepts_the_inputs_a_table_was_built_from(tmp_path):
    out = tmp_path / "table.csv"
    table.build(_model(), out)
    table.verify(_model(), out)
    # an evaluation digest needs its bank opened, so only a build checks it
    inputs = _inputs()
    inputs["banks"]["x.npz"]["evaluation_sha256"] = "3" * 64
    table.verify(_model(inputs=inputs), out)


@pytest.mark.parametrize("change,field", [
    (lambda i: i["sources"].update({"model.py": "3" * 64}), "sources/model.py"),
    (lambda i: i["sources"].update({"other.py": "3" * 64}), "sources/other.py"),
    (lambda i: i.update(profile_sha256="4" * 64), "profile_sha256"),
    (lambda i: i["banks"]["x.npz"].update(sha256="5" * 64),
     "banks/x.npz/sha256"),
    (lambda i: i["banks"].pop("x.npz"), "banks/x.npz/sha256"),
    (lambda i: i["banks"].update(y={"sha256": "6" * 64}), "banks/y/sha256"),
])
def test_verify_refuses_a_table_whose_inputs_changed(tmp_path, change, field):
    out = tmp_path / "table.csv"
    table.build(_model(), out)
    inputs = _inputs()
    change(inputs)
    with pytest.raises(ValueError, match=re.escape(field)):
        table.verify(_model(inputs=inputs), out)


def test_verify_refuses_a_changed_table_and_an_older_sidecar(tmp_path):
    out = tmp_path / "table.csv"
    table.build(_model(), out)
    data = out.read_bytes()
    out.write_bytes(data + b"\n")
    with pytest.raises(ValueError, match="csv_sha256"):
        table.verify(_model(), out)
    out.write_bytes(data)
    record = json.loads(table.sidecar(out).read_text())
    table.sidecar(out).write_text(json.dumps(dict(record, schema=2)))
    with pytest.raises(ValueError, match="schema"):
        table.verify(_model(), out)
    table.sidecar(out).unlink()
    with pytest.raises(ValueError, match="no provenance sidecar"):
        table.verify(_model(), out)


def test_the_committed_table_passes_verify_without_opening_a_bank(
        monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("a bank was opened")

    monkeypatch.setattr(response, "load_response_bank", refuse)
    monkeypatch.setattr(radiofisher_model, "load_response_bank", refuse)
    monkeypatch.setattr(banks, "FisherBank", refuse)
    table.verify(radiofisher_model.RadioFisherBAO(PROJECT), COMMITTED)


VERIFY_PROGRAM = """
import json, sys
from pathlib import Path
from rfisher.forecast.radiofisher_bao.model import RadioFisherBAO
from rfisher.tolerance import table
project, bank_dir, csv, mode = sys.argv[1:]
model = RadioFisherBAO(project, response_banks_dir=bank_dir)
if mode == "record":
    table.sidecar(csv).write_text(json.dumps(
        table.identity(model, csv, responses=False)))
try:
    table.verify(model, csv)
    print("current")
except ValueError as exc:
    print(exc)
"""


def test_verify_sees_a_one_byte_edit_to_each_kind_of_input(tmp_path):
    """In a git copy: the tolerance rule, the model, the bank code, the
    profile and a response bank each refuse the table after one byte."""
    root = tmp_path / "repo"
    shutil.copytree(ROOT / "src" / "rfisher", root / "src" / "rfisher",
                    ignore=shutil.ignore_patterns("__pycache__",
                                                  "response_banks"))
    shutil.copytree(PROJECT, root / "projects" / "chime_bao")
    bank_dir = tmp_path / "banks"
    bank_dir.mkdir()
    for item in filter_scenarios.SCENARIOS:
        (bank_dir / item.bank).write_bytes(item.name.encode())
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
    csv_path = tmp_path / "table.csv"
    csv_path.write_text("world\n")
    env = {key: value for key, value in os.environ.items()
           if key != "PYTHONPATH"}
    env.update(PYTHONPATH=str(root / "src"), PYTHONDONTWRITEBYTECODE="1")

    def verify(mode="check"):
        return subprocess.run(
            [sys.executable, "-c", VERIFY_PROGRAM, str(root / "projects" /
             "chime_bao"), str(bank_dir), str(csv_path), mode],
            env=env, check=True, capture_output=True, text=True).stdout

    assert verify("record").strip() == "current"
    edits = {
        root / "src/rfisher/tolerance/rule.py":
            "sources/rfisher/tolerance/rule.py",
        root / "src/rfisher/forecast/radiofisher_bao/model.py":
            "sources/rfisher/forecast/radiofisher_bao/model.py",
        root / banks.BANK_SOURCE_DIRECTORY / "physics.py":
            "bank_source_sha256",
        root / "projects/chime_bao/science_model.yaml": "profile_sha256",
        bank_dir / filter_scenarios.SCENARIOS[0].bank:
            f"banks/{filter_scenarios.SCENARIOS[0].bank}/sha256",
    }
    for path, field in edits.items():
        original = path.read_bytes()
        path.write_bytes(original + b"\n")
        refused = verify()
        assert refused.startswith(f"{csv_path}: the table's provenance"), \
            refused
        assert f"  {field}: recorded" in refused, (field, refused)
        path.write_bytes(original)
    assert verify().strip() == "current"
