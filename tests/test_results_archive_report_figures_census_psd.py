"""``figures_census_psd``: the 23-panel figure and the table behind it, on a synthetic run then the real one."""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from rfisher_results import style
from rfisher_results.archive import numbers as nb
from rfisher_results.archive.report import core
from rfisher_results.archive.report import figures_census_psd as m

REAL_RUN = Path("/home/djg/rail/results/archive_v5_2026-09-07")

CURRENT = "current era 2018-12..2026-08 (proxy-low)"
PREVIOUS = "previous era 2024-09..2024-11 (proxy-high) (current era is off)"


def _lobe(offset_hz: float, db: float, *, excess: float | None = None) -> dict:
    return {"offset_hz": offset_hz, "refined_offset_hz": offset_hz + 0.4, "db": db,
            "excess_db": db - 0.3 if excess is None else excess}


def _window(peak_hz: float, peak_db: float, *, n: int = 41, hole: bool = False) -> tuple[list, list, list]:
    """A toy window: a Gaussian lobe on a flat baseline, sampled across +-15 kHz."""
    step = 2 * m.WINDOW_HZ / (n - 1)
    offsets = [-m.WINDOW_HZ + i * step for i in range(n)]
    mean = [round(peak_db * math.exp(-((x - peak_hz) / 2200.0) ** 2), 4) for x in offsets]
    if hole:
        mean[0] = None                                    # a non-finite bin: the file writes null
    return offsets, mean, [0.05] * len(offsets)


def _entry(channel: int, *, peak_hz: float, peak_db: float, dominant, in_span, near=None, centre_line_hz: float = 90_000.0,
           frames: int = 1000, detected: int = 900, disposition: str = m.SUPPORTED, reasons: str = "",
           hole: bool = False, short_baseline: bool = False) -> dict:
    offsets, mean, baseline = _window(peak_hz, peak_db, hole=hole)
    return {str(channel): {
        "freq_id": 900 - channel, "frames": frames, "detected_frames": detected,
        "centre_line_rf_offset_hz": centre_line_hz, "window_median_power": 1.0e6,
        "rf_offset_hz": offsets, "mean_db": mean, "baseline_db": baseline[:-3] if short_baseline else baseline,
        "excess": [0.0] * len(offsets), "count": [frames] * len(offsets),
        "dominant": dominant, "near": near if near is not None else dominant, "in_span": in_span,
        "peak_counts": [0] * len(offsets), "disposition": disposition, "reasons": reasons}}


def _record(channel: int, freq_id: int, **sections) -> dict:
    return {"channel": channel, "freq_id": freq_id, "product": f"{freq_id}.npz", "product_sha256": "b" * 64, "notes": [],
            "sections": sections}


_ERA = {"n_eras": 2, "current_era": 2, "current_first_month": "2019-04", "current_last_month": "2026-08",
        "current_state": "proxy-low", "current_frames": 1234}


