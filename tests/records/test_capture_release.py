"""The capture release builder: its credit readings from the golden handoff, byte for byte.

A credit reading (``--credit-reading r3`` or ``r2``) needs only the handoff and the table of record, so the suite
builds both and compares them with the release r5.2's ``credit_readings/``. The whole release, which also reads the
decision evidence, the earlier releases and the survey-duration run, is compared at the gate.
"""
from __future__ import annotations

import json

import pytest

from capture_golden import quiet, sha256
from rfisher.records.chime_atsc_2026 import capture_release, capture_ruling

READINGS = {
    "r3": {"ch24_basis_a18.txt": "167d0b5d8ba33a87e807c7c2a3cdb99ac1379519161a774fd79e4b99527b180f",
           "dispositions_a18.csv": "9f4ab1329a707f932081ef11b1097d366a6d011a0a05289b469c91ebdf45a0c7",
           "thresholds_a18.csv": "f8356623c8e7000e21acdc2f0aa45201dcbdebaf0bba0d1606ec502b5667aa1d",
           "run/a18.json": "b304342d1b98f33974279c1fb80ec0d2538bffb45353ce6c70aa019135939c8a",
           "run/a18.log": "f4d9687b3e62234e7b885d697275280afa3cb3d9221ac0fdb146e2de1560b88a",
           "run/ch24_a18.json": "66f8f45900efdc35709870e5ccbe42cdc445e630d30a641cbc68a697b1807106",
           "run/thresholds.csv": "81b3e25bf159b3bf65f46dd4f1d2c19924161d6253bfa4ecee38323be07e9e66"},
    "r2": {"ch24_basis_a18.txt": "b6e7ad0eae362103e4c5e3d0b8a974790a15450a016da1e5f6564dc4202756e5",
           "dispositions_a18.csv": "e7e6b96602158f9e426be64f21dbac7af80a8ebdffac7773c5f2cba2f904c1aa",
           "thresholds_a18.csv": "5a23f70bbc6120797e6e468c307d6a1ba4f6cfb5d3758742dc29746c0e97822f",
           "run/a18.json": "fcef5256da654747ab1e696733524ecbb1609586a146016d91532779c48f39c4",
           "run/a18.log": "654feed3f97368e1699ad3e5c4309186b95f0259c52aee3a83f137589f766ea9",
           "run/ch24_a18.json": "8e224b82d498f73a28089f2d9893a5fb126097d2bf3dbc5a1bb399e4e69c3635",
           "run/thresholds.csv": "24acef154095fff37e7bc2ae8bd4968fcd62e4087bb2f4bb191ee1f6d3b3026d"},
}


@pytest.mark.parametrize("reading", sorted(READINGS))
def test_a_credit_reading_is_the_releases(capture_handoff_dir, tmp_path, reading):
    rel = tmp_path / "rel"
    unused = str(tmp_path / "unused")   # a credit reading reads no evidence, release or duration run
    quiet(capture_release.main, ["--rule", "r5_2", "--handoff", str(capture_handoff_dir), "--record-table",
                                 str(capture_handoff_dir / "frame_analysis" / "table_of_record.csv"), "--evidence", unused,
                                 "--releases", unused, "--duration-reference", unused, "--rel", str(rel),
                                 "--run", str(tmp_path / "run"), "--tables-only", "--credit-reading", reading])
    got = {p.relative_to(rel).as_posix(): sha256(p) for p in rel.rglob("*") if p.is_file()}
    assert got == READINGS[reading]


def test_the_release_manifest_keeps_the_releases_prose():
    doc = capture_release._release_doc()
    fixed = doc["fields"]
    assert fixed["release"] == "capture_ruling_a19_2026-09-25_r5_2"
    assert fixed["record"]["sha256"] == capture_release.RECORD_SHA
    identity, a18, r51, r52 = capture_ruling.switch_sets()
    assert fixed["r5_1"]["ruling_switches"] == r51 and fixed["r5_2"]["ruling_switches"] == r52
    assert set(fixed) <= set(doc["key_order"]) and "files" in doc["key_order"]
    assert json.dumps(fixed, ensure_ascii=False)


def test_only_the_release_of_record_is_built(tmp_path):
    with pytest.raises(SystemExit, match="release of record"):
        capture_release.main(["--rule", "r5_1"])
