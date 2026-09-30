"""Where the generated results live.

The tables, evidence ledgers, figures and the two immutable
forecast-completion release roots were tracked under ``out/`` until
September 2026. They are generated products, so they now live outside the
repository with the other datasets (and on the WVU OneDrive); the repository
keeps the code, the release manifests under ``docs/releases/`` and the
manifest schema. Resolution, first hit wins:

- ``$RFISHER_OUT``;
- ``out_dir`` in ``data/products.local.json``, the gitignored machine-local
  overlay ``rfisher.products`` already reads;
- the repository's own ignored ``out/``, where the scripts write by default.

This lives beside ``rfisher`` rather than inside it for the same reason as
the rest of ``rfisher_results``: the shipped banks pin a digest of
``src/rfisher/``.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV = "RFISHER_OUT"
LOCAL = ROOT / "data" / "products.local.json"
DEFAULT = ROOT / "out"
RELEASE_MANIFESTS = ROOT / "docs" / "releases"


def out_dir(local_path: Path | str = LOCAL) -> Path:
    """The results tree: the directory that holds what ``out/`` used to."""
    configured = os.environ.get(ENV)
    if configured:
        return Path(configured).expanduser()
    local_path = Path(local_path)
    if local_path.is_file():
        local = json.loads(local_path.read_text(encoding="utf-8"))
        if local.get("out_dir"):
            path = Path(local["out_dir"]).expanduser()
            return path if path.is_absolute() else ROOT / path
    return DEFAULT


def release_path(recorded: str, out: Path | None = None) -> Path:
    """Where a release manifest entry is on this machine.

    The manifests record paths relative to the repository as it was when
    ``out/`` was tracked, and a manifest is immutable, so the recorded
    ``out/`` prefix stays and resolves to the results tree. Anything else
    (the schema document) is still in the repository.
    """
    out = out_dir() if out is None else out
    if recorded.startswith("out/"):
        return out / recorded[len("out/"):]
    return ROOT / recorded


def present(*names: str, out: Path | None = None) -> bool:
    """Whether every named file exists in the results tree."""
    out = out_dir() if out is None else out
    return all((out / name).is_file() for name in names)
