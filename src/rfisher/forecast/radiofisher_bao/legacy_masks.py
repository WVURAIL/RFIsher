"""The ATSC UHF channel plan: channels 14 to 36 on 6 MHz from 470 MHz.

:data:`.scenarios.DTV_BAND` and the dissertation's forecast builders read the
channel edges here. The legacy rate table that this module also carried (the
July 2026 masking input of the legacy forecast scenarios) left the head on
2026-10-08; it is ``src/rfisher/data/survey_quarterly_rates_all23.csv@c7c3949``
and its reader is this module at that commit. A forecast over arbitrary bands
should build :class:`.scenarios.FrequencyBand` intervals directly rather than
press these channel numbers into service.
"""
from __future__ import annotations

ATSC_CH14_LOWER_EDGE = 470.0  # MHz
ATSC_WIDTH = 6.0              # MHz
ATSC_DTV_CHANNELS = tuple(range(14, 37))
ATSC_DTV_UPPER_EDGE = (
    ATSC_CH14_LOWER_EDGE + len(ATSC_DTV_CHANNELS) * ATSC_WIDTH)


def channel_edges(ch: int) -> tuple[float, float]:
    """Lower/upper frequency edge [MHz] of an ATSC UHF physical channel.

    Only channels 14-36 are accepted: the linear ``470 + 6*(ch - 14)`` map
    holds nowhere else (VHF channels 2-13 sit in disjoint low bands, and
    channels above 36 were cleared in the repack), so any other channel
    number would be assigned a frequency no transmitter uses.
    """
    if ch not in ATSC_DTV_CHANNELS:
        raise ValueError(
            f"channel {ch} is not an ATSC UHF DTV channel; supported "
            f"channels are {ATSC_DTV_CHANNELS[0]}-{ATSC_DTV_CHANNELS[-1]}")
    lo = ATSC_CH14_LOWER_EDGE + (ch - 14) * ATSC_WIDTH
    return lo, lo + ATSC_WIDTH
