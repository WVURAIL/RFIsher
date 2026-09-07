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


# the chapter table prints exactly the ch05 stub's columns (plus the channel); the block spans, frame counts,
# untimed frames, flag rates and kept frames are the companion's
CHAPTER_ROWS = {
    "14": ["14", "$1.000$", "$2.00$", "$1.259$", "$5.00$", "$+1.000$", "$2.50$", "$0.931$", "$0.966$",
           "$0.1200$--$0.1800$"],
    "19": ["19", r"$1.005^{\mathrm{off}}$", "$2.10$", r"$1.005^{\mathrm{off}}$", "$1.93$", "$-0.001$", "$0.92$",
           "$0.853$", "$0.879$", "$0.8000$--$0.8200$"],
    "20": [r"20$^{\ddagger}$", r"$1.100^{\mathrm{off}\ast}$", "$17.6$", r"$1.123^{\mathrm{off}}$", "$16.9$",
           "$+0.090$", "$0.96$", "$0.997$", "$0.997$", "$0.9868$ [--]"],
    "30": ["30", r"$0^{\ast}$", "--", "--", "--", "--", "--", "--", "--", "--"],
    "35": ["35", r"$0.9993^{\mathrm{off}}$", "$1.55$", r"$13.49^{\ast}$", "$1{,}551$", "--", "--", "$1.000$",
           "$1.000$", "$1.0000$--$1.0000$"],
    "36": ["36", "--", "$2.00$", "$1.000$", "$2.00$", "--", "$1.00$", "$0.999$", "$0.999$", "--"],
}
LEDGER_ROWS = {
    "14": ["14", "2018-12--2024-10", "$18{,}081$", "2024-10--2026-08", "$18{,}081$", "$101$", "$0.931$", "$0.966$",
           "$15{,}000$"],
    "19": ["19", "2024-12--2025-10", "$6{,}453$", "2025-11--2026-04", "$6{,}447$", "$0$", "$0.853$", "$0.879$",
           "$1{,}223$"],
    "20": [r"20$^{\ddagger}$", "2023-09--2025-07", "$10{,}581$", "2025-07--2026-06", "$10{,}568$", "$0$", "$0.990$",
           "$0.995$", "$139$"],
    "30": ["30"] + ["--"] * 8,
    "35": ["35", "2025-11--2026-03", "$6{,}152$", "2026-04--2026-08", "$6{,}136$", "$0$", "$1.000$", "$1.000$", "$0$"],
    "36": ["36", "2021-08--2025-07", "$14{,}476$", "2025-07--2026-08", "$14{,}469$", "$0$", "$0.999$", "$0.999$", "--"],
}
# every per-channel number key either table emits, and which fragment now carries it
CHAPTER_COLUMNS = {"split_status", "calibration_centre", "calibration_width_factor", "calibration_null_source",
                   "evaluation_centre", "evaluation_width_factor", "evaluation_null_source", "centre_drift_db",
                   "width_factor_ratio", "calibration_finite_estimate_rate", "evaluation_finite_estimate_rate",
                   "masked_fraction_evaluation", "masked_fraction_evaluation_q16", "masked_fraction_evaluation_q84"}
LEDGER_COLUMNS = {"calibration_first_month", "calibration_last_month", "calibration_frames", "evaluation_first_month",
                  "evaluation_last_month", "evaluation_frames", "frames_without_time_excluded",
                  "calibration_flag_rate", "evaluation_flag_rate", "kept_evaluation"}
BAND_COUNTS = {"n_channels": 6, "n_split_supported": 4, "n_channels_off_population": 3,
               "n_channels_no_null_population": 2, "n_channels_drift_defined": 3, "n_channels_replayed": 4,
               "n_channels_no_replay": 2, "frames_without_time_excluded_total": 101}


def _columns(numbers) -> set[str]:
    """The column part of each key: ``ch05.blocked_evaluation.<column>[.chNN]``."""
    return {n.key.removeprefix("ch05.blocked_evaluation.").rsplit(".ch", 1)[0] for n in numbers}


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


