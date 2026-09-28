"""RadioFisher discovery: the environment first, then the checkout's sibling."""
from __future__ import annotations

import subprocess
from pathlib import Path

from rfisher.forecast.radiofisher_bao.bank import backend

ROOT = Path(__file__).resolve().parents[2]


def _checkout(path: Path) -> Path:
    package = path / "radiofisher"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("BACKEND_ID = 'radiofisher'\n")
    (package / "baofisher.py").touch()
    return path


def test_the_sibling_candidate_sits_beside_the_git_work_tree():
    top = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "--show-toplevel"],
        check=True, capture_output=True, text=True).stdout.strip()
    sibling = Path(top).resolve().parent / "RadioFisher"
    assert backend._checkout_sibling() == (sibling,)
    # the sibling is the only fallback after RADIOFISHER_DIR
    assert backend._DEFAULT_RF_CANDIDATES == (sibling,)


def test_the_environment_wins_over_the_sibling(tmp_path, monkeypatch):
    environment = _checkout(tmp_path / "environment")
    sibling = _checkout(tmp_path / "sibling")
    monkeypatch.setattr(backend, "_DEFAULT_RF_CANDIDATES", (sibling,))
    monkeypatch.setenv("RADIOFISHER_DIR", str(environment))
    assert backend.find_radiofisher_dir() == environment
    monkeypatch.delenv("RADIOFISHER_DIR")
    assert backend.find_radiofisher_dir() == sibling


def test_discovery_never_counts_parent_directories():
    source = Path(backend.__file__).read_text(encoding="utf-8")
    assert "parents[" not in source
