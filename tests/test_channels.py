"""Merge provenance of product mask tables."""
import pytest

from rfisher import channels


# ---------------------------------------------------------------- merging
def _table(**kw):
    base = dict(fractions={14: 0.1}, source="csv", rule="r")
    base.update(kw)
    return channels.MaskTable(**base)


def test_merge_keeps_provenance():
    a = _table(fractions={14: 0.1}, epoch="e1", detector_version="d1",
               window="2020-01..2020-12")
    b = _table(fractions={15: 0.2}, epoch="e1", detector_version="d1",
               window="2020-01..2020-12")
    m = channels.merge_mask_tables(a, b)
    assert m.fractions == {14: 0.1, 15: 0.2}
    assert m.epoch == "e1"
    assert m.detector_version == "d1"
    assert m.window == "2020-01..2020-12"
    assert m.occupancy_valid


def test_merge_refuses_rule_mismatch():
    with pytest.raises(ValueError, match="different rules"):
        channels.merge_mask_tables(_table(rule="r1"), _table(rule="r2"))


def test_merge_refuses_epoch_mismatch():
    with pytest.raises(ValueError, match="epochs.*legacy"):
        channels.merge_mask_tables(_table(epoch="current"),
                              _table(epoch="legacy"))


def test_merge_refuses_detector_version_mismatch():
    with pytest.raises(ValueError, match="versions"):
        channels.merge_mask_tables(_table(detector_version="d1"),
                              _table(detector_version="d2"))


def test_merge_of_legacy_tables_stays_legacy():
    a = _table(fractions={14: 0.1}, epoch="legacy", occupancy_valid=False)
    b = _table(fractions={15: 0.2}, epoch="legacy", occupancy_valid=False)
    m = channels.merge_mask_tables(a, b)
    assert not m.occupancy_valid
    assert m.epoch == "legacy"


def test_merge_joins_differing_windows():
    a = _table(fractions={14: 0.1}, window="2020-01..2020-06")
    b = _table(fractions={15: 0.2}, window="2021-01..2021-06")
    m = channels.merge_mask_tables(a, b)
    assert "2020-01..2020-06" in m.window and "2021-01..2021-06" in m.window
