"""The one home for the zeta = 1 bias tolerances: coverage and derivation.

Two things are worth pinning about :mod:`rfisher.tolerances`. The first is
coverage: every consumer keys off ``ch in TOL_FS8``, so a channel that drops
out of the table does not fail, it silently stops being priced --- which is
how chapter 9's growth-rate verdict came to be stated for ten channels and
dashed for thirteen. The second is the derivation, because the constants are
literals: nothing in the package recomputes them, the dense bias-response
bank they came from is deliberately not shipped, and without a check against
something on disk a wrong digit is indistinguishable from a right one.

The check used here is the frozen forecast release
(``forecast_completion_channel_mapping.csv``), which prices f sigma_8 per
channel from the completed-forecast ledger at one on-sky year. That is an
independent path to the same quantity --- the constants are the smallest
tolerance the response-stability gate accepts over
``archive_reference.bias_year_grid``, and the ledger reports a single time
--- so agreement between them is evidence, not a tautology. It is available
only where the results tree is on the machine, so those tests skip rather
than pretend.
"""
from __future__ import annotations

import csv
import math

import pytest

from rfisher import tolerances
from rfisher_results.results_tree import out_dir

CHANNELS = tuple(range(14, 37))
MAPPING_NAME = "forecast_completion_channel_mapping.csv"
FAMILY = "noise_shaped"

# The forecast bin each channel is priced against: its own bin, or for the six
# straddling channels the higher-z of its two, the convention the module
# docstring reads off the published constants themselves. Recorded here so the
# grouping tests below have something to group by;
# ``test_the_binding_bins_are_the_released_mapping_s`` checks it against the
# release wherever that tree is on the machine.
BINDING_BIN = {14: 11, 15: 11, 16: 11, 17: 11,
               18: 10, 19: 10, 20: 10,
               21: 9, 22: 9, 23: 9,
               24: 8, 25: 8, 26: 8,
               27: 7, 28: 7, 29: 7, 30: 7,
               31: 6, 32: 6, 33: 6, 34: 6,
               35: 5, 36: 5}

# One unit in the third significant figure, which is all the constants carry.
# Every value here is a few times 1e-3, so that unit is 1e-5 for all of them.
LAST_DIGIT = 1e-5

# The two constants the recomputation does not return. They are what is left
# of the hard-coded ch27-36 table scripts/channel_tolerances.py names: the
# dense bank puts ch35-36 at 0.00150, and no year grid, stability gate or
# straddle convention searched produces 0.00156. Pinned so that re-deriving
# them is a deliberate act with its own evidence rather than a quiet edit.
LEGACY_FS8 = (35, 36)


def _released_mapping():
    """``{channel: row}`` from the frozen release, or ``None`` off-machine."""
    path = out_dir() / MAPPING_NAME
    if not path.is_file():
        return None
    with path.open(newline="", encoding="utf-8") as fh:
        return {int(r["channel"]): r for r in csv.DictReader(fh)
                if r["family"] == FAMILY}


def test_both_tables_price_every_dtv_channel():
    assert tuple(sorted(tolerances.TOL_APERP)) == CHANNELS
    assert tuple(sorted(tolerances.TOL_FS8)) == CHANNELS


def test_the_growth_constants_are_the_dense_bank_minima():
    """The values, spelled out, so a drift shows up here and not in a figure.

    ch14-26 are the stable zeta = 1 minima of
    data/fisher_bank_chime2022_pres_dense.npz over the 0.25/1/5/10 on-sky-year
    samples of ``archive_reference.bias_year_grid``, three significant
    figures; ch27-36 are unchanged from the published table.
    """
    assert tolerances.TOL_FS8 == {
        14: 0.00177, 15: 0.00177, 16: 0.00177, 17: 0.00177,
        18: 0.00195, 19: 0.00195, 20: 0.00195,
        21: 0.00181, 22: 0.00181, 23: 0.00181,
        24: 0.00172, 25: 0.00172, 26: 0.00172,
        27: 0.0016, 28: 0.0016, 29: 0.0016, 30: 0.0016,
        31: 0.00153, 32: 0.00153, 33: 0.00153, 34: 0.00153,
        35: 0.00156, 36: 0.00156,
    }


def test_the_published_dilation_constants_are_untouched():
    """Extending the growth table must not disturb the tier the selector uses.

    ``r_tol_dilation`` is alpha_perp (rfisher_results.archive.tolerances), so
    every operating point in chapter 9 rests on these twenty-three numbers.
    """
    assert tolerances.TOL_APERP == {
        14: 0.0201, 15: 0.0201, 16: 0.0201, 17: 0.0201,
        18: 0.012, 19: 0.012, 20: 0.012,
        21: 0.00757, 22: 0.00757, 23: 0.00757,
        24: 0.00672, 25: 0.00672, 26: 0.00672,
        27: 0.014, 28: 0.014, 29: 0.014, 30: 0.0144,
        31: 0.0156, 32: 0.0156, 33: 0.0156, 34: 0.0156,
        35: 0.0352, 36: 0.0352,
    }


