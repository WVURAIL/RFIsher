"""``calibration_anchors``, its Appendix C ledger and ``calibration_containment``: every column on a synthetic
ledger, the widths the page needs, then the real run."""
from __future__ import annotations

import json
import re
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
# the columns the ch08 stub names (Section 8, tab:calibration:anchors), and the evidence that moved to Appendix C
STUB_COLUMNS = ("ch", "estimator", "bin", "f_a", "boot", "dom_hz", "dom_db", "p50", "p90", "p99", "disposition", "prev")
MOVED_COLUMNS = ("era", "shift", "selector", "in_span", "delta", "reasons")


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


def _tabulars(tex: str) -> list[str]:
    return re.findall(r"\\begin\{tabular\}.*?\\end\{tabular\}", tex, re.S)


def _body(tex: str, panel: int = 0) -> list[list[str]]:
    """The data rows of the ``panel``-th tabular, split into cells."""
    lines = _tabulars(tex)[panel].splitlines()
    rows = []
    for line in lines[lines.index(r"\midrule") + 1:]:
        if line == r"\bottomrule":
            break
        if line == r"\midrule":
            continue
        rows.append([cell.strip() for cell in line[:-len(r" \\")].split(" & ")])
    return rows


def _header(tex: str, panel: int = 0) -> list[str]:
    lines = _tabulars(tex)[panel].splitlines()
    return [cell.strip() for cell in lines[lines.index(r"\toprule") + 1][:-len(r" \\")].split(" & ")]


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


def test_column_split_is_the_stub_and_its_ledger():
    """The chapter prints the stub's columns and the channel; the ledger prints the rest, and nothing is lost."""
    assert m.ANCHOR_COLUMNS == STUB_COLUMNS and m.LEDGER_COLUMNS == ("ch",) + MOVED_COLUMNS
    assert len(m.ANCHOR_ALIGN) == len(m.ANCHOR_HEADER) == len(m.ANCHOR_COLUMNS) == 12
    assert len(m.LEDGER_ALIGN) == len(m.LEDGER_HEADER) == len(m.LEDGER_COLUMNS) == 7
    assert set(m.ANCHOR_COLUMNS) | set(m.LEDGER_COLUMNS) == set(STUB_COLUMNS) | set(MOVED_COLUMNS)
    assert set(m.ANCHOR_COLUMNS) & set(m.LEDGER_COLUMNS) == {"ch"}
    assert m.BUILDERS == (m.build, m.build_ledger, m.build_containment)


