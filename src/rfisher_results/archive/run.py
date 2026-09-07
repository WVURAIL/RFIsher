"""Run the archive pipeline over the campaign products and write the results tree.

Per channel, in the order the design lists (``docs/archive-results-design.md``
section 4): eras (section 8.1 on the selected frames, with the recorded
sign-off and sign-on months as the station record), the current era and the
verified off era, the chronological calibration/evaluation split, the anchors
(calibration block, evaluation block, current era, previous era), the
per-frame spectrum containment of the current era, the residual chain and
its coherence gain, the null calibration, the tolerance, the selection on the
calibration block replayed on the evaluation block, the exchangeability at
the selected rank on the evaluation block's quiet frames, the screening
class, and the ledger record.

Channels run in parallel processes; each opens its own product and writes
its own per-channel files (era months, anchor contrast curves, window
spectra) under ``<out>/channels/chNN/``. The parent aggregates the tables
(``tables/*.csv``), the K* rule over all channels, the ledger
(``ledger/``) and ``run.json``.

    python -m rfisher_results.cli archive --products DIR --out DIR [--workers 6]
        [--replicates 1000] [--seed 20260907] [--channels 35,29]
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import json
import math
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Sequence

import numpy as np

from rfisher import residual

from rfisher.channels import channel_edges

from . import (anchors, blocks, chain, eras, flaggers, ledger, masked_spectra, nulls, operating, psd,
               screening, selection, tolerances, worlds)
from .numbers import git_commit
from .products import COARSE_BIN_HZ, FINE_BIN_HZ, Product, sha256_of

ROOT = Path(__file__).resolve().parents[3]


def station_records(channel: int) -> dict[str, str]:
    """``{YYYY-MM: 'sign-off'|'sign-on'}`` from the recorded transmitter events."""
    out: dict[str, str] = {}
    off_from = residual.SIGN_OFF_FROM.get(channel)
    if off_from:
        out[off_from] = "sign-off"
    off_through = residual.SIGN_ON_OFF_THROUGH.get(channel)
    if off_through:
        y, m = (int(x) for x in off_through.split("-"))
        idx = y * 12 + m            # the month after the off epoch
        out[blocks.month_label(idx)] = "sign-on"
    return out


@dataclasses.dataclass(frozen=True)
class OffEpoch:
    """The channel's verified transmitter-off population.

    ``record`` is the frame mask of the recorded off epoch (``residual.SIGN_OFF_FROM`` /
    ``SIGN_ON_OFF_THROUGH``); ``mask`` restricts it to the frames of the era table's
    proxy-low eras, so a month the section 8.1 procedure classifies proxy-high or
    ambiguous never enters the null population even when the record's date covers
    it (channel 20's record says 2022-09 while the procedure reads the transmitter
    on through 2022-12). ``mask`` is None when no record exists or nothing survives.
    """

    mask: np.ndarray | None
    off_through: str | None
    off_from: str | None
    record_frames: int
    off_frames: int
    note: str


def verified_off(product: Product, months: np.ndarray, table: eras.EraTable | None = None) -> OffEpoch:
    """Frames of the channel's verified transmitter-off epoch, restricted to proxy-low eras when a table is given."""
    ch = product.geometry.physical_channel
    off_from = residual.SIGN_OFF_FROM.get(ch)
    off_through = residual.SIGN_ON_OFF_THROUGH.get(ch)
    record = None
    if off_from:
        y, m = (int(x) for x in off_from.split("-"))
        record = product.selected & (months >= y * 12 + m - 1)
    elif off_through:
        y, m = (int(x) for x in off_through.split("-"))
        record = product.selected & (months <= y * 12 + m - 1)
    if record is None:
        return OffEpoch(None, off_through, off_from, 0, 0, "")
    if table is None:
        return OffEpoch(record if record.any() else None, off_through, off_from, int(record.sum()), int(record.sum()), "")
    low = np.zeros(record.shape, dtype=bool)
    for index, era in enumerate(table.eras):
        if era.state == eras.PROXY_LOW:
            low |= table.era_mask(product, index)
    mask = record & low
    notes = []
    dropped = int(record.sum() - mask.sum())
    if dropped:
        notes.append(f"off population: {dropped} of {int(record.sum())} frames of the recorded off epoch fall outside the "
                     f"procedure's proxy-low eras and are excluded")
    if table.unmatched_station_records:
        notes.append("station record not matched by a transition: " + ", ".join(table.unmatched_station_records))
    return OffEpoch(mask if mask.any() else None, off_through, off_from, int(record.sum()), int(mask.sum()), "; ".join(notes))


def _producer() -> dict:
    """The producing code: commit, dirty flag and a digest of this package's sources, read before the run starts."""
    import hashlib
    import subprocess
    here = Path(__file__).resolve().parent
    h = hashlib.sha256()
    for f in sorted(here.glob("*.py")):
        h.update(f.name.encode()); h.update(f.read_bytes())
    try:
        status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no", "--", "src/rfisher_results/archive"], cwd=ROOT, capture_output=True,
                                text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        status = "unknown"
    return {"repository": "WVURAIL/RFIsher", "commit": git_commit(ROOT), "dirty": bool(status), "dirty_files": status,
            "module": "rfisher_results.archive.run", "source_digest": h.hexdigest()}


