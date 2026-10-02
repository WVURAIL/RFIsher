"""``rfisher verdict archive``: from the handoff and one tolerance table to the screen.

Reads a characterization directory (checked by :mod:`.handoff`) and one
``tolerances.csv``, and writes into ``out``:

- ``verdict.csv``: one row per band, fine family and scenario, with the
  deployable set, the selector's choice and the least-R candidate, and one
  ``union`` row per band and scenario over the fine families read (the
  selection pooled over them, and their least-residual point: the
  surface's, as the detector records it, when every family of the surface
  is read);
- ``verdict_points.csv``: every fine calibration candidate of the rule
  scenario, with its cost, R, feasibility and membership of the set;
- ``screen.csv``: one row per band, the outcome under the precedence;
- ``sensitivity.csv``: the named sensitivities (:mod:`.sensitivity`);
- ``manifest.json``: the sha256 of every file read and the producer.

Nothing here reads a detector product, a response bank or a forecast.
"""
from __future__ import annotations

import csv
import io
import json
import math
from pathlib import Path
from typing import Mapping, Sequence

from .. import policy as _policy
from ..provenance import producer_identity
from . import handoff, interval, screening, sensitivity

UNION = "union"
RULE = "rule"
KEY_COLUMNS = ("band_id", "band_low_mhz", "band_high_mhz", "era_label",
               "candidate_set", "population", "threshold_family")
VERDICT_COLUMNS = KEY_COLUMNS + (
    "scenario", "role", "r_tol", "tolerance_basis", "eta_pfa",
    "eta_pfa_status", "eta_eval", "eta_sci", "lower_bound_source",
    "interval_low", "interval_high", "interval_status", "exclusion_status",
    "feasible_count", "feasible_contiguous", "selected_threshold_family",
    "selected_candidate_order", "selected_eta", "selected_masked_fraction",
    "selected_r_sys", "selected_R", "selected_cost", "plateau_members",
    "plateau_eta_low", "plateau_eta_high", "min_R", "min_R_eta",
    "min_R_incoherent", "min_R_floor_share", "false_alarm_certified")
POINT_COLUMNS = ("band_id", "candidate_set", "population", "block",
                 "threshold_family", "candidate_order", "eta", "scenario",
                 "cost", "R", "feasible", "in_deployable_set")
SCHEMA = "rfisher_verdict_v1"


def _cell(value):
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return ""
    if isinstance(value, float):
        return repr(value)
    return value


def render(rows: Sequence[Mapping], columns: Sequence[str]) -> bytes:
    """CSV bytes: floats as repr, NaN and None empty, ``\\n`` line ends."""
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(columns),
                            lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: _cell(row.get(k)) for k in columns})
    return stream.getvalue().encode("utf-8")


def _key(row: Mapping) -> dict:
    return {k: row[k] for k in KEY_COLUMNS}


def _selection_fields(chosen: interval.Selection) -> dict:
    point = chosen.selected
    low, high = chosen.plateau_eta
    return {
        "selected_threshold_family": point.family if point else "",
        "selected_candidate_order": point.candidate_order if point else None,
        "selected_eta": point.eta if point else math.nan,
        "selected_masked_fraction": point.masked_fraction if point
        else math.nan,
        "selected_r_sys": point.r_sys if point else math.nan,
        "selected_R": point.R if point else math.nan,
        "selected_cost": point.cost if point else math.nan,
        "plateau_members": chosen.plateau_members,
        "plateau_eta_low": low, "plateau_eta_high": high}


def _family_row(key, tol, readings: screening.Readings, pol,
                alpha=None) -> dict:
    keep, excl = readings.keep, readings.exclusion
    least = keep.least
    chosen = interval.select(keep.members, pol)
    incoherent = (float(least.row["r_sys_incoherent"]) / float(tol["r_tol"])
                  if least is not None else math.nan)
    return {**key, "scenario": tol["scenario"], "role": tol["role"],
            "r_tol": tol["r_tol"], "tolerance_basis": tol["tolerance_basis"],
            "eta_pfa": keep.eta_pfa, "eta_pfa_status": keep.eta_pfa_status,
            "eta_eval": keep.eta_eval, "eta_sci": keep.eta_sci,
            "lower_bound_source": keep.lower_bound_source,
            "interval_low": keep.interval_low,
            "interval_high": keep.interval_high,
            "interval_status": keep.status, "exclusion_status": excl.status,
            "feasible_count": keep.feasible_count,
            "feasible_contiguous": keep.contiguous,
            **_selection_fields(chosen),
            "min_R": least.R if least else math.nan,
            "min_R_eta": least.eta if least else math.nan,
            "min_R_incoherent": incoherent,
            "min_R_floor_share": float(least.row["floor_share"]) if least
            else math.nan,
            "false_alarm_certified": screening.certified(
                keep, readings.summary, alpha)}


