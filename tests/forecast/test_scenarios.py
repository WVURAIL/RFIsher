import numpy as np
import pytest

from rfisher.forecast.radiofisher_bao import legacy_masks as channels
from rfisher.forecast.radiofisher_bao import scenarios
from rfisher.forecast.radiofisher_bao.bank.physics import HI_REST_FREQUENCY_MHZ

# A masked survey with an excised channel (30) and kept channels at several fractions.
MIXED = {17: 0.35, 24: 0.97, 30: 0.97, 31: 0.2, 32: 0.1, 36: 0.01}


def _mixed(mode="time"):
    return scenarios.Scenario("mixed", "Mixed masking", fractions=MIXED, mode=mode)


def test_channel_edges():
    assert channels.channel_edges(14) == (470.0, 476.0)
    assert channels.channel_edges(30) == (566.0, 572.0)
    lo, hi = channels.channel_edges(30)
    zlo, zhi = HI_REST_FREQUENCY_MHZ / hi - 1.0, HI_REST_FREQUENCY_MHZ / lo - 1.0
    assert 1.48 < zlo < 1.49 and 1.50 < zhi < 1.52


def test_clean_scenario():
    sc = scenarios.clean()
    v, w = sc.bin_factors(500.0, 530.0)
    assert v == 1.0 and w == 1.0


def test_uniform_time_mode():
    sc = scenarios.uniform(0.5, scenarios.DTV_BAND)
    # bin fully inside the DTV band
    v, w = sc.bin_factors(500.0, 530.0)
    assert v == pytest.approx(1.0)
    assert w == pytest.approx(0.5)
    # fourier convention agrees for uniform masking
    sc_f = scenarios.uniform(0.5, scenarios.DTV_BAND, mode="fourier")
    v2, w2 = sc_f.bin_factors(500.0, 530.0)
    assert w2 == pytest.approx(0.5)


@pytest.mark.parametrize("factory", [
    lambda mode: scenarios.uniform(0.5, scenarios.DTV_BAND, mode=mode),
    lambda mode: scenarios.single_channel(30, 0.97, keep=True, mode=mode),
])
def test_fourier_factory_identity_is_distinct(factory):
    time = factory("time")
    fourier = factory("fourier")
    assert fourier.name == f"{time.name}_fourier"
    assert fourier.label == f"{time.label} (Fourier weighting)"


def test_uniform_outside_dtv_band():
    sc = scenarios.uniform(0.5, scenarios.DTV_BAND)
    v, w = sc.bin_factors(410.0, 440.0)   # below 470 MHz: clean
    assert v == 1.0 and w == 1.0


def test_excision_costs_volume_not_noise():
    sc = scenarios.Scenario("t", "t", fractions={30: 0.97},
                            excise_threshold=0.5)
    # 24.8 MHz bin containing ch30's 566-572 slice
    v, w = sc.bin_factors(566.6, 591.4)
    assert v == pytest.approx((591.4 - 566.6 - 5.4) / (591.4 - 566.6))
    assert w == pytest.approx(1.0)


def test_kept_channel_costs_time():
    sc = scenarios.Scenario("t", "t", fractions={30: 0.97},
                            excise_threshold=scenarios.NO_EXCISION_THRESHOLD)
    width = 591.4 - 566.6
    ov = 572.0 - 566.6
    v, w = sc.bin_factors(566.6, 591.4)
    assert v == pytest.approx(1.0)
    expected = ((width - ov) + ov * 0.03) / width
    assert w == pytest.approx(expected)
    # fourier convention is much harsher
    sc_f = scenarios.Scenario("t", "t", fractions={30: 0.97},
                              excise_threshold=scenarios.NO_EXCISION_THRESHOLD,
                              mode="fourier")
    _, wf = sc_f.bin_factors(566.6, 591.4)
    assert wf == pytest.approx(width / ((width - ov) + ov / 0.03))
    assert wf < 0.2


def test_zbin_factor_array_shape():
    zs = np.array([0.78, 0.88, 0.98])
    fac = _mixed().bin_factors_for_zbins(zs)
    assert fac.shape == (2, 2)


