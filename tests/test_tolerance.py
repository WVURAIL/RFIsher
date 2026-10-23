import importlib

import numpy as np
import pytest

from rfisher.tolerance import DV_WEIGHTS, FITTED, tolerance

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
