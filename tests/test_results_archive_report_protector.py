"""The protector specification: the decibels a cleaner would have to deliver, on a synthetic ledger."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

import pytest

from rfisher_results.archive.report import core, protector
from rfisher_results.archive.report import build as report_build
from rfisher_results.archive.worlds import PARAMETERS, WORLDS, suppression_db

REAL_RUN = Path(os.environ.get("RFISHER_ARCHIVE_RESULTS", "/home/djg/rail/results/archive_v5_2026-09-07b"))
WORLD_NAMES = tuple(w[0] for w in WORLDS)
GROWTH = "fs8"
DILATIONS = tuple(p for p in PARAMETERS if p != GROWTH)


def _rows(frag):
    """The body rows of a booktabs fragment, cells split and stripped."""
    body = frag.tex.split(r"\midrule", 1)[1].split(r"\bottomrule")[0]
    out = []
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("\\"):
            continue
        out.append([cell.strip() for cell in line.rstrip("\\").split("&")])
    return out


def _run(tmp_path, channels):
    """A ledger whose channels carry ``(r_evaluation, floor_bound)`` through every world.

    Each world's tolerance is 1e-2 for every parameter, so a channel's ratio is
    its evaluation residual over the world's suppression, and the requirement
    the fragment prints is a quantity the test can compute in one line.
    """
    ledger = tmp_path / "ledger"
    (ledger / "channels").mkdir(parents=True, exist_ok=True)
    names = []
    for ch, (r_eval, floor_bound) in sorted(channels.items()):
        section = {"channel": ch, "bins": "7", "z_lo": 1.7, "z_hi": 1.8, "r_point": 1.0,
                   "masked_fraction": 0.4, "status": "measured", "notes": "",
                   "r_evaluation": r_eval, "floor_bound": floor_bound}
        for world in WORLD_NAMES:
            drop = 10 ** (suppression_db(world) / 10)
            for p in PARAMETERS:
                section[f"{world}_{p}_r_tol"] = 1e-2
                section[f"{world}_{p}_evaluation_R"] = (
                    (r_eval / drop) / 1e-2 if r_eval is not None else math.nan)
        name = f"channels/ch{ch}_fid{900 - ch}.json"
        names.append(name)
        (ledger / "channels" / f"ch{ch}_fid{900 - ch}.json").write_text(json.dumps(
            {"channel": ch, "freq_id": 900 - ch, "product": f"{900 - ch}.npz", "product_sha256": "b" * 64,
             "notes": [], "sections": {"worlds": section}}))
    (ledger / "run.json").write_text(json.dumps(
        {"schema": {"name": "rfisher-archive-ledger", "version": 1}, "generated": "x",
         "producer": {"commit": "a" * 40}, "channels": names}))
    return core.load_run(tmp_path)


def _cells(frag, ch):
    return {n.key.rsplit(".", 2)[-2]: n.value for n in frag.numbers if n.key.endswith(f".ch{ch}")}


# ------------------------------------------------- the requirement itself
@pytest.mark.parametrize("ratio, expected", [(1.0, 0.0), (10.0, 10.0), (100.0, 20.0), (0.5, -3.0103)])
def test_the_requirement_is_ten_log_ten_of_the_ratio(ratio, expected):
    assert protector.requirement_db(ratio) == pytest.approx(expected, abs=1e-3)


@pytest.mark.parametrize("ratio", [None, math.nan, math.inf, 0.0, -1.0])
def test_no_requirement_is_stated_where_the_ratio_is_not_a_positive_number(ratio):
    assert protector.requirement_db(ratio) is None


def test_a_channel_already_inside_is_quoted_as_margin_not_as_a_requirement(tmp_path):
    """A negative requirement is the whole point of the sign convention: it reads as headroom."""
    frag = protector.build(_run(tmp_path, {29: (1e-3, False)}))
    got = _cells(frag, 29)
    assert got["peak2_dilation_db"] < 0.0
    assert _cells(frag, 29)["basis"] == "model"


# ------------------------------------------------- the table
def test_every_world_column_is_the_ratio_that_world_leaves(tmp_path):
    """The cut is booked before the protector: its columns are the remainder, not the whole job."""
    frag = protector.build(_run(tmp_path, {29: (1.0, False)}))
    got = _cells(frag, 29)
    # tolerance 1e-2 on every parameter, so the uncut ratio is 100 and the requirement 20 dB
    assert got["none_dilation_db"] == pytest.approx(20.0, abs=1e-3)
    assert got["none_growth_db"] == pytest.approx(20.0, abs=1e-3)
    # the 110 ns world has already taken its own suppression out of the same residual
    assert got["peak2_dilation_db"] == pytest.approx(20.0 - suppression_db("peak2"), abs=1e-3)


def test_a_channel_with_no_held_out_residual_is_not_in_the_table(tmp_path):
    frag = protector.build(_run(tmp_path, {29: (1.0, False), 21: (None, False)}))
    assert [r[0] for r in _rows(frag)] == ["29"]


def test_a_run_with_no_held_out_residual_states_why_rather_than_printing_a_table(tmp_path):
    frag = protector.build(_run(tmp_path, {21: (None, False)}))
    assert frag.tex == ""
    assert "no channel carries a held-out residual" in frag.notes[0]


# ------------------------------------------------- the band-level specification
def test_the_curve_counts_channels_at_each_stated_depth(tmp_path):
    """The specification is a curve: the k-th smallest requirement is what it takes to save k channels."""
    # after the 110 ns cut these need about 1.8, 11.8 and 21.8 dB on the dilations
    frag = protector.build(_run(tmp_path, {21: (0.1, False), 29: (1.0, False), 32: (10.0, False)}))
    got = {n.key.rsplit(".", 1)[-1]: n.value for n in frag.numbers}
    assert (got["n_dilation_at_10db"], got["n_dilation_at_20db"], got["n_dilation_at_30db"]) == (1, 2, 3)
    assert got["cheapest_dilation_channel"] == 21


def test_a_floor_bound_channel_is_marked_and_left_out_of_the_specification(tmp_path):
    """An upper limit is not a specification: the requirement may be zero and the table cannot tell."""
    frag = protector.build(_run(tmp_path, {21: (0.1, True), 29: (1.0, False)}))
    got = {n.key.rsplit(".", 1)[-1]: n.value for n in frag.numbers}
    assert _cells(frag, 21)["basis"] == "model/floor"
    assert (got["n_floor_bound"], got["n_measured"], got["channels"]) == (1, 0, 2)
    assert got["n_conditional"] == 2
    # ch21 is the cheaper of the two and is still not what the specification is quoted from
    assert got["cheapest_dilation_channel"] == 29
    assert got["n_dilation_at_20db"] == 1
    assert any("neither unavoidable contamination nor a calibrated confidence bound" in note for note in frag.notes)


def test_a_floor_bound_requirement_is_recorded_as_bounded_rather_than_measured(tmp_path):
    frag = protector.build(_run(tmp_path, {21: (0.1, True)}))
    status = {n.key.rsplit(".", 2)[-2]: n.status for n in frag.numbers if n.key.endswith(".ch21")}
    assert status["none_dilation_db"] == "derived"


def test_the_fragment_is_registered_in_the_report(tmp_path):
    assert "protector" in report_build.TABLE_MODULES


# ------------------------------------------------- the run of record
@pytest.mark.skipif(not (REAL_RUN / "ledger" / "run.json").exists(), reason="the archive run is not on this machine")
def test_the_run_of_record_states_a_finite_requirement_for_every_priced_channel():
    """Every failing channel fails by a finite amount; that amount is what the chapter claims."""
    frag = protector.build(core.load_run(REAL_RUN))
    values = [n.value for n in frag.numbers if "_db.ch" in n.key and n.value is not None]
    assert values, "the run of record prices no channel"
    assert all(math.isfinite(v) for v in values)
    got = {n.key.rsplit(".", 1)[-1]: n.value for n in frag.numbers}
    # the band splits: a handful within reach of a cleaner, the rest tens of decibels out
    assert got["n_dilation_at_10db"] >= 1
    assert got["n_dilation_at_10db"] <= got["n_dilation_at_30db"] < got["channels"]
