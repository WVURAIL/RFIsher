"""Release identity and a package that imports nothing on its own."""
from __future__ import annotations

import ast
from importlib import import_module, metadata
from pathlib import Path

import rfisher


RELEASE_VERSION = "4.0.0"
PUBLIC_MODULES = (
    "rfisher.cli",
    "rfisher.forecast.radiofisher_bao.api",
    "rfisher.forecast.radiofisher_bao.bank.banks",
    "rfisher.forecast.radiofisher_bao.bank.build",
    "rfisher.forecast.radiofisher_bao.coherence_gain",
    "rfisher.forecast.radiofisher_bao.layout",
    "rfisher.forecast.radiofisher_bao.legacy_masks",
    "rfisher.forecast.radiofisher_bao.scenarios",
    "rfisher.forecast.radiofisher_bao.significance",
    "rfisher.policy",
    "rfisher.records.chime_atsc_2026.capture_ruling",
    "rfisher.response.visibility",
    "rfisher.tolerance.reference",
    "rfisher.verdict.archive",
    "rfisher.verdict.interval",
)


def test_release_version_is_consistent_across_public_metadata():
    root = Path(__file__).resolve().parents[1]

    assert rfisher.__version__ == RELEASE_VERSION
    assert 'name = "rfisher"' in (
        root / "pyproject.toml").read_text(encoding="utf-8")
    assert f'version = "{RELEASE_VERSION}"' in (
        root / "pyproject.toml").read_text(encoding="utf-8")
    assert f'version: "{RELEASE_VERSION}"' in (
        root / "CITATION.cff").read_text(encoding="utf-8")


def test_installed_distribution_matches_public_version_when_available():
    try:
        installed = metadata.version("rfisher")
    except metadata.PackageNotFoundError:
        return
    assert installed == RELEASE_VERSION


def test_package_holds_the_version_and_imports_nothing():
    tree = ast.parse(Path(rfisher.__file__).read_text(encoding="utf-8"))
    assert not [node for node in ast.walk(tree)
                if isinstance(node, (ast.Import, ast.ImportFrom))]
    assigned = [target.id for node in tree.body if isinstance(node, ast.Assign)
                for target in node.targets]
    assert assigned == ["__version__"]


def test_public_modules_are_importable():
    for name in PUBLIC_MODULES:
        assert import_module(name).__name__ == name
