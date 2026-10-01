"""Channel validation and CSV rate-column weighting of the legacy mask inputs."""
import warnings

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


def test_channel_z_range_rejects_vhf():
    with pytest.raises(ValueError, match="channel 13"):
        channels.channel_z_range(13)


def test_scenario_rejects_non_atsc_channel():
    with pytest.raises(ValueError, match="channel 2"):
        scenarios.Scenario("bad", "bad", fractions={2: 0.5})


# ------------------------------------------------------------- CSV weights
def test_default_rate_column_weights_cleanly():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        fr = channels.legacy_rate_fractions()
    assert len(fr) == 23
    assert all(0.0 <= f <= 1.0 for f in fr.values())


def test_frb_rate_column_with_matching_weights():
    with pytest.warns(UserWarning, match="skipped 2 row"):
        fr = channels.legacy_rate_fractions(rate_col="hi_rate_frb",
                                       weight_col="n_frb_frames")
    assert set(fr) == set(channels.legacy_rate_fractions())
    assert all(0.0 <= f <= 1.0 for f in fr.values())
    # The FRB-window rates are a different statistic than the all-frame
    # rates; identical tables would mean the weighting silently ignored
    # the requested column.
    base = channels.legacy_rate_fractions()
    assert any(fr[ch] != base[ch] for ch in fr
               if ch not in channels.REFUSED_CHANNELS)


def test_frb_table_wraps_without_crashing():
    t = channels.legacy_rate_table(rate_col="hi_rate_frb",
                              weight_col="n_frb_frames")
    assert not t.occupancy_valid
    assert len(t.fractions) == 23
