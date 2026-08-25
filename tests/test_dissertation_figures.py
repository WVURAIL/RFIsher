from __future__ import annotations

import csv
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
FIGURE_DIR = ROOT / "scripts" / "dissertation"
FIGURE_TOOLS = ("latex", "dvipng", "kpsewhich")
MISSING_TOOLS = [name for name in FIGURE_TOOLS if shutil.which(name) is None]
requires_figure_tools = pytest.mark.skipif(
    bool(MISSING_TOOLS),
    reason="dissertation figures need: " + ", ".join(MISSING_TOOLS))


FIGURE_NAMES = (
    "fig_bao_time_vs_masking.pdf",
    "fig_bao_the_case.pdf",
    "fig_bao_convergence.pdf",
    "fig_bao_two_walls.pdf",
)


def _render_figures(path: Path, hash_seed: str) -> None:
    code = (
        "from pathlib import Path\n"
        "import figures\n"
        "figures.main(['--out', __import__('sys').argv[1]])\n"
    )
    env = os.environ.copy()
    env["PYTHONHASHSEED"] = hash_seed
    env["SOURCE_DATE_EPOCH"] = "1786492800"
    subprocess.run(
        [sys.executable, "-c", code, str(path)], cwd=FIGURE_DIR,
        env=env, check=True)


def test_stable_subset_prefix_uses_glyph_content():
    sys.path.insert(0, str(FIGURE_DIR))
    try:
        import figures
    finally:
        sys.path.pop(0)

    first = figures._stable_subset_prefix(["alpha", "beta", "gamma"])
    second = figures._stable_subset_prefix(["gamma", "alpha", "beta"])
    assert first == second
    assert re.fullmatch(r"[A-Z]{6}\+", first)


def test_current_era_points_keep_coherence_provenance():
    path = FIGURE_DIR / "data" / "bao_era_points.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        rows = {int(row["channel"]): row for row in csv.DictReader(handle)}

    assert rows[32]["tau_quality"] == "bounded_above"
    assert float(rows[32]["tau_seconds"]) == 300.0
    assert rows[35]["tau_quality"] == "measured"
    assert float(rows[35]["r_over_rtol"]) == pytest.approx(119.2723256)


@requires_figure_tools
def test_figures_are_byte_stable_between_processes(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    _render_figures(first, "1")
    _render_figures(second, "2")

    for name in FIGURE_NAMES:
        assert (first / name).read_bytes() == (second / name).read_bytes()
