"""The archive verdict's union row and its tolerance rows (rfisher.verdict.archive)."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from oc_rows import histogram_rows, summary_row
from rfisher import policy
from rfisher.response.evidence import (
    HISTORICAL_SCREENING_EVIDENCE, UnqualifiedResponseError,
    require_science_selection_evidence,
)
from rfisher.verdict import archive, handoff, screening

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "projects" / "chime_bao"


def _families(pol, r_tol):
    rows = histogram_rows({
        "1": {"candidate_multiplier_q16": [65536, 131072], "counts": [30, 30, 40],
              "systematic_residual_sums": [90.0, 60.0, 40.0]},
        "63": {"candidate_multiplier_q16": [65536, 131072], "counts": [30, 30, 40],
               "systematic_residual_sums": [150.0, 90.0, 40.0]}})
    for r in rows:
        r["r_sys_incoherent"] = r["r_sys"] / 10.0
        r["floor_share"] = 0.25
    summaries = [summary_row(f, rows) for f in ("rho=1", "rho=63")]
    return rows, summaries, screening.family_readings(rows, summaries, r_tol, pol)


def test_the_union_reads_the_least_point_of_the_families_it_covers():
    pol = policy.load(PROJECT)
    rows, summaries, families = _families(pol, 1.0)
    tol = {"scenario": "none", "role": "rule", "r_tol": 1.0, "tolerance_basis": "b"}
    surface = {**summaries[0], "least_residual_rho": 1, "least_residual_r_sys": 2.5,
               "least_residual_eta": 2.0, "least_residual_r_sys_incoherent": 0.25,
               "least_residual_floor_share": 0.25}
    whole = archive._union_row({}, tol, families, surface, "", pol)
    assert (whole["min_R"], whole["min_R_eta"]) == (2.5, 2.0)      # the detector's point of the whole surface
    one = [f for f in families if f.family == "rho=63"]
    part = archive._union_row({}, tol, one, surface, "", pol, whole_surface=False)
    least = one[0].keep.least
    assert (part["min_R"], part["min_R_eta"]) == (least.R, least.eta)
    assert part["min_R"] == 4.0 and part["min_R_incoherent"] == 0.4
    assert part["min_R_floor_share"] == 0.25


def test_a_band_with_two_rule_scenarios_is_refused(handoff_copy, tolerances, tmp_path):
    tol = tolerances({"29": [("none", "rule", 1000.0, 0.0), ("other", "rule", 900.0, 0.0)],
                      "34": [("none", "rule", 100.0, 0.0)]})
    with pytest.raises(handoff.HandoffError, match="2 rule scenarios"):
        archive.verdict_archive(handoff_copy.path, tol, PROJECT, tmp_path / "out")


def test_all_new_archive_exports_declare_historical_screening_scope(
        handoff_copy, tolerances, tmp_path):
    tol = tolerances({"29": [("none", "rule", 1.0, 0.0)],
                      "34": [("none", "rule", 1.0, 0.0)]})
    out = tmp_path / "out"
    result = archive.verdict_archive(handoff_copy.path, tol, PROJECT, out)
    for record in result["screen"]:
        assert all(record[key] == value
                   for key, value in HISTORICAL_SCREENING_EVIDENCE.items())
    manifest = json.loads((out / "manifest.json").read_text())
    assert all(manifest[key] == value
               for key, value in HISTORICAL_SCREENING_EVIDENCE.items())
    assert "verified sensitivity floors are not detected RFI" in manifest["outcome_interpretation"]
    for name in ("verdict.csv", "verdict_points.csv", "screen.csv", "sensitivity.csv"):
        with (out / name).open(newline="") as stream:
            reader = csv.DictReader(stream)
            assert set(HISTORICAL_SCREENING_EVIDENCE) <= set(reader.fieldnames)
            for record in reader:
                assert all(record[key] == str(value)
                           for key, value in HISTORICAL_SCREENING_EVIDENCE.items())
                with pytest.raises(UnqualifiedResponseError):
                    require_science_selection_evidence(record)
