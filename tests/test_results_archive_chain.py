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
