"""Strict scalar boundaries shared by the public scientific API."""
from fractions import Fraction

import numpy as np
import pytest

from rfisher import _validation as v


@pytest.mark.parametrize("validator", [v.real_scalar, v.finite_scalar,
                                       v.positive_scalar, v.nonnegative_scalar])
@pytest.mark.parametrize("value", [True, np.bool_(False), "1", None, 1 + 0j,
                                   [1], np.array(1), np.array([1])])
def test_rejects_coercible_non_real_scalars(validator, value):
    with pytest.raises(ValueError, match="exposure must be a real scalar"):
        validator(value, "exposure")


@pytest.mark.parametrize("value", [1, 0.25, np.int64(2), np.float32(0.5), Fraction(1, 3)])
def test_real_python_and_numpy_scalars_remain_accepted(value):
    for validator in (v.real_scalar, v.finite_scalar, v.positive_scalar, v.nonnegative_scalar):
        result = validator(value, "exposure")
        assert type(result) is float
        assert result == float(value)


@pytest.mark.parametrize("value", [np.nan, np.inf, -np.inf])
def test_finiteness_is_enforced_only_at_finite_boundaries(value):
    assert np.isnan(v.real_scalar(value, "x")) if np.isnan(value) else v.real_scalar(value, "x") == value
    for validator in (v.finite_scalar, v.positive_scalar, v.nonnegative_scalar):
        with pytest.raises(ValueError, match="exposure must be finite"):
            validator(value, "exposure")


def test_zero_sign_and_smallest_positive_float_boundaries():
    for zero in (0.0, -0.0):
        assert v.nonnegative_scalar(zero, "x") == 0.0
        with pytest.raises(ValueError, match="greater than zero"):
            v.positive_scalar(zero, "x")
    tiny = np.nextafter(0.0, 1.0)
    assert v.positive_scalar(tiny, "x") == tiny
    with pytest.raises(ValueError, match="non-negative"):
        v.nonnegative_scalar(-tiny, "x")
