"""The decision register page names every entry of the project's two registers."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_every_register_id_is_on_the_page():
    page = (ROOT / "docs" / "decision-register.md").read_text(encoding="utf-8")
    for name in ("science_register.json", "selector_policy.json"):
        for d in json.loads((ROOT / "projects" / "chime_bao" / name).read_text(encoding="utf-8"))["decisions"]:
            assert f"| `{d['id']}` |" in page, d["id"]
