"""The capture release builder, from the golden handoff, byte for byte.

The release also reads revision 5 and the survey-duration run, which tests/golden/records/capture_evidence.tar.gz and
survey_duration_2026-09-24/ carry (byte copies). Where no RadioFisher checkout is present the response banks'
authentication against it is stubbed; the Fisher matrices are the packaged banks' either way.

Post-processing is not modelled (stage P, 2026-10-06), so the builder no longer writes the release's credit readings
(credit_readings/r2 and r3), its post-processing sensitivity, its least-corner promotion evidence, or the credit
columns of robustness_a18.csv and ch24_per_bin_a19.csv and channel 24's archive-share reading. Their pins and the tests
of the credit readings and of revision 3's filter sensitivity are retired; the frozen release
(results/capture_ruling_a19_2026-09-25_r5_2) keeps those files. The five files pinned under CHANGED were checked
against the frozen release when the change was made: each differs only by the removed post-processing columns,
fields or clause.
"""
from __future__ import annotations

import json
import tarfile
from pathlib import Path

import pytest

from capture_golden import assert_frozen, duration_reference, quiet, sha256, record_input
from rfisher.records.chime_atsc_2026 import capture_release, capture_ruling

GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "records"
EVIDENCE_SHA256 = "4615d7fe5b7f2277b621fbc9b448ed184ceaada07cb3114a3c019f5ee5ef8ecf"
# every file of the release r5.2 the builder writes (MANIFEST.json, tests_a18.txt and the source snapshot aside)
RELEASE = {
    "CHANGES.md": "22cd5161ca23fc4c5bc3c03fcf2a144be450c302ae5c5bc39ee20eda1e08086c",
    "ch24_basis_a18.txt": "d08599fc69bc83db68d295df022e29e574c0036196d1643efc76765553399504",
    "ch24_per_bin_a19.csv": "657f0ecadbf5b3fe6b00c1b0feed0ebae58ed909570706a897e75f7ac4a2d34d",
    "dispositions_a18.csv": "81db673818ecbfff0fc7ce18e738d57939cd3e12b80690ca3c1f66d2fedb7755",
    "duration_nofilter.csv": "855d45b1af93771386c869f3f79609a7d99b7021ad5dbbcc3d2370e69f63e7ed",
    "keep_gap_a18.csv": "79d1999c5d7e0f3791aec1c37dfd75940b2597586cd284597327a99d05dd6feb",
    "phase_limit_a18/phase_limit_a18.log": "519903dcf32d204e3582cec2df096a0c477d3ccd11cc9a1ea6a2af758523b886",
    "phase_limit_a18/phase_limit_classes_a18.csv": "41dbcb6e3a3f5e470fe9629231e71ac0c26f623a404c8d0c3c2b255576ef8e31",
    "phase_limit_a18/phase_limit_ranges_a18.csv": "f6e102ac4b653893c532d5466fb347c3174e27682e660c30b6dfa8a60da398b6",
    "robustness_a18.csv": "a1c891758d4a5433aae8f3b20c10fe42601dfdd6fd94b6d38c6a1cce1e5c62b5",
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
    "run/ch24_a18.json": "815ababcf24b7c33a2f782061a0f125a0869e7fc8d63b3c510b8ca27fab9ab93",
    "run/identity.log": "1a54b7a398b628d20a16e2ecc8ec40e89b8bdfd31b3c146be48131d5a578bf73",
    "run/robustness_a18.log": "9f71dc2f32f9aa80b85352bc275decd2362b28b348c9c56e9608c7aaf93aea41",
    "run/sensitivity_a18.log": "6c5d0fe89fc9d01baac83ad5a23cfe63200426fb3a067687a5a2572e1417412e",
    "run/thresholds.csv": "d25e82e4acaf1a4f83eee1aeb54336cb22212e4dcedfbdce7fb29e6f808053ba",
    "run/units_only.json": "e703ac36a5a469e3a70800b5d0a1a7896a534e907bc7d47cdcab615eb4efb499",
    "run/units_only.log": "240b7976e85423c8fea4d0c1c4b10517aee911a990469fdea17033cd396a5234",
    "run/units_only_full.csv": "b76ae4b82ef31ac38e01476965b6831e462c8061f5b27b7bea27bc525c5d442e",
    "table_of_record_a18.csv": "13b0cc60961c1429ed1839587910ddf294ed3cd0f5e0a26d11f1214c16bb99ca",
    "tau_lower_bounds_a19.csv": "29f68a83bb287736b437cfeba6ffbbb5f072a8515ac058cd56a4683f01cfe3a7",
    "thresholds_a18.csv": "b361e09ddbcac88cbfd52c63bf2a7315698a3a9a64fd9dceea9fa8cab3cc7cfc",
}
# the files that differ from the frozen release by the removed post-processing content alone
CHANGED = {"ch24_basis_a18.txt", "ch24_per_bin_a19.csv", "robustness_a18.csv", "run/ch24_a18.json", "run/robustness_a18.log"}


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
                                 str(record_input("table_of_record.csv")), "--input-table",
                                 str(record_input("table_of_record_before_amendment8.csv")),
                                 "--releases", str(evidence / "releases"),
                                 "--duration-reference", str(duration_reference(tmp_path)),
                                 "--rel", str(rel), "--run", str(tmp_path / "run")])
    got = {p.relative_to(rel).as_posix(): sha256(p) for p in rel.rglob("*") if p.is_file() and p.name != "MANIFEST.json"}
    assert_frozen(got, RELEASE)
    manifest = json.loads((rel / "MANIFEST.json").read_text())
    doc = capture_release._release_doc()
    assert list(manifest) == [k for k in doc["key_order"] if k in manifest]
    assert {k: manifest[k] for k in doc["fields"]} == doc["fields"]
    assert manifest["files"] == got
    assert manifest["producer"]["repository"] == "WVURAIL/RFIsher"
    # the files the release has and the builder does not write, or writes without their post-processing content
    assert CHANGED - {"run/robustness_a18.log"} <= set(manifest["not_written"]) and CHANGED <= set(RELEASE)
    assert not any(k.startswith("credit_readings/") or k.startswith("PROMOTION") for k in got)
