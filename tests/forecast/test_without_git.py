"""Without git on PATH the forecast still runs, and the bank source is unknown."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PROGRAM = """
import json
from rfisher import cli
from rfisher.forecast.radiofisher_bao.bank import backend, banks
assert cli.main(["forecast", "--uniform", "0.3"]) == 0
print(json.dumps({"state": banks.bank_source_state(),
                  "root": str(banks.source_root()),
                  "candidates": [str(c) for c in backend._DEFAULT_RF_CANDIDATES]}))
"""


def _run(path: str) -> list[str]:
    env = {key: value for key, value in os.environ.items()
           if key not in ("PYTHONPATH", "RADIOFISHER_DIR")}
    env.update(PATH=path, PYTHONPATH=str(ROOT / "src"),
               PYTHONDONTWRITEBYTECODE="1", GIT_OPTIONAL_LOCKS="0")
    return subprocess.run(
        [sys.executable, "-c", PROGRAM], cwd=ROOT, env=env, check=True,
        capture_output=True, text=True).stdout.splitlines()


def test_the_forecast_runs_without_git_and_no_bank_source_is_claimed(tmp_path):
    empty = tmp_path / "bin"
    empty.mkdir()
    assert shutil.which("git", path=str(empty)) is None
    forecast, record = _run(str(empty))[-2:]
    state = json.loads(record)
    assert state == {
        "state": {"git_commit": None, "git_dirty": None,
                  "working_tree_sha256": None},
        "root": "None", "candidates": []}
    # the same forecast as with git present
    assert forecast == _run(os.environ.get("PATH", os.defpath))[-2]
