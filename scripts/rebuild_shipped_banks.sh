#!/bin/bash
# Rebuild the five shipped Fisher banks with their exact release recipe,
# check that every rebuilt array equals the committed bank's, copy them into
# place, and re-pin them in tests/forecast/test_resources.py.
#
# This is the fallback to the one metadata re-stamp: it spends about 35
# minutes where the re-stamp spends seconds. A bank records the digest of the
# bank subpackage src/rfisher/forecast/radiofisher_bao/bank at build time,
# so run this from a clean bank/ and commit the banks and pins together.
#
# The four filter-scenario response banks are never rebuilt here. They take
# the metadata re-stamp, before this script runs: restamp_bank_provenance.py
# --subset with their four BANK=OUT pairs, then a commit. The re-pin below
# covers only the five banks rebuilt here, and the closing --check covers
# all nine.
#
# Requires an installed rfisher (the rfisher command on PATH, from this
# checkout) and a RadioFisher checkout: $RADIOFISHER_DIR, or the
# ../RadioFisher sibling that RFIsher finds automatically.
#
#   NPROC=24 scripts/rebuild_shipped_banks.sh [workdir]
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -n "$(git status --porcelain -- src/rfisher/forecast/radiofisher_bao/bank)" ]; then
  echo "ERROR: the bank subpackage must be clean before rebuilding banks." >&2
  echo "Commit the source first; a dirty build fails release provenance." >&2
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
rfisher --version

build() {  # outfile, then rfisher build-bank args
  local out=$1; shift
  echo "=== building $out ($(date +%H:%M:%S)) ==="
  rfisher build-bank --out "$WORK/$out" --nt 27 --nproc "$NPROC" \
    "${RF_ARGS[@]}" "$@" 2>&1 | tail -3
  echo "done $out ($(date +%H:%M:%S))"
}

build fisher_bank_chime2022.npz          --config chime2022 --cosmology planck2018
build fisher_bank_chime2022_pact2025.npz --config chime2022 --cosmology pact2025
build fisher_bank_chime2022_cmbspa2026.npz --config chime2022 --cosmology cmbspa2026
build fisher_bank_bull2015_planck2013_epsfg1e-6.npz \
      --config bull2015 --cosmology planck2013 --epsilon-fg 1e-6 \
      --extra-time-hours "$BULL_KNEE_HOURS"
build fisher_bank_bull2015_planck2013_epsfg1e-5.npz \
      --config bull2015 --cosmology planck2013 --epsilon-fg 1e-5 \
      --extra-time-hours "$BULL_KNEE_HOURS"

SHIPPED=(
  src/rfisher/data/fisher_bank_chime2022.npz
  src/rfisher/data/fisher_bank_chime2022_pact2025.npz
  src/rfisher/data/fisher_bank_chime2022_cmbspa2026.npz
  data/fisher_bank_bull2015_planck2013_epsfg1e-6.npz
  data/fisher_bank_bull2015_planck2013_epsfg1e-5.npz
)
# A rebuild replaces provenance only: every numerical member must equal the
# committed bank's, byte for byte, or nothing is copied.
for bank in "${SHIPPED[@]}"; do
  git show "HEAD:$bank" > "$WORK/committed_$(basename "$bank")"
  python scripts/restamp_bank_provenance.py --same-arrays \
    "$WORK/committed_$(basename "$bank")" "$WORK/$(basename "$bank")"
done
for bank in "${SHIPPED[@]}"; do
  cp "$WORK/$(basename "$bank")" "$bank"
done

# Verify before re-signing anything: a pin must certify banks that already
# passed the physics gates, not whatever bytes the build produced. set -e
# aborts the re-pin on any failure below.
python scripts/verify_bank.py --bank src/rfisher/data/fisher_bank_chime2022.npz
python scripts/verify_bank.py --bank src/rfisher/data/fisher_bank_chime2022_pact2025.npz
python scripts/verify_bank.py --bank src/rfisher/data/fisher_bank_chime2022_cmbspa2026.npz
# The pins still describe the pre-rebuild state here, so every pin-checking
# test is deselected and run again after the re-pin below; everything else
# (provenance against the live source trees, direct-backend agreement) must
# pass first. Re-pinning is still gated, by restamp_bank_provenance.py's own
# provenance check.
python -m pytest tests/forecast/test_resources.py -q \
  --deselect tests/forecast/test_resources.py::test_packaged_data_bytes_are_unchanged \
  --deselect tests/forecast/test_resources.py::test_named_banks_are_distinct_matched_v3_builds \
  --deselect tests/forecast/test_resources.py::test_bull_research_banks_are_matched_strict_v2_v3_builds

python scripts/restamp_bank_provenance.py --repin "${SHIPPED[@]}"
python scripts/restamp_bank_provenance.py --check
python -m pytest -q \
  tests/forecast/test_resources.py::test_packaged_data_bytes_are_unchanged \
  tests/forecast/test_resources.py::test_named_banks_are_distinct_matched_v3_builds \
  tests/forecast/test_resources.py::test_bull_research_banks_are_matched_strict_v2_v3_builds
echo "ALL SHIPPED BANKS REBUILT, VERIFIED, AND RE-PINNED (workdir: $WORK)"
echo "Now: commit banks + pins together."
