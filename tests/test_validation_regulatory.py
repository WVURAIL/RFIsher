"""Regulatory snapshots cannot manufacture physical transmitter-off truth."""
import hashlib
import io
import json
import runpy
import struct
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

from rfisher_results.validation.regulatory import dbf_rows, fcc_history, ised_dates, lms_rows


def _dat(tmp_path, table, rows):
    keys = list(rows[0])
    text = "|".join(keys) + "|^|\n"
    text += "".join("|".join(str(row[k]) for k in keys) + "|^|\n" for row in rows)
    (tmp_path / (table + ".dat")).write_text(text)


def _dbf(fields, records, *, newline=False):
    base = bytearray(32)
    base[0] = 3
    header_len = 32 + len(fields) * 32 + 1 + newline
    record_len = 1 + sum(length for _, length in fields)
    struct.pack_into("<IHH", base, 4, len(records), header_len, record_len)
    data = io.BytesIO()
    data.write(base)
    for key, length in fields:
        field = bytearray(32)
        field[:len(key)] = key.encode()
        field[11] = ord("C")
        field[16] = length
        data.write(field)
    data.write(b"\r\n" if newline else b"\r")
    for values in records:
        data.write(b" ")
        for (_, length), value in zip(fields, values):
            data.write(value.encode().ljust(length))
    return data.getvalue() + b"\x1a"


@pytest.mark.parametrize("status", ["LICSL", "LICAN", "LICEN", "LICRP"])
def test_fcc_keeps_status_history_without_off_inference(tmp_path, status):
    _dat(tmp_path, "facility", [dict(facility_id="1", license_filing_id="L",
                                    facility_status=status, status_date="2025-01-01",
                                    expiration_date="2020-01-01")])
    _dat(tmp_path, "license_filing_version", [
        dict(filing_version_id="old", license_filing_id="L", prev_filing_version_id="",
             status_date="2019-01-01", current_status_code="GRA", active_ind="N"),
        dict(filing_version_id="new", license_filing_id="L", prev_filing_version_id="old",
             status_date="2025-01-01", current_status_code="GRA", active_ind="Y"),
    ])
    result = fcc_history(tmp_path, ["1", "missing"], snapshot_date="2026-09-08",
                         source_hashes={"source": "a" * 64})
    assert result["physical_state"] == "unknown"
    assert result["verified_rf_intervals"] == []
    assert result["missing_facility_ids"] == ["missing"]
    assert [r["active_ind"] for r in result["licence_versions"]] == ["N", "Y"]
    assert result["unresolved_predecessors"] == []


def test_ised_fixed_width_join_does_not_merge_allotment_and_operation(tmp_path):
    source = tmp_path / "ised.zip"
    fields = [("CALL_SIGN", 12), ("BANNER", 2), ("CHANNEL", 4)]
    stations = _dbf(fields, [["CHKL-DT-2", "AL", "22"], ["CHKL-DT-2", "OP", "22"]], newline=True)
    dates = _dbf([("CALLS_BANR", 14), ("BC_EFFCT", 8), ("ON_AIR", 8), ("BC_EXPIR", 8)],
                 [["CHKL-DT-2   OP", "20211007", "20130919", "bad-date"]])
    with ZipFile(source, "w") as z:
        z.writestr("tvstatio.dbf", stations)
        z.writestr("dates.dbf", dates)
    result = ised_dates(source, ["CHKL-DT-2", "MISSING"], snapshot_date="2026-09-02",
                        source_hashes={"source": "a" * 64})
    allotment, operation = result["records"]
    assert not allotment["date_row_present"]
    assert operation["dates"]["BC_EFFCT"] == "2021-10-07"
    assert operation["dates"]["ON_AIR"] == "2013-09-19"
    assert operation["invalid_dates"] == {"BC_EXPIR": "bad-date"}
    assert operation["physical_state"] == "unknown"
    assert result["missing_callsigns"] == ["MISSING"]
    assert result["verified_rf_intervals"] == []


