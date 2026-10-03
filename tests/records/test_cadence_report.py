"""The cadence report of record from the detector's report and the table of record (rfisher records cadence-report)."""
from __future__ import annotations

import gzip
import hashlib
from pathlib import Path

import pytest

from rfisher.cli import records_main
from rfisher.records.chime_atsc_2026 import cadence_report

GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "records" / "cadence_report"
# the frame analysis's CADENCE_REPORT.md and its table of record input table_of_record_v10.csv (the frozen files)
REPORT_SHA256 = "e259fdd7d91bebf4"
TABLE_SHA256 = "8f1a510b7c49f625"


def _frozen():
    report = gzip.decompress((GOLDEN / "CADENCE_REPORT.md.gz").read_bytes())
    table = gzip.decompress((GOLDEN / "table_of_record_v10.csv.gz").read_bytes())
    assert hashlib.sha256(report).hexdigest().startswith(REPORT_SHA256)
    assert hashlib.sha256(table).hexdigest().startswith(TABLE_SHA256)
    return report, table


def test_the_pair_reproduces_the_report_of_record_byte_for_byte(tmp_path):
    report, table = _frozen()
    cut = report.index(b"\n## Table of record at the measured gain")
    (tmp_path / "detector.md").write_bytes(report[:cut])      # what pilot-proxy's capture cadence-report writes
    (tmp_path / "table.csv").write_bytes(table)
    out = tmp_path / "CADENCE_REPORT.md"
    assert records_main(["cadence-report", "--detector-report", str(tmp_path / "detector.md"),
                         "--table-of-record", str(tmp_path / "table.csv"), "--out", str(out)]) == 0
    assert out.read_bytes() == report


def test_a_report_that_already_holds_the_section_is_refused(tmp_path):
    report, table = _frozen()
    with pytest.raises(ValueError, match="already holds"):
        cadence_report.compose(report, [])
    with pytest.raises(ValueError, match="newline"):
        cadence_report.compose(b"# report", [])
