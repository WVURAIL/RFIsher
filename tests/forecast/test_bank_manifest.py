"""The bank source manifest: one subpackage, hashed by one glob (design E.1)."""
from __future__ import annotations

import ast
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from rfisher.forecast.radiofisher_bao.bank import banks, templates

ROOT = Path(__file__).resolve().parents[2]
BANK_DIR = ROOT / banks.BANK_SOURCE_DIRECTORY
EXPECTED_FILES = 11
# The residual-template formula digest is recorded in every template bank;
# moving the module must not move it.
TEMPLATE_IMPLEMENTATION_SHA256 = (
    "fb34c9963c42ba7faea997d95b1dc20aabbce006dec676c03ed161d05977a0e4")
# Beyond the standard library: numpy, scipy, the RadioFisher backend, and
# camb, which only regenerates a P(k) cache (the optional "pk" extra).
ALLOWED_OUTSIDE = {"numpy", "scipy", "radiofisher", "camb"}


def _git(path, *args):
    return subprocess.run(
        ["git", "-C", str(path), "-c", "user.name=test",
         "-c", "user.email=test@example.invalid", *args],
        check=True, capture_output=True, text=True).stdout


def test_the_manifest_is_one_glob_over_the_bank_subpackage():
    assert banks.BANK_SOURCE_MANIFEST == {
        "include": (f"{banks.BANK_SOURCE_DIRECTORY}/*.py",), "exclude": ()}
    assert BANK_DIR == Path(banks.__file__).resolve().parent


def test_hashed_files_are_exactly_the_bank_subpackage():
    hashed = banks.manifest_files(ROOT, **banks.BANK_SOURCE_MANIFEST)
    on_disk = sorted(path.relative_to(ROOT).as_posix()
                     for path in BANK_DIR.rglob("*.py")
                     if "__pycache__" not in path.parts)
    assert hashed == on_disk
    assert len(hashed) == EXPECTED_FILES


def test_the_root_is_the_git_work_tree_and_the_digest_is_not_vacuous():
    top = _git(ROOT, "rev-parse", "--show-toplevel").strip()
    assert banks.source_root() == Path(top).resolve()
    state = banks.bank_source_state()
    vacuous = hashlib.sha256(b"scientific-source-manifest\0").hexdigest()
    assert state["working_tree_sha256"] not in (None, vacuous)
    assert state == banks._git_state(ROOT, **banks.BANK_SOURCE_MANIFEST)


@pytest.fixture
def source_copy(tmp_path):
    """A committed git copy of the bank subpackage beside one other file."""
    root = tmp_path / "repo"
    target = root / banks.BANK_SOURCE_DIRECTORY
    shutil.copytree(BANK_DIR, target,
                    ignore=shutil.ignore_patterns("__pycache__"))
    (root / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    (root / "src" / "rfisher" / "cli.py").write_text("VALUE = 1\n")
    _git(root, "init", "-q")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "copy")
    return root


def test_every_hashed_byte_moves_the_digest_and_nothing_else_does(source_copy):
    def digest():
        return banks._git_state(
            source_copy, **banks.BANK_SOURCE_MANIFEST)["working_tree_sha256"]

    reference = digest()
    hashed = banks.manifest_files(source_copy, **banks.BANK_SOURCE_MANIFEST)
    assert len(hashed) == EXPECTED_FILES
    for relative in hashed:
        path = source_copy / relative
        original = path.read_bytes()
        path.write_bytes(original + b"\n")
        assert digest() != reference, relative
        path.write_bytes(original)
    assert digest() == reference
    for relative in ("pyproject.toml", "src/rfisher/cli.py"):
        (source_copy / relative).write_text("VALUE = 2\n")
    assert digest() == reference


def _imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield 0, alias.name
        elif isinstance(node, ast.ImportFrom):
            yield node.level, node.module or ""


def test_the_import_closure_of_the_bank_code_stays_inside_it():
    package = "rfisher.forecast.radiofisher_bao.bank"
    outside = set()
    for path in sorted(BANK_DIR.rglob("*.py")):
        for level, module in _imports(path):
            if level:
                # a relative import may not climb out of the subpackage
                assert level == 1, f"{path.name} imports {'.' * level}{module}"
                continue
            top = module.split(".")[0]
            if top == "rfisher":
                assert module == "rfisher" or module.startswith(package), (
                    f"{path.name} imports {module}")
                if module == "rfisher":
                    outside.add("rfisher")
                continue
            assert (top in sys.stdlib_module_names or top == "__future__"
                    or top in ALLOWED_OUTSIDE), f"{path.name} imports {module}"
    # the one module outside the subpackage is the package itself, and it
    # holds the version and imports nothing
    assert outside == {"rfisher"}
    init = BANK_DIR.parents[2] / "__init__.py"
    assert not [node for node in ast.walk(ast.parse(init.read_text()))
                if isinstance(node, (ast.Import, ast.ImportFrom))]


def test_outside_a_work_tree_the_digest_is_unavailable(tmp_path):
    shutil.copytree(ROOT / "src" / "rfisher", tmp_path / "rfisher",
                    ignore=shutil.ignore_patterns("__pycache__", "*.npz"))
    code = ("from rfisher.forecast.radiofisher_bao.bank import banks\n"
            "print(banks.source_root(), banks.bank_source_state())\n")
    out = subprocess.run(
        [sys.executable, "-c", code], cwd=tmp_path, check=True, text=True,
        capture_output=True, env={**os.environ, "PYTHONPATH": str(tmp_path)}
    ).stdout
    assert out.strip() == ("None {'git_commit': None, 'git_dirty': None, "
                           "'working_tree_sha256': None}")


def test_a_copy_at_another_path_of_a_work_tree_has_no_bank_source(tmp_path):
    root = tmp_path / "other"
    shutil.copytree(ROOT / "src" / "rfisher", root / "lib" / "rfisher",
                    ignore=shutil.ignore_patterns("__pycache__", "*.npz"))
    _git(root, "init", "-q")
    code = ("from rfisher.forecast.radiofisher_bao.bank import banks\n"
            "print(banks.source_root())\n")
    out = subprocess.run(
        [sys.executable, "-c", code], cwd=root, check=True, text=True,
        capture_output=True, env={**os.environ, "PYTHONPATH": str(root / "lib")}
    ).stdout
    assert out.strip() == "None"


def test_the_template_formula_digest_survives_the_move():
    assert templates.implementation_sha256() == TEMPLATE_IMPLEMENTATION_SHA256


def test_the_bank_subpackage_carries_its_freeze_notice():
    notice = (BANK_DIR / "__init__.py").read_text(encoding="utf-8")
    assert "forces a re-stamp" in notice
    assert "scripts/restamp_bank_provenance.py" in notice
