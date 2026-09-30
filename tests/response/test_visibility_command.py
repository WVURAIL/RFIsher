"""``rfisher response visibility`` writes the known-moment check."""
from __future__ import annotations

import hashlib
import json

from rfisher.cli import main
from rfisher.response import validate, visibility

# The module moved byte for byte (the frozen endpoint JSONs cite this sha).
MODULE_SHA256 = "0d041bfdd55605c7b3422ca0d7ab4209603dbf72b8c81990e5312ba3a464b4e2"


def test_the_module_is_the_cited_one():
    data = open(visibility.__file__, "rb").read()
    assert hashlib.sha256(data).hexdigest() == MODULE_SHA256


def test_the_command_writes_the_validation(tmp_path, capsys):
    assert main(["response", "visibility", "--output", str(tmp_path)]) == 0
    result = json.loads((tmp_path / "validation.json").read_text())
    assert result["passed"] is True and result["samples"] == 250000
    assert [s["sha256"] for s in result["sources"]] == [
        hashlib.sha256(open(p, "rb").read()).hexdigest()
        for p in (validate.__file__, visibility.__file__)]
    assert result["sources"][1]["sha256"] == MODULE_SHA256
    assert json.loads(capsys.readouterr().out)["passed"] is True
