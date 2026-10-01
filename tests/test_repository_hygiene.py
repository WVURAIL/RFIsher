"""Repository hygiene: no workstation path in the code, no version suffix in a file name but a format's or a frozen
file's, no reference to a removed path except at a commit that holds it, no retired "world" name in the code, and the
byte-pinned visibility response module unchanged."""
from __future__ import annotations

import ast
import hashlib
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "rfisher"
REMOVED = ROOT / "tests" / "data" / "removed_paths.txt"
# records keep the paths and names they were written with
RECORDS = ("tests/data/", "tests/golden/", "docs/releases/", "src/rfisher/records/chime_atsc_2026/", "CHANGELOG.md",
           # the rewrite table of the register evidence, and a bank's recorded build command
           "tests/test_register_evidence.py", "tests/records/capture_golden.py")
VERSIONED_OK = re.compile(r"^(src/rfisher/data/schemas/[\w]+_v\d+\.schema\.json|tests/data/pilotproxy_v5_fixture\.json)$")
# the release basis name of the vendored coarse sensitivity (coarse_world_sensitivity_2026-09-09), and the modules
# whose sha256 the shipped tolerance table's provenance records (their names are pinned with the table)
WORLD_OK_NAMES = re.compile(r"coarse_world", re.IGNORECASE)
WORLD_OK_MODULES = ("tolerance/bands.py", "tolerance/rule.py", "tolerance/table.py", "forecast/radiofisher_bao/model.py",
                    "forecast/radiofisher_bao/response.py", "forecast/radiofisher_bao/filter_scenarios.py")
PINNED = {"src/rfisher/response/visibility.py": "0d041bfd"}


def _tracked():
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("needs a git checkout")
    files = [f for f in out.decode().split("\0") if f]
    if not files:
        pytest.skip("needs a git checkout")
    return files


def _text(path):
    try:
        return (ROOT / path).read_text(encoding="utf-8")
    except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
        return None


def test_no_workstation_path_in_the_code():
    assert not [p for p in sorted(SRC.rglob("*.py")) if "/home/djg" in p.read_text(encoding="utf-8")]


def test_no_version_suffix_in_a_file_name():
    found = [f for f in _tracked() if re.search(r"_[vV]\d", Path(f).name)
             and not f.startswith(RECORDS) and not VERSIONED_OK.match(f)]
    assert not found, found


def _removed():
    rows = [line.split("\t") for line in REMOVED.read_text(encoding="utf-8").splitlines() if line and not line.startswith("#")]
    return {path: commit for path, commit in rows}


def test_no_reference_to_a_removed_path():
    removed = _removed()
    pattern = re.compile(r"(?<![\w/.-])(" + "|".join(re.escape(p) for p in sorted(removed, key=len, reverse=True))
                         + r")(?![\w/.-]|@| at [0-9a-f]{7})")
    found = []
    for f in _tracked():
        if f.startswith(RECORDS):
            continue
        text = _text(f)
        for m in pattern.finditer(text or ""):
            found.append(f"{f}:{text.count(chr(10), 0, m.start()) + 1}: {m.group(1)}")
    assert not found, found


def test_no_world_name_in_the_code():
    found = []
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        if path.as_posix().startswith(str(SRC / "records" / "chime_atsc_2026")) or rel in WORLD_OK_MODULES:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = ([node.name] if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else
                     [node.id] if isinstance(node, ast.Name) else [node.arg] if isinstance(node, ast.arg) else [])
            found += [f"{rel}:{node.lineno}: {n}" for n in names
                      if re.search(r"(?:^|_)worlds?(?:_|$)", n, re.IGNORECASE) and not WORLD_OK_NAMES.search(n)]
    assert not found, found


def test_the_byte_pinned_module_is_unchanged():
    for path, prefix in PINNED.items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest().startswith(prefix), path
