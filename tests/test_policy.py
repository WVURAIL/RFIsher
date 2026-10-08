"""The science register and the selector policy (rfisher.policy).

Three gates:

- the register golden: every entry of the old decision register
  (``selection_policy.py`` at 7b0067b) is in one of the two science registers
  with ``side: science`` and its value unchanged, or is recorded as a detector
  entry of the detector package, or is on the deleted list with a reason;
- the dead-reference gate: every entry a module reads through the loader
  exists, is a science entry, and is not on the deleted list;
- the side gate: the loader refuses a detector register or entry.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from rfisher import policy

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "projects" / "chime_bao"
GOLDEN = ROOT / "tests" / "golden" / "registers" / "selection_policy_7b0067b.json"
SOURCES = sorted((ROOT / "src").rglob("*.py")) + sorted(
    (ROOT / "scripts").rglob("*.py"))


# The one declared rename against the golden: the tie-break's tail rho, multiplier_q16 is named candidate_order, the
# detector's enumeration order it stands for.
RENAMED = {"selection.tie_break": (("rho", "multiplier_q16"), ("candidate_order",))}
# Entries removed after the golden, each recorded in the register's source.removed.
REMOVED = {"transfer.delay_suppression.default_key"}


def _golden():
    return json.loads(GOLDEN.read_text(encoding="utf-8"))["entries"]


def _renamed(ident, value):
    if ident not in RENAMED:
        return value
    old, new = RENAMED[ident]
    assert tuple(value[-len(old):]) == old, ident
    return list(value[:-len(old)]) + list(new)


def test_every_old_entry_is_carried_moved_or_deleted():
    loaded = policy.load(PROJECT)
    targets = {"science_register": "science_register.json",
               "selector_policy": "selector_policy.json"}
    for entry in _golden():
        target = entry["target"]
        if entry["id"] in REMOVED:
            assert entry["id"] not in loaded.decisions, entry["id"]
        elif target in targets:
            decision = loaded.decision(entry["id"])
            assert decision.register == targets[target], entry["id"]
            assert decision.side == "science"
            assert policy._thaw(decision.value) == _renamed(entry["id"], entry["value"]), entry["id"]
        elif target.startswith("pilot-proxy "):
            assert entry["id"] not in loaded.decisions, entry["id"]
        else:
            assert target == "deleted" and entry["reason"], entry["id"]
            assert entry["id"] not in loaded.decisions, entry["id"]
    old = {e["id"] for e in _golden()}
    new = set(loaded.decisions) - old
    assert new == {"selector.fine_rank"}


def test_the_golden_covers_the_whole_old_register():
    entries = _golden()
    assert len(entries) == len({e["id"] for e in entries}) == 114
    counts = {}
    for e in entries:
        key = e["target"].split(" ")[0]
        counts[key] = counts.get(key, 0) + 1
    assert counts == {"science_register": 15, "selector_policy": 3,
                      "pilot-proxy": 61, "deleted": 35}


def test_the_default_project_is_the_checkouts():
    assert policy.default_project() == PROJECT.resolve()
    assert policy.load().sha256() == policy.load(PROJECT).sha256()


def test_the_selector_policy_holds_the_selector_values():
    loaded = policy.load(PROJECT)
    assert loaded.value("selection.cost_plateau_ratio") == 1.02
    assert loaded.value("selection.tolerance_equality_is_feasible") is True
    assert loaded.value("selector.fine_rank") == 63


def _read_ids(tree):
    """String arguments of calls that read a register entry through a loader."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        arg = node.args[0]
        if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
            continue
        func = node.func
        name = (func.attr if isinstance(func, ast.Attribute) else
                func.id if isinstance(func, ast.Name) else "")
        owner = (func.value.id if isinstance(func, ast.Attribute)
                 and isinstance(func.value, ast.Name) else "")
        if name in ("value", "decision") and owner in ("policy", "register",
                                                       "loaded"):
            yield arg.value


def test_no_surviving_read_names_a_deleted_or_detector_entry():
    loaded = policy.load(PROJECT)
    gone = {e["id"] for e in _golden() if e["target"] not in (
        "science_register", "selector_policy")}
    read = {}
    for path in SOURCES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for ident in _read_ids(tree):
            read.setdefault(ident, []).append(path.relative_to(ROOT).as_posix())
    assert read, "no module reads the registers"
    assert {i: p for i, p in read.items() if i in gone} == {}
    assert {i: p for i, p in read.items() if i not in loaded.decisions} == {}


def test_the_profile_names_register_entries_that_exist():
    from rfisher.forecast.radiofisher_bao import model

    profile = model.load_profile(PROJECT)
    loaded = policy.load(PROJECT)
    for ident in profile["register"].values():
        assert loaded.decision(ident).side == "science"


def _write(tmp_path, name, doc):
    path = tmp_path / name
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def test_the_loader_refuses_a_detector_register(tmp_path):
    detector = {"schema": "pilot_proxy_detector_register_v1",
                "side": "detector", "decisions": []}
    with pytest.raises(policy.RegisterSideError):
        policy.read_register(_write(tmp_path, "science_register.json",
                                    detector))


def test_the_loader_refuses_a_detector_entry(tmp_path):
    doc = json.loads((PROJECT / "science_register.json").read_text())
    doc["decisions"][0] = dict(doc["decisions"][0], side="detector")
    with pytest.raises(policy.RegisterSideError, match="tagged side"):
        policy.read_register(_write(tmp_path, "science_register.json", doc))


def test_the_loader_refuses_an_entry_without_evidence_or_an_unknown_file(
        tmp_path):
    doc = json.loads((PROJECT / "selector_policy.json").read_text())
    doc["decisions"][0] = dict(doc["decisions"][0], evidence=[],
                               status="provisional")
    with pytest.raises(policy.RegisterError, match="needs evidence"):
        policy.read_register(_write(tmp_path, "selector_policy.json", doc))
    with pytest.raises(policy.RegisterError, match="one of"):
        policy.read_register(_write(tmp_path, "register.json", doc))
    with pytest.raises(KeyError, match="no science decision"):
        policy.load(PROJECT).value("correlation.sidereal_day_seconds")


def test_an_entry_in_both_registers_is_refused(tmp_path):
    science = json.loads((PROJECT / "science_register.json").read_text())
    selector = json.loads((PROJECT / "selector_policy.json").read_text())
    selector["decisions"].append(science["decisions"][0])
    _write(tmp_path, "science_register.json", science)
    _write(tmp_path, "selector_policy.json", selector)
    with pytest.raises(policy.RegisterError, match="two registers"):
        policy.load(tmp_path)