def test_anchors_prints_the_stub_columns(tmp_path):
    run = core.load_run(_ledger(tmp_path))
    frag = m.build(run)
    assert frag.name == "calibration_anchors" and frag.label == "tab:calibration:anchors"
    assert _header(frag.tex) == ["ch", "estimator", "bin", r"$\widehat f_a$ (Hz)", r"$[q_{16}, q_{84}]$ (Hz)",
                                "dom.\\ (Hz)", "dom.\\ (dB)", r"$|\delta f|_{50}$ (Hz)", r"$|\delta f|_{90}$ (Hz)",
                                r"$|\delta f|_{99}$ (Hz)", "disposition", "prev.\\ (Hz)"]
    rows = _body(frag.tex)
    assert len(_tabulars(frag.tex)) == 1 and len(rows) == 4 and all(len(r) == len(m.ANCHOR_HEADER) for r in rows)
    r18, r21, r33, r36 = rows
    assert r18 == ["18", "median (on)", "$175$", "$-3.7$", r"$[-3.7,\,-3.7]$", "$-20.8$", "$18.4$", "$39$", "$421$",
                   "$14{,}297$", "supported", "--"]
    assert r21 == ["21", "on-quiet", r"$112^{\mathrm{s}}$", "$14.9$", r"$[14.9,\,14.9]$", r"$-151.5^{\mathrm{a}}$",
                   "$20.0$", "$39$", "$421$", "$14{,}297$", "supported", "--"]
    # ch33's anchor of record is the previous era's: f_a carries the p mark, and the disposition prints the word alone
    assert r33 == ["33", "median (on)", r"$116^{\mathrm{s}}$", r"$89.3^{\mathrm{p}}$", "--", "$-3719.9$", "$23.0$",
                   "$39$", "$421$", "$14{,}297$", "sentinel", "$458.8$"]
    assert r36 == ["36"] + ["--"] * 11
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
    # the spectrum
    assert _value(frag, "ch08.anchors.window_aliased_hz.ch21").value == 10246.5 and _value(frag, "ch08.anchors.edge_distance_hz.ch21").value == 4753.5
    assert "ch08.anchors.window_aliased_hz.ch18" not in keys and "ch08.anchors.window_aliased_hz.ch33" not in keys
    assert _value(frag, "ch08.anchors.peak_abs_p99_hz.ch18").value == 14297
    # the disposition prints the word; the number keeps the reason rendering the prose may quote
    assert _value(frag, "ch08.anchors.disposition.ch33").renderings == ("sentinel", "sentinel: oos, E, ref, alias, lobe")
    assert _value(frag, "ch08.anchors.disposition.ch18").renderings == ("supported",)
    assert _value(frag, "ch08.anchors.previous_anchor_rf_offset_hz.ch33").value == 458.81
    assert "ch08.anchors.previous_anchor_rf_offset_hz.ch18" not in keys
    notes = "\n".join(frag.notes)
    assert m.MOVED_NOTE in frag.notes and "marked p on f_a" in notes
    assert "channels 33 have an off current era" in notes and "ch33: insufficient_blocks" in notes
    assert "estimator median (on) on channels 18, 33" in notes
    assert ("fine anchor suspect (bin marked s) on channels 21, 33: ch21: bootstrap mode mass 0.30; "
            "ch33: +9.9 bins from the in-span lobe; folds onto the out-of-span feature") in notes
    assert "disposition reason codes are printed by the companion ledger, not here: ch33: oos, E, ref, alias, lobe" in notes
    assert "one era only on channels 18, 21" in notes and "anchor not measured (status ch36: empty)" in notes and "oos = stronger" in notes
    assert "previous-era anchor not measured (ch36: empty)" in notes and "containment section absent on channels 36" in notes
    assert "spectrum window aliased (dom.\\ marked a): ch21: pilot 4754 Hz from the coarse-channel edge, 10246 Hz" in notes
    assert m.LEDGER_LABEL in notes


def test_anchors_keys_the_moved_columns_it_no_longer_prints(tmp_path):
    """Every number the wide table emitted is still emitted, with the same key, printed or not."""
    frag = m.build(core.load_run(_ledger(tmp_path)))
    keys = _keys(frag)
    printed = frag.tex
    for key, value in (("ch08.anchors.source.ch18", "current_era"),
                       ("ch08.anchors.selector_anchor_source.ch33", _LOBE),
                       ("ch08.anchors.in_span_refined_offset_hz.ch33", -29.24),
                       ("ch08.anchors.anchor_lobe_offset_bins.ch33", 9.94),
                       ("ch08.anchors.shift_from_previous_bins.ch33", 31)):
        assert _value(frag, key).value == value
    assert _value(frag, "ch08.anchors.calibration_anchor_bin.ch18").value == 178 and _value(frag, "ch08.anchors.selector_anchor_bin.ch18").value == 178
    assert _value(frag, "ch08.anchors.selector_anchor_source.ch18").value == "calibration" and _value(frag, "ch08.anchors.selector_anchor_source.ch18").renderings == ("cal",)
    assert _value(frag, "ch08.anchors.calibration_anchor_bin.ch21").value == 111 and _value(frag, "ch08.anchors.selector_anchor_bin.ch21").value == 126
    assert _value(frag, "ch08.anchors.selector_anchor_source.ch36").renderings == ("nominal",) and _value(frag, "ch08.anchors.selector_anchor_bin.ch36").value == 62
    assert "ch08.anchors.calibration_anchor_bin.ch36" not in keys
    assert _value(frag, "ch08.anchors.anchor_lobe_disagree.ch33").renderings == ("*",) and "ch08.anchors.anchor_lobe_disagree.ch21" not in keys
    assert _value(frag, "ch08.anchors.anchor_folds_out_of_span.ch33").renderings == ("f",) and "ch08.anchors.anchor_folds_out_of_span.ch21" not in keys
    assert _value(frag, "ch08.anchors.reasons.ch33").value.startswith("stronger out-of-span") and "ch08.anchors.reasons.ch18" not in keys
    assert _value(frag, "ch08.anchors.reasons.ch33").source["column"] == "reasons"
    assert sorted(k for k in keys if k.endswith(".ch36")) == ["ch08.anchors.selector_anchor_bin.ch36", "ch08.anchors.selector_anchor_source.ch36",
                                                              "ch08.anchors.source.ch36"]
    # none of those cells is in the chapter table: the ledger prints them
    assert "cal $178$" not in printed and "lobe $126$" not in printed and "$+31$" not in printed and "previous" not in printed


