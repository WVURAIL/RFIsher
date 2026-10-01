"""The forecast adapter reads nothing from the detector side.

``rfisher.forecast.radiofisher_bao`` may import the forecast package, the
science-model interface and the science register loader, and nothing else of
``rfisher``: no mask ingestion, no product reader, no threshold code.
"""
from __future__ import annotations

import ast
from pathlib import Path

import rfisher

PACKAGE = Path(rfisher.__file__).resolve().parent
ADAPTER = PACKAGE / "forecast" / "radiofisher_bao"
ALLOWED = ("rfisher.forecast", "rfisher.science_model", "rfisher.policy")


def _imports(path: Path):
    """Absolute names a file imports (relative ones resolved): each module,
    and for ``from X import y`` the name ``X.y``."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    parts = path.relative_to(PACKAGE.parent).with_suffix("").parts
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = ".".join(parts[:len(parts) - node.level])
                module = f"{base}.{node.module}" if node.module else base
            else:
                module = node.module or ""
            for alias in node.names:
                yield f"{module}.{alias.name}"


def test_the_adapter_imports_only_the_forecast_and_the_science_interface():
    found = {}
    for path in sorted(ADAPTER.rglob("*.py")):
        bad = sorted({m for m in _imports(path)
                      if m.startswith("rfisher.")
                      and m != "rfisher.__version__"
                      and not m.startswith(ALLOWED)})
        if bad:
            found[path.relative_to(PACKAGE).as_posix()] = bad
    assert found == {}


def test_the_resolver_resolves_relative_imports():
    names = set(_imports(ADAPTER / "scenarios.py"))
    assert "rfisher.forecast.radiofisher_bao.legacy_masks" in names
    assert "rfisher.forecast.radiofisher_bao.bank._validation.real_scalar" \
        in names


def test_only_the_adapter_reaches_the_bank_validation():
    found = sorted(path.relative_to(PACKAGE).as_posix() for path in PACKAGE.rglob("*.py")
                   if ADAPTER not in path.parents
                   and any(m.startswith("rfisher.forecast.radiofisher_bao.bank._validation") for m in _imports(path)))
    assert found == []


def test_no_module_imports_the_detector():
    found = sorted(path.relative_to(PACKAGE).as_posix() for path in PACKAGE.rglob("*.py")
                   if any(m == "pilot_proxy" or m.startswith("pilot_proxy.") for m in _imports(path)))
    assert found == []
