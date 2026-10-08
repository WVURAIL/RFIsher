"""Channel validation of the ATSC channel plan."""
import pytest

from rfisher.forecast.radiofisher_bao import legacy_masks as channels
from rfisher.forecast.radiofisher_bao import scenarios


# ---------------------------------------------------------------- channels
def test_channel_edges_accepts_band_ends():
    assert channels.channel_edges(14) == (470.0, 476.0)
    assert channels.channel_edges(36) == (602.0, 608.0)


@pytest.mark.parametrize("ch", [2, 13, 45])
def test_channel_edges_rejects_outside_uhf(ch):
    with pytest.raises(ValueError, match=rf"channel {ch}\b.*14-36"):
        channels.channel_edges(ch)


def test_scenario_rejects_non_atsc_channel():
    with pytest.raises(ValueError, match="channel 2"):
        scenarios.Scenario("bad", "bad", fractions={2: 0.5})
