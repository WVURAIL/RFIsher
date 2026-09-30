"""The identity of the code that produced an output (informational).

:func:`producer_identity` records the repository commit and whether the
package's own sources are dirty (a change elsewhere in the checkout does not
count), a digest of the package's sources, the science register's digest,
and the sha256 of the inputs the caller names. It is written into manifests
beside the outputs; a consumer never requires it.
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Mapping

from . import __version__

PACKAGE = Path(__file__).resolve().parent


def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(["git", *args], cwd=PACKAGE, capture_output=True,
                             text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def source_digest() -> str:
    """sha256 over the package's Python sources, path and bytes, sorted."""
    digest = hashlib.sha256()
    for path in sorted(PACKAGE.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        digest.update(path.relative_to(PACKAGE).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def producer_identity(inputs: Mapping[str, str] | None = None,
                      register_sha256: str | None = None) -> dict:
    """Commit, package-scoped dirty flag, source digest, register and inputs."""
    commit = _git("rev-parse", "HEAD")
    status = _git("status", "--porcelain", "--untracked-files=no", "--",
                  str(PACKAGE))
    if register_sha256 is None:
        from . import policy

        try:
            register_sha256 = policy.sha256()
        except FileNotFoundError:
            register_sha256 = None
    return {
        "package": "rfisher", "version": __version__,
        "repository": "WVURAIL/RFIsher", "commit": commit,
        "dirty": None if status is None else bool(status),
        "dirty_files": status or "",
        "source_digest": source_digest(),
        "register_sha256": register_sha256,
        "inputs": dict(sorted((inputs or {}).items())),
    }
