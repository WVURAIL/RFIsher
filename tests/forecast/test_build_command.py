"""``rfisher build-bank`` sets the same grid and overrides as the two builders it merged."""
from __future__ import annotations

import json

import numpy as np
import pytest

from rfisher import cli
from rfisher.forecast.radiofisher_bao.bank import banks, build, templates
from test_fisherbank_schema import _write_bank


def _old_script_grid(tmin, tmax, nt, dense_knee=False, knee_range=(3.5, 5.83),
                     knee_n=8):
    """The expressions of the retired scripts/build_bank.py."""
    tgrid = np.logspace(np.log10(tmin), np.log10(tmax), nt)
    if dense_knee:
        lo, hi = knee_range
        extra = 10.0 ** np.linspace(lo, hi, knee_n)
        tgrid = np.unique(np.concatenate([tgrid, extra]))
    return tgrid


def _old_command_grid(tmin, tmax, nt, extra_time_hours=()):
    """The expressions of the retired rfisher-build-bank command."""
    t_grid = np.logspace(np.log10(tmin), np.log10(tmax), nt)
    if extra_time_hours:
        extra = np.asarray(extra_time_hours, dtype=float)
        t_grid = np.unique(np.concatenate([t_grid, extra]))
    return t_grid


@pytest.fixture
def captured(monkeypatch):
    seen = {}
    monkeypatch.setattr(build, "build_bank", lambda output, **kwargs: seen.update(
        output=output, **kwargs))
    return seen


def _same_floats(a, b):
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    return a.shape == b.shape and a.tobytes() == b.tobytes()


@pytest.mark.parametrize("argv,expected", [
    ([], _old_script_grid(1.0, 1e6, 19)),
    (["--nt", "27"], _old_script_grid(1.0, 1e6, 27)),
    (["--nt", "3", "--tmin", "100", "--tmax", "10000"],
     _old_script_grid(100.0, 1e4, 3)),
    (["--dense-knee"], _old_script_grid(1.0, 1e6, 19, dense_knee=True)),
    (["--dense-knee", "--knee-n", "2", "--nt", "2", "--tmin", "1000",
      "--tmax", "100000"],
     _old_script_grid(1000.0, 1e5, 2, dense_knee=True, knee_n=2)),
    (["--dense-knee", "--knee-range", "3.0", "6.0", "--knee-n", "5"],
     _old_script_grid(1.0, 1e6, 19, dense_knee=True, knee_range=(3.0, 6.0),
                      knee_n=5)),
    (["--nt", "27", "--extra-time-hours", "3162.2776601683795"],
     _old_command_grid(1.0, 1e6, 27, [3162.2776601683795])),
    (["--nt", "5", "--extra-time-hours", "7.5", "--extra-time-hours", "40"],
     _old_command_grid(1.0, 1e6, 5, [7.5, 40.0])),
])
def test_the_time_grid_is_float_for_float_the_old_one(tmp_path, captured, argv,
                                                        expected):
    assert cli.main(["build-bank", "--out", str(tmp_path / "b.npz"), *argv]) == 0
    assert _same_floats(captured["t_grid_hours"], expected)


def test_the_extra_times_never_move_the_base_grid():
    base = build.time_grid(1.0, 1e6, 27)
    knee = 10.0 ** 3.5
    grid = build.time_grid(1.0, 1e6, 27, extra_hours=[knee])
    assert _same_floats(np.setdiff1d(grid, [knee]), base)


@pytest.mark.parametrize("argv,expected", [
    ([], None),
    (["--p-res", "1.0"], {"P_res": 1.0}),
    (["--p-res", "1.0", "--kfg-fac", "80"], {"P_res": 1.0, "kfg_fac": 80.0}),
    (["--kfg-fac", "22"], {"kfg_fac": 22.0}),
])
def test_the_residual_and_filter_overrides_are_the_old_ones(tmp_path, captured,
                                                             argv, expected):
    assert cli.main(["build-bank", "--out", str(tmp_path / "b.npz"), *argv]) == 0
    assert captured["expt_overrides"] == expected


