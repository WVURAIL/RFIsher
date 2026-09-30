"""The capture ruling's copies, from the golden capture handoff, byte for byte.

At identity each copy writes its frozen record: channel 24's 2020 basis at the archive tau of record, the robustness
margins of the table of record and the phase limit in the booked units (the vendored records of the dissertation);
the era-redate records of channel 24 at the archive tau and timed frames of each release; and, on the r5.2 ruling, the
release's channel 24 reading, phase limit, robustness margins and duration reading.
"""
from __future__ import annotations

import csv
import shutil
from pathlib import Path

import pytest

from capture_golden import quiet, sha256
from rfisher.records.chime_atsc_2026 import (capture_ruling, cohort_basis, duration, phase_limit, robustness)
from rfisher.records.chime_atsc_2026 import capture_units as U

DURATION = Path(__file__).resolve().parents[1] / "golden" / "records" / "survey_duration_2026-09-24"
# the frame analysis's CH24_2020_BASIS.txt (the era-redate lane's repro_old too), the vendored robustness_credit.csv,
# and the vendored phase limit (provenance/phasor/*.gz, decoded)
IDENTITY = {"ch24": "73450a3af20079d3572a9cfe7bf49f12da2d190ea6b39bcdff32c577aa3c45df",
            "robustness": "d9d671d3df416e23e6327fe7f7efd1ad46bd59f9630cb7a8308ba47412bcbf53",
            "phase_limit_ranges.csv": "c69f69d0bde3af0bf043541f1741cf7e071952f0618f1879a8fc9d8df1afa2ca",
            "phase_limit_classes.csv": "41dbcb6e3a3f5e470fe9629231e71ac0c26f623a404c8d0c3c2b255576ef8e31",
            "phase_limit.log": "2eb6af163c980938cd02c387bff8f329e78fe2f01629065ca0fd6ab9efad4362"}
# the era-redate records: (archive tau, timed frames) of the author-eras release and of the 2026-09-09 release
ERA_REDATE = {("8423.051122984009", "10058"): "1d4cdf280d7a4223d1b96ece4d2b21d9459071af1978b5182fe0f84b9f0affe6",
              ("7777.250479782059", "9470"): "5b548d19c9346e65ab56fc955b96b2cf2bc6ba7bff883cb08b29ed22d0a61616"}
# the release r5.2's files
RELEASE = {"ch24_basis_a18.txt": "6e2f8b71477692a4b5ac2d8e43787fbb1826baa4b035996c169eb6cdb0228c6b",
           "ch24_a18.json": "0061e8794c2071ad18e3aaaf3a5894d6601399496318fb8fcf45062887553777",
           "ch24_per_bin_a19.csv": "cbc7e9ac8b6c01c0e2c8fb08222317a6ac64bc4d9d1a81c71ff73794085a30c6",
           "r3/ch24_basis_a18.txt": "167d0b5d8ba33a87e807c7c2a3cdb99ac1379519161a774fd79e4b99527b180f",
           "r3/ch24_a18.json": "66f8f45900efdc35709870e5ccbe42cdc445e630d30a641cbc68a697b1807106",
           "r2/ch24_basis_a18.txt": "b6e7ad0eae362103e4c5e3d0b8a974790a15450a016da1e5f6564dc4202756e5",
           "r2/ch24_a18.json": "8e224b82d498f73a28089f2d9893a5fb126097d2bf3dbc5a1bb399e4e69c3635",
           "pl/phase_limit_a18.log": "519903dcf32d204e3582cec2df096a0c477d3ccd11cc9a1ea6a2af758523b886",
           "pl/phase_limit_ranges.csv": "f6e102ac4b653893c532d5466fb347c3174e27682e660c30b6dfa8a60da398b6",
           "pl/phase_limit_classes.csv": "41dbcb6e3a3f5e470fe9629231e71ac0c26f623a404c8d0c3c2b255576ef8e31",
           "robustness_a18.csv": "84ff475230a7e4bf303674741d46d1f66d8c7f68f1e4fca5192d604d4548433f",
           "robustness_a18.log": "7ea295d3ef64ca4a7614e9b8f2933742b5da08d813f72b051a6b009f15eaa30a"}
DURATION_FILES = {"keep_gap_a18.csv": "79d1999c5d7e0f3791aec1c37dfd75940b2597586cd284597327a99d05dd6feb",
                  "duration_nofilter.csv": "855d45b1af93771386c869f3f79609a7d99b7021ad5dbbcc3d2370e69f63e7ed",
                  "sensitivity_a18.log": "6c5d0fe89fc9d01baac83ad5a23cfe63200426fb3a067687a5a2572e1417412e"}
MEASURED = ["--a18", "--set", "CH24_BASIS=measured2020", "--per-bin-own-events", "--g1-names", "literal",
            "--credit-form", "one_minus_gamma"]


def _write(path, text):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text)


def _basis(handoff, *args):
    return quiet(cohort_basis.main, ["--handoff", str(handoff), "--record-table",
                                     str(handoff / "frame_analysis" / "table_of_record.csv"), *args])


@pytest.fixture(scope="module")
def ruled(capture_handoff_dir, tmp_path_factory):
    """The r5.2 ruling's json and the units-only run's, which the copies read."""
    out = tmp_path_factory.mktemp("ruled")
    table = capture_handoff_dir / "frame_analysis" / "table_of_record_before_amendment8.csv"
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
    quiet(robustness.main, ["--handoff", str(capture_handoff_dir), str(tmp_path / "robustness.csv")])
    assert sha256(tmp_path / "robustness.csv") == IDENTITY["robustness"]
    (tmp_path / "pl").mkdir()
    _write(tmp_path / "pl" / "phase_limit.log", quiet(phase_limit.main, ["--handoff", str(capture_handoff_dir), str(tmp_path / "pl")]))
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
    for k, world in (("r3", "none"), ("r2", "200ns")):
        (t / k).mkdir()
        _write(t / k / "ch24_basis_a18.txt", _basis(capture_handoff_dir, *MEASURED, "--world", world, "--json", str(t / k / "ch24_a18.json")))
    (t / "pl").mkdir()
    _write(t / "pl" / "phase_limit_a18.log", quiet(phase_limit.main, [
        "--handoff", str(capture_handoff_dir), str(t / "pl"), "--units", "power", "--units-json", str(ruled / "units_only.json"),
        "--a18-json", str(ruled / "a18.json")]))
    _write(t / "robustness_a18.log", quiet(robustness.main, [
        "--handoff", str(capture_handoff_dir), str(t / "robustness_a18.csv"), "--a18", str(ruled / "a18.json"),
        "--ch24", str(ruled / "ch24_a18.json"), "--variant-labels"]))
    assert {name: sha256(t / name) for name in RELEASE} == RELEASE


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


def _radiofisher():
    from rfisher.forecast.radiofisher_bao.bank.backend import find_radiofisher_dir
    try:
        return find_radiofisher_dir()
    except FileNotFoundError:
        return None


@pytest.mark.skipif(_radiofisher() is None, reason="the response banks authenticate against RadioFisher; set RADIOFISHER_DIR")
def test_the_duration_reading_is_the_releases(ruled, tmp_path):
    out = tmp_path / "rel"; out.mkdir()
    quiet(duration.main, [str(ruled / "a18.json"), str(out), "--ch24", str(ruled / "ch24_a18.json"),
                          "--duration-reference", str(DURATION)])
    assert {name: sha256(out / name) for name in DURATION_FILES} == DURATION_FILES
