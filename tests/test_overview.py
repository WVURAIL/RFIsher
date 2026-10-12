"""The CHIME Overview forecast, reproduced."""
import numpy as np
import pytest

from rfisher import overview
from rfisher.tolerance import DV_WEIGHTS

NAMES = ["A", "b_HI", "Tb", "sigma_NL", "sigma8tot", "n_s", "f", "aperp", "apar", "fs8", "bs8", "pk"]

# Per-bin sigma(D_V)/D_V (percent), one clean year, Planck 2018, from the forecast goldens of
# RFIsher 05ee7e4 (planck2018, S1_clean), the forecast that reproduced the Overview's Fig. 31.
OVERVIEW_PERCENT = [0.4663, 0.4811, 0.4974, 0.5123, 0.5442, 0.5826, 0.6146, 0.6587, 0.7058, 0.7608,
                    0.8508, 0.7748, 0.7847, 0.9444, 1.0291]


def diagonal(sig_perp, sig_par, coupling=0.0):
    F = np.eye(len(NAMES))
    F[NAMES.index("aperp"), NAMES.index("aperp")] = 1 / sig_perp ** 2
    F[NAMES.index("apar"), NAMES.index("apar")] = 1 / sig_par ** 2
    i, j = NAMES.index("aperp"), NAMES.index("sigma_NL")
    F[i, j] = F[j, i] = coupling
    return F


def test_independent_bins_give_each_bin_its_own_d_v():
    out = overview.combine([diagonal(0.02, 0.03), diagonal(0.01, 0.01)], NAMES)
    for (sp, sa), got in zip(((0.02, 0.03), (0.01, 0.01)), out["sigma_dv"]):
        assert got == pytest.approx(np.sqrt((DV_WEIGHTS ** 2 * np.array([sp, sa]) ** 2).sum()))


def test_the_shared_parameter_couples_the_bins():
    free = overview.combine([diagonal(0.02, 0.03), diagonal(0.02, 0.03)], NAMES)["sigma_dv"][0]
    coupled = overview.combine([diagonal(0.02, 0.03, 30.0), diagonal(0.02, 0.03, 30.0)], NAMES)["sigma_dv"][0]
    assert coupled > free


def test_the_overview_bins():
    assert len(overview.overview_bins()) == 15 and overview.overview_bins()[0] == (0.8, 0.9)
    assert len(overview.channel_bins()) == 24


def test_reproduces_the_overview_forecast():
    got = 100 * np.array(overview.forecast(overview.overview_bins())["sigma_dv"])
    np.testing.assert_allclose(got, OVERVIEW_PERCENT, rtol=2e-3)
