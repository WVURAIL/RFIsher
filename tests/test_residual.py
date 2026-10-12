import numpy as np
import pytest

from rfisher import forecast, residual
from rfisher.bands import channel


@pytest.fixture(scope="module")
def prepared(shared):
    return forecast.prepare(channel(19), *shared)


def test_geometry_of_a_6_mhz_channel(prepared):
    g = prepared["geometry"]
    assert g["n_nu"] == pytest.approx(6.0 / 0.39)
    assert g["m"] == pytest.approx(g["r"] * (1 + g["z"]) / prepared["cosmo"]["rnu"])
    assert prepared["expt"]["dnutot"] == pytest.approx(6.0)


def test_the_shelf_sits_inside_the_wedge(prepared):
    g = prepared["geometry"]
    dP = residual.coherent_shelf(g)
    kperp = 0.05
    kw = residual.wedge_kpar(kperp, g)
    inside, outside = 0.5 * kw, 2.0 * kw
    k = np.hypot(kperp, np.array([inside, outside]))
    u = np.array([inside, outside]) / k
    out = dP(k, u, np.ones(2), np.ones(2))
    assert out[0] > 0 and out[1] == 0


def test_the_shelf_scales_with_the_noise(prepared):
    dP = residual.coherent_shelf(prepared["geometry"])
    one = dP(np.array([0.05]), np.array([0.1]), np.array([1.0]), np.array([1.0]))
    three = dP(np.array([0.05]), np.array([0.1]), np.array([3.0]), np.array([1.0]))
    assert three == pytest.approx(3 * one)


def test_wedge_edge(prepared):
    g = prepared["geometry"]
    k = 0.2
    mu = residual.wedge_mu(k, g)
    assert mu is not None
    kperp, kpar = k * np.sqrt(1 - mu * mu), k * mu
    assert kpar == pytest.approx(residual.wedge_kpar(kperp, g), rel=1e-10)
    assert residual.wedge_mu(1e-4, g) is None


def test_the_residual_is_attached_to_the_bin(prepared):
    assert callable(prepared["expt"]["P_res"])
