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
    assert taucut.TAU_NS_DEFAULT == (30.0, 50.0, 75.0, 100.0, 110.0, 125.0,
                                     140.0, 150.0, 160.0, 175.0, 200.0,
                                     280.0, 400.0)
    # The grid is never coarser than 25 ns through the 100-200 ns decade
    # where the archive curves cross 5 and 3 sigma, so those crossings are
    # read off rather than interpolated across a 50 ns gap.
    steep = [t for t in taucut.TAU_NS_DEFAULT if 100.0 <= t <= 200.0]
    assert max(np.diff(steep)) <= 25.0
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


def test_threshold_is_bracketed_on_the_grid_not_fitted():
    taus = [50.0, 100.0, 125.0, 150.0, 200.0]
    sig = [30.0, 11.0, 6.0, 2.5, 0.4]

    t0, s0, t1, s1, interp = taucut.read_off_threshold(taus, sig, 5.0)
    assert (t0, s0, t1, s1) == (125.0, 6.0, 150.0, 2.5)
    assert 125.0 < interp < 150.0
    # log-log interpolation between the bracketing grid points
    expected = np.exp(np.interp(np.log(5.0), [np.log(2.5), np.log(6.0)],
                                [np.log(150.0), np.log(125.0)]))
    assert interp == pytest.approx(expected)

    # unsorted input is fine; the bracket is the same
    assert taucut.read_off_threshold(taus[::-1], sig[::-1], 5.0)[:4] \
        == (125.0, 6.0, 150.0, 2.5)


def test_threshold_reports_never_reached_and_never_dropped():
    taus = [50.0, 100.0, 150.0]
    assert taucut.read_off_threshold(taus, [2.0, 1.0, 0.5], 3.0) \
        == (None, None, None, None, None)
    t0, s0, t1, s1, interp = taucut.read_off_threshold(
        taus, [9.0, 8.0, 7.0], 5.0)
    assert (t0, s0) == (150.0, 7.0)
    assert (t1, s1, interp) == (None, None, None)


def test_threshold_rows_and_caption_survive_dead_curves():
    """The published field never reaches 5 sigma and is dead above 150 ns;
    the tables and caption must render that without a crash or a fake
    number."""
    curves = {
        "chime2025": {"tau": [50.0, 100.0, 150.0, 200.0],
                      "significance": [3.1, 0.9, 0.1, 0.0], "no_cut": 5.3},
        "archive7yr": {"tau": [50.0, 100.0, 150.0, 200.0],
                       "significance": [30.0, 11.0, 2.5, 0.4],
                       "no_cut": 50.0},
    }
    rows = taucut._threshold_rows(curves, 7.0)
    assert {r["cut"] for r in rows} == {"hard"}
    by = {(r["config"], r["target_sigma"]): r for r in rows}
    assert by[("chime2025", "5")]["tau_last_at_or_above_ns"] == ""
    assert by[("chime2025", "3")]["tau_last_at_or_above_ns"] == "50"
    assert by[("chime2025", "3")]["tau_first_below_ns"] == "100"
    assert by[("archive7yr", "5")]["tau_last_at_or_above_ns"] == "100"
    assert by[("archive7yr", "5")]["tau_first_below_ns"] == "150"

    caption = taucut._caption(
        headline=2.2, ratio=0.18, uncut=10.4, uncut_ratio=0.84,
        undamped=88.0, sigma_nl_match=4.9, ttot_factor=5.6,
        sigma_nl_fiducial=7.0, curves=curves, curves_matched=None,
        threshold_rows=rows)
    assert "never reached" in caption
    assert "100-150 ns" in caption
    assert "sensitivity sweep not run" in caption
    assert "12.4" in caption


def test_soft_cut_rows_are_kept_apart_from_the_hard_ones():
    curves = {"archive7yr": {"tau": [100.0, 150.0], "significance": [12.0, 4.0],
                             "no_cut": 50.0}}
    hard = taucut._threshold_rows(curves, 7.0)
    soft = taucut._threshold_rows(curves, 7.0, cut="soft")
    assert {r["cut"] for r in hard} == {"hard"}
    assert {r["cut"] for r in soft} == {"soft"}
    caption = taucut._caption(
        headline=2.2, ratio=0.18, uncut=10.4, uncut_ratio=0.84,
        undamped=88.0, sigma_nl_match=4.9, ttot_factor=5.6,
        sigma_nl_fiducial=7.0, curves=curves, curves_matched=None,
        threshold_rows=hard + soft, curves_soft=curves)
    assert "archive7yr (soft)" in caption
    assert "Fig. 10" in caption
    assert taucut.SOFT_CUT_CONFIGS == ("archive7yr",)


def test_fig10_format_figure_renders_on_the_delay_axis(tmp_path):
    """Two panels on the paper's delay axis: the digitised filter response
    on top, BAO significance against the retained delay floor below."""
    curves = {
        "archive7yr": {"tau": [50.0, 100.0, 150.0, 200.0],
                       "significance": [30.0, 11.0, 2.5, 0.05]},
        "chime2025": {"tau": [50.0, 100.0, 150.0, 200.0],
                      "significance": [3.1, 0.9, 0.05, 0.0]},
    }
    ratio = np.array([0.0, 0.95, 1.0, 1.2, 1.4, 2.0, 4.0, 6.0])
    response = np.array([0.0, 0.0, 0.0, 0.5, 0.75, 0.83, 0.86, 0.87])
    out = taucut.fig_fig10_format(
        curves, {"archive7yr": "archive", "chime2025": "field"},
        {"archive7yr": 50.0, "chime2025": 5.3},
        {"archive7yr": {"tau": [50.0, 100.0, 150.0, 200.0],
                        "significance": [32.0, 14.0, 4.2, 0.9]}},
        delay_floor_of_tau=lambda tau: 1.4 * np.asarray(tau),
        kpar_of_delay=lambda delay: 0.00125 * np.asarray(delay),
        residual_table=(ratio, response),
        markers=taucut.TAU_NS_MARKERS, tau_cut_ns=200.0, tau_mask_ns=280.0,
        z_reference=1.16, outfile=tmp_path / "fig10.png")
    assert Path(out).is_file()
    assert (tmp_path / "fig10.pdf").is_file()
