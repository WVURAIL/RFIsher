r"""tab:calibration:eras (chapter 8) and its companion ledger tab:archive:calibration_eras (appendix C).

The chapter table prints exactly the columns the chapter's \stubtab names beside
the channel; the evidence the builder carries beyond the stub -- the spectral
state, the located-month count, the peak drift and range, and the
unconfirmed-instrument flag -- prints in the companion fragment. Between them
the two fragments emit the same number keys the single wide table did, each
key once.
"""
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

# the number keys the wide table emitted, split between the two fragments; no key was dropped or duplicated
CHAPTER_ROW_KEYS = {"n_eras", "current_first_month", "current_last_month", "current_boundary_uncertainty_months",
                    "current_evidence", "record_agreement", "unmatched_station_records", "stale_latest",
                    "stale_lag_months", "earlier_eras", "current_frames", "coverage", "coverage_populated_months",
                    "coverage_months_spanned"}
LEDGER_ROW_KEYS = {"current_state", "peak_months", "current_peak_drift_bins_per_month", "current_peak_range_bins",
                   "peak_range_exceeds_half_width", "unconfirmed_instrument_change_last_month"}
CHAPTER_BAND_KEYS = {"n_channels", "n_eras_total", "n_channels_multi_era", "n_channels_record_confirmed",
                     "n_channels_stale", "campaign_last_month"}
LEDGER_BAND_KEYS = {"n_channels_no_off_state", "n_channels_drift_measured", "n_channels_peak_range_exceeds_half_width",
                    "n_channels_unconfirmed_instrument_change", "designated_half_width"}


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


def _stems(frag) -> set[str]:
    """The key stems the fragment emits: 'ch08.eras.coverage.ch19' -> 'coverage'."""
    stems = set()
    for n in frag.numbers:
        rest = n.key[len(calibration_eras.KEY) + 1:]
        stems.add(rest.rsplit(".ch", 1)[0] if ".ch" in rest else rest)
    return stems


# ------------------------------------------------------------------ the registry
def test_the_registry_picks_up_both_fragments():
    assert calibration_eras.BUILDERS == (calibration_eras.build, calibration_eras.build_ledger)
    assert calibration_eras.LEDGER_NAME == "calibration_eras_ledger"
    assert calibration_eras.LEDGER_LABEL == "tab:archive:calibration_eras"


# ------------------------------------------------------------------ the chapter table
def test_the_chapter_table_prints_the_stubs_columns(tmp_path):
    """Exactly the stub's columns beside the channel: no state, drift, range or instrument column."""
    run = core.load_run(_write_run(tmp_path))
    frag = calibration_eras.build(run)
    assert frag.name == "calibration_eras" and frag.label == "tab:calibration:eras"
    assert frag.tex.startswith(r"\begin{tabular}{rllrllllrr}")
    assert frag.tex.splitlines()[2] == (r"Ch. & Start & End & $\pm$ mo & Evidence & Record & Stale (lag) & Earlier eras"
                                        r" & Frames & Coverage \\")
    assert frag.tex.count(r"\begin{tabular}") == 1        # one tabular: no panel split was needed
    for dropped in ("State", "Drift (bins/mo)", "Range (bins)", r"Instr.\ (last mo.)", "Peak mo."):
        assert dropped not in frag.tex.splitlines()[2]
    rows = _rows(frag.tex)
    assert list(rows) == [14, 17, 19, 22, 30, 35]
    assert all(len(r) == 10 for r in rows.values())
    box = "\\parbox[t]{" + calibration_eras.EARLIER_WIDTH + "}{\\raggedright "
    # a multi-era channel with a confirmed record and an unmatched station record
    r = rows[35]
    assert r[1:7] == ["2025-11", "2026-08", "2", "transmitter sign-on", "confirmed 2025-11; unmatched 2022-09", "no"]
    assert r[7] == box + "2018-12..2021-10 low; 2021-11..2025-10 high}"
    assert r[8:] == ["$12{,}288$", "10/10"]
    # a stale off channel whose record disagrees
    r = rows[19]
    assert r[1:7] == ["2024-12", "2026-04", "8", "spectral-state transition", "disagrees 2024-12 (sign-on)", "yes (4)"]
    assert r[7] == box + "2022-10..2024-03 high}" and r[8:] == ["$12{,}900$", "17/20"]
    # archive start: undefined uncertainty, no record, no earlier eras; a within-grace lag
    assert rows[22][1:] == ["2018-12", "2026-08", "--", "archive start", "--", "no (1)", "--", "$39{,}092$", "87/93"]
    r = rows[17]
    assert r[1:7] == ["2025-10", "2026-08", "0", "station change", "--", "no"]
    assert r[7] == box + "2018-12..2025-09 high}" and r[8:] == ["$12{,}601$", "11/11"]
    # an era section without an eras-table row: the table-derived cells are dashed
    assert rows[14][1:] == ["2018-12", "2026-08", "--", "archive start", "--", "no", "--", "$36{,}162$", "--"]
    assert rows[30][1:] == ["--"] * 9                     # no era section at all
    assert any("channels 14" in n for n in frag.notes) and any("channels 30" in n for n in frag.notes)
    assert any(calibration_eras.LEDGER_NAME in n and calibration_eras.LEDGER_LABEL in n and "1022 pt" in n
               for n in frag.notes)
    assert any("one tabular, no panel split" in n and "650.4 pt" in n for n in frag.notes)

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
    assert "ch08.eras.coverage.ch14" not in nums
    # band level
    assert nums["ch08.eras.n_channels"].value == 6 and nums["ch08.eras.n_eras_total"].value == 9
    assert nums["ch08.eras.n_channels_multi_era"].value == 3 and nums["ch08.eras.n_channels_record_confirmed"].value == 1
    assert nums["ch08.eras.n_channels_stale"].value == 1 and nums["ch08.eras.campaign_last_month"].value == "2026-08"
    assert all(n.source["row"] == {"channel": 35} for n in frag.numbers if n.key.endswith(".ch35"))
    assert all(n.source["table"] == "calibration_eras.tex" for n in frag.numbers)
    assert frag.inputs[-1] == tmp_path / "tables" / "eras.csv" and len(frag.inputs) == 8


