#!/usr/bin/env python3
"""Re-pin the shipped Fisher banks' SHA-256 hashes after a rebuild.

The four shipped banks are pinned in tests/test_resources.py (the two
packaged CHIME banks under EXPECTED_SHA256, the two repo-data Bull-2015
banks under BULL_BANK_SHA256). After scripts/rebuild_shipped_banks.sh
replaces the bank files, this rewrites each pin in place, keyed by the
dict entry's anchor rather than the old hash value, so it works from any
starting state. ``--check`` verifies the current pins against the current
files and changes nothing.

A byte pin certifies identity, not freshness: re-signing whatever bytes
sit at the bank paths would happily bless a bank built from an outdated
source tree. Before touching the pins, each bank's recorded baonoise and
RadioFisher ``working_tree_sha256`` is therefore compared against the
current checkouts, and the script refuses on any mismatch (or if no
RadioFisher checkout is discoverable). ``--allow-stale-provenance``
proceeds anyway, printing every mismatch.

    python scripts/restamp_bank_pins.py [--check] [--allow-stale-provenance]
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests" / "test_resources.py"

# pin anchor in tests/test_resources.py -> bank file in the checkout
BANKS = {
    "resources.DEFAULT_BANK_NAME:":
        "src/baonoise/data/fisher_bank_chime2022.npz",
    "resources.PACT2025_BANK_NAME:":
        "src/baonoise/data/fisher_bank_chime2022_pact2025.npz",
    '"fisher_bank_bull2015_planck2013_epsfg1e-6.npz":':
        "data/fisher_bank_bull2015_planck2013_epsfg1e-6.npz",
    '"fisher_bank_bull2015_planck2013_epsfg1e-5.npz":':
        "data/fisher_bank_bull2015_planck2013_epsfg1e-5.npz",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stale_provenance() -> list[str]:
    """Compare each bank's recorded source trees against the checkouts.

    Uses the same digests the tests enforce: ``fisherbank._git_state`` over
    the release source manifests, with the RadioFisher checkout discovered
    exactly as ``find_radiofisher_dir`` does (env RADIOFISHER_DIR overrides).
    A missing checkout is a hard error, not a skipped check.
    """
    from baonoise import fisherbank
    from baonoise.compat import find_radiofisher_dir

    try:
        radiofisher_root = find_radiofisher_dir()
    except FileNotFoundError as exc:
        sys.exit(
            "cannot verify bank provenance: no RadioFisher checkout found\n"
            f"  ({exc})\n"
            "Set RADIOFISHER_DIR to the checkout the banks were built from; "
            "the provenance gate is never skipped silently.")

    current = {
        "baonoise": fisherbank._git_state(
            ROOT, **fisherbank.BAONOISE_SOURCE_MANIFEST)
            ["working_tree_sha256"],
        "radiofisher": fisherbank._git_state(
            radiofisher_root, **fisherbank.RADIOFISHER_SOURCE_MANIFEST)
            ["working_tree_sha256"],
    }
    mismatches = []
    for rel in BANKS.values():
        provenance = fisherbank.FisherBank(ROOT / rel).meta["provenance"]
        for link, current_digest in current.items():
            recorded = provenance[link]["working_tree_sha256"]
            if recorded != current_digest:
                mismatches.append(
                    f"{Path(rel).name}: stale {link} provenance\n"
                    f"  recorded {recorded}\n"
                    f"  current  {current_digest}")
    return mismatches, current


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="verify pins against the bank files; write nothing")
    ap.add_argument("--allow-stale-provenance", action="store_true",
                    help="re-pin even when a bank's recorded source trees do "
                         "not match the current checkouts (printed loudly)")
    args = ap.parse_args(argv)

    mismatches, current = stale_provenance()
    for message in mismatches:
        print(message)
    if mismatches and not args.check:
        if args.allow_stale_provenance:
            print("WARNING: re-pinning despite stale provenance "
                  "(--allow-stale-provenance)")
        else:
            sys.exit(
                "refusing to re-pin: the banks above record source trees "
                "that do not match the current checkouts. Rebuild via "
                "scripts/rebuild_shipped_banks.sh, or pass "
                "--allow-stale-provenance to re-sign them anyway.")

    text = TESTS.read_text(encoding="utf-8")
    stale = 0
    for anchor, rel in BANKS.items():
        new = sha(ROOT / rel)
        pattern = re.compile(
            "(" + re.escape(anchor) + r'\s*\n\s*")([0-9a-f]{64})(")')
        m = pattern.search(text)
        if not m:
            sys.exit(f"pin anchor not found in {TESTS}: {anchor}")
        old = m.group(2)
        name = Path(rel).name
        if old == new:
            print(f"{name}: pin current")
            continue
        stale += 1
        if args.check:
            print(f"{name}: STALE pin\n  pinned {old}\n  actual {new}")
        else:
            text = pattern.sub(lambda mm: mm.group(1) + new + mm.group(3),
                               text, count=1)
            print(f"{name}: re-pinned\n  {old} -> {new}")
    # The RadioFisher source digest is a pin of the same class as the byte
    # pins: it certifies which backend tree the banks record, and it goes
    # stale in exactly the same rebuild. Maintain it here, behind the same
    # provenance gate, so a backend transition cannot leave it dangling.
    rf_pattern = re.compile(
        r'(EXPECTED_RADIOFISHER_SOURCE_SHA256 = \(\s*\n\s*")'
        r'([0-9a-f]{64})(")')
    rf_m = rf_pattern.search(text)
    if not rf_m:
        sys.exit(f"EXPECTED_RADIOFISHER_SOURCE_SHA256 not found in {TESTS}")
    if rf_m.group(2) != current["radiofisher"]:
        stale += 1
        if args.check:
            print(f"EXPECTED_RADIOFISHER_SOURCE_SHA256: STALE pin\n"
                  f"  pinned {rf_m.group(2)}\n"
                  f"  actual {current['radiofisher']}")
        else:
            text = rf_pattern.sub(
                lambda mm: mm.group(1) + current["radiofisher"] + mm.group(3),
                text, count=1)
            print(f"EXPECTED_RADIOFISHER_SOURCE_SHA256: re-pinned\n"
                  f"  {rf_m.group(2)} -> {current['radiofisher']}")
    else:
        print("EXPECTED_RADIOFISHER_SOURCE_SHA256: pin current")
    if args.check:
        print("provenance", "STALE" if mismatches else "OK")
        print("pins", "STALE" if stale else "OK")
        return 1 if stale or mismatches else 0
    if stale:
        TESTS.write_text(text, encoding="utf-8")
        print(f"updated {stale} pin(s) in {TESTS}")
    else:
        print("all pins already current; nothing written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
