"""The capture ruling's copies, from the golden capture handoff, byte for byte.

At identity each copy writes its frozen record: channel 24's 2020 basis at the archive tau of record and the phase limit
in the booked units (the vendored records of the dissertation); the era-redate records of channel 24 at the archive tau
and timed frames of each release; and, on the r5.2 ruling, the release's channel 24 reading, phase limit,
cleaner-polarization margins and duration reading.

Post-processing is not modelled (stage P, 2026-10-06). Retired here: the amendment 8 robustness record with both
credits (robustness_credit.csv, vendored by the dissertation), channel 24's credit readings (r3 and r2) and revision
2's duration reading in the 200 ns world (duration_a18.csv); the frozen releases and the dissertation keep those files.
The r5.2 files that lost post-processing content (channel 24's reading, its per-bin table and the robustness margins)
are pinned at their new bytes, which differ from the release's only by the removed columns, fields or clause.
"""
from __future__ import annotations

import csv
import shutil
from pathlib import Path

import pytest

from capture_golden import assert_frozen, duration_reference, quiet, sha256, record_input
from rfisher.records.chime_atsc_2026 import (capture_ruling, cohort_basis, duration, phase_limit, robustness)
from rfisher.records.chime_atsc_2026 import capture_units as U

DURATION = Path(__file__).resolve().parents[1] / "golden" / "records" / "survey_duration_2026-09-24"
# the frame analysis's CH24_2020_BASIS.txt (the era-redate lane's repro_old too) and the vendored phase limit
# (provenance/phasor/*.gz, decoded)
IDENTITY = {"ch24": "73450a3af20079d3572a9cfe7bf49f12da2d190ea6b39bcdff32c577aa3c45df",
            "phase_limit_ranges.csv": "c69f69d0bde3af0bf043541f1741cf7e071952f0618f1879a8fc9d8df1afa2ca",
            "phase_limit_classes.csv": "41dbcb6e3a3f5e470fe9629231e71ac0c26f623a404c8d0c3c2b255576ef8e31",
            "phase_limit.log": "2eb6af163c980938cd02c387bff8f329e78fe2f01629065ca0fd6ab9efad4362"}
# the era-redate records: (archive tau, timed frames) of the author-eras release and of the 2026-09-09 release
ERA_REDATE = {("8423.051122984009", "10058"): "1d4cdf280d7a4223d1b96ece4d2b21d9459071af1978b5182fe0f84b9f0affe6",
              ("7777.250479782059", "9470"): "5b548d19c9346e65ab56fc955b96b2cf2bc6ba7bff883cb08b29ed22d0a61616"}
# the release r5.2's files (the first three and the robustness margins without their post-processing content)
RELEASE = {"ch24_basis_a18.txt": "d08599fc69bc83db68d295df022e29e574c0036196d1643efc76765553399504",
           "ch24_a18.json": "815ababcf24b7c33a2f782061a0f125a0869e7fc8d63b3c510b8ca27fab9ab93",
           "ch24_per_bin_a19.csv": "657f0ecadbf5b3fe6b00c1b0feed0ebae58ed909570706a897e75f7ac4a2d34d",
           "pl/phase_limit_a18.log": "519903dcf32d204e3582cec2df096a0c477d3ccd11cc9a1ea6a2af758523b886",
           "pl/phase_limit_ranges.csv": "f6e102ac4b653893c532d5466fb347c3174e27682e660c30b6dfa8a60da398b6",
           "pl/phase_limit_classes.csv": "41dbcb6e3a3f5e470fe9629231e71ac0c26f623a404c8d0c3c2b255576ef8e31",
           "robustness_a18.csv": "a1c891758d4a5433aae8f3b20c10fe42601dfdd6fd94b6d38c6a1cce1e5c62b5",
           "robustness_a18.log": "9f71dc2f32f9aa80b85352bc275decd2362b28b348c9c56e9608c7aaf93aea41"}