# ------------------------------------------------------------------ the companion ledger
def test_the_companion_ledger_prints_the_evidence_columns(tmp_path):
    """tab:archive:calibration_eras: the columns the stub does not name, one row per channel."""
    run = core.load_run(_write_run(tmp_path))
    frag = calibration_eras.build_ledger(run)
    assert frag.name == "calibration_eras_ledger" and frag.label == "tab:archive:calibration_eras"
    assert frag.tex.startswith(r"\begin{tabular}{rlrrrl}")
    assert frag.tex.splitlines()[2] == r"Ch. & State & Peak mo. & Drift (bins/mo) & Range (bins) & Instr.\ (last mo.) \\"
    rows = _rows(frag.tex)
    assert list(rows) == [14, 17, 19, 22, 30, 35]         # the same one-row-per-channel shape, joined on the channel
    assert list(rows) == list(_rows(calibration_eras.build(run).tex))
    # a zero slope prints unsigned; the range 3 is marked beyond the half-width 2
    assert rows[35][1:] == ["high", "$10$", "$0.00$", "$3" + DAGGER + "$", "none"]
    # a proxy-low current era: no located month, drift and range undefined
    assert rows[19][1:] == ["low", "$0$", "--", "--", "none"]
    # the no-off fallback; a negative slope; a range at (not beyond) the half-width; an unconfirmed last-month map
    assert rows[22][1:] == ["high (no off)", "$87$", "$-0.01$", "$2$", "unconfirmed"]
    assert rows[17][1:] == ["high (no off)", "$11$", "$+0.46$", "$2.5" + DAGGER + "$", "unconfirmed"]
    # an era section without an eras-table row: the located-month count is dashed; one located month (range 0, no drift)
    assert rows[14][1:] == ["low", "--", "--", "$0$", "unconfirmed"]
    assert rows[30][1:] == ["--"] * 5                     # no era section at all
    assert any(n.startswith("the term-by-term era evidence behind tab:calibration:eras") for n in frag.notes)
    assert any(n.startswith("peak mo. is the current era's located-month count") for n in frag.notes)
    assert any(n.startswith("drift and range:") and n.endswith(": channels 14, 19") for n in frag.notes)
    assert any(n.startswith("range marked dagger where it exceeds the designated half-width 2 bins (channels 17, 35)")
               and "(3 bins against the running median)" in n for n in frag.notes)
    assert any(n.startswith("instr. (last mo.) reads 'unconfirmed'") and "(2 months)" in n and n.endswith(": channels 14, 17, 22")
               for n in frag.notes)
    assert any("channels 14" in n and "located-month count is dashed" in n for n in frag.notes)
    assert any("channels 30" in n for n in frag.notes)

    nums = _numbers(frag)
    assert nums["ch08.eras.current_state.ch22"].renderings == ("high", "proxy-high")
    assert "ch08.eras.current_state.ch30" not in nums
    d = nums["ch08.eras.current_peak_drift_bins_per_month.ch17"]
    assert d.value == pytest.approx(0.4636363636363635) and d.precision == 2 and d.renderings == ("+0.46",)
    assert nums["ch08.eras.current_peak_drift_bins_per_month.ch22"].renderings == ("-0.01",)
    assert nums["ch08.eras.current_peak_drift_bins_per_month.ch35"].renderings == ("0.00",)
    assert "ch08.eras.current_peak_drift_bins_per_month.ch14" not in nums
    assert "ch08.eras.current_peak_drift_bins_per_month.ch19" not in nums
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
    assert nums["ch08.eras.n_channels_no_off_state"].value == 2 and nums["ch08.eras.n_channels_drift_measured"].value == 3
    assert nums["ch08.eras.n_channels_peak_range_exceeds_half_width"].value == 2
    assert nums["ch08.eras.n_channels_unconfirmed_instrument_change"].value == 3
    assert nums["ch08.eras.designated_half_width"].value == 2
    assert all(n.source["table"] == "calibration_eras_ledger.tex" for n in frag.numbers)
    assert all(n.source["row"] == {"channel": 17} for n in frag.numbers if n.key.endswith(".ch17"))
    assert frag.inputs == calibration_eras.build(run).inputs


