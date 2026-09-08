"""Seeded scientific oracles, computed without the production reduction path."""
from types import SimpleNamespace

import numpy as np
import pytest

from rfisher import scenarios, thresholds
from rfisher.forecast import Forecast


@pytest.mark.parametrize("seed", range(16))
@pytest.mark.parametrize("with_variance", [False, True])
def test_histogram_selector_matches_direct_frame_replay(seed, with_variance):
    rng = np.random.default_rng(seed)
    # Adjacent >2**53 boundaries deliberately have indistinguishable float displays.
    candidates = (1, 65536, 65537, 2**63 - 1, 2**63)
    frame_count, bulk_size = 120, 4
    systematic = rng.integers(0, 17, frame_count) / 16
    variance = rng.integers(0, 65, frame_count) / 16 if with_variance else None
    tolerance = 0.48
    family, reference = {}, {}
    for rho in range(1, bulk_size + 1):
        requirements = [candidates[i] if i < len(candidates) else thresholds.ALWAYS_MASKED_Q16
                        for i in rng.integers(0, len(candidates) + 1, frame_count)]
        family[rho] = thresholds.build_q16_residual_score_histogram(
            requirements, systematic, candidates, bulk_size=bulk_size, variance_residuals=variance)
        for q16 in candidates:
            kept = [i for i, required in enumerate(requirements) if required <= q16]
            if len(kept) < 30:
                continue
            r_sys = sum(float(systematic[i]) for i in kept) / len(kept)
            r_var = None if variance is None else sum(float(variance[i]) for i in kept) / len(kept)
            reference[rho, q16] = (len(kept), r_sys, r_var,
                                   frame_count * (1 + (r_var or 0)) / len(kept))
    result = thresholds.optimize_threshold(family, tolerance)
    assert {(p.rho, p.multiplier_q16) for p in result.points} == set(reference)
    for point in result.points:
        kept, r_sys, r_var, cost = reference[point.rho, point.multiplier_q16]
        assert point.kept_frames == kept and point.masked_frames == frame_count - kept
        assert point.systematic_residual == r_sys
        assert point.variance_residual == r_var
        assert point.cost == pytest.approx(cost)
        assert point.feasible == (r_sys <= tolerance)
    feasible = {key: row for key, row in reference.items() if row[1] <= tolerance}
    if feasible:
        limit = 1.02 * min(row[3] for row in feasible.values())
        expected = min((key for key, row in feasible.items() if row[3] <= limit),
                       key=lambda key: (feasible[key][1], -feasible[key][0], *key))
        assert (result.selected.rho, result.selected.multiplier_q16) == expected
    else:
        assert result.selected is None and result.status == "no_feasible_threshold"
    assert result == thresholds.optimize_threshold(dict(reversed(list(family.items()))), tolerance)


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