def _run_dir(tmp_path: Path) -> Path:
    """A ledger of eight channels and the window spectra beside it, exercising every path."""
    ledger = tmp_path / "ledger"
    (ledger / "channels").mkdir(parents=True)
    records = [_record(ch, 900 - ch, era=dict(_ERA)) for ch in (14, 16, 19, 23, 29, 33, 35, 36)]
    files = []
    for rec in records:
        rel = f"channels/ch{rec['channel']}_fid{rec['freq_id']}.json"
        (ledger / rel).write_text(json.dumps(rec))
        files.append(rel)
    (ledger / "run.json").write_text(json.dumps(
        {"schema": {"name": "rfisher-archive-ledger", "version": 1}, "generated": "2026-09-07T00:00:00+00:00",
         "producer": {"commit": "a" * 40}, "products": {}, "channels": files, "era_config_digest": "c" * 64}))

    def write(channel: int, provenance: str, channels: dict) -> None:
        path = tmp_path / "channels" / f"ch{channel:02d}" / m.SPECTRA_JSON
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"schema": "rfisher_results.archive.psd window spectra v1", "provenance": provenance,
                                    "parameters": {"window_hz": m.WINDOW_HZ}, "channels": channels}))

    # ch14: everything present, the dominant lobe is the in-span lobe, the centre line falls in the window
    write(14, CURRENT, _entry(14, peak_hz=2.2, peak_db=15.7, dominant=_lobe(2.2, 15.7), in_span=_lobe(2.2, 15.7),
                              centre_line_hz=3059.0, hole=True))
    # ch16: no parsable provenance (the era falls back to the ledger) and a baseline shorter than the mean
    write(16, "", _entry(16, peak_hz=-0.7, peak_db=6.1, dominant=_lobe(-1.1, 6.1), in_span=_lobe(-1.1, 6.1),
                         short_baseline=True))
    # ch19: the current era is off, so the mean is the previous on era's
    write(19, PREVIOUS, _entry(19, peak_hz=19.2, peak_db=29.8, dominant=_lobe(19.2, 29.8), in_span=_lobe(19.2, 29.8)))
    # ch23: the in-span lobe is 593 Hz off nominal, with a skirt past the K = 256 span
    write(23, CURRENT, _entry(23, peak_hz=-593.7, peak_db=8.1, dominant=_lobe(-593.7, 8.1), in_span=_lobe(-593.7, 8.1),
                              disposition=m.SENTINEL, reasons="in-span lobe -593 Hz from nominal"))
    # ch29: no in-span lobe stands over the baseline
    write(29, CURRENT, _entry(29, peak_hz=41.7, peak_db=5.9, dominant=_lobe(41.7, 5.9), in_span=None,
                              disposition=m.SENTINEL))
    # ch33: the dominant lobe is a co-channel carrier outside the capture span
    write(33, CURRENT, _entry(33, peak_hz=-3720.3, peak_db=23.0, dominant=_lobe(-3720.3, 23.0), in_span=_lobe(-29.6, 3.2),
                              disposition=m.SENTINEL, reasons="stronger out-of-span feature at -3725 Hz"))
    # ch35: no spectra file at all
    # ch36: a spectra file that carries another channel
    write(36, CURRENT, _entry(30, peak_hz=0.0, peak_db=10.0, dominant=_lobe(0.0, 10.0), in_span=_lobe(0.0, 10.0)))
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


def test_spans_references_and_provenance():
    assert round(m.span_half_width_hz(m.SPAN_K), 1) == 1525.9 and round(m.span_half_width_hz(m.INNER_K), 1) == 762.9
    assert round(m.reference_offset_hz(m.SPAN_K), 1) == 6103.5 and round(m.PSD_BIN_HZ, 2) == 23.84
    assert m.parse_provenance(CURRENT) == ("current", "2018-12..2026-08", "proxy-low", False)
    assert m.parse_provenance(PREVIOUS) == ("previous", "2024-09..2024-11", "proxy-high", True)
    assert m.parse_provenance("") == ("", "", "", False) and m.parse_provenance("archive average") == ("", "", "", False)
    assert m.short_disposition(m.SENTINEL) == "supported (sentinel)" and m.short_disposition("") == "disposition unstated"
    assert m.short_disposition(m.SUPPORTED) == "supported"


