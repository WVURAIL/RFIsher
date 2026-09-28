"""The README quickstart and the minimal example run as written."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _quickstart_blocks() -> list[str]:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    section = text.split("\n## Quickstart\n", 1)[1].split("\n## ", 1)[0]
    return re.findall(r"```python\n(.*?)```", section, flags=re.S)


def test_the_readme_quickstart_runs_as_written():
    blocks = _quickstart_blocks()
    assert len(blocks) == 2
    namespace: dict = {}
    for block in blocks:
        exec(compile(block, "README.md", "exec"), namespace)
    assert namespace["fc"] is not None and namespace["scenario"] is not None


def test_the_minimal_example_runs_without_radiofisher():
    env = {key: value for key, value in os.environ.items()
           if key not in ("PYTHONPATH", "RADIOFISHER_DIR")}
    env.update(PYTHONPATH=str(ROOT / "src"), PYTHONDONTWRITEBYTECODE="1",
               MPLBACKEND="Agg")
    out = subprocess.run(
        [sys.executable, str(ROOT / "examples" / "minimal_example.py")],
        env=env, check=True, capture_output=True, text=True).stdout
    assert "S(2 yr) =" in out and "yr to 5 sigma" in out
