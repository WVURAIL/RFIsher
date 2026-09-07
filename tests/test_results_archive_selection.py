"""Selection on a calibration block and replay on an evaluation block (synthetic v5 fixture)."""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import numpy as np
import pytest

from rfisher.thresholds import ALWAYS_MASKED_Q16
from rfisher_results.archive import blocks, selection
from rfisher_results.archive.products import Product

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("v5_fixture_sel", ROOT / "tests" / "test_pilotproxy_v5.py")
v5_fixture = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v5_fixture)

FLOOR = selection.Floor(db=-55.0, evidence="stated", population="fixture")


@pytest.fixture
def product(tmp_path):
    path = v5_fixture._write_product(tmp_path / "552.npz", 33)
    with np.load(path, allow_pickle=False) as z:
        frames = int(np.asarray(z["valid"]).shape[0])
    v5_fixture._replace(path, baseband_power_linear=np.full((frames, 1), 4.0))
    with Product(path) as p:
        yield p


def _bulk():
    bulk = np.zeros(256, dtype=bool)
    bulk[:4] = True
    return bulk


def test_kept_at_follows_the_q16_rule():
    req = np.array([1, 65536, 70000, ALWAYS_MASKED_Q16], dtype=object)
    np.testing.assert_array_equal(selection.kept_at(req, 65536), [True, True, False, False])
    np.testing.assert_array_equal(selection.kept_at(req, 2**63), [True, True, True, False])


def test_systematic_residuals_use_shelf_where_finite_and_the_floor_elsewhere(product):
    rows = np.arange(product.n_frames)
    res = selection.systematic_residuals(product, rows, FLOOR)
    finite = np.isfinite(product.shelf_db)
    assert np.allclose(res[finite], 10 ** (product.shelf_db[finite] / 10))
    assert np.allclose(res[~finite], FLOOR.linear)
    assert np.allclose(selection.systematic_residuals(product, rows, FLOOR, gain=566.0), 566.0 * res)
    with pytest.raises(ValueError, match="finite floor"):
        selection.systematic_residuals(product, rows, selection.Floor(math.nan, "refused", "none"))
    with pytest.raises(ValueError, match="chain gain"):
        selection.systematic_residuals(product, rows, FLOOR, gain=0.0)


def test_selection_then_replay_on_the_fixture(product):
    split = blocks.split_blocks(product.frame_unit_index, product.unit_time, product.selected,
                                frame_time=product.frame_time, minimum_months=1)
    assert split.status in ("supported", "insufficient_support")
    result = selection.select_operating_point(
        product, split.calibration, split.evaluation, anchor_bin=128, bulk_mask=_bulk(), r_tol=100.0,
        floor=FLOOR, era_label="fixture era", minimum_observed_months=1, minimum_span_days=1e-6,
        bootstrap_replicates=50)
    assert result.status == "feasible", result.refusal
    assert result.claim_status == "screening"
    assert result.rho is not None and 1 <= result.rho <= result.bulk_size == 4
    assert result.eta_q16 is not None and result.eta == result.eta_q16 / 65536
    assert 0.0 <= result.masked_fraction < 1.0 and result.tolerance_fraction <= 1.0
    assert result.plateau is not None and result.plateau.members >= 1
    assert result.plateau.eta_low <= result.eta <= result.plateau.eta_high
    assert result.provisional["stability.maximum_cost_ratio"] == selection.PROVISIONAL_MAX_COST_RATIO
    assert result.source_id.startswith("sha256:") and len(result.policy_sha256) == 64
    ev = result.evaluation
    assert ev is not None and ev.frames == result.evaluation_frames
    assert ev.kept + round(ev.masked_fraction * ev.frames) == ev.frames
    assert math.isnan(ev.false_alarm_rate) and "not measurable" in ev.false_alarm_basis
    row = result.as_row()
    assert row["status"] == "feasible" and row["rho"] == result.rho and row["eta_q16"] == result.eta_q16
    out = selection.write_selection_rows([result], product.path.parent / "sel.csv")
    assert out.read_text().splitlines()[0].startswith("channel,freq_id,era,anchor_bin")


