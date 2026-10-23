"""The shipped table, and that one channel rebuilds to it."""
import json

import pytest

from rfisher import read_table
from rfisher.bands import channel, channels
from rfisher.table import CSV_COLUMNS, SCHEMA, build_table, row, write_table


def test_the_shipped_table_covers_every_channel():
    t = read_table()
    assert t["schema"] == SCHEMA
    assert [r["channel"] for r in t["channels"]] == [b.channel for b in channels()]
    for r in t["channels"]:
        assert r["a_tol"] == pytest.approx(1 / abs(r["response_dv"]))
        assert 0.01 < r["sigma_dv"] < 0.02
        assert all(0.015 < s < 0.05 for s in r["dilations"]["sigma"])


@pytest.mark.parametrize("number", [19])
def test_a_channel_rebuilds_to_the_shipped_row(number):
    shipped = next(r for r in read_table()["channels"] if r["channel"] == number)
    fresh = row(channel(number))
    for key in ("z_center", "sigma_dv"):
        assert fresh[key] == pytest.approx(shipped[key], rel=1e-5), key
    # D_V partly cancels the two dilation responses, which magnifies build differences
    # in its relative value; hold it to 1e-4 of the larger dilation response instead.
    scale = max(abs(v) for v in shipped["dilations"]["response"])
    for fr, sh in zip(fresh["dilations"]["response"], shipped["dilations"]["response"]):
        assert abs(fr - sh) <= 1e-4 * scale
    assert abs(fresh["response_dv"] - shipped["response_dv"]) <= 1e-4 * scale


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


def test_empty_channel_selection_is_refused():
    with pytest.raises(ValueError, match="at least one"):
        build_table([])


def test_nonpositive_worker_count_is_refused():
    with pytest.raises(ValueError, match="workers"):
        build_table(workers=0)
