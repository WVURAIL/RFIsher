"""The shipped table, and that one channel rebuilds to it."""
import json

import pytest

from rfisher import read_table
from rfisher.bands import channel, channels
from rfisher.table import CSV_COLUMNS, SCHEMA, row, write_table


def test_the_shipped_table_covers_every_channel():
    t = read_table()
    assert t["schema"] == SCHEMA
    assert [r["channel"] for r in t["channels"]] == [b.channel for b in channels()]
    for r in t["channels"]:
        assert r["a_tol"] == pytest.approx(1 / abs(r["response_dv"]))
        assert 0.01 < r["sigma_dv"] < 0.02
        assert all(0.015 < s < 0.03 for s in r["dilations"]["sigma"])


@pytest.mark.parametrize("number", [19])
def test_a_channel_rebuilds_to_the_shipped_row(number):
    shipped = next(r for r in read_table()["channels"] if r["channel"] == number)
    fresh = row(channel(number))
    for key in ("z_center", "sigma_dv", "response_dv", "a_tol"):
        assert fresh[key] == pytest.approx(shipped[key], rel=1e-6), key


def test_write_and_read(tmp_path):
    t = read_table()
    small = dict(t, channels=t["channels"][:2])
    js, cs = write_table(small, tmp_path)
    assert read_table(js) == json.loads(js.read_text())
    header, first = cs.read_text().splitlines()[:2]
    assert header.split(",") == CSV_COLUMNS and first.startswith("14,dtv,470.0,476.0,")


def test_a_foreign_file_is_refused(tmp_path):
    bad = tmp_path / "x.json"
    bad.write_text(json.dumps({"schema": "other"}))
    with pytest.raises(ValueError):
        read_table(bad)
