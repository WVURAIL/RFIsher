"""The delay-filter options of the forecast: the delay-cut hooks."""
from __future__ import annotations

import numpy as np
import pytest

from rfisher.forecast.radiofisher_bao import filter_scenarios
from rfisher.forecast.radiofisher_bao.bank.physics import HI_REST_FREQUENCY_MHZ

# The redshift at which the CHIME 2025 detection quotes its k_par floor.
Z_REFERENCE = 1.16


def _radiofisher_backend():
    from rfisher.forecast.radiofisher_bao.bank.backend import (
        find_radiofisher_dir, import_radiofisher)
    try:
        find_radiofisher_dir()
    except FileNotFoundError:
        pytest.skip("delay-cut binding requires a RadioFisher checkout")
    return import_radiofisher()


def test_delay_cut_reproduces_the_published_kpar_floor():
    """200 ns filter + 280 ns mask = 0.35 h/Mpc at z = 1.16, which is where
    the published auto-spectrum measurement begins."""
    from rfisher.forecast.radiofisher_bao.bank import cosmologies

    rf, rf_dir = _radiofisher_backend()
    cosmo = cosmologies.get("planck2018", rf, rf_dir)
    cosmo_fns = rf.background_evolution_splines(cosmo)
    experiment = {"nu_line": HI_REST_FREQUENCY_MHZ}

    kpar_min_fn = filter_scenarios.delay_cut(rf, experiment, cosmo_fns, 200e-9)

    kpar_min = kpar_min_fn(Z_REFERENCE)
    assert kpar_min / cosmo["h"] == pytest.approx(0.351, abs=5e-4)
    # A zero cut is a valid no-op so the no-cut reference runs the same path.
    assert filter_scenarios.delay_cut(rf, experiment, cosmo_fns, 0.0)(1.16) == 0.0
    # Linear in the delay, and the transition factor is separable.
    assert filter_scenarios.delay_cut(rf, experiment, cosmo_fns, 100e-9)(1.16) \
        == pytest.approx(0.5 * kpar_min)
    assert filter_scenarios.delay_cut(
        rf, experiment, cosmo_fns, 280e-9, transition=1.0)(1.16) \
        == pytest.approx(kpar_min)


def test_delay_cut_rejects_a_negative_delay():
    rf, rf_dir = _radiofisher_backend()
    from rfisher.forecast.radiofisher_bao.bank import cosmologies
    cosmo_fns = rf.background_evolution_splines(
        cosmologies.get("planck2018", rf, rf_dir))

    with pytest.raises(ValueError, match="tau_cut_seconds"):
        filter_scenarios.delay_cut(rf, {"nu_line": HI_REST_FREQUENCY_MHZ},
                                   cosmo_fns, -1e-9)


def test_filter_residual_table_is_the_digitised_fig10():
    ratio, response = filter_scenarios.filter_residual_table()

    assert ratio[0] == 0.0 and ratio[-1] > 6.0          # 0 to > 1200 ns
    assert np.all(np.diff(ratio) > 0.0)
    assert np.all(response >= 0.0) and response.max() < 1.0
    # zero below the 200 ns cut, a plateau of ~0.87 at high delay, and
    # about 0.75 at the 280 ns mask edge (ratio 1.4)
    assert np.interp(0.9, ratio, response) == pytest.approx(0.0, abs=1e-3)
    assert np.interp(1.4, ratio, response) == pytest.approx(0.756, abs=0.02)
    assert np.median(response[ratio > 4.0]) == pytest.approx(0.870, abs=0.01)


def test_filter_residual_table_rejects_malformed_files(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("a,b\n1.0,0.5\n0.5,0.6\n")
    with pytest.raises(ValueError, match="increase"):
        filter_scenarios.filter_residual_table(bad)
    bad.write_text("a,b\n0.0,-0.5\n1.0,0.6\n")
    with pytest.raises(ValueError, match="non-negative"):
        filter_scenarios.filter_residual_table(bad)


def test_delay_transfer_binds_the_fig10_response_to_the_backend():
    from rfisher.forecast.radiofisher_bao.bank import cosmologies

    rf, rf_dir = _radiofisher_backend()
    cosmo = cosmologies.get("planck2018", rf, rf_dir)
    cosmo_fns = rf.background_evolution_splines(cosmo)
    experiment = {"nu_line": HI_REST_FREQUENCY_MHZ}
    hard = filter_scenarios.delay_cut(rf, experiment, cosmo_fns, 200e-9)
    soft = filter_scenarios.delay_transfer(rf, experiment, cosmo_fns, 200e-9)

    kpar_mask_edge = hard(1.16)                 # 0.351 h/Mpc: tau = 280 ns
    kpar = np.array([0.5, 1.0, 1.4, 3.0, 8.0]) / 1.4 * kpar_mask_edge
    transfer = soft(kpar, 1.16)

    assert transfer[0] == pytest.approx(0.0, abs=1e-6)   # 100 ns: filtered
    assert transfer[1] == pytest.approx(0.0, abs=1e-3)   # 200 ns: the cut
    assert transfer[2] == pytest.approx((0.756 / 0.870) ** 2, abs=0.05)
    assert transfer[3] > 0.9                     # 600 ns: near plateau
    assert transfer[4] == pytest.approx(1.0, abs=0.02)