def _union_row(key, tol, families: Sequence[screening.Readings],
               summary: Mapping | None, status_override: str, pol, *,
               whole_surface: bool = True, alpha=None) -> dict:
    row = {**key, "threshold_family": UNION, "scenario": tol["scenario"],
           "role": tol["role"], "r_tol": tol["r_tol"],
           "tolerance_basis": tol["tolerance_basis"]}
    r_tol = float(tol["r_tol"]) if tol["r_tol"] is not None else math.nan
    if status_override:
        row["interval_status"] = status_override
    elif families:
        keep = [f.keep for f in families]
        excl = [f.exclusion for f in families]

        def union_status(parts):
            statuses = {p.status for p in parts}
            if interval.STATUS_THINNED in statuses:
                return interval.STATUS_THINNED
            if interval.STATUS_NONEMPTY in statuses:
                return interval.STATUS_NONEMPTY
            if statuses == {interval.STATUS_NO_EVALUABLE}:
                return interval.STATUS_NO_EVALUABLE
            for above in (interval.STATUS_PFA_ABOVE,
                          interval.STATUS_EVAL_ABOVE):
                if above in statuses:
                    return above
            return interval.STATUS_NO_CANDIDATE
        members = [p for part in keep for p in part.members]
        chosen = interval.select(members, pol)
        row.update(
            interval_status=union_status(keep),
            exclusion_status=union_status(excl),
            feasible_count=sum(p.feasible_count for p in keep),
            eta_eval=min((p.eta_eval for p in keep), default=math.nan),
            eta_sci=max((p.eta_sci for p in keep if math.isfinite(p.eta_sci)),
                        default=math.nan),
            false_alarm_certified=any(screening.certified(
                f.keep, f.summary, alpha) for f in families),
            **_selection_fields(chosen))
    else:
        row["interval_status"] = interval.STATUS_NO_EVALUABLE
    if summary is None or not math.isfinite(r_tol):
        return row
    if whole_surface:
        # every family of the surface is read: its least-residual point, as
        # the detector records it (with the detector's tie rule)
        if summary["least_residual_rho"] is not None:
            row.update(
                min_R=float(summary["least_residual_r_sys"]) / r_tol,
                min_R_eta=summary["least_residual_eta"],
                min_R_incoherent=float(
                    summary["least_residual_r_sys_incoherent"]) / r_tol,
                min_R_floor_share=summary["least_residual_floor_share"])
        return row
    least = [f.keep.least for f in families if f.keep.least is not None]
    if least:
        best = min(least, key=lambda p: (p.r_sys, p.masked_fraction,
                                         p.candidate_order))
        row.update(
            min_R=best.R, min_R_eta=best.eta,
            min_R_incoherent=float(best.row["r_sys_incoherent"]) / r_tol,
            min_R_floor_share=float(best.row["floor_share"]))
    return row


PROFILE = "science_model.yaml"


def declared_residual(project: str | Path) -> tuple[dict, tuple[str, ...]]:
    """The residual reference and shapes the project's science profile declares."""
    import yaml

    with (Path(project) / PROFILE).open(encoding="utf-8") as fh:
        profile = yaml.safe_load(fh)
    return dict(profile["r_reference"]), tuple(profile["residual_shapes"])


def verdict_archive(characterization: str | Path, tolerances: str | Path,
                    project: str | Path, out: str | Path) -> dict:
    """Write the archive verdict (see the module docstring); return its summary.

    The handoff must declare the residual reference and shape the project's
    science profile declares.
    """
    r_reference, shapes = declared_residual(project)
    return run(characterization, tolerances, project, out,
               r_reference=r_reference, residual_shapes=shapes)


def _tolerance_path(path: Path) -> Path:
    return path / "tolerances.csv" if path.is_dir() else path