def test_freq_weight_fn_matches_radiofisher_hook_semantics():
    sc = _mixed()
    w = sc.freq_weight_fn()
    # outside any DTV channel: clean
    assert w(450.0)[0] == 1.0 and w(700.0)[0] == 1.0
    # inside refused ch30 (566-572): excised -> NaN
    assert np.isnan(w(569.0)[0])
    # inside a kept channel: 1 - f
    f36 = sc.fractions[36]
    lo, _ = channels.channel_edges(36)
    assert w(lo + 3.0)[0] == pytest.approx(1.0 - f36)
    # vectorised call preserves shape
    nu = np.linspace(400.0, 800.0, 1001)
    assert w(nu).shape == nu.shape
    assert sc.rf_mode() == "invvar"
    assert _mixed(mode="fourier").rf_mode() == "fourier"


def test_hook_band_average_equals_bin_factors():
    """The uniform-sampled band average RadioFisher's hook computes must
    reproduce Scenario.bin_factors' piecewise-exact w_bar."""
    sc = _mixed()
    w = sc.freq_weight_fn()
    nu_lo, nu_hi = 566.6, 591.4        # representative ch30-overlap bin
    nn = np.linspace(nu_lo, nu_hi, 200001)
    ww = w(nn)
    surviving = np.isfinite(ww)
    v_frac, w_bar = sc.bin_factors(nu_lo, nu_hi)
    assert surviving.mean() == pytest.approx(v_frac, abs=2e-4)
    assert np.mean(ww[surviving]) == pytest.approx(w_bar, abs=2e-4)


def test_api_scenario_from():
    from rfisher.forecast.radiofisher_bao import api
    sc = api.scenario_from(mask={30: 0.97, 17: 0.33})
    v, w = sc.bin_factors(566.6, 591.4)
    assert v < 1.0 and w == 1.0      # ch30 excised, ch17 outside this bin
    sc2 = api.scenario_from(uniform=0.5)
    assert sc2.excise_threshold == scenarios.NO_EXCISION_THRESHOLD
    assert sc2.bin_factors(500.0, 530.0)[1] == pytest.approx(0.5)
    # An explicit threshold is applied rather than silently ignored.
    sc3 = api.scenario_from(uniform=0.5, excise_threshold=0.5)
    assert sc3.bin_factors(500.0, 530.0) == pytest.approx((0.0, 1.0))
    with pytest.raises(ValueError):
        api.scenario_from()


@pytest.mark.parametrize("fractions", [
    {30: -0.01}, {30: 1.01}, {30: np.nan}, {30: np.inf},
])
def test_scenario_rejects_invalid_masked_fractions(fractions):
    with pytest.raises(ValueError, match=r"fractions\[30\].*\[0, 1\]"):
        scenarios.Scenario("bad", "bad", fractions=fractions)


@pytest.mark.parametrize("residuals", [
    {30: -0.01}, {30: np.nan}, {30: np.inf},
])
def test_scenario_rejects_invalid_residuals(residuals):
    with pytest.raises(ValueError, match=r"residuals\[30\].*non-negative"):
        scenarios.Scenario("bad", "bad", residuals=residuals)


@pytest.mark.parametrize("mode", ["invvar", "Time", "", None, []])
def test_scenario_rejects_unknown_modes(mode):
    with pytest.raises(ValueError, match="mode must be one of"):
        scenarios.Scenario("bad", "bad", mode=mode)


@pytest.mark.parametrize("threshold", [-0.01, np.nan, -np.inf])
def test_scenario_rejects_invalid_mask_excision_thresholds(threshold):
    with pytest.raises(ValueError, match="excise_threshold"):
        scenarios.Scenario("bad", "bad", excise_threshold=threshold)


def test_threshold_above_one_disables_excision():
    sc = scenarios.Scenario(
        "kept", "kept", fractions={30: 1.0}, excise_threshold=1.01)
    assert not sc.is_excised(30)
    assert sc.excise_threshold == pytest.approx(1.01)


@pytest.mark.parametrize("threshold", [-0.01, np.nan, -np.inf])
def test_scenario_rejects_invalid_residual_excision_thresholds(threshold):
    with pytest.raises(ValueError, match="residual_excise_threshold"):
        scenarios.Scenario(
            "bad", "bad", residual_excise_threshold=threshold)