def test_ledger_prints_the_moved_columns_and_keys_none(tmp_path):
    run = core.load_run(_ledger(tmp_path))
    frag = m.build_ledger(run)
    assert frag.name == "calibration_anchors_ledger" and frag.label == "tab:archive:calibration_anchors"
    assert _header(frag.tex) == ["ch", "era", "shift (bins)", "selector bin", "in-span (Hz)", r"$\Delta$ (bins)", "reasons"]
    rows = _body(frag.tex)
    assert len(_tabulars(frag.tex)) == 1 and len(rows) == 4 and all(len(r) == len(m.LEDGER_HEADER) for r in rows)
    r18, r21, r33, r36 = rows
    assert r18 == ["18", "current", "--", "cal $178$", "$-20.8$", "$+1.4$", "--"]
    assert r21 == ["21", "current", "--", "lobe $126$ (cal $111$)", "$-151.5$", "$+0.3$", "--"]
    assert r33 == ["33", "previous", "$+31$", "lobe $126$ (cal $124$)", "$-29.2$", r"$+9.9^{*\mathrm{f}}$",
                   "oos, E, ref, alias, lobe"]
    assert r36 == ["36", "current", "--", "nominal $62$", "--", "--", "--"]
    # one row per channel, in the chapter table's order, and no number of its own
    assert [r[0] for r in rows] == [r[0] for r in _body(m.build(run).tex)]
    assert frag.numbers == [] and frag.inputs == []
    notes = "\n".join(frag.notes)
    assert "no number is keyed here: every cell is keyed by the chapter fragment as ch08.anchors.<column>.chNN" in notes
    assert "tab:calibration:anchors leaves out" in notes and "oos = stronger" in notes
    assert "selector bin taken from the PSD in-span lobe on channels 21, 33" in notes
    assert "selector bin is the nominal fine bin on channels 36" in notes and "no channel has a selected operating point" in notes
    assert "channels 33 have an off current era" in notes and "one era only on channels 18, 21" in notes
    assert "fine anchor folds onto the out-of-span feature on channels 33" in notes
    assert "containment section absent on channels 36" in notes and "selection did not run" not in notes


