"""Exact forward calibration lookup and the boundary with archive rulings."""
from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

import pytest

from rfisher import cli
from rfisher.response import threshold
from rfisher.verdict import archive, handoff


def rewrite(root, name, transform):
    path = root / name
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        names, rows = reader.fieldnames, list(reader)
    transform(rows)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=names, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    manifest = json.loads((root / "manifest.json").read_text())
    manifest["files"][name] = handoff.sha256_file(path)
    (root / "manifest.json").write_text(json.dumps(manifest))


def edit_manifest(root, **changes):
    path = root / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest.update(changes)
    path.write_text(json.dumps(manifest))


@pytest.fixture
def complete(handoff_copy):
    root = handoff_copy.path
    edit_manifest(root, fine_surface_rows="complete",
                  fine_surface_scope=handoff.COMPLETE_SCOPE,
                  fine_surface_counts={"29": {"rho=1": 3}, "34": {"rho=1": 3}})
    return root


def test_forward_sweep_preserves_proxy_and_uniform_time(complete, tmp_path):
    response = threshold.read_forward([complete])
    assert response.sources[0].complete_calibration_grid
    assert not response.sources[0].thinned
    result = threshold.write_forward(response, tmp_path / "result", clean_years=2)
    assert len(result["rows"]) == 6
    first = result["rows"][0]
    assert first["eta_q16"] == 262144
    assert first["T_required_uniform_years"] == 4
    assert first["r_sys"] == response.sources[0].table[0]["r_sys"]
    assert first["source_refusal"]
    assert "not a physical bound" in first["residual_status"]
    manifest = json.loads((tmp_path / "result" / "manifest.json").read_text())
    assert manifest["sources"][0]["manifest"]["integration_model"]
    assert manifest["sources"][0]["summaries"]
    assert set(manifest["read"]) == {"source_0/manifest.json", "source_0/oc_table.csv",
                                      "source_0/oc_summary.csv"}


def test_exact_q16_above_float_integer_precision(complete):
    word = 2**53 + 1
    def change(rows):
        rows[2].update(eta_q16=str(word), eta_exact=f"{word}/65536",
                       eta=repr(word / 65536))
    rewrite(complete, "oc_table.csv", change)
    response = threshold.read_forward([complete])
    result = threshold.query(response, band="29", family="rho=1", eta_q16=word)
    assert result["eta_q16"] == word
    with pytest.raises(handoff.HandoffError, match="no snapping"):
        threshold.query(response, band="29", family="rho=1", eta_q16=word - 1)


def test_evaluation_rows_never_supply_a_query(complete):
    def change(rows):
        rows.append({**rows[0], "block": "evaluation",
                     "population": "current_era_evaluation_block",
                     "eta_q16": "196608", "eta_exact": "196608/65536", "eta": "3.0"})
    rewrite(complete, "oc_table.csv", change)
    response = threshold.read_forward([complete])
    assert len(threshold.sweep(response)) == 6
    with pytest.raises(handoff.HandoffError, match="no supported calibration"):
        threshold.query(response, band="29", family="rho=1", eta_q16=196608)


def test_empty_evaluation_does_not_break_calibration_lookup(complete):
    def change(rows):
        rows.append({**rows[0], "block": "evaluation",
                     "population": "current_era_evaluation_block", "kept": "0",
                     "masked": "192", "masked_fraction": "1.0",
                     "exposure_cost_uniform_loss": "", "r_sys": "", "r_var": "",
                     "r_sys_incoherent": "", "floor_share": ""})
    rewrite(complete, "oc_table.csv", change)
    assert len(threshold.sweep(threshold.read_forward([complete]))) == 6


def test_deployable_maximum_q16_and_overflow(complete):
    word = 2**64 - 1
    def change(rows):
        rows[2].update(eta_q16=str(word), eta_exact=f"{word}/65536",
                       eta=repr(word / 65536))
    rewrite(complete, "oc_table.csv", change)
    response = threshold.read_forward([complete])
    assert threshold.query(response, band="29", family="rho=1", eta_q16=word)["eta_q16"] == word
    with pytest.raises(ValueError, match="64-bit"):
        threshold.query(response, band="29", family="rho=1", eta_q16=word + 1)
    rewrite(complete, "oc_table.csv", lambda rows: rows[2].update(eta_q16=str(word + 1)))
    with pytest.raises(handoff.HandoffError, match="64-bit"):
        threshold.read_forward([complete])


def test_wrong_mask_comparison_is_refused(complete):
    edit_manifest(complete, mask_rule="statistic < eta")
    with pytest.raises(handoff.HandoffError, match="mask_rule"):
        threshold.read_forward([complete])


@pytest.mark.parametrize("scope", [None, "all_operational_thresholds"])
def test_complete_surface_requires_supported_calibration_scope(complete, scope):
    edit_manifest(complete, fine_surface_scope=scope)
    with pytest.raises(handoff.HandoffError, match="supported calibration scope"):
        threshold.read_forward([complete])


