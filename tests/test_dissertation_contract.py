"""The names the dissertation's forecast builders import.

``figure_src/data/price_of_six/build_price_of_six.py`` and
``figure_src/data/survey_times/build_survey_times.py`` in the dissertation
import these names; the dissertation CI does not check RFIsher out, so this is
where a rename or removal shows. No TeX is needed.
"""
from __future__ import annotations

import inspect
from pathlib import Path

import rfisher
from rfisher.forecast.radiofisher_bao import api, scenarios
from rfisher.forecast.radiofisher_bao.bank import experiments, resources
from rfisher.forecast.radiofisher_bao.legacy_masks import channel_edges


def test_the_builders_names_resolve():
    assert Path(rfisher.__file__).is_file()
    assert channel_edges(14) == (470.0, 476.0) and channel_edges(36) == (602.0, 608.0)
    assert experiments.DUTY_2019_PRACTICE == 0.152
    assert experiments.MEAN_CALENDAR_YEAR_HOURS == 8766.0 and experiments.OVERVIEW_ONSKY_YEAR_HOURS == 8760.0
    lo, hi = experiments.zbin_freq_range(1.0, 1.1)
    assert lo < hi
    assert Path(str(resources.bank_file(resources.DEFAULT_COSMOLOGY))).is_file()


def test_the_builders_call_signatures_hold():
    assert {"mask", "target"} <= set(inspect.signature(api.required_time).parameters)
    assert "bank" in inspect.signature(api.load).parameters
    band = scenarios.FrequencyBand("pilot_ch14", 470.0, 476.0)
    scenario = scenarios.Scenario("pilot_excluded", "All declared pilot bins excluded",
                          frequency_fractions={band: 1.0}, excise_threshold=1.0)
    assert scenario.frequency_fractions == {band: 1.0}
    assert scenarios.clean().name == "clean"