# ------------------------------------------------------------------ the number keys the split must preserve
def test_the_two_fragments_emit_every_key_once(tmp_path):
    """Moving a column moved its numbers with it: the union is the pre-split inventory, with no key in both."""
    run = core.load_run(_write_run(tmp_path))
    chapter, ledger = calibration_eras.build(run), calibration_eras.build_ledger(run)
    ch_keys = {n.key for n in chapter.numbers}
    led_keys = {n.key for n in ledger.numbers}
    assert not ch_keys & led_keys
    assert _stems(chapter) == CHAPTER_ROW_KEYS | CHAPTER_BAND_KEYS
    assert _stems(ledger) == LEDGER_ROW_KEYS | LEDGER_BAND_KEYS
    # every per-channel key is emitted for the channels that carry the datum, in one fragment or the other
    for ch in (14, 17, 19, 22, 35):
        assert f"ch08.eras.n_eras.ch{ch}" in ch_keys and f"ch08.eras.current_state.ch{ch}" in led_keys
    assert len(ch_keys) + len(led_keys) == len(chapter.numbers) + len(ledger.numbers)


def test_flag_absent_from_an_older_ledger_is_dashed(tmp_path):
    """An era section written before the drift columns existed prints the dash, not a false 'none'."""
    old = {k: v for k, v in _era().items()
           if k not in ("current_peak_drift_bins_per_month", "current_peak_range_bins", "unconfirmed_instrument_change_last_month")}
    run = core.load_run(_write_run(tmp_path, records={21: old}, eras=None))
    frag = calibration_eras.build_ledger(run)
    assert _rows(frag.tex)[21][3:] == ["--", "--", "--"]
    nums = _numbers(frag)
    assert not any(k.endswith(".ch21") and ("peak" in k or "instrument" in k) for k in nums)
    assert nums["ch08.eras.n_channels_drift_measured"].value == 0
    assert nums["ch08.eras.n_channels_unconfirmed_instrument_change"].value == 0
    assert any("(no channel)" in n and n.startswith("range marked") for n in frag.notes)
    assert any("(no channel)" in n and n.startswith("instr.") for n in frag.notes)
    # the chapter table is unaffected: its columns never read the drift keys
    assert _rows(calibration_eras.build(run).tex)[21][1:5] == ["2018-12", "2026-08", "--", "archive start"]


def test_eras_json_fallback_matches_the_flat_table(tmp_path):
    for build in calibration_eras.BUILDERS:
        flat = build(core.load_run(_write_run(tmp_path / f"flat_{build.__name__}")))
        nested = build(core.load_run(_write_run(tmp_path / f"nested_{build.__name__}", eras_json=True)))
        if build is calibration_eras.build:
            assert _rows(flat.tex) == _rows(nested.tex)
            assert [(n.key, n.value) for n in flat.numbers] == [(n.key, n.value) for n in nested.numbers]
        else:
            # peak_months lives only in tables/eras.csv; every other printed cell reads the era section and agrees
            assert not any(n.key.startswith("ch08.eras.peak_months.") for n in nested.numbers)
            flat_numbers = [(n.key, n.value) for n in flat.numbers if not n.key.startswith("ch08.eras.peak_months.")]
            assert flat_numbers == [(n.key, n.value) for n in nested.numbers]
            assert all(r[2] == "--" for r in _rows(nested.tex).values())
        assert sorted(p.name for p in nested.inputs[-4:]) == ["eras.json"] * 4