def test_chapter_columns_are_the_stub_columns_and_the_companion_takes_the_rest():
    # the stub names, per channel: both blocks' null centre and width, the drift, the finite-estimate rate,
    # the block-bootstrap interval. Ten columns with the channel, nine on the companion, both a single tabular.
    assert be.HEADER == ["ch", "centre", "width", "centre", "width", "centre [dB]", "width ratio", "cal.", "eval.",
                         r"$f$ q16--q84"]
    assert len(be.HEADER) == len(be.ALIGN) == 10 and sum(span for _, span in be.GROUPS) == 10
    assert [title for title, _ in be.GROUPS] == ["", r"calibration null $F/\mu_0$", "evaluation null", "drift",
                                                 "finite-estimate rate", "diagnostic replay"]
    assert be.LEDGER_HEADER == ["ch", "months", "frames", "months", "frames", "untimed", "cal.", "eval.", "kept"]
    assert len(be.LEDGER_HEADER) == len(be.LEDGER_ALIGN) == 9 and sum(span for _, span in be.LEDGER_GROUPS) == 9
    assert [title for title, _ in be.LEDGER_GROUPS] == ["", "calibration block", "evaluation block", "excluded",
                                                        "flag rate", "replay"]
    assert be.LEDGER_NAME == "blocked_evaluation_ledger" and be.LEDGER_LABEL == "tab:archive:blocked_evaluation"
    # the registry picks both builders up
    assert be.BUILDERS == (be.build, be.build_ledger)


def test_group_header_spans_match_columns():
    head = be.group_header(be.GROUPS)
    assert r"\multicolumn{2}{c}{calibration null $F/\mu_0$}" in head and r"\cmidrule(lr){2-3}" in head
    assert r"\multicolumn{2}{c}{finite-estimate rate}" in head and r"\cmidrule(lr){8-9}" in head
    assert r"\multicolumn{1}{c}{diagnostic replay}" in head and r"\cmidrule(lr){10-10}" in head
    assert head.count(r"\multicolumn") == len([g for g in be.GROUPS if g[0]]) and head.count("&") == len(be.GROUPS) - 1

    ledger_head = be.group_header(be.LEDGER_GROUPS)
    assert r"\multicolumn{2}{c}{calibration block}" in ledger_head and r"\cmidrule(lr){2-3}" in ledger_head
    assert r"\multicolumn{1}{c}{excluded}" in ledger_head and r"\cmidrule(lr){6-6}" in ledger_head
    assert r"\multicolumn{1}{c}{replay}" in ledger_head and r"\cmidrule(lr){9-9}" in ledger_head
    assert ledger_head.count("&") == len(be.LEDGER_GROUPS) - 1


def test_every_chapter_column_on_the_synthetic_ledger(tmp_path):
    run = core.load_run(_ledger(tmp_path))
    frag = be.build(run)
    assert frag.name == "blocked_evaluation" and frag.label == "tab:estimator:blocked"
    assert frag.tex.startswith(r"\begin{tabular}{" + be.ALIGN + "}")
    assert frag.tex.count(r"\begin{tabular}") == 1        # one tabular: no panel split needed at this width
    rows = _body_rows(frag.tex)
    assert [r[0] for r in rows] == ["14", "19", r"20$^{\ddagger}$", "30", "35", "36"] and all(len(r) == len(be.HEADER) for r in rows)
    by = {r[0].split("$")[0]: r for r in rows}
    assert by == CHAPTER_ROWS

    # the moved columns are gone from the printed row: no month span, frame count, untimed count or kept count
    assert not any("2018-12" in c or "18{,}081" in c or "15{,}000" in c for r in rows for c in r)
    # ch20's printed rates are the finite-estimate rates (0.997/0.997), not the flag rates (0.990/0.995)
    assert by["20"][7:9] == ["$0.997$", "$0.997$"]
    # ch30 has no blocks section at all: only the marked calibration centre survives
    assert by["30"][2:] == [core.DASH] * 8
    # ch35's calibration null is the off population outside the block, so no between-block drift exists
    assert by["35"][5:7] == [core.DASH, core.DASH]
    # ch36's absent centre leaves the centre drift undefined while the width ratio stands
    assert by["36"][5:7] == [core.DASH, "$1.00$"]