def test_a_named_template_is_the_authenticated_template(tmp_path, captured):
    assert cli.main([
        "build-bank", "--out", str(tmp_path / "b.npz"),
        "--residual-template", "low_kparallel",
        "--template-param", "k_parallel_scale_mpc_inv=0.04"]) == 0
    template = captured["expt_overrides"]["P_res"]
    assert template == templates.make_template(
        "low_kparallel", {"k_parallel_scale_mpc_inv": 0.04})
    assert templates.validate_template_metadata(dict(template)) == dict(template)


@pytest.mark.parametrize("argv", [
    ["--template-param", "slope=1"],
    ["--p-res", "1.0", "--residual-template", "noise_shaped"],
    ["--residual-template", "wedge_like", "--template-param", "unknown=1"],
    ["--nt", "1"],
    ["--extra-time-hours", "2e6"],
])
def test_invalid_build_requests_fail_before_any_work(tmp_path, captured, argv):
    with pytest.raises(SystemExit):
        cli.main(["build-bank", "--out", str(tmp_path / "b.npz"), *argv])
    assert captured == {}


@pytest.mark.parametrize("argv,name", [
    (["--config", "chime2022"], "fisher_bank_chime2022_cmbspa2026.npz"),
    (["--cosmology", "planck2018"], "fisher_bank_chime2022.npz"),
    (["--cosmology", "pact2025"], "fisher_bank_chime2022_pact2025.npz"),
    (["--cosmology", "planck2018", "--epsilon-fg", "0", "--p-res", "1.0",
      "--dense-knee"], "fisher_bank_chime2022_pres_dense.npz"),
    (["--cosmology", "planck2018", "--epsilon-fg", "0", "--p-res", "1.0",
      "--kfg-fac", "44", "--dense-knee"],
     "fisher_bank_chime2022_pres_kfg44_dense.npz"),
    (["--cosmology", "planck2018", "--residual-template", "wedge_like"],
     "fisher_bank_chime2022_pres_wedge_like.npz"),
    (["--config", "bull2015", "--epsilon-fg", "1e-6"],
     "fisher_bank_bull2015_planck2013_epsfg1e-6.npz"),
    (["--config", "bull2015", "--epsilon-fg", "1e-5"],
     "fisher_bank_bull2015_planck2013_epsfg1e-5.npz"),
])
def test_a_directory_receives_the_conventional_name(tmp_path, captured, argv,
                                                    name):
    assert cli.main(["build-bank", "--out", str(tmp_path), *argv]) == 0
    assert captured["output"] == tmp_path / name


def test_a_build_with_a_stub_backend_writes_a_bank_that_loads(monkeypatch,
                                                               tmp_path):
    template = _write_bank(tmp_path / "template.npz")
    with np.load(template, allow_pickle=False) as archive:
        metadata = json.loads(str(archive["meta"]))

    def worker(task):
        ibin, hours = task
        return ibin, hours, np.diag([ibin + 1.0, ibin + 2.0]) * hours**2, [
            "A", "sigma_NL"]

    monkeypatch.setattr(banks, "_CTX", {
        "astrophysical_model_profile": "chime_overview_2022"})
    monkeypatch.setattr(banks, "_init_context", lambda *a, **kw: (
        object(), np.array([0.8, 0.9, 1.0]), np.array([0.85, 0.95])))
    monkeypatch.setattr(banks, "_build_provenance",
                        lambda: metadata["provenance"])
    monkeypatch.setattr(banks, "_one_fisher", worker)
    output = tmp_path / "bank.npz"
    assert cli.main(["build-bank", "--out", str(output), "--nt", "3",
                     "--tmin", "1", "--tmax", "4", "--nproc", "1",
                     "--cosmology", "planck2018"]) == 0
    bank = banks.FisherBank(output)
    assert _same_floats(bank.t_grid, _old_script_grid(1.0, 4.0, 3))
    assert bank.meta["cosmology"] == "planck2018"
    np.testing.assert_array_equal(bank.F(1, 2.0), np.diag([2.0, 3.0]) * 4.0)
