"""The channel table: one row per channel, written as JSON (with provenance) and CSV.

Each row is one RadioFisher forecast at the channel's own redshift. The table
changes only when an input in inputs.py, the residual model or the quadrature
changes; a new detector calibration never needs a new table.
"""
import csv
import importlib.metadata
import json
import os
import platform
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor
from importlib import resources
from pathlib import Path

import numpy as np
import scipy

from . import __version__, baselines, forecast, inputs, pk_cache
from .bands import Band, channels
from .tolerance import FITTED, tolerance

SCHEMA = "rfisher-channel-table-v2"
TABLE = "channel_table.json"
CSV_COLUMNS = ["channel", "role", "low_mhz", "high_mhz", "z_center", "sigma_dv", "response_dv", "a_tol"]


def row(band: Band) -> dict:
    """Forecast one channel and reduce it to its table row."""
    t0 = time.monotonic()
    F, names, p = forecast.channel_fisher(band)
    t = tolerance(F, names)
    g = p["geometry"]
    return {"channel": band.channel, "role": band.role, "low_mhz": band.low_mhz, "high_mhz": band.high_mhz,
            "z_min": band.z_min, "z_max": band.z_max, "z_center": float(p["cosmo"]["z"]),
            "sigma_dv": t["sigma_dv"], "bias_dv_per_unit_a": t["bias_dv_per_unit_a"],
            "response_dv": t["response_dv"], "a_tol": t["a_tol"], "dilations": t["dilations"],
            "condition": t["condition"],
            "residual": {"n_nu": g["n_nu"], "horizon_slope": g["m"], "band_depth_mpc": g["L"]},
            "seconds": time.monotonic() - t0}


def _git_commit(path) -> str | None:
    """HEAD of the checkout holding ``path``, marked '+dirty' if it has uncommitted changes."""
    try:
        def git(*a):
            return subprocess.run(["git", "-C", str(path), *a], capture_output=True, text=True,
                                  check=True).stdout.strip()
        head = git("rev-parse", "HEAD")
        return head + ("+dirty" if git("status", "--porcelain") else "")
    except (OSError, subprocess.CalledProcessError):
        return None


def _radiofisher_source() -> dict:
    import radiofisher
    out = {"version": radiofisher.__version__}
    try:
        direct = importlib.metadata.distribution("radiofisher").read_text("direct_url.json")
        if direct:
            info = json.loads(direct)
            out.update(url=info.get("url"), commit=info.get("vcs_info", {}).get("commit_id"))
    except importlib.metadata.PackageNotFoundError:
        pass
    out.setdefault("commit", None)
    out["commit"] = out["commit"] or _git_commit(Path(radiofisher.__file__).parent)
    return out


def provenance() -> dict:
    return {"rfisher": {"version": __version__, "commit": _git_commit(Path(__file__).parent)},
                "radiofisher": _radiofisher_source(),
                "pk_table": {"name": inputs.PK_TABLES[inputs.DEFAULT_COSMOLOGY],
                             "sha256": pk_cache.file_sha256(inputs.pk_table_path())},
                "baseline_density": {"name": baselines.INTER_FILE,
                                     "sha256": pk_cache.file_sha256(baselines.inter_file())},
                "python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__}


def build_table(bands=None, workers: int | None = None) -> dict:
    """Forecast every channel (in parallel) and return the table."""
    bands = channels() if bands is None else list(bands)
    if not bands:
        raise ValueError("at least one channel is required")
    if workers is not None and workers < 1:
        raise ValueError("workers must be positive")
    workers = min(len(bands), workers or os.cpu_count() or 1)
    if workers == 1:
        rows = [row(b) for b in bands]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            rows = list(pool.map(row, bands))
    return {"schema": SCHEMA,
                "inputs": {"cosmology": inputs.DEFAULT_COSMOLOGY,
                           "cosmology_description": inputs.COSMOLOGY_NAMES[inputs.DEFAULT_COSMOLOGY],
                           "experiment": "CHIME (CHIME Overview), inter-cylinder baselines only",
                           "baselines": inputs.DEFAULT_BASELINES,
                            "retained_hours": inputs.RETAINED_HOURS,
                            "residual": "coherent flat 6 MHz shelf in the horizon wedge, unit strength",
                            "fitted": list(FITTED),
                            "tolerance_on": "D_V: ln alpha_V = 2/3 ln alpha_perp + 1/3 ln alpha_par",
                            "quadrature": {"radial_order": forecast.RADIAL_ORDER,
                                            "angular_order": forecast.ANGULAR_ORDER,
                                            "bao_derivative_step": forecast.STEP}},
                "provenance": provenance(), "channels": rows}


def write_table(table: dict, out) -> list[Path]:
    """Write <out>/channel_table.json and <out>/channel_table.csv."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    js = out / TABLE
    js.write_text(json.dumps(table, indent=1) + "\n")
    cs = out / "channel_table.csv"
    with cs.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in table["channels"]:
            w.writerow({k: (repr(v) if isinstance(v, float) else v) for k, v in r.items()})
    return [js, cs]


def read_table(path=None) -> dict:
    """A written table, or the one shipped with the package."""
    source = resources.files("rfisher.data").joinpath(TABLE) if path is None else Path(path)
    table = json.loads(source.read_text())
    if table.get("schema") != SCHEMA:
        raise ValueError(f"{path} is not a {SCHEMA} table")
    return table
