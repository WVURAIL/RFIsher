"""Dissertation rendering checks for the all-template forecast assets."""
from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

import matplotlib
import pytest

from rfisher_results import results_tree


FIGURE_TOOLCHAIN = ("latex", "dvipng", "kpsewhich", "pdffonts", "pdfinfo")
_MISSING_TOOLS = [t for t in FIGURE_TOOLCHAIN if shutil.which(t) is None]
# The renderer fails closed rather than substituting a non-Latin-Modern font,
# so the audit only runs where the TeX and Poppler toolchain is installed.
requires_figure_toolchain = pytest.mark.skipif(
    bool(_MISSING_TOOLS),
    reason="dissertation figure audit needs: " + ", ".join(_MISSING_TOOLS))
requires_release_renderer = pytest.mark.skipif(
    matplotlib.__version__ != "3.11.1",
    reason="frozen release assets require Matplotlib 3.11.1")
SUBSET_TAG = re.compile(r"^[A-Z]{6}\+")
ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "rfisher_test_render_forecast_template_assets",
    ROOT / "scripts" / "render_forecast_template_assets.py")
assert SPEC is not None and SPEC.loader is not None
renderer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(renderer)
OUT = results_tree.out_dir()
DATED_RELEASE = OUT / "forecast_completion_20260824_reconciliation"
requires_results_tree = pytest.mark.skipif(
    not (DATED_RELEASE / "forecast_completion_release_manifest.json").is_file(),
    reason=f"forecast-completion releases not found under {OUT}; "
           "point RFISHER_OUT at the results tree")
# The repository keeps each release's manifest; the artifacts it names live in
# the results tree at the paths the manifest recorded when out/ was tracked.
KEPT_MANIFESTS = {
    "first": (
        results_tree.RELEASE_MANIFESTS
        / "forecast_completion_first_release.manifest.json",
        OUT / "forecast_completion_release_manifest.json"),
    "reconciliation": (
        results_tree.RELEASE_MANIFESTS
        / "forecast_completion_20260824_reconciliation.manifest.json",
        DATED_RELEASE / "forecast_completion_release_manifest.json"),
}


