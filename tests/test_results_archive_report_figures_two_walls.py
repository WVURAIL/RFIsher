"""``figures_two_walls``: the surface readers, the marked-point table and both figures."""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from rfisher_results import style
from rfisher_results.archive.report import core
from rfisher_results.archive.report import figures_two_walls as m

REAL_RUN = Path("/home/djg/rail/results/archive_v5_2026-09-07")

SURFACE_HEADER = "channel,rho,rank_fraction,eta_q16,eta,frames,kept,masked_fraction,r_sys,tolerance_fraction,cost,feasible,selected\n"
FRONTIER_HEADER = "channel,eta_c,frames,kept,masked_fraction,r_sys,R,evaluable\n"


def _surface(path: Path, channel: int, rows) -> None:
    """rows: (rho, eta_q16, kept, f, r_sys, R, feasible, selected)."""
    text = SURFACE_HEADER
    for rho, q16, kept, f, r, R, feasible, selected in rows:
        text += f"{channel},{rho},0.0079,{q16},{q16 / 65536},1000,{kept},{f!r},{r!r},{R!r},1.0,{feasible},{selected}\n"
    path.write_text(text, encoding="utf-8")


def _frontier(path: Path, channel: int, rows) -> None:
    """rows: (eta_c, kept, f, r_sys, R, evaluable); r_sys None writes a blank cell."""
    text = FRONTIER_HEADER
    for eta, kept, f, r, R, ok in rows:
        cells = ["" if v is None else repr(v) for v in (f, r, R)]
        text += f"{channel},{eta!r},1000,{kept},{cells[0]},{cells[1]},{cells[2]},{ok}\n"
    path.write_text(text, encoding="utf-8")


def _sections(*, rho=1, r_tol=0.0156, floor="stated", basis="bulk left side (not H0)", tau="refused",
              archive_tau="bounded_above", fs8=0.00153, flag=0.72, gain_basis="era chain"):
    return {
        "selection": {"era": "2023-12..2026-08 (proxy-low)", "status": "no feasible point", "claim_status": "diagnostic",
                      "refusal": "within-era stability refused_insufficient_support: candidate rho=1", "r_tol": r_tol,
                      "min_r_sys_rho": rho, "min_r_sys": 546.0, "min_R": 35021.0, "min_r_sys_masked_fraction": 0.997,
                      "diagnostic_rho": rho, "diagnostic_eta_q16": 78300, "diagnostic_eta": 1.1949,
                      "diagnostic_masked_fraction": 0.997, "diagnostic_r_sys": 546.0, "diagnostic_R": 35021.0,
                      "keep_everything_r_sys_calibration": 2045.0, "floor_evidence": floor, "floor_db": -35.9,
                      "coarse_min_R": 33504.0, "coarse_min_R_eta": 1.0, "coarse_min_R_masked_fraction": 0.973,
                      "coarse_R_at_flag": 33504.0, "gain_basis": gain_basis, "chain_gain": 2054312.0,
                      "masked_fraction_evaluation": None, "r_sys_evaluation": None, "R_evaluation": None},
        "null": {"floor_basis": basis, "floor_evidence": floor},
        "chain": {"tau_quality": tau, "tau_c_minutes": None, "tau_c_high_minutes": 5.0},
        "chain_archive": {"tau_quality": archive_tau, "tau_c_high_minutes": 5.0},
        "tolerance": {"r_tol_dilation": r_tol, "r_tol_fs8": fs8, "fs8_status": "priced" if fs8 else "unpriced 14-26"},
        "screening": {"screening_class": "measurement-bound on floor", "survey_flag_rate_era": flag},
    }


