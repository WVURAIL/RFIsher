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
        record=tmp_path / "record.json", banks=[f"{root / BANK}={BANK}"],
        subset=False)
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


def test_the_restamp_refuses_a_target_outside_the_repository(checkout,
                                                             tmp_path):
    outside = tmp_path / "elsewhere" / "synthetic.npz"
    args = SimpleNamespace(**{**vars(checkout.args),
                              "banks": [f"{checkout.bank}={outside}"]})
    with pytest.raises(SystemExit, match="outside the repository"):
        restamp.restamp(args)
    assert not outside.exists()
    assert checkout.bank.read_bytes() == checkout.original


def test_every_pinned_bank_must_be_restamped(checkout, monkeypatch):
    monkeypatch.setattr(restamp, "BANKS", {ANCHOR: BANK, '"other.npz":':
                                           "data/other.npz"})
    with pytest.raises(SystemExit, match="exactly the pinned banks"):
        restamp.restamp(checkout.args)


def test_the_live_pins_name_the_six_banks():
    """Three CHIME banks, two Bull banks and the no-filter response bank (the
    three delay-filter response banks went with the post-processing scenarios)."""
    text = (ROOT / restamp.PINS).read_text(encoding="utf-8")
    for anchor in restamp.BANKS:
        assert anchor in text
    assert len(restamp.BANKS) == 6
    assert restamp.RADIOFISHER_PIN.search(text)


OTHER_ANCHOR = '"other.npz":'
OTHER = "data/other.npz"


def _add_other_bank(checkout, monkeypatch):
    """A second pinned bank, still carrying its original provenance."""
    _compressed_bank(checkout.root / OTHER)
    with checkout.pins.open("a") as fh:
        fh.write(f"OTHER = {{\n    {OTHER_ANCHOR}\n        \"{'0' * 64}\",\n}}\n")
    _git(checkout.root, "add", ".")
    _git(checkout.root, "commit", "-q", "-m", "another bank")
    monkeypatch.setattr(restamp, "BANKS", {ANCHOR: BANK, OTHER_ANCHOR: OTHER})
    return SimpleNamespace(**{**vars(checkout.args), "subset": True})


def test_a_subset_restamp_repins_only_its_banks(checkout, monkeypatch):
    args = _add_other_bank(checkout, monkeypatch)
    with pytest.raises(SystemExit, match="exactly the pinned banks"):
        restamp.restamp(SimpleNamespace(**{**vars(args), "subset": False}))
    assert restamp.restamp(args) == 0
    text = checkout.pins.read_text()
    assert f'"{restamp.sha256_file(checkout.bank)}"' in text
    assert f"{OTHER_ANCHOR}\n        \"{'0' * 64}\"" in text
    # the check still covers every pinned bank
    assert restamp.check(SimpleNamespace(radiofisher_dir=None)) == 1
    problems = restamp.provenance_problems("a" * 64)
    assert problems and all(p.startswith(OTHER) for p in problems)


def test_repin_after_a_rebuild_covers_only_the_rebuilt_banks(checkout,
                                                            monkeypatch):
    assert restamp.restamp(checkout.args) == 0     # stands in for a rebuild
    _git(checkout.root, "commit", "-q", "-am", "restamped")
    _add_other_bank(checkout, monkeypatch)
    text = checkout.pins.read_text()
    checkout.pins.write_text(text.replace(
        restamp.sha256_file(checkout.bank), "1" * 64))

    def repin(*banks_named):
        return restamp.repin_after_rebuild(SimpleNamespace(
            radiofisher_dir=None, banks=list(banks_named)))

    with pytest.raises(SystemExit, match="rebuilt banks"):
        repin()
    with pytest.raises(SystemExit, match="not a pinned bank"):
        repin("data/unknown.npz")
    with pytest.raises(SystemExit, match="refusing to re-pin"):
        repin(BANK, OTHER)
    assert repin(BANK) == 0
    text = checkout.pins.read_text()
    assert f'"{restamp.sha256_file(checkout.bank)}"' in text
    assert f"{OTHER_ANCHOR}\n        \"{'0' * 64}\"" in text


