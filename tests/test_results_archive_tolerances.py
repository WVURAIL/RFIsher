"""Per-channel tolerances: the published constants, checked against the ledger."""
from __future__ import annotations

import csv
import json
import math

import pytest

from rfisher import tolerances as published
from rfisher.channels import channel_z_range
from rfisher_results.archive import tolerances as tol
from rfisher_results.results_tree import out_dir


def _write_tree(root, apar_scale=2.0):
    root.mkdir(parents=True)
    ledger = {"ledgers": {tol.ESTIMATOR: {"bins": [
        {"bin_index": 5, "z_low": 1.3, "z_high": 1.4, "points": [
            {"parameters": {"aperp": {"accepted": True, "t1": {"r_tolerance": 0.040, "failure_reason": None},
                                      "t2": {"r_tolerance": 0.035, "failure_reason": None}},
                            "apar": {"t1": {"r_tolerance": 0.035 * apar_scale, "failure_reason": None}},
                            "fs8": {"t1": {"r_tolerance": 0.0016, "failure_reason": "unstable"}}}}]},
        {"bin_index": 6, "z_low": 1.4, "z_high": 1.5, "points": [
            {"parameters": {"aperp": {"t1": {"r_tolerance": 0.0156, "failure_reason": None}},
                            "apar": {"t1": {"r_tolerance": 0.0156 * apar_scale, "failure_reason": None}}}}]},
    ]}}}
    (root / tol.LEDGER_NAME).write_text(json.dumps(ledger))
    with (root / tol.MAPPING_NAME).open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["schema", "family", "channel", "overlap_bin_indices"])
        w.writerow(["x", "noise_shaped", "35", "5"])
        w.writerow(["x", "noise_shaped", "34", "5;6"])
        w.writerow(["x", "other_family", "34", "5"])
    return root


def test_constants_come_from_the_one_home_and_the_ledger_only_checks_alpha_par(tmp_path):
    rows = {r.channel: r for r in tol.channel_tolerances(_write_tree(tmp_path / "tree"), channels=(34, 35, 14))}
    for ch in (14, 34, 35):
        assert rows[ch].r_tol_aperp == published.TOL_APERP[ch]
        assert rows[ch].r_tol_dilation == rows[ch].r_tol_aperp
        assert (rows[ch].z_low, rows[ch].z_high) == channel_z_range(ch)
    assert rows[35].bins == (5,) and rows[35].apar_over_aperp_ledger == pytest.approx(2.0)
    assert rows[34].bins == (5, 6) and rows[34].apar_over_aperp_ledger == pytest.approx(2.0 * 0.0156 / 0.0156)
    assert rows[35].dilation_binding == "aperp" and rows[35].fs8_status == "published"
    assert rows[14].bins == () and math.isnan(rows[14].apar_over_aperp_ledger)
    assert rows[14].r_tol_fs8 == published.TOL_FS8[14] and rows[14].fs8_status == "published"
    assert "unchecked" in rows[14].dilation_binding
    out = tol.write_channel_tolerances(list(rows.values()), tmp_path / "t.csv")
    with out.open(newline="") as fh:
        back = list(csv.DictReader(fh))
    assert list(back[0]) == list(tol.COLUMNS)
    by = {int(r["channel"]): r for r in back}
    assert float(by[14]["r_tol_fs8"]) == published.TOL_FS8[14]
    assert by[35]["bins"] == "5" and float(by[35]["r_tol_dilation"]) == published.TOL_APERP[35]


def test_a_ledger_where_alpha_par_binds_is_flagged_for_review(tmp_path):
    rows = {r.channel: r for r in tol.channel_tolerances(_write_tree(tmp_path / "tree", apar_scale=0.5), channels=(35,))}
    assert rows[35].apar_over_aperp_ledger == pytest.approx(0.5)
    assert "review" in rows[35].dilation_binding


def test_without_a_ledger_the_constants_still_price_every_channel(tmp_path):
    rows = tol.channel_tolerances(tmp_path / "nothing-here")
    assert [r.channel for r in rows] == list(range(14, 37))
    assert all(math.isfinite(r.r_tol_dilation) for r in rows)
    assert sum(math.isfinite(r.r_tol_fs8) for r in rows) == len(published.TOL_FS8) == 23


@pytest.mark.skipif(not (out_dir() / tol.LEDGER_NAME).is_file(), reason="results tree not configured")
def test_on_the_frozen_ledger_alpha_perp_binds_below_z_1_9_and_the_top_bin_is_flagged():
    rows = {r.channel: r for r in tol.channel_tolerances()}
    assert all(r.bins for r in rows.values())
    for ch in range(17, 37):
        assert rows[ch].apar_over_aperp_ledger >= 2.0, (ch, rows[ch].apar_over_aperp_ledger)
        assert rows[ch].dilation_binding == "aperp"
    for ch in (14, 15, 16):                       # the ledger's alpha_perp entry there is an artefact (3.22)
        assert "review" in rows[ch].dilation_binding


def test_a_channel_with_no_published_growth_constant_is_still_reported_unpriced(tmp_path, monkeypatch):
    """The unpriced row survives the ch14-26 fill.

    rfisher.tolerances now prices f sigma_8 on all twenty-three channels, so
    no channel reaches this branch today; it is the behaviour that matters if
    a constant is ever withdrawn, and an untested branch would let a withdrawn
    channel be reported with a number from somewhere else instead of a blank
    cell and a stated reason.
    """
    monkeypatch.delitem(published.TOL_FS8, 14)
    rows = list(tol.channel_tolerances(tmp_path / "nothing-here", channels=(14,)))
    assert math.isnan(rows[0].r_tol_fs8) and rows[0].fs8_status == tol.FS8_UNPRICED
    out = tol.write_channel_tolerances(rows, tmp_path / "unpriced.csv")
    with out.open(newline="") as fh:
        assert list(csv.DictReader(fh))[0]["r_tol_fs8"] == ""