def _ledger(tmp_path, channels):
    """channels: {ch: (sections, surface rows or None, frontier rows or None)}."""
    ledger = tmp_path / "ledger"
    (ledger / "channels").mkdir(parents=True)
    names = []
    for ch, (sections, surface, frontier) in channels.items():
        fid = 900 - ch
        (ledger / "channels" / f"ch{ch}_fid{fid}.json").write_text(json.dumps(
            {"channel": ch, "freq_id": fid, "product": f"{fid}.npz", "product_sha256": "b" * 64, "notes": [], "sections": sections}))
        names.append(f"channels/ch{ch}_fid{fid}.json")
        base = tmp_path / "channels" / f"ch{ch:02d}"
        base.mkdir(parents=True)
        if surface is not None:
            _surface(base / m.SURFACE_CSV, ch, surface)
        if frontier is not None:
            _frontier(base / m.FRONTIER_CSV, ch, frontier)
    (ledger / "run.json").write_text(json.dumps({"generated": "2026-09-07T00:00:00+00:00", "producer": {"commit": "a" * 40},
                                                 "channels": names, "provisional": {"occupancy_wall_masked_fraction": 0.95}}))
    return core.load_run(tmp_path)


def test_surface_reader_selects_one_rank_and_orders_by_eta(tmp_path):
    path = tmp_path / "operating_points.csv"
    _surface(path, 33, [(2, 70000, 40, 0.96, 600.0, 38000.0, False, False),
                        (1, 78300, 34, 0.997, 546.0, 35021.0, False, False),
                        (1, 66000, 900, 0.1, 1900.0, 121000.0, False, False),
                        (1, 74000, 120, 0.88, 700.0, 44000.0, False, True)])
    rows = m.read_operating_points(path, 33, 1)
    assert rows["eta_q16"].tolist() == [66000, 74000, 78300] and rows.size == 3
    assert rows["kept"].tolist() == [900, 120, 34] and rows["selected"].tolist() == [False, True, False]
    assert m.read_operating_points(path, 33, 9).size == 0        # a rank the surface does not carry
    assert m.read_operating_points(path, 14, 1).size == 0        # another channel's file
    bad = tmp_path / "bad.csv"
    bad.write_text("rho,channel,eta_q16\n1,33,2\n")
    with pytest.raises(ValueError, match="lack columns"):
        m.read_operating_points(bad, 33, 1)
    swapped = tmp_path / "swapped.csv"
    swapped.write_text(SURFACE_HEADER.replace("channel,rho,", "rho,channel,"))
    with pytest.raises(ValueError, match="first two columns"):
        m.read_operating_points(swapped, 33, 1)


def test_frontier_reader_reads_blanks_as_nan(tmp_path):
    path = tmp_path / "coarse_frontier.csv"
    _frontier(path, 29, [(1.0, 613, 0.613, 0.0571, 4.08, True), (1.2, 5, 0.995, None, None, False)])
    rows = m.read_coarse_frontier(path, 29)
    assert rows.size == 2 and rows["evaluable"].tolist() == [True, False]
    assert rows["R"][0] == pytest.approx(4.08) and math.isnan(rows["R"][1])
    assert m.read_coarse_frontier(path, 33).size == 0


def _full(tmp_path):
    surface = [(1, 66000, 900, 0.1, 1900.0, 121000.0, False, False),
               (1, 74000, 120, 0.88, 700.0, 44000.0, False, False),
               (1, 78300, 34, 0.997, 546.0, 35021.0, False, False)]
    frontier = [(1.0, 27, 0.973, 523.0, 33504.0, False), (1.005, 200, 0.8, 700.0, 44871.0, True),
                (1.05, 800, 0.2, 1500.0, 96153.0, True)]
    return _ledger(tmp_path, {
        33: (_sections(), surface, frontier),
        # no surface file and no frontier: the curve is empty, the ledger's coarse minimum still prints
        21: (_sections(rho=4, floor="measured", basis="off era p90", tau="measured", archive_tau="measured", fs8=None,
                       flag=0.605), None, None),
    })


