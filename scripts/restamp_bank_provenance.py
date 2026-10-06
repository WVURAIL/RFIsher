#!/usr/bin/env python3
"""Re-stamp the Fisher banks' RFIsher provenance, check it, or re-pin the banks.

A bank records the digest of the source that built it (``provenance.baonoise``;
the key keeps the package's former name so that every bank loads alike), and
it authenticates only against that digest. When the bank source moved into the
``forecast/radiofisher_bao/bank`` subpackage, its manifest changed and every
bank had to be re-stamped once. A re-stamp does not claim that the new code
built the bank. It claims that the new bank code computes the same arrays,
which the equivalence gate proves separately; the ``restamp`` block records
where the bank came from.

Five modes:

``restamp BANK=OUT ...``
    For each bank: authenticate it at the baseline commit in a subprocess
    under the baseline interpreter (the recorded source digest must equal the
    baseline's, and a chime2022 bank must pass the baseline evaluation
    identity); rewrite only ``meta.npy``, copying every numerical member's
    decoded bytes as read; update ``provenance.baonoise`` to this commit, the
    bank manifest and its digest; add the ``restamp`` block; write the file
    twice and require the two writes to be byte-identical; and re-pin
    ``tests/forecast/test_resources.py``. The tree must be clean, and the
    commit recorded is its HEAD. The pairs must cover every pinned bank;
    with ``--subset`` they may cover some of them, and only those are
    re-pinned (``--check`` still covers all).

``--check``
    Every pin equals its file, and every bank records the current bank-source
    digest, the current manifest, and the RadioFisher digest of the checkout.
    Any edit under ``bank/`` fails it.

``--repin BANK ...``
    After ``scripts/rebuild_shipped_banks.sh``: refuse unless each named bank
    records the current source digests, then rewrite the pins of those banks
    alone and the RadioFisher pin.

``--rebind BANK ...``
    After RadioFisher moves without changing what a bank holds: refuse unless
    the RadioFisher checkout is clean and each named bank records the
    current bank-source digest; rewrite only ``meta.npy``, copying every
    numerical member's bytes as read; replace ``provenance.radiofisher`` with
    the checkout's identity (commit, digest, backend version and
    capabilities) and append the section it replaces to
    ``restamp.radiofisher``; require a rebound chime2022 bank to authenticate
    against the checkout (``response.evaluation_identity``; the Bull banks
    are checked against the direct backend by the test suite); then re-pin
    as ``--repin`` does. The claim is the same as a re-stamp's: the arrays are
    the ones the recorded build computed, and the checkout named now
    computes them too.

``--same-arrays COMMITTED REBUILT``
    Exit non-zero unless the two banks hold byte-identical numerical members.
    The rebuild fallback runs it on every bank it rebuilds, against the bank
    it replaces.

    python scripts/restamp_bank_provenance.py --check
    python scripts/restamp_bank_provenance.py --from-commit e041d5e \\
        --baseline ../RFIsher-eras-wt --baseline-python PY \\
        --radiofisher-dir ../RadioFisher --record out/restamp.json \\
        BANK=OUT [BANK=OUT ...]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import numpy as np
from numpy.lib import format as npy_format

from rfisher import __version__
from rfisher.forecast.radiofisher_bao.bank import banks
from rfisher.forecast.radiofisher_bao.bank.backend import (
    backend_capabilities, find_radiofisher_dir, import_radiofisher)

ROOT = banks.source_root()
PINS = Path("tests/forecast/test_resources.py")
MEMBERS = ("F", "t_grid", "zs", "zc", "paramnames", "meta")
NUMERICAL = MEMBERS[:-1]

# pin anchor in the pin file -> bank path in the checkout
BANKS = {
    "resources.CMBSPA2026_BANK_NAME:":
        "src/rfisher/data/fisher_bank_chime2022_cmbspa2026.npz",
    "resources.PLANCK2018_BANK_NAME:":
        "src/rfisher/data/fisher_bank_chime2022.npz",
    "resources.PACT2025_BANK_NAME:":
        "src/rfisher/data/fisher_bank_chime2022_pact2025.npz",
    '"fisher_bank_bull2015_planck2013_epsfg1e-6.npz":':
        "data/fisher_bank_bull2015_planck2013_epsfg1e-6.npz",
    '"fisher_bank_bull2015_planck2013_epsfg1e-5.npz":':
        "data/fisher_bank_bull2015_planck2013_epsfg1e-5.npz",
    '"fisher_bank_chime2022_pres_dense.npz":':
        "src/rfisher/data/response_banks/fisher_bank_chime2022_pres_dense.npz",
}
RADIOFISHER_PIN = re.compile(
    r'(EXPECTED_RADIOFISHER_SOURCE_SHA256 = \(\s*\n\s*")([0-9a-f]{64})(")')
REASON = ("The bank source manifest became the forecast/radiofisher_bao/bank "
          "subpackage; the arrays are the ones the recorded source built.")
EVIDENCE = ("refactor-equivalence-2026-09/M5a: decoded members, mini-bank "
            "golden, evaluation identity and the tolerance table")
REBIND_REASON = ("The RadioFisher checkout moved without changing what the "
                 "bank holds; the rebound bank authenticates against it and "
                 "the tolerance table rebuilds byte for byte.")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def current_manifest() -> dict:
    return {key: list(value) for key, value in
            banks.BANK_SOURCE_MANIFEST.items()}


def read_members(path: Path) -> tuple[list[zipfile.ZipInfo], dict[str, bytes]]:
    """The zip entries of a bank and the decoded bytes of each member."""
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        data = {info.filename: archive.read(info) for info in infos}
    names = [info.filename for info in infos]
    if names != [f"{name}.npy" for name in MEMBERS]:
        raise ValueError(f"{path}: unexpected bank members {names}")
    for info in infos:
        if info.compress_type != zipfile.ZIP_DEFLATED:
            raise ValueError(f"{path}: {info.filename} is not DEFLATE")
    return infos, data


def decode_meta(npy_bytes: bytes) -> dict:
    array = npy_format.read_array(io.BytesIO(npy_bytes), allow_pickle=False)
    return json.loads(str(array))


def encode_meta(meta: dict) -> bytes:
    """``meta.npy`` exactly as the bank builder writes it."""
    stream = io.BytesIO()
    npy_format.write_array(
        stream, np.asanyarray(json.dumps(meta, sort_keys=True)),
        allow_pickle=False)
    return stream.getvalue()


def write_bank(path: Path, infos: list[zipfile.ZipInfo],
               data: dict[str, bytes]) -> None:
    """Write the members in their order, each with its own entry date."""
    with zipfile.ZipFile(path, mode="w", compression=zipfile.ZIP_DEFLATED) \
            as archive:
        for original in infos:
            info = zipfile.ZipInfo(original.filename,
                                   date_time=original.date_time)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = original.external_attr
            with archive.open(info, "w", force_zip64=True) as stream:
                stream.write(data[original.filename])


def restamped_meta(meta: dict, *, commit: str, state: dict,
                   member_sha256: dict, date: str) -> dict:
    """The bank metadata with the new RFIsher provenance and restamp block."""
    old = meta["provenance"]["baonoise"]
    new = json.loads(json.dumps(meta))
    new["provenance"]["baonoise"] = {
        **old,
        "version": __version__,
        "git_commit": commit,
        "git_dirty": False,
        "working_tree_sha256": state["working_tree_sha256"],
        "source_manifest": current_manifest(),
    }
    new["restamp"] = {
        "from_commit": old["git_commit"],
        "from_working_tree_sha256": old["working_tree_sha256"],
        "from_source_manifest": old["source_manifest"],
        "date": date,
        "reason": REASON,
        "member_sha256": member_sha256,
        "equivalence_evidence": EVIDENCE,
    }
    return new


BASELINE_PROGRAM = r"""
import hashlib, importlib.util, json, sys
from pathlib import Path
baseline, rf_dir, banks = Path(sys.argv[1]), sys.argv[2], sys.argv[3:]
import rfisher
from rfisher import fisherbank
assert Path(rfisher.__file__).resolve().is_relative_to(baseline / "src"), rfisher.__file__
spec = importlib.util.spec_from_file_location(
    "baseline_bias_tolerance", baseline / "scripts" / "bias_tolerance.py")
