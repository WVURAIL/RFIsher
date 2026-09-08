"""The four delay-cut worlds: the tolerance cache, the per-channel carry-through, and the CSV it writes."""
from __future__ import annotations

import csv
import math

import pytest

from rfisher_results.archive import worlds


def _rows():
    """A synthetic tolerance table over two bins: tighter in the cut worlds, one gate refusal."""
    out = []
    for world, _, _, _ in worlds.WORLDS:
        scale = {"none": 1.0, "peak1": 0.5, "peak2": 0.25, "deployed": 0.1}[world]
        for ib, (lo, hi) in enumerate(((1.7, 1.8), (1.8, 1.9)), start=7):
            for i, p in enumerate(worlds.PARAMETERS):
                tol = math.nan if (world == "deployed" and p == "fs8" and ib == 8) else scale * (1e-2 / (i + 1)) * (1 + ib)
                out.append({"world": world, "bin_index": ib, "z_lo": lo, "z_hi": hi, "parameter": p,
                            "tolerance": tol, "at_target": not math.isnan(tol),
                            "years_used": worlds.TARGET_YEARS if not math.isnan(tol) else math.nan,
                            "years_accepted": 0 if math.isnan(tol) else 3, "years_refused": 2})
    return out


def test_suppression_comes_from_the_chains_own_table():
    from rfisher import residual
    assert worlds.suppression_db("none") == 0.0
    assert worlds.suppression_db("deployed") == residual.DELAY_SUPPRESSION_DB["aggressive_200ns"]
    assert worlds.suppression_db("peak1") == residual.DELAY_SUPPRESSION_DB["bao_peak1"]
    assert worlds.suppression_db("peak2") == residual.DELAY_SUPPRESSION_DB["bao_peak2"]
    # the cuts are ordered: a harder cut removes more shelf
    assert (worlds.suppression_db("none") < worlds.suppression_db("peak1")
            < worlds.suppression_db("peak2") < worlds.suppression_db("deployed"))


def test_the_binding_tolerance_is_the_smallest_over_the_channels_bins():
    rows = _rows()
    one = worlds.tolerance_of(rows, "none", (7,), "aperp")
    both = worlds.tolerance_of(rows, "none", (7, 8), "aperp")
    assert one == pytest.approx(8e-2)
    assert both == pytest.approx(8e-2)           # bin 7 binds: 1e-2 * 8 < 1e-2 * 9
    assert worlds.tolerance_of(rows, "none", (8,), "aperp") == pytest.approx(9e-2)


def test_a_gate_refusal_propagates_across_overlapping_bins():
    rows = _rows()
    assert math.isnan(worlds.tolerance_of(rows, "deployed", (7, 8), "fs8"))
    assert math.isnan(worlds.tolerance_of(rows, "deployed", (8,), "fs8"))        # bin 8 alone does not


def test_bin_span_covers_every_bin_the_channel_overlaps():
    assert worlds.bin_span(_rows(), (7, 8)) == (1.7, 1.9)
    assert worlds.bin_span(_rows(), (8,)) == (1.8, 1.9)
    assert all(math.isnan(v) for v in worlds.bin_span(_rows(), ()))


def test_a_world_divides_the_residual_by_its_own_suppression():
    cw = worlds.channel_worlds(29, (7,), 100.0, 0.4, _rows())
    assert cw.status == "conditional"
    assert cw.residuals["none"] == pytest.approx(100.0)
    assert cw.residuals["deployed"] == pytest.approx(100.0 / 10 ** (11.4 / 10))
    # R is not simply the suppression: the tolerance moves with the bank too
    assert cw.ratios[("none", "aperp")] == pytest.approx(100.0 / 8e-2)
    assert cw.ratios[("deployed", "aperp")] == pytest.approx(cw.residuals["deployed"] / (0.1 * 8e-2))


def test_a_channel_without_an_operating_point_says_so():
    cw = worlds.channel_worlds(15, (7,), math.nan, math.nan, _rows())
    assert cw.status == "no operating point"
    assert cw.ratios == {}
    assert "no operating point" in cw.notes[0]


def test_a_channel_that_overlaps_no_forecast_bin_says_so():
    cw = worlds.channel_worlds(36, (), 10.0, 0.1, _rows())
    assert cw.status == "no overlapping bin"
    assert math.isnan(cw.z_lo) and math.isnan(cw.z_hi)


