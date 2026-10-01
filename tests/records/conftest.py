"""The golden capture handoff, unpacked once per session."""
from __future__ import annotations

import gzip
import json
import tarfile

import pytest

from capture_golden import GOLDEN, SOURCE, sha256


@pytest.fixture(scope="session")
def capture_handoff_dir(tmp_path_factory):
    archive = GOLDEN / "capture_handoff.tar.gz"
    assert sha256(archive) == SOURCE["capture_handoff.tar.gz"]["sha256"]
    root = tmp_path_factory.mktemp("capture_handoff") / "handoff"
    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall(root, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))
    assert sha256(root / "manifest.json") == SOURCE["capture_handoff.tar.gz"]["manifest_sha256"]
    return root


@pytest.fixture(scope="session")
def frozen_reader_objects():
    path = GOLDEN / "reader_objects.json.gz"
    assert sha256(path) == SOURCE["reader_objects.json.gz"]["sha256"]
    return json.loads(gzip.decompress(path.read_bytes()))