def test_anchors_absent_cases(tmp_path):
    root = _ledger(tmp_path)
    _mutate(root, "ch18_fid783.json", lambda s: s["containment"].update(
        {"in_span_recovered": False, "in_span_refined_offset_hz": 5.0, "anchor_lobe_offset_bins": None,
         "disposition": "unsupported", "reasons": ""}))
    _mutate(root, "ch21_fid736.json", lambda s: s.update({"selection": None}))                 # selection did not run
    _mutate(root, "ch33_fid552.json", lambda s: s.update({"selection": None, "anchor_calibration": None}))
    _mutate(root, "ch36_fid506.json", lambda s: s.update({"anchor": None, "selection": {**_SEL, "anchor_bin": None}}))
    run = core.load_run(root)
    frag, ledger = m.build(run), m.build_ledger(run)
    r18, r21, r33, r36 = _body(frag.tex)
    assert r18[10] == "unsupported" and r36 == ["36"] + ["--"] * 11
    l18, l21, l33, l36 = _body(ledger.tex)
    assert l18[4] == "--" and l18[5] == "--" and l18[6] == "--"            # in-span not recovered, Delta undefined
    assert l21[3] == "$111$" and l33[3] == "--" and l36[1:] == ["--"] * 6  # the calibration block's bin, untagged
    keys = _keys(frag)
    assert "ch08.anchors.in_span_refined_offset_hz.ch18" not in keys
    assert "ch08.anchors.calibration_anchor_bin.ch21" in keys and "ch08.anchors.selector_anchor_bin.ch18" in keys
    assert not [k for k in keys if "selector" in k and not k.endswith(".ch18")]
    assert not [k for k in keys if k.endswith(".ch36")]
    for notes in ("\n".join(frag.notes), "\n".join(ledger.notes)):
        assert "anchor section absent on channels 36" in notes or "containment section absent" in notes
    notes = "\n".join(ledger.notes)
    assert "no in-span lobe recovered on channels 18" in notes and "selection did not run on channels 21, 33" in notes
    assert "selection carries no anchor bin on channels 36" in notes
    assert "anchor section absent on channels 36" in "\n".join(frag.notes)


def test_containment_two_panels(tmp_path):
    run = core.load_run(_ledger(tmp_path))
    frag = m.build_containment(run)
    assert frag.name == "calibration_containment" and frag.label == "fig:calibration:containment"
    assert len(_tabulars(frag.tex)) == 2 and frag.tex.count(r"\medskip") == 1
    assert frag.tex.count(r"\emph{") == 2 and frag.tex.startswith(m.CONTAINMENT_PANEL_CAPTIONS[0])
    assert m.CONTAINMENT_PANEL_CAPTIONS[1] in frag.tex and frag.tex.count(r"\midrule") == 3   # two headers, one K* rule
    assert _header(frag.tex, 0) == ["ch", "disp.", "$F_{64}$", "$E_{64}$", "$F_{128}$", "$E_{128}$", "$F_{256}$", "$E_{256}$"]
    assert _header(frag.tex, 1) == ["ch", "$L_{64}$ (dB)", "$M_{64}$ (Hz)", "$C_{64}$", "$L_{128}$ (dB)", "$M_{128}$ (Hz)",
                                    "$C_{128}$", "$L_{256}$ (dB)", "$M_{256}$ (Hz)", "$C_{256}$"]
    assert [len(m.containment_header(p)) == len(m.CONTAINMENT_ALIGN[p]) for p in (0, 1)] == [True, True]
    a, b = _body(frag.tex, 0), _body(frag.tex, 1)
    assert len(a) == 7 and len(b) == 4 and all(len(r) == 8 for r in a) and all(len(r) == 10 for r in b)
    a18, a21, a33, a36, k90, k95, k99 = a
    b18, b21, b33, b36 = b
    assert a18 == ["18", "supported", "$0.962$", "$0.997$", "$0.957$", "$0.996$", "$0.943$", "$0.992$"]
    assert b18 == ["18", "$0.00$", "$3{,}031$", "$0.000$", "$0.00$", "$1{,}505$", "$0.000$", "$0.00$", "$742$", "$0.002$"]
    assert a21[1] == r"supported$^{\mathrm{a}}$" and b21[3] == r"$0.000^{\mathrm{a}}$" and b21[6] == r"$0.000^{\mathrm{a}}$"
    assert a33[1] == "sentinel" and a33[5] == "$0.008$" and b33[6] == r"$0.195^{\mathrm{a}}$" and b33[8] == "$-12$" and b33[9] == "$137.416$"
    assert a36 == ["36"] + ["--"] * 7 and b36 == ["36"] + ["--"] * 9
    # the K* rows stay in the panel that carries the E_K columns they mark, labelled by their E_min
    assert k90[:2] == [r"$E_{\min} = 0.9$", "3 eligible; sentinel 33"] and k90[5] == r"$K^\star$" and k90[7] == "fails: ch18 ($0.992$)"
    assert k90[2:5] == [""] * 3 and k90[6] == ""
    assert k95[3] == r"$K^\star$" and k95[5] == "fails: ch18 ($0.996$)" and k95[7] == ""
    assert k99[:2] == [r"$E_{\min} = 0.99$", "3 eligible; sentinel 18, 21, 33"] and k99[2:] == [""] * 6
    keys = _keys(frag)
    assert len(keys) == len(set(keys))
    assert _value(frag, "ch08.containment.ref_aliased_128.ch33").renderings == ("a",) and "ch08.containment.ref_aliased_64.ch33" not in keys
    assert sorted(k for k in keys if ".ref_aliased_" in k) == ["ch08.containment.ref_aliased_128.ch21", "ch08.containment.ref_aliased_128.ch33",
                                                               "ch08.containment.ref_aliased_64.ch21"]
    assert _value(frag, "ch08.containment.window_aliased_hz.ch21").value == 10246.5 and "ch08.containment.window_aliased_hz.ch33" not in keys
    assert _value(frag, "ch08.containment.margin_hz_256.ch33").value == -12 and _value(frag, "ch08.containment.e_128.ch18").precision == 3
    assert _value(frag, "ch08.containment.frames_in_span_64.ch18").value == 0.962
    assert _value(frag, "ch08.containment.straddle_loss_db_256.ch18").precision == 2
    assert _value(frag, "ch08.containment.disposition.ch33").renderings == ("sentinel",) and not [k for k in keys if k.endswith(".ch36")]
    assert _value(frag, "ch04.kstar.k_star.emin0.9").value == 128 and _value(frag, "ch04.kstar.failing_k.emin0.9").value == 256
    assert _value(frag, "ch04.kstar.binding_channel.emin0.9").value == 18 and _value(frag, "ch04.kstar.binding_e.emin0.9").value == 0.992
    assert _value(frag, "ch04.kstar.sentinels.emin0.9").value == "33" and _value(frag, "ch04.kstar.eligible_count.emin0.95").value == 3
    assert "ch04.kstar.k_star.emin0.99" not in keys and _value(frag, "ch04.kstar.sentinels.emin0.99").renderings == ("sentinel 18, 21, 33",)
    assert frag.inputs[-1] == tmp_path / "tables" / "kstar.csv" and len(frag.inputs) == 6
    notes = "\n".join(frag.notes)
    assert "stacked as two panels one above the other, each with the ch column" in notes
    assert "at footnotesize the two panels stand on one portrait page" in notes
    assert "K* undefined at E_min = 0.99" in notes and "ch21 K=64, ch21 K=128, ch33 K=128" in notes
    assert "disp.\\ marked a" in notes and "ch21 (10246 Hz aliased, edge 4754 Hz away)" in notes
    assert "containment section absent on channels 36" in notes


