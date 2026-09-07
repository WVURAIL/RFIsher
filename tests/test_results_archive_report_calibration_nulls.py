"""The calibration-nulls fragment (tab:calibration:nulls) from a synthetic ledger and from the real run."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rfisher_results.archive import numbers as nb
from rfisher_results.archive.report import calibration_nulls as cn
from rfisher_results.archive.report import core

REAL_RUN = Path("/home/djg/rail/results/archive_v5_2026-09-07")

# channel 29: bulk-read null, kept-half floor (probes agree), exchangeability at the diagnostic rank on 98 of 125 bulk
# bins (suspect anchor: the nominal window is excluded from the fine null)
NULL_29 = {
    "era": "2023-12..2026-08 (proxy-low)/calibration", "era_frames": 20218, "bulk_size": 125, "fine_bulk_size": 98,
    "null_source": "bulk of the mixture (declared)", "mixture_declared": True,
    "off_null_like": None, "off_check": "", "off_frames": 0,
    "kept_frames": 7830, "kept_width_factor": 1.3131372286146923, "kept_spread": 2.8096967201733154,
    "coarse_centre": 1.0011921, "coarse_centre_db": 0.005174325564534684, "coarse_core_sigma": 0.00314113905998092,
    "coarse_raw_width_factor": 1014.2838931472827, "coarse_core_width_factor": 1.5461820312487902,
    "coarse_tail_fraction": 0.18759559642980424, "coarse_tail_fraction_iid": 0.0013926869442404397,
    "fine_raw_width_factor": 20.94, "fine_core_width_factor": 1.1836748082534526,
    "floor_db": -46.66514022059937, "floor_evidence": "stated", "floor_frames": 7830, "floor_basis": "kept half about mu_0",
    "floor_population": "no verified off era; sigma-implied substitute: kept half about mu_0, 7830 frames",
    "floor_stated_kept_half_db": -46.66514022059937, "floor_stated_bulk_db": -45.95038651622138,
    "exch_rho": 4, "exch_measured": 0.9706670637284097, "exch_predicted": 0.9682539682539683, "exch_frames": 6716,
    "exch_trials": 33580, "exchangeability_rank_basis": "diagnostic point",
    "notes": "coarse null read from the bulk of the block's mixture: centre = median, scale = left side; fine null read on "
             "98 of 125 bulk bins: the nominal window is excluded because the anchor is suspect (the bulk may carry the pilot)",
}
# channel 35: verified off era (null-like), measured p90 floor, no kept frame, a diagnostic rank existed but the
# evaluation block had no quiet frame so the exchangeability check was skipped
NULL_35 = {
    "era": "2024-12..2026-04 (proxy-low)/calibration", "era_frames": 6152, "bulk_size": 126, "fine_bulk_size": 126,
    "null_source": "verified transmitter-off era", "mixture_declared": False,
    "off_null_like": True, "off_check": "centre 0.9993, core width factor 1.55", "off_frames": 11199,
    "kept_frames": 0, "kept_width_factor": None, "kept_spread": None,
    "coarse_centre": 0.9992886252178975, "coarse_centre_db": -0.0030905608282191846, "coarse_core_sigma": 0.0037114927209636393,
    "coarse_raw_width_factor": 616.182982308569, "coarse_core_width_factor": 1.5515706794781001,
    "coarse_tail_fraction": 0.18108759710688455, "coarse_tail_fraction_iid": 0.0013926869442404397,
    "fine_raw_width_factor": 517.6086802283669, "fine_core_width_factor": 6.33023211989892,
    "floor_db": -28.43558259109515, "floor_evidence": "measured", "floor_frames": 4954, "floor_basis": "off era p90",
    "floor_population": "verified off era: 4954 frames with a shelf estimate of 11199",
    "floor_stated_kept_half_db": None, "floor_stated_bulk_db": -45.94052572198811,
    "exchangeability_rank_basis": "diagnostic point", "notes": "exchangeability skipped: 0 quiet frames < 30",
}
# channel 20: a recorded off population that fails the null-like check (measured floor kept); 34 kept frames; the
# exchangeability check on 35 quiet frames
NULL_20 = {
    "era": "2023-01..2026-08 (proxy-low)/calibration", "era_frames": 10581, "bulk_size": 125, "fine_bulk_size": 125,
    "null_source": "verified transmitter-off era (not null-like)", "mixture_declared": False,
    "off_null_like": False, "off_check": "centre 1.1003 is more than 0.02 from mu_0; core width factor 17.6 exceeds 5",
    "off_frames": 10581, "kept_frames": 34, "kept_width_factor": 10.569119205867683, "kept_spread": 1.3592894190157436,
    "coarse_centre": 1.1002746072531129, "coarse_centre_db": 0.4150109018634618, "coarse_core_sigma": 0.04216045111599075,
    "coarse_raw_width_factor": 998.4351805620439, "coarse_core_width_factor": 17.62496243510263,
    "coarse_tail_fraction": 0.1442207730838295, "coarse_tail_fraction_iid": 0.0013926869442404397,
    "fine_raw_width_factor": 340.1946472179619, "fine_core_width_factor": 1.350812740212089,
    "floor_db": -26.921849764424312, "floor_evidence": "measured", "floor_frames": 10547, "floor_basis": "off era p90",
    "floor_population": "verified off era: 10547 frames with a shelf estimate of 10581",
    "exch_rho": 2, "exch_measured": 0.9942857142857143, "exch_predicted": 0.9841269841269841, "exch_frames": 35,
    "exch_trials": 175, "exchangeability_rank_basis": "diagnostic point",
    "notes": "recorded off population is not null-like (centre 1.1003 is more than 0.02 from mu_0; core width factor 17.6 "
             "exceeds 5): a carrier persists after the record",
}
# channel 14: bulk-read null whose kept-half probes disagree (spread 7.8): the floor is the bulk's left side (not H0)
NULL_14 = {
    "era": "2018-12..2026-08 (proxy-low)/calibration", "era_frames": 18032, "bulk_size": 125, "fine_bulk_size": 125,
    "null_source": "bulk of the mixture (declared)", "mixture_declared": True, "off_null_like": None, "off_frames": 0,
    "kept_frames": 1228, "kept_width_factor": 1.2315074054145856, "kept_spread": 7.757789800534923,
    "coarse_centre": 1.0137151502440844, "coarse_centre_db": 0.05915937190265238, "coarse_core_sigma": 0.008258689103759742,
    "coarse_raw_width_factor": 2391.678842724929, "coarse_core_width_factor": 3.452503029829981,
    "coarse_tail_fraction": 0.3812111801242236, "coarse_tail_fraction_iid": 0.0013926869442404397,
    "fine_raw_width_factor": 725.7221113571372, "fine_core_width_factor": 1.311536397047547,
    "floor_db": -42.4669006782741, "floor_evidence": "stated", "floor_frames": 18032, "floor_basis": "bulk left side (not H0)",
    "floor_population": "no verified off era; sigma-implied substitute: bulk left-side scale about its median "
                        "(kept-half probes disagree (spread 7.8))",
    "exch_rho": 1, "exch_measured": 0.9956666666666667, "exch_predicted": 0.9920634920634921, "exch_frames": 600,
    "exch_trials": 3000, "exchangeability_rank_basis": "selected point",     # the no-dagger branch
    "notes": "coarse null read from the bulk of the block's mixture: centre = median, scale = left side",
}
# channel 15: the bulk centre is 1.31, beyond 0.1 of mu_0: no null population, the floor refused, no rank at all
NULL_15 = {
    "era": "2025-05..2026-08 (proxy-high)/calibration", "era_frames": 7748, "bulk_size": 125, "fine_bulk_size": 125,
    "null_source": "bulk of the mixture (declared)", "mixture_declared": True, "off_null_like": None, "off_frames": 0,
    "kept_frames": 4, "kept_width_factor": None, "kept_spread": None,
    "coarse_centre": 1.3101236443208149, "coarse_centre_db": 1.1731228459642349, "coarse_core_sigma": 0.09315950368193705,
    "coarse_raw_width_factor": 1541.1475521813597, "coarse_core_width_factor": 38.94485731069866,
    "coarse_tail_fraction": 0.16894682498709343, "coarse_tail_fraction_iid": 0.0013926869442404397,
    "fine_raw_width_factor": 533.3175529152539, "fine_core_width_factor": 1.4996239692811741,
    "floor_db": None, "floor_evidence": "refused", "floor_frames": 0, "floor_basis": "none",
    "floor_population": "no off era; bulk centre 1.31 is beyond 0.1 of mu_0: the block carries no null population",
    "floor_stated_kept_half_db": None, "floor_stated_bulk_db": -31.94374019228788,
    "exchangeability_rank_basis": "",
    "notes": "coarse null read from the bulk of the block's mixture: centre = median, scale = left side",
}


def _ledger(tmp_path, records):
    ledger = tmp_path / "ledger"
    (ledger / "channels").mkdir(parents=True)
    files = []
    for ch, fid, null in records:
        rel = f"channels/ch{ch:02d}_fid{fid}.json"
        rec = {"channel": ch, "freq_id": fid, "product": f"{fid}.npz", "product_sha256": "b" * 64, "notes": [],
               "sections": {"era": {"current_first_month": "2023-12"}, "selection": None, "null": null}}
        (ledger / rel).write_text(json.dumps(rec))
        files.append(rel)
    run = {"schema": {"name": "rfisher-archive-ledger", "version": 1}, "generated": "2026-09-07T00:00:00+00:00",
           "producer": {"commit": "a" * 40}, "products": {}, "channels": files, "era_config_digest": "c" * 64}
    (ledger / "run.json").write_text(json.dumps(run))
    return core.load_run(tmp_path)


def _rows(frag):
    lines = frag.tex.splitlines()
    body = lines[lines.index(r"\midrule") + 1:lines.index(r"\bottomrule")]
    return [[cell.strip() for cell in line[:-2].split(" & ")] for line in body]


def _numbers(frag):
    return {n.key: n for n in frag.numbers}


COL = {name: i for i, name in enumerate(
    ("ch", "N", "bulk", "source", "off", "centre", "sigma", "wc_raw", "wc_core", "wf_raw", "wf_core", "kept", "spread",
     "tail", "iid", "exch", "rho", "floor", "basis", "plate"))}


def test_cell_helpers():
    assert cn.source_text("verified transmitter-off era", False) == "off era"
    assert cn.source_text("verified transmitter-off era (not null-like)", False) == "off era (not null-like)"
    assert cn.source_text("bulk of the mixture (declared)", True) == "bulk (mixture)"
    assert cn.source_text("recorded off epoch, not null-like; bulk of the mixture (declared)", True) == "off epoch not null-like; bulk (mixture)"
    assert cn.source_text("reference-bin surrogate", True) == "reference surrogate (mixture)"
    assert cn.source_text("", True) == core.DASH and cn.source_text(None, False) == core.DASH
    assert cn.off_null_like_text(True) == "yes" and cn.off_null_like_text(False) == "no"
    assert cn.off_null_like_text(None) == core.DASH and cn.off_null_like_text("") == core.DASH
    assert cn.off_null_like_text("True") == "yes" and cn.off_null_like_text("False") == "no"
    assert cn.width_factor(1012.28) == ("1{,}012", 0) and cn.width_factor(1.5461) == ("1.55", 2)
    assert cn.width_factor(None) == (core.DASH, None) and cn.width_factor(float("nan")) == (core.DASH, None)
    assert len(cn.HEADER) == len(COL) == len(cn.ALIGN)


def test_floor_basis_is_read_or_inferred():
    assert cn.floor_basis(NULL_29) == "kept half about mu_0" and cn.floor_basis(NULL_15) == "none"
    # an older ledger without floor_basis: inferred from the population text
    assert cn.floor_basis({"floor_evidence": "measured", "floor_population": "verified off era: 4954 frames"}) == "off era p90"
    assert cn.floor_basis({"floor_evidence": "stated", "floor_population": "no verified off era; sigma-implied substitute (kept half about mu_0, 7893 frames)"}) == "kept half about mu_0"
    assert cn.floor_basis({"floor_evidence": "stated", "floor_population": "no verified off era; sigma-implied substitute (bulk core width)"}) == "bulk left side (not H0)"
    assert cn.floor_basis({"floor_evidence": "refused", "floor_population": "no off era"}) == "none"
    assert cn.floor_basis({}) == ""


def test_every_column_on_a_synthetic_ledger(tmp_path):
    run = _ledger(tmp_path, [(20, 752, NULL_20), (29, 614, NULL_29), (35, 521, NULL_35), (17, 798, None),
                             (14, 844, NULL_14), (15, 829, NULL_15)])
    frag = cn.build(run)
    assert frag.name == "calibration_nulls" and frag.label == "tab:calibration:nulls"
    rows = _rows(frag)
    assert [r[0] for r in rows] == ["14", "15", "17", "20", "29", "35"] and all(len(r) == len(cn.HEADER) for r in rows)
    r14, r15, r17, r20, r29, r35 = rows
    # a channel without a null section: every cell but the channel and the plate is the dash
    assert r17[1:-1] == [core.DASH] * (len(cn.HEADER) - 2) and r17[-1] == r"Fig.~\ref{fig:archive:plate:ch17}"
    # channel 29: every column populated; the fine bulk is smaller, the rank is daggered, the floor from the kept half
    assert r29 == ["29", "$20{,}218$", "$125$ ($98$)", "bulk (mixture)", core.DASH, "$1.0012$", "$0.00314$", "$1{,}014$",
                   "$1.55$", "$20.94$", "$1.18$", "$1.31$ ($7{,}830$)", "$2.8$", "$18.76$", "$0.14$",
                   "$0.971$ / $0.968$", r"$4^\dagger$ ($6{,}716$)", "$-46.7$",
                   r"stated: kept half about $\mu_0$ ($7{,}830$)", r"Fig.~\ref{fig:archive:plate:ch29}"]
    # channel 35: off era, null-like, measured p90 floor, no kept frame (0 printed), exchangeability skipped
    assert r35[COL["source"]] == "off era" and r35[COL["off"]] == "yes" and r35[COL["centre"]] == "$0.9993$"
    assert r35[COL["kept"]] == "-- ($0$)" and r35[COL["spread"]] == core.DASH
    assert r35[COL["exch"]] == core.DASH and r35[COL["rho"]] == core.DASH
    assert r35[COL["floor"]] == "$-28.4$" and r35[COL["basis"]] == "measured: off era p90 ($4{,}954$)"
    # channel 20: the off population fails the null-like check; the measured floor is kept; 35 quiet frames tested
    assert r20[COL["source"]] == "off era (not null-like)" and r20[COL["off"]] == "no"
    assert r20[COL["kept"]] == "$10.57$ ($34$)" and r20[COL["spread"]] == "$1.4$"
    assert r20[COL["wc_core"]] == "$17.62$" and r20[COL["wf_raw"]] == "$340$"
    assert r20[COL["exch"]] == "$0.994$ / $0.984$" and r20[COL["rho"]] == r"$2^\dagger$ ($35$)"
    assert r20[COL["floor"]] == "$-26.9$" and r20[COL["basis"]] == "measured: off era p90 ($10{,}547$)"
    # channel 14: probes disagree (spread 7.8): floor from the bulk's left side; a selected rank carries no dagger
    assert r14[COL["spread"]] == "$7.8$" and r14[COL["basis"]] == r"stated: bulk left side, not $H_0$ ($18{,}032$)"
    assert r14[COL["rho"]] == "$1$ ($600$)" and r14[COL["bulk"]] == "$125$"
    # channel 15: the floor refused (no null population), no rank, too few kept frames
    assert r15[COL["floor"]] == core.DASH and r15[COL["basis"]] == "refused"
    assert r15[COL["kept"]] == "-- ($4$)" and r15[COL["spread"]] == core.DASH
    assert r15[COL["exch"]] == core.DASH and r15[COL["rho"]] == core.DASH and r15[COL["off"]] == core.DASH

    num = _numbers(frag)
    assert len(num) == len(frag.numbers)                  # no duplicate keys
    assert num["ch08.nulls.era_frames.ch29"].value == 20218 and num["ch08.nulls.era_frames.ch29"].kind == "int"
    assert num["ch08.nulls.fine_bulk_size.ch29"].value == 98 and "ch08.nulls.fine_bulk_size.ch14" not in num
    assert num["ch08.nulls.coarse_centre.ch29"].precision == 4 and num["ch08.nulls.coarse_core_sigma.ch29"].renderings == ("0.00314",)
    assert num["ch08.nulls.coarse_raw_width_factor.ch29"].precision == 0 and num["ch08.nulls.coarse_core_width_factor.ch29"].precision == 2
    assert abs(num["ch08.nulls.coarse_tail_fraction_pct.ch29"].value - 18.7596) < 1e-3
    assert num["ch08.nulls.kept_spread.ch29"].precision == 1 and abs(num["ch08.nulls.kept_spread.ch29"].value - 2.8097) < 1e-4
    assert num["ch08.nulls.exch_rho.ch29"].value == 4 and num["ch08.nulls.exch_measured.ch29"].precision == 3
    assert num["ch08.nulls.exch_frames.ch29"].value == 6716 and num["ch08.nulls.exch_rank_basis.ch29"].value == "diagnostic point"
    assert num["ch08.nulls.exch_rank_basis.ch14"].value == "selected point"
    assert num["ch08.nulls.null_source.ch20"].kind == "text" and num["ch08.nulls.null_source.ch20"].value == "off era (not null-like)"
    assert num["ch08.nulls.off_null_like.ch20"].value == "no" and num["ch08.nulls.off_null_like.ch35"].value == "yes"
    assert num["ch08.nulls.floor_db.ch35"].status == "measured" and num["ch08.nulls.floor_db.ch29"].status == "derived"
    assert num["ch08.nulls.floor_evidence.ch35"].value == "measured" and num["ch08.nulls.floor_basis.ch35"].value == "off era p90"
    assert num["ch08.nulls.floor_basis.ch29"].value == "kept half about mu_0" and num["ch08.nulls.floor_frames.ch29"].value == 7830
    assert num["ch08.nulls.floor_basis.ch14"].value == "bulk left side (not H0)" and num["ch08.nulls.floor_frames.ch14"].value == 18032
    assert num["ch08.nulls.floor_basis.ch14"].renderings == ("bulk left side, not H0",)
    assert num["ch08.nulls.floor_evidence.ch15"].value == "refused" and num["ch08.nulls.floor_evidence.ch15"].status == "refused"
    assert num["ch08.nulls.plate.ch35"].value == "fig:archive:plate:ch35" and num["ch08.nulls.plate.ch35"].kind == "text"
    assert num["ch08.nulls.kept_frames.ch20"].value == 34 and num["ch08.nulls.kept_frames.ch35"].value == 0
    # absent values add no number
    for key in ("ch08.nulls.kept_width_factor.ch35", "ch08.nulls.kept_spread.ch35", "ch08.nulls.exch_measured.ch35",
                "ch08.nulls.exch_rho.ch35", "ch08.nulls.exch_rank_basis.ch35", "ch08.nulls.off_null_like.ch29",
                "ch08.nulls.floor_db.ch15", "ch08.nulls.floor_basis.ch15", "ch08.nulls.floor_frames.ch15",
                "ch08.nulls.era_frames.ch17", "ch08.nulls.floor_evidence.ch17"):
        assert key not in num
    assert num["ch08.nulls.floor_db.ch29"].source == {"table": "calibration_nulls.tex", "row": {"channel": 29}, "column": "floor_db"}

    # the ch05 sentence: 14, 29 and 35 lie within 0.1 dB of mu_0; 15 and 20 do not; 17 has no centre
    assert num["ch05.nulls.channels"].value == 5 and num["ch05.nulls.within_0p1db_count"].value == 3
    assert abs(num["ch05.nulls.within_0p1db_fraction"].value - 3 / 5) < 1e-12 and "3/5" in num["ch05.nulls.within_0p1db_fraction"].renderings
    assert num["ch05.nulls.within_0p1db_channels"].value == "14, 29, 35"
    assert num["ch05.nulls.coarse_core_width_factor_range"].value == "1.55--3.45" and num["ch05.nulls.coarse_core_width_factor_range"].kind == "range"
    assert abs(num["ch05.nulls.coarse_core_width_factor_high"].value - 3.4525) < 1e-4
    assert num["ch05.nulls.fine_core_width_factor_range"].value == "1.18--6.33" and "1.18-6.33x" in num["ch05.nulls.fine_core_width_factor_range"].renderings
    assert num["ch05.nulls.fine_core_width_factor_all_range"].value == "1.18--6.33"

    notes = "\n".join(frag.notes)
    assert "no null section (every cell dashed): channels 17" in notes
    assert "no rank to test at" in notes and "on channels 15" in notes and "selector status" in notes
    assert "too few quiet frames (exchangeability skipped: 0 quiet frames < 30) on channels 35" in notes
    assert "the dagger marks the rank of the least-residual diagnostic point" in notes and "on channels 20, 29;" in notes
    assert "kept-half width factor and spread dashed" in notes and "channels 15, 35" in notes
    assert "off null-like dashed" in notes and "channels 14, 15, 29" in notes
    assert "off population not null-like" in notes and "kept on channels 20" in notes
    assert "floor dashed and basis 'refused'" in notes and "on channels 15" in notes
    assert "the block carries no null population" in notes      # the producer's own floor_population, not an inference
    assert "bulk's left-side scale" in notes and "on channels 14" in notes
    assert "kept half about mu_0 (the register's convention) on channels 29" in notes
    assert "fine null read on fewer bulk bins" in notes and "suspect anchor: channels 29" in notes


def test_sentence_numbers_when_no_channel_is_near_mu0(tmp_path):
    run = _ledger(tmp_path, [(20, 752, NULL_20)])
    frag = cn.build(run)
    num = _numbers(frag)
    assert num["ch05.nulls.within_0p1db_count"].value == 0 and num["ch05.nulls.within_0p1db_fraction"].value == 0.0
    assert "ch05.nulls.coarse_core_width_factor_range" not in num and "ch05.nulls.fine_core_width_factor_all_range" in num
    assert any("no channel within 0.1 dB" in n for n in frag.notes)
    run = _ledger(tmp_path / "empty", [(17, 798, None)])
    frag = cn.build(run)
    num = _numbers(frag)
    assert num["ch05.nulls.channels"].value == 0 and "ch05.nulls.within_0p1db_count" not in num
    assert any("no channel carries a coarse centre" in n for n in frag.notes)


def test_a_stated_floor_without_a_value_prints_as_its_evidence(tmp_path):
    null = dict(NULL_14, floor_db=None, floor_evidence="stated", floor_basis="none")
    frag = cn.build(_ledger(tmp_path, [(14, 844, null)]))
    row = _rows(frag)[0]
    assert row[COL["floor"]] == core.DASH and row[COL["basis"]] == "stated"
    num = _numbers(frag)
    assert num["ch08.nulls.floor_evidence.ch14"].status == "refused" and "ch08.nulls.floor_db.ch14" not in num
    assert any("floor dashed" in n and "channels 14" in n for n in frag.notes)


def test_write_report_round_trip(tmp_path):
    run = _ledger(tmp_path, [(29, 614, NULL_29), (35, 521, NULL_35)])
    manifest = core.write_report(run, tmp_path / "out", [cn.build], commit="d" * 40, generated="2026-09-07T01:00:00+00:00")
    assert manifest["artifacts"][0]["label"] == "tab:calibration:nulls" and manifest["artifacts"][0]["count"] == len(cn.build(run).numbers)
    assert (tmp_path / "out" / "tables" / "calibration_nulls.tex").read_text().startswith(r"\begin{tabular}{" + cn.ALIGN + "}")
    loaded = nb.load_numbers([tmp_path / "out" / "numbers" / "calibration_nulls.numbers.json"])
    assert {n.key for n in loaded} >= {"ch08.nulls.floor_db.ch29", "ch08.nulls.exch_rho.ch29", "ch08.nulls.floor_basis.ch35",
                                       "ch08.nulls.kept_spread.ch29", "ch05.nulls.within_0p1db_fraction"}


@pytest.mark.skipif(not (REAL_RUN / "ledger" / "run.json").is_file(), reason="the archive_v5_2026-09-07 run is not on this machine")
def test_real_run_renders_23_rows_without_duplicate_keys():
    run = core.load_run(REAL_RUN)
    frag = cn.build(run)
    rows = _rows(frag)
    assert len(rows) == 23 and [r[0] for r in rows] == [str(ch) for ch in range(14, 37)]
    doc = nb.NumbersDocument.new(frag.name, repository="x", commit="y", script="z", generated="w")
    for number in frag.numbers:
        doc.add(number)                                   # raises on a duplicate key
    num = _numbers(frag)
    by_ch = {int(r[0]): r for r in rows}

    def channels(column, predicate):
        return {ch for ch, r in by_ch.items() if predicate(r[COL[column]])}

    # floors: measured on the six off-era channels, refused where the bulk is the carrier, stated elsewhere
    assert channels("basis", lambda s: s.startswith("measured")) == {19, 20, 26, 27, 32, 35}
    assert channels("basis", lambda s: s == "refused") == {15, 17, 22, 24, 28, 30, 31, 36}
    assert channels("floor", lambda s: s == core.DASH) == {15, 17, 22, 24, 28, 30, 31, 36}
    assert channels("basis", lambda s: "kept half" in s) == {21, 29}
    assert channels("basis", lambda s: "bulk left side" in s) == {14, 16, 18, 23, 25, 33, 34}
    # the off population: null-like on four channels, not on two, absent on the rest
    assert channels("off", lambda s: s == "yes") == {19, 26, 32, 35} and channels("off", lambda s: s == "no") == {20, 27}
    # the exchangeability check: at the diagnostic rank (daggered) on 14 channels, dashed on the other nine
    with_exch = channels("exch", lambda s: s != core.DASH)
    assert with_exch == {14, 16, 18, 19, 20, 21, 23, 25, 26, 27, 29, 32, 33, 34}
    assert channels("rho", lambda s: r"^\dagger" in s) == with_exch
    assert all(num[f"ch08.nulls.exch_rank_basis.ch{ch:02d}"].value == "diagnostic point" for ch in with_exch)
    # the fine null on fewer bulk bins where the anchor is suspect
    assert channels("bulk", lambda s: "(" in s) == {21, 23, 25, 29, 33}
    assert num["ch05.nulls.channels"].value == 23 and num["ch05.nulls.within_0p1db_count"].value == 11
