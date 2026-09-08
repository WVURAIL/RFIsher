"""The archive driver end to end on synthetic v5 products (no per-frame spectra)."""
from __future__ import annotations

import csv
from functools import partial
import importlib.util
import json
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
