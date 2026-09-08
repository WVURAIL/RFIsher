"""Target-time tolerances must price every overlap and both dilations."""
import csv
import math

import pytest

from rfisher_results.archive import tolerances as tol, worlds


def _rows(apar=0.02):
    return [
        {"world": "none", "bin_index": b, "z_lo": lo, "z_hi": hi,
         "parameter": p, "tolerance": v * scale, "at_target": True,
         "years_used": 1.0, "years_accepted": 1, "years_refused": 0}
        for b, lo, hi, scale in ((5, 1.3, 1.4, 1.), (6, 1.4, 1.5, 0.5))
        for p, v in (("aperp", 0.01), ("apar", apar), ("fs8", 0.001))
    ]


def test_target_tolerances_and_every_nonzero_overlap_are_used(tmp_path):
    rows = {r.channel: r for r in tol.channel_tolerances(channels=(34, 35), derived_rows=_rows())}
    assert rows[35].bins == (5,)
    assert rows[35].r_tol_dilation == pytest.approx(0.01)
    assert rows[34].bins == (5, 6)
    assert rows[34].r_tol_dilation == pytest.approx(0.005)
    assert rows[34].r_tol_fs8 == pytest.approx(0.0005)
    path = tol.write_channel_tolerances(list(rows.values()), tmp_path / "t.csv")
    back = list(csv.DictReader(path.open()))
    assert list(back[0]) == list(tol.COLUMNS)
    assert all(r["tolerance_basis"].startswith("caller-supplied") for r in back)


def test_parallel_dilation_is_binding_when_tighter():
    row = tol.channel_tolerances(channels=(35,), derived_rows=_rows(apar=0.003))[0]
    assert row.r_tol_dilation == pytest.approx(0.003)
    assert row.dilation_binding == "apar"


def test_one_refused_overlap_cannot_be_dropped():
    rows = _rows()
    next(r for r in rows if r["bin_index"] == 6 and r["parameter"] == "apar")["tolerance"] = math.nan
    row = tol.channel_tolerances(channels=(34,), derived_rows=rows)[0]
    assert math.isnan(row.r_tol_dilation)
    assert "refused" in row.refusal


def test_another_time_is_not_a_target_time_tolerance():
    rows = _rows()
    for r in rows:
        if r["parameter"] == "aperp":
            r.update(at_target=False, years_used=0.25)
    row = tol.channel_tolerances(channels=(35,), derived_rows=rows)[0]
    assert math.isnan(row.r_tol_dilation)


def test_missing_bank_identity_does_not_fall_back_to_published_constants(monkeypatch):
    def missing():
        raise ValueError("bank identity mismatch")
    monkeypatch.setattr(worlds, "tolerances", missing)
    rows = tol.channel_tolerances(channels=(14, 35))
    assert all(math.isnan(r.r_tol_dilation) for r in rows)
    assert all("bank identity mismatch" in r.refusal for r in rows)


def test_missing_growth_is_refused_without_discarding_dilation():
    rows = [r for r in _rows() if r["parameter"] != "fs8"]
    row = tol.channel_tolerances(channels=(35,), derived_rows=rows)[0]
    assert math.isnan(row.r_tol_fs8)
    assert row.r_tol_dilation == pytest.approx(0.01)


def test_bin_missing_in_all_parameters_cannot_shrink_the_channel():
    rows = [r for r in _rows() if r["bin_index"] == 5]
    row = tol.channel_tolerances(channels=(34,), derived_rows=rows)[0]
    assert math.isnan(row.r_tol_dilation)
    assert "full channel" in row.refusal
