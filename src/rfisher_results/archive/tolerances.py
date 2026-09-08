"""Per-channel science tolerances ``r_tol`` for the selector and the tables.

The selector needs, per channel, the largest systematic residual the science
tolerates on the operable no-delay-filter tier, the acoustic dilation
(``R_dil = r_sys / min(r_perp, r_par) <= 1``, chapter 9 eq:tolerance:rtol at
``zeta = 1``), with the growth-rate tolerance ``f sigma_8`` beside it as the
binding secondary.

One home supplies the constants: :mod:`rfisher.tolerances`, the stable
``zeta = 1`` minima of the dense bias-response bank over the accepted
multi-year grid, the same convention for every channel. Both ``TOL_APERP`` and
``TOL_FS8`` now cover all 23 channels. Thirteen carried no growth-rate
constant until the bank was re-read for them, and they were missing by
omission rather than by refusal: the response-stability gate accepts the
growth rate at every integration time in every forecast bin, so there was
never a bin the tier could not be priced on. They are not priced on a
different footing: the completed-forecast ledger's single one-year point,
the footing ``scripts/channel_tolerances.py`` used, priced the lower band up
to 1.8x looser and was retired for that reason.

The ledger is still read for one check the constants cannot make on their
own: the text's dilation tier is ``min(r_perp, r_par)`` and the published
constants cover ``alpha_perp`` only. On the frozen ledger
(``forecast_completion_all_dtv_bins.json``, estimator
``perbin_noise_normalized``; ``forecast_completion_channel_mapping.csv``,
family ``noise_shaped``) the accepted ``alpha_par`` tolerance is 2 to 3.6
times looser than ``alpha_perp`` in every bin from z = 1.30 to 1.90, so
``alpha_perp`` binds there and ``r_tol_dilation = TOL_APERP``. In the
z = 1.90-2.04 bin (channels 14-16) the ledger's own accepted ``alpha_perp``
entry is 3.22, an artefact 160x the published constant, so the check is
inconclusive there and the row says ``review``; the ratio is recorded per
channel so the claim is checked where it can be, not assumed.

Output columns (``tables/channel_tolerances.csv``): ``channel, z_low, z_high,
bins, r_tol_dilation, r_tol_aperp, r_tol_fs8, fs8_status,
apar_over_aperp_ledger, dilation_binding``.
"""
from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path

from rfisher import tolerances as published
from rfisher.channels import channel_z_range

from ..results_tree import out_dir

LEDGER_NAME = "forecast_completion_all_dtv_bins.json"
MAPPING_NAME = "forecast_completion_channel_mapping.csv"
ESTIMATOR = "perbin_noise_normalized"
FAMILY = "noise_shaped"
TARGETS = ("aperp", "apar", "fs8")
CHANNELS = tuple(range(14, 37))
COLUMNS = ("channel", "z_low", "z_high", "bins", "r_tol_dilation", "r_tol_aperp", "r_tol_fs8",
           "fs8_status", "apar_over_aperp_ledger", "dilation_binding")
FS8_UNPRICED = "unpriced: no published constant; rebuild the dense bias bank to price"


@dataclass(frozen=True)
class ChannelTolerance:
    channel: int
    z_low: float
    z_high: float
    bins: tuple[int, ...]                 # ledger bins the channel overlaps (empty without a ledger)
    r_tol_aperp: float                    # published stable zeta = 1 minimum
    r_tol_fs8: float                      # published, or NaN for 14-26
    apar_over_aperp_ledger: float         # ledger check that alpha_par never binds (NaN without a ledger)

    @property
    def r_tol_dilation(self) -> float:
        """The operable tier. alpha_perp binds wherever the ledger ratio is >= 1."""
        return self.r_tol_aperp

    @property
    def dilation_binding(self) -> str:
        if math.isnan(self.apar_over_aperp_ledger):
            return "aperp (alpha_par unchecked: no ledger)"
        return "aperp" if self.apar_over_aperp_ledger >= 1.0 else "alpha_par tighter on the ledger: review"

    @property
    def fs8_status(self) -> str:
        return "published" if math.isfinite(self.r_tol_fs8) else FS8_UNPRICED

    def as_row(self) -> dict:
        return {
            "channel": self.channel, "z_low": self.z_low, "z_high": self.z_high,
            "bins": ";".join(str(b) for b in self.bins),
            "r_tol_dilation": self.r_tol_dilation, "r_tol_aperp": self.r_tol_aperp,
            "r_tol_fs8": self.r_tol_fs8, "fs8_status": self.fs8_status,
            "apar_over_aperp_ledger": self.apar_over_aperp_ledger, "dilation_binding": self.dilation_binding,
        }


