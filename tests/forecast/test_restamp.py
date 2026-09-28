"""The one bank re-stamp: metadata only, deterministic, and checked afterwards."""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import zipfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import rfisher
from rfisher.forecast.radiofisher_bao.bank import banks
from test_fisherbank_schema import _write_bank

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "restamp_bank_provenance", ROOT / "scripts" / "restamp_bank_provenance.py")
restamp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(restamp)

ANCHOR = '"synthetic.npz":'
BANK = "data/synthetic.npz"


def _git(path, *args):
    return subprocess.run(
        ["git", "-C", str(path), "-c", "user.name=test",
         "-c", "user.email=test@example.invalid", *args],
        check=True, capture_output=True, text=True).stdout.strip()


def _compressed_bank(path: Path) -> Path:
    stored = _write_bank(path.with_suffix(".stored.npz"))
    with np.load(stored, allow_pickle=False) as archive:
        arrays = {name: np.array(archive[name]) for name in restamp.MEMBERS}
    stored.unlink()
    np.savez_compressed(path, **arrays)
    return path


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    """A committed repository with the bank code, one bank and its pin."""
    root = tmp_path / "repo"
    shutil.copytree(ROOT / banks.BANK_SOURCE_DIRECTORY,
                    root / banks.BANK_SOURCE_DIRECTORY,
                    ignore=shutil.ignore_patterns("__pycache__"))
    (root / "data").mkdir()
    bank = _compressed_bank(root / BANK)
    pins = root / "tests" / "forecast" / "test_resources.py"
    pins.parent.mkdir(parents=True)
    pins.write_text(
        f"PINS = {{\n    {ANCHOR}\n        \"{'0' * 64}\",\n}}\n"
        f"EXPECTED_RADIOFISHER_SOURCE_SHA256 = (\n    \"{'a' * 64}\"\n)\n")
    _git(root, "init", "-q")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "synthetic")
    baseline = tmp_path / "baseline"
    baseline.mkdir()
    _git(baseline, "init", "-q")
    _git(baseline, "commit", "-q", "--allow-empty", "-m", "baseline")
    radiofisher = tmp_path / "RadioFisher"
    (radiofisher / "radiofisher").mkdir(parents=True)
    (radiofisher / "radiofisher" / "baofisher.py").touch()

    monkeypatch.setattr(restamp, "ROOT", root)
    monkeypatch.setattr(restamp, "BANKS", {ANCHOR: BANK})
    monkeypatch.setattr(banks, "bank_source_state", lambda: banks._git_state(
        root, **banks.BANK_SOURCE_MANIFEST))
    monkeypatch.setattr(restamp, "current_radiofisher_digest",
                        lambda explicit=None: "a" * 64)
    original = banks.FisherBank(bank).meta["provenance"]["baonoise"]

    def authenticated(baseline_dir, python, rf_dir, paths):
        return {"state": {"working_tree_sha256": "b" * 64},
                "banks": {str(path): {"recorded": original,
                                      "digest_matches": True,
                                      "manifest_matches": True,
                                      "config": "chime2022",
                                      "evaluation_identity_sha256": "c" * 64}
                          for path in paths}}

    monkeypatch.setattr(restamp, "authenticate_at_baseline", authenticated)
    args = SimpleNamespace(
        from_commit=_git(baseline, "rev-parse", "HEAD"), baseline=baseline,
        baseline_python="python", radiofisher_dir=radiofisher,
        record=tmp_path / "record.json", banks=[f"{root / BANK}={BANK}"])
    return SimpleNamespace(root=root, bank=root / BANK, pins=pins, args=args,
                           original=bank.read_bytes())


def _members(path):
    with zipfile.ZipFile(path) as archive:
        return [(info.filename, info.date_time, info.compress_type,
                 archive.read(info)) for info in archive.infolist()]