def test_channels_sharing_a_binding_bin_share_a_growth_constant():
    """A per-bin quantity cannot vary within a bin.

    The tolerance is inverted from one bin's Fisher matrix, so two channels
    priced against the same bin must carry the same number; anything else is a
    transcription slip rather than a physical difference.
    """
    by_bin = {}
    for channel, ib in BINDING_BIN.items():
        by_bin.setdefault(ib, set()).add(tolerances.TOL_FS8[channel])
    assert {ib: sorted(v) for ib, v in by_bin.items() if len(v) > 1} == {}


def test_the_legacy_dilation_block_is_the_one_break_in_that_grouping():
    """ch30 carries 0.0144 where its bin carries 0.014, and ch35-36 sit at
    0.0352 where the bank returns 0.0116.

    The lower band (ch14-26) obeys the grouping exactly, which is what makes
    it a re-derivation; ch27-36 is the surviving hard-coded table, and this
    records where the two disagree so the dissertation does not describe the
    whole of TOL_APERP as re-derived.
    """
    lower = {}
    for channel, ib in BINDING_BIN.items():
        if channel <= 26:
            lower.setdefault(ib, set()).add(tolerances.TOL_APERP[channel])
    assert {ib: sorted(v) for ib, v in lower.items() if len(v) > 1} == {}
    assert BINDING_BIN[30] == BINDING_BIN[27]
    assert tolerances.TOL_APERP[30] != tolerances.TOL_APERP[27]


def test_growth_is_the_tighter_tier_on_every_channel():
    """Chapter 9 calls f sigma_8 the binding secondary; that only means
    something if it is in fact tighter than the dilation tier everywhere."""
    looser = [ch for ch in CHANNELS
              if tolerances.TOL_FS8[ch] >= tolerances.TOL_APERP[ch]]
    assert looser == []


def test_the_binding_bins_are_the_released_mapping_s():
    """The recorded binding bin is the release's highest-z overlap bin."""
    rows = _released_mapping()
    if rows is None:
        pytest.skip("the forecast release tree is not on this machine")
    released = {ch: int(r["overlap_bin_indices"].split(";")[-1])
                for ch, r in rows.items()}
    assert released == BINDING_BIN


def test_the_release_prices_growth_for_every_channel_it_maps():
    """No channel is unpriced because the gate refused it.

    This is the evidence behind the module's claim that ch14-26 were unpriced
    by omission: the release records ``accepted`` for the growth target on all
    twenty-three, so there was never a refusal to report.
    """
    rows = _released_mapping()
    if rows is None:
        pytest.skip("the forecast release tree is not on this machine")
    assert sorted(rows) == list(CHANNELS)
    assert {r["shared_target"] for r in rows.values()} == {"fs8"}
    refused = {ch: r["perbin_status"] for ch, r in rows.items()
               if r["perbin_status"] != "accepted"}
    assert refused == {}


def test_the_constants_agree_with_the_release_where_they_share_a_bin():
    """Two derivations, one number.

    The release takes the ledger's single one-on-sky-year point and the
    smallest tolerance over every bin a channel overlaps; the constants take
    the multi-year accepted minimum and the higher-z bin. The two rules pick
    the same bin except at the six straddling channels, and where they do the
    numbers must agree to the last figure the constants carry --- they do, to
    better than a tenth of it, because the multi-year minimum falls at one
    year in every DTV bin. ch35-36 are the documented legacy pair and are
    excluded by name rather than by loosening the criterion.
    """
    rows = _released_mapping()
    if rows is None:
        pytest.skip("the forecast release tree is not on this machine")
    checked, gaps = [], {}
    for ch, r in sorted(rows.items()):
        if int(r["perbin_binding_bin"]) != BINDING_BIN[ch] or ch in LEGACY_FS8:
            continue
        checked.append(ch)
        gap = abs(float(r["perbin_conservative_tolerance"])
                  - tolerances.TOL_FS8[ch])
        if gap > LAST_DIGIT:
            gaps[ch] = gap
    assert gaps == {}
    assert len(checked) >= 15, "too few channels compared to be evidence"
    legacy = {ch: abs(float(rows[ch]["perbin_conservative_tolerance"])
                      - tolerances.TOL_FS8[ch]) for ch in LEGACY_FS8}
    assert all(gap > LAST_DIGIT for gap in legacy.values()), legacy
    assert all(math.isfinite(gap) for gap in legacy.values())