DURATION_FILES = {"keep_gap_a18.csv": "79d1999c5d7e0f3791aec1c37dfd75940b2597586cd284597327a99d05dd6feb",
                  "duration_nofilter.csv": "855d45b1af93771386c869f3f79609a7d99b7021ad5dbbcc3d2370e69f63e7ed",
                  "sensitivity_a18.log": "6c5d0fe89fc9d01baac83ad5a23cfe63200426fb3a067687a5a2572e1417412e"}
MEASURED = ["--a18", "--set", "CH24_BASIS=measured2020", "--per-bin-own-events", "--g1-names", "literal"]


def _write(path, text):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text)


def _basis(handoff, *args):
    return quiet(cohort_basis.main, ["--handoff", str(handoff), "--record-table",
                                     str(record_input("table_of_record.csv")), *args])


@pytest.fixture(scope="module")
def ruled(capture_handoff_dir, tmp_path_factory):
    """The r5.2 ruling's json and the units-only run's, which the copies read."""
    out = tmp_path_factory.mktemp("ruled")
    table = record_input("table_of_record_before_amendment8.csv")
    common = ["--input", str(table), "--handoff", str(capture_handoff_dir), "--ch33-rescan"]
    quiet(capture_ruling.main, ["--rule", "r5_2", "--json", str(out / "a18.json"), "--out", str(out / "a18.csv"), *common])
    quiet(capture_ruling.main, ["--rule", "record", "--set", "UNITS=power", "--set", "WORLD=none", "--set",
                                "GROUND_CREDIT=off", "--json", str(out / "units_only.json"), "--out", str(out / "u.csv"), *common])
    _write(out / "ch24_basis_a18.txt", _basis(capture_handoff_dir, *MEASURED, "--world", "none", "--ground", "off",
                                              "--per-bin", str(out / "ch24_per_bin_a19.csv"), "--json", str(out / "ch24_a18.json")))
    return out


def test_the_identity_copies_are_the_frozen_records(capture_handoff_dir, tmp_path):
    _write(tmp_path / "ch24.txt", _basis(capture_handoff_dir, "--tau-archive", "7777"))
    assert sha256(tmp_path / "ch24.txt") == IDENTITY["ch24"]
    with pytest.raises(SystemExit, match="--a18"):   # the amendment 8 record with credits is retired
        robustness.main(["--handoff", str(capture_handoff_dir), "--record-table", str(record_input("table_of_record.csv")),
                         str(tmp_path / "robustness.csv")])
    (tmp_path / "pl").mkdir()
    _write(tmp_path / "pl" / "phase_limit.log", quiet(phase_limit.main, ["--handoff", str(capture_handoff_dir), "--record-table", str(record_input("table_of_record.csv")), str(tmp_path / "pl")]))
    for name in ("phase_limit_ranges.csv", "phase_limit_classes.csv", "phase_limit.log"):
        assert sha256(tmp_path / "pl" / name) == IDENTITY[name], name


@pytest.mark.parametrize("tau,frames", sorted(ERA_REDATE))
def test_the_era_redate_records_of_channel_24(capture_handoff_dir, tmp_path, tau, frames):
    _write(tmp_path / "ch24.txt", _basis(capture_handoff_dir, "--tau-archive", tau, "--timed-frames", frames))
    assert sha256(tmp_path / "ch24.txt") == ERA_REDATE[(tau, frames)]


def test_the_release_copies_are_the_frozen_files(capture_handoff_dir, ruled, tmp_path):
    t = tmp_path
    for name in ("ch24_basis_a18.txt", "ch24_a18.json", "ch24_per_bin_a19.csv"):
        shutil.copy(ruled / name, t / name)
    (t / "pl").mkdir()
    _write(t / "pl" / "phase_limit_a18.log", quiet(phase_limit.main, [
        "--handoff", str(capture_handoff_dir), "--record-table", str(record_input("table_of_record.csv")), str(t / "pl"), "--units", "power", "--units-json", str(ruled / "units_only.json"),
        "--a18-json", str(ruled / "a18.json")]))
    _write(t / "robustness_a18.log", quiet(robustness.main, [
        "--handoff", str(capture_handoff_dir), "--record-table", str(record_input("table_of_record.csv")), str(t / "robustness_a18.csv"), "--a18", str(ruled / "a18.json"),
        "--ch24", str(ruled / "ch24_a18.json")]))
    assert_frozen({name: sha256(t / name) for name in RELEASE}, RELEASE)


