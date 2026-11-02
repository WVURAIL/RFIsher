import numpy as np
import pytest
from radiofisher.quadrature import quadrature_segments

from rfisher import forecast, residual
from rfisher.bands import channel


def test_unit_power_is_additive_and_noise_independent():
    k, mu = np.array([.01, .1, .5]), np.array([0, .5, 1])
    np.testing.assert_array_equal(residual.unit_power(k, mu, [1, 10, 100], [2, 3, 4]), np.ones(3))

def test_unit_power_does_not_depend_on_grid_density():
    integrals = []
    for order in (2, 4, 8):
        total = sum(np.dot(w, residual.unit_power(k, mu, 0, 0))
                    for k, mu, w in quadrature_segments([0, .25, 1], lambda k: [0, 1], order, order))
        integrals.append(total)
    np.testing.assert_allclose(integrals, 2 / 3, rtol=1e-14)

def test_prepared_residual_uses_the_unit_power(shared):
    p = forecast.prepare(channel(19), *shared)
    assert p["expt"]["P_res"] is residual.unit_power
    assert p["expt"]["dnutot"] == pytest.approx(6)


def test_temperature_normalization_matches_independent_integration(monkeypatch):
    from radiofisher import baofisher as rf
    from radiofisher import instrument
    from scipy.integrate import quad
    from scipy.interpolate import interp1d

    monkeypatch.setattr(rf, "Tsys_tot", lambda z, e: 55000.)
    monkeypatch.setattr(instrument, "mode_limits", lambda c, e: (.2, 1.))
    c = {"r": 2*np.pi, "rnu": 3., "z": 0.}
    e = {"nu_line": 1., "n(x)": interp1d([0, .3, .5, .7, 1], [1, 0, 0, 1, 1],
                                         bounds_error=False, fill_value=1e-200)}
    # Separate numerical integrals over the two supported transverse intervals.
    integral = sum(quad(lambda q: q*(np.sqrt(1-q*q)-.2), lo, hi)[0]
                   for lo, hi in [(0., .3), (.5, np.sqrt(.96))])
    expected = c["r"]**2*c["rnu"]*integral/(2*np.pi**2)
    result = residual.normalization(c, e)
    assert result["mode_volume"] == pytest.approx(expected, rel=1e-11)
    assert result["power_scale"]*expected == pytest.approx(55000.**2)
    # Interpolating the same density more finely must not change its support.
    old=e["n(x)"]; knots=np.sort(np.r_[old.x, .1, .4, .6, .8])
    e["n(x)"]=interp1d(knots,old(knots),bounds_error=False,fill_value=1e-200)
    assert residual.normalization(c,e)["mode_volume"] == pytest.approx(expected, rel=1e-11)


def test_temperature_normalization_excludes_missing_baselines(monkeypatch):
    from radiofisher import baofisher as rf
    from radiofisher import instrument
    from scipy.interpolate import interp1d

    monkeypatch.setattr(rf, "Tsys_tot", lambda z, e: 55000.)
    monkeypatch.setattr(instrument, "mode_limits", lambda c, e: (0., 1.))
    c = {"r": 2*np.pi, "rnu": 3., "z": 0.}
    e = {"nu_line": 1., "n(x)": interp1d([.2, .5], [0., 0.],
                                         bounds_error=False, fill_value=1e-200)}
    with pytest.raises(ValueError, match="mode volume"):
        residual.normalization(c, e)