def test_a_rebind_replaces_only_the_radiofisher_section(checkout, monkeypatch):
    assert restamp.restamp(checkout.args) == 0     # the bank has its block
    _git(checkout.root, "commit", "-q", "-am", "restamped")
    before = _members(checkout.bank)
    old_meta = restamp.decode_meta(before[-1][3])
    section = {**old_meta["provenance"]["radiofisher"],
               "git_commit": "f" * 40, "working_tree_sha256": "a" * 64,
               "capabilities": [c for c in old_meta["provenance"]["radiofisher"]
                                ["capabilities"] if c != "vol_frac"]}
    monkeypatch.setattr(restamp, "radiofisher_section",
                        lambda explicit=None: dict(section))
    authenticated = []
    monkeypatch.setattr(restamp, "authenticate_rebound",
                        lambda path, explicit=None: authenticated.append(
                            restamp.decode_meta(_members(path)[-1][3])))
    args = SimpleNamespace(radiofisher_dir=None, banks=[BANK])

    assert restamp.rebind(args) == 0

    after = _members(checkout.bank)
    assert [m[:3] for m in after] == [m[:3] for m in before]
    assert [m[3] for m in after[:-1]] == [m[3] for m in before[:-1]]
    meta = restamp.decode_meta(after[-1][3])
    assert meta["provenance"]["radiofisher"] == section
    assert meta["restamp"]["radiofisher"] == [{
        "from": old_meta["provenance"]["radiofisher"],
        "date": meta["restamp"]["radiofisher"][0]["date"],
        "reason": restamp.REBIND_REASON}]
    assert authenticated == [meta]           # checked before it was written
    meta["provenance"]["radiofisher"] = old_meta["provenance"]["radiofisher"]
    del meta["restamp"]["radiofisher"]
    assert meta == old_meta
    assert f'"{restamp.sha256_file(checkout.bank)}"' in checkout.pins.read_text()
    assert restamp.check(SimpleNamespace(radiofisher_dir=None)) == 0
    # a second run is a no-op
    assert restamp.rebind(args) == 0
    assert _members(checkout.bank) == after


def test_a_rebind_refuses_a_bank_whose_source_digest_is_stale(checkout,
                                                              monkeypatch):
    monkeypatch.setattr(restamp, "radiofisher_section",
                        lambda explicit=None: {"git_commit": "f" * 40})
    with pytest.raises(SystemExit, match="stale bank source digest"):
        restamp.rebind(SimpleNamespace(radiofisher_dir=None, banks=[BANK]))
    assert checkout.bank.read_bytes() == checkout.original


def test_a_rebind_refuses_a_bank_that_does_not_authenticate(checkout,
                                                             monkeypatch):
    assert restamp.restamp(checkout.args) == 0
    _git(checkout.root, "commit", "-q", "-am", "restamped")
    rebound = checkout.bank.read_bytes()
    section = {**banks.FisherBank(checkout.bank).meta["provenance"]
               ["radiofisher"], "working_tree_sha256": "b" * 64}
    monkeypatch.setattr(restamp, "radiofisher_section",
                        lambda explicit=None: section)

    def refuse(path, explicit=None):
        raise ValueError("radiofisher.working_tree_sha256 differs")

    monkeypatch.setattr(restamp, "authenticate_rebound", refuse)
    with pytest.raises(SystemExit, match="does not authenticate"):
        restamp.rebind(SimpleNamespace(radiofisher_dir=None, banks=[BANK]))
    assert checkout.bank.read_bytes() == rebound


def test_same_arrays_compares_the_numerical_members_only(checkout, tmp_path):
    original = tmp_path / "original.npz"
    original.write_bytes(checkout.original)
    assert restamp.restamp(checkout.args) == 0
    # a re-stamped bank differs in its metadata alone
    assert restamp.main(["--same-arrays", str(original),
                         str(checkout.bank)]) == 0
    with np.load(original, allow_pickle=False) as archive:
        arrays = {name: np.array(archive[name]) for name in restamp.MEMBERS}
    arrays["F"].flat[0] += 1.0
    changed = tmp_path / "changed.npz"
    np.savez_compressed(changed, **arrays)
    assert restamp.main(["--same-arrays", str(original), str(changed)]) == 1
    with pytest.raises(SystemExit):
        restamp.main(["--same-arrays", str(original)])
