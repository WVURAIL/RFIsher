"""``scripts/compare_no_split.py``: header-based table columns and a verdict that counts added columns."""
from __future__ import annotations

import importlib.util
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "scripts/compare_no_split.py"
SPEC = importlib.util.spec_from_file_location("compare_no_split_test", PATH)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)

SURFACE = "channel,rho,eta_q16,masked_fraction,r_sys\n"


def _tree(root: Path, *, surface_header: str, chain_header: str, chain_row: str) -> Path:
    (root / "archive/tables").mkdir(parents=True)
    (root / "archive/ledger").mkdir(parents=True)
    (root / "coarse").mkdir()
    (root / "archive/channels/ch20").mkdir(parents=True)
    (root / "archive/channels/ch20/operating_points.csv").write_text(surface_header)       # header only: no data rows
    (root / "archive/tables/chain.csv").write_text(chain_header + chain_row)
    (root / "archive/ledger/ledger.csv").write_text("channel,chain_chain_gain\n20,5.0\n")
    return root


def _checks(**over):
    base = dict(outside=[], outside_cells=[], unkeyed_cells=[], removed_ok=True, added=[],
                channels=[{"primary_assessment": "a", "primary_assessment_prior": "a"}],
                removed_columns=[{"table": t, "column": c} for t, c in sorted(m.REMOVED_COLUMNS)], added_columns=[],
                missing_tables=[])
    base.update(over)
    return m.verdict(**base)


def test_a_header_only_table_reports_no_false_added_columns(tmp_path):
    old = _tree(tmp_path / "old", surface_header=SURFACE, chain_header="channel,n_valid,intraday_share,chain_gain\n",
                chain_row="20,10,0.5,3.0\n")
    new = _tree(tmp_path / "new", surface_header=SURFACE, chain_header="channel,n_valid,chain_gain\n", chain_row="20,10,6.0\n")
    cells, removed, added, files = m.table_cells(old, new)
    assert added == []                                       # the first version listed every column of ch20's file
    assert removed == [{"table": "archive/tables/chain.csv", "column": "intraday_share"}]
    assert files["archive/channels/ch20/operating_points.csv"] == "byte-identical"
    assert [(c["table"], c["column"], c["ratio"]) for c in cells] == [("archive/tables/chain.csv", "chain_gain", 2.0)]


def test_a_column_added_to_a_header_only_table_is_reported(tmp_path):
    old = _tree(tmp_path / "old", surface_header=SURFACE, chain_header="channel,chain_gain\n", chain_row="20,3.0\n")
    new = _tree(tmp_path / "new", surface_header=SURFACE.replace("\n", ",selected\n"), chain_header="channel,chain_gain\n",
                chain_row="20,3.0\n")
    _, removed, added, _ = m.table_cells(old, new)
    assert added == [{"table": "archive/channels/ch20/operating_points.csv", "column": "selected"}] and removed == []


def test_passed_requires_no_added_columns_and_exactly_the_split_columns_removed():
    ok = _checks()
    assert ok["passed"] and all(ok["checks"].values())
    added = _checks(added_columns=[{"table": "archive/tables/chain.csv", "column": "new"}])
    assert not added["passed"] and not added["checks"]["no_added_columns"]
    short = _checks(removed_columns=[{"table": "archive/tables/chain.csv", "column": "intraday_share"}])
    assert not short["passed"] and not short["checks"]["removed_columns_exactly_the_split_columns"]
    assert not _checks(added=[{"channel": 20, "field": "x"}])["passed"]
    assert not _checks(channels=[{"primary_assessment": "a", "primary_assessment_prior": "b"}])["passed"]
    assert ("archive/ledger/ledger.csv", "chain_archive_ground_filter_db") in m.REMOVED_COLUMNS and len(m.REMOVED_COLUMNS) == 9


def test_a_table_missing_in_the_new_release_fails_the_verdict(tmp_path):
    old = _tree(tmp_path / "old", surface_header=SURFACE, chain_header="channel,chain_gain\n", chain_row="20,3.0\n")
    new = _tree(tmp_path / "new", surface_header=SURFACE, chain_header="channel,chain_gain\n", chain_row="20,3.0\n")
    (old / "archive/tables/screening.csv").write_text("channel,screening_class\n20,a\n")
    _, _, _, files = m.table_cells(old, new)
    assert files["archive/tables/screening.csv"] == "missing in new"
    assert m.missing_tables(files) == ["archive/tables/screening.csv"]
    result = _checks(missing_tables=m.missing_tables(files))
    assert not result["passed"] and not result["checks"]["no_missing_tables"]


def test_a_table_only_in_the_new_release_is_listed_and_fails_the_verdict(tmp_path):
    old = _tree(tmp_path / "old", surface_header=SURFACE, chain_header="channel,chain_gain\n", chain_row="20,3.0\n")
    new = _tree(tmp_path / "new", surface_header=SURFACE, chain_header="channel,chain_gain\n", chain_row="20,3.0\n")
    (new / "archive/channels/ch20/operating_point.csv").write_text("channel,rho\n20,1\n")
    _, _, _, files = m.table_cells(old, new)
    assert files["archive/channels/ch20/operating_point.csv"] == "missing in old"
    assert list(files)[-1] == "archive/channels/ch20/operating_point.csv"      # after every table of the old release
    assert m.missing_tables(files) == ["archive/channels/ch20/operating_point.csv"]
    result = _checks(missing_tables=m.missing_tables(files))
    assert not result["passed"] and not result["checks"]["no_missing_tables"]
    assert _checks()["checks"]["no_missing_tables"]