def ledger_bin_tolerances(ledger_path: Path | str, *, estimator: str = ESTIMATOR) -> dict[int, dict]:
    """``{bin_index: {z_low, z_high, aperp, apar, fs8}}``: the smallest accepted
    ``r_tolerance`` per target over a bin's points (the ledger's own footing)."""
    doc = json.loads(Path(ledger_path).read_text(encoding="utf-8"))
    out: dict[int, dict] = {}
    for b in doc["ledgers"][estimator]["bins"]:
        rec = {"z_low": float(b["z_low"]), "z_high": float(b["z_high"])}
        for target in TARGETS:
            values = []
            for point in b["points"]:
                for label, det in (point.get("parameters", {}).get(target) or {}).items():
                    if label == "accepted" or not isinstance(det, dict):
                        continue
                    if det.get("failure_reason") is not None or det.get("r_tolerance") is None:
                        continue
                    values.append(float(det["r_tolerance"]))
            rec[target] = min(values) if values else math.nan
        out[int(b["bin_index"])] = rec
    return out


def ledger_channel_bins(mapping_path: Path | str, *, family: str = FAMILY) -> dict[int, tuple[int, ...]]:
    """``{channel: overlapping ledger bin indices}`` from the released mapping."""
    out: dict[int, tuple[int, ...]] = {}
    with Path(mapping_path).open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["family"] == family:
                out[int(row["channel"])] = tuple(int(x) for x in row["overlap_bin_indices"].split(";") if x)
    return out


def channel_tolerances(results: Path | str | None = None, *, channels=CHANNELS) -> list[ChannelTolerance]:
    """The published constants per channel, with the ledger's alpha_par check
    when the results tree (default ``out_dir()``) carries the ledger."""
    root = Path(results) if results is not None else out_dir()
    ledger = root / LEDGER_NAME
    mapping = root / MAPPING_NAME
    have_ledger = ledger.is_file() and mapping.is_file()
    by_bin = ledger_bin_tolerances(ledger) if have_ledger else {}
    bins_of = ledger_channel_bins(mapping) if have_ledger else {}
    rows = []
    for channel in channels:
        z_low, z_high = channel_z_range(channel)
        bins = bins_of.get(channel, ())
        ratio = math.nan
        if bins:
            aperp = [by_bin[b]["aperp"] for b in bins if b in by_bin and math.isfinite(by_bin[b]["aperp"])]
            apar = [by_bin[b]["apar"] for b in bins if b in by_bin and math.isfinite(by_bin[b]["apar"])]
            if aperp and apar:
                ratio = min(apar) / min(aperp)
        rows.append(ChannelTolerance(
            channel=channel, z_low=z_low, z_high=z_high, bins=tuple(bins),
            r_tol_aperp=float(published.TOL_APERP[channel]),
            r_tol_fs8=float(published.TOL_FS8.get(channel, math.nan)),
            apar_over_aperp_ledger=ratio,
        ))
    return rows


def write_channel_tolerances(rows: list[ChannelTolerance], path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(COLUMNS), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            out = {}
            for k, v in row.as_row().items():
                out[k] = "" if isinstance(v, float) and not math.isfinite(v) else (repr(v) if isinstance(v, float) else v)
            writer.writerow(out)
    return path
