"""The capture release builder, from the golden handoff, byte for byte.

A credit reading (``--credit-reading r3`` or ``r2``) needs only the handoff and the table of record. The whole
release also reads the decision evidence, revisions 5 and 5.1 and the survey-duration run, which
tests/golden/records/capture_evidence.tar.gz and survey_duration_2026-09-24/ carry (byte copies). Where no RadioFisher
checkout is present the response banks' authentication against it is stubbed; the Fisher matrices are the packaged
banks' either way.
"""
from __future__ import annotations

import json
import tarfile
from pathlib import Path

import pytest

from capture_golden import quiet, sha256
from rfisher.records.chime_atsc_2026 import capture_release, capture_ruling, filter_sensitivity

GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "records"
EVIDENCE_SHA256 = "4615d7fe5b7f2277b621fbc9b448ed184ceaada07cb3114a3c019f5ee5ef8ecf"
# every file of the release r5.2 but MANIFEST.json, tests_a18.txt and the source snapshot
RELEASE = {
    "CHANGES.md": "22cd5161ca23fc4c5bc3c03fcf2a144be450c302ae5c5bc39ee20eda1e08086c",
    "PROMOTION_EVIDENCE.md": "72b64d66e2cd3b694cb4292d05776ec287a201472b206eb40bc496b709ce3fb3",
    "ch24_basis_a18.txt": "6e2f8b71477692a4b5ac2d8e43787fbb1826baa4b035996c169eb6cdb0228c6b",
    "ch24_per_bin_a19.csv": "cbc7e9ac8b6c01c0e2c8fb08222317a6ac64bc4d9d1a81c71ff73794085a30c6",
    "credit_readings/r2/ch24_basis_a18.txt": "b6e7ad0eae362103e4c5e3d0b8a974790a15450a016da1e5f6564dc4202756e5",
    "credit_readings/r2/dispositions_a18.csv": "e7e6b96602158f9e426be64f21dbac7af80a8ebdffac7773c5f2cba2f904c1aa",
    "credit_readings/r2/run/a18.json": "fcef5256da654747ab1e696733524ecbb1609586a146016d91532779c48f39c4",
    "credit_readings/r2/run/a18.log": "654feed3f97368e1699ad3e5c4309186b95f0259c52aee3a83f137589f766ea9",
    "credit_readings/r2/run/ch24_a18.json": "8e224b82d498f73a28089f2d9893a5fb126097d2bf3dbc5a1bb399e4e69c3635",
    "credit_readings/r2/run/thresholds.csv": "24acef154095fff37e7bc2ae8bd4968fcd62e4087bb2f4bb191ee1f6d3b3026d",
    "credit_readings/r2/thresholds_a18.csv": "5a23f70bbc6120797e6e468c307d6a1ba4f6cfb5d3758742dc29746c0e97822f",
    "credit_readings/r3/ch24_basis_a18.txt": "167d0b5d8ba33a87e807c7c2a3cdb99ac1379519161a774fd79e4b99527b180f",
    "credit_readings/r3/dispositions_a18.csv": "9f4ab1329a707f932081ef11b1097d366a6d011a0a05289b469c91ebdf45a0c7",
    "credit_readings/r3/run/a18.json": "b304342d1b98f33974279c1fb80ec0d2538bffb45353ce6c70aa019135939c8a",
    "credit_readings/r3/run/a18.log": "f4d9687b3e62234e7b885d697275280afa3cb3d9221ac0fdb146e2de1560b88a",
    "credit_readings/r3/run/ch24_a18.json": "66f8f45900efdc35709870e5ccbe42cdc445e630d30a641cbc68a697b1807106",
    "credit_readings/r3/run/thresholds.csv": "81b3e25bf159b3bf65f46dd4f1d2c19924161d6253bfa4ecee38323be07e9e66",
    "credit_readings/r3/thresholds_a18.csv": "f8356623c8e7000e21acdc2f0aa45201dcbdebaf0bba0d1606ec502b5667aa1d",
    "dispositions_a18.csv": "81db673818ecbfff0fc7ce18e738d57939cd3e12b80690ca3c1f66d2fedb7755",
    "duration_nofilter.csv": "855d45b1af93771386c869f3f79609a7d99b7021ad5dbbcc3d2370e69f63e7ed",
    "keep_gap_a18.csv": "79d1999c5d7e0f3791aec1c37dfd75940b2597586cd284597327a99d05dd6feb",
    "phase_limit_a18/phase_limit_a18.log": "519903dcf32d204e3582cec2df096a0c477d3ccd11cc9a1ea6a2af758523b886",
    "phase_limit_a18/phase_limit_classes_a18.csv": "41dbcb6e3a3f5e470fe9629231e71ac0c26f623a404c8d0c3c2b255576ef8e31",
    "phase_limit_a18/phase_limit_ranges_a18.csv": "f6e102ac4b653893c532d5466fb347c3174e27682e660c30b6dfa8a60da398b6",
    "postprocessing_sensitivity.csv": "8d9a751aa74d871304f1bed2e564f8696eba13e2446f2f013a89bb3b9636bd7a",
    "promotion_least_corners.csv": "b38e091f3ca45e4c9ad0acf76a21a2ed4062bf0b076065c8eea35fa10262bca5",
    "robustness_a18.csv": "84ff475230a7e4bf303674741d46d1f66d8c7f68f1e4fca5192d604d4548433f",
    "run/a18.json": "2480ae05a80adb4871747c7aee0d40a063ea11029badec4c8c96c5fb9a8750c3",
    "run/a18.log": "58ea0c23bf85308f80c2128cc0fc5835d0574cac1912f4149b2531f21243a673",
    "run/a18_bounds_off.json": "abe25ebcff88d48983027b269723d26e49dea629ce93b958d558b11b0c563b2e",
    "run/a18_bounds_off.log": "fb294cece671f06a6d2055b406a264b8cfea9b5439572ded5664122b46f90a78",
    "run/a18_full.csv": "1c7fbdd8d18cd32d8cbdb6c6d27cfe4c88256b1a4c18526feaffa9a071de6bf9",
    "run/a18_g1.json": "97bf8aaaf45975679ee7eb21569466ae8414178dd9e15bc9054fc2fc0731d915",
    "run/a18_g1.log": "02d69812a37fd3cb749a82e326d0dd3884f1349cb254931027f2adee426282ba",
    "run/a18_g1_bounds_off.json": "15ad33b6e35d50454b9e17739e935496e43415c47862bbea22b265a3b262d5f8",
    "run/a18_g1_bounds_off.log": "3dc50974974f12312e80671bf83467c8a06fc8a98c6627d0184aaf9e2fe36d48",
    "run/a18_g1_full.csv": "de43d62fac87be975baa0608f30c58e3f9a70897c21fc0de91d821c66dcb53b5",
    "run/ch24_a18.json": "0061e8794c2071ad18e3aaaf3a5894d6601399496318fb8fcf45062887553777",
    "run/identity.log": "1a54b7a398b628d20a16e2ecc8ec40e89b8bdfd31b3c146be48131d5a578bf73",
    "run/postprocessing_sensitivity.log": "c4aebb27a670674006a1847a7a495ebb9f8c5f1cd768cd422c614ffb2a19ed87",
    "run/robustness_a18.log": "7ea295d3ef64ca4a7614e9b8f2933742b5da08d813f72b051a6b009f15eaa30a",
    "run/sensitivity_a18.log": "6c5d0fe89fc9d01baac83ad5a23cfe63200426fb3a067687a5a2572e1417412e",
    "run/thresholds.csv": "d25e82e4acaf1a4f83eee1aeb54336cb22212e4dcedfbdce7fb29e6f808053ba",
    "run/units_only.json": "e703ac36a5a469e3a70800b5d0a1a7896a534e907bc7d47cdcab615eb4efb499",
    "run/units_only.log": "240b7976e85423c8fea4d0c1c4b10517aee911a990469fdea17033cd396a5234",
    "run/units_only_full.csv": "b76ae4b82ef31ac38e01476965b6831e462c8061f5b27b7bea27bc525c5d442e",
    "table_of_record_a18.csv": "13b0cc60961c1429ed1839587910ddf294ed3cd0f5e0a26d11f1214c16bb99ca",
    "tau_lower_bounds_a19.csv": "29f68a83bb287736b437cfeba6ffbbb5f072a8515ac058cd56a4683f01cfe3a7",
    "thresholds_a18.csv": "b361e09ddbcac88cbfd52c63bf2a7315698a3a9a64fd9dceea9fa8cab3cc7cfc",
}

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