def test_load_every_path(tmp_path):
    run = core.load_run(_run_dir(tmp_path))
    rows = m.spectra(run)
    by = {r.channel: r for r in rows}
    assert [r.channel for r in rows] == [14, 16, 19, 23, 29, 33, 35, 36]

    ch14 = by[14]
    assert ch14.drawable and ch14.era_source == "current" and ch14.era_months == "2018-12..2026-08"
    assert ch14.era_state == "proxy-low" and not ch14.era_off and not ch14.era_from_ledger
    assert ch14.era_word == "current era" and ch14.era_short == "current"
    assert ch14.centre_line_in_window and ch14.dominant_is_in_span_lobe and not ch14.dominant_out_of_span
    assert ch14.frames == 1000 and ch14.detected_frames == 900 and math.isnan(ch14.mean_db[0])

    assert by[16].era_from_ledger and by[16].era_months == "2019-04..2026-08" and by[16].era_source == "current"
    assert by[16].offset_hz.size == by[16].baseline_db.size == by[16].mean_db.size == 38   # truncated to the shortest

    ch19 = by[19]
    assert ch19.era_source == "previous" and ch19.era_off and ch19.era_word == "previous era (now off)"
    assert ch19.era_short == "previous (off)" and not ch19.centre_line_in_window

    assert round(by[23].in_span.refined_offset_hz, 1) == -593.3 and by[23].disposition == m.SENTINEL
    assert by[29].in_span is None and by[29].dominant is not None and by[29].drawable
    assert by[33].dominant_out_of_span and not by[33].dominant_is_in_span_lobe
    assert round(by[33].dominant.khz, 2) == -3.72 and round(by[33].in_span.refined_offset_hz, 1) == -29.2

    assert not by[35].drawable and by[35].missing_reason == f"{m.SPECTRA_JSON} absent"
    assert by[35].era_from_ledger and by[35].era_months == "2019-04..2026-08" and by[35].offset_hz.size == 0
    assert not by[36].drawable and by[36].missing_reason == f"{m.SPECTRA_JSON} carries no channel 36"

    assert m.era_counts(rows) == {"current": 5, "previous": 1, "sentinel": 3, "dominant_out_of_span": 1,
                                  "centre_line_in_window": 1, "no_in_span_lobe": 1, "no_spectrum": 2}


def test_unreadable_spectra_file_is_named_not_raised(tmp_path):
    root = _run_dir(tmp_path)
    (root / "channels" / "ch14" / m.SPECTRA_JSON).write_text("{not json")
    row = m.spectra(core.load_run(root))[0]
    assert not row.drawable and row.missing_reason.startswith(f"{m.SPECTRA_JSON} unreadable")


def test_build_every_column(tmp_path):
    run = core.load_run(_run_dir(tmp_path))
    frag = m.build(run)
    assert frag.name == "figures_census_psd" and frag.label == "fig:census:psd"
    rows = _body(frag.tex)
    assert len(rows) == 8 and all(len(r) == 9 for r in rows)
    r14, r16, r19, r23, r29, r33, r35, r36 = rows
    assert r14 == ["14", "current 2018-12--2026-08", "$1{,}000$", "supported", "$2.6$", "$15.7$", "$2.6$", "$15.7$",
                   "centre line $+3.1$ kHz"]
    assert r16[1] == "current 2019-04--2026-08" and r16[8] == "era from the ledger"
    assert r19[1:4] == ["previous (off) 2024-09--2024-11", "$1{,}000$", "supported"]
    assert r23[4:] == ["$-593.3$", "$8.1$", "$-593.3$", "$8.1$", "--"] and r23[3] == "supported (sentinel)"
    assert r29[4:] == ["--", "--", "$42.1$", "$5.9$", "no in-span lobe"]
    assert r33[4:] == ["$-29.2$", "$3.2$", "$-3719.9$", "$23.0$", "dominant out of span"]
    assert r35 == ["35", "current 2019-04--2026-08", "--", "--", "--", "--", "--", "--",
                   "spectra\\_window.json absent; era from the ledger"]
    assert r36[8] == "spectra\\_window.json carries no channel 36; era from the ledger"

    keys = _keys(frag)
    assert len(keys) == len(set(keys))
    assert not [k for k in keys if k.rsplit(".", 1)[-1] in ("35", "36")]      # no numbers for a channel with no spectrum
    p = "ch03.census_psd"
    assert _value(frag, f"{p}.era.14").value == CURRENT and "2018-12..2026-08" in _value(frag, f"{p}.era.14").renderings
    assert _value(frag, f"{p}.era.19").renderings[-1] == "previous era (now off)"
    assert _value(frag, f"{p}.era_state.16").value == "proxy-low" and _value(frag, f"{p}.frames.14").value == 1000
    assert _value(frag, f"{p}.detected_frames.14").value == 900
    assert sorted(_value(frag, f"{p}.disposition.23").renderings) == ["supported (sentinel)", "supported with sentinel"]
    n = _value(frag, f"{p}.in_span_offset_hz.23")
    assert round(n.value, 1) == -593.3 and n.precision == 1
    assert n.source == {"table": "figures_census_psd.tex", "row": {"channel": 23}, "column": "lobe [Hz]"}
    assert f"{p}.in_span_offset_hz.29" not in keys and f"{p}.in_span_db.29" not in keys
    assert round(_value(frag, f"{p}.dominant_offset_hz.33").value, 1) == -3719.9
    assert _value(frag, f"{p}.dominant_offset_khz.33").renderings == ("-3.7 kHz",)
    assert [k for k in keys if ".dominant_offset_khz." in k] == [f"{p}.dominant_offset_khz.33"]
    assert [k for k in keys if ".centre_line_rf_offset_hz." in k] == [f"{p}.centre_line_rf_offset_hz.14"]
    assert _value(frag, f"{p}.channels").value == 8 and _value(frag, f"{p}.count.previous").value == 1
    assert _value(frag, f"{p}.count.no_spectrum").value == 2 and _value(frag, f"{p}.count.sentinel").value == 3
    assert round(_value(frag, f"{p}.span_half_width_hz").value, 1) == 1525.9
    assert round(_value(frag, f"{p}.inner_span_half_width_hz").value, 1) == 762.9
    assert round(_value(frag, f"{p}.reference_offset_hz").value, 1) == 6103.5
    assert _value(frag, f"{p}.window_hz").value == 15000.0
    assert [i.name for i in frag.inputs[-6:]] == [m.SPECTRA_JSON] * 6      # the six readable spectra files

    notes = "\n".join(frag.notes)
    assert "5 panels draw the channel's current era and 1 the previous on era (channels 19: the current era is off" in notes
    assert "channels 21" not in notes and "channels 23, 29, 33: disposition 'supported with sentinel'" in notes
    assert "channels 33: the dominant lobe of the window lies outside the K = 128 span" in notes
    assert "channels 14: the coarse channel's own centre bin falls inside" in notes
    assert "channels 29: no in-span lobe stands over the baseline" in notes
    assert "channels 35, 36: no window spectrum" in notes and "channels 16, 35, 36: the spectra file carries no parsable" in notes
    assert "the panel peaks span 5.9--29.8 dB" in notes


