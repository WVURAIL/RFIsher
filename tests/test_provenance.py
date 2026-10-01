"""The producer identity counts an untracked file under the package as dirty."""
from __future__ import annotations

from rfisher import provenance


def test_an_untracked_package_file_makes_the_producer_dirty(monkeypatch):
    calls = []

    def fake_git(*args):
        calls.append(args)
        if args[0] == "rev-parse":
            return "0" * 40
        return "?? src/rfisher/extra.py" if "--untracked-files=all" in args else ""

    monkeypatch.setattr(provenance, "_git", fake_git)
    identity = provenance.producer_identity({}, "0" * 64)
    assert identity["dirty"] is True and identity["dirty_files"] == "?? src/rfisher/extra.py"
    assert any(a[0] == "status" and "--untracked-files=all" in a for a in calls)