def test_scenario_copies_and_normalises_inputs():
    fractions = {np.int64(30): np.float64(0.25)}
    residuals = {np.int64(30): np.float64(0.5)}
    sc = scenarios.Scenario(
        "ok", "ok", fractions=fractions, residuals=residuals)
    fractions[30] = 0.75
    residuals[30] = 1.0
    assert sc.fractions == {30: 0.25}
    assert sc.residuals == {30: 0.5}


def test_api_uniform_residual_mapping_is_validated_at_construction():
    from rfisher.forecast.radiofisher_bao import api

    with pytest.raises(ValueError, match="channel-specific"):
        api.scenario_from(uniform=0.2, residuals={30: np.nan})


@pytest.mark.parametrize("residual", [-0.1, np.nan, np.inf, True])
def test_api_rejects_invalid_uniform_residual(residual):
    from rfisher.forecast.radiofisher_bao import api

    with pytest.raises(ValueError, match="residual"):
        api.scenario_from(uniform=0.2, residual=residual)


def test_uniform_excision_policies_are_explicit():
    kept = scenarios.uniform(0.8)
    thresholded = scenarios.uniform(0.8, excise_threshold=0.5)
    assert not kept.is_band_excised(scenarios.DTV_BAND)
    assert thresholded.is_band_excised(scenarios.DTV_BAND)
    with pytest.raises(TypeError, match="unexpected keyword argument 'excise'"):
        scenarios.uniform(0.8, excise=True)


def test_full_chime_band_is_a_physical_frequency_interval():
    sc = scenarios.uniform(0.5, scenarios.CHIME_BAND)
    assert sc.fractions == {}
    assert sc.frequency_fractions == {scenarios.CHIME_BAND: 0.5}
    assert sc.name == "uniform50_chime"
    assert sc.label == "50% masked, CHIME band"
    assert sc.bin_factors(400.0, 800.0) == pytest.approx((1.0, 0.5))
    weight = sc.freq_weight_fn()
    assert weight(399.0)[0] == pytest.approx(1.0)
    assert weight(500.0)[0] == pytest.approx(0.5)


def test_uniform_rejects_string_band_aliases():
    with pytest.raises(ValueError, match="FrequencyBand"):
        scenarios.uniform(0.5, band="dtv")


def test_uniform_label_reflects_residual_excision_policy():
    sc = scenarios.uniform(
        0.2, residual=2.0, residual_excise_threshold=1.0)
    assert sc.is_band_excised(scenarios.DTV_BAND)
    assert "excised" in sc.label
    assert "r=2" in sc.label


def test_frequency_band_rejects_invalid_edges():
    with pytest.raises(ValueError, match="frequency-band edges"):
        scenarios.FrequencyBand("bad", 800.0, 400.0)


def test_frequency_band_separates_slug_and_display_label():
    assert scenarios.DTV_BAND.name == "dtv"
    assert scenarios.DTV_BAND.label == "DTV"
    assert scenarios.uniform(0.5).label == "50% masked, DTV band"
    same_band = scenarios.FrequencyBand("dtv", 470.0, 608.0)
    assert same_band == scenarios.DTV_BAND
    defaulted = scenarios.FrequencyBand("n71", 617.0, 652.0)
    assert defaulted.label == "n71"
    labeled = scenarios.FrequencyBand(
        "n71", 617.0, 652.0, label="5G n71 downlink")
    sc = scenarios.uniform(0.5, labeled)
    assert sc.name == "uniform50_n71"
    assert sc.label == "50% masked, 5G n71 downlink band"


@pytest.mark.parametrize("label", ["", " DTV", "DTV ", 7])
def test_frequency_band_rejects_invalid_display_labels(label):
    with pytest.raises(ValueError, match="frequency-band label"):
        scenarios.FrequencyBand("dtv", 470.0, 608.0, label=label)


def test_channel_and_frequency_band_masks_must_not_overlap():
    with pytest.raises(ValueError, match="must not overlap"):
        scenarios.Scenario(
            "bad", "bad", fractions={30: 0.2},
            frequency_fractions={scenarios.DTV_BAND: 0.2})
