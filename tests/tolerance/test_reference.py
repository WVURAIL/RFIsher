"""The frozen reference tolerance, vendored and written as band rows.

The coarse-world table (the record's deployed 200 ns tolerance and its suppression) stays vendored for the capture
records at identity; it is no longer a basis of the reference rows (stage P: post-processing is not modelled).
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import math
from importlib.resources import files

import pytest

from rfisher.cli import main
from rfisher.tolerance import reference
from rfisher.tolerance.bands import Band

# The per-band tolerances of the capture's table of record
# (table_of_record_before_amendment8.csv, fd718463): lambda_none, then
# lambda_deployed and suppression_db, as the record writes them.
RECORD = {
    14: ("0.08803187543604546", "0.00750119928573071", "11.4"),
    15: ("0.08803187543604546", "0.00750119928573071", "11.4"),
    16: ("0.08803187543604546", "0.00750119928573071", "11.4"),
    17: ("0.011104701918235394", "0.00750119928573071", "11.4"),
    18: ("0.011104701918235394", "0.015235843461215755", "11.4"),
    19: ("0.011104701918235394", "0.015235843461215755", "11.4"),
    20: ("0.008393350739527591", "0.015235843461215755", "11.4"),
    21: ("0.008393350739527591", "0.01596311463253297", "11.4"),
    22: ("0.008393350739527591", "0.01596311463253297", "11.4"),
    23: ("0.008393350739527591", "0.008020682065421818", "11.4"),
    24: ("0.01541149398966138", "0.008020682065421818", "11.4"),
    25: ("0.01541149398966138", "0.008020682065421818", "11.4"),
    26: ("0.01541149398966138", "0.008020682065421818", "11.4"),
    27: ("0.027979985304513164", "0.0512661994655337", "11.4"),
    28: ("0.027979985304513164", "0.0512661994655337", "11.4"),
    29: ("0.027979985304513164", "0.0512661994655337", "11.4"),
    30: ("0.017469164153269698", "0.008835289661451726", "11.4"),
    31: ("0.017469164153269698", "0.008835289661451726", "11.4"),
    32: ("0.017469164153269698", "0.008835289661451726", "11.4"),
    33: ("0.017469164153269698", "0.008835289661451726", "11.4"),
    34: ("0.017469164153269698", "0.008835289661451726", "11.4"),
    35: ("0.06184962800993756", "0.011129770064622178", "11.4"),
    36: ("0.06184962800993756", "0.011129770064622178", "11.4"),
}
# The per-bin tolerances the capture's bin fill reads: the exact-time
# reference's binding component and the deployed single-bin tolerance.
PER_BIN_NONE = {5: "0.06184962800993756", 6: "0.017469164153269698",
                7: "0.027979985304513164", 8: "0.01541149398966138",
                9: "0.008393350739527591", 10: "0.011104701918235394",
                11: "0.08803187543604546"}
PER_BIN_DEPLOYED = {5: "0.011129770064622178", 6: "0.008835289661451726",
                    7: "0.0512661994655337", 8: "0.008020682065421818",
                    9: "0.01596311463253297", 10: "0.015235843461215755",
                    11: "0.00750119928573071"}


def _bands():
    return [Band(str(c), 470.0 + 6.0 * (c - 14), 476.0 + 6.0 * (c - 14))
            for c in range(14, 37)]


def _data(name):
    return files("rfisher.data").joinpath("tolerances", name).read_bytes()


def test_the_vendored_files_are_the_frozen_bytes():
    for name, sha in reference.EXACT_TIME_FILES.items():
        data = _data(f"{reference.EXACT_TIME}/{name}")
        assert hashlib.sha256(data).hexdigest() == sha
    decoded = gzip.decompress(_data(reference.COARSE_WORLD_FILE))
    assert hashlib.sha256(decoded).hexdigest() == reference.COARSE_WORLD_SHA256


def test_a_changed_vendored_file_is_refused(monkeypatch):
    monkeypatch.setattr(reference, "_read", lambda name: b"changed")
    with pytest.raises(ValueError, match="sha256"):
        reference.exact_time_files()
    monkeypatch.setattr(reference, "_read",
                        lambda name: gzip.compress(b"changed"))
    with pytest.raises(ValueError, match="sha256"):
        reference.coarse_world_bytes()


def test_the_rows_carry_the_records_strings():
    rows, _ = reference.reference_rows(reference.EXACT_TIME, _bands())
    assert [repr(r["r_tol"]) for r in rows] == [RECORD[c][0]
                                               for c in range(14, 37)]
    assert {(r["scenario"], r["role"], r["zeta"], r["target_time_years"],
             r["refusal"]) for r in rows} == {("none", "rule", 1.0, 1.0, "")}
    assert "suppression_db" not in rows[0]


def test_the_deployed_tolerance_is_read_for_the_records_alone():
    assert reference.BASES == (reference.EXACT_TIME,)
    with pytest.raises(ValueError, match="unknown reference basis"):
        reference.reference_rows(reference.COARSE_WORLD, _bands())
    deployed = reference.coarse_world_bands()
    assert [(deployed[str(c)]["r_tol"], deployed[str(c)]["suppression_db"])
            for c in range(14, 37)] == [RECORD[c][1:] for c in range(14, 37)]


def test_the_components_carry_the_per_bin_tolerances():
    _, parts = reference.reference_rows(reference.EXACT_TIME, _bands())
    seen = {}
    for part in parts:
        seen.setdefault(part["bin"], set()).add(repr(part["r_tol_component"]))
    assert seen == {b: {v} for b, v in PER_BIN_NONE.items()}
    assert {b: repr(v["value"]) for b, v in reference.exact_time_bins().items()} \
        == PER_BIN_NONE
    assert {b: repr(v) for b, v in reference.coarse_world_bins().items()} == \
        PER_BIN_DEPLOYED


def test_the_least_component_is_the_band_tolerance():
    rows, parts = reference.reference_rows(reference.EXACT_TIME, _bands())
    for row in rows:
        values = [p["r_tol_component"] for p in parts
                  if p["band_id"] == row["band_id"]]
        assert min(values) == row["r_tol"]


def test_a_band_it_does_not_price_is_written_refused():
    bands = [Band("37", 608.0, 614.0), Band("18", 494.0, 501.0)]
    for basis in reference.BASES:
        rows, parts = reference.reference_rows(basis, bands)
        assert [r["refusal"] for r in rows] == [reference.REFUSED_ABSENT,
                                                reference.REFUSED_EDGES]
        assert all(math.isnan(r["r_tol"]) for r in rows) and parts == []
    with pytest.raises(ValueError, match="unknown reference basis"):
        reference.reference_rows("grid", bands)


def test_the_command_writes_the_basis(tmp_path, capsys):
    bands = tmp_path / "bands.csv"
    bands.write_text("band_id,low_mhz,high_mhz\n18,494.0,500.0\n"
                     "33,584.0,590.0\n", encoding="utf-8")
    out = tmp_path / "out"
    with pytest.raises(SystemExit):
        main(["tolerance", "reference", "--basis", reference.COARSE_WORLD,
              "--bands", str(bands), "--out", str(out)])
    assert main(["tolerance", "reference", "--basis", reference.EXACT_TIME,
                 "--bands", str(bands), "--out", str(out)]) == 0
    with (out / "tolerances.csv").open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert [(r["band_id"], r["scenario"], r["r_tol"]) for r in rows] == [
        ("18", "none", RECORD[18][0]), ("33", "none", RECORD[33][0])]
    assert (out / "tolerance_components.csv").is_file()
    assert (out / "tolerances.provenance.json").is_file()
    assert "wrote" in capsys.readouterr().out


def test_the_command_refuses_a_band_that_is_not_screened(tmp_path):
    bands = tmp_path / "bands.csv"
    bands.write_text("band_id,low_mhz,high_mhz,role\n37,608.0,614.0,control\n",
                     encoding="utf-8")
    with pytest.raises(SystemExit):
        main(["tolerance", "reference", "--basis", reference.EXACT_TIME,
              "--bands", str(bands), "--out", str(tmp_path / "out")])