bt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bt)
state = fisherbank._git_state(baseline, **fisherbank.RFISHER_SOURCE_MANIFEST)
out = {"rfisher_file": rfisher.__file__, "state": state, "banks": {}}
for path in banks:
    bank = fisherbank.FisherBank(path)
    record = bank.meta["provenance"]["baonoise"]
    row = {"recorded": record, "digest_matches": record["working_tree_sha256"] == state["working_tree_sha256"],
           "manifest_matches": record["source_manifest"] == {k: list(v) for k, v in fisherbank.RFISHER_SOURCE_MANIFEST.items()},
           "config": bank.meta["config"], "evaluation_identity_sha256": None}
    if bank.meta["config"] == "chime2022":
        identity, _ = bt._evaluation_identity(bank, rf_dir=rf_dir)
        row["evaluation_identity_sha256"] = hashlib.sha256(
            json.dumps(identity, sort_keys=True).encode()).hexdigest()
    out["banks"][path] = row
print(json.dumps(out, sort_keys=True))
"""


def authenticate_at_baseline(baseline: Path, python: str, rf_dir: Path,
                             paths: list[Path]) -> dict:
    env = {key: value for key, value in os.environ.items()
           if key != "PYTHONPATH"}
    # The baseline is only read: no bytecode, and no index refresh by git.
    env.update(PYTHONPATH=str(baseline / "src"), PYTHONDONTWRITEBYTECODE="1",
               GIT_OPTIONAL_LOCKS="0", RADIOFISHER_DIR=str(rf_dir),
               MPLBACKEND="Agg")
    completed = subprocess.run(
        [python, "-c", BASELINE_PROGRAM, str(baseline), str(rf_dir),
         *[str(path) for path in paths]],
        cwd=baseline, env=env, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        sys.exit("baseline authentication failed:\n" + completed.stderr)
    return json.loads(completed.stdout.strip().splitlines()[-1])


def git(*args) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def repin(text: str, pins: dict[str, str]) -> tuple[str, list[str]]:
    """Rewrite each anchored pin; return the new text and the changes."""
    changes = []
    for anchor, new in pins.items():
        pattern = re.compile(
            "(" + re.escape(anchor) + r'\s*\n\s*")([0-9a-f]{64})(")')
        match = pattern.search(text)
        if not match:
            sys.exit(f"pin anchor not found in {PINS}: {anchor}")
        if match.group(2) != new:
            changes.append(f"{anchor} {match.group(2)} -> {new}")
            text = pattern.sub(lambda m: m.group(1) + new + m.group(3), text,
                               count=1)
    return text, changes


def restamp(args) -> int:
    if ROOT is None:
        sys.exit("run from a git checkout of RFIsher")
    if git("status", "--porcelain"):
        sys.exit("the checkout must be clean: the re-stamp records its HEAD")
    commit = git("rev-parse", "HEAD")
    state = banks.bank_source_state()
    if state["git_commit"] != commit or state["git_dirty"] is not False \
            or state["working_tree_sha256"] is None:
        sys.exit(f"bank source state is not a clean HEAD: {state}")
    baseline = Path(args.baseline).resolve()
    baseline_head = subprocess.run(
        ["git", "-C", str(baseline), "rev-parse", "HEAD"], check=True,
        capture_output=True, text=True).stdout.strip()
    if not baseline_head.startswith(args.from_commit):
        sys.exit(f"baseline checkout is at {baseline_head}, "
                 f"not {args.from_commit}")
    pairs = []
    for item in args.banks:
        source, _, target = item.partition("=")
        if not source or not target:
            sys.exit(f"expected BANK=OUT, got {item!r}")
        pairs.append((Path(source).resolve(), (ROOT / target).resolve()
                      if not Path(target).is_absolute() else Path(target)))
    outside = [str(target) for _, target in pairs
               if not target.is_relative_to(ROOT)]
    if outside:
        sys.exit(f"targets outside the repository {ROOT}: "
                 f"{', '.join(outside)}")
    targets ={str(target.relative_to(ROOT)) for _, target in pairs}
    missing = set(BANKS.values()) - targets
    unexpected = targets - set(BANKS.values())
    if unexpected or (missing and not args.subset):
        sys.exit("the re-stamp covers exactly the pinned banks: missing "
                 f"{sorted(missing)}, unexpected {sorted(unexpected)}")

    rf_dir = find_radiofisher_dir(args.radiofisher_dir)
    base = authenticate_at_baseline(baseline, args.baseline_python, rf_dir,
                                    [source for source, _ in pairs])
    date = dt.datetime.now(dt.timezone.utc).date().isoformat()
    record = {"commit": commit, "version": __version__,
              "working_tree_sha256": state["working_tree_sha256"],
              "source_manifest": current_manifest(),
              "baseline": {"commit": baseline_head,
                           "python": args.baseline_python,
                           "state": base["state"]},
              "date": date, "banks": {}}
    staged = []
    for source, target in pairs:
        check = base["banks"][str(source)]
        if not (check["digest_matches"] and check["manifest_matches"]):
            sys.exit(f"{source} does not authenticate at the baseline: "
                     f"{check}")
        if check["config"] == "chime2022" \
                and check["evaluation_identity_sha256"] is None:
            sys.exit(f"{source}: no baseline evaluation identity")
        infos, data = read_members(source)
        members = {f"{name}.npy": sha256_bytes(data[f"{name}.npy"])
                   for name in NUMERICAL}
        meta = restamped_meta(decode_meta(data["meta.npy"]), commit=commit,
                              state=state, member_sha256=members, date=date)
        new_data = dict(data, **{"meta.npy": encode_meta(meta)})
        with tempfile.TemporaryDirectory() as scratch:
            first, second = Path(scratch) / "a.npz", Path(scratch) / "b.npz"
            write_bank(first, infos, new_data)
            write_bank(second, infos, new_data)
            if first.read_bytes() != second.read_bytes():
                sys.exit(f"{source}: the two writes differ")
            _, written = read_members(first)
            if any(written[f"{name}.npy"] != data[f"{name}.npy"]
                   for name in NUMERICAL):
                sys.exit(f"{source}: a numerical member changed")
            if decode_meta(written["meta.npy"]) != meta:
                sys.exit(f"{source}: the metadata did not round-trip")
            banks.FisherBank(first)       # the restamped bank still loads
            payload = first.read_bytes()
        staged.append((target, payload))
        record["banks"][str(target.relative_to(ROOT))] = {
            "source_sha256": sha256_file(source),
            "sha256": sha256_bytes(payload),
            "member_sha256": members,
            "from": check["recorded"],
            "baseline_evaluation_identity_sha256":
                check["evaluation_identity_sha256"],
        }
    for target, payload in staged:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    pins = {anchor: record["banks"][relative]["sha256"]
            for anchor, relative in BANKS.items() if relative in targets}
    text, changes = repin((ROOT / PINS).read_text(encoding="utf-8"), pins)
    (ROOT / PINS).write_text(text, encoding="utf-8")
    record["pins_changed"] = changes
    if args.record:
        Path(args.record).parent.mkdir(parents=True, exist_ok=True)
        Path(args.record).write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
    for change in changes:
        print("re-pinned", change)
    print(f"re-stamped {len(staged)} banks at {commit}")
    return 0


def current_radiofisher_digest(explicit=None) -> str:
    try:
        rf_dir = find_radiofisher_dir(explicit)
    except FileNotFoundError as exc:
        sys.exit("cannot verify bank provenance: no RadioFisher checkout "
                 f"found ({exc}); set RADIOFISHER_DIR")
    return banks._git_state(
        rf_dir, **banks.RADIOFISHER_SOURCE_MANIFEST)["working_tree_sha256"]


def provenance_problems(radiofisher_digest: str,
                        relatives=None) -> list[str]:
    state = banks.bank_source_state()
    problems = []
    if state["working_tree_sha256"] is None:
        problems.append("the bank source digest is unavailable outside a "
                        "git checkout")
    for relative in (BANKS.values() if relatives is None else relatives):
        path = ROOT / relative
        if not path.is_file():
            problems.append(f"{relative}: missing")
            continue
        provenance = banks.FisherBank(path).meta["provenance"]
        recorded = provenance["baonoise"]
        if recorded["working_tree_sha256"] != state["working_tree_sha256"]:
            problems.append(
                f"{relative}: stale bank source digest\n"
                f"  recorded {recorded['working_tree_sha256']}\n"
                f"  current  {state['working_tree_sha256']}")
        if recorded["source_manifest"] != current_manifest():
            problems.append(f"{relative}: stale bank source manifest "
                            f"{recorded['source_manifest']}")
        if provenance["radiofisher"]["working_tree_sha256"] \
                != radiofisher_digest:
            problems.append(
                f"{relative}: stale RadioFisher digest\n"
                f"  recorded {provenance['radiofisher']['working_tree_sha256']}\n"
                f"  current  {radiofisher_digest}")
    return problems


def pin_problems(text: str, radiofisher_digest: str) -> list[str]:
    problems = []
    for anchor, relative in BANKS.items():
        pattern = re.compile(
            "(" + re.escape(anchor) + r'\s*\n\s*")([0-9a-f]{64})(")')
        match = pattern.search(text)
        if not match:
            problems.append(f"pin anchor not found: {anchor}")
            continue
        path = ROOT / relative
        actual = sha256_file(path) if path.is_file() else None
        if match.group(2) != actual:
            problems.append(f"{relative}: stale pin\n  pinned {match.group(2)}"
                            f"\n  actual {actual}")
    match = RADIOFISHER_PIN.search(text)
    if not match or match.group(2) != radiofisher_digest:
        problems.append("EXPECTED_RADIOFISHER_SOURCE_SHA256 is stale or "
                        "missing")
    return problems


def check(args) -> int:
    if ROOT is None:
        sys.exit("run from a git checkout of RFIsher")
    radiofisher_digest = current_radiofisher_digest(args.radiofisher_dir)
    problems = provenance_problems(radiofisher_digest)
    problems += pin_problems((ROOT / PINS).read_text(encoding="utf-8"),
                             radiofisher_digest)
    for problem in problems:
        print(problem)
    print("bank provenance and pins", "STALE" if problems else "OK")
    return 1 if problems else 0


def repin_after_rebuild(args) -> int:
    if ROOT is None:
        sys.exit("run from a git checkout of RFIsher")
    rebuilt = list(dict.fromkeys(args.banks))
    if not rebuilt:
        sys.exit("--repin takes the paths of the rebuilt banks")
    unknown = sorted(set(rebuilt) - set(BANKS.values()))
    if unknown:
        sys.exit(f"--repin: not a pinned bank: {', '.join(unknown)}")
    radiofisher_digest = current_radiofisher_digest(args.radiofisher_dir)
    problems = provenance_problems(radiofisher_digest, rebuilt)
    if problems:
        for problem in problems:
            print(problem)
        sys.exit("refusing to re-pin banks whose recorded source trees do not "
                 "match the current checkouts")
    pins = {anchor: sha256_file(ROOT / relative)
            for anchor, relative in BANKS.items() if relative in rebuilt}
    text, changes = repin((ROOT / PINS).read_text(encoding="utf-8"), pins)
    text = RADIOFISHER_PIN.sub(
        lambda m: m.group(1) + radiofisher_digest + m.group(3), text, count=1)
    (ROOT / PINS).write_text(text, encoding="utf-8")
    for change in changes:
        print("re-pinned", change)
    print("pins current")
    return 0


def radiofisher_section(explicit=None) -> dict:
    """``provenance.radiofisher`` of a bank built against the checkout now."""
    rf, rf_dir = import_radiofisher(explicit)
    state = banks._git_state(rf_dir, **banks.RADIOFISHER_SOURCE_MANIFEST)
    if state["git_dirty"] is not False or state["git_commit"] is None \
            or state["working_tree_sha256"] is None:
        sys.exit(f"the RadioFisher checkout must be clean: {rf_dir} {state}")
    return {
        "backend_id": getattr(rf, "BACKEND_ID", None),
        "backend_version": getattr(rf, "BACKEND_VERSION", None),
        "api_version": getattr(rf, "BACKEND_API_VERSION", None),
        "capabilities": sorted(backend_capabilities(rf)),
        "source_manifest": {key: list(value) for key, value in
                            banks.RADIOFISHER_SOURCE_MANIFEST.items()},
        **state,
    }


def authenticate_rebound(path: Path, explicit=None) -> None:
    """Raise unless the bank at ``path`` authenticates against the checkout."""
    from rfisher.forecast.radiofisher_bao.response import evaluation_identity

    evaluation_identity(banks.FisherBank(path), rf_dir=explicit)


def rebind(args) -> int:
    if ROOT is None:
        sys.exit("run from a git checkout of RFIsher")
    rebound = list(dict.fromkeys(args.banks))
    if not rebound:
        sys.exit("--rebind takes the paths of the banks to re-bind")
    unknown = sorted(set(rebound) - set(BANKS.values()))
    if unknown:
        sys.exit(f"--rebind: not a pinned bank: {', '.join(unknown)}")
    section = radiofisher_section(args.radiofisher_dir)
    bank_digest = banks.bank_source_state()["working_tree_sha256"]
    date = dt.datetime.now(dt.timezone.utc).date().isoformat()
    staged = []
    for relative in rebound:
        path = ROOT / relative
        infos, data = read_members(path)
        meta = decode_meta(data["meta.npy"])
        if meta["provenance"]["baonoise"]["working_tree_sha256"] \
                != bank_digest:
            sys.exit(f"{relative}: stale bank source digest; a change under "
                     "bank/ takes a rebuild, not a re-bind")
        if "restamp" not in meta:
            sys.exit(f"{relative}: no restamp block to record the re-bind in")
        old = meta["provenance"]["radiofisher"]
        if old == section:
            print(f"{relative}: already bound to {section['git_commit']}")
            continue
        new = json.loads(json.dumps(meta))
        new["provenance"]["radiofisher"] = section
        new["restamp"].setdefault("radiofisher", []).append(
            {"from": old, "date": date, "reason": REBIND_REASON})
        new_data = dict(data, **{"meta.npy": encode_meta(new)})
        with tempfile.TemporaryDirectory() as scratch:
            first, second = Path(scratch) / "a.npz", Path(scratch) / "b.npz"
            write_bank(first, infos, new_data)
            write_bank(second, infos, new_data)
            if first.read_bytes() != second.read_bytes():
                sys.exit(f"{relative}: the two writes differ")
            _, written = read_members(first)
            if any(written[f"{name}.npy"] != data[f"{name}.npy"]
                   for name in NUMERICAL):
                sys.exit(f"{relative}: a numerical member changed")
            if decode_meta(written["meta.npy"]) != new:
                sys.exit(f"{relative}: the metadata did not round-trip")
            banks.FisherBank(first)       # the rebound bank still loads
            if meta["config"] == "chime2022":
                try:
                    authenticate_rebound(first, args.radiofisher_dir)
                except (RuntimeError, ValueError) as exc:
                    sys.exit(f"{relative}: the rebound bank does not "
                             f"authenticate against the checkout: {exc}")
            staged.append((path, first.read_bytes()))
    for path, payload in staged:
        path.write_bytes(payload)
        print(f"re-bound {path.relative_to(ROOT)} to {section['git_commit']}")
    return repin_after_rebuild(args)


def same_arrays(args) -> int:
    committed, rebuilt = (Path(path) for path in args.banks)
    _, old = read_members(committed)
    _, new = read_members(rebuilt)
    differ = [name for name in NUMERICAL
              if old[f"{name}.npy"] != new[f"{name}.npy"]]
    if differ:
        print(f"{rebuilt}: members differ from {committed}: "
              + ", ".join(differ))
        return 1
    print(f"{rebuilt}: the numerical members equal {committed}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true",
                      help="verify the pins and the recorded provenance; "
                           "write nothing")
    mode.add_argument("--repin", action="store_true",
                      help="re-pin the named banks, rebuilt from the current "
                           "source")
    mode.add_argument("--rebind", action="store_true",
                      help="re-stamp the named banks' RadioFisher section to "
                           "the checkout found now, then re-pin them")
    mode.add_argument("--same-arrays", action="store_true",
                      help="compare the numerical members of two banks")
    ap.add_argument("--subset", action="store_true",
                    help="let a re-stamp cover only some of the pinned banks")
    ap.add_argument("--radiofisher-dir", type=Path)
    ap.add_argument("--from-commit", help="the commit that built the banks")
    ap.add_argument("--baseline", type=Path,
                    help="a checkout of --from-commit")
    ap.add_argument("--baseline-python", default=sys.executable,
                    help="the interpreter of the baseline authentication")
    ap.add_argument("--record", type=Path,
                    help="write a JSON record of the re-stamp here")
    ap.add_argument("banks", nargs="*", metavar="BANK=OUT",
                    help="re-stamp pairs; with --repin or --rebind, the bank "
                         "paths; with --same-arrays, the two banks")
    args = ap.parse_args(argv)
    if args.check:
        return check(args)
    if args.repin:
        return repin_after_rebuild(args)
    if args.rebind:
        return rebind(args)
    if args.same_arrays:
        if len(args.banks) != 2:
            ap.error("--same-arrays takes COMMITTED REBUILT")
        return same_arrays(args)
    if not (args.from_commit and args.baseline and args.banks):
        ap.error("a re-stamp needs --from-commit, --baseline and BANK=OUT "
                 "pairs")
    return restamp(args)


if __name__ == "__main__":
    raise SystemExit(main())
