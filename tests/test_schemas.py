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
SCHEMA_SHA256 = "7fa22223e7977b745e750b5b612958ce2e28b6727a6d27ccd465059fca3526a2"
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
