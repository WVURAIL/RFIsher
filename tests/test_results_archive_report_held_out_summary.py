"""The ch06 held-out summary fragment: every column on a synthetic ledger, and the real run when present."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from rfisher_results.archive.report import core
from rfisher_results.archive.report import held_out_summary as hos

REAL_RUN = Path(os.environ.get("RFISHER_ARCHIVE_RESULTS", "/home/djg/rail/results/archive_v5_2026-09-07"))

_REFUSAL_FRAMES = "within-era stability refused_insufficient_support: candidate rho=1, eta=1.07129 retains fewer than 30 frames in one era half"
_REFUSAL_DAYS = "within-era stability refused_insufficient_support: early half spans 166.924 days; need 270"
_REFUSAL_MONTHS = "within-era stability refused_insufficient_support: early half has 3 observed months; need 6"
_REFUSAL_FLOOR = "no floor for frames without a shelf estimate"
_DIAGNOSTIC_BASIS = "least residual on the calibration surface (no feasible point)"
_NO_OFF = "not measurable: no verified off state in this block"
_OFF = "verified off era: every frame is null"
_CAP = 2054312.002658844


def _selection(**over):
    """A feasible selection with bootstrap intervals; override to make the other cases."""
    base = {"status": "feasible", "refusal": "", "claim_status": "screening", "rho": 3, "q_rho": 0.0238, "eta_q16": 70407,
            "eta": 1.0743255615234375, "masked_fraction_calibration": 0.412, "r_sys_calibration": 0.0101, "R_calibration": 0.84,
            "r_tol": 0.012, "floor_db": -40.0, "floor_evidence": "stated", "chain_gain": 300.0, "gain_basis": "era chain",
            "diagnostic_basis": "", "diagnostic_rho": None, "diagnostic_eta_q16": None, "diagnostic_eta": None,
            "diagnostic_masked_fraction": None, "diagnostic_r_sys": None, "diagnostic_R": None,
            "masked_fraction_evaluation": 0.4321, "masked_fraction_evaluation_q16": 0.401, "masked_fraction_evaluation_q84": 0.462,
            "r_sys_evaluation": 0.0105, "r_sys_evaluation_q16": 0.0101, "r_sys_evaluation_q84": 0.0122,
            "bootstrap_blocks_evaluation": 40, "kept_evaluation": 5000, "R_evaluation": 0.8713,
            "false_alarm_rate": None, "false_alarm_basis": _NO_OFF, "surface_points": 1000, "feasible_points": 12}
    base.update(over)
    return base


def _diagnostic(rho, eta_q16, eta, f_cal, refusal, **over):
    """The drift screen refused: no selected point, the least-residual point replayed as a diagnostic."""
    return _selection(status="no feasible point", refusal=refusal, claim_status="diagnostic", rho=None, q_rho=None,
                      eta_q16=None, eta=None, masked_fraction_calibration=None, r_sys_calibration=None, R_calibration=None,
                      diagnostic_basis=_DIAGNOSTIC_BASIS, diagnostic_rho=rho, diagnostic_eta_q16=eta_q16, diagnostic_eta=eta,
                      diagnostic_masked_fraction=f_cal, feasible_points=0, **over)


def _blocks(flag, finite=1.0):
    return {"status": "supported", "evaluation_flag_rate": flag, "calibration_flag_rate": flag,
            "calibration_finite_estimate_rate": finite, "evaluation_finite_estimate_rate": finite}


def _ledger(tmp_path):
    ledger = tmp_path / "ledger"
    (ledger / "channels").mkdir(parents=True)
    records = {
        # a feasible selection with bootstrap intervals, no off state, tau_c measured
        33: {"selection": _selection(), "screening": {"screening_class": "recovery candidate", "off_era_current": False},
             "blocks": _blocks(0.7), "chain": {"tau_quality": "measured"}},
        # a feasible selection replayed on a verified off era: P_fa and the flag's rate, too few blocks for an interval, tau_c bounded
        26: {"selection": _selection(rho=1, eta_q16=65536, eta=1.0, masked_fraction_calibration=0.05, floor_db=-50.0,
                                     chain_gain=2000.0, masked_fraction_evaluation=0.0312, masked_fraction_evaluation_q16=None,
                                     masked_fraction_evaluation_q84=None, r_sys_evaluation=2.5e-5, r_sys_evaluation_q16=None,
                                     r_sys_evaluation_q84=None, bootstrap_blocks_evaluation=0, kept_evaluation=900,
                                     R_evaluation=0.0021, false_alarm_rate=0.0312, false_alarm_basis=_OFF),
             "screening": {"screening_class": "off-era", "off_era_current": True}, "blocks": _blocks(0.0456),
             "chain": {"tau_quality": "bounded_above"}},
        # the diagnostic point on an off era: P_fa measured, the gain at the sidereal cap, kept frames at the floor
        19: {"selection": _diagnostic(1, 73060, 1.11480712890625, 0.8679683867968386, _REFUSAL_DAYS, floor_db=-32.6,
                                      floor_evidence="measured", chain_gain=_CAP, masked_fraction_evaluation=0.8103,
                                      masked_fraction_evaluation_q16=0.8024, masked_fraction_evaluation_q84=0.8176,
                                      r_sys_evaluation=1129.78, r_sys_evaluation_q16=1126.45, r_sys_evaluation_q84=1132.72,
                                      bootstrap_blocks_evaluation=1193, kept_evaluation=1223, R_evaluation=94148.43,
                                      false_alarm_rate=0.8103, false_alarm_basis=_OFF),
             "screening": {"screening_class": "off-era", "off_era_current": True}, "blocks": _blocks(0.8787),
             "chain": {"tau_quality": "refused"}, "chain_archive": {"tau_quality": "refused"}},
        # the diagnostic point under the archive-wide gain (era chain refused, archive chain bounded), R rounding into the next decade
        35: {"selection": _diagnostic(1, 20154270, 307.5297546386719, 0.9237646, _REFUSAL_MONTHS, floor_db=-28.4, chain_gain=440.36,
                                      gain_basis="archive-wide chain (era chain refused)", masked_fraction_evaluation=0.8815189048239895,
                                      masked_fraction_evaluation_q16=0.8733, masked_fraction_evaluation_q84=0.8898,
                                      r_sys_evaluation=35.1958, r_sys_evaluation_q16=34.4908, r_sys_evaluation_q84=35.8859,
                                      bootstrap_blocks_evaluation=722, kept_evaluation=727, R_evaluation=999.88),
             "screening": {"screening_class": "occupancy-wall excision candidate", "off_era_current": False}, "blocks": _blocks(1.0),
             "chain": {"tau_quality": "refused"}, "chain_archive": {"tau_quality": "bounded_above"}},
        # the diagnostic point whose replay kept no frame; the floor is refused but every frame carries a shelf estimate
        31: {"selection": _diagnostic(115, 67987, 1.0374, 0.994, _REFUSAL_FRAMES, floor_db=None, floor_evidence="refused",
                                      chain_gain=344.1, masked_fraction_evaluation=1.0, masked_fraction_evaluation_q16=1.0,
                                      masked_fraction_evaluation_q84=1.0, r_sys_evaluation=None, r_sys_evaluation_q16=None,
                                      r_sys_evaluation_q84=None, bootstrap_blocks_evaluation=807, kept_evaluation=0, R_evaluation=None),
             "screening": {"screening_class": "occupancy-wall excision candidate", "off_era_current": False}, "blocks": _blocks(1.0),
             "chain": {"tau_quality": "measured"}},
        # the selector refused outright: no floor, frames without a shelf estimate, no point, no replay
        15: {"selection": _selection(status="refused", refusal=_REFUSAL_FLOOR, claim_status="", rho=None, q_rho=None, eta_q16=None,
                                     eta=None, masked_fraction_calibration=None, floor_db=None, floor_evidence="refused",
                                     chain_gain=_CAP, masked_fraction_evaluation=None, masked_fraction_evaluation_q16=None,
                                     masked_fraction_evaluation_q84=None, r_sys_evaluation=None, r_sys_evaluation_q16=None,
                                     r_sys_evaluation_q84=None, bootstrap_blocks_evaluation=0, kept_evaluation=0,
                                     R_evaluation=None, false_alarm_basis="", surface_points=0, feasible_points=0),
             "screening": {"screening_class": "occupancy-wall excision candidate", "off_era_current": False},
             "blocks": _blocks(0.9974, finite=0.9995), "chain": {"tau_quality": "refused"}},
        # no selection, screening, blocks or chain section: every cell dashed
        14: {"selection": None, "screening": None, "blocks": None, "chain": None},
        # the diagnostic point on an off era that was not replayed: P_fa dashed, the flag's rate stands alone
        20: {"selection": _diagnostic(2, 85406, 1.303192138671875, 0.9434, _REFUSAL_FRAMES.replace("1.07129", "1.14157"),
                                      floor_db=-26.9, floor_evidence="measured", chain_gain=_CAP, masked_fraction_evaluation=None,
                                      masked_fraction_evaluation_q16=None, masked_fraction_evaluation_q84=None, r_sys_evaluation=None,
                                      r_sys_evaluation_q16=None, r_sys_evaluation_q84=None, bootstrap_blocks_evaluation=0,
                                      kept_evaluation=0, R_evaluation=None, false_alarm_basis=""),
             "screening": {"screening_class": "off-era", "off_era_current": True}, "blocks": _blocks(0.9967),
             "chain": {"tau_quality": "refused"}},
    }
    run = {"schema": {"name": "rfisher-archive-ledger", "version": 1}, "generated": "2026-09-07T00:00:00+00:00",
           "producer": {"commit": "a" * 40}, "products": {}, "era_config_digest": "c" * 64,
           "channels": [f"channels/ch{ch}_fid{900 - ch}.json" for ch in sorted(records)]}
    (ledger / "run.json").write_text(json.dumps(run))
    for ch, sections in records.items():
        rec = {"channel": ch, "freq_id": 900 - ch, "product": f"{900 - ch}.npz", "product_sha256": "b" * 64, "notes": [],
               "sections": sections}
        (ledger / "channels" / f"ch{ch}_fid{900 - ch}.json").write_text(json.dumps(rec))
    return tmp_path


def _rows(frag):
    lines = frag.tex.splitlines()
    body = lines[lines.index(r"\midrule") + 1:lines.index(r"\bottomrule")]
    return {int(line.split(" & ")[0]): [c.strip() for c in line.rstrip(" \\").split(" & ")] for line in body}


def _numbers(frag, ch):
    return {n.key.split(".")[2]: n for n in frag.numbers if n.source["row"].get("channel") == ch}


PER_CHANNEL = 21
COUNTS = 10


def test_header_and_shape(tmp_path):
    frag = hos.build(core.load_run(_ledger(tmp_path)))
    assert frag.name == "held_out_summary" and frag.label == "tab:detection:heldout"
    assert frag.tex.startswith(r"\begin{tabular}{lrrrrrrrrlll}")
    header = frag.tex.splitlines()[2].rstrip(" \\").split(" & ")
    assert header == list(hos.HEADER) and len(hos.COLUMNS) == len(hos.HEADER) == len(hos.ALIGN) == 12
    rows = _rows(frag)
    assert sorted(rows) == [14, 15, 19, 20, 26, 31, 33, 35] and all(len(r) == 12 for r in rows.values())
    assert len(frag.inputs) == 9


def test_feasible_row_prints_the_selected_point_and_intervals(tmp_path):
    frag = hos.build(core.load_run(_ledger(tmp_path)))
    r = _rows(frag)[33]
    assert r[1] == "$3$" and r[2] == r"$1.0743\ (70{,}407)$" and r[3] == "$0.412$"
    assert r[4] == r"$0.432\ [0.401, 0.462]$" and r[5] == r"$0.0105\ [0.0101, 0.0122]$" and r[6] == "$0.871$"
    assert r[7:] == ["--", "--", "feasible", "screening", "--"]
    n = _numbers(frag, 33)
    assert len(n) == PER_CHANNEL
    assert n["point_basis"].value == "selected" and n["rho"].value == 3 and n["rho"].kind == "int" and n["rho"].renderings == ("3",)
    assert n["eta_q16"].value == 70407 and n["eta_q16"].renderings == ("70407",) and n["eta_q16"].status == "measured"
    assert n["eta"].value == 1.0743255615234375 and n["eta"].precision == 4
    assert n["masked_fraction_calibration"].value == 0.412 and n["masked_fraction_calibration"].precision == 3
    assert n["masked_fraction_evaluation"].precision == 3 and n["masked_fraction_evaluation_q84"].value == 0.462
    assert n["r_sys_evaluation"].precision == 4 and n["r_sys_evaluation"].status == "measured"
    assert n["r_sys_evaluation_q16"].value == 0.0101 and n["r_sys_evaluation_q84"].precision == 4
    assert n["R"].value == 0.8713 and n["R"].precision == 3 and n["R"].status == "measured"
    assert n["kept_evaluation"].value == 5000 and n["kept_evaluation"].kind == "int"
    assert n["gain_basis"].value == "era chain" and n["tau_quality"].value == "measured"
    assert n["false_alarm_rate"].value is None and n["false_alarm_rate"].status == "refused"
    assert n["false_alarm_rate_flag"].value is None and n["false_alarm_rate_flag"].status == "refused"
    assert n["false_alarm_basis"].value == _NO_OFF
    assert n["status"].value == "feasible" and n["claim_status"].value == "screening" and n["refusal"].value == ""
    assert n["refusal"].renderings == ("--",)
    assert all(v.source["table"] == "held_out_summary.tex" and v.source["row"] == {"channel": 33} for v in n.values())


def test_off_era_replay_prints_pfa_the_flag_rate_and_marks_the_missing_interval(tmp_path):
    frag = hos.build(core.load_run(_ledger(tmp_path)))
    r = _rows(frag)[26]
    assert r[1] == "$1$" and r[2] == r"$1.0000\ (65{,}536)$" and r[3] == "$0.050$"
    assert r[4] == r"$0.031\ [\mbox{--}]$" and r[5] == r"$2.50\times10^{-5}\ [\mbox{--}]{}^{\mathrm{b}}$"
    assert r[6] == r"$2.10\times10^{-3}$" and r[7] == "$0.031$" and r[8] == "$0.046$"
    assert r[9:] == ["feasible", "screening", "--"]
    n = _numbers(frag, 26)
    assert n["false_alarm_rate"].value == 0.0312 and n["false_alarm_rate"].status == "measured" and n["false_alarm_rate"].precision == 3
    assert n["false_alarm_rate_flag"].value == 0.0456 and n["false_alarm_rate_flag"].status == "measured"
    assert n["false_alarm_basis"].value == _OFF
    assert n["masked_fraction_evaluation_q16"].value is None and n["masked_fraction_evaluation_q16"].status == "refused"
    assert n["r_sys_evaluation"].value == 2.5e-5 and n["r_sys_evaluation"].precision is None
    assert n["r_sys_evaluation"].renderings == ("2.50x10^{-5}", "2.50e-5") and n["r_sys_evaluation"].status == "bounded"
    assert n["r_sys_evaluation_q16"].status == "refused" and n["R"].status == "bounded"
    assert n["R"].renderings == ("2.10x10^{-3}", "2.10e-3") and n["tau_quality"].value == "bounded_above"


def test_diagnostic_row_on_an_off_era_at_the_cap(tmp_path):
    frag = hos.build(core.load_run(_ledger(tmp_path)))
    r = _rows(frag)[19]
    assert r[1] == r"$1{}^{\dagger}$" and r[2] == r"$1.1148\ (73{,}060)$" and r[3] == "$0.868$"
    assert r[4] == r"$0.810\ [0.802, 0.818]$"
    assert r[5] == r"$1.13\times10^{3}\ [1.13\times10^{3}, 1.13\times10^{3}]{}^{\mathrm{c}}$"
    assert r[6] == r"$9.41\times10^{4}$" and r[7] == "$0.810$" and r[8] == "$0.879$"
    assert r[9:] == ["no feasible point", "diagnostic", "drift screen: early half 167 d (need 270)"]
    n = _numbers(frag, 19)
    assert n["point_basis"].value == hos.DIAGNOSTIC
    assert n["rho"].value == 1 and n["eta"].value == 1.11480712890625 and n["eta"].precision == 4
    assert n["eta_q16"].value == 73060 and n["eta_q16"].status == "measured" and n["eta_q16"].renderings == ("73060",)
    assert n["masked_fraction_calibration"].value == 0.8679683867968386
    assert n["r_sys_evaluation"].value == 1129.78 and n["r_sys_evaluation"].status == "bounded"
    assert n["r_sys_evaluation"].renderings == ("1.13x10^{3}", "1.13e3") and n["r_sys_evaluation_q84"].status == "bounded"
    assert n["R"].value == 94148.43 and n["R"].precision is None and n["R"].renderings == ("9.41x10^{4}", "9.41e4")
    assert n["false_alarm_rate"].value == 0.8103 and n["false_alarm_rate_flag"].value == 0.8787
    assert n["tau_quality"].value == "refused" and n["gain_basis"].value == "era chain"
    assert n["refusal"].value == _REFUSAL_DAYS and n["claim_status"].value == "diagnostic"


def test_diagnostic_row_under_the_archive_wide_gain(tmp_path):
    frag = hos.build(core.load_run(_ledger(tmp_path)))
    r = _rows(frag)[35]
    assert r[1] == r"$1{}^{\dagger}$" and r[2] == r"$307.53\ (20{,}154{,}270)$" and r[3] == "$0.924$"
    assert r[4] == r"$0.882\ [0.873, 0.890]$" and r[5] == r"$35.2\ [34.5, 35.9]{}^{\mathrm{ab}}$"
    assert r[6] == r"$1.00\times10^{3}$" and r[7] == "--" and r[8] == "--"
    assert r[9:] == ["no feasible point", "diagnostic", "drift screen: early half 3 months (need 6)"]
    n = _numbers(frag, 35)
    assert n["eta"].precision == 2 and n["eta_q16"].value == 20154270
    assert n["gain_basis"].value == "archive-wide chain (era chain refused)" and n["tau_quality"].value == "bounded_above"
    assert n["r_sys_evaluation"].precision == 1 and n["r_sys_evaluation"].status == "bounded"
    assert n["R"].value == 999.88 and n["R"].renderings == ("1.00x10^{3}", "1.00e3")


def test_replay_that_kept_no_frame_dashes_the_residual(tmp_path):
    frag = hos.build(core.load_run(_ledger(tmp_path)))
    r = _rows(frag)[31]
    assert r[1] == r"$115{}^{\dagger}$" and r[2] == r"$1.0374\ (67{,}987)$" and r[3] == "$0.994$"
    assert r[4] == r"$1.000\ [1.000, 1.000]$" and r[5:9] == ["--"] * 4
    assert r[9:] == ["no feasible point", "diagnostic", r"drift screen: $<30$ frames/half at $\rho=1$, $\eta=1.071$"]
    n = _numbers(frag, 31)
    assert n["masked_fraction_evaluation"].value == 1.0 and n["masked_fraction_evaluation"].status == "measured"
    assert n["r_sys_evaluation"].value is None and n["r_sys_evaluation"].status == "refused"
    assert n["R"].value is None and n["R"].status == "refused"
    assert n["kept_evaluation"].value == 0 and n["kept_evaluation"].status == "measured"
    assert n["refusal"].value == _REFUSAL_FRAMES


def test_refused_selection_dashes_every_value_cell(tmp_path):
    frag = hos.build(core.load_run(_ledger(tmp_path)))
    r = _rows(frag)[15]
    assert r == ["15"] + ["--"] * 8 + ["refused", "--", _REFUSAL_FLOOR]
    n = _numbers(frag, 15)
    assert n["point_basis"].value == "none" and n["rho"].value is None and n["rho"].status == "refused"
    assert n["eta_q16"].value is None and n["eta_q16"].status == "refused" and n["eta_q16"].renderings == ()
    assert n["status"].value == "refused" and n["claim_status"].value == "" and n["claim_status"].renderings == ("--",)
    assert n["refusal"].value == _REFUSAL_FLOOR and n["refusal"].renderings == (_REFUSAL_FLOOR,)
    assert n["false_alarm_basis"].value.startswith("not measurable") and "no replay" in n["false_alarm_basis"].value


def test_absent_sections_dash_every_cell(tmp_path):
    frag = hos.build(core.load_run(_ledger(tmp_path)))
    r = _rows(frag)[14]
    assert r == ["14"] + ["--"] * 11
    n = _numbers(frag, 14)
    assert n["point_basis"].value == "none" and n["rho"].value is None and n["R"].value is None
    assert n["false_alarm_basis"].value == "" and n["false_alarm_basis"].renderings == ("--",)
    assert n["gain_basis"].value == "" and n["tau_quality"].value == "" and n["kept_evaluation"].value is None
    assert n["status"].value == "" and n["status"].renderings == ("--",)


def test_off_era_without_a_replay_prints_the_flag_rate_alone(tmp_path):
    frag = hos.build(core.load_run(_ledger(tmp_path)))
    r = _rows(frag)[20]
    assert r[1] == r"$2{}^{\dagger}$" and r[2] == r"$1.3032\ (85{,}406)$" and r[3] == "$0.943$"
    assert r[4:8] == ["--"] * 4 and r[8] == "$0.997$"
    assert r[9:] == ["no feasible point", "diagnostic", r"drift screen: $<30$ frames/half at $\rho=1$, $\eta=1.142$"]
    n = _numbers(frag, 20)
    assert n["false_alarm_rate"].value is None and n["false_alarm_rate_flag"].value == 0.9967
    assert "nothing was replayed" in n["false_alarm_basis"].value and "screening.off_era_current" in n["false_alarm_basis"].value
    assert n["r_sys_evaluation"].status == "refused"


def test_counts_notes_and_key_discipline(tmp_path):
    frag = hos.build(core.load_run(_ledger(tmp_path)))
    counts = {n.key: n.value for n in frag.numbers if not n.source["row"]}
    assert counts == {"ch06.heldout.n_channels": 8, "ch06.heldout.n_selected": 2, "ch06.heldout.n_diagnostic": 4,
                      "ch06.heldout.n_refused": 1, "ch06.heldout.n_replayed": 5, "ch06.heldout.n_replay_kept_none": 1,
                      "ch06.heldout.n_off_era_evaluation_blocks": 3, "ch06.heldout.n_false_alarm_measured": 2,
                      "ch06.heldout.n_gain_archive": 1, "ch06.heldout.n_residual_bounded": 3}
    assert len(counts) == COUNTS
    keys = [n.key for n in frag.numbers]
    assert len(keys) == len(set(keys)) == 8 * PER_CHANNEL + COUNTS and all(k.startswith("ch06.heldout.") for k in keys)
    assert all(n.status in ("measured", "bounded", "refused", "derived") for n in frag.numbers)
    text = "\n".join(frag.notes)
    assert "Selected points (selection.rho, eta, eta_q16, masked_fraction_calibration): channels 26, 33." in text
    assert "Dagger rows (19, 20, 31, 35)" in text and "selection.diagnostic_basis" in text
    assert "Status 'refused' on channels 15 (no floor for frames without a shelf estimate)" in text
    assert "Channels 31 also carry a refused floor" in text and "every frame of both blocks carries a shelf estimate" in text
    assert "Channels 14 carry no selection point and no diagnostic point" in text
    assert "dashed on channels 20: the point was not replayed" in text
    assert "Channels 31: the replay kept no frame" in text
    assert "Channels 26 print an evaluation value with '[--]'" in text
    assert "P_fa on channels 19, 20, 26 is the replay's masked fraction" in text
    assert "On channels 20 the block is an off era but nothing was replayed" in text
    assert "sidereal-day cap (mark c; selection.chain_gain) on channels 19" in text
    assert "bounded above (mark b) on channels 26, 35" in text
    assert "archive-wide chain because the era chain refused (mark a; selection.gain_basis) on channels 35" in text
    assert "On channels 19 r_sys,eval is within 1% of the floor times the chain gain" in text
    assert "prints as the value itself on channels 19" in text
    assert "Claim 'diagnostic' on channels 19, 20, 31, 35" in text


def test_helpers():
    assert hos.fmt_sig(0.8713) == ("0.871", 3, ())
    assert hos.fmt_sig(656.39) == ("656", 0, ())
    assert hos.fmt_sig(0.0) == ("0", 0, ())
    assert hos.fmt_sig(999.88) == (r"1.00\times10^{3}", None, ("1.00x10^{3}", "1.00e3"))
    assert hos.fmt_sig(6696.57) == (r"6.70\times10^{3}", None, ("6.70x10^{3}", "6.70e3"))
    assert hos.fmt_sig(9.97e6) == (r"9.97\times10^{6}", None, ("9.97x10^{6}", "9.97e6"))
    assert hos.fmt_sig(0.0042) == (r"4.20\times10^{-3}", None, ("4.20x10^{-3}", "4.20e-3"))
    assert hos.fmt_sig(0.009999) == ("0.0100", 4, ())
    assert hos.fmt_sig(-12345.6) == (r"-1.23\times10^{4}", None, ("-1.23x10^{4}", "-1.23e4"))
    assert hos.fmt_sig(None) == ("--", None, ()) and hos.fmt_sig(float("nan"))[0] == "--"
    two = lambda x: core.fmt(x, 2)  # noqa: E731
    assert hos.fmt_interval(0.5, 0.4, 0.6, two) == r"0.50\ [0.40, 0.60]"
    assert hos.fmt_interval(0.5, None, 0.6, two) == r"0.50\ [\mbox{--}]" and hos.fmt_interval(None, 0.4, 0.6, two) == "--"
    assert hos.short_refusal("") == "--" and hos.short_refusal(None) == "--"
    assert hos.short_refusal(_REFUSAL_FRAMES) == r"drift screen: $<30$ frames/half at $\rho=1$, $\eta=1.071$"
    assert hos.short_refusal("within-era stability refused_insufficient_support: early half has 5 observed months; need 6") == \
        "drift screen: early half 5 months (need 6)"
    assert hos.short_refusal("within-era stability refused_insufficient_support: late half spans 166.924 days; need 270") == \
        "drift screen: late half 167 d (need 270)"
    assert hos.short_refusal("within-era stability refused_unconfigured: cost margin unset") == "drift screen unconfigured: cost margin unset"
    assert hos.short_refusal("preparation: 100% masked") == r"preparation: 100\% masked"
    assert hos.floor_times_gain({"floor_db": -30.0, "chain_gain": 1000.0}) == pytest.approx(1.0)
    assert hos.floor_times_gain({"floor_db": None, "chain_gain": 1000.0}) is None


def test_point_and_gain_helpers():
    def channel(sections):
        return core.Channel(19, 767, "767.npz", "b" * 64, (), sections, Path("ch19_fid767.json"))

    assert hos.point({"rho": 3, "eta": 1.5, "eta_q16": 98304, "masked_fraction_calibration": 0.2, "diagnostic_rho": 1}) == \
        (hos.SELECTED, 3, 1.5, 98304, 0.2)
    assert hos.point({"rho": None, "diagnostic_rho": 1, "diagnostic_eta": 1.1, "diagnostic_eta_q16": 72090,
                      "diagnostic_masked_fraction": 0.9}) == (hos.DIAGNOSTIC, 1, 1.1, 72090, 0.9)
    assert hos.point({"rho": None, "diagnostic_rho": None}) == ("", None, None, None, None) and hos.point({})[0] == ""
    assert hos.gain_basis(channel({"selection": {"gain_basis": "era chain"}, "chain": {"tau_quality": "measured"}})) == \
        ("", "era chain", "measured")
    assert hos.gain_basis(channel({"selection": {"gain_basis": "era chain"}, "chain": {"tau_quality": "refused"},
                                   "chain_archive": {"tau_quality": "measured"}})) == (r"{}^{\mathrm{c}}", "era chain", "refused")
    assert hos.gain_basis(channel({"selection": {"gain_basis": "archive-wide chain (era chain refused)"},
                                   "chain": {"tau_quality": "refused"}, "chain_archive": {"tau_quality": "measured"}})) == \
        (r"{}^{\mathrm{a}}", "archive-wide chain (era chain refused)", "measured")
    assert hos.gain_basis(channel({"selection": {}, "chain": None})) == ("", "", "")
    assert hos.off_era_block(channel({"selection": {}, "screening": {"off_era_current": True}}))
    assert hos.off_era_block(channel({"selection": {"false_alarm_basis": _OFF}, "screening": None}))
    assert not hos.off_era_block(channel({"selection": {"false_alarm_basis": _NO_OFF}, "screening": {"off_era_current": False}}))
    assert hos.false_alarm_basis(channel({"selection": {}, "screening": None})) == ""
    assert hos.false_alarm_basis(channel({"selection": {"false_alarm_basis": _OFF}})) == _OFF


def test_write_report_round_trip(tmp_path):
    run = core.load_run(_ledger(tmp_path))
    manifest = core.write_report(run, tmp_path / "out", [hos.build], commit="d" * 40, generated="2026-09-07T09:00:00+00:00")
    art = manifest["artifacts"][0]
    assert art["name"] == "held_out_summary" and art["label"] == "tab:detection:heldout" and art["count"] == 8 * PER_CHANNEL + COUNTS
    assert art["table"] == "tables/held_out_summary.tex" and art["notes"] == hos.build(run).notes
    doc = json.loads((tmp_path / "out" / "numbers" / "held_out_summary.numbers.json").read_text())
    assert doc["export"] == "held_out_summary" and len(doc["inputs"]) == 9
    assert (tmp_path / "out" / "tables" / "held_out_summary.tex").read_text() == hos.build(run).tex


@pytest.mark.skipif(not (REAL_RUN / "ledger" / "run.json").is_file(), reason="the archive run is not on this machine")
def test_real_run_renders_23_rows(tmp_path):
    run = core.load_run(REAL_RUN)
    frag = hos.build(run)
    rows = _rows(frag)
    assert len(rows) == 23 and sorted(rows) == list(range(14, 37))
    keys = [n.key for n in frag.numbers]
    assert len(keys) == len(set(keys)) == 23 * PER_CHANNEL + COUNTS
    core.write_report(run, tmp_path / "out", [hos.build], commit=run.commit, generated="2026-09-07T09:00:00+00:00")
    doc = json.loads((tmp_path / "out" / "numbers" / "held_out_summary.numbers.json").read_text())
    doc_keys = [n["key"] for n in doc["numbers"]]
    assert len(doc_keys) == len(set(doc_keys)) == len(keys)
    # a dagger only as the diagnostic mark, and only on rows whose claim is diagnostic
    assert "^\\dagger" not in frag.tex.replace("{}^{\\dagger}", "")
    by_ch = {n.key: n.value for n in frag.numbers}
    for ch, r in rows.items():
        assert (r"{}^{\dagger}" in r[1]) == (by_ch[f"ch06.heldout.claim_status.ch{ch}"] == "diagnostic"), ch
    # this run: no selected point; the selector refused 15, 28, 30, 36 (refused floor); the other 19 are diagnostic
    refused = [ch for ch in rows if by_ch[f"ch06.heldout.status.ch{ch}"] == "refused"]
    assert refused == [15, 28, 30, 36] and all(rows[ch][1:9] == ["--"] * 8 for ch in refused)
    assert by_ch["ch06.heldout.n_selected"] == 0 and by_ch["ch06.heldout.n_diagnostic"] == 19 and by_ch["ch06.heldout.n_refused"] == 4
    # off-era evaluation blocks 19, 20, 26, 27, 32 carry P_fa and the flag's rate; nobody else does
    off = [ch for ch in rows if rows[ch][7] != "--"]
    assert off == [19, 20, 26, 27, 32] and all(rows[ch][8] != "--" for ch in off)
    assert by_ch["ch06.heldout.n_off_era_evaluation_blocks"] == 5 and by_ch["ch06.heldout.n_false_alarm_measured"] == 5
    assert all(rows[ch][7] == rows[ch][8] == "--" for ch in rows if ch not in off)
    # replays that kept no frame: f_eval 1.000, residual and R undefined
    assert rows[31][5] == rows[31][6] == "--" and rows[33][5] == rows[33][6] == "--" and rows[31][4].startswith("$1.000")
    assert by_ch["ch06.heldout.n_replay_kept_none"] == 2 and by_ch["ch06.heldout.n_replayed"] == 19
    # every gain is the era chain; the cap and the bound mark the residual
    assert by_ch["ch06.heldout.n_gain_archive"] == 0 and "mathrm{a" not in frag.tex
    assert r"{}^{\mathrm{c}}" in rows[14][5] and r"{}^{\mathrm{b}}" in rows[18][5] and "mathrm" not in rows[20][5]
    assert by_ch["ch06.heldout.n_residual_bounded"] == 12       # cap on 14 16 17 19 22 23 25 27 34, bound on 18 21 29; 33 has no residual
