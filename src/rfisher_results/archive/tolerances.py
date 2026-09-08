"""Target-time, bank-derived per-channel tolerances.

The operational path uses the authenticated no-filter world table, requires
both acoustic dilations, and takes the minimum over every nonzero-overlap
redshift bin. Missing, unauthenticated, or target-time-refused cells remain
unpriced. Legacy published constants are not substituted. The historical
ledger readers remain available for auditing earlier releases.
"""
from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path

from rfisher.channels import channel_z_range

LEDGER_NAME = "forecast_completion_all_dtv_bins.json"
MAPPING_NAME = "forecast_completion_channel_mapping.csv"
ESTIMATOR = "perbin_noise_normalized"
FAMILY = "noise_shaped"
TARGETS = ("aperp", "apar", "fs8")
CHANNELS = tuple(range(14, 37))
COLUMNS = ("channel", "z_low", "z_high", "bins", "r_tol_dilation", "r_tol_aperp", "r_tol_fs8",
           "fs8_status", "apar_over_aperp_ledger", "dilation_binding", "r_tol_apar", "tolerance_basis", "refusal")
FS8_UNPRICED = "unpriced: no published constant; rebuild the dense bias bank to price"


@dataclass(frozen=True)
class ChannelTolerance:
    channel: int
    z_low: float
    z_high: float
    bins: tuple[int, ...]                 # all overlapping forecast bins
    r_tol_aperp: float                    # target-time minimum, or NaN on refusal
    r_tol_fs8: float                      # target-time minimum, or NaN on refusal
    apar_over_aperp_ledger: float         # compatibility name for derived apar/aperp
    r_tol_apar: float = math.nan
    tolerance_basis: str = "unverified historical constants"
    refusal: str = ""

    @property
    def r_tol_dilation(self) -> float:
        """Both dilation parameters must have an accepted target-time tolerance."""
        values = (self.r_tol_aperp, self.r_tol_apar)
        return min(values) if all(math.isfinite(v) and v > 0 for v in values) else math.nan

    @property
    def dilation_binding(self) -> str:
        if not math.isfinite(self.r_tol_dilation):
            return "refused: both dilation tolerances required at the target time"
        return "aperp" if self.r_tol_aperp <= self.r_tol_apar else "apar"

    @property
    def fs8_status(self) -> str:
        return "derived at target time" if math.isfinite(self.r_tol_fs8) else "refused at target time"

    def as_row(self) -> dict:
        return {
            "channel": self.channel, "z_low": self.z_low, "z_high": self.z_high,
            "r_tol_apar": self.r_tol_apar, "tolerance_basis": self.tolerance_basis, "refusal": self.refusal,
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


def channel_tolerances(results: Path | str | None = None, *, channels=CHANNELS,
                       derived_rows=None) -> list[ChannelTolerance]:
    """Price both dilations and growth at the declared target time.

    All nonzero-overlap bins must be priced. Historical constants and
    alternative integration times are never fallback tolerances. ``results``
    remains accepted for callers reading legacy ledgers separately.
    """
    from . import worlds
    refusal = ""
    supplied_rows = derived_rows is not None
    if derived_rows is None:
        try:
            derived_rows = worlds.tolerances()
        except (OSError, ValueError, RuntimeError) as exc:
            derived_rows = []
            refusal = f"authenticated target-time tolerances unavailable: {exc}"
    no_filter = [r for r in derived_rows if r["world"] == "none"]
    rows = []
    for channel in channels:
        z_low, z_high = channel_z_range(channel)
        bins = tuple(sorted({int(r["bin_index"]) for r in no_filter
                             if float(r["z_lo"]) < z_high and float(r["z_hi"]) > z_low}))
        # A missing bin in every parameter must not disappear from the request.
        # Require the union of the supplied intervals to cover the whole channel.
        covered_to = z_low
        for lo, hi in sorted({(float(r["z_lo"]), float(r["z_hi"])) for r in no_filter
                              if int(r["bin_index"]) in bins}):
            if lo > covered_to + 1e-10:
                break
            covered_to = max(covered_to, hi)
        coverage_ok = covered_to >= z_high - 1e-10
        values = {p: worlds.tolerance_of(no_filter, "none", bins, p) if coverage_ok else math.nan for p in TARGETS}
        channel_refusal = refusal or ("forecast bins do not cover the full channel" if not coverage_ok else
                                      "one or more target-time parameter tolerances refused" if any(not math.isfinite(v) for v in values.values()) else "")
        source = "caller-supplied no-filter rows" if supplied_rows else "authenticated no-filter bank"
        if refusal:
            source = "unavailable authenticated no-filter bank"
        ratio = values["apar"] / values["aperp"] if math.isfinite(values["aperp"]) else math.nan
        rows.append(ChannelTolerance(
            channel=channel, z_low=z_low, z_high=z_high, bins=tuple(bins),
            r_tol_aperp=values["aperp"], r_tol_apar=values["apar"], r_tol_fs8=values["fs8"],
            apar_over_aperp_ledger=ratio,
            tolerance_basis=f"{source}; {worlds.TARGET_YEARS:g} on-sky year; minimum over every overlapping bin",
            refusal=channel_refusal,
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
