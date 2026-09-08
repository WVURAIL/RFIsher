"""Distance metrics, singular information and direct-backend refusal paths."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from rfisher import forecast, scenarios
from test_forecast import _Bank, _forecast, SCENARIO


@pytest.mark.parametrize("matrix,coefficients", [([1], [1]), ([[1, 0]], [1]), ([[1]], [1, 0])])
def test_linear_variance_refuses_incompatible_shapes(matrix, coefficients):
    with pytest.raises(ValueError, match="shapes disagree"):
        forecast._variance_from_fisher(matrix, coefficients)


@pytest.mark.parametrize("matrix,coefficients", [
    (np.empty((0, 0)), []), ([[np.nan]], [1]), ([[1]], [np.inf]), ([[-1]], [1]), ([[0]], [1]),
])
def test_invalid_information_cannot_yield_a_finite_variance(matrix, coefficients):
    assert np.isinf(forecast._variance_from_fisher(matrix, coefficients))


def test_distance_and_parameter_metrics_refuse_absent_information():
    fc = _forecast(np.eye(2), names=("A", "aperp"))
    assert np.isinf(fc.sigma_dv_bin(SCENARIO, 1, 0))
    assert np.isinf(fc.sigma_dv_bin(SCENARIO, 1, 5))
    assert np.isinf(fc.sigma_param_bin(SCENARIO, 1, 5))
    assert np.isinf(fc.sigma_param_bin(SCENARIO, 1, 0, "unknown"))
    assert fc.sigma_param_bin(SCENARIO, 1, 0, "aperp0") == pytest.approx(1)
    shared = _forecast(np.diag([4, 9]), names=("A", "aperp0"), style="shared_A")
    assert shared.sigma_param_bin(SCENARIO, 1, 0, "aperp0") == pytest.approx(1 / 3)
    assert shared.required_years(SCENARIO, target=5, duty=0.5, hours_per_year=10) == pytest.approx(2)


@pytest.fixture
def direct(monkeypatch):
    bank = _Bank(np.eye(2), ["A", "sigma_NL"])
    bank.meta = {"config": "bull2015", "cosmology": "planck2013", "astrophysical_model_profile": "bull2015"}
    backend = SimpleNamespace(
        experiments=SimpleNamespace(cosmo={"h": 0.7}),
        with_astrophysical_profile=Mock(side_effect=lambda cosmo, profile: {**cosmo, "profile": profile}),
        background_evolution_splines=Mock(return_value=("background",)),
        fisher=Mock(return_value=(np.diag([9, 4]), ["A", "sigma_NL"])))
    monkeypatch.setattr("rfisher.backend.bind_radiofisher", lambda *args: Path("/synthetic-backend"))
    monkeypatch.setattr("rfisher.backend.require_backend_capabilities", lambda *args, **kwargs: frozenset())
    monkeypatch.setattr("rfisher.pkcache.load_fiducial_cosmology", lambda rf, path, cosmo: cosmo)
    monkeypatch.setattr("rfisher.survey.experiment_from_bank_metadata", lambda *args, **kwargs: {})
    return forecast.Forecast(bank, backend, style="perbin_A"), backend


def test_direct_bull_path_applies_profile_and_passes_experiment_hooks(direct):
    fc, backend = direct
    assert fc.sigma_A_direct(scenarios.clean(), 10) == pytest.approx(1 / 3)
    backend.with_astrophysical_profile.assert_called_once_with({"h": 0.7}, "bull2015")
    args = backend.fisher.call_args.args
    assert args[2] == {"h": 0.7, "profile": "bull2015"}
    assert args[3]["noise_freq_mode"] == "invvar" and args[3]["vol_frac"] == 1
    np.testing.assert_array_equal(args[3]["noise_freq_weight"]([500, 600]), [1, 1])
    assert args[4] == ("background",)


@pytest.mark.parametrize("updates,kwargs,message", [
    ({}, {"cosmo_fns": ("unbound",)}, "cannot be supplied without cosmo"),
    ({"config": "unknown"}, {}, "unsupported direct-validation"),
    ({"astrophysical_model_profile": "unknown"}, {}, "canonical HI"),
    ({"astrophysical_model_profile": "unknown"}, {"cosmo": {}}, "recorded canonical"),
])
def test_direct_forecast_refuses_unbound_or_unsupported_context(direct, updates, kwargs, message):
    fc, backend = direct
    fc.bank.meta.update(updates)
    with pytest.raises(ValueError, match=message):
        fc.sigma_A_direct(scenarios.clean(), 10, **kwargs)
    backend.fisher.assert_not_called()


def test_direct_parameter_drift_is_refused(direct):
    fc, backend = direct
    backend.fisher.return_value = (np.eye(2), ["A", "different"])
    with pytest.raises(RuntimeError, match="parameter schema does not match"):
        fc.sigma_A_direct(scenarios.clean(), 10)