def _quiet_cohort_is_null(product: Product, mask) -> bool:
    """Whether a mask's coarse-quiet frames are a null population: the bulk's centre lies at mu_0."""
    frames = np.asarray(mask, dtype=bool) & product.selected
    if frames.sum() < nulls.MIN_NULL_FRAMES:
        return True
    widths = nulls.describe_null(product.statistic[frames], nulls.COARSE_DOF)
    return bool(math.isfinite(widths.centre) and abs(widths.centre - 1.0) <= nulls.OFF_CENTRE_TOLERANCE)


def _fine_bin_of_rf(rf_offset_hz: float, geometry) -> int:
    """The padded fine bin an RF offset from the nominal pilot falls on (the inverse of anchors.rf_offset_of_bin)."""
    fine_hz = geometry.grid_residual_hz + float(np.sign(geometry.sense) or 1) * float(rf_offset_hz)
    return int(round(fine_hz / FINE_BIN_HZ)) % anchors.FINE_BINS


COARSE_ETA_GRID = tuple(np.round(np.arange(1.0, 1.5001, 0.005), 3)) + (1.6, 1.8, 2.0, 3.0, 5.0, 10.0, 100.0)


def _coarse_frontier(product: Product, block, floor: selection.Floor, gain: float, r_tol: float) -> list[dict]:
    """The coarse rule F > eta_c mu_0 on a block: masked fraction and floor-bounded residual per eta_c."""
    rows = np.flatnonzero(np.asarray(block, dtype=bool))
    if rows.size == 0 or not math.isfinite(floor.linear):
        return []
    q = product.statistic[rows]
    residual = selection.systematic_residuals(product, rows, floor, gain)
    out = []
    for eta in COARSE_ETA_GRID:
        kept = q <= float(eta)
        n_kept = int(kept.sum())
        r = float(residual[kept].mean()) if n_kept else math.nan
        out.append({"eta_c": float(eta), "frames": int(rows.size), "kept": n_kept, "masked_fraction": 1.0 - n_kept / rows.size,
                    "r_sys": r, "R": r / r_tol if (math.isfinite(r) and math.isfinite(r_tol) and r_tol > 0) else math.nan,
                    "evaluable": n_kept >= 30})
    return out


def _frontier_summary(frontier: list[dict]) -> dict:
    ok = [f for f in frontier if f["evaluable"] and math.isfinite(f["R"])]
    if not ok:
        return {"coarse_min_R": math.nan, "coarse_min_R_eta": math.nan, "coarse_min_R_masked_fraction": math.nan, "coarse_R_at_flag": math.nan}
    best = min(ok, key=lambda f: f["R"])
    at_flag = next((f for f in frontier if f["eta_c"] == 1.0), None)
    return {"coarse_min_R": best["R"], "coarse_min_R_eta": best["eta_c"], "coarse_min_R_masked_fraction": best["masked_fraction"],
            "coarse_R_at_flag": at_flag["R"] if at_flag else math.nan}


def _rate(flag: np.ndarray, block: np.ndarray) -> float:
    """Fraction of a block's frames carrying ``flag`` (NaN on an empty block)."""
    block = np.asarray(block, dtype=bool)
    return float(np.asarray(flag, dtype=bool)[block].mean()) if block.any() else math.nan


def _label(era: eras.Era | None) -> str:
    return f"{era.first_label}..{era.last_label} ({era.state})" if era else "no era"


