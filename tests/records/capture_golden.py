"""The golden capture handoff and helpers for the capture record tests."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path

GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "handoff" / "capture"
SOURCE = json.loads((GOLDEN / "SOURCE.json").read_text())


def sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def quiet(fn, args):
    """Run a record's main in process; return its stdout."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert not fn(args)
    return buf.getvalue()
