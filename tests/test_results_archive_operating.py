"""The operating point: the frontier, the knee, and what the mask buys."""
from __future__ import annotations

import math

import pytest

from rfisher_results.archive import operating


def _point(rho, eta_q16, f, kept, r, cost=None):
    return {"rho": rho, "eta_q16": eta_q16, "eta": eta_q16 / 65536, "masked_fraction": f, "kept": kept,
            "r_sys": r, "cost": cost if cost is not None else (1.0 / (1.0 - f) if f < 1 else math.inf)}


def test_the_frontier_is_the_lower_envelope_and_drops_unsupported_points():
    points = [_point(1, 65536, 0.0, 1000, 10.0), _point(2, 66000, 0.5, 500, 1.0), _point(3, 67000, 0.5, 500, 2.0),
              _point(4, 68000, 0.8, 200, 0.9), _point(5, 69000, 0.9, 20, 0.1),        # keeps too few: not a point
              _point(6, 70000, 0.95, 50, 0.85)]
    f = operating.pareto_frontier(points)
    assert [p.masked_fraction for p in f] == [0.0, 0.5, 0.8, 0.95]
    assert [p.r_sys for p in f] == [10.0, 1.0, 0.9, 0.85]      # the 0.5 point at r = 2.0 is dominated
    assert all(p.kept >= operating.MIN_KEPT for p in f)
    assert operating.pareto_frontier([_point(1, 65536, 0.9, 5, 0.1)]) == []


def test_the_knee_is_the_corner_not_the_end():
    """A frontier that falls steeply and then flattens: the point is the corner, not the last point."""
    points = [_point(1, 65536 + i, f, 1000, r) for i, (f, r) in enumerate(
        [(0.0, 100.0), (0.2, 20.0), (0.4, 4.0), (0.5, 1.0), (0.7, 0.95), (0.9, 0.92), (0.99, 0.90)])]
    o = operating.choose(7, points)
    assert o.status == "measured" and o.point is not None
    assert 0.4 <= o.point.masked_fraction <= 0.7           # the corner, not 0.99
    assert o.r_floor == 0.90 and o.keep_everything_r == 100.0
    assert o.suppression == pytest.approx(100.0 / o.point.r_sys)
    # the margin rule chases the flat tail, which is why it is reported and not used
    assert o.sensitivity[0.05][0] >= o.point.masked_fraction
    assert o.point is o.knee


def test_a_channel_with_no_usable_point_says_so():
    o = operating.choose(9, [_point(1, 65536, 0.9, 5, 0.1)])
    assert o.status == "no frontier" and o.point is None and math.isnan(o.suppression)
    assert any("keeps" in n for n in o.notes)
    row = o.as_row()
    assert row["channel"] == 9 and row["operating_rho"] == -1 and math.isnan(row["r_floor"])


def test_rows_round_trip(tmp_path):
    points = [_point(1, 65536 + i, f, 1000, r) for i, (f, r) in enumerate([(0.0, 10.0), (0.4, 1.0), (0.9, 0.9)])]
    o = operating.choose(3, points)
    out = operating.write_operating_points([o], tmp_path / "op.csv")
    lines = out.read_text().splitlines()
    assert lines[0].startswith("channel,frontier_points,r_floor") and len(lines) == 2
    row = o.as_row()
    assert row["suppression_db"] == pytest.approx(10 * math.log10(o.suppression))
    assert set(row) >= set(operating.OPERATING_COLUMNS)
