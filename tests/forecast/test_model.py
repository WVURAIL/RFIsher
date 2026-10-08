"""The RadioFisher BAO science model: bands to bins, and the Protocol."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from rfisher.forecast.radiofisher_bao import legacy_masks as channels
from rfisher.forecast.radiofisher_bao import model
from rfisher.forecast.radiofisher_bao.bank import experiments
from rfisher.forecast.radiofisher_bao.bank.physics import HI_REST_FREQUENCY_MHZ
from rfisher.science_model import ScienceModel

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "projects" / "chime_bao"
# The ``bins`` column of the frozen channel_tolerances.csv of the archive
# releases (author eras 2026-09-23 and no-split r2 2026-09-24, byte-equal).
FROZEN_BINS = {
    14: "11", 15: "11", 16: "11", 17: "10;11", 18: "10", 19: "10",
    20: "9;10", 21: "9", 22: "9", 23: "8;9", 24: "8", 25: "8", 26: "7;8",
    27: "7", 28: "7", 29: "7", 30: "6;7", 31: "6", 32: "6", 33: "6",
    34: "5;6", 35: "5", 36: "5",
}


@pytest.fixture(scope="module")
def science():
    return model.RadioFisherBAO(PROJECT)


def test_the_model_satisfies_the_science_model_protocol(science):
    assert isinstance(science, ScienceModel)


@pytest.mark.parametrize("channel", sorted(FROZEN_BINS))
def test_the_band_redshift_range_is_bit_equal_to_the_channel_one(channel):
    low, high = channels.channel_edges(channel)
    expected = (HI_REST_FREQUENCY_MHZ / high - 1.0, HI_REST_FREQUENCY_MHZ / low - 1.0)
    for edges in ((low, high), (int(low), int(high))):
        got = model.redshift_range(*edges)
        assert [value.hex() for value in got] \
            == [value.hex() for value in expected]


@pytest.mark.parametrize("channel", sorted(FROZEN_BINS))
def test_bins_and_coverage_are_the_frozen_ones(science, channel):
    low, high = channels.channel_edges(channel)
    bins, covered = science.bins_for_band(int(low), int(high))
    assert ";".join(str(b) for b in bins) == FROZEN_BINS[channel]
    assert covered


def test_a_band_beyond_the_bins_is_not_covered(science):
    bins, covered = science.bins_for_band(395.0, 410.0)
    assert bins == (14,) and not covered
    assert science.bins_for_band(900.0, 910.0) == ((), False)


def test_the_bins_are_the_experiment_bins_as_the_table_rounds_them(science):
    zs, _ = experiments.chime2022_zbins()
    bins = science.bins()
    assert [b.index for b in bins] == list(range(len(zs) - 1))
    assert [(b.low, b.high) for b in bins] == [
        (round(float(zs[i]), 4), round(float(zs[i + 1]), 4))
        for i in range(len(zs) - 1)]
    table = ROOT / "src/rfisher/data/tolerances/tolerance_T1yr.csv"
    with table.open(newline="") as fh:
        edges = {(int(r["bin_index"]), float(r["z_lo"]), float(r["z_hi"]))
                 for r in csv.DictReader(fh)}
    assert edges == {(b.index, b.low, b.high) for b in bins}


def test_the_model_opens_no_bank_until_a_response_is_asked(science,
                                                          monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("a bank was opened")

    monkeypatch.setattr(model, "load_response_bank", refuse)
    fresh = model.RadioFisherBAO(PROJECT)
    assert fresh.bins_for_band(584, 590) == ((6,), True)
    assert fresh.hours(1.0) == experiments.OVERVIEW_ONSKY_YEAR_HOURS
    with pytest.raises(AssertionError, match="a bank was opened"):
        fresh.load("none")


def test_an_undeclared_scenario_is_refused(science):
    with pytest.raises(KeyError, match="no scenario"):
        science.bank("wedge")
