"""The ``tolerance_eta`` fragment (tab:tolerance:eta): selected or diagnostic points per channel."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

import pytest

from rfisher_results.archive import numbers as nb
from rfisher_results.archive.report import core, tolerance_eta as te

REAL_RUN = Path(os.environ.get("RFISHER_ARCHIVE_RESULTS", Path.home() / "rail" / "results" / "archive_v5_2026-09-07"))
CAP = 2054312.002658844                     # the sidereal-day cap on the chain gain


def _rows(frag: core.Fragment) -> list[list[str]]:
    lines = [ln for ln in frag.tex.splitlines() if ln.endswith(r"\\")]
    return [[c.strip() for c in ln[:-2].split(" & ")] for ln in lines[1:]]    # the first is the header


def _cells(frag: core.Fragment, channel: int) -> dict[str, str]:
    for row in _rows(frag):
        if row[0] == str(channel):
            return dict(zip(te.HEADER, row))
    raise KeyError(channel)


def _record(channel: int, freq_id: int, sections: dict, notes=()) -> dict:
    return {"channel": channel, "freq_id": freq_id, "product": f"{freq_id}.npz", "product_sha256": "b" * 64,
            "notes": list(notes), "sections": sections}


def _diagnostic(rho, eta_q16, f, r_sys, R, cost) -> dict:
    return {"rho": None, "q_rho": None, "eta_q16": None, "eta": None, "masked_fraction_calibration": None,
            "r_sys_calibration": None, "R_calibration": None, "cost": None, "plateau_members": None,
            "plateau_eta_low": None, "plateau_eta_high": None, "status": "no feasible point", "claim_status": "diagnostic",
            "diagnostic_basis": "least residual on the calibration surface (no feasible point)", "diagnostic_rho": rho,
            "diagnostic_eta_q16": eta_q16, "diagnostic_eta": eta_q16 / 65536, "diagnostic_masked_fraction": f,
            "diagnostic_r_sys": r_sys, "diagnostic_R": R, "diagnostic_cost": cost, "min_r_sys": r_sys, "min_R": R,
            "min_r_sys_rho": rho, "min_r_sys_eta": eta_q16 / 65536, "min_r_sys_masked_fraction": f, "feasible_points": 0}


def _ledger(tmp_path: Path) -> Path:
    ledger = tmp_path / "ledger"
    (ledger / "channels").mkdir(parents=True)
    files = [f"channels/ch{c}_fid{f}.json" for c, f in ((15, 829), (16, 813), (17, 798), (19, 767), (33, 552), (35, 521))]
    run = {"schema": {"name": "rfisher-archive-ledger", "version": 1}, "generated": "2026-09-07T00:00:00+00:00",
           "producer": {"commit": "a" * 40}, "products": {}, "channels": files, "era_config_digest": "c" * 64}
    (ledger / "run.json").write_text(json.dumps(run))

    def era(first, last, state, off=False):
        return {"current_first_month": first, "current_last_month": last, "current_state": state, "off_era_current": off}

    # ch33: diagnostic point (least residual); stated bulk-left-side floor; tau bound; coarse frontier; gain from the chain section
    sel33 = {"era": "2023-12..2026-08 (proxy-low)", "bulk_size": 125, "r_tol": 0.0156, "floor_db": -35.94443521758792,
             "floor_evidence": "stated", "floor_population": "no verified off era; sigma-implied substitute: bulk left-side scale",
             "refusal": "within-era stability refused_insufficient_support: candidate rho=1, eta=1.17926 retains fewer than 30 frames in one era half",
             "surface_points": 1378418, "coarse_min_R": 33504.12524519568, "coarse_min_R_eta": 1.0, "coarse_min_R_masked_fraction": 0.973,
             "gain_basis": "era chain", **_diagnostic(1, 78313, 0.9971315278832363, 546.3311526736431, 35021.22773548995, 348.6176470588264)}
    null33 = {"floor_db": -35.94443521758792, "floor_evidence": "stated", "floor_frames": 11853, "floor_basis": "bulk left side (not H0)",
              "floor_stated_kept_half_db": -38.51852382269598, "floor_stated_bulk_db": -35.94443521758792, "kept_frames": 320}
    rec33 = _record(33, 552, {"era": era("2023-12", "2026-08", "proxy-low"), "selection": sel33, "null": null33,
                              "chain": {"tau_quality": "bounded_above", "tau_outcome": "bound", "chain_gain": 1180.9658799509368}})
    (ledger / "channels" / "ch33_fid552.json").write_text(json.dumps(rec33))

    # ch35: a selected, feasible point (R <= 1: bold); measured off-era floor; tau measured; plateau of three; the diagnostic keys are ignored
    sel35 = {"era": "2025-11..2026-08 (proxy-high)", "bulk_size": 126, "r_tol": 0.0352, "floor_db": -28.4356, "floor_evidence": "measured",
             "floor_population": "verified off era: 4954 frames with a shelf estimate of 11199", "status": "feasible",
             "claim_status": "screening", "refusal": "", "rho": 3, "q_rho": 3 / 127, "eta_q16": 70000, "eta": 70000 / 65536,
             "masked_fraction_calibration": 0.4321, "r_sys_calibration": 0.0291, "R_calibration": 0.8267, "cost": 1.761,
             "plateau_members": 3, "plateau_eta_low": 1.05, "plateau_eta_high": 1.12, "feasible_points": 12,
             "diagnostic_rho": 1, "diagnostic_eta_q16": 20154270, "diagnostic_eta": 307.5, "diagnostic_masked_fraction": 0.9238,
             "diagnostic_r_sys": 37.01, "diagnostic_R": 1051.0, "diagnostic_cost": 13.12, "coarse_min_R": 0.57, "coarse_min_R_eta": 1.02,
             "chain_gain": 440.4, "gain_basis": "era chain"}
    rec35 = _record(35, 521, {"era": era("2025-11", "2026-08", "proxy-high"), "selection": sel35,
                              "null": {"floor_frames": 4954, "floor_basis": "off era p90"},
                              "chain": {"tau_quality": "measured", "chain_gain": 440.4}})
    (ledger / "channels" / "ch35_fid521.json").write_text(json.dumps(rec35))

    # ch17: diagnostic point on a refused floor (no null population, no coarse frontier); tau refused (cap); months refusal
    sel17 = {"era": "2025-10..2026-08 (proxy-high)", "bulk_size": 125, "r_tol": 0.0201, "floor_db": None, "floor_evidence": "refused",
             "floor_population": "no off era; bulk centre 44.5 is beyond 0.1 of mu_0: the block carries no null population",
             "refusal": "within-era stability refused_insufficient_support: early half has 3 observed months; need 6",
             "coarse_min_R": None, "coarse_min_R_eta": None, "chain_gain": CAP, "gain_basis": "era chain",
             **_diagnostic(124, 122397, 0.9952441344324667, 570574.0270992547, 28386767.517375853, 210.26666666666767)}
    rec17 = _record(17, 798, {"era": era("2025-10", "2026-08", "proxy-high"), "selection": sel17,
                              "null": {"floor_db": None, "floor_evidence": "refused", "floor_frames": 0, "floor_basis": "none"},
                              "chain": {"tau_quality": "refused", "tau_outcome": "refused (cap)", "chain_gain": CAP}})
    (ledger / "channels" / "ch17_fid798.json").write_text(json.dumps(rec17))

    # ch15: the selector refused outright (no floor for frames without a shelf estimate): no surface, no diagnostic point
    sel15 = {"era": "2025-05..2026-08 (proxy-high)", "bulk_size": 125, "r_tol": 0.0201, "floor_db": None, "floor_evidence": "refused",
             "status": "refused", "claim_status": "", "refusal": "no floor for frames without a shelf estimate", "rho": None,
             "diagnostic_rho": None, "diagnostic_eta": None, "surface_points": 0, "coarse_min_R": None, "chain_gain": CAP,
             "gain_basis": "era chain"}
    rec15 = _record(15, 829, {"era": era("2025-05", "2026-08", "proxy-high"), "selection": sel15,
                              "null": {"floor_evidence": "refused", "floor_frames": 0, "floor_basis": "none"},
                              "chain": {"tau_quality": "refused", "chain_gain": CAP}})
    (ledger / "channels" / "ch15_fid829.json").write_text(json.dumps(rec15))

    # ch19: an off-era channel (measured off-era floor, false-alarm point); the archive-wide gain where the era chain refused
    sel19 = {"era": "2024-12..2026-04 (proxy-low)", "bulk_size": 125, "r_tol": 0.012, "floor_db": -32.62346099837274,
             "floor_evidence": "measured", "floor_population": "verified off era: 5503 frames with a shelf estimate of 6453",
             "refusal": "within-era stability refused_insufficient_support: early half spans 166.924 days; need 270",
             "coarse_min_R": 93570.52317147385, "coarse_min_R_eta": 1.0, "chain_gain": 1180.9658799509368,
             "gain_basis": "archive-wide chain (era chain refused)",
             **_diagnostic(1, 73060, 0.8679683867968386, 1122.8462780576758, 93570.52317147299, 7.573943661971828)}
    rec19 = _record(19, 767, {"era": era("2024-12", "2026-04", "proxy-low", off=True), "selection": sel19,
                              "null": {"floor_db": -32.62346099837274, "floor_evidence": "measured", "floor_frames": 5503,
                                       "floor_basis": "off era p90", "off_frames": 6453},
                              "chain": {"tau_quality": "measured", "chain_gain": 3191.0}})
    (ledger / "channels" / "ch19_fid767.json").write_text(json.dumps(rec19))

    # ch16: the selection, null and chain sections are absent; only the era section exists
    rec16 = _record(16, 813, {"era": era("2018-12", "2026-08", "proxy-low"), "selection": None, "null": None, "chain": None})
    (ledger / "channels" / "ch16_fid813.json").write_text(json.dumps(rec16))
    return tmp_path


def test_short_refusal_reduces_to_the_reason():
    assert te.short_refusal("within-era stability refused_insufficient_support: early half has 3 observed months; need 6") == \
        "refused: early half 3 months < 6"
    assert te.short_refusal("within-era stability refused_insufficient_support: late half spans 166.924 days; need 270") == \
        "refused: late half 167 days < 270"
    assert te.short_refusal("within-era stability refused_insufficient_support: candidate rho=1, eta=1.0507 retains fewer than 30 frames in one era half") == \
        "refused: sparse candidate rho=1 eta=1.05"
    assert te.short_refusal("x: candidate rho=2, eta=103.062 retains fewer than 30 frames in one era half") == "refused: sparse candidate rho=2 eta=103.06"
    assert te.short_refusal("within-era stability refused_insufficient_support: no selector-evaluable candidate has supported era halves") == \
        "refused: no supported candidate"
    assert te.short_refusal("within-era stability refused_unconfigured: both drift limits and the per-half retained-frame floor must be declared") == \
        "refused: drift limits unconfigured"
    assert te.short_refusal("no floor for frames without a shelf estimate") == "refused: no floor (frames without a shelf estimate)"
    assert te.short_refusal("preparation: something else entirely") == "refused: something else entirely"
    assert te.short_refusal("") == "" and te.short_refusal(None) == ""


def test_sig_rounds_before_choosing_the_decade():
    assert te.sig(195.461, 3) == "195" and te.sig(0.0471, 3) == "0.0471" and te.sig(0.9145, 4) == "0.9145"
    assert te.sig(-42.4669, 3) == "-42.5" and te.sig(1.1949615478515625, 4) == "1.195" and te.sig(1594.0, 4) == "1594"
    assert te.sig(570574.03, 3) == r"5.71\times10^{5}" and te.sig(2087473.4, 3) == r"2.09\times10^{6}"
    assert te.sig(99960.0, 3) == r"1.00\times10^{5}" and te.sig(0.0004, 3) == r"4.00\times10^{-4}"
    assert te.sig(999.6, 3) == "1000" and te.sig(0.00099996, 3) == "0.00100" and te.sig(-99960.0, 3) == r"-1.00\times10^{5}"
    assert te.sig(None) == core.DASH and te.sig(math.nan) == core.DASH and te.sig(0.0) == "0"


def test_era_label_falls_back_to_the_era_section(tmp_path):
    run = core.load_run(_ledger(tmp_path))
    by = run.by_channel()
    assert te.era_label(by[33]) == ("2023-12..2026-08", "proxy-low")
    assert te.era_label(by[16]) == ("2018-12..2026-08", "proxy-low")
    empty = core.Channel(1, 1, "p", "s", (), {"era": None, "selection": None}, tmp_path)
    assert te.era_label(empty) == ("", "")


def test_resolve_point_prefers_the_selection_then_the_diagnostic(tmp_path):
    run = core.load_run(_ledger(tmp_path))
    by = run.by_channel()
    pt = te.resolve_point(by[33])
    assert pt.diagnostic and pt.rho == 1 and pt.eta_q16 == 78313 and pt.cost == pytest.approx(348.617647)
    assert pt.q_rho == pytest.approx(1 / 126) and pt.q_rho_derived and pt.basis.startswith("least residual")
    pt = te.resolve_point(by[35])
    assert pt.source == "selection" and not pt.diagnostic and pt.rho == 3 and pt.eta_q16 == 70000
    assert pt.q_rho == pytest.approx(3 / 127) and not pt.q_rho_derived and pt.R == pytest.approx(0.8267) and pt.basis == ""
    assert te.resolve_point(by[15]).source == "" and te.resolve_point(by[16]).rho is None
    # a point without a bulk size has no derived q_rho
    ch = core.Channel(1, 1, "p", "s", (), {"selection": {"diagnostic_rho": 2, "diagnostic_eta": 1.5}}, tmp_path)
    pt = te.resolve_point(ch)
    assert pt.rho == 2 and math.isnan(pt.q_rho) and pt.eta_q16 is None and math.isnan(pt.cost)


def test_build_renders_every_column(tmp_path):
    run = core.load_run(_ledger(tmp_path))
    frag = te.build(run)
    assert frag.name == "tolerance_eta" and frag.label == "tab:tolerance:eta"
    rows = _rows(frag)
    assert [r[0] for r in rows] == ["15", "16", "17", "19", "33", "35"] and all(len(r) == len(te.HEADER) for r in rows)
    assert frag.tex.startswith("% tab:tolerance:eta: a dagger") and "\n\\begin{tabular}{" + te.ALIGN + "}\n" in frag.tex

    c33 = _cells(frag, 33)          # the diagnostic point: dagger, derived q_rho, stated floor with its population, tau bound
    assert c33["era"] == "2023-12--2026-08" and c33["state"] == "proxy-low" and c33[r"$|\mathcal B|$"] == "$125$"
    assert c33[r"$\rho^\star$"] == r"$1^\dagger$" and c33[r"$q_\rho$"] == "$0.0079$"
    assert c33[r"$\eta^\star$"] == "$1.195$" and c33[r"$\eta^\star_{q16}$"] == "$78{,}313$" and c33["$f$"] == "$0.9971$"
    assert c33["floor (dB)"] == "$-35.9$" and c33["floor basis"] == "bulk left side, $11{,}853$"
    assert c33[r"$r_{\rm proxy}$"] == "$546$" and c33[r"$r_{\rm tol}$"] == "$0.0156$" and c33["$R$"] == "$35000$"
    assert c33[r"$R_{\rm c}$ ($\eta_{\rm c}$)"] == "$33500$ ($1.000$)" and c33[r"$\mathcal C$"] == "$349$"
    assert c33["plateau"] == core.DASH and c33[r"$\tau_c$"] == "bound" and c33["gain"] == "$1{,}181$" and c33["gain basis"] == "era"
    assert c33["status"] == "no feasible point (diagnostic)"
    assert c33["screen"] == r"refused: sparse candidate $\rho=$1 $\eta=$1.18"

    c35 = _cells(frag, 35)          # a selected point: no dagger, bold R and R_c, plateau, measured off-era floor
    assert c35[r"$\rho^\star$"] == "$3$" and c35[r"$q_\rho$"] == "$0.0236$" and c35[r"$\eta^\star$"] == "$1.068$"
    assert c35[r"$\eta^\star_{q16}$"] == "$70{,}000$" and c35["$f$"] == "$0.4321$" and c35["floor (dB)"] == "$-28.4$"
    assert c35["floor basis"] == "off era p90, $4{,}954$" and c35[r"$r_{\rm proxy}$"] == "$0.0291$"
    assert c35["$R$"] == r"$\mathbf{0.827}$" and c35[r"$R_{\rm c}$ ($\eta_{\rm c}$)"] == r"$\mathbf{0.570}$ ($1.020$)"
    assert c35[r"$\mathcal C$"] == "$1.76$" and c35["plateau"] == "$3$ ($1.050$--$1.120$)" and c35[r"$\tau_c$"] == "measured"
    assert c35["gain"] == "$440$" and c35["status"] == "feasible (screening)" and c35["screen"] == core.DASH

    c17 = _cells(frag, 17)          # a diagnostic point on a refused floor: no floor, no basis, no coarse frontier; cap
    assert c17[r"$\rho^\star$"] == r"$124^\dagger$" and c17[r"$q_\rho$"] == "$0.9841$" and c17[r"$\eta^\star$"] == "$1.868$"
    assert c17["floor (dB)"] == core.DASH and c17["floor basis"] == core.DASH and c17[r"$R_{\rm c}$ ($\eta_{\rm c}$)"] == core.DASH
    assert c17[r"$r_{\rm proxy}$"] == r"$5.71\times10^{5}$" and c17["$R$"] == r"$2.84\times10^{7}$" and c17[r"$\mathcal C$"] == "$210$"
    assert c17[r"$\tau_c$"] == "cap" and c17["gain"] == "$2{,}054{,}312$" and c17["screen"] == "refused: early half 3 months $<$ 6"

    c15 = _cells(frag, 15)          # the selector refused outright: no point at all, the bulk, tolerance and chain survive
    assert c15["status"] == "refused" and c15["screen"] == "refused: no floor (frames without a shelf estimate)"
    assert c15[r"$|\mathcal B|$"] == "$125$" and c15[r"$r_{\rm tol}$"] == "$0.0201$" and c15[r"$\tau_c$"] == "cap"
    assert c15["gain"] == "$2{,}054{,}312$" and c15["gain basis"] == "era"
    for h in (r"$\rho^\star$", r"$q_\rho$", r"$\eta^\star$", r"$\eta^\star_{q16}$", "$f$", "floor (dB)", "floor basis",
              r"$r_{\rm proxy}$", "$R$", r"$R_{\rm c}$ ($\eta_{\rm c}$)", r"$\mathcal C$", "plateau"):
        assert c15[h] == core.DASH, h

    c19 = _cells(frag, 19)          # an off-era channel with the archive-wide gain
    assert c19["state"] == "proxy-low (off)" and c19["floor basis"] == "off era p90, $5{,}503$" and c19["floor (dB)"] == "$-32.6$"
    assert c19["gain"] == "$1{,}181$" and c19["gain basis"] == "archive" and c19["screen"] == "refused: early half 167 days $<$ 270"
    assert c19[r"$r_{\rm proxy}$"] == "$1120$" and c19["$R$"] == "$93600$" and c19[r"$R_{\rm c}$ ($\eta_{\rm c}$)"] == "$93600$ ($1.000$)"

    c16 = _cells(frag, 16)          # no selection, null or chain section: the era survives, everything else is the dash
    assert c16["era"] == "2018-12--2026-08" and c16["state"] == "proxy-low"
    assert all(c16[h] == core.DASH for h in te.HEADER if h not in ("ch", "era", "state"))

    # numbers: one per printed value, keyed ch09.eta.<column>.chNN, no duplicates, statuses as the chapter's vocabulary
    keys = [n.key for n in frag.numbers]
    assert len(keys) == len(set(keys))
    by_key = {n.key: n for n in frag.numbers}
    assert by_key["ch09.eta.rho.ch33"].value == 1 and by_key["ch09.eta.eta_q16.ch33"].value == 78313
    assert by_key["ch09.eta.cost.ch33"].value == pytest.approx(348.617647) and "349" in by_key["ch09.eta.cost.ch33"].renderings
    assert by_key["ch09.eta.q_rho.ch33"].value == pytest.approx(1 / 126) and by_key["ch09.eta.q_rho.ch33"].status == "derived"
    assert by_key["ch09.eta.q_rho.ch35"].status == "measured" and by_key["ch09.eta.q_rho.ch35"].precision == 4
    assert by_key["ch09.eta.point_basis.ch33"].value == "diagnostic" and "least residual on the calibration surface (no feasible point)" in \
        by_key["ch09.eta.point_basis.ch33"].renderings
    assert by_key["ch09.eta.point_basis.ch35"].value == "selected" and "ch09.eta.point_basis.ch15" not in by_key
    assert by_key["ch09.eta.R.ch33"].status == "bounded" and by_key["ch09.eta.r_proxy.ch17"].status == "bounded"
    assert by_key["ch09.eta.r_proxy.ch17"].precision is None and r"5.71\times10^{5}" in by_key["ch09.eta.r_proxy.ch17"].renderings
    assert by_key["ch09.eta.R.ch35"].status == "measured" and by_key["ch09.eta.R.ch35"].precision == 3
    assert by_key["ch09.eta.coarse_min_R.ch35"].value == 0.57 and by_key["ch09.eta.coarse_min_R_eta.ch35"].value == 1.02
    assert by_key["ch09.eta.coarse_min_R.ch33"].status == "bounded" and "ch09.eta.coarse_min_R.ch17" not in by_key
    assert by_key["ch09.eta.floor_db.ch33"].status == "derived" and by_key["ch09.eta.floor_db.ch35"].status == "measured"
    assert by_key["ch09.eta.floor_frames.ch33"].value == 11853 and "ch09.eta.floor_frames.ch17" not in by_key
    assert by_key["ch09.eta.floor_basis.ch33"].value == "bulk left side" and "bulk left side (not H0)" in by_key["ch09.eta.floor_basis.ch33"].renderings
    assert by_key["ch09.eta.floor_basis.ch19"].value == "off era p90" and "measured" in by_key["ch09.eta.floor_basis.ch19"].renderings
    assert by_key["ch09.eta.floor_evidence.ch17"].value == "refused" and by_key["ch09.eta.floor_evidence.ch17"].status == "refused"
    assert by_key["ch09.eta.floor_evidence.ch33"].status == "derived" and "ch09.eta.floor_db.ch17" not in by_key
    assert by_key["ch09.eta.chain_gain.ch17"].value == pytest.approx(CAP) and by_key["ch09.eta.chain_gain.ch17"].status == "bounded"
    assert by_key["ch09.eta.chain_gain.ch33"].value == pytest.approx(1180.96588) and by_key["ch09.eta.chain_gain.ch35"].status == "measured"
    assert by_key["ch09.eta.gain_basis.ch19"].value == "archive" and "archive-wide chain (era chain refused)" in by_key["ch09.eta.gain_basis.ch19"].renderings
    assert by_key["ch09.eta.refusal.ch15"].value == "refused: no floor (frames without a shelf estimate)" and by_key["ch09.eta.refusal.ch15"].status == "refused"
    assert by_key["ch09.eta.refusal.ch33"].value == "refused: sparse candidate rho=1 eta=1.18"
    assert by_key["ch09.eta.tau_quality.ch17"].value == "cap" and "refused" in by_key["ch09.eta.tau_quality.ch17"].renderings
    assert by_key["ch09.eta.status.ch15"].value == "refused" and "ch09.eta.claim_status.ch15" not in by_key
    assert by_key["ch09.eta.era.ch16"].value == "2018-12..2026-08" and "2018-12--2026-08" in by_key["ch09.eta.era.ch16"].renderings
    assert by_key["ch09.eta.state.ch19"].value == "proxy-low" and "proxy-low (off)" in by_key["ch09.eta.state.ch19"].renderings
    assert by_key["ch09.eta.plateau_members.ch35"].value == 3 and by_key["ch09.eta.plateau_eta_high.ch35"].value == 1.12
    assert not any(k.endswith(".ch16") and k.split(".")[2] not in ("era", "state") for k in keys)
    assert by_key["ch09.eta.n_channels"].value == 6 and by_key["ch09.eta.n_selected"].value == 1
    assert by_key["ch09.eta.n_diagnostic"].value == 3 and by_key["ch09.eta.n_no_point"].value == 2 and by_key["ch09.eta.n_pass"].value == 1
    assert by_key["ch09.eta.n_floor_measured"].value == 2 and by_key["ch09.eta.n_floor_stated"].value == 1
    assert by_key["ch09.eta.n_floor_refused"].value == 2 and by_key["ch09.eta.n_coarse"].value == 3
    assert by_key["ch09.eta.n_tau_cap"].value == 2 and by_key["ch09.eta.n_tau_bound"].value == 1 and by_key["ch09.eta.n_tau_measured"].value == 2
    assert by_key["ch09.eta.n_off_era"].value == 1 and by_key["ch09.eta.n_gain_archive"].value == 1
    assert by_key["ch09.eta.rho.ch33"].source == {"table": "tolerance_eta.tex", "row": {"channel": 33}, "column": "rho"}

    # inputs: the ledger only; notes say what is dashed and why
    assert frag.inputs == run.inputs() and len(frag.inputs) == 7
    notes = "\n".join(frag.notes)
    assert "3 of 6 channels have no selected point" in notes and "2 channels have no point at all" in notes
    assert "dashed plateau: no selected point: ch15, ch16, ch17, ch19, ch33" in notes
    assert "dashed floor_db: floor refused (the block carries no null population): ch15, ch17" in notes
    assert "dashed R_c: no coarse frontier (floor refused): ch15, ch17" in notes and "dashed R_c: no coarse frontier: ch16" in notes
    assert "dashed rho: no diagnostic point: the selector refused before a surface existed: ch15" in notes
    assert "dashed status: no selection section: ch16" in notes and "upper bounds on 3 channels" in notes
    assert "1 channels are evaluated on a verified off era" in notes


def test_write_report_with_the_builder(tmp_path):
    run = core.load_run(_ledger(tmp_path))
    manifest = core.write_report(run, tmp_path / "out", [te.build], commit="d" * 40, generated="2026-09-07T09:00:00+00:00")
    art = manifest["artifacts"][0]
    assert art["name"] == "tolerance_eta" and art["label"] == "tab:tolerance:eta" and art["count"] == len(te.build(run).numbers)
    doc = json.loads((tmp_path / "out" / "numbers" / "tolerance_eta.numbers.json").read_text())
    assert doc["producer"]["script"] == "rfisher_results.archive.report.tolerance_eta"
    assert len(doc["inputs"]) == 7 and all(i["sha256"] for i in doc["inputs"])
    assert (tmp_path / "out" / "tables" / "tolerance_eta.tex").read_text() == te.build(run).tex


@pytest.mark.skipif(not (REAL_RUN / "ledger" / "run.json").is_file(), reason="the v5 archive results are not on this machine")
def test_real_run_renders_23_rows_without_duplicate_keys():
    run = core.load_run(REAL_RUN)
    frag = te.build(run)
    rows = _rows(frag)
    assert len(rows) == 23 and [r[0] for r in rows] == [str(c) for c in range(14, 37)]
    doc = nb.NumbersDocument.new(frag.name, repository="r", commit="c", script="s", generated="g")
    for number in frag.numbers:
        doc.add(number)                       # raises on a duplicate key
    by_key = {n.key: n for n in frag.numbers}
    channels = range(14, 37)
    refused = [15, 28, 30, 36]                # no floor for frames without a shelf estimate: no surface, no point
    assert by_key["ch09.eta.n_selected"].value == 0 and by_key["ch09.eta.n_diagnostic"].value == 19
    assert by_key["ch09.eta.n_no_point"].value == 4 and by_key["ch09.eta.n_pass"].value == 0 and r"\mathbf" not in frag.tex
    assert sorted(c for c in channels if by_key[f"ch09.eta.status.ch{c:02d}"].value == "refused") == refused
    assert all(by_key[f"ch09.eta.claim_status.ch{c:02d}"].value == "diagnostic" for c in channels if c not in refused)
    assert all(f"ch09.eta.claim_status.ch{c:02d}" not in by_key for c in refused)
    for c in channels:
        if c in refused:
            assert f"ch09.eta.rho.ch{c:02d}" not in by_key and _cells(frag, c)["$R$"] == core.DASH
        else:                                 # every diagnostic point carries its exact eta_q16 and cost; q_rho is derived
            assert by_key[f"ch09.eta.point_basis.ch{c:02d}"].value == "diagnostic"
            assert f"ch09.eta.eta_q16.ch{c:02d}" in by_key and f"ch09.eta.cost.ch{c:02d}" in by_key
            assert by_key[f"ch09.eta.q_rho.ch{c:02d}"].status == "derived"
        assert _cells(frag, c)["plateau"] == core.DASH and by_key[f"ch09.eta.gain_basis.ch{c:02d}"].value == "era"
    assert sorted(c for c in channels if by_key[f"ch09.eta.floor_evidence.ch{c:02d}"].value == "measured") == [19, 20, 26, 27, 32, 35]
    assert sorted(c for c in channels if by_key[f"ch09.eta.floor_evidence.ch{c:02d}"].value == "refused") == [15, 17, 22, 24, 28, 30, 31, 36]
    assert all(f"ch09.eta.floor_db.ch{c:02d}" not in by_key for c in (15, 17, 22, 24, 28, 30, 31, 36))
    assert all(f"ch09.eta.coarse_min_R.ch{c:02d}" not in by_key for c in (15, 17, 22, 24, 28, 30, 31, 36))
    assert by_key["ch09.eta.n_coarse"].value == 15 and by_key["ch09.eta.n_floor_refused"].value == 8
    assert sorted(c for c in channels if by_key[f"ch09.eta.tau_quality.ch{c:02d}"].value == "bound") == [18, 21, 29]
    assert sorted(c for c in channels if by_key[f"ch09.eta.tau_quality.ch{c:02d}"].value == "measured") == [20, 24, 26, 31, 32, 35]
    assert by_key["ch09.eta.n_off_era"].value == 5 and all(_cells(frag, c)["state"].endswith("(off)") for c in (19, 20, 26, 27, 32))
    assert by_key["ch09.eta.chain_gain.ch33"].value == pytest.approx(2054312.0027) and by_key["ch09.eta.chain_gain.ch33"].status == "bounded"
