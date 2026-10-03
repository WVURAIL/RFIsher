"""The examples run as written (the minimal example is run by test_readme.py)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_the_verdict_example_prices_the_golden_handoff():
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src") + os.pathsep + os.environ.get("PYTHONPATH", ""),
               PYTHONDONTWRITEBYTECODE="1")
    out = subprocess.run([sys.executable, str(ROOT / "examples" / "verdict_from_oc_table.py")], env=env,
                         capture_output=True, text=True, timeout=600, check=True).stdout
    assert "band scenario   r_tol" in out
    assert "band 29: undetermined" in out and "band 34: undetermined" in out