def process_channel(path: str, out_dir: str, *, campaign_last_month: int, replicates: int, seed: int,
                    era_config: eras.EraConfig | None = None, tolerance_row: dict | None = None) -> dict:
    """The whole pipeline for one product; returns small rows, writes large files."""
    t0 = time.time()
    out = Path(out_dir)
    p = Product(path)
    g = p.geometry
    ch = g.physical_channel
    ch_dir = out / "channels" / f"ch{ch:02d}"
    ch_dir.mkdir(parents=True, exist_ok=True)
    config = era_config or eras.DEFAULT_CONFIG
    record = ledger.ChannelRecord(ch, g.freq_id, p.path.name, sha256_of(p.path))
    notes = record.notes

    # 0. what the product is: its geometry and its frame accounting
    lo_mhz, hi_mhz = channel_edges(ch)
    record.add("geometry", {
        "pilot_hz": g.pilot_hz, "centre_hz": g.centre_hz, "sense": g.sense, "grid_residual_hz": g.grid_residual_hz,
        "nominal_fine_bin": g.nominal_fine_bin, "nominal_psd_bin": g.nominal_psd_bin,
        "centre_line_rf_offset_hz": g.centre_line_rf_offset_hz, "stored_window_centre": g.stored_window_centre,
        "allocation_low_mhz": lo_mhz, "allocation_high_mhz": hi_mhz, "coarse_bin_hz": COARSE_BIN_HZ, "fine_bin_hz": FINE_BIN_HZ,
        "fine_pad_factor": p.fine_pad_factor, "fine_guard_bins": p.fine_guard_bins,
        "census_excluded_bins": ";".join(str(int(b)) for b in np.atleast_1d(p.fine_census_excluded_bins)),
        "mu0": p.mu0, "shelf_offset_db": float(p.view.shelf_offset_db),
    })
    months_all = eras.frame_months(p)
    sel_months = months_all[p.selected & (months_all >= 0)]
    record.add("product", {
        "n_frames": p.n_frames, "n_valid": int(p.valid.sum()), "n_selected": int(p.selected.sum()),
        "n_units": int(np.unique(p.frame_unit_index[p.selected]).size) if p.selected.any() else 0,
        "n_rejected_flag": int((p.selected & p.rejected).sum()),
        "n_with_shelf_estimate": int((p.selected & np.isfinite(p.shelf_db)).sum()),
        "n_without_time": int((p.selected & ~np.isfinite(p.frame_time)).sum()),
        "health_schema": p.health.schema, "health_excluded": int((p.valid & ~p.health.include).sum()),
        "health_reasons": ";".join(f"{k}:{v}" for k, v in sorted(p.health.reason_counts.items())),
        "first_month": blocks.month_label(int(sel_months.min())) if sel_months.size else "",
        "last_month": blocks.month_label(int(sel_months.max())) if sel_months.size else "",
        "per_frame_spectra": "psd_frame_db_i16" in p.archive.files,
    })

    # 1. eras
    table = eras.era_table(p, config=config, campaign_last_month=campaign_last_month, station_record=station_records(ch))
    eras.write_era_json(table, ch_dir / "eras.json")
    era = table.current_era
    timed = np.isfinite(p.frame_time)
    era_mask_all = table.current_era_mask(p)
    era_mask = era_mask_all & timed          # one block definition for every module: frames without a time are excluded
    untimed_excluded = int((era_mask_all & ~timed).sum())
    months = eras.frame_months(p)
    off = verified_off(p, months, table)
    off_mask, off_through, off_from = off.mask, off.off_through, off.off_from
    if off.note:
        notes.append(off.note)
    # the current era is an off era when the recorded off epoch covers most of it (chapter 8: the off state is
    # established by the era and the record); whether that population also reads as a null is reported beside it
    off_ok, off_widths, off_reason = nulls.off_population_check(p, off_mask)
    off_majority = bool(off_mask is not None and era_mask.any() and off_mask[era_mask].mean() > 0.5)
    off_era_current = off_majority
    if off_mask is not None and not off_ok:
        notes.append(f"recorded off population is not null-like ({off_reason}): a carrier persists after the record")
    record.add("era", {**eras.channel_row(table), "off_record_frames": off.record_frames, "off_population_frames": off.off_frames,
                       "off_null_like": off_ok if off_widths is not None else None, "off_majority_of_current_era": off_majority,
                       "off_era_current": off_era_current, "current_level_median_db": era.level_median_db if era else math.nan})
    era_label = _label(era)
    # on an off era the transmitter's position, containment and chain are read from the last on era (the previous era)
    reference_index = table.current_index - 1 if (off_era_current and table.current_index > 0) else table.current_index
    if reference_index >= 0 and reference_index != table.current_index:
        reference_mask = table.era_mask(p, reference_index) & timed
        reference_label = f"previous era {_label(table.eras[reference_index])} (current era is off)"
        notes.append(f"anchor, containment and chain read on the {reference_label}")
    else:
        reference_mask, reference_label = era_mask, f"current era {era_label}"

    # 2. blocks (month support on the era procedure's own gate)
    split = blocks.split_blocks(p.frame_unit_index, p.unit_time, era_mask, frame_time=p.frame_time, minimum_months=1,
                                month_kwargs=dict(min_frames=config.min_frames, min_units=config.min_units, min_days=config.min_days))
    off_for_null = (off_mask & ~split.evaluation) if off_mask is not None else None      # the evaluation block never enters the null
    off_for_eval = (off_mask & split.evaluation) if off_mask is not None else None
    record.add("blocks", {
        "status": split.status, "detail": split.detail, "boundary_time": split.boundary_time,
        "calibration_frames": split.calibration_frames, "evaluation_frames": split.evaluation_frames,
        "calibration_units": split.calibration_units, "evaluation_units": split.evaluation_units,
        "calibration_months": len(split.calibration_months), "evaluation_months": len(split.evaluation_months),
        "frames_without_time_excluded": untimed_excluded,
        "boundary_month": blocks.month_label(int(blocks.month_index([split.boundary_time])[0])) if math.isfinite(split.boundary_time) else "",
        "calibration_finite_estimate_rate": _rate(np.isfinite(p.shelf_db), split.calibration),
        "evaluation_finite_estimate_rate": _rate(np.isfinite(p.shelf_db), split.evaluation),
        "calibration_flag_rate": _rate(p.rejected, split.calibration), "evaluation_flag_rate": _rate(p.rejected, split.evaluation),
        "calibration_first_month": blocks.month_label(split.calibration_months[0].month) if split.calibration_months else "",
        "calibration_last_month": blocks.month_label(split.calibration_months[-1].month) if split.calibration_months else "",
        "evaluation_first_month": blocks.month_label(split.evaluation_months[0].month) if split.evaluation_months else "",
        "evaluation_last_month": blocks.month_label(split.evaluation_months[-1].month) if split.evaluation_months else "",
    })

    # 3. anchors. The on-minus-quiet estimator needs a quiet cohort that is a null: where a mask's coarse bulk sits
    # far above mu_0 the frames below mu_0 are the carrier's lower tail, and the plain median is used instead.
    ratio = anchors.fine_ratio(p)
    anchor_results = []
    anc = {}
    quiet_ok = {}
    masks = [("calibration", split.calibration), ("evaluation", split.evaluation), ("current_era", era_mask)]
    if table.current_index > 0:
        masks.append(("previous_era", table.era_mask(p, table.current_index - 1) & timed))
    for label, mask in masks:
        quiet_ok[label] = _quiet_cohort_is_null(p, mask)
        anc[label] = anchors.anchor(p, mask, label, ratio=ratio, replicates=replicates, seed=seed, quiet_usable=quiet_ok[label])
        anchor_results.append(anc[label])
    anchors.write_contrast_curves(anchor_results, ch_dir / "anchor_contrast.csv")
    # the table's anchor: the current era's (eq 8.1), or the previous era's on an off-era channel
    if reference_index != table.current_index and anc.get("previous_era") is not None and anc["previous_era"].status == "ok":
        table_anchor = anc["previous_era"]
    else:
        table_anchor = anc["current_era"]
    # the selector's anchor: the calibration block's (held out from the evaluation block)
    selector_anchor = anc["calibration"] if anc["calibration"].status == "ok" else table_anchor
    record.add("anchor", {**anchors.anchor_record(table_anchor), "source": table_anchor.label,
                          "quiet_cohort_is_null": quiet_ok.get(table_anchor.label)})
    record.add("anchor_calibration", {**anchors.anchor_record(selector_anchor), "source": selector_anchor.label,
                                      "quiet_cohort_is_null": quiet_ok.get(selector_anchor.label)})
    record.add("anchor_evaluation", anchors.anchor_record(anc["evaluation"]))
    record.add("anchor_era", anchors.anchor_record(anc["current_era"]))
    if "previous_era" in anc:
        row = anchors.anchor_record(anc["previous_era"])
        both = anc["previous_era"].status == "ok" and anc["current_era"].status == "ok"
        row["shift_from_previous_bins"] = anchors.anchor_shift_bins(anc["current_era"], anc["previous_era"]) if both else None
        record.add("anchor_previous", row)
    else:
        record.add("anchor_previous", None)

    # 4. containment on the reference era (needs the per-frame spectra the campaign products carry). The table's
    # fine anchor is compared with the spectrum's in-span lobe: a disagreement beyond the designated half-width
    # sets the sentinel (design section 6); an out-of-window anchor is an alias only when it folds onto the
    # out-of-span feature by one coarse bin.
    anchor_suspect, anchor_note, lobe_bin = False, "", None
    if reference_mask.any() and "psd_frame_db_i16" in p.archive.files:
        spectrum = psd.accumulate_spectra(p, reference_mask)
        first = psd.analyse(spectrum, g)
        lobe_hz = first.row.in_span_refined_offset_hz if first.row.in_span_recovered else math.nan
        anchor_hz = float(table_anchor.anchor_rf_offset_hz) if table_anchor.status == "ok" else math.nan
        offset_bins = psd.anchor_lobe_offset_bins(anchor_hz, lobe_hz)
        disagree = math.isfinite(offset_bins) and abs(offset_bins) > anchors.DESIGNATED_HALF_WIDTH + 0.5
        folds = False
        if math.isfinite(first.row.out_of_span_offset_hz) and math.isfinite(anchor_hz):
            tol = (anchors.DESIGNATED_HALF_WIDTH + 0.5) * FINE_BIN_HZ
            folds = any(abs(anchor_hz - (first.row.out_of_span_offset_hz + k * COARSE_BIN_HZ)) <= tol for k in (-1, 1))
        reasons = []
        if folds:
            reasons.append(f"fine anchor aliases the out-of-span feature at {first.row.out_of_span_offset_hz:.0f} Hz by one coarse bin")
        elif table_anchor.status == "ok" and table_anchor.aliased_out_of_window:
            notes.append("fine anchor lies beyond the +-30-bin acquisition window (no fold onto an out-of-span feature)")
        if disagree:
            reasons.append(f"fine anchor {offset_bins:+.1f} bins from the PSD in-span lobe")
        anchor_note = "; ".join(reasons)
        cont = psd.analyse(spectrum, g, anchor_aliases=bool(folds or disagree), anchor_note=anchor_note)
        psd.write_spectra_json([cont], ch_dir / "spectra_window.json", provenance=reference_label)
        containment_row = cont.row
        mode_mass = float(table_anchor.boot_mode_mass) if table_anchor.status == "ok" else math.nan
        anchor_suspect = bool(disagree or folds or (math.isfinite(mode_mass) and mode_mass < 0.5))
        if first.row.in_span_recovered:
            lobe_bin = _fine_bin_of_rf(lobe_hz, g)
        record.add("containment", {**dataclasses.asdict(cont.row), "anchor_lobe_offset_bins": offset_bins,
                                   "anchor_lobe_disagree": bool(disagree), "anchor_folds_out_of_span": bool(folds),
                                   "anchor_suspect": anchor_suspect, "lobe_fine_bin": lobe_bin, "era": reference_label})
    else:
        cont, containment_row = None, None
        record.add("containment", None)
        if reference_mask.any():
            notes.append("containment skipped: product carries no per-frame spectra")

    # 5. chain on the reference era (chapter 9: the chain terms on the channel's current era), with the
    # archive-wide chain beside it for comparison with the superseded numbers
    gain_basis = ""
    try:
        ch_res = chain.residual_chain_on_frames(p, reference_mask, population=reference_label, off_through=off_through, off_from=off_from)
        record.add("chain", ch_res.as_row())
        gain, tau_quality, gain_basis = ch_res.gain, ch_res.tau_quality, "era chain"
    except Exception as exc:  # the chain refuses loudly on some channels; record, do not stop
        ch_res = None
        record.add("chain", None)
        notes.append(f"chain on the {reference_label}: {type(exc).__name__}: {exc}")
        gain, tau_quality = math.nan, "unmeasured"
    try:
        ch_all = chain.residual_chain(p.path, off_through=off_through, off_from=off_from)
        record.add("chain_archive", ch_all.as_row())
        if not math.isfinite(gain):
            gain, tau_quality, gain_basis = ch_all.gain, ch_all.tau_quality, "archive-wide chain (era chain refused)"
            notes.append("chain gain taken from the archive-wide chain: the era chain refused")
    except Exception as exc:
        record.add("chain_archive", None)
        notes.append(f"archive-wide chain: {type(exc).__name__}: {exc}")

    # 6. tolerance
    tol_row = tolerance_row or {}
    r_tol = float(tol_row.get("r_tol_dilation", math.nan))
    record.add("tolerance", tol_row or None)

    # 7. null calibration on the calibration block (floor first; exchangeability after the selection). The
    # evaluation block never enters the null: the floor and the widths that score both blocks are read from the
    # calibration block, or from the verified off population outside the evaluation block. When the fine anchor is
    # suspect the nominal window is excluded from the fine null's bulk (the bulk may carry the pilot). The selector's
    # anchor is the calibration block's; when that anchor is suspect and the spectrum recovered an in-span lobe, the
    # lobe's fine bin is used instead, labelled.
    anchor_bin = int(selector_anchor.anchor_bin) if selector_anchor.status == "ok" else g.nominal_fine_bin
    anchor_source = selector_anchor.label if selector_anchor.status == "ok" else "nominal bin"
    if anchor_suspect and lobe_bin is not None:
        anchor_bin, anchor_source = int(lobe_bin), "psd in-span lobe (fine anchor suspect)"
        notes.append(f"selector anchor taken from the PSD in-span lobe (bin {anchor_bin}): {anchor_note or 'anchor bootstrap mode mass below 0.5'}")
    bulk = anchors.bulk_mask(anchor_bin, pad_factor=p.fine_pad_factor, guard_fine_bins=p.fine_guard_bins,
                             census_excluded_bins=p.fine_census_excluded_bins)
    exclude = anchors.window_bins(g.nominal_fine_bin, anchors.WINDOW_HALF_WIDTH) if anchor_suspect else None
    if split.calibration.any():
        null_block, null_label = split.calibration, f"{era_label}/calibration"
    else:
        null_block, null_label = era_mask, era_label
        if era_mask.any():
            notes.append("null calibrated on the whole era: no calibration block")
    null_cal = nulls.calibrate_null(p, null_block, anchor_bin=anchor_bin, bulk_mask=bulk, era_label=null_label,
                                    off_era=off_for_null, fine_t=ratio, exclude_fine_bins=exclude)
    floor = selection.Floor(null_cal.floor.db, null_cal.floor.evidence, null_cal.floor.population)

    # 8. selection on the calibration block, replayed on the evaluation block (never without a chain gain)
    if not math.isfinite(gain):
        notes.append("selection skipped: no chain gain (both chains refused)")
    if math.isfinite(r_tol) and split.calibration.any() and math.isfinite(gain):
        sel = selection.select_operating_point(
            p, split.calibration, split.evaluation, anchor_bin=anchor_bin, bulk_mask=bulk, r_tol=r_tol, floor=floor,
            era_label=era_label, gain=gain, latest_era=True, off_era=off_era_current,
            bootstrap_replicates=replicates, bootstrap_seed=seed)
        sel = dataclasses.replace(sel, anchor_sentinel=anchor_note)
    else:
        sel = None
        notes.append("selection skipped: no tolerance or no calibration frames")
    exch_rho = None
    if sel is not None:
        exch_rho = sel.rho if sel.rho is not None else sel.diagnostic.get("rho")
    if exch_rho is not None:
        null_cal = nulls.calibrate_null(p, null_block, anchor_bin=anchor_bin, bulk_mask=bulk, era_label=null_label,
                                        off_era=off_for_null, rho=int(exch_rho), quiet_block=split.evaluation, fine_t=ratio,
                                        exclude_fine_bins=exclude)
    record.add("null", {**null_cal.as_row(), "anchor_bin": anchor_bin, "anchor_source": anchor_source,
                        "exchangeability_rank_basis": ("selected point" if (sel is not None and sel.rho is not None) else
                                                       ("diagnostic point" if exch_rho is not None else ""))})
    # the same description on the evaluation block (the blocked-evaluation table's drift columns)
    if split.evaluation.any():
        null_eval = nulls.calibrate_null(p, split.evaluation, anchor_bin=anchor_bin, bulk_mask=bulk,
                                         era_label=f"{era_label}/evaluation", off_era=off_for_eval, fine_t=ratio,
                                         exclude_fine_bins=exclude)
        record.add("null_evaluation", null_eval.as_row())
    else:
        record.add("null_evaluation", None)
    if sel is not None:
        selection.write_operating_points(sel, ch_dir / "operating_points.csv")
        # the keep-everything residual on each block, whether or not a point was selected (r_keep of the chain)
        keep = {}
        for name, block in (("calibration", split.calibration), ("evaluation", split.evaluation)):
            rows = np.flatnonzero(np.asarray(block, dtype=bool))
            try:
                keep[f"keep_everything_r_sys_{name}"] = float(selection.systematic_residuals(p, rows, floor, gain).mean()) if rows.size else math.nan
            except ValueError:
                keep[f"keep_everything_r_sys_{name}"] = math.nan
        # why the drift screen refused: the candidate it refused on, and the drift a selected point would see
        drift = {}
        try:
            bundle = selection.build_residual_score_bundle(
                p.path, split.calibration, anchor_bin=int(anchor_bin),
                designated_half_width=selection.DESIGNATED_HALF_WIDTH, bulk_mask=bulk)
            drift = selection.drift_diagnostic(
                bundle, selection.systematic_residuals(p, bundle.source_row_index, floor, gain),
                p.frame_time[bundle.source_row_index])
        except Exception as exc:
            notes.append(f"drift diagnostic: {type(exc).__name__}: {exc}")
            drift = {"drift_status": f"{type(exc).__name__}"}

        # the coarse rule's own frontier (f, r_sys) on the calibration block, beside the fine surface
        frontier = _coarse_frontier(p, split.calibration, floor, gain, r_tol)
        _write_csv([{"channel": ch, **row} for row in frontier], ch_dir / "coarse_frontier.csv")
        record.add("selection", {**sel.as_row(), **selection.surface_summary(sel), **keep, "anchor_source": anchor_source,
                                 "gain_basis": gain_basis, **_frontier_summary(frontier), **drift})
    else:
        record.add("selection", None)

    # 8b. the operating point: the knee of the calibration block's own mask-against-residual frontier,
    # applied to the evaluation block the calibration never saw, with the before-and-after spectra it produces
    op = None
    if sel is not None and sel.points:
        op = operating.choose(ch, list(sel.points))
        operating.write_operating_points([op], ch_dir / "operating_point.csv")
        record.add("operating", op.as_row())
        for note in op.notes:
            notes.append(f"operating point: {note}")
    else:
        record.add("operating", None)
    spectra = []
    if op is not None and op.point is not None and split.evaluation.any() and "psd_frame_db_i16" in p.archive.files:
        for basis, rho, eta_q16, eta in (("operating point", op.point.rho, op.point.eta_q16, op.point.eta),):
            try:
                kept_frames = masked_spectra.kept_at_point(p, split.evaluation, anchor_bin=anchor_bin, bulk_mask=bulk,
                                                           rho=rho, eta_q16=eta_q16)
                spectra.append(masked_spectra.measure(p, split.evaluation, kept_frames, basis=basis, rho=rho,
                                                      eta_q16=eta_q16, eta=eta))
            except Exception as exc:
                notes.append(f"held-out spectra ({basis}): {type(exc).__name__}: {exc}")
        # the survey flag on the same block, as the reference the operating point is measured against
        try:
            spectra.append(masked_spectra.measure(p, split.evaluation, split.evaluation & ~p.rejected,
                                                  basis="survey flag", rho=0, eta_q16=selection.Q16_SCALE, eta=1.0))
        except Exception as exc:
            notes.append(f"held-out spectra (survey flag): {type(exc).__name__}: {exc}")
    if spectra:
        masked_spectra.write_spectra_rows(spectra, ch_dir / "held_out_spectra.csv")
        masked_spectra.write_spectra_npz(spectra, ch_dir / "held_out_spectra.npz")
        record.add("held_out", {f"{s.basis.replace(' ', '_')}_{k}": v for s in spectra for k, v in s.as_row().items()
                                if k not in ("channel", "freq_id", "basis")})
    else:
        record.add("held_out", None)

    # 9. the incumbent flaggers on the same frames (chapter 9's flagger table)
    try:
        flag_cmp = flaggers.compare(
            p, era_mask, floor_db=floor.db, floor_evidence=floor.evidence, era_label=era_label,
            diagnostic=(sel.diagnostic if sel is not None else None), anchor_bin=anchor_bin, bulk_mask=bulk)
        record.add("flaggers", flaggers.channel_row(flag_cmp))
    except Exception as exc:
        flag_cmp = None
        record.add("flaggers", None)
        notes.append(f"flaggers: {type(exc).__name__}: {exc}")

    # 10. screening
    flag_rate = float(p.rejected[era_mask].mean()) if era_mask.any() else math.nan
    ev = sel.evaluation if (sel is not None and sel.evaluation is not None) else None
    inputs = screening.ScreeningInputs(
        off_era=off_era_current,
        selection_status=sel.status if sel is not None else "refused",
        tolerance_fraction=(sel.tolerance_fraction if (sel is not None and sel.status == "feasible") else math.nan),
        masked_fraction=(sel.masked_fraction if (sel is not None and sel.status == "feasible") else math.nan),
        survey_flag_rate=flag_rate, floor_evidence=floor.evidence, correlation_quality=tau_quality,
        refusal=sel.refusal if sel is not None else "no selection",
        claim_status=sel.claim_status if sel is not None else "",
        era_state=era.state if era else "", era_level_db=float(era.level_median_db) if era else math.nan,
        anchor_sentinel=anchor_note, stability_status=sel.stability.get("status", "") if sel is not None else "")
    screen = screening.screen(inputs)
    record.add("screening", {**screen.as_row(), "survey_flag_rate_era": flag_rate, "off_era_current": off_era_current,
                             "off_through": off_through or "", "off_from": off_from or "",
                             "evaluation_masked_fraction_at_diagnostic": ev.masked_fraction if ev is not None else math.nan,
                             "evaluation_R_at_diagnostic": ev.tolerance_fraction if ev is not None else math.nan})

    p.close()
    return {
        "record": record,
        "era_rows": eras.era_rows(table), "era_channel_row": eras.channel_row(table),
        "anchor_rows": [anchors.anchor_row(a) for a in anchor_results],
        "containment_row": containment_row,
        "null_row": null_cal.as_row(),
        "selection_row": sel.as_row() if sel is not None else None,
        "chain_row": ch_res.as_row() if ch_res is not None else None,
        "screening_row": {"channel": ch, **screen.as_row()},
        "flagger_rows": [r.as_row() for r in flag_cmp.rows] if flag_cmp is not None else [],
        "operating_row": op.as_row() if op is not None else None,
        "held_out_rows": [s.as_row() for s in spectra],
        "seconds": time.time() - t0,
    }


