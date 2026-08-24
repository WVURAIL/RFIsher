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
the tolerance of the bin that binds it.
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

# f sigma_8 (growth), same build, channels with published constants.
TOL_FS8 = {
    27: 0.0016, 28: 0.0016, 29: 0.0016, 30: 0.0016,
    31: 0.00153, 32: 0.00153, 33: 0.00153, 34: 0.00153,
    35: 0.00156, 36: 0.00156,
}
