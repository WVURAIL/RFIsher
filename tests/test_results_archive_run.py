"""The archive driver end to end on synthetic v5 products (no per-frame spectra)."""
from __future__ import annotations

import csv
from functools import partial
import importlib.util
import json
import math
import multiprocessing
from pathlib import Path

import numpy as np
import pytest

from rfisher_results.archive import run as archive_run

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("v5_fixture_run", ROOT / "tests" / "test_pilotproxy_v5.py")
v5_fixture = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v5_fixture)


def _products(tmp_path):
    d = tmp_path / "products"
    d.mkdir()
    for channel, fid in ((35, 521), (33, 552)):
        path = v5_fixture._write_product(d / f"{fid}.npz", channel)
        with np.load(path, allow_pickle=False) as z:
            frames = int(np.asarray(z["valid"]).shape[0])
        v5_fixture._replace(path, baseband_power_linear=np.full((frames, 1), 4.0))
    return d


def test_station_records_follow_the_recorded_months():
    assert archive_run.station_records(19) == {"2024-12": "sign-off"}
    assert archive_run.station_records(35) == {"2021-11": "sign-on"}
    assert archive_run.station_records(29) == {}


@pytest.mark.parametrize("workers", [1, 2])
def test_driver_runs_every_stage_and_writes_the_tree(tmp_path, monkeypatch, synthetic_archive_health, workers):
    def unavailable():
        raise ValueError("test: no authenticated bank")
    monkeypatch.setattr(archive_run.worlds, "tolerances", unavailable)
    monkeypatch.setattr(archive_run, "ProcessPoolExecutor", partial(
        archive_run.ProcessPoolExecutor, mp_context=multiprocessing.get_context("spawn")))
    products = _products(tmp_path)
    out = tmp_path / "out"
    summary = archive_run.run_archive(products, out, workers=workers, replicates=5, seed=3, generated="2026-09-07T00:00:00+00:00")
    assert summary["errors"] == [], summary["errors"]
    assert summary["channels"] == [33, 35]
    run = json.loads((out / "ledger" / "run.json").read_text())
    assert run["era_config_digest"] and run["bootstrap"] == {"replicates": 5, "seed": 3}
    assert run["provisional"]["stability.maximum_cost_ratio"] == 1.05
    assert run["worlds_contract"]["time_rule"] == "target_only"
    assert run["worlds_contract"]["target_years"] == archive_run.worlds.TARGET_YEARS
    assert run["worlds_contract"]["physical_recovery_certified"] is False
    rows = list(csv.DictReader((out / "ledger" / "ledger.csv").open()))
    assert [r["channel"] for r in rows] == ["33", "35"]
    for r in rows:
        assert r["era_n_eras"] and r["blocks_status"] in ("supported", "insufficient_support", "empty")
        assert r["anchor_status"] in ("ok", "empty")
        assert r["containment_present"] == "False"          # fixtures carry no per-frame spectra
        assert r["geometry_allocation_low_mhz"] and r["product_n_frames"] and r["product_health_schema"]
        assert r["null_evaluation_present"] == "False"       # no era on the small fixture, so no evaluation block
        assert r["null_null_source"]
        assert r["screening_screening_class"]
        assert "skipped" in r["notes"]           # no per-frame spectra, or no populated era on the small fixture
    for name in ("eras_channels.csv", "anchors.csv", "nulls.csv", "screening.csv", "channel_tolerances.csv"):
        assert (out / "tables" / name).is_file(), name
    # a table with no rows is not written: the small fixture forms no era, so there is no per-era table
    assert all(r["era_n_eras"] == "0" for r in rows) and not (out / "tables" / "eras.csv").exists()
    assert (out / "channels" / "ch35" / "eras.json").is_file() and (out / "channels" / "ch35" / "anchor_contrast.csv").is_file()
    ch35 = json.loads((out / "ledger" / "channels" / "ch35_fid521.json").read_text())
    assert ch35["sections"]["tolerance"]["r_tol_dilation"] is None
    assert "no authenticated bank" in ch35["sections"]["tolerance"]["refusal"]
    assert ch35["sections"]["evaluation_contract"]["station_event_basis"] == "archive-inferred, not independently verified"
    assert ch35["sections"]["screening"]["off_through"] == "2021-10"


