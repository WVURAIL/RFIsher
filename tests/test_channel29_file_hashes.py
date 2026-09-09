"""Frozen source and data hashes remain byte-exact on supported Python versions."""
import hashlib
import importlib.util
from pathlib import Path

import pytest


@pytest.mark.parametrize("script", [
    "calibrate_channel29_controls_v1", "compare_channel29_policies_v1",
])
@pytest.mark.parametrize("size", [0, 1024 * 1024 + 37])
def test_hashes_do_not_require_python311_file_digest(tmp_path, monkeypatch, script, size):
    monkeypatch.delattr(hashlib, "file_digest", raising=False)
    source = Path(__file__).resolve().parents[1] / "scripts" / f"{script}.py"
    spec = importlib.util.spec_from_file_location(f"hash_test_{script}", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    content = (b"\r\n\x00\xff" * ((size + 3) // 4))[:size]
    path = tmp_path / "input.dat"
    path.write_bytes(content)
    assert module.sha(path) == hashlib.sha256(content).hexdigest()