def test_the_measured_basis_opens_no_borrowed_quantity(capture_handoff_dir, ruled, tmp_path):
    """Item 34: with the borrowed files removed from the handoff the measured reading is the same, byte for byte."""
    root = tmp_path / "handoff"
    shutil.copytree(capture_handoff_dir, root)
    shutil.rmtree(root / "cohort2020"); (root / "frame_analysis" / "pilot_to_inband.csv").unlink()
    _basis(root, *MEASURED, "--world", "none", "--ground", "off", "--json", str(tmp_path / "ch24_a18.json"))
    assert sha256(tmp_path / "ch24_a18.json") == sha256(ruled / "ch24_a18.json")
    with pytest.raises(FileNotFoundError):
        _basis(root, "--tau-archive", "7777")


def test_channel_24_per_bin(ruled):
    """Every in-band bin of channel 24 is over the allowance on the long range."""
    with open(ruled / "ch24_per_bin_a19.csv", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert [int(r["freq_id"]) for r in rows] == list(range(676, 692))
    assert all(10 ** (float(r["bao_long_bar_db"]) / 10) > U.ALLOW_R for r in rows)


def test_the_duration_reading_is_the_releases(ruled, tmp_path, monkeypatch):
    """The keep gap and the no-filter duration reading on the packaged banks; where no RadioFisher checkout is
    present the banks' authentication against it is stubbed (the Fisher matrices are the banks' either way)."""
    from rfisher.forecast.radiofisher_bao import response
    from rfisher.forecast.radiofisher_bao.bank.backend import find_radiofisher_dir
    try:
        find_radiofisher_dir()
    except FileNotFoundError:
        monkeypatch.setattr(response, "evaluation_identity", lambda bank, rf_dir=None: ({}, {}))
    out = tmp_path / "rel"; out.mkdir()
    quiet(duration.main, [str(ruled / "a18.json"), str(out), "--ch24", str(ruled / "ch24_a18.json"),
                          "--duration-reference", str(duration_reference(tmp_path))])
    assert_frozen({name: sha256(out / name) for name in DURATION_FILES}, DURATION_FILES)


def test_the_measured_basis_refuses_a_credit(capture_handoff_dir, tmp_path):
    """Channel 24's credit readings (the ground credit, the 200 ns filter plus S) are not computed."""
    for world, ground in (("none", "on"), ("200ns", "off")):
        with pytest.raises(SystemExit, match="post-processing"):
            _basis(capture_handoff_dir, *MEASURED, "--world", world, "--ground", ground, "--json", str(tmp_path / "x.json"))


def test_duration_refuses_a_filtered_ruling(capture_handoff_dir, tmp_path):
    """Revision 2's 200 ns duration reading is not computed: a ruling that prices a delay filter is refused."""
    table = record_input("table_of_record_before_amendment8.csv")
    quiet(capture_ruling.main, ["--rule", "a18", "--set", "TAU_LOWER_BOUNDS=off", "--set", "WORLD=200ns", "--json",
                                str(tmp_path / "a18.json"), "--input", str(table), "--handoff", str(capture_handoff_dir),
                                "--out", str(tmp_path / "full.csv"), "--ch33-rescan"])
    out = tmp_path / "rel"; out.mkdir()
    with pytest.raises(SystemExit, match="delay filter"):
        duration.main([str(tmp_path / "a18.json"), str(out), "--duration-reference", str(DURATION)])
