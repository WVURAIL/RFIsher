"""Disk-to-interpolator verification against an exact thermal-limit model."""
import warnings

import numpy as np
import pytest

from rfisher.fisherbank import FisherBank
from test_fisherbank_schema import _write_bank


@pytest.mark.parametrize("seed", range(8))
def test_every_matrix_element_obeys_analytic_time_scaling_across_bins(tmp_path, seed):
    rng = np.random.default_rng(seed)
    factors = rng.normal(size=(3, 3, 3))
    matrices = factors @ np.swapaxes(factors, -1, -2) + np.eye(3)
    times = np.array([1.0, 2.0, 4.0, 8.0])

    def fill(arrays, meta):
        arrays.update(F=matrices[:, None] * times[None, :, None, None]**2,
                      zs=np.array([0.8, 0.9, 1.0, 1.1]), zc=np.array([0.85, 0.95, 1.05]))

    path = _write_bank(tmp_path / "analytic.npz", names=("A", "aperp", "apar"), mutate=fill)
    bank = FisherBank(path)
    path.unlink()  # no lazy archive handle may leak into interpolation
    assert bank.nbins == bank.npar == 3
    for ibin in range(3):
        np.testing.assert_array_equal(bank.F(ibin, 0), np.zeros((3, 3)))
        for hours in [0.125, 1.0, 1.5, 2.0, 3.0, 4.0, 7.9, 8.0]:
            np.testing.assert_allclose(bank.F(ibin, hours), matrices[ibin] * hours**2, rtol=1e-12, atol=1e-12)
        result = bank.F(ibin, 1.5)
        result[0, 0] = -1
        assert bank.F(ibin, 1.5)[0, 0] > 0
    with pytest.warns(RuntimeWarning, match="above the bank grid"):
        np.testing.assert_allclose(bank.F(0, 9), matrices[0] * 64)
    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        np.testing.assert_allclose(bank.F(1, 100), matrices[1] * 64)
    assert not seen