def test_companion_ledger_prints_the_moved_columns(tmp_path):
    run = core.load_run(_ledger(tmp_path))
    frag = be.build_ledger(run)
    assert frag.name == be.LEDGER_NAME and frag.label == be.LEDGER_LABEL
    assert frag.tex.startswith(r"\begin{tabular}{" + be.LEDGER_ALIGN + "}")
    assert frag.tex.count(r"\begin{tabular}") == 1
    rows = _body_rows(frag.tex)
    # one row per channel in the chapter table's order, the same daggered channel cell
    assert [r[0] for r in rows] == [r[0] for r in _body_rows(be.build(run).tex)]
    assert all(len(r) == len(be.LEDGER_HEADER) for r in rows)
    assert {r[0].split("$")[0]: r for r in rows} == LEDGER_ROWS

    notes = "\n".join(frag.notes)
    assert r"the per-channel evidence behind Table~\ref{tab:estimator:blocked} (ch05): the same 6 channels" in notes
    assert "blocks section absent on ch 30" in notes
    assert "ddagger: split not supported on ch20 insufficient_support: calibration block has 0 populated months" in notes
    assert "untimed: 101 frames without a recorded time excluded from both blocks on 1 of 6 channels" in notes and "ch14 101" in notes
    assert "months are the block's first and last populated month" in notes
    assert "the finite-estimate rate differs from the survey flag rate on ch 20" in notes
    assert "kept dashed on ch 30, 36" in notes
    assert "the replay kept no frame on ch 35" in notes
    assert r"the masked fraction and its interval are in Table~\ref{tab:estimator:blocked}" in notes
    assert len(frag.inputs) == 7


def test_chapter_notes_explain_the_marks_and_point_at_the_companion(tmp_path):
    run = core.load_run(_ledger(tmp_path))
    notes = "\n".join(be.build(run).notes)
    assert "blocks section absent on ch 30" in notes
    assert "ddagger: split not supported on ch20 insufficient_support: calibration block has 0 populated months" in notes
    assert "null_evaluation absent on ch 30" in notes
    assert "off: the coarse null is the verified transmitter-off population of the block's frames (null.null_source) on ch 19, 20; on ch 35 (calibration block only)" in notes
    assert "off*: on ch 20 the off population fails the null-like check" in notes
    assert "*: the ledger records no null population for the block" in notes and "on ch30 (cal), ch35 (eval)" in notes
    assert "drift dashed on ch 35" in notes and "ch35 calibration null 11199 frames against 6152 in the block (the archive's verified off population, off through 2021-10)" in notes
    assert "centre drift undefined (absent or non-positive centre) on ch 36" in notes
    assert "printed on 3 of 6 channels" in notes
    assert "the finite-estimate rate differs from the survey flag rate on ch 20" in notes
    assert "a diagnostic, not a selected operating point: no channel has one (selection.status no feasible point: 4, refused: 1" in notes
    assert "replay cell dashed on ch 30, 36" in notes and "no floor for frames without a shelf estimate (1)" in notes and "absent (1)" in notes
    assert "replay on ch 20 has no bootstrap interval" in notes
    assert "selector refusals (selection.refusal): within-era stability refused_insufficient_support (4); no floor for frames without a shelf estimate (1)" in notes
    # the chapter says where the columns it no longer prints went, and the moved notes went with them
    assert be.MOVED_NOTE in be.build(run).notes
    assert r"Table~\ref{tab:archive:blocked_evaluation}" in be.MOVED_NOTE
    assert not any(n.startswith("untimed:") or n.startswith("months are the block's") for n in be.build(run).notes)
    assert any(n.startswith("untimed:") for n in be.build_ledger(run).notes)