def test_duplicate_fine_summary_is_refused(complete):
    rewrite(complete, "oc_summary.csv", lambda rows: rows.append(dict(rows[0])))
    with pytest.raises(handoff.HandoffError, match="duplicate fine summary"):
        threshold.read_forward([complete])


def test_evaluation_summary_cannot_complete_calibration_surface(complete):
    rewrite(complete, "oc_summary.csv", lambda rows: rows[0].update(
        population="current_era_evaluation_block"))
    with pytest.raises(handoff.HandoffError, match="fine summary population"):
        threshold.read_forward([complete])


def test_under_supported_calibration_candidate_is_refused(complete):
    rewrite(complete, "oc_table.csv", lambda rows: rows[0].update(
        kept="29", masked="163", masked_fraction=repr(163 / 192),
        exposure_cost_uniform_loss=repr(192 / 29)))
    with pytest.raises(handoff.HandoffError, match="below 30 frames"):
        threshold.read_forward([complete])


def test_duplicate_candidate_order_is_refused(complete):
    rewrite(complete, "oc_table.csv", lambda rows: rows[1].update(
        candidate_order=rows[0]["candidate_order"]))
    with pytest.raises(handoff.HandoffError, match="duplicate fine candidate_order"):
        threshold.read_forward([complete])


@pytest.mark.parametrize("changes,match", [
    ({"eta_q16": "262145"}, "eta_q16"),
    ({"eta_exact": "262145/65536"}, "eta_q16"),
    ({"eta": "4.1"}, "eta_q16"),
    ({"rho": "2"}, "family/rank"),
    ({"rank_fraction": "0.1"}, "rank_fraction"),
    ({"kept": "97"}, "kept \\+ masked"),
    ({"masked_fraction": "0.6"}, "masked_fraction"),
    ({"exposure_cost_uniform_loss": "3"}, "exposure_cost"),
    ({"r_sys": "nan"}, "r_sys"),
    ({"floor_share": "1.1"}, "floor_share"),
    ({"population": "current_era_evaluation_block"}, "population/block"),
    ({"bulk_size": "125", "rank_fraction": str(1 / 126)}, "geometry"),
])
def test_corrupt_complete_rows_are_refused(complete, changes, match):
    rewrite(complete, "oc_table.csv", lambda rows: rows[0].update(changes))
    with pytest.raises(handoff.HandoffError, match=match):
        threshold.read_forward([complete])


@pytest.mark.parametrize("counts", [
    {"29": [], "34": {"rho=1": 3}},
    {"29": {"rho=1": True}, "34": {"rho=1": 3}},
    {"29": {"rho=1": 3}},
    {"29": {"rho=1": 2}, "34": {"rho=1": 3}},
    {"29": {"rho=2": 3}, "34": {"rho=1": 3}},
])
def test_complete_counts_are_exact_and_not_boolean(complete, counts):
    edit_manifest(complete, fine_surface_counts=counts)
    with pytest.raises(handoff.HandoffError):
        threshold.read_forward([complete])


def test_summary_count_and_actual_count_checked_separately(complete):
    rewrite(complete, "oc_table.csv", lambda rows: rows.pop())
    with pytest.raises(handoff.HandoffError, match="row count"):
        threshold.read_forward([complete])


def test_keep_must_not_decrease_at_increasing_threshold(complete):
    def change(rows):
        rows[1].update(kept="48", masked="144", masked_fraction="0.75",
                       exposure_cost_uniform_loss="4")
    rewrite(complete, "oc_table.csv", change)
    with pytest.raises(handoff.HandoffError, match="monotone"):
        threshold.read_forward([complete])


def test_candidate_order_gaps_are_allowed_but_reordering_is_not(complete):
    rewrite(complete, "oc_table.csv", lambda rows: rows[2].update(candidate_order="7"))
    threshold.read_forward([complete])
    rewrite(complete, "oc_table.csv", lambda rows: rows.__setitem__(slice(0, 2), rows[1::-1]))
    with pytest.raises(handoff.HandoffError, match="monotone"):
        threshold.read_forward([complete])


@pytest.mark.parametrize("token", [None, "complete: every evaluable candidate", "unexpected"])
def test_unrecognized_completeness_produces_status_without_curve(complete, tmp_path, token):
    edit_manifest(complete, fine_surface_rows=token)
    result = threshold.write_forward(threshold.read_forward([complete]), tmp_path / "result")
    assert result["rows"] == []
    assert len(result["bands"]) == 2
    assert all(row["status"] == "incomplete calibration surface" for row in result["bands"])


