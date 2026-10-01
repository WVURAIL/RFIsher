"""The project registers against the frozen archive policy copy (the registers at f56916a, byte for byte): every key of
every entry is the same but the evidence strings that named deleted files (now cited at the last commit that holds
them, or by the file that holds the code now) and the tie-break's renamed tail."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "projects" / "chime_bao"
FROZEN = ROOT / "src" / "rfisher" / "records" / "chime_atsc_2026" / "data" / "policy_2026_archive"
EVIDENCE = {
    "scripts/bias_tolerance.py": ["scripts/bias_tolerance.py@e041d5e"],
    "scripts/three_worlds.py": ["scripts/three_worlds.py@e041d5e"],
    "src/rfisher/forecast.py": ["src/rfisher/forecast.py@e041d5e"],
    "src/rfisher/residual.py": ["src/rfisher/residual.py@7b0067b"],
    "src/rfisher/thresholds.py": ["src/rfisher/thresholds.py@7b0067b", "src/rfisher/verdict/interval.py"],
    "docs/contamination-residuals.md": ["docs/tolerance.md"],
}
VALUES = {"selection.tie_break": ["systematic_residual", "masked_fraction", "candidate_order"]}


def _evidence(old):
    out = []
    for e in old:
        for new in EVIDENCE.get(e, [e]):
            if new not in out:
                out.append(new)
    return out


def test_only_the_declared_strings_differ_from_the_frozen_registers():
    for name in ("science_register.json", "selector_policy.json"):
        new = json.loads((PROJECT / name).read_text(encoding="utf-8"))
        old = json.loads((FROZEN / name).read_text(encoding="utf-8"))
        assert [d["id"] for d in new["decisions"]] == [d["id"] for d in old["decisions"]]
        source = dict(new["source"])
        if name == "selector_policy.json":
            assert source.pop("renamed") == {"selection.tie_break": source_rename()}
        assert source == old["source"]
        assert {k: v for k, v in new.items() if k not in ("decisions", "source")} == \
            {k: v for k, v in old.items() if k not in ("decisions", "source")}
        for a, b in zip(new["decisions"], old["decisions"]):
            assert a["evidence"] == _evidence(b["evidence"]), a["id"]
            assert a["value"] == VALUES.get(a["id"], b["value"]), a["id"]
            assert {k: v for k, v in a.items() if k not in ("evidence", "value")} == \
                {k: v for k, v in b.items() if k not in ("evidence", "value")}, a["id"]


def source_rename():
    return ("the tail rho, multiplier_q16 of the 7b0067b value is named candidate_order, the order it stands for (M6)")


def test_no_evidence_names_a_deleted_file():
    for name in ("science_register.json", "selector_policy.json"):
        for d in json.loads((PROJECT / name).read_text(encoding="utf-8"))["decisions"]:
            for e in d["evidence"]:
                if e.startswith(("https://", "dissertation/")) or "@" in e:
                    continue
                assert (ROOT / e.split(" ")[0]).exists(), (d["id"], e)
