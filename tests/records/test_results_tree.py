"""The results-tree resolver: environment, local overlay, default; and how a
release manifest's recorded paths land on this machine."""
from __future__ import annotations

import json

from rfisher_results import results_tree as rt


def test_environment_wins(tmp_path, monkeypatch):
    monkeypatch.setenv(rt.ENV, str(tmp_path / "tree"))
    assert rt.out_dir(tmp_path / "absent.json") == tmp_path / "tree"


def test_local_overlay_then_the_ignored_scratch_default(tmp_path, monkeypatch):
    monkeypatch.delenv(rt.ENV, raising=False)
    local = tmp_path / "products.local.json"
    assert rt.out_dir(local) == rt.DEFAULT
    local.write_text(json.dumps({"out_dir": str(tmp_path / "tree")}))
    assert rt.out_dir(local) == tmp_path / "tree"
    local.write_text(json.dumps({"out_dir": "results/here"}))
    assert rt.out_dir(local) == rt.ROOT / "results" / "here"
    # the overlay rfisher.products reads, without an out_dir entry
    local.write_text(json.dumps({"channels": {}}))
    assert rt.out_dir(local) == rt.DEFAULT


def test_release_paths_keep_their_recorded_prefix(tmp_path):
    assert rt.release_path("out/forecast_completion_all_dtv_bins.json",
                           tmp_path) \
        == tmp_path / "forecast_completion_all_dtv_bins.json"
    assert rt.release_path(
        "out/forecast_completion_20260824_reconciliation/x.csv", tmp_path) \
        == tmp_path / "forecast_completion_20260824_reconciliation" / "x.csv"
    assert rt.release_path(
        "docs/forecast-completion-release-manifest.schema.json", tmp_path) \
        == rt.ROOT / "docs" / "forecast-completion-release-manifest.schema.json"


def test_present_needs_every_named_file(tmp_path):
    (tmp_path / "a.csv").write_text("x")
    assert rt.present("a.csv", out=tmp_path)
    assert not rt.present("a.csv", "b.csv", out=tmp_path)
