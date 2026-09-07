"""``calibration_anchors`` and ``calibration_containment``: every column on a synthetic ledger, then the real run."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rfisher_results.archive import numbers as nb
from rfisher_results.archive.report import calibration_anchors as m
from rfisher_results.archive.report import core

REAL_RUN = Path("/home/djg/rail/results/archive_v5_2026-09-07")
_CONT = {"frames": 100, "detected_frames": 90, "edge_distance_hz": 26496.5, "window_aliased_hz": 0.0,
         "dominant_refined_offset_hz": -20.8, "dominant_db": 18.36, "in_span_refined_offset_hz": -20.8,
         "in_span_recovered": True, "peak_abs_median_hz": 39.49, "peak_abs_p90_hz": 420.96, "peak_abs_p99_hz": 14296.9,
         "anchor_lobe_offset_bins": 1.43, "anchor_lobe_disagree": False, "anchor_folds_out_of_span": False,
         "anchor_suspect": False, "lobe_fine_bin": 176, "era": "current era 2018-12..2026-08 (proxy-low)",
         "disposition": "supported", "reasons": ""}
for _k, _f, _e, _s, _m, _r in ((64, 0.962, 0.997, 0.0002, 3030.96, 0.00049), (128, 0.957, 0.996, 0.0007, 1505.08, 0.00023),
                               (256, 0.943, 0.992, 0.0027, 742.14, 0.00196)):
    _CONT.update({f"frames_in_span_{_k}": _f, f"e_{_k}": _e, f"straddle_loss_db_{_k}": _s, f"margin_hz_{_k}": _m,
                  f"ref_contamination_{_k}": _r, f"ref_aliased_{_k}": False})
# the anchor of record: the current era's, plain median of the on cohort (the quiet cohort is not a null)
_ANCHOR = {"label": "current_era", "status": "ok", "method": "median_fallback",
           "fallback_cohort": "on (quiet cohort is not a null)", "anchor_bin": 175, "anchor_rf_offset_hz": -3.725,
           "boot_status": "ok", "boot_rf_hz_q16": -3.725, "boot_rf_hz_q84": -3.725, "boot_mode_mass": 1.0,
           "source": "current_era", "quiet_cohort_is_null": False}
# the selector's anchor: the calibration block's, on-minus-quiet
_CAL = {**_ANCHOR, "label": "calibration", "method": "on_minus_quiet", "fallback_cohort": "", "anchor_bin": 178,
        "anchor_rf_offset_hz": -39.488, "boot_rf_hz_q16": -39.488, "boot_rf_hz_q84": -39.488, "source": "calibration",
        "quiet_cohort_is_null": True}
_SEL = {"status": "no feasible point", "claim_status": "diagnostic", "anchor_bin": 178, "anchor_source": "calibration",
        "anchor_sentinel": ""}
_LOBE = "psd in-span lobe (fine anchor suspect)"


def _record(ch, fid, sections):
    return {"channel": ch, "freq_id": fid, "product": f"{fid}.npz", "product_sha256": "b" * 64, "notes": [],
            "sections": sections}


def _ledger(tmp_path, *, kstar=True):
    ledger = tmp_path / "ledger"
    (ledger / "channels").mkdir(parents=True)
    files = ["channels/ch18_fid783.json", "channels/ch21_fid736.json", "channels/ch33_fid552.json", "channels/ch36_fid506.json"]
    run = {"schema": {"name": "rfisher-archive-ledger", "version": 1}, "generated": "2026-09-07T00:00:00+00:00",
           "producer": {"commit": "a" * 40}, "products": {}, "channels": files, "era_config_digest": "c" * 64}
    (ledger / "run.json").write_text(json.dumps(run))
    # ch18: everything measured on the current era, selector on the calibration block, one era, no marks
    (ledger / files[0]).write_text(json.dumps(_record(18, 783, {
        "anchor": dict(_ANCHOR), "anchor_calibration": dict(_CAL), "anchor_previous": None, "selection": dict(_SEL),
        "containment": dict(_CONT), "era": {"n_eras": 1}})))
    # ch21: on-quiet current era; suspect by bootstrap mode mass alone (no lobe disagreement), so the selector took the
    # PSD in-span lobe; the containment window is aliased (pilot near the coarse-channel edge), references at K = 64/128
    anchor = {**_ANCHOR, "method": "on_minus_quiet", "fallback_cohort": "", "anchor_bin": 112, "anchor_rf_offset_hz": 14.9,
              "boot_rf_hz_q16": 14.9, "boot_rf_hz_q84": 14.9, "boot_mode_mass": 0.3, "quiet_cohort_is_null": True}
    cal = {**_CAL, "anchor_bin": 111, "anchor_rf_offset_hz": 26.8}
    cont = {**_CONT, "edge_distance_hz": 4753.5, "window_aliased_hz": 10246.5, "dominant_refined_offset_hz": -151.5,
            "dominant_db": 20.04, "in_span_refined_offset_hz": -151.5, "anchor_lobe_offset_bins": 0.3,
            "anchor_suspect": True, "lobe_fine_bin": 126, "ref_aliased_64": True, "ref_aliased_128": True}
    (ledger / files[1]).write_text(json.dumps(_record(21, 736, {
        "anchor": anchor, "anchor_calibration": cal, "anchor_previous": None,
        "selection": {**_SEL, "anchor_bin": 126, "anchor_source": _LOBE}, "containment": cont, "era": {"n_eras": 1}})))
    # ch33: previous-era anchor of record (off current era), bootstrap not ok, sentinel with every reason (the anchor
    # disagrees with the lobe and folds onto the out-of-span feature), aliased K = 128 reference, shift
    anchor = {**_ANCHOR, "label": "previous_era", "anchor_bin": 116, "anchor_rf_offset_hz": 89.3,
              "boot_status": "insufficient_blocks", "boot_rf_hz_q16": 89.3, "boot_rf_hz_q84": 113.1, "boot_mode_mass": 0.57,
              "source": "previous_era"}
    cal = {**_CAL, "method": "median_fallback", "fallback_cohort": "on (quiet cohort is not a null)", "anchor_bin": 124,
           "anchor_rf_offset_hz": -6.1, "quiet_cohort_is_null": False}
    previous = {"label": "previous_era", "status": "ok", "anchor_bin": 85, "anchor_rf_offset_hz": 458.81,
                "shift_from_previous_bins": 31}
    cont = {**_CONT, "dominant_refined_offset_hz": -3719.91, "dominant_db": 22.96, "in_span_refined_offset_hz": -29.24,
            "anchor_lobe_offset_bins": 9.94, "anchor_lobe_disagree": True, "anchor_folds_out_of_span": True,
            "anchor_suspect": True, "lobe_fine_bin": 126, "era": "previous era 2018-12..2020-11 (proxy-high) (current era is off)",
            "disposition": "supported with sentinel",
            "reasons": ("stronger out-of-span feature at -3725 Hz; E_128 = 0.008 < E_min = 0.9; K = 128 reference "
                        "contamination 0.195 >= 0.05; fine anchor aliases the out-of-span feature at -3725 Hz by one "
                        "coarse bin; fine anchor +9.9 bins from the PSD in-span lobe"),
            "e_128": 0.008, "ref_contamination_128": 0.195, "ref_aliased_128": True, "ref_contamination_256": 137.4157,
            "margin_hz_256": -12.5}
    (ledger / files[2]).write_text(json.dumps(_record(33, 552, {
        "anchor": anchor, "anchor_calibration": cal, "anchor_previous": previous,
        "selection": {**_SEL, "anchor_bin": 126, "anchor_source": _LOBE, "anchor_sentinel": "fine anchor +9.9 bins from the PSD in-span lobe"},
        "containment": cont, "era": {"n_eras": 4}})))
    # ch36: anchor empty on both blocks, selector on the nominal bin, previous era present but empty, containment absent
    (ledger / files[3]).write_text(json.dumps(_record(36, 506, {
        "anchor": {"status": "empty", "method": "", "anchor_bin": -1, "boot_status": "empty", "source": "current_era"},
        "anchor_calibration": {"status": "empty", "method": "", "anchor_bin": -1, "boot_status": "empty", "source": "calibration"},
        "anchor_previous": {"status": "empty", "anchor_rf_offset_hz": None, "shift_from_previous_bins": None},
        "selection": {**_SEL, "anchor_bin": 62, "anchor_source": "nominal bin"}, "containment": None, "era": {"n_eras": 2}})))
    if kstar:
        (tmp_path / "tables").mkdir()
        (tmp_path / "tables" / "kstar.csv").write_text(
            "e_min,k_star,failing_k,binding_channel,binding_e,sentinels,eligible\n"
            "0.9,128,256,18,0.992,33,18;21;33\n"
            "0.95,64,128,18,0.996,33,18;21;33\n"
            "0.99,,,,,18;21;33,18;21;33\n")
    return tmp_path


def _body(tex: str) -> list[list[str]]:
    """The data rows of the first tabular, split into cells."""
    lines = tex.splitlines()
    rows = []
    for line in lines[lines.index(r"\midrule") + 1:]:
        if line == r"\bottomrule":
            break
        if line == r"\midrule":
            continue
        rows.append([cell.strip() for cell in line[:-len(r" \\")].split(" & ")])
    return rows


def _keys(frag):
    return [n.key for n in frag.numbers]


def _value(frag, key):
    return next(n for n in frag.numbers if n.key == key)


def _mutate(root, name, fn):
    path = root / "ledger" / "channels" / name
    rec = json.loads(path.read_text())
    fn(rec["sections"])
    path.write_text(json.dumps(rec))


def test_reason_codes_and_disposition_text():
    assert m.reason_codes(_CONT["reasons"]) == []
    assert m.reason_codes("stronger out-of-span feature at -3725 Hz; E_128 = 0.008 < E_min = 0.9; K = 128 reference contamination "
                          "0.195 >= 0.05; fine anchor aliases the out-of-span feature at -3725 Hz by one coarse bin; fine anchor "
                          "+9.9 bins from the PSD in-span lobe; something new") == ["oos", "E", "ref", "alias", "lobe", "other"]
    assert m.disposition_text("supported") == "supported" and m.disposition_text("unsupported", "") == "unsupported"
    assert m.disposition_text("supported with sentinel", "E_128 = 0.5 < E_min = 0.9") == "sentinel: E"
    assert m.disposition_text("odd", "") == "odd"


def test_method_text_and_window_aliased():
    assert m.method_text("on_minus_quiet", "") == "on-quiet"
    assert m.method_text("median_fallback", "on (quiet cohort is not a null)") == "median (on)"
    assert m.method_text("median_fallback", "all") == "median (all)" and m.method_text("median_fallback", "") == "median"
    assert m.method_text("other", "x") == "other"
    assert m.window_aliased({"window_aliased_hz": 4128.5}) and not m.window_aliased({"window_aliased_hz": 0.0})
    assert not m.window_aliased({}) and not m.window_aliased({"window_aliased_hz": None})


def test_anchors_every_column(tmp_path):
    run = core.load_run(_ledger(tmp_path))
    frag = m.build(run)
    assert frag.name == "calibration_anchors" and frag.label == "tab:calibration:anchors"
    rows = _body(frag.tex)
    assert len(rows) == 4 and all(len(r) == len(m.ANCHOR_HEADER) for r in rows)
    assert len(m.ANCHOR_ALIGN) == len(m.ANCHOR_HEADER) == 17
    r18, r21, r33, r36 = rows
    assert r18 == ["18", "current", "median (on)", "$175$", "$-3.7$", r"$[-3.7,\,-3.7]$", "cal $178$", "$-20.8$", "$18.4$",
                   "$-20.8$", "$+1.4$", "$39$", "$421$", "$14{,}297$", "supported", "--", "--"]
    assert r21 == ["21", "current", "on-quiet", r"$112^{\mathrm{s}}$", "$14.9$", r"$[14.9,\,14.9]$", "lobe $126$ (cal $111$)",
                   r"$-151.5^{\mathrm{a}}$", "$20.0$", "$-151.5$", "$+0.3$", "$39$", "$421$", "$14{,}297$", "supported", "--", "--"]
    assert r33 == ["33", "previous", "median (on)", r"$116^{\mathrm{s}}$", "$89.3$", "--", "lobe $126$ (cal $124$)", "$-3719.9$",
                   "$23.0$", "$-29.2$", r"$+9.9^{*\mathrm{f}}$", "$39$", "$421$", "$14{,}297$", "sentinel: oos, E, ref, alias, lobe",
                   "$458.8$", "$+31$"]
    assert r36 == ["36", "current", "--", "--", "--", "--", "nominal $62$"] + ["--"] * 10
    keys = _keys(frag)
    assert len(keys) == len(set(keys))
    # the anchor of record
    assert _value(frag, "ch08.anchors.source.ch33").value == "previous_era" and _value(frag, "ch08.anchors.source.ch33").renderings == ("previous",)
    assert _value(frag, "ch08.anchors.method.ch18").value == "median_fallback on (quiet cohort is not a null)"
    assert _value(frag, "ch08.anchors.method.ch18").renderings == ("median (on)",) and _value(frag, "ch08.anchors.method.ch21").renderings == ("on-quiet",)
    n = _value(frag, "ch08.anchors.anchor_rf_offset_hz.ch33")
    assert n.value == 89.3 and n.precision == 1 and n.source == {"table": "calibration_anchors.tex", "row": {"channel": 33},
                                                                 "column": "anchor_rf_offset_hz"}
    assert _value(frag, "ch08.anchors.anchor_bin.ch18").kind == "int" and _value(frag, "ch08.anchors.anchor_bin.ch33").value == 116
    assert "ch08.anchors.boot_rf_hz_q16.ch18" in keys and "ch08.anchors.boot_rf_hz_q16.ch33" not in keys
    assert _value(frag, "ch08.anchors.anchor_suspect.ch21").renderings == ("s",) and "ch08.anchors.anchor_suspect.ch18" not in keys
    # the selector's anchor
    assert _value(frag, "ch08.anchors.calibration_anchor_bin.ch18").value == 178 and _value(frag, "ch08.anchors.selector_anchor_bin.ch18").value == 178
    assert _value(frag, "ch08.anchors.selector_anchor_source.ch18").value == "calibration" and _value(frag, "ch08.anchors.selector_anchor_source.ch18").renderings == ("cal",)
    assert _value(frag, "ch08.anchors.calibration_anchor_bin.ch21").value == 111 and _value(frag, "ch08.anchors.selector_anchor_bin.ch21").value == 126
    assert _value(frag, "ch08.anchors.selector_anchor_source.ch33").value == _LOBE and _value(frag, "ch08.anchors.selector_anchor_source.ch33").renderings == ("lobe",)
    assert _value(frag, "ch08.anchors.selector_anchor_source.ch36").renderings == ("nominal",) and _value(frag, "ch08.anchors.selector_anchor_bin.ch36").value == 62
    assert "ch08.anchors.calibration_anchor_bin.ch36" not in keys
    # the spectrum
    assert _value(frag, "ch08.anchors.window_aliased_hz.ch21").value == 10246.5 and _value(frag, "ch08.anchors.edge_distance_hz.ch21").value == 4753.5
    assert "ch08.anchors.window_aliased_hz.ch18" not in keys and "ch08.anchors.window_aliased_hz.ch33" not in keys
    assert _value(frag, "ch08.anchors.anchor_lobe_disagree.ch33").renderings == ("*",) and "ch08.anchors.anchor_lobe_disagree.ch21" not in keys
    assert _value(frag, "ch08.anchors.anchor_folds_out_of_span.ch33").renderings == ("f",) and "ch08.anchors.anchor_folds_out_of_span.ch21" not in keys
    assert _value(frag, "ch08.anchors.anchor_lobe_offset_bins.ch33").value == 9.94
    assert _value(frag, "ch08.anchors.disposition.ch33").renderings == ("sentinel: oos, E, ref, alias, lobe",)
    assert _value(frag, "ch08.anchors.reasons.ch33").value.startswith("stronger out-of-span") and "ch08.anchors.reasons.ch18" not in keys
    assert _value(frag, "ch08.anchors.peak_abs_p99_hz.ch18").value == 14297
    # the previous era
    assert "ch08.anchors.previous_anchor_rf_offset_hz.ch18" not in keys and _value(frag, "ch08.anchors.shift_from_previous_bins.ch33").value == 31
    assert sorted(k for k in keys if k.endswith(".ch36")) == ["ch08.anchors.selector_anchor_bin.ch36", "ch08.anchors.selector_anchor_source.ch36",
                                                              "ch08.anchors.source.ch36"]
    notes = "\n".join(frag.notes)
    assert "channels 33 have an off current era" in notes and "ch33: insufficient_blocks" in notes
    assert "estimator median (on) on channels 18, 33" in notes
    assert ("fine anchor suspect (bin marked s) on channels 21, 33: ch21: bootstrap mode mass 0.30; "
            "ch33: +9.9 bins from the in-span lobe; folds onto the out-of-span feature") in notes
    assert "selector bin taken from the PSD in-span lobe on channels 21, 33" in notes
    assert "selector bin is the nominal fine bin on channels 36" in notes and "no channel has a selected operating point" in notes
    assert "spectrum window aliased (dom.\\ marked a): ch21: pilot 4754 Hz from the coarse-channel edge, 10246 Hz" in notes
    assert "fine anchor folds onto the out-of-span feature on channels 33" in notes
    assert "one era only on channels 18, 21" in notes and "anchor not measured (status ch36: empty)" in notes and "oos = stronger" in notes
    assert "previous-era anchor not measured (ch36: empty)" in notes and "containment section absent on channels 36" in notes
    assert "selection did not run" not in notes


def test_anchors_absent_cases(tmp_path):
    root = _ledger(tmp_path)
    _mutate(root, "ch18_fid783.json", lambda s: s["containment"].update(
        {"in_span_recovered": False, "in_span_refined_offset_hz": 5.0, "anchor_lobe_offset_bins": None,
         "disposition": "unsupported", "reasons": ""}))
    _mutate(root, "ch21_fid736.json", lambda s: s.update({"selection": None}))                 # selection did not run
    _mutate(root, "ch33_fid552.json", lambda s: s.update({"selection": None, "anchor_calibration": None}))
    _mutate(root, "ch36_fid506.json", lambda s: s.update({"anchor": None, "selection": {**_SEL, "anchor_bin": None}}))
    frag = m.build(core.load_run(root))
    r18, r21, r33, r36 = _body(frag.tex)
    assert r18[9] == "--" and r18[10] == "--" and r18[14] == "unsupported"
    assert r21[6] == "$111$" and r33[6] == "--" and r36[1:7] == ["--"] * 6
    keys = _keys(frag)
    assert "ch08.anchors.in_span_refined_offset_hz.ch18" not in keys
    assert "ch08.anchors.calibration_anchor_bin.ch21" in keys and "ch08.anchors.selector_anchor_bin.ch18" in keys
    assert not [k for k in keys if "selector" in k and not k.endswith(".ch18")]
    assert not [k for k in keys if k.endswith(".ch36")]
    notes = "\n".join(frag.notes)
    assert "no in-span lobe recovered on channels 18" in notes and "selection did not run on channels 21, 33" in notes
    assert "selection carries no anchor bin on channels 36" in notes and "anchor section absent on channels 36" in notes


def test_containment_every_column(tmp_path):
    run = core.load_run(_ledger(tmp_path))
    frag = m.build_containment(run)
    assert frag.name == "calibration_containment" and frag.label == "fig:calibration:containment"
    rows = _body(frag.tex)
    assert len(rows) == 7 and all(len(r) == len(m.containment_header()) for r in rows)
    r18, r21, r33, r36, k90, k95, k99 = rows
    assert r18[:7] == ["18", "supported", "$0.962$", "$0.997$", "$0.00$", "$3{,}031$", "$0.000$"]
    assert r18[7:12] == ["$0.957$", "$0.996$", "$0.00$", "$1{,}505$", "$0.000$"]
    assert r18[12:] == ["$0.943$", "$0.992$", "$0.00$", "$742$", "$0.002$"]
    assert r21[1] == r"supported$^{\mathrm{a}}$" and r21[6] == r"$0.000^{\mathrm{a}}$" and r21[11] == r"$0.000^{\mathrm{a}}$" and r21[16] == "$0.002$"
    assert r33[1] == "sentinel" and r33[8] == "$0.008$" and r33[11] == r"$0.195^{\mathrm{a}}$" and r33[15] == "$-12$" and r33[16] == "$137.416$"
    assert r36 == ["36"] + ["--"] * 16
    assert k90[:2] == [r"$K^\star$ ($E_{\min} = 0.9$)", "3 eligible; sentinel 33"] and k90[8] == r"$K^\star$" and k90[13] == "fails: ch18 ($0.992$)"
    assert k90[2:8] == [""] * 6 and k90[9:13] == [""] * 4 and k90[14:] == [""] * 3
    assert k95[3] == r"$K^\star$" and k95[8] == "fails: ch18 ($0.996$)" and k95[13] == ""
    assert k99[:2] == [r"$K^\star$ ($E_{\min} = 0.99$)", "3 eligible; sentinel 18, 21, 33"] and k99[2:] == [""] * 15
    assert frag.tex.count(r"\midrule") == 2          # header rule and the K* rule
    keys = _keys(frag)
    assert len(keys) == len(set(keys))
    assert _value(frag, "ch08.containment.ref_aliased_128.ch33").renderings == ("a",) and "ch08.containment.ref_aliased_64.ch33" not in keys
    assert sorted(k for k in keys if ".ref_aliased_" in k) == ["ch08.containment.ref_aliased_128.ch21", "ch08.containment.ref_aliased_128.ch33",
                                                               "ch08.containment.ref_aliased_64.ch21"]
    assert _value(frag, "ch08.containment.window_aliased_hz.ch21").value == 10246.5 and "ch08.containment.window_aliased_hz.ch33" not in keys
    assert _value(frag, "ch08.containment.margin_hz_256.ch33").value == -12 and _value(frag, "ch08.containment.e_128.ch18").precision == 3
    assert _value(frag, "ch08.containment.disposition.ch33").renderings == ("sentinel",) and not [k for k in keys if k.endswith(".ch36")]
    assert _value(frag, "ch04.kstar.k_star.emin0.9").value == 128 and _value(frag, "ch04.kstar.failing_k.emin0.9").value == 256
    assert _value(frag, "ch04.kstar.binding_channel.emin0.9").value == 18 and _value(frag, "ch04.kstar.binding_e.emin0.9").value == 0.992
    assert _value(frag, "ch04.kstar.sentinels.emin0.9").value == "33" and _value(frag, "ch04.kstar.eligible_count.emin0.95").value == 3
    assert "ch04.kstar.k_star.emin0.99" not in keys and _value(frag, "ch04.kstar.sentinels.emin0.99").renderings == ("sentinel 18, 21, 33",)
    assert frag.inputs[-1] == tmp_path / "tables" / "kstar.csv" and len(frag.inputs) == 6
    notes = "\n".join(frag.notes)
    assert "K* undefined at E_min = 0.99" in notes and "ch21 K=64, ch21 K=128, ch33 K=128" in notes
    assert "disp.\\ marked a" in notes and "ch21 (10246 Hz aliased, edge 4754 Hz away)" in notes
    assert "containment section absent on channels 36" in notes


def test_containment_without_kstar(tmp_path):
    run = core.load_run(_ledger(tmp_path, kstar=False))
    frag = m.build_containment(run)
    assert len(_body(frag.tex)) == 4 and frag.tex.count(r"\midrule") == 1 and frag.inputs == []
    assert not [k for k in _keys(frag) if k.startswith("ch04.")] and "tables/kstar.csv absent: no K* rows" in frag.notes


def test_write_report_round_trip(tmp_path):
    run = core.load_run(_ledger(tmp_path))
    manifest = core.write_report(run, tmp_path / "out", list(m.BUILDERS), commit="d" * 40, generated="2026-09-07T09:00:00+00:00")
    assert [a["name"] for a in manifest["artifacts"]] == ["calibration_anchors", "calibration_containment"]
    docs = [nb.load_numbers([tmp_path / "out" / "numbers" / f"{a['name']}.numbers.json"]) for a in manifest["artifacts"]]
    assert [len(d) for d in docs] == [a["count"] for a in manifest["artifacts"]]
    assert (tmp_path / "out" / "tables" / "calibration_anchors.tex").read_text().startswith(r"\begin{tabular}{lllrrrlrrrrrrrlrr}")
    assert (tmp_path / "out" / "tables" / "calibration_containment.tex").read_text().startswith(r"\begin{tabular}{llrrrrrrrrrrrrrrr}")


@pytest.mark.skipif(not (REAL_RUN / "ledger" / "run.json").is_file(), reason="real archive run not on this machine")
def test_real_run_renders_23_channels():
    run = core.load_run(REAL_RUN)
    anchors, containment = m.build(run), m.build_containment(run)
    for frag, extra in ((anchors, 0), (containment, 3)):
        rows = _body(frag.tex)
        assert len(rows) == 23 + extra and [r[0] for r in rows[:23]] == [str(c) for c in range(14, 37)]
        keys = _keys(frag)
        assert len(keys) == len(set(keys))
        doc = nb.NumbersDocument.new(frag.name, repository="r", commit="c", script="s", generated="g")
        for n in frag.numbers:
            doc.add(n)                                    # raises on a duplicate key
        assert sorted(int(k.rsplit(".ch", 1)[1]) for k in keys if ".window_aliased_hz." in k) == [21, 32]
    by = {r[0]: r for r in _body(anchors.tex)}
    assert [ch for ch, r in by.items() if r[1] == "previous"] == ["19", "20", "26", "27", "32"]
    assert [ch for ch, r in by.items() if r[2] == "on-quiet"] == ["16", "21", "23", "25", "29"]
    assert by["33"][14] == "sentinel: oos, E, ref, lobe" and by["18"][14] == "supported"
    assert by["18"][6] == "cal $178$" and by["21"][6] == "lobe $126$ (cal $111$)" and by["27"][6] == "cal $246$"
    assert by["14"][15] == "--" and by["33"][15] == "$458.8$" and by["33"][16] == "$+31$" and by["27"][16] == "$-14$"
    assert by["21"][7].endswith(r"^{\mathrm{a}}$") and by["27"][10] == "$+0.0$".replace("+", "")
    assert _value(anchors, "ch08.anchors.anchor_bin.ch33").value == 116 and _value(anchors, "ch08.anchors.calibration_anchor_bin.ch33").value == 124
    assert _value(anchors, "ch08.anchors.selector_anchor_bin.ch33").value == 126
    keys = _keys(anchors)
    assert sorted(int(k.rsplit(".ch", 1)[1]) for k in keys if ".anchor_suspect." in k) == [21, 23, 25, 29, 33]
    assert sorted(int(k.rsplit(".ch", 1)[1]) for k in keys if ".anchor_lobe_disagree." in k) == [21, 23, 25, 29, 33]
    assert not [k for k in keys if ".anchor_folds_out_of_span." in k]
    assert not [k for k in keys if ".selector_anchor_source." in k and _value(anchors, k).value not in ("calibration", _LOBE)]
    assert _value(containment, "ch04.kstar.k_star.emin0.9").value == 128 and _value(containment, "ch04.kstar.binding_channel.emin0.9").value == 23
    aliased = sorted(k for k in _keys(containment) if ".ref_aliased_" in k)
    assert aliased == ["ch08.containment.ref_aliased_128.ch21", "ch08.containment.ref_aliased_64.ch21", "ch08.containment.ref_aliased_64.ch32"]
    notes = "\n".join(anchors.notes)
    assert "channels 19, 20, 26, 27, 32 have an off current era" in notes and "selector bin taken from the PSD in-span lobe on channels 21, 23, 25, 29, 33" in notes
