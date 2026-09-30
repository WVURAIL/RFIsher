"""Seeded scientific oracles, computed without the production reduction path."""
from types import SimpleNamespace

import numpy as np
import pytest

from rfisher.forecast.radiofisher_bao import scenarios
from rfisher.forecast.radiofisher_bao.significance import Forecast


@pytest.mark.parametrize("seed", range(12))
@pytest.mark.parametrize("mode", ["time", "fourier"])
def test_scenario_band_reduction_matches_frequency_cell_integral(seed, mode):
    rng = np.random.default_rng(seed)
    bands = [scenarios.FrequencyBand(f"slice{i}", 500 + 10 * i, 510 + 10 * i) for i in range(4)]
    fractions = rng.uniform(0, 0.8, 4)
    fractions[0] = 1.0                     # volume excision
    residuals = rng.uniform(0, 2, 4)
    scenario = scenarios.Scenario("bench", "bench", mode=mode, excise_threshold=1.0,
                                  frequency_fractions=dict(zip(bands, fractions)),
                                  frequency_residuals=dict(zip(bands, residuals)))
    frequencies = np.arange(490.5, 550, 1.0)
    weights = np.ones(frequencies.size)
    for i in range(4):
        inside = (frequencies >= 500 + 10 * i) & (frequencies < 510 + 10 * i)
        weights[inside] = np.nan if i == 0 else (1 - fractions[i]) / (1 + residuals[i])
    live = weights[np.isfinite(weights)]
    volume, effective_time = scenario.bin_factors(490, 550)
    assert volume == pytest.approx(len(live) / len(weights))
    expected = np.mean(live) if mode == "time" else len(live) / sum(1 / live)
    assert effective_time == pytest.approx(expected)
    np.testing.assert_allclose(scenario.freq_weight_fn()(frequencies), weights, equal_nan=True)


@pytest.mark.parametrize("seed", range(12))
def test_correlated_multibin_forecast_matches_dense_inverse_and_time_scaling(seed):
    rng = np.random.default_rng(seed)
    raw = rng.normal(size=(3, 3, 3))
    matrices = raw @ np.swapaxes(raw, -1, -2) + np.eye(3)
    bank = SimpleNamespace(paramnames=["A", "aperp", "apar"], zs=np.arange(4), nbins=3, artifact_kind="forecast",
                           t_grid=np.array([0.01, 1, 10, 100]),
                           F=lambda index, hours: matrices[index] * hours**2)
    fc = Forecast(bank, style="perbin_A")
    volumes, weights = rng.uniform(0.2, 1, (2, 3))
    scenario = SimpleNamespace(bin_factors_for_zbins=lambda zs: np.column_stack([volumes, weights]))
    information = sum(volumes[i] * weights[i]**2 / np.linalg.inv(matrices[i])[0, 0]
                      for i in range(3))
    for hours in [0.0, 0.5, 1.0, 7.0]:
        assert fc.significance(scenario, hours) == pytest.approx(hours * np.sqrt(information), rel=1e-11)
    assert fc.significance(scenario, 2, bins=[1]) == pytest.approx(
        2 * weights[1] * np.sqrt(volumes[1] / np.linalg.inv(matrices[1])[0, 0]))
    assert fc.significance(scenario, 2, bins=[]) == 0
    expected_bins = [2 * weights[i] * np.sqrt(volumes[i] / np.linalg.inv(matrices[i])[0, 0])
                     for i in range(3)]
    np.testing.assert_allclose(fc.per_bin_significance(scenario, 2), expected_bins)
    coefficients = np.array([0, 2 / 3, 1 / 3])
    for ibin in range(3):
        covariance = np.linalg.inv(matrices[ibin]) / (volumes[ibin] * (2 * weights[ibin])**2)
        assert fc.sigma_dv_bin(scenario, 2, ibin) == pytest.approx(np.sqrt(coefficients @ covariance @ coefficients))
    assert fc.required_hours(scenario, target=5, t_lo=0.01, t_hi=100) == pytest.approx(
        5 / np.sqrt(information), rel=1e-9)
