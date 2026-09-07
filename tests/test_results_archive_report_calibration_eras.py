"""tab:calibration:eras: every column from a synthetic ledger, and the real run when present."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from rfisher_results.archive import numbers as nb
from rfisher_results.archive.report import calibration_eras, core

REAL = Path("/home/djg/rail/results/archive_v5_2026-09-07")
ERA_COLUMNS = ["channel", "freq_id", "era", "n_eras", "first_month", "last_month", "state", "evidence", "record_agreement",
               "boundary_uncertainty_months", "populated_months", "months_spanned", "coverage", "peak_offset_bins",
               "peak_drift_bins_per_month", "peak_range_bins", "peak_months", "is_current"]
DAGGER = calibration_eras.RANGE_MARK


def _era(**kw):
    base = {"n_eras": 1, "current_era": 1, "current_first_month": "2018-12", "current_last_month": "2026-08",
            "current_state": "proxy-low", "current_evidence": "archive start", "current_boundary_uncertainty_months": 0,
            "current_frames": 40552, "stale_latest": False, "stale_lag_months": 0, "stale_reference": "campaign",
            "campaign_last_month": "2026-08", "fallback": "", "unmatched_station_records": "",
            "current_peak_drift_bins_per_month": None, "current_peak_range_bins": None,
            "unconfirmed_instrument_change_last_month": False}
    base.update(kw)
    return base


RECORDS = {
    # a multi-era on channel: a slope that rounds to zero prints unsigned; range 3 exceeds the half-width 2
    35: _era(n_eras=3, current_era=3, current_first_month="2025-11", current_state="proxy-high",
             current_evidence="transmitter sign-on", current_boundary_uncertainty_months=2, current_frames=12288,
             unmatched_station_records="2022-09", current_peak_drift_bins_per_month=3.9114090282281235e-16,
             current_peak_range_bins=3.0),
    # an off (proxy-low) current era: no located month, drift and range undefined
    19: _era(n_eras=2, current_era=2, current_first_month="2024-12", current_last_month="2026-04",
             current_evidence="spectral-state transition", current_boundary_uncertainty_months=8, current_frames=12900,
             stale_latest=True, stale_lag_months=4),
    # a single on era: a negative slope, range at (not beyond) the half-width, an unconfirmed last-month instrument map
    22: _era(current_state="proxy-high", fallback="no_off_state", stale_lag_months=1, current_frames=39092,
             current_peak_drift_bins_per_month=-0.007589273797893458, current_peak_range_bins=2.0,
             unconfirmed_instrument_change_last_month=True),
    # a positive slope with a half-integer range beyond the half-width
    17: _era(n_eras=2, current_era=2, current_first_month="2025-10", current_state="proxy-high",
             current_evidence="station change", current_boundary_uncertainty_months=0, current_frames=12601,
             fallback="no_off_state", current_peak_drift_bins_per_month=0.4636363636363635, current_peak_range_bins=2.5,
             unconfirmed_instrument_change_last_month=True),
    # one located month: a range of zero beside an undefined drift; no eras-table row
    14: _era(current_frames=36162, current_peak_range_bins=0.0, unconfirmed_instrument_change_last_month=True),
    30: None,
}
ERAS = [
    dict(channel=35, era=1, first_month="2018-12", last_month="2021-10", state="proxy-low", evidence="archive start",
         record_agreement="", populated_months=33, months_spanned=35, coverage=33 / 35, peak_months=0, is_current=False),
    dict(channel=35, era=2, first_month="2021-11", last_month="2025-10", state="proxy-high", evidence="station change",
         record_agreement="", populated_months=40, months_spanned=48, coverage=40 / 48, peak_offset_bins=25.0,
         peak_drift_bins_per_month=-0.29, peak_range_bins=8.0, peak_months=40, is_current=False),
    dict(channel=35, era=3, first_month="2025-11", last_month="2026-08", state="proxy-high", evidence="transmitter sign-on",
         record_agreement="confirmed by record 2025-11", populated_months=10, months_spanned=10, coverage=1.0,
         peak_offset_bins=28.5, peak_drift_bins_per_month=3.9114090282281235e-16, peak_range_bins=3.0, peak_months=10,
         is_current=True),
    dict(channel=19, era=1, first_month="2022-10", last_month="2024-03", state="proxy-high", evidence="archive start",
         record_agreement="", populated_months=18, months_spanned=18, coverage=1.0, peak_offset_bins=0.0,
         peak_drift_bins_per_month=0.43, peak_range_bins=6.0, peak_months=18, is_current=False),
    dict(channel=19, era=2, first_month="2024-12", last_month="2026-04", state="proxy-low", evidence="spectral-state transition",
         record_agreement="record 2024-12 says sign-on; direction disagrees", populated_months=17, months_spanned=20,
         coverage=0.85, peak_months=0, is_current=True),
    dict(channel=22, era=1, first_month="2018-12", last_month="2026-08", state="proxy-high", evidence="archive start",
         record_agreement="", populated_months=87, months_spanned=93, coverage=87 / 93, peak_offset_bins=12.0,
         peak_drift_bins_per_month=-0.007589273797893458, peak_range_bins=2.0, peak_months=87, is_current=True),
    dict(channel=17, era=1, first_month="2018-12", last_month="2025-09", state="proxy-high", evidence="archive start",
         record_agreement="", populated_months=70, months_spanned=82, coverage=70 / 82, peak_offset_bins=2.0,
         peak_drift_bins_per_month=-0.05, peak_range_bins=5.0, peak_months=60, is_current=False),
    dict(channel=17, era=2, first_month="2025-10", last_month="2026-08", state="proxy-high", evidence="station change",
         record_agreement="", populated_months=11, months_spanned=11, coverage=1.0, peak_offset_bins=20.0,
         peak_drift_bins_per_month=0.4636363636363635, peak_range_bins=2.5, peak_months=11, is_current=True),
]


def _write_run(tmp_path, records=RECORDS, eras=ERAS, *, eras_json: bool = False):
    ledger = tmp_path / "ledger"
    (ledger / "channels").mkdir(parents=True)
    files = []
    for ch, era in sorted(records.items()):
        fid = 1000 - ch
        rel = f"channels/ch{ch:02d}_fid{fid}.json"
        files.append(rel)
        rec = {"channel": ch, "freq_id": fid, "product": f"{fid}.npz", "product_sha256": "b" * 64, "notes": [],
               "sections": {"era": era, "selection": None}}
        (ledger / rel).write_text(json.dumps(rec))
    run = {"schema": {"name": "rfisher-archive-ledger", "version": 1}, "generated": "2026-09-07T00:00:00+00:00",
           "producer": {"commit": "a" * 40}, "products": {}, "channels": files, "campaign_last_month": "2026-08",
           "era_config": {"station_shift_bins": 3.0, "persistence_months": 2}, "era_config_digest": "c" * 64}
    (ledger / "run.json").write_text(json.dumps(run))
    if eras is not None and not eras_json:
        (tmp_path / "tables").mkdir()
        with (tmp_path / "tables" / "eras.csv").open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=ERA_COLUMNS)
            w.writeheader()
            for row in eras:
                w.writerow({**{k: "" for k in ERA_COLUMNS}, "freq_id": 1000 - row["channel"],
                            "n_eras": sum(r["channel"] == row["channel"] for r in eras), "boundary_uncertainty_months": 0, **row})
    elif eras is not None:
        # the per-channel eras.json carries the span, state, evidence, record and coverage of each era (no peak drift columns)
        by_channel: dict[int, list] = {}
        for row in eras:
            by_channel.setdefault(row["channel"], []).append(row)
        for ch, rows in by_channel.items():
            d = tmp_path / "channels" / f"ch{ch:02d}"
            d.mkdir(parents=True)
            current = [r["era"] for r in rows if r["is_current"]][0]
            (d / "eras.json").write_text(json.dumps({"channel": ch, "current_era": current,
                                                     "eras": [{k: v for k, v in r.items() if not k.startswith("peak_") and k != "is_current"}
                                                              for r in rows]}))
    return tmp_path


def _rows(tex: str) -> dict[int, list[str]]:
    lines = tex.splitlines()
    body = lines[lines.index(r"\midrule") + 1: lines.index(r"\bottomrule")]
    rows = [[c.strip() for c in ln[:-2].split(" & ")] for ln in body if ln.endswith(r"\\")]
    return {int(r[0]): r for r in rows}


def _numbers(frag) -> dict[str, nb.Number]:
    keys = [n.key for n in frag.numbers]
    assert len(keys) == len(set(keys))
    return {n.key: n for n in frag.numbers}


def test_every_column_from_a_synthetic_ledger(tmp_path):
    run = core.load_run(_write_run(tmp_path))
    frag = calibration_eras.build(run)
    assert frag.name == "calibration_eras" and frag.label == "tab:calibration:eras"
    assert frag.tex.startswith(r"\begin{tabular}{rlllrllllrrrrl}")
    assert frag.tex.splitlines()[2] == (r"Ch. & State & Start & End & $\pm$ mo & Evidence & Record & Stale (lag) & Earlier eras & Frames"
                                        r" & Coverage & Drift (bins/mo) & Range (bins) & Instr.\ (last mo.) \\")
    rows = _rows(frag.tex)
    assert list(rows) == [14, 17, 19, 22, 30, 35]
    box = "\\parbox[t]{" + calibration_eras.EARLIER_WIDTH + "}{\\raggedright "
    # a multi-era channel with a confirmed record and an unmatched station record; a zero slope, a marked range
    r = rows[35]
    assert r[1:8] == ["high", "2025-11", "2026-08", "2", "transmitter sign-on", "confirmed 2025-11; unmatched 2022-09", "no"]
    assert r[8] == box + "2018-12..2021-10 low; 2021-11..2025-10 high}"
    assert r[9:] == ["$12{,}288$", "10/10", "$0.00$", "$3" + DAGGER + "$", "none"]
    # a stale off channel whose record disagrees: no located month, drift and range undefined
    r = rows[19]
    assert r[1:8] == ["low", "2024-12", "2026-04", "8", "spectral-state transition", "disagrees 2024-12 (sign-on)", "yes (4)"]
    assert r[8] == box + "2022-10..2024-03 high}" and r[9:] == ["$12{,}900$", "17/20", "--", "--", "none"]
    # archive start: undefined uncertainty, no record, no earlier eras; the no-off fallback and a within-grace lag;
    # a negative slope, a range at the half-width (unmarked), an unconfirmed instrument map in the last month
    r = rows[22]
    assert r[1:] == ["high (no off)", "2018-12", "2026-08", "--", "archive start", "--", "no (1)", "--", "$39{,}092$", "87/93",
                     "$-0.01$", "$2$", "unconfirmed"]
    # a positive slope and a half-integer range beyond the half-width
    r = rows[17]
    assert r[1:8] == ["high (no off)", "2025-10", "2026-08", "0", "station change", "--", "no"]
    assert r[8] == box + "2018-12..2025-09 high}"
    assert r[9:] == ["$12{,}601$", "11/11", "$+0.46$", "$2.5" + DAGGER + "$", "unconfirmed"]
    # an era section without an eras-table row: the table-derived cells are dashed; one located month (range 0, no drift)
    r = rows[14]
    assert r[1:] == ["low", "2018-12", "2026-08", "--", "archive start", "--", "no", "--", "$36{,}162$", "--", "--", "$0$", "unconfirmed"]
    # no era section at all
    assert rows[30][1:] == ["--"] * 13
    assert any("channels 14" in n for n in frag.notes) and any("channels 30" in n for n in frag.notes)
    assert any(n.startswith("drift and range:") and n.endswith(": channels 14, 19") for n in frag.notes)
    assert any(n.startswith("range marked dagger where it exceeds the designated half-width 2 bins (channels 17, 35)")
               and "(3 bins against the running median)" in n for n in frag.notes)
    assert any(n.startswith("instr. (last mo.) reads 'unconfirmed'") and "(2 months)" in n and n.endswith(": channels 14, 17, 22")
               for n in frag.notes)

    nums = _numbers(frag)
    assert nums["ch08.eras.n_eras.ch35"].value == 3 and nums["ch08.eras.current_first_month.ch35"].value == "2025-11"
    assert nums["ch08.eras.current_boundary_uncertainty_months.ch35"].value == 2
    assert "ch08.eras.current_boundary_uncertainty_months.ch22" not in nums
    assert nums["ch08.eras.current_evidence.ch35"].renderings == ("transmitter sign-on", "sign-on")
    assert nums["ch08.eras.record_agreement.ch35"].renderings == ("confirmed by record 2025-11", "confirmed 2025-11")
    assert nums["ch08.eras.record_agreement.ch19"].renderings[1] == "disagrees 2024-12 (sign-on)"
    assert nums["ch08.eras.unmatched_station_records.ch35"].renderings == ("unmatched 2022-09", "2022-09")
    assert "ch08.eras.record_agreement.ch22" not in nums and "ch08.eras.unmatched_station_records.ch19" not in nums
    assert nums["ch08.eras.stale_latest.ch19"].renderings == ("yes", "yes (4)") and nums["ch08.eras.stale_lag_months.ch19"].value == 4
    assert nums["ch08.eras.stale_latest.ch22"].renderings == ("no", "no (1)") and nums["ch08.eras.stale_lag_months.ch14"].value == 0
    assert nums["ch08.eras.earlier_eras.ch35"].value == "2018-12..2021-10 low; 2021-11..2025-10 high"
    assert "ch08.eras.earlier_eras.ch22" not in nums and "ch08.eras.earlier_eras.ch14" not in nums
    assert nums["ch08.eras.current_frames.ch35"].value == 12288 and nums["ch08.eras.current_frames.ch35"].kind == "int"
    assert nums["ch08.eras.coverage.ch19"].value == 0.85 and nums["ch08.eras.coverage.ch19"].renderings == ("17/20",)
    assert nums["ch08.eras.coverage_populated_months.ch19"].value == 17 and nums["ch08.eras.coverage_months_spanned.ch19"].value == 20
    assert "ch08.eras.coverage.ch14" not in nums and "ch08.eras.current_state.ch30" not in nums
    assert nums["ch08.eras.current_state.ch22"].renderings == ("high", "proxy-high")
    # drift, range, the mark and the instrument flag
    d = nums["ch08.eras.current_peak_drift_bins_per_month.ch17"]
    assert d.value == pytest.approx(0.4636363636363635) and d.precision == 2 and d.renderings == ("+0.46",)
    assert nums["ch08.eras.current_peak_drift_bins_per_month.ch22"].renderings == ("-0.01",)
    assert nums["ch08.eras.current_peak_drift_bins_per_month.ch35"].renderings == ("0.00",)
    assert not {k for k in nums if k.startswith("ch08.eras.current_peak_drift_bins_per_month.")} & {".ch14", ".ch19", ".ch30"}
    assert "ch08.eras.current_peak_drift_bins_per_month.ch14" not in nums and "ch08.eras.current_peak_drift_bins_per_month.ch19" not in nums
    r35 = nums["ch08.eras.current_peak_range_bins.ch35"]
    assert r35.value == 3.0 and r35.precision == 0 and r35.renderings == ("3",) and r35.kind == "float"
    r17 = nums["ch08.eras.current_peak_range_bins.ch17"]
    assert r17.value == 2.5 and r17.precision == 1 and r17.renderings == ("2.5",)
    assert nums["ch08.eras.current_peak_range_bins.ch14"].value == 0.0 and "ch08.eras.current_peak_range_bins.ch19" not in nums
    assert nums["ch08.eras.peak_range_exceeds_half_width.ch35"].value == "yes"
    assert nums["ch08.eras.peak_range_exceeds_half_width.ch22"].value == "no"
    assert nums["ch08.eras.peak_range_exceeds_half_width.ch14"].value == "no"
    assert "ch08.eras.peak_range_exceeds_half_width.ch19" not in nums
    assert nums["ch08.eras.peak_months.ch17"].value == 11 and nums["ch08.eras.peak_months.ch19"].value == 0
    assert "ch08.eras.peak_months.ch14" not in nums
    u = nums["ch08.eras.unconfirmed_instrument_change_last_month.ch22"]
    assert u.value == "yes" and u.kind == "text" and u.renderings == ("yes", "unconfirmed")
    assert nums["ch08.eras.unconfirmed_instrument_change_last_month.ch35"].renderings == ("no", "none")
    assert "ch08.eras.unconfirmed_instrument_change_last_month.ch30" not in nums
    # band level
    assert nums["ch08.eras.n_channels"].value == 6 and nums["ch08.eras.n_eras_total"].value == 9
    assert nums["ch08.eras.n_channels_multi_era"].value == 3 and nums["ch08.eras.n_channels_record_confirmed"].value == 1
    assert nums["ch08.eras.n_channels_stale"].value == 1 and nums["ch08.eras.n_channels_no_off_state"].value == 2
    assert nums["ch08.eras.n_channels_drift_measured"].value == 3
    assert nums["ch08.eras.n_channels_peak_range_exceeds_half_width"].value == 2
    assert nums["ch08.eras.n_channels_unconfirmed_instrument_change"].value == 3
    assert nums["ch08.eras.designated_half_width"].value == 2
    assert nums["ch08.eras.campaign_last_month"].value == "2026-08"
    assert all(n.source["row"] == {"channel": 35} for n in frag.numbers if n.key.endswith(".ch35"))
    assert all(n.source["table"] == "calibration_eras.tex" for n in frag.numbers)
    assert frag.inputs[-1] == tmp_path / "tables" / "eras.csv" and len(frag.inputs) == 8


def test_flag_absent_from_an_older_ledger_is_dashed(tmp_path):
    """An era section written before the drift columns existed prints the dash, not a false 'none'."""
    old = {k: v for k, v in _era().items()
           if k not in ("current_peak_drift_bins_per_month", "current_peak_range_bins", "unconfirmed_instrument_change_last_month")}
    frag = calibration_eras.build(core.load_run(_write_run(tmp_path, records={21: old}, eras=None)))
    assert _rows(frag.tex)[21][11:] == ["--", "--", "--"]
    nums = _numbers(frag)
    assert not any(k.endswith(".ch21") and ("peak" in k or "instrument" in k) for k in nums)
    assert nums["ch08.eras.n_channels_drift_measured"].value == 0
    assert nums["ch08.eras.n_channels_unconfirmed_instrument_change"].value == 0
    assert any("(no channel)" in n and n.startswith("range marked") for n in frag.notes)
    assert any("(no channel)" in n and n.startswith("instr.") for n in frag.notes)


def test_eras_json_fallback_matches_the_flat_table(tmp_path):
    flat = calibration_eras.build(core.load_run(_write_run(tmp_path / "flat")))
    nested = calibration_eras.build(core.load_run(_write_run(tmp_path / "nested", eras_json=True)))
    assert _rows(flat.tex) == _rows(nested.tex)
    # peak_months lives only in tables/eras.csv; every printed cell reads the era section and agrees
    flat_numbers = [(n.key, n.value) for n in flat.numbers if not n.key.startswith("ch08.eras.peak_months.")]
    assert flat_numbers == [(n.key, n.value) for n in nested.numbers]
    assert not any(n.key.startswith("ch08.eras.peak_months.") for n in nested.numbers)
    assert sorted(p.name for p in nested.inputs[-4:]) == ["eras.json"] * 4


def test_inconsistent_eras_table_is_dashed_with_a_note(tmp_path):
    eras = [dict(r, first_month="2025-12") if r["channel"] == 35 and r["is_current"] else r for r in ERAS]
    frag = calibration_eras.build(core.load_run(_write_run(tmp_path, eras=eras)))
    r = _rows(frag.tex)[35]
    assert r[2] == "2025-11" and r[6] == "unmatched 2022-09" and r[8] == "--" and r[10] == "--"
    assert r[11:] == ["$0.00$", "$3" + DAGGER + "$", "none"]     # the era section's own columns survive
    assert any(n.startswith("ch35: the eras table's current era (2025-12..2026-08) disagrees") for n in frag.notes)
    nums = _numbers(frag)
    assert "ch08.eras.record_agreement.ch35" not in nums and "ch08.eras.coverage.ch35" not in nums
    assert "ch08.eras.peak_months.ch35" not in nums and nums["ch08.eras.current_peak_range_bins.ch35"].value == 3.0


def test_write_report_round_trip(tmp_path):
    run = core.load_run(_write_run(tmp_path))
    manifest = core.write_report(run, tmp_path / "out", [calibration_eras.build], commit="d" * 40, generated="2026-09-07T01:00:00+00:00")
    assert manifest["artifacts"][0]["label"] == "tab:calibration:eras"
    doc = json.loads((tmp_path / "out" / "numbers" / "calibration_eras.numbers.json").read_text())
    assert {i["path"] for i in doc["inputs"]} >= {str(tmp_path / "tables" / "eras.csv")}
    assert nb.load_numbers([tmp_path / "out" / "numbers" / "calibration_eras.numbers.json"])


@pytest.mark.skipif(not (REAL / "ledger" / "run.json").is_file(), reason="the final archive run is not on this machine")
def test_real_run_renders_23_channels(tmp_path):
    run = core.load_run(REAL)
    frag = calibration_eras.build(run)
    rows = _rows(frag.tex)
    assert list(rows) == list(range(14, 37))
    nums = _numbers(frag)
    assert nums["ch08.eras.n_channels"].value == 23
    assert rows[30][7].startswith("yes") and nums["ch08.eras.stale_latest.ch30"].value == "yes"
    assert rows[19][6].startswith("confirmed 2024-12") and rows[29][8] == "--"
    # the drift columns: marked ranges on the slow-drift on channels, dashes on every proxy-low era
    assert rows[15][11:] == ["$+0.29$", "$5" + DAGGER + "$", "none"]
    assert rows[17][11:] == ["$+0.46$", "$8" + DAGGER + "$", "unconfirmed"]
    assert rows[22][11:] == ["$-0.01$", "$2$", "none"] and rows[14][11:] == ["--", "$0$", "unconfirmed"]
    assert all(rows[ch][11:13] == ["--", "--"] for ch in (19, 20, 26, 27, 32))
    assert nums["ch08.eras.n_channels_peak_range_exceeds_half_width"].value == 5
    assert [ch for ch in rows if DAGGER in rows[ch][12]] == [15, 17, 24, 31, 35]
    assert nums["ch08.eras.n_channels_unconfirmed_instrument_change"].value == 8
    assert nums["ch08.eras.peak_months.ch15"].value == 16
    core.write_report(run, tmp_path, [calibration_eras.build], commit=run.commit, generated=run.generated)
    doc = json.loads((tmp_path / "numbers" / "calibration_eras.numbers.json").read_text())
    keys = [n["key"] for n in doc["numbers"]]
    assert len(keys) == len(set(keys)) and len(keys) == len(frag.numbers)
