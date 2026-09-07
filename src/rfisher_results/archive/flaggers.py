"""The incumbent flaggers against the pilot proxy, on each channel's current era.

Chapter 9's flagger table asks what the flaggers a survey already runs would
leave behind on the same frames the pilot proxy is scored on. The flaggers
themselves are :mod:`rfisher.incumbent`'s --- a median-absolute-deviation cut
within an acquisition, and a spectral-kurtosis cut with the Nita and Gary null
--- and only the measurement they are scored against is rebuilt here, for two
reasons the v5 products force.

*The field names.* ``rfisher.incumbent.shelf_per_frame`` reads the legacy
``snr_shelf_db``; the v5 products carry the same quantity as
``estimated_data_shelf_snr_db``, which :class:`~.products.Product` exposes as
``shelf_db``.

*The era, and one floor.* The incumbent comparison was written on the whole
archive. Chapter 9 evaluates every channel on its current era, and the floor a
frame without a resolved excess is booked at is the analysis's own
(:mod:`.nulls`), not a percentile recomputed here: a flagger comparison that
invents its own floor is not comparable with the residual chain that the rest
of the chapter reports.

Scored population. The era's frames, restricted to acquisitions of at least
``min_frames`` (a block statistic needs a block), and to frames the health
gate admits. Every flagger sees exactly those frames, so the masked fractions
and the surviving shelf are comparable across rows.

Rows. Keep everything; the MAD cut; the spectral-kurtosis cut; the pilot proxy
at the survey flag (``F > mu_0``, the bootstrap rule the kernel runs); and the
pilot proxy at the point the selection reports --- on this run a declared
diagnostic, because no channel has a selected point. The last is the row
chapter 9 calls the one that matters, and it is computed from the exact
integer fine powers through the same bundle the selector uses, not from a
stored decision.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import numpy as np

from rfisher.incumbent import DEFAULT_MAD_K, acquisition_blocks, mad_flag, sk_flag

from . import selection
from .products import Product

MIN_BLOCK_FRAMES = 8              # a block statistic needs a block; the incumbents' own minimum
SK_NSIGMA = 3.0
SURVEY_FLAG = "pilot proxy, survey flag"
DIAGNOSTIC = "pilot proxy, reported point"
KEEP_EVERYTHING = "keep everything"


@dataclass(frozen=True)
class FlaggerRow:
    """One flagger on one channel's scored population."""

    channel: int
    name: str
    masked_fraction: float
    kept: int
    retained_shelf_linear: float      # mean shelf-or-floor over the kept frames
    retained_shelf_db: float
    suppression_db: float             # keep-everything mean over this row's mean, in dB
    status: str = "measured"          # 'measured' | 'undefined' (nothing kept)

    def as_row(self) -> dict:
        return {"channel": self.channel, "flagger": self.name, "masked_fraction": self.masked_fraction,
                "kept": self.kept, "retained_shelf_linear": self.retained_shelf_linear,
                "retained_shelf_db": self.retained_shelf_db, "suppression_db": self.suppression_db,
                "status": self.status}


@dataclass(frozen=True)
class ChannelFlaggers:
    channel: int
    freq_id: int
    era_label: str
    scored_frames: int
    era_frames: int
    blocks: int
    block_median_frames: float
    floor_db: float
    floor_evidence: str
    duty_cycle: float                 # fraction of the scored frames the survey flag rejects
    rows: tuple[FlaggerRow, ...]
    diagnostic_basis: str = ""
    notes: tuple[str, ...] = field(default_factory=tuple)

    def by_name(self, name: str) -> FlaggerRow | None:
        return next((r for r in self.rows if r.name == name), None)


def _score(name: str, channel: int, flag: np.ndarray, linear: np.ndarray, base: np.ndarray,
           all_mean: float) -> FlaggerRow:
    keep = base & ~flag
    n = int(base.sum())
    kept = int(keep.sum())
    if not kept:
        return FlaggerRow(channel, name, 1.0, 0, math.nan, math.nan, math.nan, "undefined")
    mean = float(linear[keep].mean())
    return FlaggerRow(channel, name, 1.0 - kept / n, kept, mean, 10.0 * math.log10(mean) if mean > 0 else -math.inf,
                      10.0 * math.log10(all_mean / mean) if mean > 0 and all_mean > 0 else math.inf)