def test_the_restamp_rewrites_only_the_rfisher_provenance(checkout, tmp_path):
    before = _members(checkout.bank)
    old_meta = restamp.decode_meta(before[-1][3])
    head = _git(checkout.root, "rev-parse", "HEAD")
    state = banks.bank_source_state()

    assert restamp.restamp(checkout.args) == 0

    after = _members(checkout.bank)
    assert [m[:3] for m in after] == [m[:3] for m in before]
    assert [m[3] for m in after[:-1]] == [m[3] for m in before[:-1]]
    meta = restamp.decode_meta(after[-1][3])
    record = meta["provenance"]["baonoise"]
    assert record == {
        "version": rfisher.__version__, "git_commit": head,
        "git_dirty": False,
        "working_tree_sha256": state["working_tree_sha256"],
        "source_manifest": {"include": list(
            banks.BANK_SOURCE_MANIFEST["include"]), "exclude": []}}
    block = meta.pop("restamp")
    assert block["from_commit"] == old_meta["provenance"]["baonoise"][
        "git_commit"]
    assert block["from_working_tree_sha256"] == "a" * 64
    assert block["member_sha256"] == {
        name: restamp.sha256_bytes(data) for name, _, _, data in before[:-1]}
    assert set(block) == {"from_commit", "from_working_tree_sha256",
                          "from_source_manifest", "date", "reason",
                          "member_sha256", "equivalence_evidence"}
    assert str(checkout.root.parent) not in json.dumps(block)   # no paths
    meta["provenance"]["baonoise"] = old_meta["provenance"]["baonoise"]
    assert meta == old_meta                     # built_utc and the rest kept
    banks.FisherBank(checkout.bank)

    pinned = restamp.sha256_file(checkout.bank)
    assert f'"{pinned}"' in checkout.pins.read_text()
    saved = json.loads(checkout.args.record.read_text())
    assert saved["banks"][BANK]["sha256"] == pinned
    assert saved["commit"] == head


def test_the_restamped_file_is_the_same_bytes_every_time(checkout, tmp_path):
    assert restamp.restamp(checkout.args) == 0
    first = checkout.bank.read_bytes()
    _git(checkout.root, "checkout", "--", ".")
    assert checkout.bank.read_bytes() == checkout.original
    assert restamp.restamp(checkout.args) == 0
    assert checkout.bank.read_bytes() == first


def test_the_check_passes_then_fails_after_an_edit_under_bank(checkout):
    args = SimpleNamespace(radiofisher_dir=None)
    assert restamp.check(args) == 1                  # not yet re-stamped
    assert restamp.restamp(checkout.args) == 0
    assert restamp.check(args) == 0
    physics = checkout.root / banks.BANK_SOURCE_DIRECTORY / "physics.py"
    physics.write_bytes(physics.read_bytes() + b"\n")
    assert restamp.check(args) == 1


def test_the_restamp_refuses_a_dirty_tree(checkout):
    (checkout.root / "notes.txt").write_text("uncommitted\n")
    with pytest.raises(SystemExit, match="clean"):
        restamp.restamp(checkout.args)
    assert checkout.bank.read_bytes() == checkout.original


def test_the_restamp_refuses_a_bank_the_baseline_does_not_authenticate(
        checkout, monkeypatch):
    def refused(baseline_dir, python, rf_dir, paths):
        return {"state": {}, "banks": {str(path): {
            "recorded": {}, "digest_matches": False, "manifest_matches": True,
            "config": "chime2022", "evaluation_identity_sha256": None}
            for path in paths}}

    monkeypatch.setattr(restamp, "authenticate_at_baseline", refused)
    with pytest.raises(SystemExit, match="does not authenticate"):
        restamp.restamp(checkout.args)
    assert checkout.bank.read_bytes() == checkout.original


def test_every_pinned_bank_must_be_restamped(checkout, monkeypatch):
    monkeypatch.setattr(restamp, "BANKS", {ANCHOR: BANK, '"other.npz":':
                                           "data/other.npz"})
    with pytest.raises(SystemExit, match="exactly the pinned banks"):
        restamp.restamp(checkout.args)


def test_the_live_pins_name_the_nine_banks():
    text = (ROOT / restamp.PINS).read_text(encoding="utf-8")
    for anchor in restamp.BANKS:
        assert anchor in text
    assert len(restamp.BANKS) == 9
    assert restamp.RADIOFISHER_PIN.search(text)
