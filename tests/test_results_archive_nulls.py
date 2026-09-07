"""Null calibration: widths against the F-distribution, probes, exchangeability, floor."""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import numpy as np
import pytest
from scipy import stats

from rfisher_results.archive import nulls
from rfisher_results.archive.products import Product

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("v5_fixture_nulls", ROOT / "tests" / "test_pilotproxy_v5.py")
v5_fixture = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v5_fixture)


def test_iid_widths_match_the_text():
    mean, sigma = nulls.iid_width(nulls.FINE_DOF)
    assert mean == pytest.approx(1.00024, abs=2e-5) and 100 * sigma == pytest.approx(2.71, abs=0.01)
    mean, sigma = nulls.iid_width(nulls.COARSE_DOF)
    assert mean == pytest.approx(1.000002, abs=1e-6) and 100 * sigma == pytest.approx(0.239, abs=0.001)


def test_corrected_probes_recover_an_ideal_null_and_the_as_coded_ones_do_not():
    rng = np.random.default_rng(3)
    x = stats.f.rvs(*nulls.COARSE_DOF, size=100_000, random_state=rng)
    d = nulls.describe_null(x, nulls.COARSE_DOF)
    assert d.raw_width_factor == pytest.approx(1.0, abs=0.02)
    assert d.core_width_factor == pytest.approx(1.0, abs=0.03) and d.core_spread == pytest.approx(1.0, abs=0.05)
    assert d.as_coded_sigma / d.iid_sigma == pytest.approx(0.84, abs=0.03) and d.as_coded_spread > 1.8
    assert d.tail_fraction == pytest.approx(d.tail_fraction_iid, abs=0.001)
    assert d.centre_db == pytest.approx(0.0, abs=0.01)


def test_a_contaminated_tail_inflates_raw_but_not_core():
    rng = np.random.default_rng(4)
    x = stats.f.rvs(*nulls.FINE_DOF, size=50_000, random_state=rng)
    x[:250] *= 20.0                         # a 0.5% contaminated tail
    d = nulls.describe_null(x, nulls.FINE_DOF)
    assert d.raw_width_factor > 5.0 and d.core_width_factor == pytest.approx(1.0, abs=0.05)
    assert 0.006 < d.tail_fraction < 0.009      # 0.5% contamination plus the model tail (0.19%)


def test_exchangeability_of_null_designated_bins_matches_the_combinatorial_rate():
    rng = np.random.default_rng(5)
    frames, bins = 4000, 256
    t = stats.f.rvs(*nulls.FINE_DOF, size=(frames, bins), random_state=rng)
    bulk = np.zeros(bins, dtype=bool)
    bulk[::2] = True
    designated = [126, 127, 128, 129, 130]
    for b in range(124, 133):
        bulk[b] = False                       # designated window with guards leaves the bulk
    bulk_size = int(bulk.sum())
    for rho in (1, 64, 120):
        e = nulls.exchangeability_rate(t, bulk, rho, designated)
        assert e.bulk_size == bulk_size and e.trials == frames * 5 and e.test_bins == tuple(designated)
        assert e.predicted_rate == pytest.approx((bulk_size + 1 - rho) / (bulk_size + 1))
        assert e.measured_rate == pytest.approx(e.predicted_rate, abs=0.012), rho
        assert e.max_over_test_rate >= e.measured_rate
    # a designated window carrying a line on 'quiet' frames breaks exchangeability
    t[:, 128] *= 3.0
    hot = nulls.exchangeability_rate(t, bulk, 120, designated)
    assert hot.measured_rate > hot.predicted_rate + 0.1
    with pytest.raises(ValueError, match="outside the bulk"):
        nulls.exchangeability_rate(t, bulk, 64, [0])


@pytest.fixture
def product(tmp_path):
    path = v5_fixture._write_product(tmp_path / "521.npz", 35)
    with np.load(path, allow_pickle=False) as z:
        frames = int(np.asarray(z["valid"]).shape[0])
    v5_fixture._replace(path, baseband_power_linear=np.full((frames, 1), 4.0))
    with Product(path) as p:
        yield p


def test_calibrate_null_on_the_fixture_declares_its_source_and_floor(product):
    bulk = np.zeros(256, dtype=bool)
    bulk[::2] = True
    for k in range(-4, 5):
        bulk[(128 + k) % 256] = False
    era = product.selected
    cal = nulls.calibrate_null(product, era, anchor_bin=128, bulk_mask=bulk, era_label="fixture", rho=3)
    assert cal.mixture_declared and "mixture" in cal.null_source
    assert cal.era_frames == int(era.sum()) and cal.bulk_size == int(bulk.sum())
    assert cal.coarse.frames == cal.era_frames
    assert cal.floor.evidence in ("stated", "refused")
    row = cal.as_row()
    assert "coarse_core_width_factor" in row and "fine_raw_width_factor" in row and row["null_source"] == cal.null_source
    # an off era with enough frames carrying a shelf estimate gives a measured floor
    off = np.zeros(product.n_frames, dtype=bool)
    off[: product.n_frames // 2] = True
    cal_off = nulls.calibrate_null(product, era, anchor_bin=128, bulk_mask=bulk, era_label="fixture", off_era=off)
    finite = np.isfinite(product.shelf_db[off]).sum()
    if finite >= nulls.FLOOR_MIN_FRAMES:
        assert cal_off.floor.evidence == "measured" and cal_off.null_source.startswith("verified")
    else:
        assert cal_off.floor.evidence == "stated"
    nulls.write_null_rows([cal, cal_off], product.path.parent / "nulls.csv")
    header = (product.path.parent / "nulls.csv").read_text().splitlines()[0]
    assert header.startswith("channel,freq_id,era,era_frames,null_source")
    assert math.isfinite(cal.fine.iid_sigma)