def test_render_writes_the_figure(tmp_path):
    style.configure(require_tex=False)
    run = core.load_run(_run_dir(tmp_path))
    paths = m.render(run, tmp_path / "figures")
    assert [p.name for p in paths] == ["fig_census_psd_all23.pdf", "fig_census_psd_all23.png"]
    for path in paths:
        head = path.read_bytes()[:8]
        assert head.startswith(b"%PDF") if path.suffix == ".pdf" else head.startswith(b"\x89PNG")


def test_figure_panels_and_legend(tmp_path):
    style.configure(require_tex=False)
    rows = m.spectra(core.load_run(_run_dir(tmp_path)))
    fig = m.figure_census_psd(rows)
    assert len(fig.axes) == len(rows) + 1                       # the panels and the reading-note cell
    panel = fig.axes[0]
    assert panel.get_xscale() == "symlog" and panel.get_xlim() == (-15.0, 15.0)
    assert list(panel.get_xticks()) == [-15.0, 0.0, 15.0]
    assert [round(float(x), 3) for x in panel.get_xticks(minor=True)] == [-6.104, -1.526, -0.763, 0.763, 1.526, 6.104]
    assert [t.get_text() for t in panel.get_xticklabels()] == []            # only the foot of each column is labelled
    assert [t.get_text() for t in fig.axes[6].get_xticklabels()] == ["$-15$", "0", "$15$"]    # ch35 closes its column
    low, high = panel.get_ylim()
    assert low <= -1.0 and high > 15.7 / m.HEADROOM * 0.9        # the spectrum keeps the lower HEADROOM of the panel
    labels = [t.get_text() for t in fig.legends[0].get_texts()]
    assert labels[:2] == ["era-mean spectrum", "sliding-median baseline"]
    assert labels[-1] == "coarse-channel centre line (instrumental)"     # only drawn because ch14 carries one
    m.plt.close(fig)
    without = [r for r in rows if not r.centre_line_in_window]
    assert not [h for h in m.legend_handles(without) if "centre line" in str(h.get_label())]


