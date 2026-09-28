"""The general layers name no telescope, emitter, cosmology or Fisher code."""
from __future__ import annotations

import ast
import re
from pathlib import Path

import rfisher

PACKAGE = Path(rfisher.__file__).resolve().parent
GENERAL = sorted((PACKAGE / "tolerance").glob("*.py")) + [
    PACKAGE / "science_model.py"]
PROJECT_WORDS = re.compile(r"pilot|atsc|dtv|chime|bao|radiofisher",
                           re.IGNORECASE)


def _identifiers(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            yield node.id
        elif isinstance(node, ast.Attribute):
            yield node.attr
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                               ast.ClassDef)):
            yield node.name
        elif isinstance(node, ast.arg):
            yield node.arg
        elif isinstance(node, ast.alias):
            yield node.asname or node.name
        elif isinstance(node, ast.keyword) and node.arg:
            yield node.arg


def test_the_general_layers_import_nothing_from_a_science_model():
    for path in GENERAL:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("rfisher.forecast"), path
                assert not (node.level and "forecast" in node.module), path
            if isinstance(node, ast.Import):
                assert not any(alias.name.startswith("rfisher.forecast")
                               for alias in node.names), path


def test_the_general_layers_use_no_project_identifiers():
    found = {}
    for path in GENERAL:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        bad = sorted({name for name in _identifiers(tree)
                      if PROJECT_WORDS.search(name)})
        if bad:
            found[path.name] = bad
    assert found == {}
