"""The handoff checks (rfisher.verdict.handoff)."""
from __future__ import annotations

import json
import math

import pytest

from rfisher.verdict import handoff

R_REFERENCE = {
    "definition": "residual interference power over system noise power per "
                  "frame, in the band",
    "feed_sum": "all_inputs", "frame_seconds": 0.04194304,
    "noise_bandwidth_hz": 6000000.0, "summed_terms": 262144}


def test_the_schema_version_is_pinned():
    spec = handoff.schema()
    assert spec["properties"]["schema"]["const"] == handoff.SCHEMA
    assert spec["properties"]["schema_version"]["const"] == \
        handoff.SCHEMA_VERSION == 1


def test_the_vendored_golden_handoff_reads(handoff_copy):
    oc = handoff.read_characterization(handoff_copy.path,
                                       r_reference=R_REFERENCE,
                                       residual_shapes=("band_thermal",))
    assert len(oc.table) == 6 and len(oc.summary) == 2
    assert set(oc.bands) == {"29", "34"} and oc.thinned
    row = oc.table[0]
    assert row["eta"] == 4.0 and row["candidate_order"] == 0
    assert math.isnan(row["pfa"]) and row["mark"] == "least_residual"
    assert oc.summary[0]["floor_verified"] is False
    assert set(oc.sha256) == {"oc_table.csv", "oc_summary.csv",
                              "manifest.json"}


def test_a_file_that_differs_from_its_manifest_is_refused(handoff_copy):
    path = handoff_copy.path / "oc_table.csv"
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(handoff.HandoffError, match="sha256"):
        handoff.read_characterization(handoff_copy.path)


@pytest.mark.parametrize("field,value,match", [
    ("r_reference", {**R_REFERENCE, "noise_bandwidth_hz": 5.0e6},
     "r_reference"),
    ("residual_shape", "band_flat", "residual shape"),
    ("schema_version", 2, "version"),
    ("schema", "capture_operating_characteristic", "schema"),
])
def test_a_manifest_that_disagrees_is_refused(handoff_copy, field, value,
                                              match):
    path = handoff_copy.path / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest[field] = value
    path.write_text(json.dumps(manifest))
    with pytest.raises(handoff.HandoffError, match=match):
        handoff.read_characterization(handoff_copy.path,
                                      r_reference=R_REFERENCE,
                                      residual_shapes=("band_thermal",))


def test_band_edges_must_be_the_manifests(handoff_copy):
    path = handoff_copy.path / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["bands"][0]["high_mhz"] = 567.0
    path.write_text(json.dumps(manifest))
    with pytest.raises(handoff.HandoffError, match="edges"):
        handoff.read_characterization(handoff_copy.path)


def test_a_missing_key_or_column_is_refused(handoff_copy):
    path = handoff_copy.path / "manifest.json"
    manifest = json.loads(path.read_text())
    del manifest["null_policy"]
    path.write_text(json.dumps(manifest))
    with pytest.raises(handoff.HandoffError, match="missing"):
        handoff.read_characterization(handoff_copy.path)


def test_tolerance_rows_and_their_edges(handoff_copy, tolerances):
    oc = handoff.read_characterization(handoff_copy.path)
    rows = handoff.read_tolerances(
        tolerances({"29": [("none", "rule", 0.02, 0.0)],
                    "34": [("none", "rule", None, 0.0)]}), oc.bands)
    assert rows[0]["r_tol"] == 0.02 and math.isnan(rows[1]["r_tol"])
    shifted = dict(oc.bands)
    shifted["29"] = {**shifted["29"], "low_mhz": 559.0}
    with pytest.raises(handoff.HandoffError, match="edges"):
        handoff.read_tolerances(tolerances({"29": [("none", "rule", 0.02,
                                                    0.0)]}), shifted)
