"""The Python snippets of the tolerance page run as written, on the bank they load.

None of them quotes a number, so each keeps ``api.load()`` (the default cmbspa2026 bank); a snippet that quotes a
thesis-bank number would load ``api.load(cosmology="planck2018")`` and this test would hold the number to it.
"""
from __future__ import annotations

import re
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "tolerance.md"


def _snippets():
    return re.findall(r"```python\n(.*?)```", PAGE.read_text(encoding="utf-8"), flags=re.S)


def test_the_page_has_its_snippets():
    assert len([s for s in _snippets() if "api.load(" in s]) == 3


@pytest.mark.parametrize("index", range(3))
def test_each_snippet_runs(index):
    code = [s for s in _snippets() if "api.load(" in s][index]
    assert not re.search(r"#\s*->|^\s*>>>", code, flags=re.M), "a quoted result: hold it to the snippet's bank"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        exec(compile(code, f"{PAGE.name} snippet {index}", "exec"), {})
