"""RFIsher: how much residual DTV power each 6 MHz channel tolerates.

For each channel, one RadioFisher forecast at the channel's own redshift gives
the clean one-year uncertainty of the two BAO dilations and the bias a coherent
DTV residual of unit strength adds to each. Bias is proportional to strength,
so the channel's first-order tolerance is the strength at which the combined
volume-distance bias equals its clean uncertainty. Full coherence is assumed;
residual strength is supplied directly at the forecast exposure, without
stacking, gamma estimation, or temporal-gain fits. nonlinear.py separately
checks finite amplitudes in an expected-covariance model.

    bands       the channels and their redshifts
    inputs      the fixed forecast inputs: cosmology, P(k) table, CHIME, one year
    residual    the coherent DTV residual (a flat 6 MHz shelf)
    forecast    one channel's Fisher matrix, with the residual's bias row
    tolerance   uncertainties, bias per unit strength, tolerance
    table       all channels, written with provenance
    nonlinear   finite-amplitude expected-likelihood checks
    figures     per-channel plates and the summary
"""
__version__ = "1.0.0"

from . import tolerance
from .bands import Band, channels
from .forecast import channel_fisher
from .table import build_table, read_table

__all__ = ["Band", "build_table", "channel_fisher", "channels", "read_table", "tolerance"]
