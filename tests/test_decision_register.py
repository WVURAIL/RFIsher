"""The decision register tables match the project's two registers."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_register_tables_match_the_json():
    page = (ROOT / "docs" / "decision-register.md").read_text(encoding="utf-8")
    tables = []
    for name in ("science_register.json", "selector_policy.json"):
        rows = ["| Id | Value | Status | Evidence |", "|---|---|---|---|"]
        for d in json.loads((ROOT / "projects" / "chime_bao" / name).read_text(encoding="utf-8"))["decisions"]:
            rows.append(f"| `{d['id']}` | {json.dumps(d['value'])} | {d['status']} | {'; '.join(d['evidence'])} |")
        tables.extend(rows)
    assert [line for line in page.splitlines() if line.startswith("|")] == tables