@requires_figure_toolchain
@requires_results_tree
def test_renderer_exports_figure_table_and_complete_caption(tmp_path):
    figure = tmp_path / "comparison.png"
    table = tmp_path / "summary.tex"
    caption = tmp_path / "caption.txt"
    manifest = tmp_path / "manifest.json"
    argv = [
        "--comparison",
        str(OUT / "forecast_completion_template_comparison.csv"),
        "--channels",
        str(OUT / "forecast_completion_channel_mapping.csv"),
        "--status",
        str(OUT / "forecast_completion_template_status.csv"),
        "--figure", str(figure),
        "--table", str(table),
        "--caption", str(caption),
        "--manifest", str(manifest),
    ]
    assert renderer.main(argv) == 0

    assert figure.stat().st_size > 20_000
    assert figure.with_suffix(".pdf").stat().st_size > 10_000
    fonts = subprocess.run(
        ["pdffonts", str(figure.with_suffix(".pdf"))], check=True,
        capture_output=True, text=True).stdout
    assert "Type 3" not in fonts
    assert "STIX" not in fonts
    assert "DejaVu" not in fonts
    assert "Cmr10" not in fonts
    font_rows = [line.split() for line in fonts.splitlines()[2:] if line.strip()]
    assert font_rows
    assert all(SUBSET_TAG.sub("", row[0]).startswith("LM")
               and row[1:3] == ["Type", "1"]
               and row[4] == "yes" for row in font_rows)
    info = subprocess.run(
        ["pdfinfo", str(figure.with_suffix(".pdf"))], check=True,
        capture_output=True, text=True).stdout
    assert "CreationDate:" not in info
    assert "ModDate:" not in info
    tex = table.read_text(encoding="utf-8")
    assert "13/8" in tex
    assert "15/6" in tex
    assert "42/21" in tex
    assert "40/23" in tex
    assert "39/24" in tex
    assert "sensitivity-envelope ordering only" in tex
    assert all(line.endswith(r"\\") for line in tex.splitlines()
               if any(label in line for label in (
                   "Noise-shaped unit", "Low-$k_", "Wedge-like",
                   "Localized $k$ shell")))
    text = caption.read_text(encoding="utf-8")
    assert "not an overlap-weighted average" in text
    assert "data-dependent and incomplete" in text
    release = json.loads(manifest.read_text(encoding="utf-8"))
    assert release["schema"] == renderer.MANIFEST_SCHEMA
    assert release["artifact_count"] == 12
    assert release["wall_clock_fields_included"] is False
    assert release["absolute_paths_included"] is False
    assert all(not item["path"].startswith("/")
               for item in release["artifacts"])
    assert len(release["empirical_template_refusals"]) == 3
    assert release["scientific_scope"]["physical_channels"] \
        == list(range(14, 37))
    identities = release["scientific_identities"]
    assert identities["all_build_evaluation_pairs_verified_equal"] is True
    assert identities["baonoise"]["working_tree_sha256"] \
        == "ae448067c9eaf60d2dde3e0d7a57110db41759a62f2ee89e7ac4c9072e13e1a3"
    assert identities["radiofisher"]["clean_git_commit"] \
        == "3cc9f34e183db9e04820c8a2e7932395ec3a0441"
    assert len(identities["per_evidence"]) == 4
    assert release["figure_rendering"] == {
        "font_contract": "T1 Latin Modern via LaTeX",
        "all_fonts_embedded_type1": True,
        "font_names": release["figure_rendering"]["font_names"],
        "creation_modification_dates_included": False,
    }
    assert all(name.startswith("LM")
               for name in release["figure_rendering"]["font_names"])
    assert release["figure_rendering"]["font_names"] \
        == sorted({SUBSET_TAG.sub("", row[0]) for row in font_rows})
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(renderer.MANIFEST_SCHEMA_PATH.read_text(
        encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(release)

    expected_bytes = {
        output: output.read_bytes()
        for output in (figure, figure.with_suffix(".pdf"), table, caption,
                       manifest)
    }
    assert renderer.main(argv) == 0
    assert all(output.read_bytes() == content
               for output, content in expected_bytes.items())


@requires_results_tree
def test_aggregate_retains_exact_disposition_counts():
    comparisons = renderer._read_rows(
        OUT / "forecast_completion_template_comparison.csv",
        renderer.COMPARISON_SCHEMA)
    channels = renderer._read_rows(
        OUT / "forecast_completion_channel_mapping.csv",
        renderer.CHANNEL_SCHEMA)
    renderer._validate(comparisons, channels)
    summary = renderer._aggregate(comparisons, channels)

    assert summary["noise_shaped"]["perbin_accepted"] == 13
    assert summary["noise_shaped"]["perbin_rejected"] == 8
    assert summary["low_kparallel"]["perbin_accepted"] == 15
    assert summary["low_kparallel"]["perbin_rejected"] == 6
    assert summary["wedge_like"]["combined_noise_accepted"] == 40
    assert summary["wedge_like"]["combined_noise_rejected"] == 23
    assert summary["k_shell_localized"]["combined_fixed_accepted"] == 39
    assert summary["k_shell_localized"]["combined_fixed_rejected"] == 24


def test_commit_note_matches_the_evaluation_history():
    assert "one clean RFIsher commit" in renderer._commit_note({"a" * 40})
    assert "different clean RFIsher commits" in renderer._commit_note(
        {"a" * 40, "b" * 40})


@requires_results_tree
def test_dated_manifest_is_complete_and_self_consistent():
    manifest = json.loads((
        DATED_RELEASE / "forecast_completion_release_manifest.json"
    ).read_text(encoding="utf-8"))
    assert manifest["artifact_count"] == 12
    assert "one clean Bao commit" in manifest[
        "scientific_identities"]["commit_note"]
    assert manifest["scientific_identities"]["baonoise"][
        "clean_git_commits"] == [
            "1d7de4f0329772a18320d390bbe7eab12c3d9a0c"]
    assert all("banks/" not in item["path"]
               for item in manifest["artifacts"])


@requires_figure_toolchain
@requires_release_renderer
@requires_results_tree
def test_dated_renderer_reproduces_the_released_assets(tmp_path):
    figure = tmp_path / "forecast_completion_channel_tolerances.png"
    table = tmp_path / "forecast_completion_template_summary.tex"
    caption = tmp_path / "forecast_completion_channel_tolerances_caption.txt"
    manifest = tmp_path / "forecast_completion_release_manifest.json"
    assert renderer.main([
        "--comparison", str(
            DATED_RELEASE / "forecast_completion_template_comparison.csv"),
        "--channels", str(
            DATED_RELEASE / "forecast_completion_channel_mapping.csv"),
        "--status", str(
            DATED_RELEASE / "forecast_completion_template_status.csv"),
        "--figure", str(figure),
        "--table", str(table),
        "--caption", str(caption),
        "--manifest", str(manifest),
        "--preserve-release-metadata",
    ]) == 0
    for generated, released in (
        (figure, DATED_RELEASE / figure.name),
        (figure.with_suffix(".pdf"),
         DATED_RELEASE / figure.with_suffix(".pdf").name),
        (table, DATED_RELEASE / table.name),
        (caption, DATED_RELEASE / caption.name),
    ):
        assert generated.read_bytes() == released.read_bytes()


def test_kept_release_manifests_are_valid_records():
    """A fresh clone carries the identity of both releases even when the
    results tree is elsewhere: each kept manifest validates against the
    schema and names twelve repository-relative artifacts."""
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(renderer.MANIFEST_SCHEMA_PATH.read_text(
        encoding="utf-8"))
    for kept, _ in KEPT_MANIFESTS.values():
        manifest = json.loads(kept.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(manifest)
        assert manifest["artifact_count"] == 12 == len(manifest["artifacts"])
        assert all(item["path"].startswith(("out/", "docs/"))
                   for item in manifest["artifacts"])


@requires_results_tree
@pytest.mark.parametrize("release", sorted(KEPT_MANIFESTS))
def test_results_tree_matches_the_kept_manifests(release):
    kept, shipped = KEPT_MANIFESTS[release]
    manifest = json.loads(kept.read_text(encoding="utf-8"))
    # the same record, whatever line endings the checkout gave the kept copy
    assert json.loads(shipped.read_text(encoding="utf-8")) == manifest
    for item in manifest["artifacts"]:
        path = results_tree.release_path(item["path"], OUT)
        assert path.stat().st_size == item["size_bytes"], item["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() \
            == item["sha256"], item["path"]
