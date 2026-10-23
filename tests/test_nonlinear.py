"""Check the finite covariance model against independent signal and score identities."""

import copy

import numpy as np
import pytest
from radiofisher import baofisher as rf

from rfisher import bands, forecast
from rfisher.nonlinear import PARAMETERS, FiniteBAOModel, check_conventions


@pytest.fixture(scope="module")
def model():
    p = forecast.prepare(bands.channel(14))
    c, e = p["cosmo"], p["expt"]
    theta = check_conventions(p)
    kval = np.linspace(0.0351, 0.2493, 39)
    uval = np.linspace(0.053, 0.947, 23)
    k, mu = np.meshgrid(kval, uval)
    ds, names = rf.fisher_integrands(kval, uval, c, e)
    q, y = c["r"] * k * np.sqrt(1 - mu**2), c["rnu"] * k * mu
    cs, cn = rf.Csignal(q, y, c, e), rf.Cnoise(q, y, c, e)
    sf = cs / (cs + cn)
    deriv = np.stack([ds[names.index(n)].ravel() for n in PARAMETERS], axis=1)
    m = FiniteBAOModel(
        k.ravel(),
        mu.ravel(),
        np.ones(k.size),
        sf.ravel(),
        np.asarray(ds[-1]).ravel(),
        deriv,
        theta,
        c["fbao"].x,
        c["fbao"].y,
    )
    return m, p


def test_finite_signal_matches_radiofisher_when_dilation_fixed(model):
    m, p = model
    changed = m.theta0.copy()
    changed[[0, 1, 4, 5]] *= [1.2, 1.3, 0.9, 1.1]
    c = copy.deepcopy(p["cosmo"])
    c.update(
        A=changed[0],
        sigma_nl=np.sqrt(changed[1]),
        f=changed[4] / (c["D"] * c["sigma_8"]),
        btot=changed[5] / (c["D"] * c["sigma_8"]),
    )
    q = c["r"] * m.k * np.sqrt(1 - m.mu2)
    y = c["rnu"] * m.k * m.mu
    direct = rf.Csignal(q, y, c, p["expt"]) / rf.Csignal(q, y, p["cosmo"], p["expt"])
    np.testing.assert_allclose(m.signal_ratio(changed), direct, rtol=2e-14)
    np.testing.assert_allclose(m.signal_ratio(m.theta0), 1, rtol=2e-14)


def test_all_six_derivatives_match_declared_fisher(model):
    m, _ = model
    check = m.derivative_check()
    assert max(check["numeric_relative_l2"]) < 1e-3
    assert max(check["piecewise_gradient_relative_l2"]) < 1e-3


def test_expected_likelihood_score_and_clean_hessian(model):
    m, _ = model
    value, gradient = m.objective(m.theta0, 0)
    assert abs(value) < 1e-20
    np.testing.assert_allclose(gradient, 0, atol=1e-16)
    _, gradient = m.objective(m.theta0, 1e-4)
    np.testing.assert_allclose(gradient, -1e-4 * m.bias_row, rtol=1e-6, atol=1e-16)
    numeric = np.empty((6, 6))
    for i in range(6):
        step = 1e-7 * max(abs(m.theta0[i]), 0.1)
        hi, lo = m.theta0.copy(), m.theta0.copy()
        hi[i] += step
        lo[i] -= step
        numeric[:, i] = (m.objective(hi, 0)[1] - m.objective(lo, 0)[1]) / (2 * step)
    scale = np.sqrt(np.diag(m.fisher))
    assert np.max(np.abs((numeric - m.fisher) / np.outer(scale, scale))) < 1e-3


def test_finite_objective_gradient_and_nonlinearity(model):
    m, _ = model
    theta = m.theta0.copy()
    theta[[0, 1, 4, 5]] *= [1.1, 0.8, 1.02, 1.03]
    theta[2:4] = [1.0031, 0.9973]
    value, grad = m.objective(theta, 1e-4)
    for i in range(6):
        step = 1e-8 * max(abs(theta[i]), 0.1)
        hi, lo = theta.copy(), theta.copy()
        hi[i] += step
        lo[i] -= step
        numeric = (m.objective(hi, 1e-4)[0] - m.objective(lo, 1e-4)[0]) / (2 * step)
        assert numeric == pytest.approx(grad[i], rel=1e-4, abs=1e-8)
    linear = 1 + (m.derivatives @ (theta - m.theta0)) / np.maximum(m.signal_fraction, 1e-250)
    assert np.max(np.abs(m.signal_ratio(theta) - linear)) > 1e-3
    assert np.isfinite(value)


def test_wrong_dilation_switch_refused(model):
    _, p = model
    q = copy.deepcopy(p)
    q["expt"]["use"]["alpha_volume"] = True
    with pytest.raises(ValueError, match="dilation switches"):
        check_conventions(q)


def test_nonphysical_signal_and_negative_strength_refused(model):
    m, _ = model
    theta = m.theta0.copy()
    theta[1] = -1
    with pytest.raises(ValueError):
        m.signal_ratio(theta)
    with pytest.raises(ValueError):
        m.objective(m.theta0, -1)


