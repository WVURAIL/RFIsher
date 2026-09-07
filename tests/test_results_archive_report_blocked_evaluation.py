"""The ch05 blocked-evaluation fragment: every column on a synthetic ledger, then the real run."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

import pytest

from rfisher_results.archive import numbers as nb
from rfisher_results.archive.report import blocked_evaluation as be
from rfisher_results.archive.report import core

REAL_RUN = Path(os.environ.get("RFISHER_ARCHIVE_RESULTS", "/home/djg/rail/results/archive_v5_2026-09-07"))
_STABILITY = "within-era stability refused_insufficient_support: candidate rho=1, eta=1.07129 retains fewer than 30 frames in one era half"
_NO_FLOOR = "no floor for frames without a shelf estimate"
BULK_SOURCE = "bulk of the mixture (declared)"
OFF_SOURCE = "verified transmitter-off era"


def _blocks(cal_first, cal_last, cal_frames, eval_first, eval_last, eval_frames, *, untimed=0, fin=(1.0, 1.0), flag=None,
            status="supported", detail=""):
    flag = fin if flag is None else flag
    return {"status": status, "detail": detail, "calibration_frames": cal_frames, "evaluation_frames": eval_frames,
            "calibration_first_month": cal_first, "calibration_last_month": cal_last,
            "evaluation_first_month": eval_first, "evaluation_last_month": eval_last, "frames_without_time_excluded": untimed,
            "calibration_finite_estimate_rate": fin[0], "evaluation_finite_estimate_rate": fin[1],
            "calibration_flag_rate": flag[0], "evaluation_flag_rate": flag[1]}


def _null(source, centre, width, frames, *, basis="bulk left side (not H0)", null_like=None):
    return {"null_source": source, "mixture_declared": source == BULK_SOURCE, "coarse_centre": centre,
            "coarse_core_width_factor": width, "coarse_frames": frames, "floor_basis": basis, "off_null_like": null_like}


def _replay(mf, q16, q84, kept, blocks, *, status="no feasible point", claim="diagnostic", refusal=_STABILITY, fa=None):
    return {"status": status, "claim_status": claim, "refusal": refusal, "rho": None, "eta": None,
            "diagnostic_basis": "least residual on the calibration surface (no feasible point)", "diagnostic_rho": 1,
            "diagnostic_eta": 1.0743255615234375, "masked_fraction_evaluation": mf, "masked_fraction_evaluation_q16": q16,
            "masked_fraction_evaluation_q84": q84, "kept_evaluation": kept, "bootstrap_blocks_evaluation": blocks,
            "false_alarm_rate": fa}


def _record(ch, fid, sections):
    return {"channel": ch, "freq_id": fid, "product": f"{fid}.npz", "product_sha256": f"{ch:02x}" * 32, "notes": [],
            "sections": sections}


def _ledger(tmp_path: Path) -> Path:
    ledger = tmp_path / "ledger"
    (ledger / "channels").mkdir(parents=True)
    records = [
        # ch14: supported split, the bulk read as a null on both blocks, a diagnostic replay with its bootstrap interval
        _record(14, 844, {
            "blocks": _blocks("2018-12", "2024-10", 18081, "2024-10", "2026-08", 18081, untimed=101, fin=(0.93142, 0.96648)),
            "null": _null(BULK_SOURCE, 1.0, 2.0, 18081),
            "null_evaluation": _null(BULK_SOURCE, 10 ** 0.1, 5.0, 18081),
            "selection": _replay(0.15, 0.12, 0.18, 15000, 40)}),
        # ch19: the off population is each block's own frames (null-like on both), replayed on the off era
        _record(19, 767, {
            "blocks": _blocks("2024-12", "2025-10", 6453, "2025-11", "2026-04", 6447, fin=(0.8528, 0.8787)),
            "null": _null(OFF_SOURCE, 1.00549, 2.0965, 6453, basis="off era p90", null_like=True),
            "null_evaluation": _null(OFF_SOURCE, 1.00531, 1.9255, 6447, basis="off era p90", null_like=True),
            "selection": _replay(0.81, 0.80, 0.82, 1223, 1193, fa=0.81)}),
        # ch20: split without support, the calibration off population not null-like, a replay without an interval,
        # a flag rate that differs from the finite-estimate rate
        _record(20, 752, {
            "blocks": _blocks("2023-09", "2025-07", 10581, "2025-07", "2026-06", 10568, fin=(0.997, 0.997), flag=(0.990, 0.995),
                              status="insufficient_support",
                              detail="calibration block has 0 populated months, evaluation block 6; the era procedure needs 1 in each"),
            "null": _null(OFF_SOURCE + " (not null-like)", 1.10027, 17.625, 10581, basis="off era p90", null_like=False),
            "null_evaluation": _null(OFF_SOURCE, 1.12336, 16.949, 10568, basis="off era p90", null_like=True),
            "selection": _replay(0.98684, None, None, 139, 0, fa=0.98684)}),
        # ch30: no blocks section, a non-positive calibration centre without a width and no null population,
        # no null_evaluation, the selector refused (no replay)
        _record(30, 598, {
            "blocks": None,
            "null": _null(BULK_SOURCE, 0.0, None, 4592, basis="none"),
            "null_evaluation": None,
            "selection": _replay(None, None, None, 0, 0, status="refused", claim="", refusal=_NO_FLOOR)}),
        # ch35: the calibration null is the archive's off population outside the block, the evaluation block carries
        # no null population; the replay kept no frame
        _record(35, 521, {
            "era": {"off_through": "2021-10", "off_era_current": False},
            "blocks": _blocks("2025-11", "2026-03", 6152, "2026-04", "2026-08", 6136),
            "null": _null(OFF_SOURCE, 0.99929, 1.5516, 11199, basis="off era p90", null_like=True),
            "null_evaluation": _null(BULK_SOURCE, 13.48916, 1551.479, 6136, basis="none"),
            "selection": _replay(1.0, 1.0, 1.0, 0, 722)}),
        # ch36: an absent calibration centre with a width, so the drift is undefined; no selection section
        _record(36, 506, {
            "blocks": _blocks("2021-08", "2025-07", 14476, "2025-07", "2026-08", 14469, fin=(0.999, 0.999)),
            "null": _null(BULK_SOURCE, None, 2.0, 14476),
            "null_evaluation": _null(BULK_SOURCE, 1.0, 2.0, 14469),
            "selection": None}),
    ]
    rels = []
    for rec in records:
        rel = f"channels/ch{rec['channel']:02d}_fid{rec['freq_id']}.json"
        (ledger / rel).write_text(json.dumps(rec))
        rels.append(rel)
    run = {"schema": {"name": "rfisher-archive-ledger", "version": 1}, "generated": "2026-09-07T00:00:00+00:00",
           "producer": {"commit": "a" * 40}, "products": {}, "channels": rels, "era_config_digest": "e" * 64}
    (ledger / "run.json").write_text(json.dumps(run))
    return tmp_path


def _body_rows(tex: str) -> list[list[str]]:
    lines = tex.splitlines()
    body = lines[lines.index(r"\midrule") + 1: lines.index(r"\bottomrule")]
    return [[c.strip() for c in line[: -len(r" \\")].split(" & ")] for line in body]


def test_derived_quantities():
    assert be.drift_db(1.0, 10.0) == pytest.approx(10.0) and be.drift_db(2.0, 1.0) == pytest.approx(-10 * math.log10(2))
    assert math.isnan(be.drift_db(None, 1.0)) and math.isnan(be.drift_db(0.0, 1.0)) and math.isnan(be.drift_db(1.0, float("nan")))
    assert be.width_ratio(2.0, 5.0) == 2.5 and math.isnan(be.width_ratio(0.0, 1.0)) and math.isnan(be.width_ratio(None, 1.0))


def test_null_population_reads_source_check_and_basis():
    assert be.null_population({}) == "" and be.null_population(None) == ""
    assert be.null_population({"null_source": BULK_SOURCE, "floor_basis": "kept half about mu_0"}) == be.BULK
    assert be.null_population({"null_source": BULK_SOURCE, "floor_basis": "none"}) == be.BULK_NO_NULL
    assert be.null_population({"null_source": OFF_SOURCE, "off_null_like": True, "floor_basis": "off era p90"}) == be.OFF
    assert be.null_population({"null_source": OFF_SOURCE, "off_null_like": False}) == be.OFF_NOT_NULL_LIKE
    assert be.null_population({"null_source": OFF_SOURCE + " (not null-like)", "off_null_like": None}) == be.OFF_NOT_NULL_LIKE
    assert be.MARKS[be.BULK] == "" and all(be.MARKS[k].startswith("^{") for k in (be.BULK_NO_NULL, be.OFF, be.OFF_NOT_NULL_LIKE))


def test_group_header_spans_match_columns():
    head = be.group_header(be.GROUPS)
    assert sum(span for _, span in be.GROUPS) == len(be.HEADER) == len(be.ALIGN) == 18
    assert r"\multicolumn{2}{c}{calibration block}" in head and r"\cmidrule(lr){2-3}" in head and r"\cmidrule(lr){6-6}" in head
    assert r"\multicolumn{2}{c}{diagnostic replay (eval.)}" in head and r"\cmidrule(lr){17-18}" in head
    assert head.count(r"\multicolumn") == len([g for g in be.GROUPS if g[0]]) and head.count("&") == len(be.GROUPS) - 1


def test_every_column_on_the_synthetic_ledger(tmp_path):
    run = core.load_run(_ledger(tmp_path))
    frag = be.build(run)
    assert frag.name == "blocked_evaluation" and frag.label == "tab:estimator:blocked"
    assert frag.tex.startswith(r"\begin{tabular}{" + be.ALIGN + "}")
    rows = _body_rows(frag.tex)
    assert [r[0] for r in rows] == ["14", "19", r"20$^{\ddagger}$", "30", "35", "36"] and all(len(r) == len(be.HEADER) for r in rows)
    by = {r[0].split("$")[0]: r for r in rows}

    # ch14: every cell printed, the drift derived, the interval and kept frames of the replay
    assert by["14"] == ["14", "2018-12--2024-10", "$18{,}081$", "2024-10--2026-08", "$18{,}081$", "$101$",
                        "$1.000$", "$2.00$", "$1.259$", "$5.00$", "$+1.000$", "$2.50$",
                        "$0.931$", "$0.966$", "$0.931$", "$0.966$", "$0.1200$--$0.1800$", "$15{,}000$"]
    # ch19: the off population marked on both centres, and the drift is a between-block measurement
    assert by["19"][5] == "$0$" and by["19"][6] == r"$1.005^{\mathrm{off}}$" and by["19"][8] == r"$1.005^{\mathrm{off}}$"
    assert by["19"][7] == "$2.10$" and by["19"][9] == "$1.93$" and by["19"][10] == "$-0.001$" and by["19"][11] == "$0.92$"
    assert by["19"][12:16] == ["$0.853$", "$0.879$", "$0.853$", "$0.879$"] and by["19"][16:] == ["$0.8000$--$0.8200$", "$1{,}223$"]
    # ch20: the split mark, the not-null-like mark on the calibration centre, a replay value without an interval
    assert by["20"][6] == r"$1.100^{\mathrm{off}\ast}$" and by["20"][8] == r"$1.123^{\mathrm{off}}$"
    assert by["20"][12:16] == ["$0.997$", "$0.997$", "$0.990$", "$0.995$"]
    assert by["20"][16] == "$0.9868$ [--]" and by["20"][17] == "$139$"
    # ch30: no blocks, the no-null mark on a zero centre without a width, no evaluation null, refused: no replay
    assert by["30"][1:6] == [core.DASH] * 5 and by["30"][6] == r"$0^{\ast}$" and by["30"][7:] == [core.DASH] * 11
    # ch35: the calibration null outside the block (off) against an evaluation bulk with no null population: no drift;
    # the replay kept no frame
    assert by["35"][6] == r"$0.9993^{\mathrm{off}}$" and by["35"][7] == "$1.55$" and by["35"][8] == r"$13.49^{\ast}$" and by["35"][9] == "$1{,}551$"
    assert by["35"][10:12] == [core.DASH, core.DASH] and by["35"][16:] == ["$1.0000$--$1.0000$", "$0$"]
    # ch36: an absent centre leaves the centre drift undefined (the width ratio stands); no selection section
    assert by["36"][6] == core.DASH and by["36"][7] == "$2.00$" and by["36"][8:10] == ["$1.000$", "$2.00$"]
    assert by["36"][10:12] == [core.DASH, "$1.00$"] and by["36"][16:] == [core.DASH, core.DASH]

    keys = [n.key for n in frag.numbers]
    assert len(keys) == len(set(keys)) and all(k.startswith("ch05.blocked_evaluation.") for k in keys)
    by_key = {n.key: n for n in frag.numbers}
    k = "ch05.blocked_evaluation."
    assert by_key[k + "calibration_first_month.ch14"].value == "2018-12" and by_key[k + "evaluation_last_month.ch14"].renderings == ("2026-08",)
    assert by_key[k + "calibration_frames.ch14"].value == 18081 and by_key[k + "calibration_frames.ch14"].kind == "int"
    assert by_key[k + "frames_without_time_excluded.ch14"].value == 101 and by_key[k + "frames_without_time_excluded.ch19"].value == 0
    assert by_key[k + "split_status.ch20"].value == "insufficient_support"
    assert by_key[k + "split_status.ch20"].renderings == ("insufficient", "insufficient_support")
    assert k + "split_status.ch14" not in by_key and k + "split_status.ch30" not in by_key
    assert by_key[k + "calibration_centre.ch14"].precision == 3 and by_key[k + "evaluation_centre.ch14"].value == pytest.approx(10 ** 0.1)
    assert by_key[k + "calibration_null_source.ch14"].renderings == (be.BULK,)
    assert by_key[k + "calibration_null_source.ch20"].value == OFF_SOURCE + " (not null-like)"
    assert by_key[k + "calibration_null_source.ch20"].renderings == (be.OFF_NOT_NULL_LIKE, be.MARKS[be.OFF_NOT_NULL_LIKE])
    assert by_key[k + "evaluation_null_source.ch35"].renderings == (be.BULK_NO_NULL, r"^{\ast}")
    assert by_key[k + "centre_drift_db.ch14"].value == pytest.approx(1.0) and by_key[k + "centre_drift_db.ch14"].status == "derived"
    assert by_key[k + "width_factor_ratio.ch14"].value == 2.5 and by_key[k + "centre_drift_db.ch19"].value == pytest.approx(10 * math.log10(1.00531 / 1.00549))
    assert by_key[k + "calibration_finite_estimate_rate.ch14"].value == pytest.approx(0.93142)
    assert by_key[k + "evaluation_flag_rate.ch20"].value == pytest.approx(0.995)
    assert by_key[k + "masked_fraction_evaluation.ch14"].value == 0.15 and by_key[k + "masked_fraction_evaluation.ch14"].precision == 4
    assert by_key[k + "masked_fraction_evaluation_q16.ch14"].value == 0.12 and by_key[k + "masked_fraction_evaluation_q84.ch14"].value == 0.18
    assert by_key[k + "masked_fraction_evaluation_q16.ch14"].renderings == ("0.1200--0.1800",)
    assert by_key[k + "evaluation_width_factor.ch35"].precision == 0 and by_key[k + "evaluation_width_factor.ch35"].value == pytest.approx(1551.479)
    assert by_key[k + "kept_evaluation.ch14"].value == 15000 and by_key[k + "kept_evaluation.ch35"].value == 0
    assert by_key[k + "masked_fraction_evaluation.ch20"].value == pytest.approx(0.98684) and k + "masked_fraction_evaluation_q16.ch20" not in by_key
    for absent in ("calibration_frames.ch30", "frames_without_time_excluded.ch30", "calibration_width_factor.ch30",
                   "evaluation_centre.ch30", "centre_drift_db.ch30", "centre_drift_db.ch35", "width_factor_ratio.ch35",
                   "centre_drift_db.ch36", "calibration_centre.ch36", "masked_fraction_evaluation.ch30",
                   "masked_fraction_evaluation.ch36", "kept_evaluation.ch30", "kept_evaluation.ch36"):
        assert k + absent not in by_key, absent
    assert by_key[k + "calibration_centre.ch30"].value == 0.0
    assert all(n.source["table"] == "blocked_evaluation.tex" for n in frag.numbers)
    assert all(n.source["row"] == {"channel": int(n.key.rsplit(".ch", 1)[1])} for n in frag.numbers if ".ch" in n.key)
    counts = {key.rsplit(".", 1)[1]: n.value for key, n in by_key.items() if ".ch" not in key}
    assert counts == {"n_channels": 6, "n_split_supported": 4, "n_channels_off_population": 3, "n_channels_no_null_population": 2,
                      "n_channels_drift_defined": 3, "n_channels_replayed": 4, "n_channels_no_replay": 2,
                      "frames_without_time_excluded_total": 101}

    notes = "\n".join(frag.notes)
    assert "blocks section absent on ch 30" in notes
    assert "ddagger: split not supported on ch20 insufficient_support: calibration block has 0 populated months" in notes
    assert "untimed: 101 frames without a recorded time excluded from both blocks on 1 of 6 channels" in notes and "ch14 101" in notes
    assert "null_evaluation absent on ch 30" in notes
    assert "off: the coarse null is the verified transmitter-off population of the block's frames (null.null_source) on ch 19, 20; on ch 35 (calibration block only)" in notes
    assert "off*: on ch 20 the off population fails the null-like check" in notes
    assert "*: the ledger records no null population for the block" in notes and "on ch30 (cal), ch35 (eval)" in notes
    assert "drift dashed on ch 35" in notes and "ch35 calibration null 11199 frames against 6152 in the block (the archive's verified off population, off through 2021-10)" in notes
    assert "centre drift undefined (absent or non-positive centre) on ch 36" in notes
    assert "printed on 3 of 6 channels" in notes
    assert "the finite-estimate rate differs from the survey flag rate on ch 20" in notes
    assert "a diagnostic, not a selected operating point: no channel has one (selection.status no feasible point: 4, refused: 1" in notes
    assert "replay cells dashed on ch 30, 36" in notes and "no floor for frames without a shelf estimate (1)" in notes and "absent (1)" in notes
    assert "replay on ch 20 has no bootstrap interval" in notes
    assert "the replay kept no frame on ch 35" in notes
    assert "selector refusals (selection.refusal): within-era stability refused_insufficient_support (4); no floor for frames without a shelf estimate (1)" in notes
    assert len(frag.inputs) == 7


def test_rates_note_when_they_coincide(tmp_path):
    run = core.load_run(_ledger(tmp_path))
    frag = be.build(run)
    assert any("differs from the survey flag rate on ch 20" in n for n in frag.notes)
    # every channel's flag rate equal to its finite-estimate rate: the note says so
    for c in run.channels:
        if c.has("blocks"):
            b = dict(c.blocks)
            b["calibration_flag_rate"], b["evaluation_flag_rate"] = b["calibration_finite_estimate_rate"], b["evaluation_finite_estimate_rate"]
            c.sections["blocks"] = b
    frag = be.build(run)
    assert any(n.startswith("the finite-estimate rate equals the survey flag rate on every channel (5)") for n in frag.notes)


def test_write_report_round_trip(tmp_path):
    run = core.load_run(_ledger(tmp_path))
    manifest = core.write_report(run, tmp_path / "out", [be.build], commit="f" * 40, generated="2026-09-07T01:00:00+00:00")
    art = manifest["artifacts"][0]
    assert art["name"] == "blocked_evaluation" and art["label"] == "tab:estimator:blocked" and art["count"] == len(be.build(run).numbers)
    loaded = nb.load_numbers([tmp_path / "out" / "numbers" / "blocked_evaluation.numbers.json"])
    assert len(loaded) == art["count"] and len({n.key for n in loaded}) == art["count"]
    assert (tmp_path / "out" / "tables" / "blocked_evaluation.tex").read_text() == be.build(run).tex
    assert art["notes"] == be.build(run).notes


@pytest.mark.skipif(not (REAL_RUN / "ledger" / "run.json").is_file(), reason="archive results not present")
def test_real_run_renders_23_channels(tmp_path):
    run = core.load_run(REAL_RUN)
    frag = be.build(run)
    rows = _body_rows(frag.tex)
    assert len(rows) == 23 and [int(r[0]) for r in rows] == list(range(14, 37))
    assert all(len(r) == len(be.HEADER) for r in rows)
    core.write_report(run, tmp_path / "out", [be.build], commit=run.commit, generated="2026-09-07T09:00:00+00:00")
    doc = json.loads((tmp_path / "out" / "numbers" / "blocked_evaluation.numbers.json").read_text())
    keys = [n["key"] for n in doc["numbers"]]
    assert len(keys) == len(set(keys)) and keys and all(k.startswith("ch05.blocked_evaluation.") for k in keys)
    assert frag.notes
    # no channel has a selected point: every replay printed is the diagnostic one, none of the numbers a selection
    assert all(c.selection.get("rho") is None for c in run.channels)
    assert any("a diagnostic, not a selected operating point: no channel has one" in n for n in frag.notes)
