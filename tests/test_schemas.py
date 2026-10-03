"""The vendored handoff schema and the golden handoff it describes.

The schema is the detector repository's file byte for byte, pinned by its
sha256; the golden handoff is that repository's small fixture, pinned the
same way. Neither is fetched from the other repository at test time.
"""
from __future__ import annotations

import csv
import hashlib
import json
from importlib.resources import files
from pathlib import Path

import pytest

SCHEMA = "operating_characteristic_v1.schema.json"
SCHEMA_SHA256 = "8267e9e0990ad531675ba5f9ab01aede92cfe4787ada938c7978f7d400143cd2"
GOLDEN = Path(__file__).resolve().parent / "golden" / "handoff" / "archive"
GOLDEN_SHA256 = {
    "manifest.json":
        "023a0177c6fd74e383e9c53b354fb6e1dce3ee24149cfa678da23c1a5d0c1b89",
    "oc_summary.csv":
        "957c35e849a6e26d0ae3880feaa4426775a7724df0bf38fcc917f2f2f07e22fd",
    "oc_table.csv":
        "8611b3dbc71222f929db362174f45422b68cb36ad8d0f6edb0597fdca9e115a3",
}


def _schema_bytes() -> bytes:
    return files("rfisher.data").joinpath("schemas", SCHEMA).read_bytes()


def test_the_vendored_schema_is_pinned():
    assert hashlib.sha256(_schema_bytes()).hexdigest() == SCHEMA_SHA256
    schema = json.loads(_schema_bytes())
    assert schema["properties"]["schema"] == {"const": "operating_characteristic"}
    assert schema["properties"]["schema_version"] == {"const": 1}


def test_the_golden_handoff_is_pinned():
    for name, sha in GOLDEN_SHA256.items():
        assert hashlib.sha256((GOLDEN / name).read_bytes()).hexdigest() == sha


def test_the_golden_handoff_has_the_schemas_columns():
    schema = json.loads(_schema_bytes())
    for name, key in (("oc_table.csv", "x-oc-table-columns"),
                      ("oc_summary.csv", "x-oc-summary-columns")):
        with (GOLDEN / name).open(newline="", encoding="utf-8") as fh:
            header = next(csv.reader(fh))
        assert header == [c["name"] for c in schema[key]]


def test_the_golden_manifest_validates_against_the_schema():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(_schema_bytes())
    manifest = json.loads((GOLDEN / "manifest.json").read_text(encoding="utf-8"))
    jsonschema.validate(manifest, schema)
    for name, sha in manifest["files"].items():
        assert hashlib.sha256((GOLDEN / name).read_bytes()).hexdigest() == sha


CAPTURE_SCHEMA = "capture_operating_characteristic_v1.schema.json"
CAPTURE_SCHEMA_SHA256 = "0b406a23c947000f7fcfd48c2723c2ca84f3b17ac2c37c211b76e9328a69861d"
CAPTURE_GOLDEN = Path(__file__).resolve().parent / "golden" / "handoff" / "capture_oc" / "capture_oc.tar.gz"
CAPTURE_GOLDEN_SHA256 = {
    "capture_oc.tar.gz": "37211d416b877fb39d08a9fd0c7ceff1df48bf4ffc0c488653670c4398a01e5d",
    "manifest.json": "87524b592f33d7a8dfda30234e70022a1a800866c3a24bfe301a267e186566b1",
    "capture_oc_summary.csv": "2284f15a6e43b203a9f384df4cb60a0d479603b88c64ef41fe29cc0857ae244e",
    "capture_oc_table.csv": "81f157c2f900d1f1aeae27e3be37e13a90a83f56002c56e5d498fd6ec9d0d60b",
    "capture_tau_bounds.csv": "103ed35e7b7b31fb1cee3d6337df6744479fb482d1ac26b401baf61aecb03dbe",
}


def _capture_golden(tmp_path) -> Path:
    import tarfile
    assert hashlib.sha256(CAPTURE_GOLDEN.read_bytes()).hexdigest() == CAPTURE_GOLDEN_SHA256["capture_oc.tar.gz"]
    root = tmp_path / "capture_oc"
    with tarfile.open(CAPTURE_GOLDEN, "r:gz") as tar:
        tar.extractall(root, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))
    for name, sha in CAPTURE_GOLDEN_SHA256.items():
        if name != "capture_oc.tar.gz":
            assert hashlib.sha256((root / name).read_bytes()).hexdigest() == sha, name
    return root


def test_the_vendored_capture_schema_is_pinned():
    data = files("rfisher.data").joinpath("schemas", CAPTURE_SCHEMA).read_bytes()
    assert hashlib.sha256(data).hexdigest() == CAPTURE_SCHEMA_SHA256
    schema = json.loads(data)
    assert schema["properties"]["schema"] == {"const": "capture_operating_characteristic"}
    assert schema["properties"]["schema_version"] == {"const": 1}


def test_capture_golden_source_records_every_file():
    source = json.loads((CAPTURE_GOLDEN.parent / "SOURCE.json").read_text(encoding="utf-8"))
    assert source["commit"] == "1b57419d73c788d139a0b81237430eeb3a9a1ab0"
    assert source["archive_sha256"] == CAPTURE_GOLDEN_SHA256["capture_oc.tar.gz"]
    assert source["files"] == {name: sha for name, sha in CAPTURE_GOLDEN_SHA256.items() if name != "capture_oc.tar.gz"}


def test_the_golden_capture_handoff_has_the_schemas_columns(tmp_path):
    from rfisher.records.chime_atsc_2026 import capture_oc
    root = _capture_golden(tmp_path)
    for name, columns in capture_oc.schema_columns().items():
        with (root / name).open(newline="", encoding="utf-8") as fh:
            assert next(csv.reader(fh)) == columns, name
    assert tuple(capture_oc.schema_columns()["capture_tau_bounds.csv"]) == capture_oc.TAU_COLUMNS


def test_the_capture_handoff_reader_reads_the_golden(tmp_path):
    from rfisher.records.chime_atsc_2026 import capture_oc
    root = _capture_golden(tmp_path)
    read = capture_oc.read_oc(root)
    assert read["sha256"]["manifest.json"] == CAPTURE_GOLDEN_SHA256["manifest.json"]
    assert {name: rows[0] for name, rows in read.items() if name.endswith(".csv")} == capture_oc.schema_columns()