@pytest.fixture(scope="module")
def evidence(tmp_path_factory):
    archive = GOLDEN / "capture_evidence.tar.gz"
    assert sha256(archive) == EVIDENCE_SHA256
    root = tmp_path_factory.mktemp("capture_evidence")
    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall(root, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))
    return root


def _banks_without_radiofisher(monkeypatch):
    from rfisher.forecast.radiofisher_bao import response
    from rfisher.forecast.radiofisher_bao.bank.backend import find_radiofisher_dir
    try:
        find_radiofisher_dir()
    except FileNotFoundError:
        monkeypatch.setattr(response, "evaluation_identity", lambda bank, rf_dir=None: ({}, {}))


def test_the_release_is_the_frozen_one(capture_handoff_dir, evidence, tmp_path, monkeypatch):
    _banks_without_radiofisher(monkeypatch)
    rel = tmp_path / "rel"
    quiet(capture_release.main, ["--rule", "r5_2", "--handoff", str(capture_handoff_dir), "--record-table",
                                 str(capture_handoff_dir / "frame_analysis" / "table_of_record.csv"),
                                 "--evidence", str(evidence / "evidence"), "--releases", str(evidence / "releases"),
                                 "--duration-reference", str(GOLDEN / "survey_duration_2026-09-24"),
                                 "--rel", str(rel), "--run", str(tmp_path / "run")])
    got = {p.relative_to(rel).as_posix(): sha256(p) for p in rel.rglob("*") if p.is_file() and p.name != "MANIFEST.json"}
    assert got == RELEASE
    manifest = json.loads((rel / "MANIFEST.json").read_text())
    doc = capture_release._release_doc()
    assert list(manifest) == [k for k in doc["key_order"] if k in manifest]
    assert {k: manifest[k] for k in doc["fields"]} == doc["fields"]
    assert {k: v for k, v in manifest["files"].items()} == RELEASE
    assert manifest["producer"]["repository"] == "WVURAIL/RFIsher"


def test_revision_3s_filter_sensitivity(capture_handoff_dir, evidence, tmp_path):
    """Revision 3 (no filter, the ground credit) against revision 2, from the ruling's own json."""
    table = capture_handoff_dir / "frame_analysis" / "table_of_record_before_amendment8.csv"
    quiet(capture_ruling.main, ["--rule", "a18", "--set", "TAU_LOWER_BOUNDS=off", "--sensitivity", "r3", "--json",
                                str(tmp_path / "a18.json"), "--input", str(table), "--handoff", str(capture_handoff_dir),
                                "--out", str(tmp_path / "full.csv"), "--ch33-rescan"])
    r3 = evidence / "releases" / "capture_ruling_a18_2026-09-24_r3"
    quiet(filter_sensitivity.main, [str(tmp_path / "a18.json"), str(r3 / "dispositions_a18.csv"),
                                    str(evidence / "releases" / "capture_ruling_a18_2026-09-24_r2"),
                                    str(tmp_path / "filter_sensitivity.csv")])
    assert sha256(tmp_path / "filter_sensitivity.csv") == sha256(r3 / "filter_sensitivity.csv")