def test_containment_without_kstar(tmp_path):
    run = core.load_run(_ledger(tmp_path, kstar=False))
    frag = m.build_containment(run)
    assert len(_body(frag.tex, 0)) == 4 and len(_body(frag.tex, 1)) == 4
    assert frag.tex.count(r"\midrule") == 2 and frag.inputs == []
    assert not [k for k in _keys(frag) if k.startswith("ch04.")] and "tables/kstar.csv absent: no K* rows" in frag.notes


def test_write_report_round_trip(tmp_path):
    run = core.load_run(_ledger(tmp_path))
    manifest = core.write_report(run, tmp_path / "out", list(m.BUILDERS), commit="d" * 40, generated="2026-09-07T09:00:00+00:00")
    assert [a["name"] for a in manifest["artifacts"]] == ["calibration_anchors", "calibration_anchors_ledger", "calibration_containment"]
    assert [a["label"] for a in manifest["artifacts"]][1] == "tab:archive:calibration_anchors"
    docs = [nb.load_numbers([tmp_path / "out" / "numbers" / f"{a['name']}.numbers.json"]) for a in manifest["artifacts"]]
    assert [len(d) for d in docs] == [a["count"] for a in manifest["artifacts"]] and docs[1] == []
    keys = {n.key for doc in docs for n in doc}
    assert {"ch08.anchors.source.ch18", "ch08.anchors.selector_anchor_bin.ch18", "ch08.anchors.shift_from_previous_bins.ch33"} <= keys
    assert (tmp_path / "out" / "tables" / "calibration_anchors.tex").read_text().startswith(r"\begin{tabular}{llrrrrrrrrlr}")
    assert (tmp_path / "out" / "tables" / "calibration_anchors_ledger.tex").read_text().startswith(r"\begin{tabular}{llrlrrl}")
    assert r"\begin{tabular}{llrrrrrr}" in (tmp_path / "out" / "tables" / "calibration_containment.tex").read_text()


