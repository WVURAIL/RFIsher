"""The chapter 11 matrix, the appendix C atlas counts and the headline numbers."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

import pytest

from rfisher_results.archive import screening as sc
from rfisher_results.archive.report import conclusions_matrix as cm
from rfisher_results.archive.report import core

REAL_RESULTS = Path(os.environ.get("RFISHER_ARCHIVE_RESULTS", "/home/djg/rail/results/archive_v5_2026-09-07"))
RAIL = "baseband_power_at_negative_full_scale_ceiling"
NO_FLOOR = "no floor for frames without a shelf estimate: the residual convention cannot price them"


def _record(channel, freq_id, sections):
    return {"channel": channel, "freq_id": freq_id, "product": f"{freq_id}.npz", "product_sha256": "b" * 64, "notes": [],
            "sections": sections}


def _sections():
    """Six synthetic channels covering every column and its absent cases."""
    return {
        21: _record(21, 736, {                                    # a feasible selected point, replayed
            "product": {"n_frames": 2100, "n_valid": 2090, "health_excluded": 10, "health_reasons": f"{RAIL}:6;weird_reason:4"},
            "era": {"current_first_month": "2019-01", "current_last_month": "2026-08", "current_frames": 2000},
            "selection": {"rho": 1, "eta": 1.05, "status": "feasible", "claim_status": "screening", "floor_evidence": "measured",
                          "masked_fraction_calibration": 0.4, "calibration_frames": 1000, "kept_evaluation": 500,
                          "masked_fraction_evaluation": 0.45, "diagnostic_masked_fraction": None, "min_R": 0.8,
                          "coarse_min_R": 0.7, "coarse_min_R_masked_fraction": 0.3},
            "null": {"floor_evidence": "measured", "floor_basis": "off era p90", "coarse_centre_db": 0.01,
                     "coarse_core_width_factor": 1.5, "fine_core_width_factor": 1.2},
            "chain": {"tau_quality": "bounded_above"},
            "screening": {"screening_class": sc.BOUND_FLOOR}}),
        23: _record(23, 706, {                                    # no feasible point: diagnostic point, replay kept nothing
            "product": {"n_frames": 3000, "n_valid": 3000, "health_excluded": 0, "health_reasons": ""},
            "era": {"current_first_month": "2020-02", "current_last_month": "2026-08", "current_frames": 1000},
            "selection": {"rho": None, "status": "no feasible point", "claim_status": "diagnostic", "floor_evidence": "stated",
                          "masked_fraction_calibration": None, "calibration_frames": 500, "diagnostic_masked_fraction": 0.9,
                          "kept_evaluation": 0, "masked_fraction_evaluation": 1.0, "min_R": 5.0, "coarse_min_R": None},
            "null": {"floor_evidence": "stated", "floor_basis": "bulk left side (not H0)", "coarse_centre_db": 0.3,
                     "coarse_core_width_factor": 15.5, "fine_core_width_factor": 5.0},
            "chain": {"tau_quality": "refused"},
            "screening": {"screening_class": sc.BOUND_TAU}}),
        22: _record(22, 721, {                                    # diagnostic point, never replayed; refused floor
            "product": {"n_frames": 4000, "n_valid": 3990, "health_reasons": ""},
            "era": {"current_first_month": "2018-12", "current_last_month": "2026-08", "current_frames": 3500},
            "selection": {"rho": None, "status": "no feasible point", "claim_status": "diagnostic", "floor_evidence": "refused",
                          "calibration_frames": 1750, "diagnostic_masked_fraction": 0.98, "kept_evaluation": None,
                          "masked_fraction_evaluation": None, "min_R": 100.0, "coarse_min_R": 90.0, "coarse_min_R_masked_fraction": 0.5},
            "null": {"floor_evidence": "refused", "floor_basis": "none", "coarse_centre_db": 5.6,
                     "coarse_core_width_factor": 187.0, "fine_core_width_factor": 2.3},
            "chain": {"tau_quality": "measured"},
            "screening": {"screening_class": sc.WALL}}),
        24: _record(24, 690, {                                    # the selector refused: no surface at all
            "product": {"n_frames": 5000, "n_valid": 5000, "health_excluded": 2, "health_reasons": f"{RAIL}:2"},
            "era": {"current_first_month": "2019-03", "current_last_month": "2026-04", "current_frames": 4000},
            "selection": {"rho": None, "status": "refused", "refusal": NO_FLOOR, "claim_status": "", "floor_evidence": "refused",
                          "calibration_frames": 2000, "diagnostic_masked_fraction": None, "kept_evaluation": 0,
                          "masked_fraction_evaluation": None, "min_R": None, "coarse_min_R": None},
            "null": {"floor_evidence": "refused", "floor_basis": "none", "coarse_centre_db": 20.0,
                     "coarse_core_width_factor": 15000.0, "fine_core_width_factor": 41.5},
            "chain": {"tau_quality": "refused"},
            "screening": {"screening_class": sc.WALL}}),
        19: _record(19, 767, {                                    # off era with no selection, null or chain record
            "product": {"n_frames": 500, "n_valid": 480, "health_excluded": 3, "health_reasons": "detector_invalid:20"},
            "era": {"current_frames": 300},
            "selection": None, "null": None, "chain": None,
            "screening": {"screening_class": sc.OFF_ERA}}),
        40: _record(40, 400, {                                    # unscreened
            "product": {"n_frames": 10, "n_valid": 10, "health_excluded": 0, "health_reasons": ""},
            "era": {"current_first_month": "2024-01", "current_last_month": "2024-02", "current_frames": 10},
            "selection": None, "null": {"floor_evidence": "odd"}, "chain": {"tau_quality": "unmeasured"}}),
    }


def _ledger(tmp_path, records=None, *, kstar=True, e_min=0.9):
    records = _sections() if records is None else records
    ledger = tmp_path / "ledger"
    (ledger / "channels").mkdir(parents=True, exist_ok=True)
    files = []
    for ch, rec in sorted(records.items()):
        rel = f"channels/ch{ch:02d}_fid{rec['freq_id']}.json"
        (ledger / rel).write_text(json.dumps(rec))
        files.append(rel)
    run = {"schema": {"name": "rfisher-archive-ledger", "version": 1}, "generated": "2026-09-07T00:00:00+00:00",
           "producer": {"commit": "a" * 40}, "products": {}, "channels": files, "era_config_digest": "c" * 64,
           "provisional": {"e_min": e_min}}
    (ledger / "run.json").write_text(json.dumps(run))
    if kstar:
        (tmp_path / "tables").mkdir(exist_ok=True)
        (tmp_path / "tables" / "kstar.csv").write_text(
            "e_min,k_star,failing_k,binding_channel,binding_e,sentinels,eligible\n"
            "0.8,256,512,21,0.81,33,21;22;23\n0.9,128,256,23,0.7929,33,21;22;23\n")
    return core.load_run(tmp_path)


def _rows(tex: str) -> list[list[str]]:
    """Body rows of a booktabs tabular as lists of stripped cells."""
    lines = tex.splitlines()
    body = lines[lines.index(r"\midrule") + 1: lines.index(r"\bottomrule")]
    return [[c.strip() for c in ln[:-2].split(" & ")] for ln in body if ln.endswith(r"\\")]


def _by_key(frag):
    keys = [n.key for n in frag.numbers]
    assert len(keys) == len(set(keys)), "duplicate number keys"
    return {n.key: n for n in frag.numbers}


# ------------------------------------------------------------------ helpers
def test_policy_class_and_point_helpers(tmp_path):
    assert cm.policy_of(sc.WALL) == cm.POLICY_EXCISED
    assert all(cm.policy_of(c) == cm.POLICY_KEPT for c in (sc.RECOVERY, sc.BOUND_FLOOR, sc.BOUND_TAU, sc.OFF_ERA))
    assert cm.policy_of(cm.UNCLASSIFIED) == cm.POLICY_NONE and cm.policy_of("") == cm.POLICY_NONE
    assert cm.render_reasons(f"{RAIL}:7") == "rail 7"
    assert cm.render_reasons(f"{RAIL}:5;detector_invalid:4;detector_powers_all_zero:4") == "rail 5, invalid 4, all-zero 4"
    assert cm.render_reasons("odd_name:2") == r"odd\_name 2" and cm.render_reasons("") == "" and cm.render_reasons(None) == ""
    assert cm._sig(299.37) == ("299", 0) and cm._sig(2.3077) == ("2.31", 2) and cm._sig(0.01234) == ("0.0123", 4)
    assert cm._sig(None) == (core.DASH, None) and cm._sig(0.0) == ("0", 0) and cm._sig(math.inf) == (core.DASH, None)
    assert cm._slug("bulk left side (not H0)") == "bulk_left_side_not_h0" and cm._slug("kept half about mu_0") == "kept_half_about_mu_0"

    by = _ledger(tmp_path).by_channel()
    assert cm.operating_point_fraction(by[21]) == (0.4, "selected")
    assert cm.operating_point_fraction(by[23]) == (0.9, "diagnostic")
    assert cm.operating_point_fraction(by[24]) == (None, "") and cm.operating_point_fraction(by[19]) == (None, "")
    assert cm.kept_at_point(by[21]) == {"basis": "selected", "calibration": 600, "evaluation": 500}
    assert cm.kept_at_point(by[23]) == {"basis": "diagnostic", "calibration": 50, "evaluation": 0}
    assert cm.kept_at_point(by[22]) == {"basis": "diagnostic", "calibration": 35, "evaluation": None}
    assert cm.kept_at_point(by[24]) == {"basis": "", "calibration": None, "evaluation": None}
    assert cm.selection_status(by[24]) == "refused" and cm.selection_status(by[19]) == cm.SELECTION_NONE


# ------------------------------------------------------------------ (a) the matrix
def test_matrix_counts_policies_statuses_and_band_level(tmp_path):
    run = _ledger(tmp_path)
    frag = cm.build(run)
    assert frag.name == "conclusions_matrix" and frag.label == "tab:conclusions:matrix"
    rows = _rows(frag.tex)
    labels = {r[0]: r for r in rows}
    assert labels[r"\quad recovery candidate"][1] == "0"
    assert labels[r"\quad measurement-bound on floor"][1] == "1"
    assert labels[r"\quad measurement-bound on $\tau_c$"][1] == "1"
    assert labels[r"\quad occupancy-wall excision candidate"][1] == "2"
    assert labels[r"\quad off-era"][1] == "1"
    assert labels[r"\quad unclassified (no screening record)"][1] == "1"
    assert labels[r"\quad kept-and-masked, at the operating point"][1] == "3"
    assert labels[r"\quad of which evaluated on an off era"][1] == "1"
    assert labels[r"\quad excised interior"][1] == "2"
    assert labels[r"\quad monitoring tap (pilot-bin channel of an excised allocation)"][1] == "2"
    assert labels[r"\quad no policy (unscreened)"][1] == "1"
    assert labels[r"\quad feasible (selected point)"][1] == "1"
    assert labels[r"\quad no feasible point (diagnostic point replayed)"][1] == "2"
    assert labels[r"\quad refused (no evaluated surface)"][1] == "1"
    assert labels[r"\quad no selection record"][1] == "2"
    assert labels[r"\quad claim status diagnostic"][1] == "2"
    assert labels[r"\quad kept channels entering the average"][1] == "2"
    assert labels[r"\quad current-era frames on those channels"][2] == "$3{,}000$"
    assert labels[r"\quad masked fraction $f$, frame-weighted"][2] == "$0.567$"
    assert labels[r"\quad integration-time cost $1/(1-f)$"][2] == "$2.31$"
    assert any(r[0] == r"\emph{Band level at the operating points} (" + cm.BASIS_MIXED + ")" for r in rows)
    assert frag.tex.count(r"\midrule") == 4 and frag.inputs == run.inputs()

    n = _by_key(frag)
    assert n["ch11.matrix.channels"].value == 6 and n["ch11.matrix.class.measurement_bound_floor"].value == 1
    assert n["ch11.matrix.class.unclassified"].value == 1 and n["ch11.matrix.policy.none"].value == 1
    assert n["ch11.matrix.policy.kept_and_masked"].value == 3 and n["ch11.matrix.policy.kept_and_masked_off_era"].value == 1
    assert n["ch11.matrix.policy.excised_interior"].value == 2 and n["ch11.matrix.policy.monitoring_tap"].value == 2
    assert n["ch11.matrix.selection.feasible"].value == 1 and n["ch11.matrix.selection.no_feasible_point"].value == 2
    assert n["ch11.matrix.selection.refused"].value == 1 and n["ch11.matrix.selection.no_selection_record"].value == 2
    assert n["ch11.matrix.selection.diagnostic"].value == 2 and n["ch11.matrix.kept_channels"].value == 2
    assert n["ch11.matrix.kept_frames"].value == 3000 and n["ch11.matrix.masked_fraction"].value == pytest.approx(1700 / 3000)
    assert n["ch11.matrix.time_cost"].value == pytest.approx(3000 / 1300) and n["ch11.matrix.time_cost"].precision == 2
    assert n["ch11.matrix.time_cost"].renderings == ("2.31",) and n["ch11.matrix.masked_fraction"].status == "derived"
    assert n["ch11.matrix.operating_point_basis"].value == cm.BASIS_MIXED and n["ch11.matrix.operating_point_basis"].kind == "text"
    assert n["ch11.matrix.class.off_era"].source == {"table": "conclusions_matrix.tex", "row": {"group": "screening class", "label": sc.OFF_ERA},
                                                     "column": "channels"}
    assert any("ch19 left out of the band level: no masked fraction" in s for s in frag.notes)
    assert any("without a screening class: 40" in s for s in frag.notes)
    assert any("mixed basis" in s for s in frag.notes)
    assert any("band level over kept channels 21, 23" in s for s in frag.notes)


def test_matrix_band_level_edge_cases(tmp_path):
    records = _sections()
    records[23]["sections"]["selection"]["diagnostic_masked_fraction"] = 1.0       # masks every frame: cost undefined
    records[21]["sections"]["era"]["current_frames"] = None                         # no weight: left out
    run = _ledger(tmp_path, records)
    frag = cm.build(run)
    labels = {r[0]: r for r in _rows(frag.tex)}
    assert labels[r"\quad integration-time cost $1/(1-f)$"][2] == core.DASH
    assert labels[r"\quad masked fraction $f$, frame-weighted"][2] == "$1.000$"
    assert labels[r"\quad kept channels entering the average"][1] == "1"
    keys = {n.key for n in frag.numbers}
    assert "ch11.matrix.time_cost" not in keys and "ch11.matrix.masked_fraction" in keys
    assert any("cost undefined" in s for s in frag.notes) and any("ch21 left out of the band level: no current-era frame count" in s for s in frag.notes)
    assert any("no channel has a feasible selected point" in s for s in frag.notes)
    assert any(cm.BASIS_DIAGNOSTIC in r[0] for r in _rows(frag.tex))

    only_wall = {22: _sections()[22]}
    frag = cm.build(_ledger(tmp_path / "wall", only_wall))
    rows = _rows(frag.tex)
    labels = {r[0]: r for r in rows}
    assert labels[r"\quad kept channels entering the average"][1] == "0"
    assert labels[r"\quad current-era frames on those channels"][2] == core.DASH
    assert labels[r"\quad masked fraction $f$, frame-weighted"][2] == core.DASH
    assert labels[r"\quad integration-time cost $1/(1-f)$"][2] == core.DASH
    assert r"\quad no policy (unscreened)" not in labels and r"\quad unclassified (no screening record)" not in labels
    assert r"\quad no selection record" not in labels
    assert any(r[0] == r"\emph{Band level at the operating points}" for r in rows)     # no basis suffix without a kept channel
    assert any("band level undefined" in s for s in frag.notes)
    assert {n.key for n in frag.numbers} == {"ch11.matrix.channels", "ch11.matrix.kept_channels"} | {
        f"ch11.matrix.class.{s}" for s in cm.CLASS_SLUGS.values()} | {
        "ch11.matrix.policy.kept_and_masked", "ch11.matrix.policy.kept_and_masked_off_era", "ch11.matrix.policy.excised_interior",
        "ch11.matrix.policy.monitoring_tap"} | {f"ch11.matrix.selection.{s}" for s in cm.SELECTION_SLUGS.values()} | {
        "ch11.matrix.selection.diagnostic"}


# ------------------------------------------------------------------ (b) the atlas counts
def _head_cells(tex: str) -> list[str]:
    """The header cells of a booktabs tabular."""
    lines = tex.splitlines()
    return [c.strip() for c in lines[lines.index(r"\toprule") + 1][:-2].split(" & ")]


def test_atlas_counts_prints_the_stub_columns_and_no_others(tmp_path):
    """The appendix C stub names six columns; the table prints them beside the channel and nothing more."""
    frag = cm.build_atlas_counts(_ledger(tmp_path))
    assert _head_cells(frag.tex) == ["ch", r"\texttt{freq\_id}", "valid", r"\shortstack{excluded\\(reason)}", "current era",
                                     r"\shortstack{era\\frames}", r"\shortstack{kept at point\\(cal.\ + eval.)}",
                                     r"\shortstack{plate\\digest}"]
    assert frag.tex.splitlines()[0] == r"\begin{tabular}{rrrlcrrl}"     # eight columns, one tabular: no stacked panels
    assert all(len(r) == 8 for r in _rows(frag.tex))
    for dropped in ("frames &", "kept, cal.", "kept, eval."):            # the three columns of the first draft
        assert dropped not in frag.tex
    assert any(s.startswith("the printed columns are the appendix C stub's own and no others") for s in frag.notes)
    assert [b.__name__ for b in cm.BUILDERS] == ["build", "build_atlas_counts", "build_headline"]   # no companion ledger


def test_atlas_counts_columns_and_absent_cases(tmp_path):
    run = _ledger(tmp_path)
    frag = cm.build_atlas_counts(run)
    assert frag.name == "archive_atlas_counts" and frag.label == "tab:archive:atlas-counts" and frag.inputs == run.inputs()
    rows = {int(r[0]): r for r in _rows(frag.tex)}
    assert list(rows) == [19, 21, 22, 23, 24, 40] and all(len(r) == 8 for r in rows.values())
    dag, both = cm.DAGGER, "^{" + cm.MARK_DIAGNOSTIC + cm.MARK_NO_REPLAY + "}"
    stacked = cm.STACK_OPEN + r"$10$ (rail 6,\\weird\_reason 4)" + cm.STACK_CLOSE   # two reasons: one to a line
    assert rows[21] == ["21", "736", "$2{,}090$", stacked, "2019-01--2026-08", "$2{,}000$", "$1{,}100$", "--"]
    assert rows[23] == ["23", "706", "$3{,}000$", "$0$", "2020-02--2026-08", "$1{,}000$", f"$50{dag}$", "--"]
    assert rows[22][3] == "--" and rows[22][6] == f"$35{both}$"          # diagnostic point, never replayed
    assert rows[24][3] == "$2$ (rail 2)" and rows[24][6] == "--"
    assert rows[19] == ["19", "767", "$480$", "$3$ (invalid 20)", "--", "$300$", "--", "--"]
    assert rows[40][4] == "2024-01--2024-02" and rows[40][6] == "--"
    assert cm.render_reasons(f"{RAIL}:6;weird_reason:4") == r"rail 6, weird\_reason 4"    # the one-line rendering the prose may use

    n = _by_key(frag)
    assert n["appC.atlas_counts.freq_id.ch21"].value == 736 and n["appC.atlas_counts.n_frames.ch21"].value == 2100
    assert n["appC.atlas_counts.n_valid.ch19"].value == 480 and n["appC.atlas_counts.health_excluded.ch19"].value == 3
    assert n["appC.atlas_counts.health_reasons.ch21"].value == f"{RAIL}:6;weird_reason:4"
    assert n["appC.atlas_counts.health_reasons.ch21"].renderings == (r"rail 6, weird\_reason 4",)
    assert n["appC.atlas_counts.current_era.ch21"].value == "2019-01..2026-08" and n["appC.atlas_counts.current_era.ch21"].renderings == ("2019-01--2026-08",)
    assert n["appC.atlas_counts.current_frames.ch22"].value == 3500
    assert n["appC.atlas_counts.kept_calibration.ch21"].value == 600 and n["appC.atlas_counts.kept_calibration.ch21"].status == "measured"
    assert n["appC.atlas_counts.kept_evaluation.ch21"].value == 500 and n["appC.atlas_counts.kept_total.ch21"].value == 1100
    assert n["appC.atlas_counts.kept_calibration.ch23"].value == 50 and n["appC.atlas_counts.kept_calibration.ch23"].status == "derived"
    assert n["appC.atlas_counts.kept_evaluation.ch23"].value == 0 and n["appC.atlas_counts.kept_total.ch23"].value == 50
    assert n["appC.atlas_counts.kept_calibration.ch22"].value == 35
    assert "appC.atlas_counts.kept_evaluation.ch22" not in n and "appC.atlas_counts.kept_total.ch22" not in n
    assert not any(k.startswith("appC.atlas_counts.kept_") and k.endswith(("ch24", "ch19", "ch40")) for k in n)
    assert "appC.atlas_counts.health_excluded.ch22" not in n and "appC.atlas_counts.health_reasons.ch23" not in n
    assert "appC.atlas_counts.current_era.ch19" not in n
    printed = {"freq_id", "valid", "excluded", "current era", "era frames", "kept at point"}
    assert {v.source["column"] for v in n.values()} == printed | {cm.NOT_PRINTED}
    for key in ("n_frames.ch21", "kept_calibration.ch21", "kept_evaluation.ch21"):    # the three unprinted columns keep their numbers
        assert n[f"appC.atlas_counts.{key}"].source == {"table": "archive_atlas_counts.tex",
                                                        "row": {"channel": int(key[-2:])}, "column": cm.NOT_PRINTED}
    assert n["appC.atlas_counts.kept_total.ch21"].source["column"] == "kept at point"
    assert any(s.startswith("dagger: no selected (rho*, eta*) on channels 22, 23") for s in frag.notes)
    assert any(s.startswith("double dagger: the kept cell on channel 22 is the calibration block alone") for s in frag.notes)
    assert any("kept at point is the dash on channels 19, 24, 40" in s for s in frag.notes)
    assert any(s.strip().startswith("24: " + NO_FLOOR) for s in frag.notes)
    assert any(s.strip().startswith("19, 40: no selection record") for s in frag.notes)
    assert any("the two blocks are not printed as separate columns" in s for s in frag.notes)
    assert any("replay kept no frame on channel 23" in s for s in frag.notes)
    assert any("no current-era span" in s and "19" in s for s in frag.notes)
    assert any(s.startswith("product.n_frames") and "not printed" in s and "channels 19, 21, 22" in s for s in frag.notes)
    assert any("plate digest is the dash" in s for s in frag.notes)


def test_atlas_without_diagnostic_points_has_no_dagger_note(tmp_path):
    frag = cm.build_atlas_counts(_ledger(tmp_path, {21: _sections()[21]}))
    assert cm.DAGGER not in frag.tex and cm.MARK_NO_REPLAY not in frag.tex
    assert not any(s.startswith(("dagger", "double dagger")) for s in frag.notes)
    assert not any("is the dash on channel" in s for s in frag.notes)
    assert any(s.endswith("differs from the valid count on channel 21") for s in frag.notes)   # singular: one channel


# ------------------------------------------------------------------ (c) the headline
def test_headline_numbers_under_both_prefixes(tmp_path):
    run = _ledger(tmp_path)
    frag = cm.build_headline(run)
    assert frag.name == "headline" and frag.tex.startswith("% headline: numbers only")
    n = _by_key(frag)
    for prefix in ("ch11", "front"):
        h = {k[len(prefix) + 10:]: v for k, v in n.items() if k.startswith(prefix + ".headline.")}
        assert h["channels"].value == 6 and h["class.recovery_candidate"].value == 0 and h["class.measurement_bound_floor"].value == 1
        assert h["class.occupancy_wall_excision_candidate"].value == 2 and h["class.off_era"].value == 1 and h["class.unclassified"].value == 1
        assert h["class.occupancy_wall_excision_candidate_channels"].value == "22, 24" and h["class.off_era_channels"].value == "19"
        assert "class.recovery_candidate_channels" not in h and h["class.unclassified_channels"].value == "40"
        assert h["measurement_bound"].value == 2 and h["kept_and_masked"].value == 3
        assert (h["selection_feasible"].value, h["selection_no_feasible_point"].value, h["selection_refused"].value) == (1, 2, 1)
        assert h["selection_no_selection_record"].value == 2 and h["selection_refused_channels"].value == "24"
        assert h["selection_diagnostic"].value == 2
        assert (h["floor_measured"].value, h["floor_stated"].value, h["floor_refused"].value) == (1, 1, 2)
        assert h["floor_measured_channels"].value == "21" and h["floor_measured_channels"].kind == "text"
        assert h["floor_stated_channels"].value == "23" and h["floor_refused_channels"].value == "22, 24"
        assert h["floor_stated_bulk_left_side_not_h0"].value == 1 and "floor_stated_kept_half_about_mu_0" not in h
        assert (h["tau_measured"].value, h["tau_bounded"].value, h["tau_refused"].value, h["tau_unmeasured"].value) == (1, 1, 2, 2)
        assert h["tau_measured_channels"].value == "22" and h["tau_bounded_channels"].value == "21"
        assert h["kstar_e_min"].value == 0.9 and h["kstar_k_star"].value == 128 and h["kstar_failing_k"].value == 256
        assert h["kstar_binding_channel"].value == 23 and h["kstar_binding_e"].value == pytest.approx(0.7929) and h["kstar_sentinels"].value == "33"
        assert h["within_10x_tolerance"].value == 2 and h["within_10x_tolerance_channels"].value == "21, 23"
        assert h["min_R"].value == 0.8 and h["min_R"].renderings == ("0.800",) and h["min_R_channel"].value == 21
        assert h["coarse_frontier_channels"].value == 2 and h["coarse_min_R"].value == 0.7 and h["coarse_min_R_channel"].value == 21
        assert h["coarse_min_R_masked_fraction"].value == 0.3 and h["coarse_min_R"].renderings == ("0.700",)
        assert h["coarse_centre_within_0p1_db"].value == 1 and h["coarse_centre_channels"].value == 4
        assert h["coarse_centre_within_0p1_db_fraction"].value == pytest.approx(0.25)
        assert h["coarse_core_width_factor_min"].value == 1.5 and h["coarse_core_width_factor_max"].value == 15000.0
        assert h["fine_core_width_factor_min"].value == 1.2 and h["fine_core_width_factor_max"].value == 41.5
        assert h["coarse_core_width_factor_max"].renderings == ("15000",) and h["coarse_core_width_factor_max"].precision == 0
        assert h["kept_channels"].value == 2 and h["kept_frames"].value == 3000
        assert h["masked_fraction"].value == pytest.approx(1700 / 3000) and h["time_cost"].value == pytest.approx(3000 / 1300)
        assert h["operating_point_basis"].value == cm.BASIS_MIXED
    assert len([k for k in n if k.startswith("ch11.")]) == len([k for k in n if k.startswith("front.")])
    assert any("ch40: floor evidence 'odd' counted nowhere" in s for s in frag.notes)
    assert any("ch19: floor evidence None counted nowhere" in s for s in frag.notes)
    assert any("stated floors from 'bulk left side (not H0)': 23" in s for s in frag.notes)
    assert any("tau_c refused on 23, 24" in s for s in frag.notes)
    assert any("selection status 'no selection record' on 19, 40" in s for s in frag.notes)
    assert frag.inputs[-1] == tmp_path / "tables" / "kstar.csv" and len(frag.inputs) == 8


def test_headline_without_kstar_surface_or_nulls(tmp_path):
    frag = cm.build_headline(_ledger(tmp_path, kstar=False))
    assert not any(k.startswith("ch11.headline.kstar") for k in _by_key(frag)) and any("kstar.csv absent" in s for s in frag.notes)
    assert frag.inputs == core.load_run(tmp_path).inputs()
    frag = cm.build_headline(_ledger(tmp_path / "e95", e_min=0.95))
    assert any("no row at E_min 0.95" in s for s in frag.notes)
    only = {19: _sections()[19]}
    frag = cm.build_headline(_ledger(tmp_path / "off", only))
    n = _by_key(frag)
    assert "ch11.headline.min_R" not in n and n["ch11.headline.within_10x_tolerance"].value == 0
    assert "ch11.headline.coarse_min_R" not in n and n["ch11.headline.coarse_frontier_channels"].value == 0
    assert "ch11.headline.coarse_centre_within_0p1_db_fraction" not in n and n["ch11.headline.coarse_centre_channels"].value == 0
    assert "ch11.headline.coarse_core_width_factor_min" not in n and "ch11.headline.kept_frames" not in n
    assert any("min_R undefined" in s for s in frag.notes) and any("coarse_min_R undefined" in s for s in frag.notes)
    assert any("centred fraction is undefined" in s for s in frag.notes) and any("band level undefined" in s for s in frag.notes)
    assert any("null.fine_core_width_factor: its range is undefined" in s for s in frag.notes)


def test_write_report_with_all_three_builders(tmp_path):
    run = _ledger(tmp_path)
    manifest = core.write_report(run, tmp_path / "out", list(cm.BUILDERS), commit="d" * 40, generated="2026-09-07T01:00:00+00:00")
    names = [a["name"] for a in manifest["artifacts"]]
    assert names == ["conclusions_matrix", "archive_atlas_counts", "headline"]
    for a in manifest["artifacts"]:
        doc = json.loads((tmp_path / "out" / a["numbers"]).read_text())
        keys = [x["key"] for x in doc["numbers"]]
        assert len(keys) == len(set(keys)) == a["count"]
        assert all(v["value"] is None or not (isinstance(v["value"], float) and math.isnan(v["value"])) for v in doc["numbers"])
    assert (tmp_path / "out" / "tables" / "headline.tex").read_text().startswith("% headline")


# ------------------------------------------------------------------ the real run
@pytest.mark.skipif(not (REAL_RESULTS / "ledger" / "run.json").is_file(), reason="archive results directory absent")
def test_real_run_renders_23_channels(tmp_path):
    run = core.load_run(REAL_RESULTS)
    manifest = core.write_report(run, tmp_path, list(cm.BUILDERS), commit=run.commit, generated="2026-09-07T09:00:00+00:00")
    atlas = (tmp_path / "tables" / "archive_atlas_counts.tex").read_text()
    rows = _rows(atlas)
    assert len(rows) == 23 and [int(r[0]) for r in rows] == list(range(14, 37)) and all(len(r) == 8 for r in rows)
    assert len(_head_cells(atlas)) == 8 and atlas.count(r"\begin{tabular}{") == 1     # the stub's columns, one panel
    refused = {c.channel for c in run.channels if cm.selection_status(c) == "refused"}
    assert refused == {15, 28, 30, 36}
    assert {int(r[0]) for r in rows if r[6] == core.DASH} == refused
    for r in rows:
        if int(r[0]) not in refused:
            assert r[6].startswith("$") and r[6].endswith(("$", "}$"))
    atlas_numbers = json.loads((tmp_path / "numbers" / "archive_atlas_counts.numbers.json").read_text())["numbers"]
    atlas_keys = {x["key"] for x in atlas_numbers}
    assert len(atlas_numbers) == len(atlas_keys) == 217          # the key set the number gate verifies: the trim removed none of it
    for stem in ("n_frames", "n_valid", "kept_calibration", "kept_evaluation", "kept_total"):
        assert any(k.startswith(f"appC.atlas_counts.{stem}.ch") for k in atlas_keys)
    assert {k for k in atlas_keys if ".n_frames." in k} == {f"appC.atlas_counts.n_frames.ch{c}" for c in range(14, 37)}
    for a in manifest["artifacts"]:
        doc = json.loads((tmp_path / a["numbers"]).read_text())
        keys = [x["key"] for x in doc["numbers"]]
        assert len(keys) == len(set(keys)) == a["count"] > 0
    matrix = {n["key"]: n["value"] for n in json.loads((tmp_path / "numbers" / "conclusions_matrix.numbers.json").read_text())["numbers"]}
    assert matrix["ch11.matrix.channels"] == 23
    assert sum(matrix[f"ch11.matrix.class.{s}"] for s in cm.CLASS_SLUGS.values()) == 23
    assert matrix["ch11.matrix.policy.kept_and_masked"] + matrix["ch11.matrix.policy.excised_interior"] == 23
    assert matrix["ch11.matrix.policy.monitoring_tap"] == matrix["ch11.matrix.policy.excised_interior"]
    assert sum(v for k, v in matrix.items() if k.startswith("ch11.matrix.selection.") and not k.endswith(".diagnostic")) == 23
    assert matrix["ch11.matrix.kept_channels"] == matrix["ch11.matrix.policy.kept_and_masked"] - len(refused & {
        c.channel for c in run.channels if cm.policy_of(cm.class_of(c)) == cm.POLICY_KEPT})
    headline = {n["key"]: n["value"] for n in json.loads((tmp_path / "numbers" / "headline.numbers.json").read_text())["numbers"]}
    assert headline["ch11.headline.channels"] == 23 == headline["front.headline.channels"]
    assert headline["ch11.headline.floor_measured"] + headline["ch11.headline.floor_stated"] + headline["ch11.headline.floor_refused"] == 23
    assert headline["ch11.headline.tau_measured"] + headline["ch11.headline.tau_bounded"] + headline["ch11.headline.tau_refused"] \
        + headline["ch11.headline.tau_unmeasured"] == 23
    assert headline["ch11.headline.kstar_k_star"] > 0 and headline["ch11.headline.min_R_channel"] in range(14, 37)
    assert headline["ch11.headline.coarse_min_R_channel"] in range(14, 37)
