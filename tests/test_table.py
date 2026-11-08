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
    assert fresh["normalization"]["power_scale"] == pytest.approx(shipped["normalization"]["power_scale"], rel=1e-10)
    for key in ("z_center", "sigma_dv"):
        assert fresh[key] == pytest.approx(shipped[key], rel=1e-5), key
    # The two dilation responses partly cancel in D_V, which magnifies the small changes between
    # numpy and scipy builds in the relative D_V response. Each response is compared to 1e-4 of
    # the larger dilation response.
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


def test_a_row_with_a_template_and_a_target():
    from test_residual import doubled

    from rfisher import residual
    base, other = row(channel(19)), row(channel(19), template=doubled, target="aperp")
    assert "target" not in base and base["normalization"] is not None
    assert other["normalization"] is None
    assert other["residual"]["model"].endswith(":doubled") and base["residual"]["model"] == residual.MODEL
    assert other["response_dv"] == pytest.approx(2 * base["response_dv"], rel=1e-12)
    assert other["target"]["weights"] == {"aperp": 1.0}
    assert other["target"]["response"] == pytest.approx(2 * base["dilations"]["response"][0], rel=1e-12)


def test_the_table_records_only_options_that_differ(monkeypatch):
    import rfisher.table as module

    monkeypatch.setattr(module, "row", lambda band, **options: {"channel": band.channel})
    default = build_table([channel(19)], workers=1)
    assert "target" not in default["inputs"] and "telescope" not in default["inputs"]
    assert default["inputs"]["experiment"] == "CHIME (CHIME Overview), inter-cylinder baselines only"
    assert build_table([channel(19)], workers=1, target="fs8")["inputs"]["target"] == "fs8"


def test_an_unknown_telescope_is_refused():
    with pytest.raises(ValueError, match="telescope"):
        build_table([channel(19)], workers=1, telescope="nope")


def synthetic_backend(band, template, telescope):
    """A backend with a known answer: diagonal dilation errors of 0.02 and B on aperp only."""
    import numpy as np
    names = ["A", "s_NL", "aperp", "apar", "fs8", "bs8", "_Pres"]
    F = np.diag([1.0, 1.0, 2500.0, 2500.0, 1.0, 1.0, 0.0])
    F[2, 6] = F[6, 2] = 5e4
    return {"F": F, "names": names, "z_center": band.z_center, "normalization": None}


def test_another_backend_fills_the_row():
    r = row(channel(19), backend=synthetic_backend, target="aperp")
    assert r["dilations"]["bias_per_unit_a"] == pytest.approx([20.0, 0.0])
    assert r["target"]["response"] == pytest.approx(1000.0)
    assert r["z_center"] == channel(19).z_center and r["normalization"] is None
    t = build_table([channel(19)], workers=1, backend=synthetic_backend)
    assert t["inputs"]["backend"].endswith(":synthetic_backend")


def test_an_unknown_backend_is_refused():
    with pytest.raises(ValueError, match="backend"):
        build_table([channel(19)], workers=1, backend="nope")


@pytest.mark.parametrize("telescope", ["chord", "hirax", "kko", "gbo", "hcro"])
def test_other_telescopes_run(telescope):
    import math
    r = row(channel(19), telescope=telescope)
    assert r["sigma_dv"] > 0 and math.isfinite(r["a_tol"]) and r["a_tol"] > 0
    assert r["normalization"]["power_scale"] > 0
    t = build_table([channel(19)], workers=1, telescope=telescope)
    assert t["inputs"]["telescope"] == telescope and t["inputs"]["experiment"].endswith("all baselines")
