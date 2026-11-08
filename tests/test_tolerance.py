import importlib

import numpy as np
import pytest

from rfisher.tolerance import DV_WEIGHTS, FITTED, target_tolerance, tolerance

NAMES = ["A", "b_HI", "Tb", "s_NL", "sigma8tot", "n_s", "f", "aperp", "apar", "fs8", "bs8", "pk", "_Pres"]


def synthetic(B):
    """A Fisher matrix whose fitted block is diagonal with sigma = 0.02 for each dilation."""
    F = np.zeros((len(NAMES), len(NAMES)))
    for p in FITTED:
        i = NAMES.index(p)
        F[i, i] = 1 / 0.02 ** 2 if p in ("aperp", "apar") else 1.0
    for p, b in B.items():
        i, j = NAMES.index(p), NAMES.index("_Pres")
        F[i, j] = F[j, i] = b
    return F


def test_known_answer():
    # bias = C B = 0.02^2 B, so the dilation biases are 20 and 10
    t = tolerance(synthetic({"aperp": 5e4, "apar": 2.5e4}), NAMES)
    bias = np.array([20.0, 10.0])
    sigma_dv = 0.02 * np.sqrt((DV_WEIGHTS ** 2).sum())
    assert t["dilations"]["sigma"] == pytest.approx([0.02, 0.02])
    assert t["sigma_dv"] == pytest.approx(sigma_dv)
    assert t["response_dv"] == pytest.approx(DV_WEIGHTS @ bias / sigma_dv)
    assert t["a_tol"] == pytest.approx(1 / abs(t["response_dv"]))


def test_opposite_biases_cancel_in_d_v():
    t = tolerance(synthetic({"aperp": 5e4, "apar": -1e5}), NAMES)
    assert t["dilations"]["response"] == pytest.approx([1000.0, -2000.0])
    assert t["response_dv"] == pytest.approx(0.0, abs=1e-9)
    assert t["a_tol"] > 1e9


@pytest.mark.parametrize("direction", [-1, 1])
def test_distance_shift_has_opposite_sign_to_fitted_dilation(direction):
    result = tolerance(synthetic({"aperp": direction * 5e4, "apar": direction * 2.5e4}), NAMES)
    strength = 1e-8
    aperp, apar = 1 + strength * np.asarray(result["dilations"]["bias_per_unit_a"])
    distance_ratio = aperp ** (-2 / 3) * apar ** (-1 / 3)
    distance_shift = np.log(distance_ratio) / result["sigma_dv"]
    assert distance_shift == pytest.approx(-strength * result["response_dv"], rel=1e-6)
    assert result["bias_dv_per_unit_a"] == pytest.approx(
        result["response_dv"] * result["sigma_dv"]
    )


def test_held_parameters_do_not_enter():
    F = synthetic({"aperp": 5e4})
    G = F.copy()
    G[NAMES.index("b_HI"), NAMES.index("aperp")] = G[NAMES.index("aperp"), NAMES.index("b_HI")] = 1e9
    assert tolerance(F, NAMES)["response_dv"] == tolerance(G, NAMES)["response_dv"]


def test_a_fitted_parameter_without_information_is_refused():
    F = synthetic({"aperp": 1.0})
    F[NAMES.index("fs8"), NAMES.index("fs8")] = 0
    with pytest.raises(ValueError):
        tolerance(F, NAMES)


def test_the_explicit_module_and_function_imports():
    module = importlib.import_module("rfisher.tolerance")
    exported = importlib.import_module("rfisher").tolerance   # what `from rfisher import tolerance` binds
    assert exported is module and not callable(exported)
    assert exported.FITTED == FITTED and exported.tolerance is tolerance
    F = synthetic({"aperp": 5e4, "apar": 2.5e4})
    assert exported.tolerance(F, NAMES) == tolerance(F, NAMES)


def test_the_dv_target_reproduces_the_dv_tolerance():
    F = synthetic({"aperp": 5e4, "apar": 2.5e4, "fs8": 3.0})
    dv, target = tolerance(F, NAMES), target_tolerance(F, NAMES, "dv")
    assert target["sigma"] == pytest.approx(dv["sigma_dv"], rel=1e-14)
    assert target["response"] == pytest.approx(dv["response_dv"], rel=1e-14)
    assert target["a_tol"] == pytest.approx(dv["a_tol"], rel=1e-14)


def test_single_parameter_targets():
    # the fitted block is diagonal, so each bias is C B and each sigma is the diagonal error
    F = synthetic({"aperp": 5e4, "apar": 2.5e4, "fs8": 3.0})
    assert target_tolerance(F, NAMES, "aperp")["response"] == pytest.approx(20.0 / 0.02)
    assert target_tolerance(F, NAMES, "apar")["response"] == pytest.approx(10.0 / 0.02)
    assert target_tolerance(F, NAMES, "fs8")["response"] == pytest.approx(3.0)
    assert target_tolerance(F, NAMES, {"aperp": 1, "apar": -1})["bias_per_unit_a"] == pytest.approx(10.0)


def test_a_projection_from_another_fisher_code():
    F = synthetic({"aperp": 5e4, "apar": 2.5e4})
    keep = [i for i, n in enumerate(NAMES) if n != "_Pres"]
    clean, names = F[np.ix_(keep, keep)], [NAMES[i] for i in keep]
    B = F[keep, NAMES.index("_Pres")]
    embedded = target_tolerance(F, NAMES, "dv")
    supplied = target_tolerance(clean, names, "dv", bias_projection=B)
    assert supplied == embedded


def test_a_target_of_a_smaller_fitted_set():
    F = synthetic({"aperp": 5e4, "apar": 2.5e4})
    result = target_tolerance(F, NAMES, "aperp", fitted=("aperp", "apar"))
    assert result["sigma"] == pytest.approx(0.02) and result["response"] == pytest.approx(1000.0)


@pytest.mark.parametrize("weights, message", [({}, "at least one"), ({"b_HI": 1.0}, "not fitted")])
def test_a_bad_target_is_refused(weights, message):
    with pytest.raises(ValueError, match=message):
        target_tolerance(synthetic({"aperp": 1.0}), NAMES, weights)


def test_a_target_without_a_residual_is_refused():
    keep = [i for i, n in enumerate(NAMES) if n != "_Pres"]
    F = synthetic({"aperp": 1.0})[np.ix_(keep, keep)]
    with pytest.raises(ValueError, match="residual"):
        target_tolerance(F, [NAMES[i] for i in keep], "dv")
