"""The July 2026 masking inputs of the legacy forecast scenarios.

The scenario builders of :mod:`.scenarios`, and ``scripts/verify_bank.py``,
``scripts/run_forecast.py`` and :mod:`rfisher.plots`, read one channel plan
and one vendored rate table: the ATSC UHF channels 14 to 36 on 6 MHz from
470 MHz, and ``survey_quarterly_rates_all23.csv`` (pilot-proxy
``data/provenance/survey_stratum_20260718/``). That table's provenance is
identified: ``analysis/survey_composition.py`` produced it on 2026-07-18 with
the coarse rule ``F > mu_hat + 0.012 * mu0`` (about five null widths above
each channel's empirical zero point) from the *first* production trawl,
whose weight bank (sha256 ``b0dce17a...``, kept as
``weights/legacy_halfband/``) assumed the coarse-channel center at Nyquist
and was mistuned by fs/2 relative to the verified center-at-DC frame
convention. Pilots were suppressed by 39-47 dB at the line on every channel
except 30, whose pilot sits 847 Hz from fs/4 where that error self-cancels.
The table is therefore a record of the legacy epoch, not an occupancy
measurement; :func:`legacy_rate_table` wraps it with that rule and epoch so
the limitation is visible rather than implied.

Channels 24 and 30 had no calibrated zero point in the detector of that
epoch (the transmitter is essentially always on); they are modelled as masked
at REFUSED_FRACTION. A forecast over arbitrary bands should build
:class:`.scenarios.FrequencyBand` intervals directly rather than press these
channel numbers into service.
"""
from __future__ import annotations

import csv
import warnings
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .bank.physics import HI_REST_FREQUENCY_MHZ
from .bank.resources import data_file

DEFAULT_RATES_NAME = "survey_quarterly_rates_all23.csv"
DEFAULT_RATES_CSV = data_file(DEFAULT_RATES_NAME)

ATSC_CH14_LOWER_EDGE = 470.0  # MHz
ATSC_WIDTH = 6.0              # MHz
ATSC_DTV_CHANNELS = tuple(range(14, 37))
ATSC_DTV_UPPER_EDGE = (
    ATSC_CH14_LOWER_EDGE + len(ATSC_DTV_CHANNELS) * ATSC_WIDTH)

# Channels with no calibrated zero point in pilot-proxy (persistently on-air).
REFUSED_CHANNELS = (24, 30)
REFUSED_FRACTION = 0.97       # masked fraction adopted for refused channels

# Provenance of the vendored quarterly CSV (see the module docstring).
LEGACY_CSV_RULE = (
    "coarse F > mu_hat + 0.012*mu0 on the empirical zero point "
    "(pilot-proxy analysis/survey_composition.py, 2026-07-18)"
)
LEGACY_CSV_EPOCH = (
    "legacy-halfband epoch: first production trawl, weight bank b0dce17a "
    "(coarse-channel center assumed at Nyquist; mistuned by fs/2, pilots "
    "suppressed 39-47 dB except channel 30)"
)


def _source_name(source) -> str:
    """Display name for a path or package resource."""
    name = getattr(source, "name", None)
    return str(name) if name is not None else Path(source).name


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


def channel_z_range(ch: int) -> tuple[float, float]:
    """21cm redshift interval covered by an ATSC channel (z_lo at upper edge)."""
    lo, hi = channel_edges(ch)
    return (HI_REST_FREQUENCY_MHZ / hi - 1.0,
            HI_REST_FREQUENCY_MHZ / lo - 1.0)