def test_off_era_replay_reports_the_false_alarm_rate(product):
    split = blocks.split_blocks(product.frame_unit_index, product.unit_time, product.selected,
                                frame_time=product.frame_time, minimum_months=1)
    result = selection.select_operating_point(
        product, split.calibration, split.evaluation, anchor_bin=128, bulk_mask=_bulk(), r_tol=100.0,
        floor=FLOOR, era_label="off era", off_era=True, minimum_observed_months=1, minimum_span_days=1e-6,
        bootstrap_replicates=20)
    assert result.status == "feasible", result.refusal
    assert result.evaluation.false_alarm_rate == result.evaluation.masked_fraction


def test_refusals_are_reported_not_raised(product):
    nothing = np.zeros(product.n_frames, dtype=bool)
    r = selection.select_operating_point(product, nothing, nothing, anchor_bin=128, bulk_mask=_bulk(), r_tol=1.0,
                                         floor=FLOOR, era_label="e")
    assert r.status == "refused" and "no usable frames" in r.refusal
    # a tolerance no point can meet is a selector outcome, not a refusal
    split = blocks.split_blocks(product.frame_unit_index, product.unit_time, product.selected,
                                frame_time=product.frame_time, minimum_months=1)
    tight = selection.select_operating_point(
        product, split.calibration, split.evaluation, anchor_bin=128, bulk_mask=_bulk(), r_tol=1e-12,
        floor=FLOOR, era_label="e", minimum_observed_months=1, minimum_span_days=1e-6)
    assert tight.status == "no feasible point" and tight.rho is None
    # the register's calendar-support gate refuses a short calibration block: the point is still
    # computed and reported, labelled diagnostic, with the refusal beside it
    short = selection.select_operating_point(
        product, split.calibration, split.evaluation, anchor_bin=128, bulk_mask=_bulk(), r_tol=100.0,
        floor=FLOOR, era_label="e")
    assert short.claim_status == "diagnostic" and "stability" in short.refusal
    assert short.status in ("feasible", "no feasible point") and short.stability["status"].startswith("refused")
    if short.status == "feasible":
        assert short.rho is not None and short.evaluation is not None
    # the evaluated surface is kept and written, with the selected point marked
    assert short.points and all(set(p) == set(selection.POINT_COLUMNS) for p in short.points)
    summary = selection.surface_summary(short)
    assert summary["surface_points"] == len(short.points) and summary["min_r_sys"] <= min(p["r_sys"] for p in short.points if p["r_sys"] == p["r_sys"])
    out = selection.write_operating_points(short, product.path.parent / "op.csv")
    lines = out.read_text().splitlines()
    assert lines[0] == "channel," + ",".join(selection.POINT_COLUMNS) + ",selected" and len(lines) == len(short.points) + 1
    assert sum(line.endswith(",True") for line in lines[1:]) == (1 if short.status == "feasible" else 0)


def test_rows_carry_the_unmasked_residual_and_the_evaluation_intervals(tmp_path):
    from rfisher_results.archive import selection as sel_mod
    row = sel_mod.SelectionResult(
        channel=35, freq_id=521, era_label="e", anchor_bin=1, bulk_size=125, r_tol=0.03, floor=FLOOR, calibration_frames=10,
        evaluation_frames=10, frames_without_time=0, status="refused", refusal="x", claim_status="", rho=None,
        rank_fraction=float("nan"), eta_q16=None, eta=float("nan"), masked_fraction=float("nan"),
        systematic_residual=float("nan"), tolerance_fraction=float("nan"), cost=float("nan"), plateau=None, evaluation=None,
        unmasked_residual=0.5).as_row()
    assert row["r_sys_unmasked_calibration"] == 0.5 and row["bootstrap_blocks_evaluation"] == 0
    for key in ("masked_fraction_evaluation_q16", "r_sys_evaluation_q84", "r_sys_unmasked_evaluation"):
        assert key in row
