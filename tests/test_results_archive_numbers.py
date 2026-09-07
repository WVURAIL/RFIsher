"""numbers.json documents and the rerun-marker matcher."""
from __future__ import annotations

import csv
import json

import pytest

from rfisher_results.archive import numbers as nb


def test_document_round_trip_and_duplicate_keys(tmp_path):
    doc = nb.NumbersDocument.new("nulls", repository="WVURAIL/RFIsher", commit="0" * 40, script="archive/nulls.py", generated="2026-09-07T00:00:00Z")
    src = tmp_path / "in.csv"; src.write_text("a\n1\n")
    doc.add_input(src, rows=1)
    doc.add(nb.Number("ch08.nulls.core.ch29", 1.654, precision=2, source={"table": "nulls.csv", "row": {"channel": 29}, "column": "coarse_core_width_factor"}))
    doc.add(nb.Number("ch08.eras.count", 30, kind="int"))
    doc.add(nb.Number("ch08.tau.ch33", "bound", kind="text", renderings=("bound", "five minutes")))
    doc.add(nb.Number("ch09.nan", float("nan"), status="refused"))
    with pytest.raises(ValueError, match="duplicate"):
        doc.add(nb.Number("ch08.eras.count", 31, kind="int"))
    with pytest.raises(ValueError, match="kind"):
        nb.Number("x", 1, kind="weird")
    path = doc.write(tmp_path / "numbers" / "nulls.numbers.json")
    raw = json.loads(path.read_text())
    assert raw["schema"] == nb.SCHEMA and raw["inputs"][0]["sha256"] and raw["numbers"][3]["value"] is None
    back = nb.load_numbers([path])
    assert [n.key for n in back] == ["ch08.nulls.core.ch29", "ch08.eras.count", "ch08.tau.ch33", "ch09.nan"]
    assert back[2].renderings == ("bound", "five minutes")


def test_marker_normalization_unwraps_the_gate_conventions():
    assert nb.normalize_marker(r"\rerun{$\mathbf{0.83}$}") == "0.83"
    assert nb.normalize_marker(r"$1{,}566\times$") == "1,566x"
    assert nb.normalize_marker(r"\rerun{34, 45, 62, and 165 minutes}") == "34, 45, 62, and 165 minutes"
    assert nb.normalize_marker(r"7.6-year") == "7.6-year"
    assert nb.parse_numeric("1,566x") == (1566.0, 0)
    assert nb.parse_numeric("0.0246 dB") == (0.0246, 4)
    assert nb.parse_numeric("eight") is None


def test_matcher_verifies_within_half_ulp_and_reports_changes_and_missing_sources(tmp_path):
    inv = tmp_path / "inv.csv"
    with inv.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["file", "line", "section", "value", "context", "key"])
        w.writerow(["chapters/ch08.tex", 10, "Nulls", r"$1.65$", "...", "ch08.core.ch29"])        # verified (1.654 -> 1.65)
        w.writerow(["chapters/ch08.tex", 12, "Nulls", r"$1.9$", "...", "ch08.core.ch29"])         # changed
        w.writerow(["chapters/ch08.tex", 14, "Tau", r"five minutes", "...", "ch08.tau.ch33"])      # verified by rendering
        w.writerow(["chapters/ch09.tex", 20, "Eta", r"\rerun{$0.4747$}", "...", ""])               # unbound: found by value
        w.writerow(["chapters/ch09.tex", 22, "Eta", r"\rerun{$99$}", "...", ""])                   # unbound: no source
        w.writerow(["chapters/ch09.tex", 24, "Eta", r"\rerun{$0.5$}", "...", "missing.key"])       # bound to an absent key
    numbers = [nb.Number("ch08.core.ch29", 1.654, precision=2), nb.Number("ch08.tau.ch33", "bound", kind="text", renderings=("five minutes",)),
               nb.Number("ch09.f.ch33", 0.47472)]
    matches = nb.match_markers(nb.load_inventory(inv), numbers)
    statuses = [(m.marker.line, m.status) for m in matches]
    assert statuses == [(10, "verified"), (12, "changed"), (14, "verified"), (20, "verified"), (22, "no-source"), (24, "no-source")]
    report = nb.chapter_report(matches)
    assert report["chapters/ch08.tex"] == {"verified": 2, "changed": 1, "no-source": 0, "flip": False}
    assert report["chapters/ch09.tex"]["flip"] is False
    good = nb.match_markers(nb.load_inventory(inv)[:1] + nb.load_inventory(inv)[2:3], numbers)
    assert nb.chapter_report(good)["chapters/ch08.tex"]["flip"] is True


def test_half_ulp_precision_rule():
    assert nb.half_ulp(2) == pytest.approx(0.005)
    n = [nb.Number("k", 0.4747, precision=4)]
    m = nb.match_markers([nb.Marker("f", 1, "", "$0.475$", "", "k")], n)   # text prints 3 decimals of a 4-decimal number
    assert m[0].status == "changed"
    m = nb.match_markers([nb.Marker("f", 1, "", "$0.475$", "", "k")], [nb.Number("k", 0.4747)])   # precision unknown: the marker's
    assert m[0].status == "verified"