@pytest.mark.skipif(not (REAL_RUN / "ledger" / "run.json").is_file(), reason="real archive run not on this machine")
def test_real_run_renders_23_channels():
    run = core.load_run(REAL_RUN)
    anchors, ledger, containment = m.build(run), m.build_ledger(run), m.build_containment(run)
    for frag, panel, extra in ((anchors, 0, 0), (ledger, 0, 0), (containment, 0, 3), (containment, 1, 0)):
        rows = _body(frag.tex, panel)
        assert len(rows) == 23 + extra and [r[0] for r in rows[:23]] == [str(c) for c in range(14, 37)]
        keys = _keys(frag)
        assert len(keys) == len(set(keys))
        doc = nb.NumbersDocument.new(frag.name, repository="r", commit="c", script="s", generated="g")
        for n in frag.numbers:
            doc.add(n)                                    # raises on a duplicate key
    for frag in (anchors, containment):
        assert sorted(int(k.rsplit(".ch", 1)[1]) for k in _keys(frag) if ".window_aliased_hz." in k) == [21, 32]
    by = {r[0]: r for r in _body(anchors.tex)}
    led = {r[0]: r for r in _body(ledger.tex)}
    # the five off-era channels: the anchor of record is the previous era's (p on f_a, era = previous in the ledger)
    assert [ch for ch, r in led.items() if r[1] == "previous"] == ["19", "20", "26", "27", "32"]
    assert [ch for ch, r in by.items() if r[3].endswith(r"^{\mathrm{p}}$")] == ["19", "20", "26", "27", "32"]
    assert [ch for ch, r in by.items() if r[1] == "on-quiet"] == ["16", "21", "23", "25", "29"]
    assert by["33"][10] == "sentinel" and by["18"][10] == "supported" and led["33"][6] == "oos, E, ref, lobe"
    assert [ch for ch, r in led.items() if r[6] != "--"] == ["21", "23", "25", "29", "33"]
    assert led["18"][3] == "cal $178$" and led["21"][3] == "lobe $126$ (cal $111$)" and led["27"][3] == "cal $246$"
    assert by["14"][11] == "--" and by["33"][11] == "$458.8$" and led["33"][2] == "$+31$" and led["27"][2] == "$-14$"
    assert by["21"][5].endswith(r"^{\mathrm{a}}$") and led["27"][5] == "$0.0$"
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
    assert "channels 19, 20, 26, 27, 32 have an off current era" in notes
    assert "selector bin taken from the PSD in-span lobe on channels 21, 23, 25, 29, 33" in "\n".join(ledger.notes)


@pytest.mark.skipif(not (REAL_RUN / "ledger" / "run.json").is_file(), reason="real archive run not on this machine")
def test_real_run_fragments_fit_the_page():
    """The measured natural widths (pdflatex, 11pt): the chapter table scales into landscape, the ledger fits
    portrait, and each containment panel fits landscape unscaled. See the module docstring."""
    run = core.load_run(REAL_RUN)
    anchors, ledger, containment = m.build(run), m.build_ledger(run), m.build_containment(run)
    assert len(_header(anchors.tex)) == 12 and len(_header(ledger.tex)) == 7
    assert len(_header(containment.tex, 0)) == 8 and len(_header(containment.tex, 1)) == 10
    # no cell of the widest columns the trim removed is left in the chapter table
    assert "in-span" not in anchors.tex and "selector" not in anchors.tex and "sentinel:" not in anchors.tex
