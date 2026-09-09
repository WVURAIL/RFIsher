"""Boundary and accounting checks for the retrospective comparison driver."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from rfisher.thresholds import ALWAYS_MASKED_Q16, MAX_MULTIPLIER_Q16

PATH = Path(__file__).resolve().parents[1] / 'scripts/compare_channel29_policies_v1.py'
SPEC = importlib.util.spec_from_file_location('channel29_policy_driver_test', PATH)
driver = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(driver)


def test_bundle_zero_sentinel_is_not_a_free_keep():
    bundle = SimpleNamespace(
        rho=np.array([1]), required_multiplier_q16=np.array([[0], [1], [MAX_MULTIPLIER_Q16]], dtype=np.uint64),
        always_masked=np.array([[True], [False], [False]]))
    req = driver.decoded_requirements(bundle, 1)
    assert list(req) == [ALWAYS_MASKED_Q16, 1, MAX_MULTIPLIER_Q16]
    assert driver.fine_keep(req, MAX_MULTIPLIER_Q16).tolist() == [False, True, True]
    assert bundle.required_multiplier_q16[0, 0] == 0


def test_missing_frozen_rank_does_not_fall_back():
    bundle = SimpleNamespace(rho=np.array([1, 2]))
    with pytest.raises(ValueError, match='Frozen rank unavailable'):
        driver.decoded_requirements(bundle, 3)


def test_allowance_and_cost_use_same_retained_exposure():
    bundle = SimpleNamespace(exposure_seconds=np.array([1., 3., 2.]),
                             frame_time=np.array([1., 2., 3.]),
                             acquisition_index=np.array([0, 1, 2]))
    budgets = {w: {'dilation': None, 'fs8': 2.} for w in driver.WORLD_SUPPRESSION_DB}
    row = driver.block_summary(np.array([True, True, False]), bundle, np.array([1., 5., 100.]), 1., 10., budgets)
    assert row['allowance'] == 4.
    assert row['chain_allowance'] == 40.
    assert row['retention'] == 2 / 3
    assert row['mask_only_cost_restore_one_retained_year'] == 1.5
    assert row['pricing']['none']['fs8']['R'] == 20.
    assert row['pricing']['none']['dilation']['R'] is None
    assert row['pricing']['none']['dilation']['status'] == 'unpriced'
    assert row['floor_only_kept'] == 1


def test_zero_kept_is_unpriced_not_zero_residual():
    bundle = SimpleNamespace(exposure_seconds=np.ones(2), frame_time=np.array([1., 2.]),
                             acquisition_index=np.array([0, 1]))
    budgets = {w: {'dilation': 1., 'fs8': 2.} for w in driver.WORLD_SUPPRESSION_DB}
    row = driver.block_summary(np.zeros(2, dtype=bool), bundle, np.ones(2), 1., 10., budgets)
    assert row['kept'] == 0
    assert row['allowance'] is None
    assert row['mask_only_cost_restore_one_retained_year'] is None
    assert row['pricing']['deployed']['fs8']['R'] is None


def test_calibration_halves_have_fixed_denominator():
    bundle = SimpleNamespace(exposure_seconds=np.ones(4), frame_time=np.arange(4.),
                             acquisition_index=np.arange(4))
    budgets = {w: {'dilation': 1., 'fs8': 2.} for w in driver.WORLD_SUPPRESSION_DB}
    row = driver.block_summary(np.array([True, False, True, True]), bundle, np.ones(4), 1., 10., budgets,
                               cohort=np.array([True, True, False, False]))
    assert row['frames'] == 2 and row['kept'] == 1
    assert row['mask_only_cost_restore_one_retained_year'] == 2.


def test_analysis_refuses_existing_output(tmp_path):
    with pytest.raises(ValueError, match='new directory'):
        driver.run(SimpleNamespace(release=tmp_path, output=tmp_path))