def test_write_report_round_trip(tmp_path):
    style.configure(require_tex=False)
    run = core.load_run(_run_dir(tmp_path))
    out = tmp_path / "out"
    figs = m.render(run, out / "figures")
    manifest = core.write_report(run, out, [m.build], commit="d" * 40, generated="2026-09-07T09:00:00+00:00",
                                 extra_artifacts=figs)
    assert [a["name"] for a in manifest["artifacts"]] == ["figures_census_psd"] + ["fig_census_psd_all23"] * 2
    assert manifest["artifacts"][0]["label"] == "fig:census:psd"
    doc = nb.load_numbers([out / "numbers" / "figures_census_psd.numbers.json"])
    assert len(doc) == manifest["artifacts"][0]["count"] == len(m.build(run).numbers)
    assert (out / "tables" / "figures_census_psd.tex").read_text().startswith(r"\begin{tabular}{llrlrrrrl}")


@pytest.mark.skipif(not (REAL_RUN / "ledger" / "run.json").is_file(), reason="real archive run not on this machine")
def test_real_run_renders_23_panels():
    run = core.load_run(REAL_RUN)
    rows = m.spectra(run)
    assert [r.channel for r in rows] == list(range(14, 37)) and all(r.drawable for r in rows)
    assert [r.channel for r in rows if r.era_source == "previous"] == [19, 20, 26, 27, 32]
    assert all(r.era_off for r in rows if r.era_source == "previous")
    assert [r.channel for r in rows if r.disposition == m.SENTINEL] == [21, 23, 25, 29, 33]
    assert [r.channel for r in rows if r.dominant_out_of_span] == [33]
    assert [r.channel for r in rows if r.centre_line_in_window] == [14, 28]
    assert not [r for r in rows if r.era_from_ledger or r.in_span is None or r.dominant is None]

    frag = m.build(run)
    body = _body(frag.tex)
    assert len(body) == 23 and [r[0] for r in body] == [str(c) for c in range(14, 37)]
    keys = _keys(frag)
    assert len(keys) == len(set(keys))
    doc = nb.NumbersDocument.new(frag.name, repository="r", commit="c", script="s", generated="g")
    for number in frag.numbers:
        doc.add(number)                                   # raises on a duplicate key
    p = "ch03.census_psd"
    for name in ("era", "disposition", "frames", "in_span_offset_hz", "in_span_db", "dominant_offset_hz", "dominant_db"):
        assert sorted(int(k.rsplit(".", 1)[1]) for k in keys if f".{name}." in k) == list(range(14, 37))
    assert _value(frag, f"{p}.channels").value == 23
    assert _value(frag, f"{p}.count.current").value == 18 and _value(frag, f"{p}.count.previous").value == 5
    assert _value(frag, f"{p}.count.no_spectrum").value == 0 and _value(frag, f"{p}.count.no_in_span_lobe").value == 0
    assert round(_value(frag, f"{p}.dominant_offset_hz.33").value, 1) == -3719.9
    assert _value(frag, f"{p}.dominant_offset_khz.33").renderings == ("-3.7 kHz",)
    assert round(_value(frag, f"{p}.in_span_offset_hz.33").value, 1) == -29.2
    assert round(_value(frag, f"{p}.in_span_db.33").value, 1) == 3.2
    assert round(_value(frag, f"{p}.in_span_offset_hz.23").value, 1) == -593.3
    assert round(_value(frag, f"{p}.centre_line_rf_offset_hz.14").value, 1) == 3059.0
    by = {r[0]: r for r in body}
    assert by["33"][8] == "dominant out of span" and by["28"][8] == "centre line $-12.6$ kHz"
    assert by["19"][1] == "previous (off) 2024-09--2024-11" and by["23"][4] == "$-593.3$"
    assert not [r for r in body if "--" in r[2:8]]                    # every channel has an era, frames and both lobes
    notes = "\n".join(frag.notes)
    assert "18 panels draw the channel's current era and 5 the previous on era" in notes
    assert "the panel peaks span 5.9--42.3 dB" in notes