def test_numbers_are_partitioned_between_the_fragments_and_none_dropped(tmp_path):
    run = core.load_run(_ledger(tmp_path))
    chapter, ledger = be.build(run), be.build_ledger(run)
    chapter_keys = {n.key for n in chapter.numbers}
    ledger_keys = {n.key for n in ledger.numbers}
    # every key the one wide table used to emit is still emitted, exactly once, by exactly one fragment
    assert not chapter_keys & ledger_keys
    assert all(k.startswith("ch05.blocked_evaluation.") for k in chapter_keys | ledger_keys)
    assert len(chapter.numbers) == len(chapter_keys) and len(ledger.numbers) == len(ledger_keys)
    assert _columns(chapter.numbers) == CHAPTER_COLUMNS | set(BAND_COUNTS)
    assert _columns(ledger.numbers) == LEDGER_COLUMNS
    assert len(chapter_keys | ledger_keys) == 115

    by_key = {n.key: n for n in chapter.numbers}
    k = "ch05.blocked_evaluation."
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
    assert by_key[k + "masked_fraction_evaluation.ch14"].value == 0.15 and by_key[k + "masked_fraction_evaluation.ch14"].precision == 4
    assert by_key[k + "masked_fraction_evaluation_q16.ch14"].value == 0.12 and by_key[k + "masked_fraction_evaluation_q84.ch14"].value == 0.18
    assert by_key[k + "masked_fraction_evaluation_q16.ch14"].renderings == ("0.1200--0.1800",)
    assert by_key[k + "evaluation_width_factor.ch35"].precision == 0 and by_key[k + "evaluation_width_factor.ch35"].value == pytest.approx(1551.479)
    assert by_key[k + "masked_fraction_evaluation.ch20"].value == pytest.approx(0.98684) and k + "masked_fraction_evaluation_q16.ch20" not in by_key
    assert by_key[k + "calibration_centre.ch30"].value == 0.0
    for absent in ("calibration_width_factor.ch30", "evaluation_centre.ch30", "centre_drift_db.ch30",
                   "centre_drift_db.ch35", "width_factor_ratio.ch35", "centre_drift_db.ch36",
                   "calibration_centre.ch36", "masked_fraction_evaluation.ch30", "masked_fraction_evaluation.ch36"):
        assert k + absent not in by_key, absent
    assert all(n.source["table"] == "blocked_evaluation.tex" for n in chapter.numbers)
    counts = {key.rsplit(".", 1)[1]: n.value for key, n in by_key.items() if ".ch" not in key}
    assert counts == BAND_COUNTS

    # the columns the chapter table no longer prints keep their keys, on the companion, unchanged
    led = {n.key: n for n in ledger.numbers}
    assert led[k + "calibration_first_month.ch14"].value == "2018-12" and led[k + "evaluation_last_month.ch14"].renderings == ("2026-08",)
    assert led[k + "calibration_frames.ch14"].value == 18081 and led[k + "calibration_frames.ch14"].kind == "int"
    assert led[k + "frames_without_time_excluded.ch14"].value == 101 and led[k + "frames_without_time_excluded.ch19"].value == 0
    assert led[k + "evaluation_flag_rate.ch20"].value == pytest.approx(0.995)
    assert led[k + "calibration_flag_rate.ch20"].value == pytest.approx(0.990)
    assert led[k + "kept_evaluation.ch14"].value == 15000 and led[k + "kept_evaluation.ch35"].value == 0
    for absent in ("calibration_frames.ch30", "frames_without_time_excluded.ch30", "kept_evaluation.ch30",
                   "kept_evaluation.ch36"):
        assert k + absent not in led, absent
    assert all(n.source["table"] == "blocked_evaluation_ledger.tex" for n in ledger.numbers)
    assert all(n.source["row"] == {"channel": int(n.key.rsplit(".ch", 1)[1])}
               for n in list(chapter.numbers) + list(ledger.numbers) if ".ch" in n.key)


