"""Survey-adapter contracts that bridge RFIsher to RadioFisher's public API."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from rfisher import resources, survey


def test_bull_redshift_bins_use_supported_backend_helper_directly():
    experiment = {"survey_numax": 800.0, "survey_dnutot": 400.0}
    seen = {}

    class Backend:
        @staticmethod
        def zbins_equal_spaced(expt, *, dz):
            seen.update(expt=expt, dz=dz)
            return [0.8, 0.9, 1.0], [0.85, 0.95]

    edges, centers = survey.chime_zbins(Backend(), experiment, dz=0.1)

    assert seen == {"expt": experiment, "dz": 0.1}
    assert np.array_equal(edges, [0.8, 0.9, 1.0])
    assert np.array_equal(centers, [0.85, 0.95])


def test_bull_experiment_ignores_radiofisher_root_array_config(tmp_path):
    stale = tmp_path / "array_config" / "nx_CHIME_800.dat"
    stale.parent.mkdir()
    stale.write_text("historical checkout data")
    backend = SimpleNamespace(
        experiments=SimpleNamespace(
            CHIME={"n(x)": "array_config/nx_CHIME_800.dat"}))

    experiment = survey.chime_experiment(backend, tmp_path)

    expected = resources.filesystem_data_file(
        resources.SYNTHETIC_BASELINE_NAME)
    assert Path(experiment["n(x)"]).resolve() == expected.resolve()
    assert Path(experiment["n(x)"]).resolve() != stale.resolve()


def test_recorded_bull_experiment_restores_foregrounds_and_overrides(
        monkeypatch, tmp_path):
    baseline = tmp_path / "nx.dat"
    baseline.write_text("baseline")
    seen = []

    def make_experiment(_rf, _rf_dir, ttot_hours, epsilon_fg, k_nl0):
        seen.append((ttot_hours, epsilon_fg, k_nl0))
        return {
            "ttot": ttot_hours * survey.HRS_MHZ,
            "epsilon_fg": epsilon_fg,
            "k_nl0": k_nl0,
            "n(x)": str(baseline),
        }

    monkeypatch.setattr(survey, "chime_experiment", make_experiment)
    meta = {
        "config": "bull2015",
        "expt_overrides": {"kfg_fac": 80.0},
        "provenance": {"experiment": {"settings": {
            "ttot": survey.HRS_MHZ,
            "epsilon_fg": 1e-5,
            "k_nl0": 0.2,
            "kfg_fac": 80.0,
            "n(x)": baseline.name,
        }}},
    }

    experiment = survey.experiment_from_bank_metadata(
        object(), tmp_path, meta, ttot_hours=25.0)

    assert seen == [(1.0, 1e-5, 0.2), (25.0, 1e-5, 0.2)]
    assert experiment["ttot"] == 25.0 * survey.HRS_MHZ
    assert experiment["kfg_fac"] == 80.0


def test_recorded_overview_experiment_restores_kfg_override(monkeypatch, tmp_path):
    baseline = tmp_path / "chime2021" / "array_config" / "nx.dat"
    baseline.parent.mkdir(parents=True)
    baseline.write_text("baseline")

    def make_experiment(_rf, _rf_dir, ttot_hours):
        return {
            "ttot": ttot_hours * survey.HRS_MHZ,
            "epsilon_fg": 0.0,
            "k_nl0": 0.14,
            "n(x)": str(baseline),
        }

    monkeypatch.setattr(survey, "chime2022_experiment", make_experiment)
    meta = {
        "config": "chime2022",
        "expt_overrides": {"kfg_fac": 44.0},
        "provenance": {"experiment": {"settings": {
            "ttot": survey.HRS_MHZ,
            "epsilon_fg": 0.0,
            "k_nl0": 0.14,
            "kfg_fac": 44.0,
            "n(x)": "chime2021/array_config/nx.dat",
        }}},
    }

    experiment = survey.experiment_from_bank_metadata(
        object(), tmp_path, meta, ttot_hours=12.0)

    assert experiment["ttot"] == 12.0 * survey.HRS_MHZ
    assert experiment["kfg_fac"] == 44.0


def test_recorded_experiment_fails_closed_on_unexplained_setting_drift(
        monkeypatch, tmp_path):
    monkeypatch.setattr(
        survey, "chime2022_experiment",
        lambda _rf, _rf_dir, ttot_hours: {
            "ttot": ttot_hours * survey.HRS_MHZ, "epsilon_fg": 0.0})
    meta = {
        "config": "chime2022", "expt_overrides": {},
        "provenance": {"experiment": {"settings": {
            "ttot": survey.HRS_MHZ, "epsilon_fg": 1e-5}}},
    }

    with np.testing.assert_raises_regex(ValueError, "cannot be reconstructed"):
        survey.experiment_from_bank_metadata(
            object(), tmp_path, meta, ttot_hours=1.0)



# ---------------------------------------------- CHIME 2025 / archive configs
def test_chime2025_experiment_overrides_only_field_band_and_time(monkeypatch):
    """The published-detection configuration is the Overview instrument
    pointed at a smaller field for less time; nothing else moves."""
    seen = {}

    def fake_chime2022(rf, rf_dir, ttot_hours=None):
        seen["ttot_hours"] = ttot_hours
        return {"Sarea": 9.44314001338921, "survey_numax": 800.0,
                "survey_dnutot": 400.0, "nu_line": 1420.406, "k_nl0": 0.14,
                "epsilon_fg": 0, "Ndish": 1024, "dnu": 0.390,
                "Tsys_tot(z)": lambda z: 55e3}

    monkeypatch.setattr(survey, "chime2022_experiment", fake_chime2022)
    experiment = survey.chime2025_experiment(object(), "/nonexistent")

    assert seen["ttot_hours"] == survey.CHIME2025_TTOT_HOURS == 385.0
    assert experiment["survey_numax"] == survey.CHIME2025_NUMAX_MHZ == 707.8
    assert experiment["survey_dnutot"] == pytest.approx(99.6)
    assert experiment["Sarea"] == pytest.approx(2200.0 * (np.pi / 180.0) ** 2)
    # Instrument, foregrounds and non-linear cutoff are the Overview's.
    assert experiment["k_nl0"] == 0.14
    assert experiment["epsilon_fg"] == 0
    assert experiment["Ndish"] == 1024
    assert experiment["Tsys_tot(z)"](1.16) == 55e3


def test_published_band_is_three_bins_of_dz_about_one_tenth():
    lo = survey.HI_REST_FREQUENCY_MHZ / survey.CHIME2025_NUMAX_MHZ - 1.0
    hi = survey.HI_REST_FREQUENCY_MHZ / survey.CHIME2025_NUMIN_MHZ - 1.0

    assert lo == pytest.approx(1.0068, abs=1e-4)
    assert hi == pytest.approx(1.3354, abs=1e-4)
    assert (hi - lo) / survey.CHIME2025_NZBINS == pytest.approx(0.1095,
                                                               abs=5e-4)
    # The band brackets the redshift the published k_par floor is quoted at.
    assert lo < survey.CHIME2025_Z_REFERENCE < hi


def test_chime2025_zbins_split_the_band_rather_than_tiling_from_its_edge():
    seen = {}

    class Backend:
        @staticmethod
        def zbins_equal_spaced(expt, *, bins):
            seen.update(expt=expt, bins=bins)
            return [1.0, 1.1, 1.2, 1.3], [1.05, 1.15, 1.25]

    edges, centers = survey.chime2025_zbins(Backend(), {"band": "published"})

    assert seen == {"expt": {"band": "published"}, "bins": 3}
    assert np.array_equal(edges, [1.0, 1.1, 1.2, 1.3])
    assert np.array_equal(centers, [1.05, 1.15, 1.25])


def test_archive_hours_is_seven_calendar_years_at_the_2019_duty_cycle():
    hours = survey.archive_hours()

    assert hours == pytest.approx(
        survey.ARCHIVE_CALENDAR_YEARS * survey.MEAN_CALENDAR_YEAR_HOURS
        * survey.DUTY_2019_PRACTICE)
    assert hours == pytest.approx(9327.0, abs=1.0)
    # The headline the caption quotes: 1.06 Overview on-sky years.
    assert hours / survey.OVERVIEW_ONSKY_YEAR_HOURS == pytest.approx(
        1.06, abs=5e-3)
    assert survey.archive_hours(years=1.0, duty=1.0) == pytest.approx(
        survey.MEAN_CALENDAR_YEAR_HOURS)


def _radiofisher_backend():
    from rfisher.backend import find_radiofisher_dir, import_radiofisher
    try:
        find_radiofisher_dir()
    except FileNotFoundError:
        pytest.skip("delay-cut binding requires a RadioFisher checkout")
    return import_radiofisher()


def test_delay_cut_reproduces_the_published_kpar_floor():
    """200 ns filter + 280 ns mask = 0.35 h/Mpc at z = 1.16, which is where
    the published auto-spectrum measurement begins."""
    from rfisher import cosmologies

    rf, rf_dir = _radiofisher_backend()
    cosmo = cosmologies.get("planck2018", rf, rf_dir)
    cosmo_fns = rf.background_evolution_splines(cosmo)
    experiment = {"nu_line": survey.HI_REST_FREQUENCY_MHZ}

    kpar_min_fn = survey.delay_cut(rf, experiment, cosmo_fns, 200e-9)

    kpar_min = kpar_min_fn(survey.CHIME2025_Z_REFERENCE)
    assert kpar_min / cosmo["h"] == pytest.approx(0.351, abs=5e-4)
    # A zero cut is a valid no-op so the no-cut reference runs the same path.
    assert survey.delay_cut(rf, experiment, cosmo_fns, 0.0)(1.16) == 0.0
    # Linear in the delay, and the transition factor is separable.
    assert survey.delay_cut(rf, experiment, cosmo_fns, 100e-9)(1.16) \
        == pytest.approx(0.5 * kpar_min)
    assert survey.delay_cut(
        rf, experiment, cosmo_fns, 280e-9, transition=1.0)(1.16) \
        == pytest.approx(kpar_min)


def test_delay_cut_rejects_a_negative_delay():
    rf, rf_dir = _radiofisher_backend()
    from rfisher import cosmologies
    cosmo_fns = rf.background_evolution_splines(
        cosmologies.get("planck2018", rf, rf_dir))

    with pytest.raises(ValueError, match="tau_cut_seconds"):
        survey.delay_cut(rf, {"nu_line": survey.HI_REST_FREQUENCY_MHZ},
                         cosmo_fns, -1e-9)


# ------------------------------------------------- accepted-sky archive
def test_accepted_sky_is_the_declination_band_within_y_of_0p4():
    """|y| < 0.4 is |sin za_NS| < 0.4: 23.6 deg either side of CHIME's
    latitude, 25.7-72.9 deg in declination, about 10,760 deg^2."""
    area = survey.accepted_sky_area_deg2()

    half = np.degrees(np.arcsin(0.4))
    lo, hi = survey.CHIME_LATITUDE_DEG - half, survey.CHIME_LATITUDE_DEG + half
    assert (lo, hi) == pytest.approx((25.74, 72.90), abs=0.01)
    expected = (2.0 * np.pi * (np.sin(np.radians(hi)) - np.sin(np.radians(lo)))
                * (180.0 / np.pi) ** 2)
    assert area == pytest.approx(expected)
    assert 10_700.0 < area < 10_800.0
    # A third of the Overview sky, which is the number the caption quotes.
    assert area / survey.OVERVIEW_SAREA_DEG2 == pytest.approx(0.347, abs=2e-3)


def test_accepted_sky_area_clips_at_the_pole_and_rejects_bad_sines():
    # From a pole-adjacent site the band cannot extend past +90 deg.
    polar = survey.accepted_sky_area_deg2(y_max=0.4, latitude_deg=80.0)
    assert polar < survey.accepted_sky_area_deg2(y_max=0.4, latitude_deg=0.0)
    with pytest.raises(ValueError):
        survey.accepted_sky_area_deg2(y_max=1.5)
    with pytest.raises(ValueError):
        survey.accepted_sky_area_deg2(y_max=0.0)


def test_accepted_archive_holds_per_voxel_depth_fixed(monkeypatch):
    """A declination cut loses volume, not depth: Sarea / t_tot -- the
    combination RadioFisher's thermal noise depends on -- must be the
    same for the accepted-sky archive as for the full-sky one."""
    seen = []

    def fake_chime2022(rf, rf_dir, ttot_hours=None):
        seen.append(ttot_hours)
        return {"Sarea": survey.OVERVIEW_SAREA_DEG2 / survey.DEG2_PER_SR,
                "ttot": ttot_hours * survey.HRS_MHZ,
                "survey_numax": 800.0, "survey_dnutot": 400.0}

    monkeypatch.setattr(survey, "chime2022_experiment", fake_chime2022)
    full = survey.chime2022_experiment(None, None,
                                       ttot_hours=survey.archive_hours())
    accepted = survey.archive_accepted_experiment(None, None)

    assert seen[-1] == pytest.approx(survey.accepted_archive_hours())
    assert accepted["Sarea"] * survey.DEG2_PER_SR == pytest.approx(
        survey.accepted_sky_area_deg2())
    assert accepted["Sarea"] / accepted["ttot"] == pytest.approx(
        full["Sarea"] / full["ttot"])
    # Band untouched; only the field and the time scale with it.
    assert accepted["survey_numax"] == 800.0
    assert accepted["survey_dnutot"] == 400.0
    assert survey.accepted_archive_hours() == pytest.approx(3236.0, abs=1.0)