def test_a_refused_parameter_is_named_in_the_notes():
    cw = worlds.channel_worlds(18, (8,), 100.0, 0.5, _rows())
    assert cw.status == "conditional"
    assert math.isnan(cw.ratios[("deployed", "fs8")])
    assert "deployed/fs8" in cw.notes[0]


def test_the_row_carries_every_world_and_parameter():
    row = worlds.channel_worlds(29, (7, 8), 100.0, 0.4, _rows()).as_row()
    assert row["channel"] == 29 and row["bins"] == "7;8"
    for world, _, _, _ in worlds.WORLDS:
        assert f"{world}_r" in row and row[f"{world}_suppression_db"] == worlds.suppression_db(world)
        for p in worlds.PARAMETERS:
            assert f"{world}_{p}_R" in row and f"{world}_{p}_r_tol" in row


def test_the_csv_round_trips_floats_exactly(tmp_path):
    rows = _rows()
    results = [worlds.channel_worlds(29, (7,), 123.456789, 0.4, rows),
               worlds.channel_worlds(15, (), math.nan, math.nan, rows)]
    path = worlds.write_world_rows(results, tmp_path / "worlds.csv")
    with path.open(newline="", encoding="utf-8") as fh:
        back = list(csv.DictReader(fh))
    assert [r["channel"] for r in back] == ["29", "15"]
    assert float(back[0]["none_r"]) == 123.456789
    assert "np.float64" not in path.read_text(encoding="utf-8")       # numpy scalars are written as plain floats


def test_unauthenticated_cache_is_not_accepted(tmp_path):
    path = tmp_path / "cache.csv"
    path.write_text("old,unverified,cache\n")
    assert not worlds._cache_is_current(path, tmp_path)
    with pytest.raises(ValueError, match="required bias-response bank is missing"):
        worlds.tolerances(bank_dir=tmp_path, cache=path)


def test_authenticated_cache_roundtrip_and_content_changes(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace
    for _, filename, _, _ in worlds.WORLDS:
        (tmp_path / filename).write_bytes(b"fixture bank")
    bt = SimpleNamespace(load_bias_bank=lambda *a, **k: SimpleNamespace(evaluation_identity={"source": "v1"}))
    monkeypatch.setattr(worlds, "_bias_tolerance", lambda: bt)
    path = tmp_path / "cache.csv"
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(worlds.CACHE_COLUMNS))
        w.writeheader()
        w.writerows(_rows())
    path.with_suffix(".provenance.json").write_text(json.dumps(worlds._cache_identity(path, tmp_path)))
    assert worlds._cache_is_current(path, tmp_path)
    back = worlds.tolerances(bank_dir=tmp_path, cache=path)
    assert isinstance(back[0]["bin_index"], int)
    assert isinstance(back[0]["at_target"], bool)
    old = path.read_bytes()
    path.write_bytes(old + b"\n")
    assert not worlds._cache_is_current(path, tmp_path)
    path.write_bytes(old)
    (tmp_path / worlds.WORLDS[0][1]).write_bytes(b"changed bank")
    assert not worlds._cache_is_current(path, tmp_path)


def test_target_time_refusal_is_not_replaced_by_another_year(monkeypatch):
    from types import SimpleNamespace
    target_hours = worlds.TARGET_YEARS * worlds.survey.OVERVIEW_ONSKY_YEAR_HOURS
    bank = SimpleNamespace(paramnames=list(worlds.PARAMETERS), zs=[1.3, 1.4], F=lambda ib, t: t)
    bt = SimpleNamespace(
        load_bias_bank=lambda *a, **k: bank,
        bias_per_unit_r=lambda *a: ({p: 1. for p in worlds.PARAMETERS}, {p: .01 for p in worlds.PARAMETERS}),
        stability=lambda b, ib, t, names, p, frac: (2. if t == target_hours and p == "aperp" else 1., 1))
    monkeypatch.setattr(worlds, "_bias_tolerance", lambda: bt)
    rows = worlds.compute_tolerances()
    for r in rows:
        if r["parameter"] == "aperp":
            assert not r["at_target"] and math.isnan(r["tolerance"])
            assert r["years_accepted"] > 0
        else:
            assert r["at_target"] and r["years_used"] == worlds.TARGET_YEARS