def test_control_and_empty_bands_remain_in_status(complete, tmp_path):
    manifest = json.loads((complete / "manifest.json").read_text())
    manifest["bands"].append({"band_id": "37", "low_mhz": 608, "high_mhz": 614,
                              "role": "control", "marker_freq_id": 477})
    manifest["fine_surface_counts"]["37"] = {}
    edit_manifest(complete, **manifest)
    result = threshold.write_forward(threshold.read_forward([complete]), tmp_path / "result",
                                     band="29", family="rho=1")
    control = result["bands"][-1]
    assert control["band_role"] == "control"
    assert control["status"] == "no supported calibration candidates"
    assert len(result["bands"]) == 3
    assert result["bands"][1]["status"] == "excluded by requested filters"


def test_zero_candidate_summary_is_preserved(complete, tmp_path):
    rewrite(complete, "oc_table.csv", lambda rows: rows.__setitem__(slice(3, None), []))
    rewrite(complete, "oc_summary.csv", lambda rows: rows[1].update(candidates_evaluable="0"))
    edit_manifest(complete, fine_surface_counts={"29": {"rho=1": 3}, "34": {"rho=1": 0}})
    result = threshold.write_forward(threshold.read_forward([complete]), tmp_path / "result")
    assert result["bands"][1]["supported_candidates"] == 0
    assert result["bands"][1]["source_refusal"]


def test_complete_handoff_is_refused_by_archive_before_output(complete, tmp_path):
    project = Path(__file__).resolve().parents[2] / "projects" / "chime_bao"
    with pytest.raises(handoff.HandoffError, match="forward-only"):
        archive.verdict_archive(complete, tmp_path / "missing-tolerances.csv",
                                project, tmp_path / "verdict")
    assert not (tmp_path / "verdict").exists()


def test_path_traversal_and_duplicate_bands_refused(complete):
    manifest = json.loads((complete / "manifest.json").read_text())
    manifest["files"]["../outside"] = "ignored"
    edit_manifest(complete, **manifest)
    with pytest.raises(handoff.HandoffError, match="unsafe"):
        threshold.read_forward([complete])
    del manifest["files"]["../outside"]
    edit_manifest(complete, **manifest)
    with pytest.raises(handoff.HandoffError, match="duplicate bands"):
        threshold.read_forward([complete, complete])


def test_separate_control_input_and_common_model_identity(complete, tmp_path):
    control = tmp_path / "control"
    shutil.copytree(complete, control)
    for filename in ("oc_table.csv", "oc_summary.csv"):
        def change(rows):
            rows[:] = [row for row in rows if row["band_id"] == "29"]
            for row in rows:
                row.update(band_id="37", band_low_mhz="608", band_high_mhz="614")
                if "band_role" in row:
                    row["band_role"] = "control"
        rewrite(control, filename, change)
    edit_manifest(control, bands=[{"band_id": "37", "low_mhz": 608,
                                    "high_mhz": 614, "role": "control"}],
                  fine_surface_counts={"37": {"rho=1": 3}})
    response = threshold.read_forward([complete, control])
    assert len(threshold.sweep(response)) == 9
    assert threshold.query(response, band="37", family="rho=1",
                           eta_q16=262144)["band_role"] == "control"
    manifest = json.loads((control / "manifest.json").read_text())
    manifest["integration_model"]["frame_seconds"] = 1
    edit_manifest(control, **manifest)
    with pytest.raises(handoff.HandoffError, match="incompatible integration_model"):
        threshold.read_forward([complete, control])


@pytest.mark.parametrize("years", [0, -1, float("inf"), float("nan"), True])
def test_clean_years_must_be_positive_finite(complete, years):
    with pytest.raises(ValueError, match="clean_years"):
        threshold.sweep(threshold.read_forward([complete]), clean_years=years)


def test_cli_exact_query_and_new_directory(complete, tmp_path):
    out = tmp_path / "export"
    args = ["response", "threshold", "--characterization", str(complete),
            "--out", str(out), "--band", "29", "--family", "rho=1",
            "--eta-q16", "262144", "--eta-q16", "524288"]
    assert cli.main(args) == 0
    assert len(list(csv.DictReader((out / "response.csv").open()))) == 2
    with pytest.raises(SystemExit) as exc:
        cli.main(args)
    assert exc.value.code == 2


def test_cli_exact_query_requires_band_and_family(complete, tmp_path):
    with pytest.raises(SystemExit) as exc:
        cli.main(["response", "threshold", "--characterization", str(complete),
                  "--out", str(tmp_path / "export"), "--eta-q16", "262144"])
    assert exc.value.code == 2
    assert not (tmp_path / "export").exists()


def test_write_refuses_a_source_changed_since_read(complete, tmp_path):
    response = threshold.read_forward([complete])
    edit_manifest(complete, mask_rule="different")
    with pytest.raises(handoff.HandoffError, match="source changed"):
        threshold.write_forward(response, tmp_path / "export")
    assert not (tmp_path / "export").exists()