def _worlds(results: Sequence[dict]) -> list:
    """Each channel's operating point carried through the four delay-cut worlds.

    Derived, not measured: it reads each channel's chosen point and its
    forecast bins, so it needs no product and runs in the parent. A channel
    with no operating point, or no overlapping forecast bin, is still listed
    with the reason -- the table is an inventory of every channel, not of the
    ones that happen to have a number.
    """
    try:
        rows = worlds.tolerances()
        bins_of = tolerances.ledger_channel_bins(tolerances.out_dir() / tolerances.MAPPING_NAME)
    except Exception as exc:                                  # no banks, or no released mapping
        print(f"worlds: skipped ({type(exc).__name__}: {exc})", flush=True)
        return []
    out = []
    for r in results:
        ch = r["record"].channel
        op = r["operating_row"] or {}
        out.append(worlds.channel_worlds(ch, bins_of.get(ch, ()),
                                         float(op.get("operating_r_sys", math.nan)),
                                         float(op.get("operating_masked_fraction", math.nan)), rows))
    return out


def _write_csv(rows: Sequence[dict], path: Path) -> Path | None:
    import csv
    rows = [r for r in rows if r]
    if not rows:
        return None
    keys: list[str] = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if (isinstance(v, float) and not math.isfinite(v)) or v is None else repr(v) if isinstance(v, float) else v)
                        for k, v in ((k, r.get(k)) for k in keys)})
    return path


