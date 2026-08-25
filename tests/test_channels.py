"""Channel validation, CSV rate-column weighting, and merge provenance."""
import warnings

import pytest

from rfisher import channels as chn
from rfisher import scenarios


# ---------------------------------------------------------------- channels
def test_channel_edges_accepts_band_ends():
    assert chn.channel_edges(14) == (470.0, 476.0)
    assert chn.channel_edges(36) == (602.0, 608.0)


@pytest.mark.parametrize("ch", [2, 13, 45])
def test_channel_edges_rejects_outside_uhf(ch):
    with pytest.raises(ValueError, match=rf"channel {ch}\b.*14-36"):
        chn.channel_edges(ch)


def test_channel_z_range_rejects_vhf():
    with pytest.raises(ValueError, match="channel 13"):
        chn.channel_z_range(13)


def test_scenario_rejects_non_atsc_channel():
    with pytest.raises(ValueError, match="channel 2"):
        scenarios.Scenario("bad", "bad", fractions={2: 0.5})


# ------------------------------------------------------------- CSV weights
def test_default_rate_column_weights_cleanly():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        fr = chn.legacy_rate_fractions()
    assert len(fr) == 23
    assert all(0.0 <= f <= 1.0 for f in fr.values())


def test_frb_rate_column_with_matching_weights():
    with pytest.warns(UserWarning, match="skipped 2 row"):
        fr = chn.legacy_rate_fractions(rate_col="hi_rate_frb",
                                       weight_col="n_frb_frames")
    assert set(fr) == set(chn.legacy_rate_fractions())
    assert all(0.0 <= f <= 1.0 for f in fr.values())
    # The FRB-window rates are a different statistic than the all-frame
    # rates; identical tables would mean the weighting silently ignored
    # the requested column.
    base = chn.legacy_rate_fractions()
    assert any(fr[ch] != base[ch] for ch in fr
               if ch not in chn.REFUSED_CHANNELS)


def test_frb_table_wraps_without_crashing():
    t = chn.legacy_rate_table(rate_col="hi_rate_frb",
                              weight_col="n_frb_frames")
    assert not t.occupancy_valid
    assert len(t.fractions) == 23


# ---------------------------------------------------------------- merging
def _table(**kw):
    base = dict(fractions={14: 0.1}, source="csv", rule="r")
    base.update(kw)
    return chn.MaskTable(**base)


def test_merge_keeps_provenance():
    a = _table(fractions={14: 0.1}, epoch="e1", detector_version="d1",
               window="2020-01..2020-12")
    b = _table(fractions={15: 0.2}, epoch="e1", detector_version="d1",
               window="2020-01..2020-12")
    m = chn.merge_mask_tables(a, b)
    assert m.fractions == {14: 0.1, 15: 0.2}
    assert m.epoch == "e1"
    assert m.detector_version == "d1"
    assert m.window == "2020-01..2020-12"
    assert m.occupancy_valid


def test_merge_refuses_rule_mismatch():
    with pytest.raises(ValueError, match="different rules"):
        chn.merge_mask_tables(_table(rule="r1"), _table(rule="r2"))


def test_merge_refuses_epoch_mismatch():
    with pytest.raises(ValueError, match="epochs.*legacy"):
        chn.merge_mask_tables(_table(epoch="current"),
                              _table(epoch="legacy"))


def test_merge_refuses_detector_version_mismatch():
    with pytest.raises(ValueError, match="versions"):
        chn.merge_mask_tables(_table(detector_version="d1"),
                              _table(detector_version="d2"))


def test_merge_of_legacy_tables_stays_legacy():
    a = _table(fractions={14: 0.1}, epoch="legacy", occupancy_valid=False)
    b = _table(fractions={15: 0.2}, epoch="legacy", occupancy_valid=False)
    m = chn.merge_mask_tables(a, b)
    assert not m.occupancy_valid
    assert m.epoch == "legacy"


def test_merge_joins_differing_windows():
    a = _table(fractions={14: 0.1}, window="2020-01..2020-06")
    b = _table(fractions={15: 0.2}, window="2021-01..2021-06")
    m = chn.merge_mask_tables(a, b)
    assert "2020-01..2020-06" in m.window and "2021-01..2021-06" in m.window
