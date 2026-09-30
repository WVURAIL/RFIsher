"""The delay-filter scenarios, their assumed suppression, the profile, and the hooks."""
from __future__ import annotations

from pathlib import Path

import shutil

import numpy as np
import pytest
import yaml

from rfisher import policy
from rfisher.forecast.radiofisher_bao import filter_scenarios, model
from rfisher.forecast.radiofisher_bao.bank.physics import HI_REST_FREQUENCY_MHZ

PROJECT = Path(__file__).resolve().parents[2] / "projects" / "chime_bao"

# The redshift at which the CHIME 2025 detection quotes its k_par floor.
Z_REFERENCE = 1.16


def _radiofisher_backend():
    from rfisher.forecast.radiofisher_bao.bank.backend import (
        find_radiofisher_dir, import_radiofisher)
    try:
        find_radiofisher_dir()
    except FileNotFoundError:
        pytest.skip("delay-cut binding requires a RadioFisher checkout")
    return import_radiofisher()


def test_delay_cut_reproduces_the_published_kpar_floor():
    """200 ns filter + 280 ns mask = 0.35 h/Mpc at z = 1.16, which is where
    the published auto-spectrum measurement begins."""
    from rfisher.forecast.radiofisher_bao.bank import cosmologies

    rf, rf_dir = _radiofisher_backend()
    cosmo = cosmologies.get("planck2018", rf, rf_dir)
    cosmo_fns = rf.background_evolution_splines(cosmo)
    experiment = {"nu_line": HI_REST_FREQUENCY_MHZ}

    kpar_min_fn = filter_scenarios.delay_cut(rf, experiment, cosmo_fns, 200e-9)

    kpar_min = kpar_min_fn(Z_REFERENCE)
    assert kpar_min / cosmo["h"] == pytest.approx(0.351, abs=5e-4)
    # A zero cut is a valid no-op so the no-cut reference runs the same path.
    assert filter_scenarios.delay_cut(rf, experiment, cosmo_fns, 0.0)(1.16) == 0.0
    # Linear in the delay, and the transition factor is separable.
    assert filter_scenarios.delay_cut(rf, experiment, cosmo_fns, 100e-9)(1.16) \
        == pytest.approx(0.5 * kpar_min)
    assert filter_scenarios.delay_cut(
        rf, experiment, cosmo_fns, 280e-9, transition=1.0)(1.16) \
        == pytest.approx(kpar_min)


def test_delay_cut_rejects_a_negative_delay():
    rf, rf_dir = _radiofisher_backend()
    from rfisher.forecast.radiofisher_bao.bank import cosmologies
    cosmo_fns = rf.background_evolution_splines(
        cosmologies.get("planck2018", rf, rf_dir))

    with pytest.raises(ValueError, match="tau_cut_seconds"):
        filter_scenarios.delay_cut(rf, {"nu_line": HI_REST_FREQUENCY_MHZ},
                                   cosmo_fns, -1e-9)


def test_filter_residual_table_is_the_digitised_fig10():
    ratio, response = filter_scenarios.filter_residual_table()

    assert ratio[0] == 0.0 and ratio[-1] > 6.0          # 0 to > 1200 ns
    assert np.all(np.diff(ratio) > 0.0)
    assert np.all(response >= 0.0) and response.max() < 1.0
    # zero below the 200 ns cut, a plateau of ~0.87 at high delay, and
    # about 0.75 at the 280 ns mask edge (ratio 1.4)
    assert np.interp(0.9, ratio, response) == pytest.approx(0.0, abs=1e-3)
    assert np.interp(1.4, ratio, response) == pytest.approx(0.756, abs=0.02)
    assert np.median(response[ratio > 4.0]) == pytest.approx(0.870, abs=0.01)


