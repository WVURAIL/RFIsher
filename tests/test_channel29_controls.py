import math

import numpy as np
import pytest

from rfisher_results.validation.channel29_controls import (
    ETA_DENOMINATOR, ETA_NUMERATOR, FLOOR_LINEAR, REFERENCE_NORM_SUM_SQ,
    TARGET_NORM_SQ, assemble_cases, exact_kept, frame_seed, maximum_kept_shelf,
    population_measurement,
)


def test_exact_equality_and_adjacent_integer_decisions():
    # Every product in the comparison is far outside uint64 range.
    target = TARGET_NORM_SQ * ETA_NUMERATOR
    reference = REFERENCE_NORM_SUM_SQ * ETA_DENOMINATOR
    common = math.gcd(target, reference)
    target //= common
    reference //= common
    powers = np.array([[target-1, reference, 0], [target, reference, 0],
                       [target+1, reference, 0], [0, 0, 0]], dtype=np.uint64)
    assert exact_kept(powers).tolist() == [True, True, False, False]


def test_uint64_reference_sum_does_not_wrap():
    top = np.iinfo(np.uint64).max
    assert exact_kept(np.array([[top, top, top]], dtype=np.uint64)).item()


def test_float_measurements_refused():
    with pytest.raises(ValueError):
        exact_kept(np.ones((2, 3)))


def test_floor_is_algebraically_above_every_kept_shelf():
    assert maximum_kept_shelf() == pytest.approx(8.18028096067e-6)
    assert maximum_kept_shelf() < FLOOR_LINEAR


def test_truth_uses_only_retained_members():
    def population(n, db, keep):
        p = np.tile(np.array([[TARGET_NORM_SQ, REFERENCE_NORM_SUM_SQ, 0]], dtype=np.uint64), (n, 1))
        p[keep:, 0] *= 100
        return population_measurement(p, shelf_db=db, clip_fraction=np.zeros(n))
    populations = {"off": population(96, None, 60),
                   "on_m50": population(32, -50, 10),
                   "on_m44": population(32, -44, 2),
                   "on_m10": population(32, -10, 0)}
    rows = assemble_cases(populations)
    assert rows["intermittent_m50"]["truth"] == pytest.approx(1e-4/70)
    assert rows["intermittent_m44"]["truth"] == pytest.approx(2*10**-4.4/62)
    assert rows["intermittent_m10"]["truth"] == 0
    assert rows["null"]["kept"] == 60
    assert rows["variable_50pct"]["truth"] == pytest.approx((1e-4 + 2*10**-4.4)/72)


def test_reference_blinding_is_retained_and_reported():
    p = np.array([[637200, 1271300, 1271300]], dtype=np.uint64)
    row = population_measurement(p, shelf_db=-35, clip_fraction=np.array([.1]))
    assert row["kept"] == 1
    assert row["truth_kept_mean"] > row["assigned_kept_mean"]
    assert row["clip_fraction_mean"] == .1


def test_seeds_are_partitioned_and_reproducible():
    args = ["d6cf969313e361a5dd3b59f3bb4601f216c48e1f374bf9da1685feaaab8753e3", "calibration", 0, "off", 0]
    assert frame_seed(*args) == frame_seed(*args)
    values = {frame_seed(args[0], stage, b, pop, i) % (1 << 63)
              for stage in ["audit", "calibration", "evaluation", "stress"]
              for b in range(2) for pop in ["off", "on_m50"] for i in range(4)}
    assert len(values) == 64