def _worker(args):
    path, out_dir, kwargs = args
    try:
        return process_channel(path, out_dir, **kwargs)
    except Exception:
        return {"error": traceback.format_exc(), "path": path}


def run_archive(products_dir: Path | str, out_dir: Path | str, *, workers: int = 6, replicates: int = blocks.DEFAULT_REPLICATES,
                seed: int = blocks.DEFAULT_SEED, channels: Sequence[int] | None = None,
                era_config: eras.EraConfig | None = None, generated: str | None = None) -> dict:
    products_dir, out = Path(products_dir), Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    producer = _producer()                     # read once, before any work: the code that runs is the code named
    paths = sorted(products_dir.glob("*.npz"))
    opened = [Product(p) for p in paths]
    all_channels = {p.geometry.physical_channel: p for p in opened}
    config = era_config or eras.DEFAULT_CONFIG
    # the campaign snapshot is the last populated month over every product present, whatever subset runs
    campaign_last = eras.campaign_last_populated_month(list(all_channels.values()), config)
    by_channel = {c: all_channels[c] for c in channels} if channels else all_channels
    tol_rows = {r.channel: r.as_row() for r in tolerances.channel_tolerances()}
    tolerances.write_channel_tolerances(tolerances.channel_tolerances(), out / "tables" / "channel_tolerances.csv")
    jobs = [(str(p.path), str(out), dict(campaign_last_month=campaign_last, replicates=replicates, seed=seed,
                                         era_config=config, tolerance_row=tol_rows.get(c)))
            for c, p in sorted(by_channel.items())]
    for p in opened:
        p.close()
    results, errors = [], []
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=int(workers)) as pool:
        futures = [pool.submit(_worker, job) for job in jobs]
        for fut in as_completed(futures):
            r = fut.result()
            if "error" in r:
                errors.append(r)
                print(f"FAILED {Path(r['path']).name}:\n{r['error']}", flush=True)
            else:
                results.append(r)
                print(f"done ch{r['record'].channel:02d} in {r['seconds']:.0f}s: {r['screening_row']['screening_class']}", flush=True)
    results.sort(key=lambda r: r["record"].channel)

    # aggregate tables
    tables = out / "tables"
    _write_csv([row for r in results for row in r["era_rows"]], tables / "eras.csv")
    _write_csv([r["era_channel_row"] for r in results], tables / "eras_channels.csv")
    _write_csv([row for r in results for row in r["anchor_rows"]], tables / "anchors.csv")
    cont_rows = [r["containment_row"] for r in results if r["containment_row"] is not None]
    if cont_rows:
        psd.write_containment_csv(cont_rows, tables / "containment.csv")
        psd.write_kstar_csv(psd.k_star_table(cont_rows), tables / "kstar.csv")
    _write_csv([r["null_row"] for r in results], tables / "nulls.csv")
    _write_csv([r["selection_row"] for r in results], tables / "selection.csv")
    _write_csv([r["chain_row"] for r in results], tables / "chain.csv")
    _write_csv([r["screening_row"] for r in results], tables / "screening.csv")
    _write_csv([row for r in results for row in r["flagger_rows"]], tables / "flaggers.csv")
    _write_csv([r["operating_row"] for r in results], tables / "operating_points.csv")
    _write_csv([row for r in results for row in r["held_out_rows"]], tables / "held_out_spectra.csv")
    world_rows = _worlds(results)
    if world_rows:
        worlds.write_world_rows(world_rows, tables / "worlds.csv")
        by_ch = {w.channel: w for w in world_rows}
        for r in results:                       # the section rides in the channel's own record
            w = by_ch.get(r["record"].channel)
            if w is not None:
                r["record"].add("worlds", w.as_row())

    book = ledger.Ledger(run={
        "generated": generated or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "producer": {**producer, "commit_at_end": git_commit(ROOT),
                     "source_changed_during_run": _producer()["source_digest"] != producer["source_digest"]},
        "products_dir": str(products_dir), "products": {p.name: sha256_of(p) for p in paths},
        "channels": sorted(by_channel), "campaign_last_month": blocks.month_label(campaign_last),
        "era_config": json.loads(config.canonical_json()), "era_config_digest": config.digest,
        "bootstrap": {"replicates": replicates, "seed": seed},
        "provisional": {"stability.minimum_half_retained_frames": selection.PROVISIONAL_MIN_HALF_RETAINED,
                        "stability.maximum_cost_ratio": selection.PROVISIONAL_MAX_COST_RATIO,
                        "stability.maximum_systematic_residual_ratio": selection.PROVISIONAL_MAX_SYSTEMATIC_RATIO,
                        "occupancy_wall_masked_fraction": screening.OCCUPANCY_WALL_MASKED_FRACTION,
                        "occupancy_wall_flag_rate": screening.OCCUPANCY_WALL_FLAG_RATE,
                        "null_scale_probes": list(nulls.CORE_PROBES), "containment_window_hz": psd.WINDOW_HZ, "e_min": psd.E_MIN},
        "errors": [{"path": e["path"], "error": e["error"].splitlines()[-1]} for e in errors],
        "seconds": time.time() - t0,
    })
    for r in results:
        book.add(r["record"])
    book.write(out / "ledger")
    return {"channels": [r["record"].channel for r in results], "errors": errors, "out": str(out), "seconds": time.time() - t0}
