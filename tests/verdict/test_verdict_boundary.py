"""The verdict is generic: what it imports, what it opens, what it is called."""
from __future__ import annotations

import ast
import re
from pathlib import Path

import rfisher

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


AUDIT = r"""
import json, os, sys
opened = []
def hook(event, args):
    if event == "open" and not isinstance(args[0], int):
        try:
            opened.append(os.fsdecode(os.fspath(args[0])))
        except TypeError:
            pass
sys.addaudithook(hook)
from rfisher.verdict.archive import verdict_archive
verdict_archive(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
open(sys.argv[5], "w").write(json.dumps(opened))
"""


def test_a_verdict_run_opens_only_the_handoff_and_one_tolerance_table(
        handoff_copy, tolerances, tmp_path):
    """A file-open audit (sys.addaudithook, in its own interpreter) of a verdict
    run: of the data it reads, only the three handoff files and the one
    tolerance table."""
    import json
    import os
    import subprocess
    import sys

    tol = tolerances({"29": [("none", "rule", 1000.0, 0.0)],
                      "34": [("none", "rule", None, 0.0)]})
    out = tmp_path / "science"
    log = tmp_path / "opened.json"
    env = dict(os.environ, PYTHONPATH=str(PACKAGE.parent),
               PYTHONDONTWRITEBYTECODE="1")
    subprocess.run([sys.executable, "-c", AUDIT, str(handoff_copy.path),
                    str(tol), str(PROJECT), str(out), str(log)], check=True,
                   capture_output=True, env=env)
    opened = {Path(p).resolve() for p in json.loads(log.read_text())}
    data = {p for p in opened
            if PACKAGE not in p.parents and PROJECT.resolve() not in p.parents
            and out.resolve() not in p.parents and p != log.resolve()
            and p.suffix in (".csv", ".json", ".yaml")
            and not str(p).startswith((sys.prefix, sys.base_prefix))}
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
    output = capsys.readouterr().out
    assert "2 undetermined" in output
    assert "Historical conditional screening only" in output
    assert "physical operating recommendations are not established" in output
    assert {p.name for p in out.iterdir()} == {
        "verdict.csv", "verdict_points.csv", "screen.csv", "sensitivity.csv",
        "manifest.json"}
    screen = (out / "screen.csv").read_text().splitlines()
    assert screen[1].startswith("29,undetermined,2,detector refused:")
    assert screen[2].startswith("34,undetermined,1,tolerance refused:")
