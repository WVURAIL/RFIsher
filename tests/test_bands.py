import pytest

from rfisher.bands import NU21_MHZ, Band, channel, channels


def test_the_channel_list():
    bands = channels()
    assert [b.channel for b in bands] == list(range(14, 38))
    assert all(b.high_mhz - b.low_mhz == 6.0 for b in bands)
    assert [b.role for b in bands].count("control") == 1 and channel(37).role == "control"
    assert channel(14).low_mhz == 470.0 and channel(37).high_mhz == 614.0


def test_redshifts_follow_from_the_band_edges():
    b = Band(19, 500.0, 506.0)
    assert b.z_min == pytest.approx(NU21_MHZ / 506.0 - 1)
    assert b.z_max == pytest.approx(NU21_MHZ / 500.0 - 1)
    assert b.z_min < b.z_center < b.z_max


def test_unknown_channel():
    with pytest.raises(KeyError):
        channel(13)