def test_rates_note_when_they_coincide(tmp_path):
    run = core.load_run(_ledger(tmp_path))
    assert any("differs from the survey flag rate on ch 20" in n for n in be.build(run).notes)
    assert any("differs from the survey flag rate on ch 20" in n for n in be.build_ledger(run).notes)
    # every channel's flag rate equal to its finite-estimate rate: both fragments say so
    for c in run.channels:
        if c.has("blocks"):
            b = dict(c.blocks)
            b["calibration_flag_rate"], b["evaluation_flag_rate"] = b["calibration_finite_estimate_rate"], b["evaluation_finite_estimate_rate"]
            c.sections["blocks"] = b
    for frag in (be.build(run), be.build_ledger(run)):
        assert any(n.startswith("the finite-estimate rate equals the survey flag rate on every channel (5)") for n in frag.notes)


def test_write_report_round_trip(tmp_path):
    run = core.load_run(_ledger(tmp_path))
    manifest = core.write_report(run, tmp_path / "out", list(be.BUILDERS), commit="f" * 40,
                                 generated="2026-09-07T01:00:00+00:00")
    arts = {a["name"]: a for a in manifest["artifacts"]}
    assert set(arts) == {"blocked_evaluation", "blocked_evaluation_ledger"}
    assert arts["blocked_evaluation"]["label"] == "tab:estimator:blocked"
    assert arts["blocked_evaluation_ledger"]["label"] == "tab:archive:blocked_evaluation"
    for name, build in (("blocked_evaluation", be.build), ("blocked_evaluation_ledger", be.build_ledger)):
        frag = build(run)
        assert arts[name]["count"] == len(frag.numbers)
        loaded = nb.load_numbers([tmp_path / "out" / "numbers" / f"{name}.numbers.json"])
        assert len(loaded) == arts[name]["count"] and len({n.key for n in loaded}) == arts[name]["count"]
        assert (tmp_path / "out" / "tables" / f"{name}.tex").read_text() == frag.tex
        assert arts[name]["notes"] == frag.notes
    # the two documents together still carry every key, once
    both = nb.load_numbers([tmp_path / "out" / "numbers" / "blocked_evaluation.numbers.json",
                            tmp_path / "out" / "numbers" / "blocked_evaluation_ledger.numbers.json"])
    assert len({n.key for n in both}) == len(both) == 115


@pytest.mark.skipif(not (REAL_RUN / "ledger" / "run.json").is_file(), reason="archive results not present")
def test_real_run_renders_23_channels(tmp_path):
    run = core.load_run(REAL_RUN)
    chapter, ledger = be.build(run), be.build_ledger(run)
    for frag, header in ((chapter, be.HEADER), (ledger, be.LEDGER_HEADER)):
        rows = _body_rows(frag.tex)
        assert len(rows) == 23 and [int(r[0].split("$")[0]) for r in rows] == list(range(14, 37))
        assert all(len(r) == len(header) for r in rows)
        assert frag.tex.count(r"\begin{tabular}") == 1
        assert frag.notes
    core.write_report(run, tmp_path / "out", list(be.BUILDERS), commit=run.commit, generated="2026-09-07T09:00:00+00:00")
    keys = []
    for name in ("blocked_evaluation", "blocked_evaluation_ledger"):
        doc = json.loads((tmp_path / "out" / "numbers" / f"{name}.numbers.json").read_text())
        keys += [n["key"] for n in doc["numbers"]]
    assert len(keys) == len(set(keys)) and keys and all(k.startswith("ch05.blocked_evaluation.") for k in keys)
    # the split is supported on all 23 channels, so no channel is daggered and no split_status key is emitted;
    # every other column of each fragment is present, and the two column sets stay disjoint
    assert not any(be.split_marked(c) for c in run.channels) and r"\ddagger" not in chapter.tex
    assert _columns(chapter.numbers) == (CHAPTER_COLUMNS - {"split_status"}) | set(BAND_COUNTS)
    assert _columns(ledger.numbers) == LEDGER_COLUMNS
    assert not _columns(chapter.numbers) & _columns(ledger.numbers)
    # no channel has a selected point: every replay printed is the diagnostic one, none of the numbers a selection
    assert all(c.selection.get("rho") is None for c in run.channels)
    assert any("a diagnostic, not a selected operating point: no channel has one" in n for n in chapter.notes)