def legacy_rate_fractions(rates_csv: str | Path = DEFAULT_RATES_CSV,
                          refused_fraction: float = REFUSED_FRACTION,
                          rate_col: str = "hi_rate_all",
                          weight_col: str = "n_valid_frames"
                          ) -> dict[int, float]:
    """Exposure-weighted legacy rate per ATSC channel.

    Weights each quarterly rate in ``rate_col`` by the exposure count in
    ``weight_col``, then adds the refused channels at ``refused_fraction``.
    The weight must count the frames the rate was computed over, so a custom
    ``rate_col`` usually needs its matching weight column: ``hi_rate_all``
    pairs with ``n_valid_frames`` (the default), ``hi_rate_frb`` with
    ``n_frb_frames``. Rows whose rate or weight cell is empty (quarters in
    which the survey recorded no frames of that kind) carry no exposure and
    are skipped, with the skipped count reported as a :class:`UserWarning`.
    """
    num = defaultdict(float)
    den = defaultdict(float)
    skipped = 0
    opener = getattr(rates_csv, "open", None)
    fh = (opener("r", encoding="utf-8", newline="") if opener is not None
          else open(rates_csv, encoding="utf-8", newline=""))
    with fh:
        for row in csv.DictReader(fh):
            rate_text = (row[rate_col] or "").strip()
            weight_text = (row[weight_col] or "").strip()
            if not rate_text or not weight_text:
                skipped += 1
                continue
            ch = int(row["atsc_channel"])
            n = float(weight_text)
            num[ch] += n * float(rate_text)
            den[ch] += n
    if skipped:
        warnings.warn(
            f"skipped {skipped} row(s) of {_source_name(rates_csv)} with an "
            f"empty {rate_col!r} or {weight_col!r} cell",
            stacklevel=2)
    fractions = {ch: num[ch] / den[ch] for ch in num if den[ch] > 0}
    for ch in REFUSED_CHANNELS:
        fractions[ch] = refused_fraction
    return dict(sorted(fractions.items()))


@dataclass
class MaskTable:
    """Per-channel masked fractions, carrying the rule that produced them.

    The ``rule`` field is the reason this class exists. A bare
    ``{channel: fraction}`` dict cannot be
    checked against the detector it is supposed to describe; this can.
    """
    fractions: dict[int, float]
    source: str                     # 'products' | 'csv'
    rule: str                       # the detector's own rule, or 'unrecorded'
    detector_version: str = "unrecorded"
    n_frames: dict[int, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    window: str = "full span"       # epoch the fractions describe
    epoch: str = "current"          # detector epoch that produced the fractions
    occupancy_valid: bool = True    # False: not a DTV occupancy measurement

    @property
    def is_traceable(self) -> bool:
        return self.rule != "unrecorded"

    @property
    def is_occupancy_measurement(self) -> bool:
        """True when the fractions measure DTV occupancy under an identified,
        correctly tuned detector. The vendored legacy CSV is traceable but
        not an occupancy measurement."""
        return bool(self.occupancy_valid)

    def summary(self) -> str:
        head = (f"{len(self.fractions)} channels from {self.source}; "
                f"rule: {self.rule}")
        if self.window != "full span":
            head += f"; window: {self.window}"
        if not self.occupancy_valid:
            head += f"; NOT an occupancy measurement ({self.epoch})"
        body = "\n".join(
            f"    ch{ch:>3d}  {f:7.4f}"
            + (f"   ({self.n_frames[ch]} frames)" if ch in self.n_frames else "")
            for ch, f in sorted(self.fractions.items()))
        tail = "".join(f"\n    ! {n}" for n in self.notes)
        return f"{head}\n{body}{tail}"


def legacy_rate_table(rates_csv: str | Path = DEFAULT_RATES_CSV,
                      refused_fraction: float = REFUSED_FRACTION,
                      rate_col: str = "hi_rate_all",
                      weight_col: str = "n_valid_frames") -> MaskTable:
    """The vendored quarterly CSV, wrapped so its provenance and limits show.

    The rule and epoch are those of the shipped
    ``survey_quarterly_rates_all23.csv``; a caller passing another CSV with the
    same column layout inherits the same labels and should override them.
    A custom ``rate_col`` usually needs its matching ``weight_col``; see
    :func:`legacy_rate_fractions`.
    """
    fr = legacy_rate_fractions(rates_csv, refused_fraction, rate_col,
                               weight_col)
    return MaskTable(
        fractions=fr, source="csv", rule=LEGACY_CSV_RULE,
        epoch=LEGACY_CSV_EPOCH, occupancy_valid=False,
        notes=[f"column {rate_col!r} in {_source_name(rates_csv)} was produced "
               f"by the legacy fs/2-mistuned detector epoch; its rates are the "
               f"null tail plus leakage from the strongest carriers, not DTV "
               f"occupancy (channel 30 excepted); refused channels "
               f"{REFUSED_CHANNELS} are the assumed {refused_fraction:.2f}, "
               f"not a rate"])
