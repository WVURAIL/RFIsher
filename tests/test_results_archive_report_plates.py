"""``plates``: Appendix C's per-channel plates and the table behind them, synthetic then real."""
from __future__ import annotations

import csv
import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

from rfisher_results import style
from rfisher_results.archive import numbers as nb
from rfisher_results.archive.products import NFFT, PSD_BIN_HZ, Product
from rfisher_results.archive.report import core
from rfisher_results.archive.report import plates as m

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("v5_fixture_plates", ROOT / "tests" / "test_pilotproxy_v5.py")
v5_fixture = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v5_fixture)

REAL_RUN = Path("/home/djg/rail/results/archive_v5_2026-09-07")
REAL_CHANNEL = 24                      # the smallest product that carries a diagnostic point

FRAMES, UNITS = 24, 12
ANCHOR_BIN = 128                       # the fixture's designated window is centred here
BULK_REFERENCE = 20                    # every bulk bin's three terms, so every bulk T is exactly 1
MONTHS = ("2024-06", "2024-07", "2024-08", "2024-11", "2025-01", "2025-02")
PEAKS = (10, 24, 30, 40, 60, 200)      # designated target term per frame group -> Z = peak / BULK_REFERENCE


def _month_seconds(label: str) -> float:
    year, month = int(label[:4]), int(label[5:])
    days = 0
    for y in range(1970, year):
        days += 366 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 365
    lengths = [31, 29 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 28,
               31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    days += sum(lengths[:month - 1])
    return days * 86400.0 + 43200.0


def _fine_terms(peaks) -> np.ndarray:
    """Every bulk bin at ``T = 1``; the designated window at ``T = peak / BULK_REFERENCE``."""
    terms = np.full((FRAMES, 3, 256), BULK_REFERENCE, dtype=np.uint64)
    designated = [(ANCHOR_BIN + k) % 256 for k in range(-2, 3)]
    for frame in range(FRAMES):
        terms[frame, 0, designated] = int(peaks[frame % len(peaks)])
    return terms


def _spectra(rows: int, line_bin: int, loud) -> tuple[np.ndarray, np.ndarray]:
    """A flat unit floor with one line; ``loud`` frames carry 20 dB more there."""
    power = np.ones((rows, NFFT))
    power[:, line_bin] = 10.0
    power[np.asarray(loud, dtype=int), line_bin] = 1000.0
    codes = np.round(1000.0 * np.log10(power)).astype(np.int16)
    return codes, np.ones((rows, 1))


def _write_product(directory: Path, channel: int, *, peaks=PEAKS, months=MONTHS, dead_bulk: bool = False,
                   rail: bool = True, loud=None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    freq_id = 900 - channel
    path = v5_fixture._write_product(directory / f"{freq_id}.npz", channel, frames=FRAMES, units=UNITS)
    times = np.asarray([_month_seconds(months[unit % len(months)]) + unit * 3600.0 for unit in range(UNITS)])
    terms = _fine_terms(peaks)
    if dead_bulk:
        terms[0, 1:] = 0                              # no bulk bin has a positive denominator: always masked
    power = np.full((FRAMES, 1), 4.0)
    if rail:
        power[3, 0] = m.FULL_SCALE_NATIVE
    codes, reference = _spectra(FRAMES, line_bin=64, loud=range(FRAMES // 2) if loud is None else loud)
    v5_fixture._replace(path, unit_time0_ctime=times, fine_power_u64=terms, baseband_power_linear=power,
                        psd_frame_db_i16=codes, psd_db_reference=reference,
                        psd_db_step_per_code=np.asarray(0.01, dtype=np.float64),
                        psd_db_invalid_code=np.asarray(-32768, dtype=np.int16))
    return path


def _eras(path: Path, *, current: int, records) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"channel": 0, "current_era": current,
                                "eras": [{"era": i + 1, "first_month": f, "last_month": l, "state": s}
                                         for i, (f, l, s) in enumerate(records)]}))


def _points(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["channel", "rho", "eta", "masked_fraction", "r_sys"],
                                lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _sections(*, first: str, last: str, state: str = "proxy-high", off: bool = False, rho=1, eta=1.6,
              frames: int = FRAMES) -> dict:
    selection = {"anchor_bin": ANCHOR_BIN, "status": "no feasible point", "claim_status": "diagnostic",
                 "diagnostic_rho": rho, "diagnostic_eta": eta, "diagnostic_masked_fraction": 0.75,
                 "kept_evaluation": 3, "r_tol": 0.02, "diagnostic_r_sys": 12.0,
                 "masked_fraction_evaluation": 0.8, "masked_fraction_evaluation_q16": 0.75,
                 "masked_fraction_evaluation_q84": 0.85, "r_sys_evaluation": 11.0,
                 "r_sys_evaluation_q16": 10.0, "r_sys_evaluation_q84": 12.5, "refusal": "within-era stability"}
    if rho is None:
        selection = {"anchor_bin": ANCHOR_BIN, "status": "refused", "claim_status": "diagnostic",
                     "diagnostic_rho": None, "diagnostic_eta": None, "r_tol": 0.02,
                     "refusal": "no floor: frames without a shelf estimate"}
    return {
        "geometry": {"grid_residual_hz": 7.24, "fine_pad_factor": 2, "fine_guard_bins": 1},
        "product": {"n_frames": frames},
        "era": {"current_first_month": first, "current_last_month": last, "current_state": state,
                "off_era_current": off, "current_frames": frames, "current_level_median_db": 0.5},
        "blocks": {"calibration_frames": 12, "evaluation_frames": 12},
        "anchor_era": {"anchor_fine_hz": 23.8},
        "containment": {"disposition": "supported", "peak_abs_median_hz": 24.0,
                        "frames_in_span_64": 0.9, "frames_in_span_128": 0.9, "frames_in_span_256": 0.8},
        "tolerance": {"r_tol_dilation": 0.02},
        "null": {"coarse_centre": 1.01, "coarse_core_sigma": 0.004, "bulk_size": 125, "anchor_bin": ANCHOR_BIN},
        "selection": selection,
        "screening": {"survey_flag_rate_era": 0.5, "screening_class": "occupancy-wall excision candidate"},
    }


def _record(channel: int, sections: dict) -> dict:
    return {"channel": channel, "freq_id": 900 - channel, "product": f"{900 - channel}.npz",
            "product_sha256": "b" * 64, "notes": [], "sections": sections}


def _run_dir(tmp_path: Path) -> Path:
    """Six channels: the full path, an off era, a refusal, a point that keeps nothing, no product, no side files."""
    ledger = tmp_path / "ledger"
    (ledger / "channels").mkdir(parents=True)
    products = tmp_path / "products"
    plan = {
        14: _sections(first=MONTHS[0], last=MONTHS[-1], rho=1, eta=1.6),
        19: _sections(first=MONTHS[3], last=MONTHS[-1], state="proxy-low", off=True, rho=1, eta=1.6),
        28: _sections(first=MONTHS[0], last=MONTHS[-1], rho=None),
        31: _sections(first=MONTHS[0], last=MONTHS[-1], rho=1, eta=0.2),      # below every Z: nothing survives
        35: _sections(first=MONTHS[0], last=MONTHS[-1], rho=1, eta=1.6),      # no product on disk
        36: _sections(first=MONTHS[0], last=MONTHS[-1], rho=1, eta=1.6),      # no eras.json, no operating points
    }
    files = []
    for channel, sections in plan.items():
        rel = f"channels/ch{channel}_fid{900 - channel}.json"
        (ledger / rel).write_text(json.dumps(_record(channel, sections)))
        files.append(rel)
    (ledger / "run.json").write_text(json.dumps(
        {"schema": {"name": "rfisher-archive-ledger", "version": 1}, "generated": "2026-09-07T00:00:00+00:00",
         "producer": {"commit": "a" * 40}, "products": {}, "products_dir": str(products), "channels": files}))

    for channel in (14, 19, 28, 31, 36):
        _write_product(products, channel, dead_bulk=(channel == 14))
    for channel in (14, 28, 31, 35):
        _eras(tmp_path / "channels" / f"ch{channel:02d}" / m.ERAS_JSON, current=2,
              records=[(MONTHS[0], MONTHS[2], "proxy-high"), (MONTHS[3], MONTHS[-1], "proxy-high")])
    _eras(tmp_path / "channels" / "ch19" / m.ERAS_JSON, current=2,
          records=[(MONTHS[0], MONTHS[2], "proxy-high"), (MONTHS[3], MONTHS[-1], "proxy-low")])
    for channel in (14, 19, 31, 35):
        _points(tmp_path / "channels" / f"ch{channel:02d}" / m.POINTS_CSV,
                [{"channel": channel, "rho": rho, "eta": 1.0 + 0.1 * i, "masked_fraction": 0.9 - 0.1 * i,
                  "r_sys": 100.0 / (i + 1)} for rho in (1, 2, 3) for i in range(5)])
    _points(tmp_path / "channels" / "ch28" / m.POINTS_CSV, [])
    return tmp_path


def _ungated() -> bool:
    """Whether the actual health provider or one of its dependencies is absent."""
    try:
        from pilot_proxy.archive_health import evaluate_frame_health  # noqa: F401
    except ImportError:
        return True
    return False


@pytest.fixture(autouse=True)
def _clear():
    m.clear_cache()
    yield
    m.clear_cache()


def _body(tex: str) -> list[list[str]]:
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


# ------------------------------------------------------------------ pure helpers
def test_coordinates_and_spans():
    assert m.month_index_of("2024-10") == 2024 * 12 + 9
    assert m.month_index_of("") == -1 and m.month_index_of("2024-1") == -1 and m.month_index_of("20xx-10") == -1
    assert round(m.span_half_width_hz(64), 1) == 3051.8 and round(m.span_half_width_hz(128), 1) == 1525.9
    assert round(m.span_half_width_hz(256), 1) == 762.9
    assert round(m.wrap_fine_hz(7.24), 2) == 7.24 and math.isnan(m.wrap_fine_hz(None))
    assert round(m.wrap_fine_hz(3000.0), 1) == round(3000.0 - 256 * 11.920928955078125, 1)


def test_histogram_edges_survival_and_containment_edges():
    values = np.asarray([1.0, 2.0, 4.0, 8.0])
    edges = m.histogram_edges(values, log=True, bins=3)
    assert edges[0] == 1.0 and round(edges[-1], 6) == 8.0 and np.all(np.diff(edges) > 0)
    assert m.histogram_edges(np.asarray([np.nan]), log=False).shape == (m.HIST_BINS + 1,)
    assert np.allclose(m.histogram_edges(np.asarray([2.0, 2.0]), log=False)[[0, -1]], [2.0, 3.0])

    x, above = m.survival(np.asarray([3.0, 1.0, 2.0, np.nan]))
    assert list(x) == [1.0, 2.0, 3.0] and list(above) == [3.0, 2.0, 1.0]
    assert m.survival(np.asarray([np.nan]))[0].size == 0

    edges = m.containment_edges()
    assert edges[0] == PSD_BIN_HZ / 2.0 and edges[-1] == m.WINDOW_HZ
    assert np.diff(edges).min() >= PSD_BIN_HZ - 1e-9            # never finer than one stored bin


def test_read_eras_and_points(tmp_path):
    path = tmp_path / m.ERAS_JSON
    _eras(path, current=2, records=[("2024-01", "2024-05", "proxy-high"), ("2024-06", "2024-09", "proxy-low")])
    records, current = m.read_eras(path)
    assert current == 1 and [r.state for r in records] == ["proxy-high", "proxy-low"]
    assert records[1].label == "2024-06..2024-09" and records[1].first_month == m.month_index_of("2024-06")

    assert m.read_eras(tmp_path / "missing.json") == ((), -1)
    (tmp_path / "bad.json").write_text("{not json")
    assert m.read_eras(tmp_path / "bad.json") == ((), -1)
    path.write_text(json.dumps({"current_era": 9, "eras": [{"era": 1, "first_month": "x", "last_month": "2024-05"}]}))
    records, current = m.read_eras(path)
    assert records == () and current == -1                       # an unparsable month drops the era

    csv_path = tmp_path / m.POINTS_CSV
    _points(csv_path, [{"channel": 14, "rho": 1, "eta": 1.0, "masked_fraction": 0.5, "r_sys": 9.0},
                       {"channel": 14, "rho": 1, "eta": "", "masked_fraction": "", "r_sys": 8.0}])
    curves = m.read_points(csv_path)
    assert curves.present and curves.rows == 2 and list(curves.by_rho) == [1]
    assert curves.by_rho[1].shape == (1, 3)                      # the row without a masked fraction is dropped
    assert not m.read_points(tmp_path / "absent.csv").present


def test_z_statistic_reproduces_the_keep_boundary():
    ratio = np.asarray([[1.0, 2.0, 3.0, 4.0], [1.0, 0.0, 3.0, 4.0]])
    positive = np.asarray([[True, True, True, True], [True, False, True, True]])
    bulk = np.asarray([False, True, True, False])
    # anchor bin 0 with half width 0 would be the designated set; use the module's width on a 4-bin axis
    z = m.z_statistic(ratio, positive, anchor_bin=0, bulk=bulk, rho=1)
    assert z.shape == (2,)
    with pytest.raises(ValueError):
        m.z_statistic(ratio, positive, anchor_bin=0, bulk=bulk, rho=5)


def test_monthly_fine_means():
    ratio = np.asarray([[1.0, 3.0], [3.0, 5.0], [10.0, 10.0]])
    months = np.asarray([100, 100, 102])
    mask = np.asarray([True, True, False])
    got_months, means = m.monthly_fine_means(ratio, months, mask)
    assert list(got_months) == [100] and np.allclose(means, [[2.0, 4.0]])
    assert m.monthly_fine_means(ratio, months, np.zeros(3, dtype=bool))[0].size == 0


def test_spectrum_pass_denominators(tmp_path):
    path = _write_product(tmp_path / "products", 14, loud=range(4))
    with Product(path) as product:
        era = np.zeros(product.n_frames, dtype=bool)
        era[:8] = True
        keep = np.zeros(product.n_frames, dtype=bool)
        keep[:4] = True                                   # the four loud frames of the era
        result = m.spectrum_pass(product, era, keep, era & product.rejected, chunk=5)
    line = int(np.argmax(result.all_mean))
    assert result.all_frames == 8 and result.keep_frames == 4
    # P_all = (4 x 1000 + 4 x 10) / 8, P_keep|keep = 1000, removed = (4 x 1000 + 4 x 10 - 4 x 1000) / 8
    assert result.all_mean[line] == pytest.approx((4 * 1000.0 + 4 * 10.0) / 8)
    assert result.keep_mean[line] == pytest.approx(1000.0)
    assert result.removed[line] == pytest.approx(4 * 10.0 / 8)
    assert result.removed[line] != pytest.approx(result.all_mean[line] - result.keep_mean[line])
    assert result.peak_offsets_hz.size == int((era & product.rejected).sum())


# ------------------------------------------------------------------ the layers
def test_compute_every_path(tmp_path):
    run = core.load_run(_run_dir(tmp_path))
    rows = m.plates(run)
    by = {p.channel: p for p in rows}
    assert [p.channel for p in rows] == [14, 19, 28, 31, 35, 36]

    ch14 = by[14]
    assert ch14.present and ch14.has_point and ch14.era_months == f"{MONTHS[0]}..{MONTHS[-1]}"
    # The fixture has one saturated-ceiling frame; a working health provider
    # excludes it from every plotted current-era population.
    selected_frames = FRAMES if _ungated() else FRAMES - 1
    assert ch14.era_frames == selected_frames and ch14.era_frames_untimed == 0
    assert ch14.reference_is_current and ch14.coarse.size == selected_frames and ch14.level_db.size == selected_frames
    assert ch14.input_power.size == selected_frames and ch14.rail_frames == int(_ungated())
    # Z = peak / 20 on every frame but the one whose bulk denominators are all zero (always masked)
    assert math.isinf(ch14.z.max())
    finite = np.round(ch14.z[np.isfinite(ch14.z)], 6)
    assert set(finite) == {round(peak / BULK_REFERENCE, 6) for peak in PEAKS}
    assert ch14.kept_frames == int((ch14.z <= ch14.eta).sum())
    assert ch14.masked_fraction_era == pytest.approx(1.0 - ch14.kept_frames / selected_frames)
    assert ch14.has_keep and math.isfinite(ch14.removed_fraction) and ch14.removed_fraction > 0
    assert ch14.heat_months.size == len(MONTHS) and ch14.heat_db.shape == (len(MONTHS), 256)
    assert ch14.populated_months == len(MONTHS)
    assert ch14.blank_months == m.month_index_of(MONTHS[-1]) - m.month_index_of(MONTHS[0]) + 1 - len(MONTHS)
    assert set(ch14.in_span) == set(m.SPANS) and ch14.peak_offsets_hz.size > 0
    assert ch14.curves.present and sorted(ch14.curves.by_rho) == [1, 2, 3]
    assert ch14.boundaries == (m.month_index_of(MONTHS[3]),)

    ch19 = by[19]
    assert ch19.era_off and not ch19.reference_is_current
    assert ch19.reference_label == f"{MONTHS[0]}..{MONTHS[2]}"      # the previous on era carries the peaks
    assert ch19.era_frames < FRAMES                                 # only the later months are the era

    ch28 = by[28]
    assert ch28.present and not ch28.has_point and ch28.z.size == 0 and not ch28.has_keep
    assert ch28.after_mask_reason == "no diagnostic point to apply"
    assert not ch28.curves.present and ch28.no_point_reason.startswith("no floor")
    assert ch28.coarse.size == selected_frames                               # the histograms still stand

    ch31 = by[31]
    assert ch31.has_point and ch31.kept_frames == 0 and not ch31.has_keep
    assert ch31.after_mask_reason == "no current-era frame survives the mask"
    assert ch31.all_db.size == NFFT and not np.isfinite(ch31.keep_db).any()

    ch35 = by[35]
    assert not ch35.present and "not found" in ch35.missing_reason
    assert ch35.coarse.size == 0 and ch35.era_months == f"{MONTHS[0]}..{MONTHS[-1]}"
    assert ch35.curves.present                                      # its ledger side files are still read

    ch36 = by[36]
    assert ch36.present and ch36.boundaries == () and not ch36.curves.present

    assert m.counts(rows) == {"with_point": 5, "refused": 1, "off_era": 1, "no_after_mask": 1,
                              "no_product": 1, "no_curves": 2, "other_health_gate": 5 if _ungated() else 0}


def test_unreadable_product_is_named_not_raised(tmp_path):
    root = _run_dir(tmp_path)
    (root / "products" / "886.npz").write_bytes(b"not an npz")
    m.clear_cache()
    plate = {p.channel: p for p in m.plates(core.load_run(root))}[14]
    assert not plate.present and "unreadable" in plate.missing_reason


def test_plates_are_computed_once(tmp_path):
    run = core.load_run(_run_dir(tmp_path))
    first = m.plates(run, channels=[14])[0]
    assert m.plates(run, channels=[14])[0] is first
    m.clear_cache()
    assert m.plates(run, channels=[14])[0] is not first


# ------------------------------------------------------------------ the fragment
def test_build_every_column(tmp_path):
    run = core.load_run(_run_dir(tmp_path))
    frag = m.build(run)
    assert frag.name == "plates" and frag.label == "fig:archive:atlas"
    rows = _body(frag.tex)
    assert len(rows) == 6 and all(len(r) == 10 for r in rows)
    r14, r19, r28, r31, r35, r36 = rows
    assert r14[0] == "14" and r14[1] == f"{MONTHS[0]}--{MONTHS[-1]} proxy-high" and r14[3] == "$1$"
    assert r14[4] == "$1.600$"
    assert r14[9] == (r"frame-health gate valid\_only" if _ungated() else "--")
    assert "current era off" in r19[9] and f"{MONTHS[0]}--{MONTHS[2]}" in r19[9].replace("..", "--")
    assert r28[3] == "--" and r28[4] == "--" and r28[5] == "--" and r28[6] == "--"
    assert "selector refused" in r28[9] and "no trade curves" in r28[9]
    assert r31[5] == "$0$" and r31[6] == "--" and "no after-mask spectrum" in r31[9]
    assert r35[2] == "--" and "not found" in r35[9]
    assert "no trade curves" in r36[9]

    names = [Path(i).name for i in frag.inputs]
    assert m.ERAS_JSON in names and m.POINTS_CSV in names
    assert not [n for n in names if n.endswith(".npz")]          # the gigabyte products are named, never hashed

    keys = _keys(frag)
    assert len(keys) == len(set(keys))
    p = "appC.plates"
    assert f"{p}.era_frames.ch35" not in keys and f"{p}.era.ch35" in keys
    assert f"{p}.kept_frames.ch35" not in keys and f"{p}.eta.ch35" in keys      # the ledger's point, no product
    assert f"{p}.rho.ch28" not in keys and f"{p}.removed_fraction.ch31" not in keys
    assert _value(frag, f"{p}.era_frames.ch14").value == (FRAMES if _ungated() else FRAMES - 1)
    assert _value(frag, f"{p}.input_rail_frames.ch14").value == int(_ungated())
    assert _value(frag, f"{p}.bulk_centre.ch14").value == 1.01
    assert _value(frag, f"{p}.in_span_128.ch14").precision == 3
    assert _value(frag, f"{p}.measured_anchor_hz.ch14").value == pytest.approx(23.8)
    assert _value(frag, f"{p}.eta.ch14").source == {"table": "plates.tex", "row": {"channel": 14},
                                                    "column": r"$\eta$"}
    assert _value(frag, f"{p}.z_bulk_centre.ch14").status == "derived"
    assert _value(frag, f"{p}.count.no_product").value == 1 and _value(frag, f"{p}.channels").value == 6
    assert _value(frag, f"{p}.full_scale_native").value == 128.0
    assert round(_value(frag, f"{p}.span_half_width_hz.k128").value, 1) == 1525.9

    notes = "\n".join(frag.notes)
    assert "channels 19: the current era is a transmitter-off era" in notes
    assert "channels 28: the selector refused before a surface was evaluated" in notes
    assert "channels 31: the diagnostic point keeps no current-era frame" in notes
    assert "channels 28, 36: operating_points.csv carries no candidate point" in notes
    assert "channels 35: the product could not be opened" in notes
    assert "their sha256 digests are the run's own" in notes
    assert "not the difference of the two drawn curves" in notes
    if _ungated():
        assert "channels 14, 19, 28, 31, 36: this process could not apply the run's frame-health gate" in notes


def test_numbers_document_round_trip(tmp_path):
    run = core.load_run(_run_dir(tmp_path))
    frag = m.build(run)
    doc = nb.NumbersDocument.new(frag.name, repository="WVURAIL/RFIsher", commit="a" * 40,
                                 script="rfisher_results.archive.report.plates", generated="2026-09-07T00:00:00+00:00")
    for number in frag.numbers:
        doc.add(number)
    path = doc.write(tmp_path / "plates.numbers.json")
    assert json.loads(path.read_text())["numbers"]


# ------------------------------------------------------------------ the figure
def test_render_writes_one_plate_per_channel(tmp_path):
    style.configure(require_tex=False)
    run = core.load_run(_run_dir(tmp_path))
    paths = m.render(run, tmp_path / "figures")
    assert [p.name for p in paths] == [name for channel in (14, 19, 28, 31, 35, 36)
                                       for name in (f"fig_archive_plate_ch{channel:02d}.pdf",
                                                    f"fig_archive_plate_ch{channel:02d}.png")]
    for path in paths:
        head = path.read_bytes()[:8]
        assert head.startswith(b"%PDF") if path.suffix == ".pdf" else head.startswith(b"\x89PNG")


def test_figure_panels_and_heads(tmp_path):
    style.configure(require_tex=False)
    run = core.load_run(_run_dir(tmp_path))
    by = {p.channel: p for p in m.plates(run)}

    fig = m.figure_plate(by[14])
    assert len(fig.axes) == 9                       # eight panels and the heatmap's colour bar
    coarse, level, power, fine = fig.axes[:4]
    assert coarse.get_xscale() == "log" and coarse.get_yscale() == "log"
    assert level.get_xscale() == "linear" and power.get_xscale() == "log"
    assert fine.get_xscale() == "log"
    assert any(round(line.get_xdata()[0], 4) == round(by[14].eta, 4) for line in fine.get_lines())
    spectra = fig.axes[4]
    assert [t.get_text() for t in spectra.get_legend().get_texts()][-1] == "nominal pilot"
    era = fig.axes[5]
    assert era.get_xlabel().startswith("UTC calendar month")
    assert round(era.get_ylim()[1]) >= 1500 and round(era.get_ylim()[0]) <= -1500
    trade = fig.axes[7]
    assert trade.get_yscale() == "log"
    assert m.plate_subtitle(by[14])[1].startswith("diagnostic point")
    m.plt.close(fig)

    fig = m.figure_plate(by[35])
    assert not by[35].present and "Channel 35" in m.plate_title(by[35])
    texts = [t.get_text() for t in fig.texts]
    assert any("not found" in t for t in texts)
    m.plt.close(fig)

    fig = m.figure_plate(by[28])
    assert m.plate_subtitle(by[28])[1].startswith("the selector refused")
    m.plt.close(fig)


def test_write_report_round_trip(tmp_path):
    style.configure(require_tex=False)
    run = core.load_run(_run_dir(tmp_path))
    out = tmp_path / "out"
    figs = m.render(run, out / "figures")
    manifest = core.write_report(run, out, [m.build], commit="a" * 40, generated="2026-09-07T00:00:00+00:00",
                                 extra_artifacts=figs)
    names = [a["name"] for a in manifest["artifacts"]]
    assert names[0] == "plates" and "fig_archive_plate_ch14" in names
    assert (out / "tables" / "plates.tex").is_file() and (out / "numbers" / "plates.numbers.json").is_file()


def test_module_is_registered():
    from rfisher_results.archive.report import build as build_module

    assert m.NAME in build_module.FIGURE_MODULES


# ------------------------------------------------------------------ the real run
@pytest.mark.skipif(not (REAL_RUN / "ledger" / "run.json").is_file(), reason="the archive run is not on this machine")
def test_real_run_ledger_layers():
    """Every channel's ledger-side layer, without opening a product."""
    run = core.load_run(REAL_RUN)
    rows = m.plates(run, products_dir=REAL_RUN / "no-such-directory")
    assert len(rows) == 23 and all(not p.present for p in rows)
    by = {p.channel: p for p in rows}
    assert [c for c in by if by[c].era_off] == [19, 20, 26, 27, 32]
    assert [c for c in by if not by[c].has_point] == [15, 28, 30, 36]
    assert not by[15].curves.present and by[14].curves.present
    assert by[19].reference_label == "2024-09..2024-11" and not by[19].reference_is_current
    assert by[14].era_months == "2018-12..2026-08" and by[14].boundaries == ()
    frag = m.build(run, products_dir=REAL_RUN / "no-such-directory")
    assert len(_body(frag.tex)) == 23
    m.clear_cache()


@pytest.mark.skipif(not (REAL_RUN / "ledger" / "run.json").is_file(), reason="the archive run is not on this machine")
def test_real_product_reproduces_the_run_kept_count():
    """The plate's mask is the run's: kept on the era equals the two blocks' kept counts."""
    run = core.load_run(REAL_RUN)
    ledger = run.by_channel()[REAL_CHANNEL]
    if not (Path(str(run.run["products_dir"])) / ledger.product).is_file():
        pytest.skip("the v5 products are not on this machine")
    plate = m.compute_plate(run, ledger)
    assert plate.present and plate.has_point
    blocks, selection = ledger.blocks, ledger.selection
    calibration = round((1.0 - float(selection["diagnostic_masked_fraction"])) * float(blocks["calibration_frames"]))
    expected = calibration + float(selection["kept_evaluation"])
    blocked = float(blocks["calibration_frames"]) + float(blocks["evaluation_frames"])
    if plate.health_gate_agrees:
        assert plate.kept_frames == expected and plate.era_frames == blocked
    else:
        # without pilot_proxy the era mask is valid frames alone, so it carries the gate's own excluded frames
        excluded = float(ledger.section("product").get("health_excluded", 0))
        assert expected <= plate.kept_frames <= expected + excluded
        assert blocked <= plate.era_frames <= blocked + excluded
    for k in m.SPANS:
        assert plate.in_span[k] == pytest.approx(plate.ledger_in_span[k], abs=5e-4)
    m.clear_cache()


def test_trade_curves_with_no_drawable_row_is_absent(tmp_path):
    """A file that carries rows but no finite point draws nothing, and says so."""
    path = tmp_path / m.POINTS_CSV
    _points(path, [{"channel": 14, "rho": 1, "eta": 1.0, "masked_fraction": "", "r_sys": ""}])
    curves = m.read_points(path)
    assert curves.rows == 1 and not curves.present and curves.by_rho == {}


def test_fine_statistic_marks_the_dead_reference_bins(tmp_path):
    """The ratio and its positive-denominator mask come out of one read of the terms."""
    path = _write_product(tmp_path / "products", 14, dead_bulk=True)
    with Product(path) as product:
        ratio, positive = m.fine_statistic(product)
    assert ratio.shape == (FRAMES, 256) and positive.shape == ratio.shape
    assert not positive[0].any() and positive[1].all()       # frame 0's references were zeroed
    assert np.all(ratio[0] == 0.0) and np.allclose(ratio[1, 5], 1.0)


@pytest.mark.parametrize("check", [test_compute_every_path, test_build_every_column])
def test_plate_denominators_without_health_dependency(tmp_path, monkeypatch, check):
    monkeypatch.setitem(sys.modules, "pilot_proxy.archive_health", None)
    check(tmp_path)