def test_zero_signal_corner_has_finite_covariance_gradient(model):
    m, _ = model
    theta = m.theta0.copy()
    theta[4:] = 0
    value, gradient = m.objective(theta, 1e-4)
    assert np.isfinite(value) and np.isfinite(gradient).all()


def test_local_exact_hessian_matches_gradient_difference(model):
    m, _ = model
    theta = m.theta0.copy()
    theta[[0, 1, 4, 5]] *= [1.1, 0.8, 1.02, 1.03]
    theta[2:4] = [1.0031, 0.9973]
    H = m.curvature(theta, 1e-4)
    numeric = np.empty((6, 6))
    for i in range(6):
        step = 1e-8 * max(abs(theta[i]), 0.1)
        hi, lo = theta.copy(), theta.copy()
        hi[i] += step
        lo[i] -= step
        numeric[:, i] = (m.objective(hi, 1e-4)[1] - m.objective(lo, 1e-4)[1]) / (2 * step)
    scale = np.sqrt(np.diag(m.fisher))
    assert np.max(np.abs((numeric - H) / np.outer(scale, scale))) < 1e-3


@pytest.fixture
def small_cache(monkeypatch, tmp_path):
    from rfisher.nonlinear import build_model

    monkeypatch.setattr(forecast, "radial_edges", lambda p: np.linspace(0.0311, 0.2493, 41))
    monkeypatch.setattr(forecast, "angular_edges", lambda k, p: np.array([0.043, 0.25, 0.5, 0.75, 1.0]))
    p = forecast.prepare(bands.channel(14))
    directory = tmp_path / "cache"
    m, identity = build_model(p, directory, radial_order=2, angular_order=3, chunk_segments=8)
    return p, directory, m, identity


def test_normal_prepared_grid_and_resumption(small_cache):
    from rfisher.nonlinear import build_model

    p, directory, first, identity = small_cache
    second, again = build_model(p, directory, radial_order=2, angular_order=3, chunk_segments=8)
    assert identity == again
    np.testing.assert_array_equal(first.derivatives, second.derivatives)
    np.testing.assert_array_equal(first.fisher, second.fisher)


def test_changed_noise_setting_and_custom_residual_refused(small_cache):
    from rfisher.nonlinear import build_model

    p, directory, _, _ = small_cache
    p["expt"]["dnu"] *= 2
    with pytest.raises(ValueError, match="identity differs"):
        build_model(p, directory, radial_order=2, angular_order=3, chunk_segments=8)
    p["expt"]["P_res"] = lambda *args: 0
    with pytest.raises(ValueError, match="standard coherent-shelf"):
        build_model(p, directory, radial_order=2, angular_order=3, chunk_segments=8)


def test_swapped_valid_chunk_is_refused(small_cache):
    from rfisher.nonlinear import build_model

    p, directory, _, _ = small_cache
    (directory / "00008.npz").write_bytes((directory / "00000.npz").read_bytes())
    with pytest.raises(ValueError, match="identity/segment"):
        build_model(p, directory, radial_order=2, angular_order=3, chunk_segments=8)


def test_mutated_checkpoint_payload_refused(small_cache):
    from rfisher.nonlinear import build_model

    p, directory, _, _ = small_cache
    path = directory / "00000.npz"
    with np.load(path) as z:
        data = {k: z[k] for k in z.files}
    data["rows"][0, 3] += 1
    np.savez_compressed(path, **data)
    with pytest.raises(ValueError, match="payload mismatch"):
        build_model(p, directory, radial_order=2, angular_order=3, chunk_segments=8)


def test_retention_check_uses_covariance_scale_and_rejects_real_change():
    from rfisher.nonlinear import check_retained_modes

    full = np.eye(7)
    full[0, 1] = full[1, 0] = 1e-20
    fisher = full[:6, :6].copy()
    fisher[0, 1] += 1e-15
    bias = full[:6, 6].copy()
    bias[2] += 1e-15
    check = check_retained_modes(fisher, bias, full)
    assert check["fisher_max_normalized"] < 1e-12
    assert check["bias_max_normalized"] < 1e-12
    fisher[2, 2] += 1e-6
    with pytest.raises(ValueError, match="discarding infinite-noise"):
        check_retained_modes(fisher, bias, full)


def test_blocked_sums_reproduce_independent_weighted_outer_products(model):
    m, _ = model
    # Noninteger replication exercises the block boundary and final short block.
    ix = np.arange(70003) % len(m.k)
    repeated = FiniteBAOModel(
        m.k[ix],
        m.mu[ix],
        m.weight[ix],
        m.signal_fraction[ix],
        m.residual_fraction[ix],
        m.derivatives[ix],
        m.theta0,
        m.template_k,
        m.template_f,
    )
    counts = np.bincount(ix, minlength=len(m.k))
    expected_f = np.einsum("ni,nj,n->ij", m.derivatives, m.derivatives, m.weight * counts)
    expected_b = np.einsum("ni,n->i", m.derivatives, m.weight * m.residual_fraction * counts)
    np.testing.assert_allclose(repeated.fisher, expected_f, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(repeated.bias_row, expected_b, rtol=1e-12, atol=1e-12)
