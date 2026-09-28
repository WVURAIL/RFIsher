"""The per-bin tolerance table: its layout, its v3 provenance and its reader."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from rfisher.forecast.radiofisher_bao import response
from rfisher.forecast.radiofisher_bao.bank import banks
from rfisher.science_model import Bin, Parameters, Scenario
from rfisher.tolerance import table

ROOT = Path(__file__).resolve().parents[2]
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


def _model(tolerance=0.5):
    return SimpleNamespace(
        parameters=Parameters(("a",), ("c",)), zeta=1.0, target_years=1.0,
        year_grid=(1.0,), maximum_tolerance_ratio=1.2,
        scenarios=(Scenario("none", "rule", 0.0, "x.npz"),),
        load=lambda name: None, bins=lambda: (Bin(0, "z 0.8-0.9", 0.8, 0.9),),
        hours=lambda years: years,
        response=lambda *a: ({"a": 1.0, "c": 1.0},
                             {"a": tolerance, "c": tolerance}),
        accept=lambda *a: (1.0, 1),
        identity=lambda: {"sources": {"model.py": "0" * 64},
                          "banks": {"x.npz": {"sha256": "1" * 64}}})


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
