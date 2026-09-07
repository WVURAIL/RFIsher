"""``figures_status``: both figures and the table behind them on a synthetic ledger, then the real run."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rfisher_results import style
from rfisher_results.archive import numbers as nb
from rfisher_results.archive.report import core
from rfisher_results.archive.report import figures_status as m

REAL_RUN = Path("/home/djg/rail/results/archive_v5_2026-09-07")
EXCISION = "none: excision, with the pilot bin kept as a monitoring tap"
FLOOR = "measured floor from a verified off state"
SIGN_ON = "era transition: the next sign-on"
NEW_RULE = "closing by a new_rule the table does not know about"

_ANCHOR = {"status": "ok", "anchor_rf_offset_hz": -3.7, "boot_status": "ok", "boot_rf_hz_q16": -15.6, "boot_rf_hz_q84": -3.7,
           "source": "current_era"}
_CONT = {"in_span_recovered": True, "in_span_refined_offset_hz": -20.8, "e_128": 0.996, "e_256": 0.992, "window_aliased_hz": 0.0,
         "anchor_suspect": False, "anchor_lobe_offset_bins": 0.43, "era": "current era 2018-12..2026-08 (proxy-low)"}
_SCREEN = {"screening_class": m.WALL, "closing_condition": EXCISION, "survey_flag_rate_era": 0.926, "off_era_current": False,
           "off_from": ""}
_SEL = {"claim_status": "diagnostic", "status": "no feasible point", "anchor_source": "calibration", "anchor_sentinel": ""}


def _record(channel: int, freq_id: int, **sections) -> dict:
    return {"channel": channel, "freq_id": freq_id, "product": f"{freq_id}.npz", "product_sha256": "b" * 64, "notes": [],
            "sections": sections}


def _ledger(tmp_path, *, kstar=True, e_min=0.9):
    ledger = tmp_path / "ledger"
    (ledger / "channels").mkdir(parents=True)
    records = [
        # ch18: every value present, one era, no marks
        _record(18, 783, screening=dict(_SCREEN), anchor=dict(_ANCHOR), anchor_previous=None, containment=dict(_CONT),
                selection=dict(_SEL)),
        # ch21: measurement-bound on floor, aliased window, fine anchor suspect (selector on the lobe bin)
        _record(21, 736, screening={**_SCREEN, "screening_class": m.BOUND_FLOOR, "closing_condition": FLOOR, "survey_flag_rate_era": 0.605},
                anchor={**_ANCHOR, "anchor_rf_offset_hz": 14.9, "boot_rf_hz_q16": 14.9, "boot_rf_hz_q84": 14.9}, anchor_previous=None,
                containment={**_CONT, "in_span_refined_offset_hz": -151.5, "e_128": 0.988, "e_256": 0.983, "window_aliased_hz": 10246.5,
                             "anchor_suspect": True, "anchor_lobe_offset_bins": 13.954},
                selection={**_SEL, "anchor_source": "psd in-span lobe (fine anchor suspect)",
                           "anchor_sentinel": "fine anchor +14.0 bins from the PSD in-span lobe"}),
        # ch23: binds K* (E_256 below E_min), a previous era distinct from the anchor, suspect
        _record(23, 706, screening={**_SCREEN, "screening_class": m.BOUND_FLOOR, "closing_condition": FLOOR, "survey_flag_rate_era": 0.89},
                anchor={**_ANCHOR, "anchor_rf_offset_hz": -306.5, "boot_rf_hz_q16": -390.0, "boot_rf_hz_q84": -294.6},
                anchor_previous={"status": "ok", "anchor_rf_offset_hz": 100.0, "shift_from_previous_bins": -34},
                containment={**_CONT, "in_span_refined_offset_hz": -593.3, "e_128": 0.977, "e_256": 0.793, "anchor_suspect": True,
                             "anchor_lobe_offset_bins": 24.06},
                selection={**_SEL, "anchor_source": "psd in-span lobe (fine anchor suspect)"}),
        # ch25: recovery candidate with a selected point; no bootstrap, no lobe, E_256 undefined
        _record(25, 675, screening={**_SCREEN, "screening_class": m.RECOVERY, "closing_condition": "measured correlation time",
                                    "survey_flag_rate_era": 0.5},
                anchor={**_ANCHOR, "anchor_rf_offset_hz": 15.8, "boot_status": "insufficient_blocks", "boot_rf_hz_q16": None,
                        "boot_rf_hz_q84": None},
                anchor_previous=None,
                containment={**_CONT, "in_span_recovered": False, "in_span_refined_offset_hz": None, "e_128": 0.977, "e_256": None},
                selection={**_SEL, "claim_status": "screening", "status": "feasible"}),
        # ch29: measurement-bound on tau_c with a closing condition outside the short-form table (wrapped, escaped)
        _record(29, 614, screening={**_SCREEN, "screening_class": m.BOUND_TAU, "closing_condition": NEW_RULE, "survey_flag_rate_era": 0.64},
                anchor={**_ANCHOR, "anchor_rf_offset_hz": 100.2, "boot_rf_hz_q16": 88.3, "boot_rf_hz_q84": 100.2}, anchor_previous=None,
                containment={**_CONT, "in_span_refined_offset_hz": 42.1, "e_128": 0.944, "e_256": 0.923}, selection=dict(_SEL)),
        # ch32: off era; the anchor of record is the previous era's (the open marker coincides and is omitted); aliased
        _record(32, 568, screening={**_SCREEN, "screening_class": m.OFF_ERA, "closing_condition": SIGN_ON, "survey_flag_rate_era": 0.598,
                                    "off_era_current": True, "off_from": "2023-02"},
                anchor={**_ANCHOR, "anchor_rf_offset_hz": -95.8, "boot_rf_hz_q16": -95.8, "boot_rf_hz_q84": -95.8, "source": "previous_era"},
                anchor_previous={"status": "ok", "anchor_rf_offset_hz": -95.8, "shift_from_previous_bins": -11},
                containment={**_CONT, "in_span_refined_offset_hz": -95.7, "e_128": 0.994, "e_256": 0.991, "window_aliased_hz": 4128.5,
                             "era": "previous era 2018-12..2020-11 (proxy-high) (current era is off)"},
                selection=dict(_SEL)),
        # ch33: the K* sentinel (E_128 far below E_min), previous era, suspect, selection refused (no floor)
        _record(33, 552, screening={**_SCREEN, "screening_class": m.BOUND_FLOOR, "closing_condition": FLOOR, "survey_flag_rate_era": 0.72},
                anchor={**_ANCHOR, "anchor_rf_offset_hz": 89.3, "boot_rf_hz_q16": 89.3, "boot_rf_hz_q84": 113.1},
                anchor_previous={"status": "ok", "anchor_rf_offset_hz": 458.8, "shift_from_previous_bins": 31},
                containment={**_CONT, "in_span_refined_offset_hz": -29.2, "e_128": 0.008, "e_256": 0.007, "anchor_suspect": True,
                             "anchor_lobe_offset_bins": 9.94},
                selection={**_SEL, "claim_status": "", "status": "refused", "refusal": "no floor for frames without a shelf estimate"}),
        # ch36: nothing measured: no screening record, an empty anchor, an empty previous era, no containment, no selection
        _record(36, 506, screening=None, anchor={"status": "empty", "anchor_rf_offset_hz": None, "boot_status": "empty", "source": "current_era"},
                anchor_previous={"status": "empty", "anchor_rf_offset_hz": None}, containment=None, selection=None),
    ]
    files = []
    for rec in records:
        rel = f"channels/ch{rec['channel']}_fid{rec['freq_id']}.json"
        (ledger / rel).write_text(json.dumps(rec))
        files.append(rel)
    run = {"schema": {"name": "rfisher-archive-ledger", "version": 1}, "generated": "2026-09-07T00:00:00+00:00",
           "producer": {"commit": "a" * 40}, "products": {}, "channels": files, "era_config_digest": "c" * 64}
    if e_min is not None:
        run["provisional"] = {"e_min": e_min}
    (ledger / "run.json").write_text(json.dumps(run))
    if kstar:
        (tmp_path / "tables").mkdir()
        (tmp_path / "tables" / "kstar.csv").write_text(
            "e_min,k_star,failing_k,binding_channel,binding_e,sentinels,eligible\n"
            "0.9,128,256,23,0.793,33,18;21;23;25;29;32;33\n"
            "0.95,64,128,29,0.944,33,18;21;23;25;29;32;33\n"
            "0.99,,,,,18;33,18;21;23;25;29;32;33\n")
    return tmp_path


def _body(tex: str) -> list[list[str]]:
    """The data rows of the tabular, split into cells."""
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


def test_short_closing_and_spans():
    assert m.short_closing(EXCISION) == "excision;\nmonitoring tap" and m.short_closing("") == core.DASH
    assert m.short_closing(NEW_RULE) == "closing by a\nnew\\_rule the\ntable does not"      # wrapped to 16, escaped, three lines at most
    assert [round(m.span_half_width_hz(k), 1) for k in m.SPANS] == [3051.8, 1525.9, 762.9]


def test_channel_status_counts_and_footnote(tmp_path):
    run = core.load_run(_ledger(tmp_path))
    rows = m.statuses(run)
    by = {r.channel: r for r in rows}
    assert [r.channel for r in rows] == [18, 21, 23, 25, 29, 32, 33, 36]
    assert by[18].anchored and by[18].has_boot and by[18].lobe_recovered and not by[18].aliased and not by[18].anchor_suspect
    assert by[21].aliased and by[21].anchor_suspect and by[21].selector_anchor_source == "psd in-span lobe (fine anchor suspect)"
    assert not by[25].has_boot and not by[25].lobe_recovered and by[25].selected and not by[25].diagnostic and not by[25].refused
    assert by[32].off_era and by[32].anchor_from_previous_era and by[32].previous_present and by[32].off_from == "2023-02"
    assert by[33].refused and not by[33].diagnostic and by[33].previous_present and by[33].refusal.startswith("no floor")
    assert not by[36].screened and not by[36].anchored and not by[36].previous_present and not by[36].lobe_recovered
    assert not (by[36].selected or by[36].diagnostic or by[36].refused)
    assert m.selection_summary(rows) == {"selected": [25], "diagnostic": [18, 21, 23, 29, 32], "refused": [33], "unrecorded": [36]}
    counts = m.class_counts(rows)
    assert list(counts) == list(m.CLASSES) + [m.UNSCREENED]
    assert [counts[c] for c in m.CLASSES] == [1, 3, 1, 1, 1] and counts[m.UNSCREENED] == 1
    note = m.footnote(rows).replace("\n", " ")
    assert note.startswith("1 of 8 channels have a selected operating point; 5 of 8 selections are diagnostic (the drift screen refused), "
                           "1 refused on the calibration surface (ch 33) and 1 without a selection record; the classes rest")
    assert max(len(line) for line in m.footnote(rows).splitlines()) <= m.FOOTNOTE_WIDTH
    assert m.footnote(rows[:1]).startswith("No channel has a selected operating point: 1 of 1 selections are diagnostic (the drift screen "
                                           "refused); the classes rest")
    assert m.run_e_min(run) == 0.9
    marks = m.kstar_marks(run, 0.9)
    assert marks.k_star == 128 and marks.failing_k == 256 and marks.binding_channel == 23 and marks.sentinels == (33,)
    assert m.kstar_marks(run, 0.99).k_star is None and m.kstar_marks(run, 0.5) is None


def test_build_every_column(tmp_path):
    run = core.load_run(_ledger(tmp_path))
    frag = m.build(run)
    assert frag.name == "figures_status" and frag.label == "fig:conclusions:status;fig:calibration:containment"
    rows = _body(frag.tex)
    assert len(rows) == 8 and all(len(r) == 10 for r in rows)
    r18, r21, r23, r25, r29, r32, r33, r36 = rows
    assert r18 == ["18", "occupancy-wall excision candidate", "excision; monitoring tap", "$0.93$", "$-3.7$", "--", "$-20.8$",
                   "$0.996$", "$0.992$", "--"]
    assert r21 == ["21", "measurement-bound on floor", "measured floor (verified off)", "$0.60$", "$14.9$", "--", "$-151.5$",
                   "$0.988$", "$0.983$", "anchor suspect ($+14.0$ bins); aliased"]
    assert r23[4:] == ["$-306.5$", "$100.0$", "$-593.3$", "$0.977$", "$0.793$", r"anchor suspect ($+24.1$ bins); binds $K^\star$"]
    assert r25 == ["25", "recovery candidate", r"measured $\tau_c$", "$0.50$", "$15.8$", "--", "--", "$0.977$", "--", "--"]
    assert r29[1:3] == [r"measurement-bound on $\tau_c$", "closing by a new\\_rule the table does not"]
    assert r32 == ["32", "off-era", "next sign-on", "$0.60$", "$-95.8$", "$-95.8$", "$-95.7$", "$0.994$", "$0.991$",
                   "anchor from previous era; aliased"]
    assert r33[4:] == ["$89.3$", "$458.8$", "$-29.2$", "$0.008$", "$0.007$", "anchor suspect ($+9.9$ bins); sentinel"]
    assert r36 == ["36", "no screening record", "--", "--", "--", "--", "--", "--", "--", "--"]

    keys = _keys(frag)
    assert len(keys) == len(set(keys))
    assert not [k for k in keys if k.endswith(".36")]
    s, c = "ch11.status_map", "ch08.containment_map"
    assert _value(frag, f"{s}.screening_class.18").renderings == (m.WALL,) and _value(frag, f"{s}.closing_condition.18").value == EXCISION
    assert _value(frag, f"{s}.closing_condition.25").renderings == ("measured correlation time", "measured tau_c")
    assert _value(frag, f"{s}.survey_flag_rate_era.21").value == 0.605 and _value(frag, f"{s}.survey_flag_rate_era.21").precision == 2
    assert _value(frag, f"{s}.off_from.32").renderings == ("2023-02",) and [k for k in keys if ".off_from." in k] == [f"{s}.off_from.32"]
    n = _value(frag, f"{c}.anchor_rf_offset_hz.23")
    assert n.value == -306.5 and n.precision == 1 and n.source == {"table": "figures_status.tex", "row": {"channel": 23}, "column": "anchor"}
    assert _value(frag, f"{c}.anchor_source.32").value == "previous_era" and _value(frag, f"{c}.boot_rf_hz_q84.33").value == 113.1
    assert f"{c}.boot_rf_hz_q16.25" not in keys and f"{c}.in_span_refined_offset_hz.25" not in keys and f"{c}.e_256.25" not in keys
    assert sorted(int(k.rsplit(".", 1)[1]) for k in keys if ".anchor_previous_rf_offset_hz." in k) == [23, 32, 33]
    assert sorted(int(k.rsplit(".", 1)[1]) for k in keys if ".anchor_suspect." in k) == [21, 23, 33]
    assert _value(frag, f"{c}.anchor_suspect.21").value == "psd in-span lobe (fine anchor suspect)"
    assert _value(frag, f"{c}.anchor_lobe_offset_bins.23").value == 24.06 and _value(frag, f"{c}.anchor_lobe_offset_bins.23").precision == 1
    assert sorted(int(k.rsplit(".", 1)[1]) for k in keys if ".window_aliased_hz." in k) == [21, 32]
    assert _value(frag, f"{c}.window_aliased_hz.21").renderings == ("aliased",) and _value(frag, f"{c}.e_128.33").value == 0.008
    assert [_value(frag, f"{s}.count.{m._slug(cls)}").value for cls in m.CLASSES] == [1, 3, 1, 1, 1]
    assert _value(frag, f"{s}.count.no_screening_record").value == 1 and _value(frag, f"{s}.channels").value == 8
    assert [_value(frag, f"{s}.count.{o}").value for o in ("selected", "diagnostic", "refused")] == [1, 5, 1]
    assert _value(frag, f"{c}.k_star").value == 128 and _value(frag, f"{c}.failing_k").value == 256
    assert _value(frag, f"{c}.binding_channel").value == 23 and _value(frag, f"{c}.binding_e").value == 0.793
    assert _value(frag, f"{c}.sentinels").renderings == ("33",) and _value(frag, f"{c}.e_min").value == 0.9
    assert round(_value(frag, f"{c}.span_half_width_hz.k128").value, 1) == 1525.9
    assert frag.inputs[-1] == tmp_path / "tables" / "kstar.csv" and len(frag.inputs) == 10

    notes = "\n".join(frag.notes)
    assert "1 of 8 channels have a selected operating point; 5 of 8 selections are diagnostic" in notes
    assert "ch33: selection refused: no floor for frames without a shelf estimate" in notes
    assert "channels 36: no selection record (neither selected, diagnostic nor refused)" in notes
    assert "the unscreened draw a dashed cell" in notes and "channels 32: anchor and lobe read from the previous era" in notes
    assert "channels 21, 23, 33: containment.anchor_suspect" in notes and "channels 36: no anchor" in notes
    assert "channels 25: no bootstrap quantiles" in notes and "channels 25, 36: no in-span lobe" in notes
    assert "E undefined (dash): 25:e_256, 36:e_128, 36:e_256" in notes and "channels 21, 32: containment.window_aliased_hz > 0" in notes
    assert "K* = 128, binding channel 23 (E_256 = 0.793), sentinels 33" in notes


def test_build_without_kstar_or_e_min(tmp_path):
    run = core.load_run(_ledger(tmp_path, kstar=False, e_min=None))
    frag = m.build(run)
    assert m.run_e_min(run) == m.DEFAULT_E_MIN and len(frag.inputs) == 9
    keys = _keys(frag)
    assert not [k for k in keys if k.split(".")[-1] in ("k_star", "failing_k", "binding_channel", "binding_e", "sentinels")]
    by = {r[0]: r for r in _body(frag.tex)}
    assert by["23"][9] == "anchor suspect ($+24.1$ bins)" and by["33"][9] == "anchor suspect ($+9.9$ bins)"
    assert "tables/kstar.csv absent or lacks an e_min = 0.9 row: no binding-channel or sentinel marks, no K* in the title" in frag.notes


def test_unknown_class_is_counted_under_its_own_name(tmp_path):
    root = _ledger(tmp_path)
    path = root / "ledger" / "channels" / "ch18_fid783.json"
    rec = json.loads(path.read_text())
    rec["sections"]["screening"]["screening_class"] = "held-out"
    path.write_text(json.dumps(rec))
    run = core.load_run(root)
    counts = m.class_counts(m.statuses(run))
    assert list(counts) == list(m.CLASSES) + ["held-out", m.UNSCREENED] and counts["held-out"] == 1 and counts[m.WALL] == 0
    frag = m.build(run)
    assert _value(frag, "ch11.status_map.count.held_out").value == 1 and _body(frag.tex)[0][1] == "held-out"
    assert "0 occupancy-wall excision candidate; 1 off-era; 1 held-out; 1 no screening record" in "\n".join(frag.notes)
    style.configure(require_tex=False)
    fig = m.figure_status_map(m.statuses(run))
    assert [t.get_text() for t in fig.legends[0].get_texts()][-2:] == ["held-out (1)", "no screening record (1)"]
    m.plt.close(fig)


def test_render_writes_both_figures(tmp_path):
    style.configure(require_tex=False)
    run = core.load_run(_ledger(tmp_path))
    paths = m.render(run, tmp_path / "figures")
    assert [p.name for p in paths] == ["fig_conclusions_status.pdf", "fig_conclusions_status.png",
                                       "fig_calibration_containment.pdf", "fig_calibration_containment.png"]
    for p in paths:
        head = p.read_bytes()[:8]
        assert head.startswith(b"%PDF") if p.suffix == ".pdf" else head.startswith(b"\x89PNG")


def test_write_report_round_trip(tmp_path):
    style.configure(require_tex=False)
    run = core.load_run(_ledger(tmp_path))
    out = tmp_path / "out"
    figs = m.render(run, out / "figures")
    manifest = core.write_report(run, out, [m.build], commit="d" * 40, generated="2026-09-07T09:00:00+00:00", extra_artifacts=figs)
    names = [a["name"] for a in manifest["artifacts"]]
    assert names == ["figures_status", "fig_conclusions_status", "fig_conclusions_status", "fig_calibration_containment",
                     "fig_calibration_containment"]
    assert manifest["artifacts"][1]["table"] == "figures/fig_conclusions_status.pdf"
    doc = nb.load_numbers([out / "numbers" / "figures_status.numbers.json"])
    assert len(doc) == manifest["artifacts"][0]["count"] == len(m.build(run).numbers)
    assert (out / "tables" / "figures_status.tex").read_text().startswith(r"\begin{tabular}{lllrrrrrrl}")


@pytest.mark.skipif(not (REAL_RUN / "ledger" / "run.json").is_file(), reason="real archive run not on this machine")
def test_real_run_renders_23_channels():
    run = core.load_run(REAL_RUN)
    frag = m.build(run)
    rows = _body(frag.tex)
    assert len(rows) == 23 and [r[0] for r in rows] == [str(c) for c in range(14, 37)]
    keys = _keys(frag)
    assert len(keys) == len(set(keys))
    doc = nb.NumbersDocument.new(frag.name, repository="r", commit="c", script="s", generated="g")
    for n in frag.numbers:
        doc.add(n)                                        # raises on a duplicate key
    by = {r[0]: r for r in rows}
    assert [ch for ch, r in by.items() if "anchor from previous era" in r[9]] == ["19", "20", "26", "27", "32"]
    assert [ch for ch, r in by.items() if "anchor suspect" in r[9]] == ["21", "23", "25", "29", "33"]
    assert [ch for ch, r in by.items() if "aliased" in r[9]] == ["21", "32"]
    assert r"binds $K^\star$" in by["23"][9] and "sentinel" in by["33"][9] and by["33"][7] == "$0.008$"
    assert by["15"][5] == "$-129.6$" and by["14"][5] == "--" and by["21"][5] == "--" and "--" not in by["21"][3:5] + by["21"][6:9]
    assert not [r for r in rows if "--" in r[1:5] or "--" in r[6:9]]     # every channel screened, anchored, with a lobe and both E
    s, c = "ch11.status_map", "ch08.containment_map"
    assert [_value(frag, f"{s}.count.{m._slug(cls)}").value for cls in m.CLASSES] == [0, 5, 0, 13, 5]
    assert [_value(frag, f"{s}.count.{o}").value for o in ("selected", "diagnostic", "refused")] == [0, 19, 4]
    assert _value(frag, f"{c}.k_star").value == 128 and _value(frag, f"{c}.binding_channel").value == 23
    assert _value(frag, f"{c}.sentinels").value == "33" and _value(frag, f"{c}.e_min").value == 0.9
    notes = "\n".join(frag.notes)
    assert "No channel has a selected operating point: 19 of 23 selections are diagnostic" in notes
    assert "4 refused on the calibration surface (ch 15, 28, 30, 36)" in notes and notes.count("selection refused: no floor") == 4
    note = m.footnote(m.statuses(run))
    assert note.startswith("No channel has a selected operating point") and len(note.splitlines()) <= 2