def test_corrupt_table_width_is_not_silent_missing_evidence(tmp_path):
    (tmp_path / "facility.dat").write_text("facility_id|status|^|\n1|^|\n")
    with pytest.raises(ValueError, match="row width"):
        list(lms_rows(tmp_path, "facility", {"facility_id"}))


def test_truncated_dbf_fails(tmp_path):
    data = _dbf([("CALL_SIGN", 12)], [["CHKL-DT"]])
    (tmp_path / "tvstatio.dbf").write_bytes(data[:-4])
    with pytest.raises(ValueError, match="truncated"):
        list(dbf_rows(tmp_path, "tvstatio"))


def test_invalid_provenance_fails(tmp_path):
    with pytest.raises(ValueError, match="SHA256"):
        fcc_history(tmp_path, ["1"], snapshot_date="2026-09-08", source_hashes={})


@pytest.mark.parametrize("layout", ["zip", "dat", "both"])
def test_builder_hashes_the_fcc_tables_it_reads(tmp_path, monkeypatch, layout):
    """A stale ZIP beside extracted data must not receive the data's identity."""
    fcc = tmp_path / "fcc"
    fcc.mkdir()
    _dat(fcc, "facility", [dict(facility_id="1", callsign="KNEW", license_filing_id="L",
                                 facility_status="LICEN", status_date="2025-01-01")])
    _dat(fcc, "license_filing_version", [
        dict(filing_version_id="new", license_filing_id="L", prev_filing_version_id="",
             status_date="2025-01-01", current_status_code="GRA", active_ind="Y"),
    ])
    expected = {}
    for table in ["facility", "license_filing_version"]:
        direct, zipped = fcc / f"{table}.dat", fcc / f"{table}.zip"
        if layout in {"zip", "both"}:
            # Both forms are valid but deliberately disagree, so hashing the
            # unused ZIP cannot pass merely because extracted bytes coincide.
            archive_text = direct.read_text().replace("KNEW", "KOLD")
            archive_text = archive_text.replace("2025-01-01", "2020-01-01")
            with ZipFile(zipped, "w") as z:
                z.writestr(direct.name, archive_text)
        if layout == "zip":
            direct.unlink()
        chosen = zipped if layout == "zip" else direct
        expected[str(chosen.resolve())] = hashlib.sha256(chosen.read_bytes()).hexdigest()
    candidates, census = tmp_path / "candidates.csv", tmp_path / "census.csv"
    candidates.write_text("facility_id\n1\n")
    census.write_text("callsign\nKNEW\n")
    ised = tmp_path / "ised.zip"
    with ZipFile(ised, "w") as z:
        z.writestr("tvstatio.dbf", _dbf(
            [("CALL_SIGN", 12), ("BANNER", 2), ("CHANNEL", 4), ("PROVINCE", 2)],
            [["CHKL-DT", "OP", "24", "BC"]]))
        z.writestr("dates.dbf", _dbf([("CALLS_BANR", 14)], [["CHKL-DT     OP"]]))
    out = tmp_path / "out"
    script = Path(__file__).resolve().parents[1] / "scripts/build_regulatory_evidence.py"
    monkeypatch.setattr(sys, "argv", [str(script), "--fcc", str(fcc),
                                      "--fcc-candidates", str(candidates), "--census", str(census),
                                      "--ised", str(ised), "--fcc-snapshot-date", "2026-09-08",
                                      "--ised-snapshot-date", "2026-09-02", "--out", str(out)])
    runpy.run_path(str(script), run_name="__main__")
    result = json.loads((out / "fcc-history.json").read_text())
    bound_tables = {key: value for key, value in result["source_sha256"].items()
                    if Path(key).parent == fcc}
    assert bound_tables == expected
    assert result["facilities"][0]["callsign"] == ("KOLD" if layout == "zip" else "KNEW")
    assert result["physical_state"] == "unknown"