def run(characterization: str | Path, tolerances: str | Path,
        project: str | Path, out: str | Path, *, r_reference: Mapping,
        residual_shapes: Sequence[str]) -> dict:
    """Write the archive verdict; ``r_reference`` and ``residual_shapes`` are
    the science model's, which the handoff must match."""
    pol = _policy.load(project)
    screening.check_precedence(pol)
    oc = handoff.read_characterization(characterization,
                                       r_reference=r_reference,
                                       residual_shapes=residual_shapes)
    if oc.manifest.get("fine_surface_scope") == handoff.COMPLETE_SCOPE:
        raise handoff.HandoffError(
            "complete calibration handoffs are forward-only; use 'rfisher "
            "response threshold'. The archive selector does not accept this scope.")
    alpha = (oc.manifest.get("null_policy") or {}).get("alpha")
    tol_path = _tolerance_path(Path(tolerances))
    tol_rows = handoff.read_tolerances(tol_path, oc.bands)
    by_band_tol: dict[str, list] = {}
    for t in tol_rows:
        by_band_tol.setdefault(t["band_id"], []).append(t)
    rows_by_band: dict[str, list] = {}
    for r in oc.table:
        rows_by_band.setdefault(str(r["band_id"]), []).append(r)
    summary_by_band: dict[str, list] = {}
    for s in oc.summary:
        summary_by_band.setdefault(str(s["band_id"]), []).append(s)
    screened = [b for b, v in oc.bands.items() if v.get("role") == "screened"]
    verdict_rows, point_rows, screen_rows, sens_rows = [], [], [], []
    for band in screened:
        summaries = summary_by_band.get(band, [])
        fine = [s for s in summaries if s["candidate_set"] == interval.FINE]
        first = (fine or summaries or [None])[0]
        key = (_key(first) if first is not None else
               {"band_id": band, "band_low_mhz": oc.bands[band]["low_mhz"],
                "band_high_mhz": oc.bands[band]["high_mhz"],
                "era_label": "", "candidate_set": interval.FINE,
                "population": "", "threshold_family": UNION})
        key = {**key, "candidate_set": interval.FINE}
        tols = by_band_tol.get(band, [])
        rule = [t for t in tols if t["role"] == RULE]
        if len(rule) > 1:
            raise handoff.HandoffError(f"band {band}: {len(rule)} rule "
                                       "scenarios in the tolerance table; "
                                       "a band has one")
        rule_tol = rule[0] if rule else None
        rule_families = []
        surface_families = {
            r["threshold_family"] for r in rows_by_band.get(band, [])
            if r["candidate_set"] == interval.FINE
            and r["block"] == interval.CALIBRATION}
        for tol in tols:
            r_tol = float(tol["r_tol"])
            if not math.isfinite(r_tol):
                verdict_rows.append(_union_row(key, tol, [], None,
                                               interval.STATUS_TOLERANCE, pol))
                continue
            families = screening.family_readings(
                rows_by_band.get(band, []), fine, r_tol, pol,
                thinned=oc.thinned)
            refused = screening.detector_refusal(summaries, families)
            for f in families:
                verdict_rows.append(_family_row(
                    {**_key(f.summary)}, tol, f, pol, alpha))
            verdict_rows.append(_union_row(
                key, tol, families, fine[0] if fine else None,
                interval.STATUS_DETECTOR if (refused and not families) else "",
                pol, whole_surface={f.family for f in families}
                == surface_families, alpha=alpha))
            if tol is rule_tol:
                rule_families = families
                candidates = interval.fine_candidates(
                    rows_by_band.get(band, []), pol)
                for f in families:
                    members = {q.candidate_order for q in f.keep.members}
                    for p in interval.points(
                            [r for r in candidates
                             if r["threshold_family"] == f.family],
                            r_tol, pol):
                        point_rows.append({
                            **{k: p.row[k] for k in (
                                "band_id", "candidate_set", "population",
                                "block", "threshold_family",
                                "candidate_order", "eta")},
                            "scenario": tol["scenario"], "cost": p.cost,
                            "R": p.R, "feasible": p.feasible,
                            "in_deployable_set": p.candidate_order in members})
        outcome = screening.screen(band, rule_tol, summaries, rule_families,
                                   pol, alpha=alpha)
        screen_rows.append(outcome.as_row())
        candidates = interval.fine_candidates(rows_by_band.get(band, []), pol)
        exclusion_points = []
        for f in rule_families:
            column = screening.exclusion_residual(
                f.summary["chain_gain_status"], pol)
            exclusion_points += [(r[column], f.family) for r in candidates
                                 if r["threshold_family"] == f.family]
        sens_rows += sensitivity.sensitivities(
            band, outcome.outcome, tols, exclusion_points)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    written = {}
    for name, rows, columns in (
            ("verdict.csv", verdict_rows, VERDICT_COLUMNS),
            ("verdict_points.csv", point_rows, POINT_COLUMNS),
            ("screen.csv", screen_rows, screening.SCREEN_COLUMNS),
            ("sensitivity.csv", sens_rows, sensitivity.COLUMNS)):
        data = render(rows, columns)
        (out / name).write_bytes(data)
        written[name] = handoff.sha256_file(out / name)
    read = {**{f"characterization/{k}": v for k, v in oc.sha256.items()},
            "tolerances.csv": handoff.sha256_file(tol_path)}
    manifest = {"schema": SCHEMA, "files": written, "read": read,
                "rule_version": screening.RULE_VERSION,
                "producer": producer_identity(read, pol.sha256())}
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8")
    return {"screen": screen_rows, "files": written}
