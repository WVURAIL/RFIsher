"""The capture ruling of record, from the golden capture handoff, byte for byte.

The golden handoff (tests/golden/handoff/capture) is the detector's measurements the release r5.2 producer read. From
it the ported records must write the frozen files exactly: the table of record at identity (9867551a) and its v7
input (fd718463), the r5.2 release's ruling runs, and the ruling runs of revisions 2 to 5.1, whose switches the rule
files keep. The whole release is compared at the gate.

The release's credit readings (run/ of credit_readings/r3 and r2) are retired with stage P (2026-10-06): post-processing
is not modelled, and their rule files were removed. Revisions 2 and 3 stay, set by their switches.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from capture_golden import assert_frozen, quiet, sha256, record_input
from rfisher.records.chime_atsc_2026 import capture_ruling, table_of_record
from rfisher.records.chime_atsc_2026 import capture_units as U

RECORD = "9867551ad591757ed8b8864940376c68666483833478b4711292e0517a27b195"   # table_of_record.csv
RECORD_V7 = "fd718463005beace5f4b52882a6b70d7a6f0c44b54d244b1c8a8aa3d99e6548f"  # table_of_record_before_amendment8.csv
IDENTITY_LOG = "1a54b7a398b628d20a16e2ecc8ec40e89b8bdfd31b3c146be48131d5a578bf73"
# the release r5.2's run/ files (results/capture_ruling_a19_2026-09-25_r5_2)
R52 = {
    "a18.json": "2480ae05a80adb4871747c7aee0d40a063ea11029badec4c8c96c5fb9a8750c3",
    "a18_full.csv": "1c7fbdd8d18cd32d8cbdb6c6d27cfe4c88256b1a4c18526feaffa9a071de6bf9",
    "thresholds.csv": "d25e82e4acaf1a4f83eee1aeb54336cb22212e4dcedfbdce7fb29e6f808053ba",
    "a18.log": "58ea0c23bf85308f80c2128cc0fc5835d0574cac1912f4149b2531f21243a673",
    "a18_g1.json": "97bf8aaaf45975679ee7eb21569466ae8414178dd9e15bc9054fc2fc0731d915",
    "a18_g1_full.csv": "de43d62fac87be975baa0608f30c58e3f9a70897c21fc0de91d821c66dcb53b5",
    "units_only.json": "e703ac36a5a469e3a70800b5d0a1a7896a534e907bc7d47cdcab615eb4efb499",
    "units_only_full.csv": "b76ae4b82ef31ac38e01476965b6831e462c8061f5b27b7bea27bc525c5d442e",
    "a18_bounds_off.json": "abe25ebcff88d48983027b269723d26e49dea629ce93b958d558b11b0c563b2e",
    "a18_g1_bounds_off.json": "15ad33b6e35d50454b9e17739e935496e43415c47862bbea22b265a3b262d5f8",
}
# run/a18.json of the earlier revisions (results/capture_ruling_a1{8,9}_*)
REVISIONS = {
    "r5_1": (["--rule", "r5_1"], "ba5ce3763b953220ba2e1a5b9fae9f396a2b3b8d68fe62377a6e09456bad5386"),
    "r5": (["--rule", "r5"], "5fc50842591da39f49ccccc9cd58476f5a8f419b4a88f490f9f052d7c2699393"),
    "r4": (["--rule", "a18", "--set", "TAU_LOWER_BOUNDS=off"],
           "ceab72a8bfdbe818c49b3da4f8e12362b0d96e69956547495d8e4c65192d2ae6"),
    "r3": (["--rule", "a18", "--set", "TAU_LOWER_BOUNDS=off", "--set", "GROUND_CREDIT=on"],
           "82b0a808029c529b212b15abee585972e1c45740a04563f01c70b989ad8f37fc"),
    "r2": (["--rule", "a18", "--set", "TAU_LOWER_BOUNDS=off", "--set", "GROUND_CREDIT=on", "--set", "WORLD=200ns"],
           "95bc937ea97f9ebccb765a8456b4858c038fb6aa622d18fcb6203347adb5dc15"),
}
# revision 5.3 (DECISIONS.md item 87): the release's four rulings with each channel's own frames per dump
R53 = {
    "a18.json": "50ddb72d12987257edca732738d0fa8f7ae8b40d8b350e0aa96fd298a76f880e",
    "a18_g1.json": "9ca5a7864ae4a612a9ea90c17af9311df43efdf9f0c0fec3ddc50975a402aefd",
    "a18_bounds_off.json": "0b796807579da9750018a55647715be48dd9c3ef9b049753adb4d69b1a0fe5ef",
    "a18_g1_bounds_off.json": "91635045d4d64fe921fbb81b531f6fbe0284e2b77b4f2da3bc9b593594784096",
}
BOUNDS_OFF = ["--set", "TAU_LOWER_BOUNDS=off", "--set", "BOUND_SOURCE=summary", "--set", "BOUND_CALIBRATION=off"]
# the release's run/a18.json by section (sha256 of each top-level value as sorted json, first 12 hex digits): on a
# mismatch the test names the sections that differ
A18_SECTIONS = {"switches": "85e0739bdbdf", "summary": "d142bbaf4b42", "has_pilot": "d2c6967a1e7a",
                "results": "e411292523f1", "S": "8d0dcef48d9e", "lam_dep": "51e41f5a72bf", "lam_none": "f6c942b5225a",
                "thresholds": "0d9f1f6ca2cc", "admissible_min_G": "50d0ef50e307", "world": "30a0924a3360",
                "lam_exclusion": "f6c942b5225a", "fill": "fd618e49dce3", "tau_lower_bounds": "e10bcddcde91",
                "tau_lower_bounds_used": "e392691b8e7a", "tau_censored": "4eb148a6e9f2",
                "tau_probe_censored": "375bd39db8f9", "tau_lower_bounds_calibration": "cc264e5ff769"}


def _sections(path):
    doc = json.loads(Path(path).read_text())
    digest = {k: hashlib.sha256(json.dumps(v, sort_keys=True).encode()).hexdigest()[:12] for k, v in doc.items()}
    return {k: (digest.get(k), v) for k, v in A18_SECTIONS.items() if digest.get(k) != v}, doc.get("admissible_min_G")


def ruling(handoff, out, *args, table=None):
    table = table or record_input("table_of_record_before_amendment8.csv")
    return quiet(capture_ruling.main, [*args, "--input", str(table), "--handoff", str(handoff), "--out", str(out),
                                       "--ch33-rescan"])


def test_the_identity_rule_writes_the_table_of_record(capture_handoff_dir, tmp_path):
    log = ruling(capture_handoff_dir, tmp_path / "identity.csv", "--rule", "record")
    assert sha256(tmp_path / "identity.csv") == RECORD
    (tmp_path / "identity.log").write_text(log)
    assert sha256(tmp_path / "identity.log") == IDENTITY_LOG
    identity = capture_ruling.resolve("record")
    explicit = sum((["--set", f"{k}={v}"] for k, v in identity.items()), [])
    ruling(capture_handoff_dir, tmp_path / "explicit.csv", "--rule", "a18", *explicit)
    assert sha256(tmp_path / "explicit.csv") == RECORD


def test_the_v7_table_and_the_record_are_rebuilt(capture_handoff_dir, tmp_path):
    quiet(table_of_record.main, ["--handoff", str(capture_handoff_dir), "--gain-bao", str(record_input("gain_bao.csv")),
                                 "--out", str(tmp_path / "v7.csv")])
    assert sha256(tmp_path / "v7.csv") == RECORD_V7
    ruling(capture_handoff_dir, tmp_path / "record.csv", "--rule", "record", table=tmp_path / "v7.csv")
    assert sha256(tmp_path / "record.csv") == RECORD


def test_the_release_runs_are_the_frozen_ones(capture_handoff_dir, tmp_path):
    t = tmp_path
    log = ruling(capture_handoff_dir, t / "a18_full.csv", "--rule", "r5_2", "--json", str(t / "a18.json"),
                 "--thresholds", str(t / "thresholds.csv"))
    (t / "a18.log").write_text(log)
    ruling(capture_handoff_dir, t / "a18_g1_full.csv", "--rule", "r5_2", "--sensitivity", "g1",
           "--json", str(t / "a18_g1.json"))
    ruling(capture_handoff_dir, t / "units_only_full.csv", "--rule", "record", "--set", "UNITS=power",
           "--set", "WORLD=none", "--set", "GROUND_CREDIT=off", "--json", str(t / "units_only.json"))
    ruling(capture_handoff_dir, t / "bo.csv", "--rule", "r5_2", *BOUNDS_OFF, "--json", str(t / "a18_bounds_off.json"))
    ruling(capture_handoff_dir, t / "g1bo.csv", "--rule", "r5_2", *BOUNDS_OFF, "--sensitivity", "g1",
           "--json", str(t / "a18_g1_bounds_off.json"))
    got = {name: sha256(t / name) for name in R52}
    assert_frozen(got, R52, _sections(t / "a18.json"))


@pytest.mark.parametrize("revision", sorted(REVISIONS))
def test_the_earlier_revisions_keep_their_switches(capture_handoff_dir, tmp_path, revision):
    args, expected = REVISIONS[revision]
    ruling(capture_handoff_dir, tmp_path / "full.csv", *args, "--json", str(tmp_path / "a18.json"))
    assert_frozen({"a18.json": sha256(tmp_path / "a18.json")}, {"a18.json": expected})


D2 = "20260917090230"


def test_three_bins_of_the_second_science_dump_hold_27_frames():
    assert U.SHORT_BINS == {(D2, 511): (35, 27), (D2, 703): (23, 27), (D2, 759): (19, 27)}
    assert [U.nframes(D2, ch) for ch in (19, 23, 35)] == [27, 27, 27]
    short = {(D2, 19), (D2, 23), (D2, 35)}
    assert all(U.nframes(e, ch) == n for e, n in U.NFRAMES.items() for ch in range(14, 38) if (e, ch) not in short)
    assert U.constants()["NFRAMES"][D2] == 33   # the handoff's manifest records the dump's count


def _leaves(x, path=""):
    if isinstance(x, dict):
        for k, v in x.items():
            yield from _leaves(v, f"{path}/{k}")
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from _leaves(v, f"{path}/{i}")
    else:
        yield path, x


def test_revision_5_3_moves_only_the_frame_count(capture_handoff_dir, tmp_path):
    """Item 87's prediction: with the true frames only channel 19's lowest-epoch reading of D2 changes, 33 to 27 frames;
    no R value, threshold, verdict or disposition moves (the tables are byte for byte r5.2's)."""
    runs = {"a18.json": [], "a18_g1.json": ["--sensitivity", "g1"], "a18_bounds_off.json": BOUNDS_OFF,
            "a18_g1_bounds_off.json": [*BOUNDS_OFF, "--sensitivity", "g1"]}
    got = {}
    for name, extra in runs.items():
        docs, tables = [], []
        for rule in ("r5_2", "r5_3"):
            d = tmp_path / rule; d.mkdir(exist_ok=True)
            ruling(capture_handoff_dir, d / f"{name}.csv", "--rule", rule, *extra, "--json", str(d / name),
                   "--thresholds", str(d / f"{name}.thr"))
            docs.append(dict(_leaves(json.loads((d / name).read_text()))))
            tables.append((sha256(d / f"{name}.csv"), sha256(d / f"{name}.thr")))
        old, new = docs
        moved = {k: (old.get(k), new.get(k)) for k in old.keys() | new.keys() if old.get(k) != new.get(k)}
        assert moved == {"/results/19/shortest/low/epochs/2/n_frames": (33, 27), "/switches/FRAMES": (None, "bin")}, name
        assert old["/results/19/shortest/low/epochs/2/epoch"] == D2
        assert tables[0] == tables[1], name
        got[name] = sha256(tmp_path / "r5_3" / name)
    assert_frozen(got, R53)
