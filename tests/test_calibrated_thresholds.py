import importlib.util
import csv
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
ppcal = ModuleType("ppcal")
ppcal.era_view = ModuleType("ppcal.era_view")
ppcal.eras = ModuleType("ppcal.eras")
calib = ModuleType("ppcal.calib")
calib.calibrate = None
products = ModuleType("ppcal.products")
products.Channel = None
products.load_all = None
products.product_paths = lambda directory: sorted(Path(directory).glob("*.npz"))
saved_modules = {name: sys.modules.get(name) for name in
                 ("ppcal", "ppcal.calib", "ppcal.products")}
saved_path = sys.path[:]
try:
    sys.modules["ppcal"] = ppcal
    sys.modules["ppcal.calib"] = calib
    sys.modules["ppcal.products"] = products
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "calibrated_thresholds", ROOT / "scripts" /
        "calibrated_thresholds.py")
    calibrated = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(calibrated)
finally:
    sys.path[:] = saved_path
    for name, previous in saved_modules.items():
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous


def test_load_channels_filters_before_full_load(tmp_path, monkeypatch):
    for fid, ch in ((568, 32), (521, 35)):
        np.savez(tmp_path / f"{fid}.npz", physical_channel=np.array([ch]))

    loaded = []

    def channel(path):
        loaded.append(Path(path).name)
        with np.load(path) as data:
            return SimpleNamespace(ch=int(data["physical_channel"][0]))

    monkeypatch.setattr(calibrated, "Channel", channel)
    channels = calibrated.load_channels(tmp_path, {32})

    assert [c.ch for c in channels] == [32]
    assert loaded == ["568.npz"]


def test_load_channels_refuses_missing_request(tmp_path):
    np.savez(tmp_path / "568.npz", physical_channel=np.array([32]))

    with pytest.raises(SystemExit, match="35"):
        calibrated.load_channels(tmp_path, {35})


@pytest.mark.parametrize(
    ("quality", "expected"),
    [
        ("measured", "measured tau"),
        ("bounded_above", "upper bound on tau"),
        ("refused", "upper bound (tau at sidereal cap)"),
        ("unavailable", "unavailable"),
    ],
)
def test_residual_basis_preserves_quality(quality, expected):
    assert calibrated.residual_basis(quality) == expected


def _era_record(channel=35):
    return {
        "ch": channel,
        "era": "2021-11..2026-07",
        "eta1_status_adopted": "evaluated",
        "mask_eta1_adopted": 0.4805376645,
        "r_eta1_adopted": 4.198385861331264,
        "r_tol_dilation": 0.0352,
        "mask_cost_adopted": 0.013511621394567297,
        "r_cost_adopted": 4.734007337892885,
        "tau_seconds": 2767.651212286865,
        "tau_quality": "measured",
        "floor_basis": "quiet_era_p90",
        "floor_era": "2018-12..2021-10",
        "floor_frames": 3359,
        "floor_db": -24.98,
        "product_file": "521.npz",
        "product_sha256": "b" * 64,
        "product_schema": "pilotproxy_detector_datatrawl_v3",
        "detector_version": "pilot-proxy/0.3.0",
        "generator_sha256": "c" * 64,
        "analysis_source_sha256": "a" * 64,
    }


def test_write_era_points_derives_the_figure_values(tmp_path):
    record = _era_record()
    path = tmp_path / "points.csv"

    calibrated.write_era_points(path, [record])

    with path.open(newline="", encoding="utf-8") as handle:
        row = next(csv.DictReader(handle))
    assert row == {
        "channel": "35",
        "era": "2021-11..2026-07",
        "eta_basis": "eta_mu_1",
        "masked_fraction": "0.4805376645",
        "r_over_rtol": "119.2723256",
        "best_cost_masked_fraction": "0.01351162139",
        "best_cost_r_over_rtol": "134.4888448",
        "tau_seconds": "2767.651212",
        "tau_quality": "measured",
        "floor_basis": "quiet_era_p90",
        "floor_era": "2018-12..2021-10",
        "floor_frames": "3359",
        "floor_db": "-24.98",
        "r_tol_dilation": "0.0352",
        "r_eta1_adopted": "4.198385861",
        "r_cost_adopted": "4.734007338",
        "product_file": "521.npz",
        "product_sha256": "b" * 64,
        "product_schema": "pilotproxy_detector_datatrawl_v3",
        "detector_version": "pilot-proxy/0.3.0",
        "generator_sha256": "c" * 64,
        "analysis_source_sha256": "a" * 64,
    }


def test_eta1_export_refuses_a_dropped_unity_row():
    rows = [{"eta_mu": 1.01}, {"eta_mu": 1.1}]
    with pytest.raises(ValueError, match="eta_mu=1 row is unavailable"):
        calibrated.eta1_row(rows)
    with pytest.raises(ValueError, match="no calibrated eta_mu=1 row"):
        calibrated.era_point_record({
            "ch": 32, "eta1_status_adopted": "unavailable"})


def test_failed_export_keeps_the_existing_file(tmp_path):
    path = tmp_path / "points.csv"
    path.write_text("original\n", encoding="utf-8")
    invalid = _era_record(channel=32)
    invalid["eta1_status_adopted"] = "unavailable"

    with pytest.raises(ValueError, match="no calibrated eta_mu=1 row"):
        calibrated.write_era_points(path, [_era_record(), invalid])

    assert path.read_text(encoding="utf-8") == "original\n"


def test_failed_csv_write_keeps_the_existing_file(tmp_path):
    path = tmp_path / "table.csv"
    path.write_text("original\n", encoding="utf-8")

    with pytest.raises(ValueError, match="dict contains fields"):
        calibrated.write_csv_atomic(
            path, ("value",), ({"value": 1}, {"extra": 2}))

    assert path.read_text(encoding="utf-8") == "original\n"


def test_cap_aliases_preserve_the_table_contract():
    record = {f"{stem}_adopted": index
              for index, stem in enumerate(calibrated.CAP_ALIAS_STEMS)}

    calibrated.add_cap_aliases(record)

    assert all(record[f"{stem}_cap"] == record[f"{stem}_adopted"]
               for stem in calibrated.CAP_ALIAS_STEMS)
