#!/bin/bash
# Rebuild the four shipped Fisher banks with their exact release recipe,
# copy them into place, and re-pin tests/test_resources.py.
#
# Banks record a working_tree_sha256 over pyproject + src/rfisher/*.py at
# build time, so run this AFTER all source changes are final, from a clean
# tree, and commit the banks + pins together as a re-stamp commit.
#
# Requires an installed rfisher (rfisher-build-bank on PATH) and a
# RadioFisher checkout: $RADIOFISHER_DIR, or the ../RadioFisher sibling
# that RFIsher finds automatically.
#
#   NPROC=24 scripts/rebuild_shipped_banks.sh [workdir]
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -n "$(git status --porcelain -- pyproject.toml src/rfisher)" ]; then
  echo "ERROR: pyproject/src/rfisher must be clean before rebuilding banks." >&2
  echo "Commit the source cleanup first; dirty banks fail release provenance." >&2
  exit 1
fi

WORK=${1:-$(mktemp -d)}
NPROC=${NPROC:-$(nproc)}
RF_ARGS=()
[ -n "${RADIOFISHER_DIR:-}" ] && RF_ARGS=(--radiofisher-dir "$RADIOFISHER_DIR")
# One targeted point resolves the Bull bin-8 interpolation knee at 3,300 hr
# without moving any of the 27 release-grid points. Keep the decimal literal:
# it is Python's round-trip representation of 10**3.5 hours.
BULL_KNEE_HOURS=3162.2776601683795
rfisher-build-bank --version

build() {  # outfile, then rfisher-build-bank args
  local out=$1; shift
  echo "=== building $out ($(date +%H:%M:%S)) ==="
  rfisher-build-bank --out "$WORK/$out" --nt 27 --nproc "$NPROC" \
    "${RF_ARGS[@]}" "$@" 2>&1 | tail -3
  echo "done $out ($(date +%H:%M:%S))"
}

build fisher_bank_chime2022.npz          --config chime2022 --cosmology planck2018
build fisher_bank_chime2022_pact2025.npz --config chime2022 --cosmology pact2025
build fisher_bank_bull2015_planck2013_epsfg1e-6.npz \
      --config bull2015 --cosmology planck2013 --epsilon-fg 1e-6 \
      --extra-time-hours "$BULL_KNEE_HOURS"
build fisher_bank_bull2015_planck2013_epsfg1e-5.npz \
      --config bull2015 --cosmology planck2013 --epsilon-fg 1e-5 \
      --extra-time-hours "$BULL_KNEE_HOURS"

cp "$WORK/fisher_bank_chime2022.npz"          src/rfisher/data/
cp "$WORK/fisher_bank_chime2022_pact2025.npz" src/rfisher/data/
cp "$WORK/fisher_bank_bull2015_planck2013_epsfg1e-6.npz" data/
cp "$WORK/fisher_bank_bull2015_planck2013_epsfg1e-5.npz" data/
python scripts/fg_sensitivity.py

# Verify before re-signing anything: a pin must certify banks that already
# passed the physics gates, not whatever bytes the build produced. set -e
# aborts the re-stamp on any failure below.
python scripts/verify_bank.py --bank src/rfisher/data/fisher_bank_chime2022.npz
python scripts/verify_bank.py --bank src/rfisher/data/fisher_bank_chime2022_pact2025.npz
# The pins still describe the pre-rebuild state here, so every pin-checking
# test is deselected and run again after the re-stamp below; everything else
# (provenance vs the live source trees, direct-backend agreement) must pass
# first. test_named_banks_are_distinct_matched_v3_builds is on that list
# because it also asserts EXPECTED_RADIOFISHER_SOURCE_SHA256, which the
# re-stamp maintains: leaving it selected made this step fail on exactly the
# backend change the pin exists to record. Re-signing is still gated, by
# restamp_bank_pins.py's own provenance check.
python -m pytest tests/test_resources.py -q \
  --deselect tests/test_resources.py::test_packaged_data_bytes_are_unchanged \
  --deselect tests/test_resources.py::test_named_banks_are_distinct_matched_v3_builds \
  --deselect tests/test_resources.py::test_bull_research_banks_are_matched_strict_v2_v3_builds

python scripts/restamp_bank_pins.py
python scripts/check_paper_numbers.py
python -m pytest -q \
  tests/test_resources.py::test_packaged_data_bytes_are_unchanged \
  tests/test_resources.py::test_named_banks_are_distinct_matched_v3_builds \
  tests/test_resources.py::test_bull_research_banks_are_matched_strict_v2_v3_builds
echo "ALL SHIPPED BANKS REBUILT, VERIFIED, AND RE-PINNED (workdir: $WORK)"
echo "foreground_sensitivity.csv regenerated and paper-number gate passed."
echo "Now: commit banks + pins together as the re-stamp commit."
