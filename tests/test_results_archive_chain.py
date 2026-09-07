"""The residual chain wrapper on a synthetic v5 product."""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import numpy as np

from rfisher import residual
from rfisher_results.archive import chain

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("v5_fixture_chain", ROOT / "tests" / "test_pilotproxy_v5.py")
v5_fixture = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v5_fixture)


def test_chain_assembles_rfisher_results_and_books_the_gain(tmp_path):
    path = v5_fixture._write_product(tmp_path / "552.npz", 33)
    result = chain.residual_chain(path)
    assert result.channel == 33 and result.population.startswith("transmitter-on frames of the whole archive")
    assert result.n_valid > 0 and result.tau_quality in ("measured", "bounded_above", "refused")
    assert result.components and all(share >= 0 and n_coh >= 1 for share, n_coh in result.components)
    assert result.gain == sum(s * n for s, n in result.components)
    assert result.delay_key == residual.DEFAULT_DELAY_KEY and result.delay_suppression_db == 0.0
    if result.tau_quality == "refused":
        # a refusal books everything at the sidereal-day cap with no ground-filter credit
        assert result.components == ((1.0, residual.n_coh_from_correlation_time(residual.MAX_TAU_C_SECONDS)),)
    row = result.as_row()
    assert row["chain_gain"] == result.gain and row["tau_outcome"] in ("measured", "bound", "refused (cap)")
    assert math.isfinite(row["n_coh_intraday"]) and row["n_coh_intraday"] >= 1.0
    # an off epoch changes the recorded population
    off = chain.residual_chain(path, off_through="2020-01")
    assert "through 2020-01" in off.population
    assert chain.FRAME_SECONDS == residual.CHIME_FRAME_SECONDS
    assert np.isfinite(off.n_valid)


def test_masked_valid_and_invalidation_follow_the_product_contract():
    import numpy as np
    from rfisher_results.archive import chain
    column = np.ones((6, 1), dtype=np.uint8)
    out = chain.masked_valid(column, np.array([1, 0, 1, 1, 0, 1], dtype=bool))
    assert out.shape == (6, 1) and out.dtype == np.uint8 and out.reshape(-1).tolist() == [1, 0, 1, 1, 0, 1]
    arrays = {"valid": column, "p_ref_sum_u64": np.full((6, 1), 7, dtype=np.uint64), "p_ref_lower_u64": np.full((6, 1), 3, dtype=np.uint64),
              "p_ref_upper_u64": np.full((6, 1), 4, dtype=np.uint64), "reject_mask": np.ones((6, 1), dtype=np.uint8),
              "coarse_power_ratio": np.ones((6, 1)), "estimated_data_shelf_snr_db": np.zeros((6, 1)), "other": np.arange(6)}
    inv = chain.invalidate_frames(arrays, np.array([1, 0, 1, 1, 0, 1], dtype=bool))
    assert inv["valid"].reshape(-1).tolist() == [1, 0, 1, 1, 0, 1]
    assert inv["p_ref_sum_u64"].reshape(-1).tolist() == [7, 0, 7, 7, 0, 7] and inv["p_ref_lower_u64"].reshape(-1)[1] == 0
    assert inv["reject_mask"].reshape(-1).tolist() == [1, 0, 1, 1, 0, 1]
    assert np.isnan(inv["coarse_power_ratio"].reshape(-1)[[1, 4]]).all() and inv["coarse_power_ratio"].reshape(-1)[0] == 1.0
    assert inv["other"].tolist() == list(range(6)) and arrays["p_ref_sum_u64"].reshape(-1).tolist() == [7] * 6   # inputs untouched