def test_inconsistent_eras_table_is_dashed_with_a_note(tmp_path):
    eras = [dict(r, first_month="2025-12") if r["channel"] == 35 and r["is_current"] else r for r in ERAS]
    run = core.load_run(_write_run(tmp_path, eras=eras))
    chapter = calibration_eras.build(run)
    r = _rows(chapter.tex)[35]
    assert r[1] == "2025-11" and r[5] == "unmatched 2022-09" and r[7] == "--" and r[9] == "--"
    assert any(n.startswith("ch35: the eras table's current era (2025-12..2026-08) disagrees") and
               n.endswith("record, earlier eras and coverage are dashed") for n in chapter.notes)
    ch_nums = _numbers(chapter)
    assert "ch08.eras.record_agreement.ch35" not in ch_nums and "ch08.eras.coverage.ch35" not in ch_nums
    ledger = calibration_eras.build_ledger(run)
    led = _rows(ledger.tex)[35]
    assert led[2] == "--"                                          # the located-month count comes from the eras table
    assert led[3:] == ["$0.00$", "$3" + DAGGER + "$", "none"]      # the era section's own columns survive
    assert any(n.startswith("ch35: the eras table's current era (2025-12..2026-08) disagrees") and
               n.endswith("the located-month count are dashed") for n in ledger.notes)
    led_nums = _numbers(ledger)
    assert "ch08.eras.peak_months.ch35" not in led_nums and led_nums["ch08.eras.current_peak_range_bins.ch35"].value == 3.0


def test_write_report_round_trip(tmp_path):
    run = core.load_run(_write_run(tmp_path))
    manifest = core.write_report(run, tmp_path / "out", list(calibration_eras.BUILDERS), commit="d" * 40,
                                 generated="2026-09-07T01:00:00+00:00")
    assert [a["label"] for a in manifest["artifacts"][:2]] == ["tab:calibration:eras", "tab:archive:calibration_eras"]
    assert (tmp_path / "out" / "tables" / "calibration_eras.tex").is_file()
    assert (tmp_path / "out" / "tables" / "calibration_eras_ledger.tex").is_file()
    docs = [json.loads((tmp_path / "out" / "numbers" / f"{name}.numbers.json").read_text())
            for name in ("calibration_eras", "calibration_eras_ledger")]
    for doc in docs:
        assert {i["path"] for i in doc["inputs"]} >= {str(tmp_path / "tables" / "eras.csv")}
    keys = [n["key"] for doc in docs for n in doc["numbers"]]
    assert len(keys) == len(set(keys))
    assert nb.load_numbers([tmp_path / "out" / "numbers" / "calibration_eras.numbers.json",
                            tmp_path / "out" / "numbers" / "calibration_eras_ledger.numbers.json"])


@pytest.mark.skipif(not (REAL / "ledger" / "run.json").is_file(), reason="the final archive run is not on this machine")
def test_real_run_renders_23_channels(tmp_path):
    run = core.load_run(REAL)
    frag = calibration_eras.build(run)
    rows = _rows(frag.tex)
    assert list(rows) == list(range(14, 37))
    nums = _numbers(frag)
    assert nums["ch08.eras.n_channels"].value == 23
    assert rows[30][6].startswith("yes") and nums["ch08.eras.stale_latest.ch30"].value == "yes"
    assert rows[19][5].startswith("confirmed 2024-12") and rows[29][7] == "--"
    assert nums["ch08.eras.n_channels_stale"].value == 5 and nums["ch08.eras.n_channels_record_confirmed"].value == 4

    ledger = calibration_eras.build_ledger(run)
    led = _rows(ledger.tex)
    assert list(led) == list(range(14, 37))
    led_nums = _numbers(ledger)
    # the drift columns: marked ranges on the slow-drift on channels, dashes on every proxy-low era
    assert led[15][3:] == ["$+0.29$", "$5" + DAGGER + "$", "none"]
    assert led[17][3:] == ["$+0.46$", "$8" + DAGGER + "$", "unconfirmed"]
    assert led[22][3:] == ["$-0.01$", "$2$", "none"] and led[14][3:] == ["--", "$0$", "unconfirmed"]
    assert all(led[ch][3:5] == ["--", "--"] for ch in (19, 20, 26, 27, 32))
    assert led_nums["ch08.eras.n_channels_peak_range_exceeds_half_width"].value == 5
    assert [ch for ch in led if DAGGER in led[ch][4]] == [15, 17, 24, 31, 35]
    assert led_nums["ch08.eras.n_channels_unconfirmed_instrument_change"].value == 8
    assert led_nums["ch08.eras.peak_months.ch15"].value == 16

    core.write_report(run, tmp_path, list(calibration_eras.BUILDERS), commit=run.commit, generated=run.generated)
    keys = []
    for name in ("calibration_eras", "calibration_eras_ledger"):
        doc = json.loads((tmp_path / "numbers" / f"{name}.numbers.json").read_text())
        keys += [n["key"] for n in doc["numbers"]]
    assert len(keys) == len(set(keys)) and len(keys) == len(frag.numbers) + len(ledger.numbers)
