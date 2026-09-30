"""The package list of pyproject.toml, and the project a wheel carries."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _pyproject():
    if sys.version_info < (3, 11):
        pytest.skip("tomllib needs Python 3.11")
    import tomllib

    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_the_listed_packages_are_the_packages_under_src():
    setuptools = _pyproject()["tool"]["setuptools"]
    found = sorted(
        ".".join(p.parent.relative_to(ROOT / "src").parts)
        for p in (ROOT / "src").rglob("__init__.py"))
    assert sorted(setuptools["packages"]) == sorted(found + ["rfisher.projects"])
    assert setuptools["package-dir"] == {"": "src",
                                         "rfisher.projects": "projects"}


def test_the_wheel_carries_the_project_files():
    data = _pyproject()["tool"]["setuptools"]["package-data"]["rfisher.projects"]
    shipped = {p.relative_to(ROOT / "projects").as_posix()
               for pattern in data for p in (ROOT / "projects").glob(pattern)}
    project = {p.relative_to(ROOT / "projects").as_posix()
               for p in (ROOT / "projects").rglob("*") if p.is_file()}
    assert shipped == project
