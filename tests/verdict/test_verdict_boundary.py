"""The verdict is generic: what it imports, what it opens, what it is called."""
from __future__ import annotations

import ast
import builtins
import io
import re
from pathlib import Path

import rfisher
from rfisher.verdict.archive import verdict_archive

PACKAGE = Path(rfisher.__file__).resolve().parent
ROOT = PACKAGE.parents[1]
PROJECT = ROOT / "projects" / "chime_bao"
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


def test_a_verdict_run_opens_only_the_handoff_and_one_tolerance_table(
        handoff_copy, tolerances, tmp_path, monkeypatch):
    tol = tolerances({"29": [("none", "rule", 1000.0, 0.0)],
                      "34": [("none", "rule", None, 0.0)]})
    out = tmp_path / "science"
    opened = []
    real_open, real_io_open = builtins.open, io.open

    def record(file, *args, **kwargs):
        opened.append(Path(file).resolve() if isinstance(file, (str, Path))
                      else file)
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", record)
    monkeypatch.setattr(io, "open", record)
    verdict_archive(handoff_copy.path, tol, PROJECT, out)
    monkeypatch.setattr(builtins, "open", real_open)
    monkeypatch.setattr(io, "open", real_io_open)
    data = {p for p in opened if isinstance(p, Path)
            and PACKAGE not in p.parents and PROJECT.resolve() not in p.parents
            and out.resolve() not in p.parents}
    assert data == {handoff_copy.path.resolve() / name for name in (
        "oc_table.csv", "oc_summary.csv", "manifest.json")} | {tol.resolve()}


def test_the_command_writes_the_verdict(handoff_copy, tolerances, tmp_path,
                                        capsys):
    from rfisher.cli import main

    tol = tolerances({"29": [("none", "rule", 1000.0, 0.0)],
                      "34": [("none", "rule", None, 0.0)]})
    out = tmp_path / "science"
    assert main(["verdict", "archive", "--project", str(PROJECT),
                 "--characterization", str(handoff_copy.path),
                 "--tolerances", str(tol), "--out", str(out)]) == 0
    assert "2 undetermined" in capsys.readouterr().out
    assert {p.name for p in out.iterdir()} == {
        "verdict.csv", "verdict_points.csv", "screen.csv", "sensitivity.csv",
        "manifest.json"}
    screen = (out / "screen.csv").read_text().splitlines()
    assert screen[1].startswith("29,undetermined,2,detector refused:")
    assert screen[2].startswith("34,undetermined,1,tolerance refused:")