def test_filter_residual_table_rejects_malformed_files(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("a,b\n1.0,0.5\n0.5,0.6\n")
    with pytest.raises(ValueError, match="increase"):
        filter_scenarios.filter_residual_table(bad)
    bad.write_text("a,b\n0.0,-0.5\n1.0,0.6\n")
    with pytest.raises(ValueError, match="non-negative"):
        filter_scenarios.filter_residual_table(bad)


def test_delay_transfer_binds_the_fig10_response_to_the_backend():
    from rfisher.forecast.radiofisher_bao.bank import cosmologies

    rf, rf_dir = _radiofisher_backend()
    cosmo = cosmologies.get("planck2018", rf, rf_dir)
    cosmo_fns = rf.background_evolution_splines(cosmo)
    experiment = {"nu_line": HI_REST_FREQUENCY_MHZ}
    hard = filter_scenarios.delay_cut(rf, experiment, cosmo_fns, 200e-9)
    soft = filter_scenarios.delay_transfer(rf, experiment, cosmo_fns, 200e-9)

    kpar_mask_edge = hard(1.16)                 # 0.351 h/Mpc: tau = 280 ns
    kpar = np.array([0.5, 1.0, 1.4, 3.0, 8.0]) / 1.4 * kpar_mask_edge
    transfer = soft(kpar, 1.16)

    assert transfer[0] == pytest.approx(0.0, abs=1e-6)   # 100 ns: filtered
    assert transfer[1] == pytest.approx(0.0, abs=1e-3)   # 200 ns: the cut
    assert transfer[2] == pytest.approx((0.756 / 0.870) ** 2, abs=0.05)
    assert transfer[3] > 0.9                     # 600 ns: near plateau
    assert transfer[4] == pytest.approx(1.0, abs=0.02)


# ------------------------------------------------ scenarios and the profile

def test_the_scenarios_are_the_four_worlds_in_their_order():
    assert [(s.name, s.bank, s.kfg_fac, s.suppression_key)
            for s in filter_scenarios.SCENARIOS] == [
        ("none", "fisher_bank_chime2022_pres_dense.npz", None, "none"),
        ("peak1", "fisher_bank_chime2022_pres_kfg22_dense.npz", 22.0,
         "bao_peak1"),
        ("peak2", "fisher_bank_chime2022_pres_kfg44_dense.npz", 44.0,
         "bao_peak2"),
        ("deployed", "fisher_bank_chime2022_pres_kfg80_dense.npz", 80.0,
         "aggressive_200ns"),
    ]


def test_the_suppression_is_the_literal_table():
    assert filter_scenarios.DELAY_SUPPRESSION_DB == {
        "none": 0.0, "aggressive_200ns": 11.4, "bao_peak2": 8.2,
        "bao_peak1": 3.6}
    assert [filter_scenarios.suppression_db(s.name)
            for s in filter_scenarios.SCENARIOS] == [0.0, 3.6, 8.2, 11.4]
    assert filter_scenarios.DEFAULT_DELAY_KEY == "none" \
        == policy.value("transfer.delay_suppression.default_key")
    with pytest.raises(KeyError, match="unknown filter scenario"):
        filter_scenarios.suppression_db("wedge")


def test_the_model_reads_the_register_values_the_profile_names():
    profile = model.load_profile(PROJECT)
    parameters = profile["parameters"]
    assert tuple(parameters["required"]) + tuple(parameters["reported"]) \
        == policy.value("archive_reference.three_worlds_parameters", PROJECT)
    assert tuple(parameters["required"]) == ("aperp", "apar")
    assert profile["register"] == model.REGISTER_KEYS
    assert profile["target_years"] == 1.0 and type(profile["target_years"]) \
        is float
    built = model.RadioFisherBAO(PROJECT)
    # The literals the profile stated before the register became their one
    # source (7b0067b), and the transfer closure g_sys = g_var = 1.
    assert built.year_grid == (1.0, 2.0, 3.0, 5.0, 8.0)
    assert built.time_fraction == 0.1
    assert built.maximum_tolerance_ratio == 1.2
    assert built.zeta == 1.0
    assert built.transfer_gains == {"systematic": 1.0, "variance": 1.0}
    for value in (built.zeta, built.time_fraction,
                  built.maximum_tolerance_ratio, *built.year_grid):
        assert type(value) is float
    for key, ident in model.REGISTER_KEYS.items():
        assert policy.load(PROJECT).decision(ident).side == "science", key
    for ident in model.REGISTER_IDS:
        assert ident in policy.load(PROJECT).decisions


def test_the_profile_gives_the_no_filter_scenario_the_rule_role():
    built = model.RadioFisherBAO(PROJECT)
    assert [(s.name, s.role, s.suppression_db, s.response_source)
            for s in built.scenarios] == [
        (s.name, "rule" if s.name == "none" else "sensitivity",
         filter_scenarios.suppression_db(s.name), s.bank)
        for s in filter_scenarios.SCENARIOS]


def _project_copy(tmp_path, profile):
    for name in policy.FILES:
        shutil.copy(PROJECT / name, tmp_path / name)
    (tmp_path / "science_model.yaml").write_text(yaml.safe_dump(profile))
    return tmp_path


@pytest.mark.parametrize("field,value,match", [
    ("kfg_fac", 40.0, "the forecast defines"),
    ("role", "rescue", "role must be one of"),
])
def test_a_profile_that_disagrees_with_the_forecast_is_refused(
        tmp_path, field, value, match):
    profile = yaml.safe_load((PROJECT / "science_model.yaml").read_text())
    profile["scenarios"][1][field] = value
    with pytest.raises(ValueError, match=match):
        model.RadioFisherBAO(_project_copy(tmp_path, profile))


@pytest.mark.parametrize("roles,suppression", [
    (("rule", "rule", "sensitivity", "sensitivity"), None),
    (("sensitivity",) * 4, None),
    (("sensitivity", "rule", "sensitivity", "sensitivity"), None),
])
def test_exactly_one_rule_scenario_without_suppression(tmp_path, roles,
                                                       suppression):
    profile = yaml.safe_load((PROJECT / "science_model.yaml").read_text())
    for entry, role in zip(profile["scenarios"], roles):
        entry["role"] = role
    with pytest.raises(ValueError, match="exactly one scenario"):
        model.RadioFisherBAO(_project_copy(tmp_path, profile))


@pytest.mark.parametrize("field,value,match", [
    ("register", {"zeta": "science.systematic_budget.primary_zeta"},
     "register must name"),
    ("r_reference", {"frame_seconds": 0.04194304}, "r_reference holds"),
    ("residual_shapes", [], "residual_shapes"),
    ("report_band_mhz", [608.0, 470.0], "report_band_mhz"),
    ("report_band_mhz", [470, 608], "report_band_mhz"),
])
def test_a_profile_with_a_malformed_field_is_refused(tmp_path, field, value,
                                                     match):
    profile = yaml.safe_load((PROJECT / "science_model.yaml").read_text())
    profile[field] = value
    with pytest.raises(ValueError, match=match):
        model.load_profile(_project_copy(tmp_path, profile))


def test_a_profile_of_another_adapter_is_refused(tmp_path):
    profile = yaml.safe_load((PROJECT / "science_model.yaml").read_text())
    profile["adapter"] = "another"
    with pytest.raises(ValueError, match="adapter"):
        model.load_profile(_project_copy(tmp_path, profile))
