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
                            "tolerance": tol, "years_accepted": 0 if math.isnan(tol) else 3, "years_refused": 2})
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


def test_a_gate_refusal_is_skipped_not_propagated():
    rows = _rows()
    assert math.isfinite(worlds.tolerance_of(rows, "deployed", (7, 8), "fs8"))   # bin 7 survives
    assert math.isnan(worlds.tolerance_of(rows, "deployed", (8,), "fs8"))        # bin 8 alone does not


def test_bin_span_covers_every_bin_the_channel_overlaps():
    assert worlds.bin_span(_rows(), (7, 8)) == (1.7, 1.9)
    assert worlds.bin_span(_rows(), (8,)) == (1.8, 1.9)
    assert all(math.isnan(v) for v in worlds.bin_span(_rows(), ()))


def test_a_world_divides_the_residual_by_its_own_suppression():
    cw = worlds.channel_worlds(29, (7,), 100.0, 0.4, _rows())
    assert cw.status == "measured"
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
    assert cw.status == "measured"
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


def test_the_cache_is_read_back_with_the_types_the_analysis_needs(tmp_path):
    path = tmp_path / "cache.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(worlds.CACHE_COLUMNS), lineterminator="\n")
        w.writeheader()
        for r in _rows():
            w.writerow({k: worlds._cell(r[k]) for k in worlds.CACHE_COLUMNS})
    path.touch()
    back = worlds.tolerances(bank_dir=tmp_path, cache=path)           # no bank present: the cache stands
    assert len(back) == len(_rows())
    assert isinstance(back[0]["bin_index"], int) and isinstance(back[0]["z_lo"], float)
    assert math.isnan([r for r in back if r["world"] == "deployed" and r["parameter"] == "fs8"
                       and r["bin_index"] == 8][0]["tolerance"])


def test_the_shipped_cache_covers_every_world_and_parameter():
    if not worlds.CACHE.is_file():
        pytest.skip("the tolerance cache has not been built on this machine")
    rows = worlds.tolerances()
    assert {r["world"] for r in rows} == set(w[0] for w in worlds.WORLDS)
    assert {r["parameter"] for r in rows} == set(worlds.PARAMETERS)
    per_world = {w[0]: [r for r in rows if r["world"] == w[0]] for w in worlds.WORLDS}
    assert len(set(len(v) for v in per_world.values())) == 1          # every world covers the same bins
    assert all(math.isfinite(r["tolerance"]) for r in rows if r["years_accepted"])
