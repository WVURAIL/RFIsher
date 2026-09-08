"""Stable zeta = 1 bias tolerances per ATSC channel, one home.

These constants were previously duplicated (and, worse, derived on two
different footings) across scripts/optimal_thresholds.py,
scripts/calibrated_thresholds.py, and scripts/dissertation/make_two_walls.py.
They are the stable zeta = 1 minima of the dense bias-response bank
(``scripts/bias_tolerance.py --zeta 1.0`` on the ``--p-res 1.0 --dense-knee``
build), taken over the accepted multi-year grid --- the same convention for
every channel, upper and lower band alike. The retired practice of extending
the lower band from the completed-forecast ledger's single 1-on-sky-year
point priced ch14-26 against tolerances up to ~1.8x looser than the
convention applied to ch27-36; every consumer now imports these.

Keys are ATSC channel numbers; a channel straddling a bin boundary carries
the tolerance of the bin that binds it. That is the higher-z (lower
frequency) of its two bins, read off the six straddling channels themselves:
ch17, 20, 23 and 26 carry bins 11, 10, 9 and 8 in TOL_APERP, and ch30 and 34
carry bins 7 and 6 in TOL_FS8. It is a positional rule and not a "take the
smaller of the two", so it disagrees with the released channel mapping's own
rule (``mapping_rule`` in ``forecast_completion_channel_mapping.csv`` is
"minimum accepted tolerance over every nonzero-overlap bin") wherever the
higher-z bin is the looser. For the growth rate that is five of the six
straddlers, ch17 alone landing on the release's own binding bin; the
dilations are not counted here, because their published ch27--36 block was
never re-derived and a comparison against it would be measuring that
instead. Where a
verdict turns on a straddling channel, quote the release's conservative
number beside it: for f sigma_8 that is ch20 0.00181 against 0.00195,
ch23 0.00171 against 0.00181, ch26 0.00160 against 0.00172, and, among the
published ten, ch30 0.00153 against 0.0016 and ch34 0.00150 against 0.00153.

Derivation, and how much of it reproduces. Both tables were re-derived from
``data/fisher_bank_chime2022_pres_dense.npz`` over the
``archive_reference.bias_year_grid`` samples (0.25, 1, 5, 10 on-sky years),
keeping the integration times the registered response-stability gate accepts
(``science.response_stability``: the tolerance moves by no more than 1.20
across a +/-10 per cent perturbation in time, with no sign flip in the
response) and taking the smallest accepted tolerance. That recomputation
returns TOL_APERP exactly for ch14-26 and TOL_FS8 exactly for ch27-34, which
is the evidence the f sigma_8 entries added for ch14-26 sit on the published
footing rather than beside it. It does not return the ch27-36 TOL_APERP
block, nor TOL_FS8 for ch35-36 (0.00156 published against 0.00150 from the
bank, and no year grid, gate or straddle convention searched reproduces
0.00156). Those are the survivors of the hard-coded ch27-36 table that
scripts/channel_tolerances.py names, they are left exactly as they stood,
and nothing here claims they were re-derived.
"""
from __future__ import annotations

# alpha_perp (transverse acoustic dilation), stable zeta = 1 minima.
# ch14-17: bin 1.90-2.04; ch18-20: 1.80-1.90; ch21-23: 1.70-1.80;
# ch24-26: 1.60-1.70; ch27-29: 1.50-1.60; ch30 straddles; ch31-34: 1.40-1.50;
# ch35-36: 1.30-1.40.
TOL_APERP = {
    14: 0.0201, 15: 0.0201, 16: 0.0201, 17: 0.0201,
    18: 0.012, 19: 0.012, 20: 0.012,
    21: 0.00757, 22: 0.00757, 23: 0.00757,
    24: 0.00672, 25: 0.00672, 26: 0.00672,
    27: 0.014, 28: 0.014, 29: 0.014, 30: 0.0144,
    31: 0.0156, 32: 0.0156, 33: 0.0156, 34: 0.0156,
    35: 0.0352, 36: 0.0352,
}

# f sigma_8 (growth), same build, same bins, three significant figures with
# trailing zeros dropped (0.0016 is bin 7's 0.00160363).
#
# ch14-26 were unpriced until now because nobody had run the growth-rate
# minimum for their bins, not because the science refuses them: on this bank
# the stability gate accepts f sigma_8 at all four grid times in all fifteen
# forecast bins (aperp, by contrast, survives at only one of the four in the
# 1.50-1.60 bin). The frozen ledger agrees independently --- every one of the
# 23 channels carries ``perbin_status = accepted`` against ``shared_target =
# fs8`` in forecast_completion_channel_mapping.csv, and its own per-channel
# tolerances sit within one unit of the last figure quoted here wherever the
# two rules pick the same bin (tests/test_tolerances.py checks sixteen of
# them). The minimum falls at the 1-on-sky-year sample in every DTV
# bin, which is why the retired single-year footing does not loosen the lower
# band here the way it did for alpha_perp.
TOL_FS8 = {
    14: 0.00177, 15: 0.00177, 16: 0.00177, 17: 0.00177,
    18: 0.00195, 19: 0.00195, 20: 0.00195,
    21: 0.00181, 22: 0.00181, 23: 0.00181,
    24: 0.00172, 25: 0.00172, 26: 0.00172,
    27: 0.0016, 28: 0.0016, 29: 0.0016, 30: 0.0016,
    31: 0.00153, 32: 0.00153, 33: 0.00153, 34: 0.00153,
    35: 0.00156, 36: 0.00156,
}
