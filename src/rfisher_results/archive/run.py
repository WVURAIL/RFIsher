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

from . import anchors, blocks, chain, eras, ledger, nulls, psd, screening, selection, tolerances
from .numbers import git_commit
from .products import Product, sha256_of

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


def verified_off(product: Product, months: np.ndarray) -> tuple[np.ndarray | None, str | None, str | None]:
    """Frames of the channel's verified transmitter-off epoch, and its month bounds."""
    ch = product.geometry.physical_channel
    off_from = residual.SIGN_OFF_FROM.get(ch)
    off_through = residual.SIGN_ON_OFF_THROUGH.get(ch)
    mask = None
    if off_from:
        y, m = (int(x) for x in off_from.split("-"))
        mask = product.selected & (months >= y * 12 + m - 1)
    elif off_through:
        y, m = (int(x) for x in off_through.split("-"))
        mask = product.selected & (months <= y * 12 + m - 1)
    return mask, off_through, off_from


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

    # 1. eras
    table = eras.era_table(p, config=config, campaign_last_month=campaign_last_month, station_record=station_records(ch))
    eras.write_era_json(table, ch_dir / "eras.json")
    era = table.current_era
    era_mask = table.current_era_mask(p)
    months = eras.frame_months(p)
    off_mask, off_through, off_from = verified_off(p, months)
    off_era_current = bool(off_mask is not None and era is not None and off_mask[era_mask].mean() > 0.5) if era_mask.any() else False
    record.add("era", eras.channel_row(table))
    era_label = _label(era)

    # 2. blocks
    split = blocks.split_blocks(p.frame_unit_index, p.unit_time, era_mask, frame_time=p.frame_time, minimum_months=1)
    record.add("blocks", {
        "status": split.status, "detail": split.detail, "boundary_time": split.boundary_time,
        "calibration_frames": split.calibration_frames, "evaluation_frames": split.evaluation_frames,
        "calibration_units": split.calibration_units, "evaluation_units": split.evaluation_units,
        "calibration_months": len(split.calibration_months), "evaluation_months": len(split.evaluation_months),
        "boundary_month": blocks.month_label(int(blocks.month_index([split.boundary_time])[0])) if math.isfinite(split.boundary_time) else "",
    })

    # 3. anchors
    ratio = anchors.fine_ratio(p)
    anchor_results = []
    anc = {}
    for label, mask in (("calibration", split.calibration), ("evaluation", split.evaluation), ("current_era", era_mask)):
        anc[label] = anchors.anchor(p, mask, label, ratio=ratio, replicates=replicates, seed=seed)
        anchor_results.append(anc[label])
    if table.current_index > 0:
        anc["previous_era"] = anchors.anchor(p, table.era_mask(p, table.current_index - 1), "previous_era", ratio=ratio,
                                             replicates=replicates, seed=seed)
        anchor_results.append(anc["previous_era"])
    anchors.write_contrast_curves(anchor_results, ch_dir / "anchor_contrast.csv")
    of_record = anc["calibration"] if anc["calibration"].status == "ok" else anc["current_era"]
    record.add("anchor", anchors.anchor_row(of_record))
    record.add("anchor_evaluation", anchors.anchor_row(anc["evaluation"]))
    record.add("anchor_era", anchors.anchor_row(anc["current_era"]))
    if "previous_era" in anc:
        row = anchors.anchor_row(anc["previous_era"])
        row["shift_from_previous_bins"] = anchors.anchor_shift_bins(anc["current_era"], anc["previous_era"]) if anc["previous_era"].status == "ok" else ""
        record.add("anchor_previous", row)
    else:
        record.add("anchor_previous", None)

    # 4. containment (current era; needs the per-frame spectra the campaign products carry)
    if era_mask.any() and "psd_frame_db_i16" in p.archive.files:
        cont = psd.containment(p, era_mask, anchor_aliases=bool(of_record.aliased_out_of_window))
        psd.write_spectra_json([cont], ch_dir / "spectra_window.json", provenance=f"current era {era_label}")
        containment_row = cont.row
        record.add("containment", dataclasses.asdict(cont.row))
    else:
        cont, containment_row = None, None
        record.add("containment", None)
        if era_mask.any():
            notes.append("containment skipped: product carries no per-frame spectra")

    # 5. chain (archive-wide on population outside the declared off epoch)
    try:
        ch_res = chain.residual_chain(p.path, off_through=off_through, off_from=off_from)
        record.add("chain", ch_res.as_row())
        gain, tau_quality = ch_res.gain, ch_res.tau_quality
    except Exception as exc:  # the chain refuses loudly on some channels; record, do not stop
        ch_res = None
        record.add("chain", None)
        notes.append(f"chain: {type(exc).__name__}: {exc}")
        gain, tau_quality = 1.0, "unmeasured"

    # 6. tolerance
    tol_row = tolerance_row or {}
    r_tol = float(tol_row.get("r_tol_dilation", math.nan))
    record.add("tolerance", tol_row or None)

    # 7. null calibration (floor first; exchangeability after the selection)
    anchor_bin = int(of_record.anchor_bin) if of_record.status == "ok" else g.nominal_fine_bin
    bulk = of_record.bulk if of_record.status == "ok" else anchors.bulk_mask(anchor_bin, pad_factor=p.fine_pad_factor,
                                                                             guard_fine_bins=p.fine_guard_bins,
                                                                             census_excluded_bins=p.fine_census_excluded_bins)
    null_cal = nulls.calibrate_null(p, era_mask, anchor_bin=anchor_bin, bulk_mask=bulk, era_label=era_label,
                                    off_era=off_mask, fine_t=ratio)
    floor = selection.Floor(null_cal.floor.db, null_cal.floor.evidence, null_cal.floor.population)

    # 8. selection on the calibration block, replayed on the evaluation block
    if math.isfinite(r_tol) and split.calibration.any():
        sel = selection.select_operating_point(
            p, split.calibration, split.evaluation, anchor_bin=anchor_bin, bulk_mask=bulk, r_tol=r_tol, floor=floor,
            era_label=era_label, gain=gain, latest_era=True, off_era=off_era_current,
            bootstrap_replicates=replicates, bootstrap_seed=seed)
    else:
        sel = None
        notes.append("selection skipped: no tolerance or no calibration frames")
    if sel is not None and sel.rho is not None:
        null_cal = nulls.calibrate_null(p, era_mask, anchor_bin=anchor_bin, bulk_mask=bulk, era_label=era_label,
                                        off_era=off_mask, rho=sel.rho, quiet_block=split.evaluation, fine_t=ratio)
    record.add("null", null_cal.as_row())
    record.add("selection", sel.as_row() if sel is not None else None)

    # 9. screening
    flag_rate = float(p.rejected[era_mask].mean()) if era_mask.any() else math.nan
    ev = sel.evaluation if (sel is not None and sel.evaluation is not None) else None
    inputs = screening.ScreeningInputs(
        off_era=off_era_current,
        selection_status=sel.status if sel is not None else "refused",
        tolerance_fraction=(ev.tolerance_fraction if ev is not None else (sel.tolerance_fraction if sel is not None else math.nan)),
        masked_fraction=(ev.masked_fraction if ev is not None else (sel.masked_fraction if sel is not None else math.nan)),
        survey_flag_rate=flag_rate, floor_evidence=floor.evidence, correlation_quality=tau_quality,
        refusal=sel.refusal if sel is not None else "no selection",
        claim_status=sel.claim_status if sel is not None else "")
    screen = screening.screen(inputs)
    record.add("screening", {**screen.as_row(), "survey_flag_rate_era": flag_rate, "off_era_current": off_era_current,
                             "off_through": off_through or "", "off_from": off_from or ""})

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
        "seconds": time.time() - t0,
    }


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
    paths = sorted(products_dir.glob("*.npz"))
    opened = [Product(p) for p in paths]
    by_channel = {p.geometry.physical_channel: p for p in opened}
    if channels:
        by_channel = {c: by_channel[c] for c in channels}
    config = era_config or eras.DEFAULT_CONFIG
    campaign_last = eras.campaign_last_populated_month(list(by_channel.values()), config)
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

    book = ledger.Ledger(run={
        "generated": generated or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "producer": {"repository": "WVURAIL/RFIsher", "commit": git_commit(ROOT), "module": "rfisher_results.archive.run"},
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
