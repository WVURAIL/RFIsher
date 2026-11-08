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


def fisher(shared, **options):
    """F and names of channel 19 from the shared inputs."""
    cosmo, expt, fns = shared
    return forecast.channel_fisher(channel(19), cosmo=cosmo, expt=expt, fns=fns, **options)[:2]


def doubled(k, mu, cn, cs):
    return 2 * residual.unit_power(k, mu, cn, cs)


def line_of_sight(k, mu, cn, cs):
    """Power only along the line of sight, a smooth stand-in for a spectral residual."""
    return np.broadcast_to(np.asarray(mu) ** 2, np.broadcast_shapes(np.shape(k), np.shape(mu))).copy()


def test_the_response_is_linear_in_the_template(shared):
    from rfisher.tolerance import tolerance
    unit = tolerance(*fisher(shared))
    twice = tolerance(*fisher(shared, template=doubled))
    assert twice["response_dv"] == pytest.approx(2 * unit["response_dv"], rel=1e-12)
    assert twice["sigma_dv"] == unit["sigma_dv"]


def test_a_template_changes_the_bias_and_not_the_clean_forecast(shared):
    from rfisher.tolerance import tolerance
    flat = tolerance(*fisher(shared))
    radial = tolerance(*fisher(shared, template=line_of_sight))
    assert radial["sigma_dv"] == flat["sigma_dv"]
    assert radial["dilations"]["covariance"] == flat["dilations"]["covariance"]
    assert radial["response_dv"] != pytest.approx(flat["response_dv"], rel=1e-3)


def test_a_template_must_be_callable(shared):
    with pytest.raises(TypeError, match="template"):
        forecast.prepare(channel(19), *shared, template=1.0)


def test_templates_load_by_name():
    assert residual.load_template("rfisher.residual:unit_power") is residual.unit_power
    assert residual.template_name(residual.unit_power) == residual.MODEL
    assert residual.template_name(doubled) == f"{__name__}:doubled"
    for spec in ("rfisher.residual", ":unit_power", "rfisher.residual:"):
        with pytest.raises(ValueError):
            residual.load_template(spec)
    with pytest.raises(TypeError):
        residual.load_template("rfisher.residual:MODEL")
