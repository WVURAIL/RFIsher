"""tab:tolerance:channels from the ledger: every column, the marks, the dashes."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from rfisher_results.archive.report import core
from rfisher_results.archive.report import tolerance_channels as tc

RESULTS = Path(os.environ.get("RFISHER_ARCHIVE_RESULTS", Path.home() / "rail" / "results" / "archive_v5_2026-09-07"))
PER_CHANNEL = 24
BAND = 11


def _ledger(tmp_path):
    ledger = tmp_path / "ledger"
    (ledger / "channels").mkdir(parents=True)
    run = {"schema": {"name": "rfisher-archive-ledger", "version": 1}, "generated": "2026-09-07T00:00:00+00:00",
           "producer": {"commit": "a" * 40}, "products": {"552.npz": "b" * 64, "844.npz": "c" * 64},
           "channels": ["channels/ch33_fid552.json", "channels/ch14_fid844.json"], "era_config_digest": "d" * 64}
    (ledger / "run.json").write_text(json.dumps(run))
    # ch33 as a selected point (the hypothetical the stub was written for): calibration-block values, measured floor,
    # measured tau, fs8 priced, era chain on the current era
    full = {"channel": 33, "freq_id": 552, "product": "552.npz", "product_sha256": "b" * 64, "notes": [], "sections": {
        "geometry": {"pilot_hz": 584309441.0, "allocation_low_mhz": 584.0, "allocation_high_mhz": 590.0},
        "era": {"current_first_month": "2023-12", "current_last_month": "2026-08", "off_era_current": False},
        "chain": {"chain_population": "current era 2023-12..2026-08 (proxy-low): 23695 valid frames", "on_shelf_db": -34.001,
                  "intraday_share": 0.08497, "ground_filter_db": 8.1491, "tau_quality": "measured", "tau_c_minutes": 5.5,
                  "tau_c_high_minutes": 6.1},
        "chain_archive": {"chain_population": "transmitter-on frames of the whole archive", "on_shelf_db": -34.117,
                          "tau_quality": "bounded_above", "tau_c_minutes": 5.0, "tau_c_high_minutes": 5.0},
        "null": {"coarse_frames": 11853, "floor_db": -35.944, "floor_evidence": "measured", "floor_basis": "off era p90"},
        "tolerance": {"z_low": 1.40747, "z_high": 1.43220, "r_tol_fs8": 0.00153, "fs8_status": "published"},
        "selection": {"status": "feasible", "claim_status": "screening", "rho": 2, "eta": 1.05,
                      "masked_fraction_calibration": 0.61234, "r_sys_calibration": 0.0040, "R_calibration": 0.2564,
                      "masked_fraction_evaluation": 0.7, "r_sys_evaluation": 0.005, "R_evaluation": 0.3,
                      "keep_everything_r_sys_calibration": 1.1581, "r_sys_unmasked_calibration": 1.1581,
                      "diagnostic_r_sys": 0.0031, "diagnostic_masked_fraction": 0.7, "diagnostic_R": 0.2,
                      "min_r_sys": 0.0031, "min_r_sys_masked_fraction": 0.7, "min_R": 0.2, "gain_basis": "era chain"},
        "screening": {"screening_class": "recovery candidate", "survey_flag_rate_era": 0.71952}}}
    # ch14 as the run has it: the diagnostic point, a stated floor from the bulk's left side, no chain section, fs8 unpriced
    sparse = {"channel": 14, "freq_id": 844, "product": "844.npz", "product_sha256": "c" * 64, "notes": [], "sections": {
        "geometry": {"pilot_hz": 470309441.0, "allocation_low_mhz": 470.0, "allocation_high_mhz": 476.0},
        "era": {"current_first_month": "2018-12", "current_last_month": "2026-08", "off_era_current": False},
        "chain": None,
        "null": {"coarse_frames": 18032, "floor_db": -42.4669, "floor_evidence": "stated", "floor_basis": "bulk left side (not H0)"},
        "tolerance": {"z_low": 1.98405, "z_high": 2.02214, "r_tol_fs8": None,
                      "fs8_status": "unpriced: no published constant; rebuild the dense bias bank to price"},
        "selection": {"status": "no feasible point", "claim_status": "diagnostic", "rho": None, "eta": None,
                      "masked_fraction_calibration": None, "r_sys_calibration": None, "R_calibration": None,
                      "diagnostic_basis": "least residual on the calibration surface (no feasible point)",
                      "diagnostic_masked_fraction": 0.99778, "diagnostic_r_sys": 185.94187, "diagnostic_R": 9250.8393,
                      "masked_fraction_evaluation": 0.9996, "r_sys_evaluation": 116.4, "R_evaluation": 5791.36,
                      "keep_everything_r_sys_calibration": 12849.898, "r_sys_unmasked_calibration": 12849.898,
                      "min_r_sys": 185.94187, "min_r_sys_masked_fraction": 0.99778, "min_R": 9250.8393, "feasible_points": 0,
                      "gain_basis": "archive-wide chain (era chain refused)"},
        "screening": {"screening_class": "occupancy-wall excision candidate", "survey_flag_rate_era": 0.94931}}}
    (ledger / "channels" / "ch33_fid552.json").write_text(json.dumps(full))
    (ledger / "channels" / "ch14_fid844.json").write_text(json.dumps(sparse))
    return tmp_path


def _channel(number: int, sections: dict) -> core.Channel:
    return core.Channel(number, 1000 - number, f"{1000 - number}.npz", "0" * 64, (), sections, Path(f"ch{number}.json"))


def _numbers(frag: core.Fragment, ch: int) -> dict:
    return {n.key.split(".")[2]: n for n in frag.numbers if n.key.endswith(f".ch{ch}")}


def _rows(tex: str) -> dict[int, list[str]]:
    body = tex.split("\\midrule", 1)[1].split("\\bottomrule")[0]
    rows = [line[:-2].strip() for line in body.strip().splitlines() if line.endswith(r"\\")]
    return {int(r.split(" & ")[0]): r.split(" & ") for r in rows}


def test_sci_and_minutes_formatting():
    assert tc.sci(134.601) == "135" and tc.sci(0.0743) == "0.0743" and tc.sci(0.0) == "0" and tc.sci(None) == "--"
    assert tc.sci(12858.194) == "1.29\\times10^{4}" and tc.sci(2007112.59) == "2.01\\times10^{6}"
    assert tc.sci(0.0009996) == "1.00\\times10^{-3}" and tc.sci(999.6) == "1.00\\times10^{3}"
    assert tc._render(tc.sci(12858.194)) == "1.29x10^{4}" and tc._decimals(tc.sci(12858.194)) is None
    assert tc._decimals("0.0743") == 4 and tc._decimals("135") == 0
    assert tc.minutes(5.0) == "5" and tc.minutes(162.805) == "163" and tc.minutes(9.8795) == "9.88"
    assert tc.minutes(62.052) == "62.1" and tc.minutes(None) == "--"


def test_every_column_on_a_selected_point_and_a_diagnostic_channel(tmp_path):
    run = core.load_run(_ledger(tmp_path))
    frag = tc.build(run)
    assert frag.name == "tolerance_channels" and frag.label == "tab:tolerance:channels"
    rows = _rows(frag.tex)
    assert list(rows) == [14, 33] and len(tc.HEADER) == 18 and all(len(r) == 18 for r in rows.values())
    assert frag.tex.startswith("\\begin{tabular}{" + tc.ALIGN + "}")
    assert frag.tex.count("\\midrule") == 2          # header rule and the half-band break between 14 and 33

    # the selected point: calibration-block values, no dagger; measured floor unmarked; tau measured; fs8 priced
    assert rows[33] == ["33", "584--590", "1.407--1.432", "$584.309$", "2023-12--2026-08", "$0.720$", "$0.612$", "$-34.0$",
                        "$11{,}853$", "$-35.9$", "$0.085$", "$8.1$", "$5.5$", "$1.16$", "$4.00\\times10^{-3}$", "$0.256$",
                        "$2.61$", "recovery candidate"]
    n33 = _numbers(frag, 33)
    assert len(n33) == PER_CHANNEL
    assert n33["point_basis"].value == "selected" and n33["point_basis"].status == "measured"
    assert n33["masked_fraction"].value == 0.61234 and n33["masked_fraction"].status == "measured"
    assert n33["r_proxy"].value == 0.0040 and n33["r_proxy"].status == "measured" and n33["r_proxy"].precision is None
    assert n33["R_dilation"].value == 0.2564 and n33["R_dilation"].status == "measured" and n33["R_dilation"].precision == 3
    assert n33["R_fs8"].value == pytest.approx(0.0040 / 0.00153) and n33["R_fs8"].renderings == ("2.61",)
    assert n33["tau_c_minutes"].value == 5.5 and n33["tau_c_minutes"].status == "measured" and n33["tau_c_minutes"].precision == 1
    assert n33["tau_quality"].value == "measured"
    assert n33["floor_db"].status == "measured" and n33["floor_evidence"].renderings == ("measured", "off era p90")
    assert n33["null_frames"].kind == "int" and n33["null_frames"].value == 11853
    assert n33["pilot_mhz"].value == pytest.approx(584.309441) and n33["pilot_mhz"].precision == 3
    assert n33["allocation_low_mhz"].value == 584.0 and n33["z_high"].value == 1.43220
    assert n33["era_first_month"].value == "2023-12" and n33["era_last_month"].kind == "text"
    assert n33["chain_basis"].value == "current era" and n33["chain_basis"].renderings[1].startswith("current era 2023-12")
    assert n33["screening_class"].renderings == ("recovery candidate", "recovery candidate")
    assert n33["r_keep"].value == 1.1581 and n33["r_keep"].status == "measured" and n33["r_keep"].renderings == ("1.16",)
    assert n33["r_proxy"].source == {"table": "tolerance_channels.tex", "row": {"channel": 33}, "column": "r_proxy"}

    # the diagnostic channel: least-residual point with a dagger, stated floor marked s, no chain section, fs8 unpriced
    assert rows[14] == ["14", "470--476", "1.984--2.022", "$470.309$", "2018-12--2026-08", "$0.949$", "${0.998}^{\\dagger}$",
                        "--", "$18{,}032$", "${-42.5}^{\\mathrm{s}}$", "--", "--", "--", "$1.28\\times10^{4}$",
                        "$186$", "$9.25\\times10^{3}$", "unpriced", "occupancy wall"]
    n14 = _numbers(frag, 14)
    assert len(n14) == PER_CHANNEL
    assert n14["point_basis"].value == "diagnostic" and n14["masked_fraction"].value == 0.99778
    assert n14["masked_fraction"].status == "derived" and n14["r_proxy"].value == 185.94187 and n14["R_dilation"].value == 9250.8393
    assert n14["r_proxy"].status == "bounded" and n14["R_dilation"].status == "bounded"     # no chain: tau_c is not measured
    assert n14["r_keep"].value == 12849.898 and n14["r_keep"].status == "bounded" and n14["r_keep"].renderings == ("1.28x10^{4}",)
    assert n14["R_fs8"].value is None and n14["R_fs8"].status == "pending" and n14["R_fs8"].renderings == ("unpriced",)
    assert n14["floor_db"].status == "derived" and n14["floor_evidence"].renderings == ("stated", "bulk left side (not H0)")
    for col in ("on_shelf_db", "intraday_share", "ground_filter_db", "tau_c_minutes", "chain_basis"):
        assert n14[col].value is None and n14[col].renderings == ("--",), col
    assert n14["tau_quality"].value is None and n14["tau_c_minutes"].status == "pending"
    assert n14["screening_class"].value == "occupancy-wall excision candidate"
    assert n14["screening_class"].renderings == ("occupancy-wall excision candidate", "occupancy wall")

    # band-level counts and the notes
    band = {n.key.split(".")[2]: n.value for n in frag.numbers if n.key.count(".") == 2}
    assert band == {"n_channels": 2, "n_point_selected": 1, "n_point_diagnostic": 1, "n_floor_measured": 1, "n_floor_stated": 1,
                    "n_floor_refused": 0, "n_tau_measured": 1, "n_tau_bounded": 0, "n_tau_refused": 0, "n_fs8_priced": 1,
                    "n_off_era": 0}
    keys = [n.key for n in frag.numbers]
    assert len(keys) == len(set(keys)) and len(keys) == 2 * PER_CHANNEL + BAND
    assert all(k.startswith("ch09.channels.") for k in keys)
    assert any("1 of 2 channels carry a selected operating point (ch33)" in note for note in frag.notes)
    assert any("gain basis: the residual is priced on the archive-wide chain (era chain refused) on ch14" in note for note in frag.notes)
    assert any("ch14 on_shelf_db: chain.on_shelf_db absent (no chain section)" in note for note in frag.notes)
    assert any("ch14 tau_c_minutes" in note for note in frag.notes)
    assert not any(note.startswith("dashed:") and "ch33" in note for note in frag.notes)
    assert not any("floor refused beside a point" in note for note in frag.notes)


def test_refused_selector_bounded_tau_and_refused_floor():
    frag = core.Fragment(tc.NAME, tc.LABEL, "")
    absent: list[str] = []
    # ch15 as the run has it: the selector refused (no floor for frames without a shelf estimate), floor refused, tau refused
    refused = _channel(15, {"chain": {"chain_population": "current era 2025-05..2026-08 (proxy-high): 15496 valid frames",
                                      "on_shelf_db": -26.98, "intraday_share": 0.09, "ground_filter_db": 10.3,
                                      "tau_quality": "refused", "tau_c_minutes": None, "tau_c_high_minutes": None},
                            "null": {"coarse_frames": 7748, "floor_db": None, "floor_evidence": "refused", "floor_basis": "none",
                                     "floor_population": "no off era; bulk centre 1.31 is beyond 0.1 of mu_0: the block carries no null population"},
                            "tolerance": {"r_tol_fs8": 0.0016, "fs8_status": "published"},
                            "selection": {"status": "refused", "refusal": "no floor for frames without a shelf estimate", "claim_status": "",
                                          "diagnostic_r_sys": None, "diagnostic_R": None, "diagnostic_masked_fraction": None,
                                          "min_r_sys": None, "min_R": None, "keep_everything_r_sys_calibration": None},
                            "screening": {"screening_class": "occupancy-wall excision candidate"}})
    cells = tc._row(refused, frag, absent)
    assert cells[6] == "--" and cells[9] == "--" and cells[12] == "cap" and cells[13:17] == ["--"] * 4
    assert cells[7] == "$-27.0$" and cells[17] == "occupancy wall" and cells[1] == "--" and cells[4] == "--"
    n = _numbers(frag, 15)
    assert len(n) == PER_CHANNEL and n["point_basis"].value == "absent"
    assert n["floor_db"].value is None and n["floor_db"].status == "refused" and n["floor_evidence"].value == "refused"
    for col in ("masked_fraction", "r_keep", "r_proxy", "R_dilation", "R_fs8"):
        assert n[col].value is None and n[col].status == "refused" and n[col].renderings == ("--",), col
    assert n["tau_c_minutes"].status == "refused" and n["tau_c_minutes"].renderings == ("cap",)
    assert any(a == "ch15 r_proxy: selector refused: no floor for frames without a shelf estimate" for a in absent)
    assert any(a.startswith("ch15 floor_db: floor refused (no off era; bulk centre 1.31") for a in absent)
    assert any("ch15 R_fs8: f sigma_8 tolerance published but r_proxy undefined: selector refused" in a for a in absent)
    assert any("ch15 allocation_low_mhz" in a for a in absent) and any("ch15 era_first_month" in a for a in absent)

    # a bounded tau with a diagnostic point on an older ledger (min_* only, no diagnostic_* keys): still a diagnostic point
    bounded = _channel(29, {"chain": {"tau_quality": "bounded_above", "tau_c_minutes": 5.0, "tau_c_high_minutes": 5.0},
                            "tolerance": {"r_tol_fs8": 0.0016, "fs8_status": "published"},
                            "selection": {"status": "no feasible point", "claim_status": "diagnostic", "min_r_sys": 0.0602,
                                          "min_R": 4.30, "min_r_sys_masked_fraction": 0.99822, "r_sys_unmasked_calibration": 2.83},
                            "screening": {"screening_class": "measurement-bound on tau_c"}})
    cells = tc._row(bounded, frag, absent)
    assert cells[12] == "$\\le 5$" and cells[6] == "${0.998}^{\\dagger}$" and cells[13] == "$2.83$" and cells[14] == "$0.0602$"
    assert cells[15] == "$4.30$" and cells[16] == "$37.6$" and cells[17] == "bound: $\\tau_c$"
    n = _numbers(frag, 29)
    assert n["tau_c_minutes"].value == 5.0 and n["tau_c_minutes"].status == "bounded" and n["tau_c_minutes"].precision == 0
    assert n["point_basis"].value == "diagnostic" and n["r_proxy"].status == "bounded" and n["r_keep"].value == 2.83
    assert n["screening_class"].renderings == ("measurement-bound on tau_c", "bound: tau_c")
    assert not any(a.startswith("ch29 r_") for a in absent)

    # a bounded tau whose bound carries no minutes; no selection section at all
    cells = tc._row(_channel(23, {"chain": {"tau_quality": "bounded_above"}}), frag, absent)
    assert cells[12] == "--" and cells[17] == "--"
    n = _numbers(frag, 23)
    assert n["tau_c_minutes"].value is None and n["tau_c_minutes"].status == "bounded" and n["point_basis"].value == "absent"
    assert n["r_keep"].value is None and any("ch23 r_keep: selection.keep_everything_r_sys_calibration absent (no selection section)" in a for a in absent)
    assert any("ch23 R_fs8: tolerance.fs8_status absent" in a for a in absent)
    assert tc.point(_channel(1, {})).basis == "absent" and tc.point(_channel(1, {})).why == "no selection section"
    assert tc.point(_channel(2, {"selection": {"status": "no evaluable point"}})).why.startswith("selection status 'no evaluable point'")


def test_off_era_channel_prints_the_previous_era_chain_and_the_note():
    # ch19 as the run has it: current era off, chain on the previous on era, measured off-era floor, tau refused
    off = _channel(19, {"geometry": {"pilot_hz": 500309441.0, "allocation_low_mhz": 500.0, "allocation_high_mhz": 506.0},
                        "era": {"current_first_month": "2024-12", "current_last_month": "2026-04", "off_era_current": True},
                        "chain": {"chain_population": "previous era 2024-09..2024-11 (proxy-high) (current era is off): 1489 valid frames",
                                  "on_shelf_db": -6.7886, "intraday_share": 0.00427, "ground_filter_db": 23.506, "tau_quality": "refused"},
                        "null": {"coarse_frames": 6453, "floor_db": -32.6235, "floor_evidence": "measured", "floor_basis": "off era p90"},
                        "tolerance": {"z_low": 1.80713, "z_high": 1.84081, "r_tol_fs8": None, "fs8_status": "unpriced: no published constant"},
                        "selection": {"status": "no feasible point", "claim_status": "diagnostic", "diagnostic_masked_fraction": 0.86797,
                                      "diagnostic_r_sys": 1122.846, "diagnostic_R": 93570.52, "keep_everything_r_sys_calibration": 1468.365,
                                      "gain_basis": "era chain"},
                        "screening": {"screening_class": "off-era", "survey_flag_rate_era": 0.86574}})
    # ch17 as the run has it: floor refused but every calibration frame has a shelf estimate, so a point exists
    unfloored = _channel(17, {"chain": {"chain_population": "current era 2025-10..2026-08 (proxy-high): 12601 valid frames",
                                        "on_shelf_db": -5.38, "intraday_share": 0.0103, "ground_filter_db": 19.76, "tau_quality": "refused"},
                              "era": {"off_era_current": False},
                              "null": {"coarse_frames": 6308, "floor_db": None, "floor_evidence": "refused", "floor_basis": "none",
                                       "floor_population": "no off era; bulk centre 44.5 is beyond 0.1 of mu_0: the block carries no null population"},
                              "selection": {"status": "no feasible point", "claim_status": "diagnostic", "diagnostic_masked_fraction": 0.99524,
                                            "diagnostic_r_sys": 570574.03, "diagnostic_R": 28386767.5, "keep_everything_r_sys_calibration": 604055.5},
                              "screening": {"screening_class": "occupancy-wall excision candidate", "survey_flag_rate_era": 1.0}})
    run = core.Run(Path("nowhere"), {"producer": {"commit": "f" * 40}}, (unfloored, off))
    frag = tc.build(run)
    rows = _rows(frag.tex)
    assert list(rows) == [17, 19]
    assert rows[19] == ["19", "500--506", "1.807--1.841", "$500.309$", "2024-12--2026-04", "$0.866$", "${0.868}^{\\dagger}$", "$-6.8$",
                        "$6{,}453$", "$-32.6$", "$0.004$", "$23.5$", "cap", "$1.47\\times10^{3}$", "$1.12\\times10^{3}$",
                        "$9.36\\times10^{4}$", "unpriced", "off-era"]
    assert rows[17][9] == "--" and rows[17][14] == "$5.71\\times10^{5}$" and rows[17][16] == "--"
    n19 = _numbers(frag, 19)
    assert n19["chain_basis"].value == "previous era" and n19["chain_basis"].renderings[1].startswith("previous era 2024-09")
    assert n19["floor_db"].status == "measured" and n19["floor_evidence"].renderings == ("measured", "off era p90")
    assert _numbers(frag, 17)["chain_basis"].value == "current era"
    band = {n.key.split(".")[2]: n.value for n in frag.numbers if n.key.count(".") == 2}
    assert band["n_off_era"] == 1 and band["n_floor_refused"] == 1 and band["n_floor_measured"] == 1 and band["n_tau_refused"] == 2
    assert any(note.startswith("chain: ") and "transmitter-off era (ch19)" in note for note in frag.notes)
    assert any(note.startswith("floor refused beside a point on ch17:") for note in frag.notes)
    assert any(note == "gain basis: every residual is priced on the era chain (selection.gain_basis)" for note in frag.notes)
    assert frag.tex.count("\\midrule") == 1        # no half-band break: both channels are below 26


def test_write_report_carries_the_fragment(tmp_path):
    run = core.load_run(_ledger(tmp_path))
    manifest = core.write_report(run, tmp_path / "out", [tc.build], commit="e" * 40, generated="2026-09-07T01:00:00+00:00")
    art = manifest["artifacts"][0]
    assert art["label"] == "tab:tolerance:channels" and art["count"] == 2 * PER_CHANNEL + BAND
    assert art["table"] == "tables/tolerance_channels.tex"
    doc = json.loads((tmp_path / "out" / "numbers" / "tolerance_channels.numbers.json").read_text())
    assert doc["producer"]["script"] == "rfisher_results.archive.report.tolerance_channels" and len(doc["inputs"]) == 3


@pytest.mark.skipif(not (RESULTS / "ledger" / "run.json").is_file(), reason="the 2026-09-07 archive run is not on this machine")
def test_real_run_renders_23_rows_with_unique_keys(tmp_path):
    run = core.load_run(RESULTS)
    core.write_report(run, tmp_path, [tc.build], commit=run.commit, generated="2026-09-07T09:00:00+00:00")
    rows = _rows((tmp_path / "tables" / "tolerance_channels.tex").read_text())
    assert list(rows) == list(range(14, 37)) and all(len(r) == 18 for r in rows.values())
    doc = json.loads((tmp_path / "numbers" / "tolerance_channels.numbers.json").read_text())
    keys = [n["key"] for n in doc["numbers"]]
    assert len(keys) == len(set(keys)) == 23 * PER_CHANNEL + BAND and all(k.startswith("ch09.channels.") for k in keys)
    by_key = {n["key"]: n for n in doc["numbers"]}

    def channels(column, value):
        return [ch for ch in range(14, 37) if by_key[f"ch09.channels.{column}.ch{ch}"]["value"] == value]

    # the facts of this run: no selected point anywhere; the selector refused on 15/28/30/36; floors measured on the six
    # off-population channels and refused on eight; tau_c measured on six, bounded on three; fs8 priced on 27-36
    assert channels("point_basis", "selected") == [] and channels("point_basis", "absent") == [15, 28, 30, 36]
    assert channels("point_basis", "diagnostic") == [ch for ch in range(14, 37) if ch not in (15, 28, 30, 36)]
    assert channels("floor_evidence", "measured") == [19, 20, 26, 27, 32, 35]
    assert channels("floor_evidence", "refused") == [15, 17, 22, 24, 28, 30, 31, 36]
    assert channels("tau_quality", "measured") == [20, 24, 26, 31, 32, 35] and channels("tau_quality", "bounded_above") == [18, 21, 29]
    assert channels("chain_basis", "previous era") == [19, 20, 26, 27, 32]
    assert rows[23][12] == "cap" and rows[29][12] == "$\\le 5$" and rows[33][12] == "cap" and rows[26][12] == "$9.88$"
    assert rows[14][16] == "unpriced" and rows[27][16] != "unpriced" and rows[33][6] == "${0.997}^{\\dagger}$"
    assert rows[15][13:16] == ["--"] * 3 and rows[15][16] == "unpriced" and rows[28][13:17] == ["--"] * 4
    assert rows[17][9] == "--" and rows[17][14] != "--"
    band = {k.split(".")[2]: n["value"] for k, n in by_key.items() if k.count(".") == 2}
    assert band == {"n_channels": 23, "n_point_selected": 0, "n_point_diagnostic": 19, "n_floor_measured": 6, "n_floor_stated": 9,
                    "n_floor_refused": 8, "n_tau_measured": 6, "n_tau_bounded": 3, "n_tau_refused": 14, "n_fs8_priced": 10,
                    "n_off_era": 5}
    notes = tc.build(run).notes
    dashed = [note for note in notes if note.startswith("dashed:")]
    assert {note.split()[1] for note in dashed} == {"ch15", "ch17", "ch22", "ch24", "ch28", "ch30", "ch31", "ch36"}
    assert any(note.startswith("floor refused beside a point on ch17, ch22, ch24, ch31:") for note in notes)