def compare(product: Product, era: np.ndarray, *, floor_db: float, floor_evidence: str, era_label: str,
            diagnostic: dict | None = None, anchor_bin: int | None = None, bulk_mask: np.ndarray | None = None,
            mad_k: float = DEFAULT_MAD_K, sk_nsigma: float = SK_NSIGMA,
            min_frames: int = MIN_BLOCK_FRAMES) -> ChannelFlaggers:
    """Every flagger on one channel's era, scored on the frames all of them can see."""
    era = np.asarray(era, dtype=bool) & product.selected
    unit = product.frame_unit_index
    notes: list[str] = []
    inblock = np.zeros(era.shape, dtype=bool)
    for a, b in acquisition_blocks(np.where(era, unit, -1), min_frames):
        inblock[a:b] = True
    base = era & inblock
    sizes = np.array([b - a for a, b in acquisition_blocks(np.where(era, unit, -1), min_frames)], dtype=float)
    if not base.any():
        notes.append(f"no acquisition of the era reaches {min_frames} frames: nothing is scored")
        return ChannelFlaggers(product.geometry.physical_channel, product.geometry.freq_id, era_label,
                               0, int(era.sum()), 0, 0.0, floor_db, floor_evidence, math.nan, (), "", tuple(notes))

    floor_linear = 10.0 ** (floor_db / 10.0) if math.isfinite(floor_db) else math.nan
    shelf = product.shelf_db
    finite = np.isfinite(shelf)
    if not math.isfinite(floor_linear) and not finite[base].all():
        notes.append("floor is refused and some scored frames carry no shelf estimate: those frames are dropped")
        base = base & finite
    linear = np.full(shelf.shape, floor_linear, dtype=float)
    linear[finite] = np.maximum(10.0 ** (shelf[finite] / 10.0), floor_linear if math.isfinite(floor_linear) else -math.inf)
    all_mean = float(linear[base].mean())
    power = np.asarray(product.archive["baseband_power_linear"])[:, 0].astype(float)
    channel = product.geometry.physical_channel

    sk, _, _ = sk_flag(power, unit, nsigma=sk_nsigma, min_frames=min_frames)
    rows = [_score(KEEP_EVERYTHING, channel, np.zeros(era.shape, dtype=bool), linear, base, all_mean),
            _score(f"MAD {mad_k:g}x within acquisition", channel, mad_flag(power, unit, k=mad_k), linear, base, all_mean),
            _score(f"SK {sk_nsigma:g}sigma within acquisition", channel, sk, linear, base, all_mean),
            _score(SURVEY_FLAG, channel, product.rejected, linear, base, all_mean)]

    basis = ""
    if diagnostic and anchor_bin is not None and bulk_mask is not None:
        rho, eta_q16 = diagnostic.get("rho"), diagnostic.get("eta_q16")
        if rho is not None and eta_q16 is not None:
            try:
                bundle = selection.build_residual_score_bundle(
                    product.path, base, anchor_bin=int(anchor_bin),
                    designated_half_width=selection.DESIGNATED_HALF_WIDTH, bulk_mask=np.asarray(bulk_mask, dtype=bool))
                required = np.asarray(bundle.requirements_by_rho()[int(rho)], dtype=object)
                flag = np.ones(era.shape, dtype=bool)
                flag[bundle.source_row_index] = ~selection.kept_at(required, int(eta_q16))
                rows.append(_score(DIAGNOSTIC, channel, flag, linear, base, all_mean))
                basis = diagnostic.get("basis", "")
            except Exception as exc:            # the bundle refuses loudly on some blocks; record, do not stop
                notes.append(f"reported point not scored: {type(exc).__name__}: {exc}")
        else:
            notes.append("reported point not scored: the selection carries no rank or multiplier")
    else:
        notes.append("reported point not scored: no selection to read it from")

    return ChannelFlaggers(
        channel=channel, freq_id=product.geometry.freq_id, era_label=era_label, scored_frames=int(base.sum()),
        era_frames=int(era.sum()), blocks=int(sizes.size), block_median_frames=float(np.median(sizes)) if sizes.size else 0.0,
        floor_db=floor_db, floor_evidence=floor_evidence,
        duty_cycle=float(product.rejected[base].mean()), rows=tuple(rows), diagnostic_basis=basis, notes=tuple(notes))


def channel_row(result: ChannelFlaggers) -> dict:
    """One flat row per channel: the summary the ledger carries."""
    row = {"channel": result.channel, "freq_id": result.freq_id, "era": result.era_label,
           "scored_frames": result.scored_frames, "era_frames": result.era_frames, "blocks": result.blocks,
           "block_median_frames": result.block_median_frames, "floor_db": result.floor_db,
           "floor_evidence": result.floor_evidence, "duty_cycle": result.duty_cycle,
           "diagnostic_basis": result.diagnostic_basis, "notes": "; ".join(result.notes)}
    for r in result.rows:
        tag = {KEEP_EVERYTHING: "keep", SURVEY_FLAG: "flag", DIAGNOSTIC: "point"}.get(r.name)
        if tag is None:
            tag = "mad" if r.name.startswith("MAD") else "sk"
        row[f"{tag}_masked_fraction"] = r.masked_fraction
        row[f"{tag}_kept"] = r.kept
        row[f"{tag}_retained_shelf_db"] = r.retained_shelf_db
        row[f"{tag}_suppression_db"] = r.suppression_db
        row[f"{tag}_status"] = r.status
    return row


FLAGGER_COLUMNS = ("channel", "flagger", "masked_fraction", "kept", "retained_shelf_linear", "retained_shelf_db",
                   "suppression_db", "status")


def write_flagger_rows(results: Sequence[ChannelFlaggers], path: Path | str) -> Path:
    """One row per (channel, flagger): the long form the chapter's summary is taken over."""
    import csv

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(FLAGGER_COLUMNS), lineterminator="\n")
        writer.writeheader()
        for result in results:
            for r in result.rows:
                writer.writerow({k: (repr(v) if isinstance(v, float) else v) for k, v in r.as_row().items()})
    return path
