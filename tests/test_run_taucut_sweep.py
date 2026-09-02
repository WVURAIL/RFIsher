"""Metric contracts for the delay-cut sweep driver."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from rfisher import survey

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "rfisher_test_run_taucut_sweep", ROOT / "scripts" / "run_taucut_sweep.py")
assert SPEC is not None and SPEC.loader is not None
taucut = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(taucut)


def test_delay_grid_and_markers_are_the_proposal_figure_s():
    assert taucut.TAU_NS_DEFAULT == (30.0, 50.0, 75.0, 100.0, 150.0, 200.0,
                                     280.0, 400.0)
    assert [tau for tau, _ in taucut.TAU_NS_MARKERS] == [280.0, 100.0, 50.0]
    # Every marked delay is a point the sweep actually evaluates.
    assert {tau for tau, _ in taucut.TAU_NS_MARKERS} <= set(
        taucut.TAU_NS_DEFAULT)
    assert survey.CHIME2025_TAU_CUT_NS in taucut.TAU_NS_DEFAULT


def test_calibration_lifts_the_nonlinear_cutoff_above_the_detection_band():
    """k_NL,0 = 0.14 Mpc^-1 reaches 0.35 h/Mpc at z = 1.16 and would delete
    the whole 0.4-1.5 h/Mpc band the published detection lives in."""
    ns = 0.96605
    z = survey.CHIME2025_Z_REFERENCE
    default_cut_mpc = 0.14 * (1.0 + z) ** (2.0 / (2.0 + ns))
    lifted_cut_mpc = taucut.CALIBRATION_K_NL0 * (1.0 + z) ** (2.0 / (2.0 + ns))
    band_top_mpc = survey.CHIME2025_KMAX_H * 0.6732

    assert default_cut_mpc < survey.CHIME2025_KMIN_H * 0.6732
    assert lifted_cut_mpc > band_top_mpc


def test_quadrature_combines_independent_bins_and_ignores_dead_ones():
    assert taucut._quadrature([1.0, 1.0]) == pytest.approx(1.0 / np.sqrt(2.0))
    assert taucut._quadrature([2.0, np.inf]) == pytest.approx(2.0)
    assert taucut._quadrature([np.inf, np.inf]) == np.inf
    assert taucut._quadrature([]) == np.inf


def test_infinite_errors_are_written_as_inf_not_silently_rounded():
    assert taucut._fmt(np.inf) == "inf"
    assert taucut._fmt(0.0) == "0"
    assert taucut._fmt(0.123456789, 4) == "0.1235"


def test_bao_metrics_use_the_repository_s_shared_A_marginalisation():
    """A diagonal three-parameter stack must give sigma(A) from the summed
    A information, and per-bin alphas that combine in quadrature."""
    names = ["A", "b_HI", "Tb", "sigma_NL", "sigma8tot", "n_s", "f",
             "aperp", "apar", "fs8", "bs8", "pk"]
    nbins = 2

    def matrix(scale):
        F = np.eye(len(names)) * scale
        return F

    F_list = [matrix(4.0), matrix(4.0)]

    from rfisher.backend import find_radiofisher_dir, import_radiofisher
    try:
        find_radiofisher_dir()
    except FileNotFoundError:
        pytest.skip("bao_metrics needs the backend's matrix combiner")
    rf, _ = import_radiofisher()

    metrics = taucut.bao_metrics(rf, names, F_list)

    # A is shared: two bins of information 4 each -> sigma = 1/sqrt(8).
    assert metrics["sigma_A"] == pytest.approx(1.0 / np.sqrt(8.0))
    assert metrics["significance"] == pytest.approx(np.sqrt(8.0))
    assert len(metrics["per_bin"]) == nbins
    # apar/aperp are expanded per bin: 4 each, combined in quadrature.
    for entry in metrics["per_bin"]:
        assert entry["sigma_apar"] == pytest.approx(0.5)
        assert entry["sigma_aperp"] == pytest.approx(0.5)
    assert metrics["sigma_apar"] == pytest.approx(0.5 / np.sqrt(2.0))
    assert metrics["sigma_aperp"] == pytest.approx(0.5 / np.sqrt(2.0))
