"""Release identity and intentionally supported top-level imports."""
from __future__ import annotations

from importlib import import_module, metadata
from pathlib import Path

import rfisher


RELEASE_VERSION = "3.0.0"
PUBLIC_MODULES = (
    "api",
    "backend",
    "channels",
    "constants",
    "cosmologies",
    "fisherbank",
    "forecast",
    "incumbent",
    "layout",
    "pkcache",
    "preparation",
    "products",
    "residual",
    "residual_scores",
    "resources",
    "scenarios",
    "selection_policy",
    "survey",
    "thresholds",
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


def test_public_module_exports_are_exact_and_importable():
    assert tuple(rfisher.__all__) == PUBLIC_MODULES
    for name in PUBLIC_MODULES:
        exported = getattr(rfisher, name)
        assert import_module(f"rfisher.{name}") is exported