def test_channel_curve_reads_both_files_and_marks_the_points(tmp_path):
    run = _full(tmp_path)
    c = m.channel_curve(run, run.by_channel()[33])
    assert c.rho == 1 and c.curve.size == 3 and c.n_full == 3
    assert c.marker is not None and c.curve["r_sys"][c.marker] == pytest.approx(546.0)
    assert c.keep_index is None                                  # no f = 0 row on this surface
    assert c.coarse.size == 3 and c.coarse_index is not None
    assert c.coarse["eta_c"][c.coarse_index] == pytest.approx(1.005)   # the least evaluable R, not the f = 0.973 row
    assert c.coarse_min["R"] == pytest.approx(33504.0)           # the ledger's value is printed, not the file's
    assert any("differs from selection.coarse_min_R" in n for n in c.notes)
    assert c.dashed and "stated floor" in c.dashed_reason and "tau_c refused" in c.dashed_reason
    assert c.keep_ratio == pytest.approx(2045.0 / 0.0156) and c.fs8_wall == pytest.approx(0.00153 / 0.0156)
    assert any("tau_c refused on the era chain and bound on the archive-wide chain" in n for n in c.notes)
    # the channel with no surface file: an empty curve, the ledger's numbers, a note
    empty = m.channel_curve(run, run.by_channel()[21])
    assert empty.curve.size == 0 and empty.coarse.size == 0 and empty.rho == 4
    assert not empty.dashed and math.isnan(empty.fs8_wall)
    assert any(m.SURFACE_CSV in n for n in empty.notes) and any("unpriced" in n for n in empty.notes)


def test_build_emits_one_row_per_channel_with_unique_keys(tmp_path):
    frag = m.build(_full(tmp_path))
    assert frag.name == m.NAME and frag.label == ";".join(m.LABELS)
    body = [line for line in frag.tex.splitlines() if line.startswith(("33 ", "21 "))]
    assert len(body) == 2
    keys = [n.key for n in frag.numbers]
    assert len(keys) == len(set(keys)) and all(k.startswith(("ch09.twowalls.", "ch09.case.")) for k in keys)
    assert {"ch09.twowalls.R.ch33", "ch09.twowalls.R_coarse.ch33"} <= set(keys)
    assert any(k.startswith("ch09.case.") for k in keys)          # the case figure's numbers ride along
    assert core.DASH in frag.tex                                  # the channel without a surface dashes its curve columns


def test_render_writes_both_figures_and_the_curves_csv(tmp_path):
    style.configure(require_tex=False)
    run = _full(tmp_path)
    paths = m.render(run, tmp_path / "figures")
    names = [Path(p).name for p in paths]
    assert names[0] == m.CURVES_CSV
    assert {f"{m.FIGURE_TWO_WALLS}.pdf", f"{m.FIGURE_TWO_WALLS}.png"} <= set(names)
    assert all(Path(p).is_file() and Path(p).stat().st_size > 0 for p in paths)
    curves = (tmp_path / "figures" / m.CURVES_CSV).read_text().splitlines()
    assert curves[0] == ",".join(m.CURVE_COLUMNS)
    assert any(line.startswith("33,fine,") for line in curves) and any(line.startswith("33,coarse,") for line in curves)


@pytest.mark.skipif(not (REAL_RUN / "ledger" / "run.json").is_file(), reason="the archive run is not on this machine")
def test_the_real_run_draws_every_channel():
    style.configure(require_tex=False)
    run = core.load_run(REAL_RUN)
    cs = m.channel_curves(run)
    assert len(cs) == 23
    drawn = [c for c in cs if c.curve.size]
    assert len(drawn) >= 19                                        # the four refused-floor channels have no surface
    assert all(c.marker is not None for c in drawn)
    frag = m.build(run, curves=cs)
    keys = [n.key for n in frag.numbers]
    assert len(keys) == len(set(keys))
    assert np.isfinite([c.flag_rate for c in cs]).all()
