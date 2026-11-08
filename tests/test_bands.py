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


def test_a_band_file_replaces_the_dtv_channels(tmp_path):
    path = tmp_path / "bands.csv"
    path.write_text("channel,low_mhz,high_mhz\n1,600.0,610.0\n2,700.0,702.5\n")
    bands = channels(path)
    assert [(b.channel, b.low_mhz, b.high_mhz) for b in bands] == [(1, 600.0, 610.0), (2, 700.0, 702.5)]
    assert channel(2, path).z_max == pytest.approx(NU21_MHZ / 700.0 - 1)


@pytest.mark.parametrize("text, message", [
    ("channel,low_mhz\n1,600\n", "lacks the columns"),
    ("channel,low_mhz,high_mhz\n", "no channels"),
    ("channel,low_mhz,high_mhz\n1,600,606\n1,606,612\n", "repeats"),
    ("channel,low_mhz,high_mhz\n1,606,600\n", "low_mhz < high_mhz"),
    ("channel,low_mhz,high_mhz\n1,1420,1430\n", "low_mhz < high_mhz"),
])
def test_a_bad_band_file_is_refused(tmp_path, text, message):
    path = tmp_path / "bands.csv"
    path.write_text(text)
    with pytest.raises(ValueError, match=message):
        channels(path)
