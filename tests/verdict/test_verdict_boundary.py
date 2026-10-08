"""The verdict modules are generic: what they import and what they are called."""
from __future__ import annotations

import ast
import re
from pathlib import Path

import rfisher

PACKAGE = Path(rfisher.__file__).resolve().parent
VERDICT = sorted((PACKAGE / "verdict").glob("*.py"))
GENERAL = VERDICT + [PACKAGE / "policy.py"]
PROJECT_WORDS = re.compile(r"pilot|atsc|dtv|chime|bao|radiofisher",
                           re.IGNORECASE)
FORBIDDEN = ("rfisher.forecast", "rfisher.tolerance", "rfisher.records")


def _modules(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = ["rfisher", "verdict"][:max(0, 2 - node.level + 1)]
                module = ".".join(base + ([node.module] if node.module
                                          else []))
            else:
                module = node.module or ""
            yield module
            for alias in node.names:
                yield f"{module}.{alias.name}"


def test_the_verdict_imports_no_science_model_tolerance_or_record():
    found = {p.name: sorted(m for m in _modules(p) if m.startswith(FORBIDDEN))
             for p in VERDICT}
    assert {k: v for k, v in found.items() if v} == {}


def _identifiers(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            yield node.id
        elif isinstance(node, ast.Attribute):
            yield node.attr
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            yield node.name
        elif isinstance(node, ast.arg):
            yield node.arg
        elif isinstance(node, ast.alias):
            yield node.asname or node.name
        elif isinstance(node, ast.keyword) and node.arg:
            yield node.arg


def test_the_verdict_and_the_policy_loader_name_no_project():
    found = {}
    for path in GENERAL:
        bad = sorted({n for n in _identifiers(ast.parse(path.read_text(
            encoding="utf-8"))) if PROJECT_WORDS.search(n)})
        if bad:
            found[path.name] = bad
    assert found == {}