def test_driver_passes_an_author_dated_era_list_to_its_channel_and_records_it(tmp_path, monkeypatch, synthetic_archive_health):
    def unavailable():
        raise ValueError("test: no authenticated bank")
    monkeypatch.setattr(archive_run.worlds, "tolerances", unavailable)
    monkeypatch.setattr(archive_run, "ProcessPoolExecutor", partial(
        archive_run.ProcessPoolExecutor, mp_context=multiprocessing.get_context("spawn")))
    products = _products(tmp_path)
    out = tmp_path / "out"
    spec = {33: [("2020-01", "2020-06", "archive start")]}
    summary = archive_run.run_archive(products, out, workers=1, replicates=5, seed=3,
                                      generated="2026-09-23T00:00:00+00:00", era_overrides=spec)
    # the small fixture has no populated month, so the imposed list is refused on its own channel only
    assert summary["channels"] == [35]
    assert len(summary["errors"]) == 1 and "holds no populated month" in summary["errors"][0]["error"]
    run = json.loads((out / "ledger" / "run.json").read_text())
    assert run["era_overrides"] == {"33": [["2020-01", "2020-06", "archive start"]]}
    assert len(run["era_overrides_sha256"]) == 64


@pytest.mark.parametrize("point,evaluation,expected", [
    (0.02, 0.04, False), (0.04, 0.02, True), (0.02, float("nan"), False), (0.02, 0.02, True),
])
def test_world_floor_flag_belongs_to_evaluation_policy(monkeypatch, point, evaluation, expected):
    from types import SimpleNamespace
    from rfisher_results.archive import run, worlds
    rows = [{"world": name, "parameter": parameter, "bin_index": 7, "z_lo": 1.5, "z_hi": 1.6,
             "tolerance": 1.0, "at_target": True}
            for name, _, _, _ in worlds.WORLDS for parameter in worlds.PARAMETERS]
    monkeypatch.setattr(worlds, "tolerances", lambda: rows)
    monkeypatch.setattr(run.tolerances, "channel_tolerances",
                        lambda **kwargs: [SimpleNamespace(channel=29, bins=(7,))])
    result = run._worlds([{
        "record": SimpleNamespace(channel=29),
        "operating_row": {"operating_r_sys": point, "operating_masked_fraction": 0.5, "r_floor": 0.02},
        "selection_row": {"r_sys_evaluation": evaluation},
        "null_row": {"floor_db": -20.0}, "chain_row": {"chain_gain": 2.0},
    }])[0]
    assert result.floor_bound is expected


def test_coarse_frontier_minimum_on_a_rounding_plateau_is_its_least_mask():
    """Channel 18 of the 2026-09-24 release: R is the same to 1e-15 from eta_c 1.0 to 1.03 (every kept frame
    at the floor). The exact minimum sat at eta_c 1.0 by the last digit; the reported point is the least mask."""
    from rfisher_results.archive.run import _frontier_summary
    plateau = [(1.0, 0.971702780251311, 163.4505217626282), (1.005, 0.9047, 163.45052176262828),
               (1.01, 0.8310, 163.45052176262826), (1.015, 0.7743, 163.4505217626282),
               (1.02, 0.7242, 163.45052176262823), (1.025, 0.6833, 163.45052176262826),
               (1.03, 0.6477688, 163.45052176262826), (1.035, 0.6203, 163.87742218003282), (1.5, 0.1429, 506.6)]
    frontier = [{"eta_c": e, "masked_fraction": f, "R": R, "evaluable": True} for e, f, R in plateau]
    frontier.append({"eta_c": 0.99, "masked_fraction": 0.999, "R": 1.0, "evaluable": False})   # not evaluable: ignored
    s = _frontier_summary(frontier)
    assert s["coarse_min_R_eta"] == 1.03 and s["coarse_min_R_masked_fraction"] == 0.6477688
    assert s["coarse_min_R"] == 163.45052176262826 and s["coarse_R_at_flag"] == 163.4505217626282
    assert math.isnan(_frontier_summary([])["coarse_min_R_eta"])
    # a real minimum is not a tie
    frontier[3]["R"] = 163.0
    assert _frontier_summary(frontier)["coarse_min_R_eta"] == 1.015
