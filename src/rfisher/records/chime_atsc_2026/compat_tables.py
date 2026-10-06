"""The frozen layouts of the two 2026 archive releases, written from the handoff.

The archive releases of record wrote one tree in which the detector's
characterization and the science pricing were mixed: ``tables/{selection,
screening, worlds, channel_tolerances, operating_points, chain}.csv``, the
per-band ``channels/chNN/{operating_points, operating_point,
coarse_frontier}.csv`` and the ledger (``ledger/channels/*.json``,
``ledger/ledger.csv``, ``ledger/run.json``). This module writes those files
from the detector's characterization directory and the tolerance tables,
with the tokens and column orders the releases have:

- the detector's values are copied from its tables, summary and ledger
  sections; a section key the detector added after the releases is left out,
  and the two science columns it no longer writes (the delay key and its
  suppression) are put back from the rule scenario;
- the science values are priced here: the tolerance of each band (the rule
  scenario), R = r / r_tol of every written candidate, the selection the
  frozen selector made (the verdict's pooled selector), the screening class
  and its reasons (the frozen rule, verbatim), and the ledger's tolerance,
  selection, operating and screening sections.

Post-processing is not modelled, and the growth rate sets no tolerance
(stage P, 2026-10-06). The releases' delay-filter scenarios (``worlds.csv``,
the ledger's ``worlds`` section and ``run.json``'s ``worlds_contract``) and
their f sigma_8 tolerance columns (``r_tol_fs8`` and ``fs8_status`` of
``channel_tolerances.csv`` and of the ledger's tolerance section, the growth
columns of ``ladder_pricing.csv``) are not written; the frozen releases keep
them. Every other file and column is the releases'. The chain's delay key and
its suppression are the frozen policy's (``none``, 0 dB: no filter credit).

A band is priced where the frozen run priced it: where the rule scenario has
a tolerance and the detector characterized a surface. A value the handoff
does not carry is never guessed: :class:`NotReproducible` names it.

The selector policy and the science register these layouts were priced
under are frozen with them (``data/policy_2026_archive``, byte copies of the
project's registers at the release of these records): a later change of the
project's policy, such as the fine rank the verdict reads, changes the
verdict and leaves these layouts as the releases wrote them.
"""
from __future__ import annotations

import csv
import io
import json
import math
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from typing import Any, Mapping, Sequence

from rfisher import policy as _policy
from rfisher.forecast.radiofisher_bao.model import (RadioFisherBAO,
                                                    packaged_table,
                                                    redshift_range)
from rfisher.provenance import producer_identity, source_digest
from rfisher.tolerance import table as tolerance_table
from rfisher.tolerance.bands import tolerance_of
from rfisher.verdict import handoff, interval

from . import ladder_pricing

RELEASES = ("archive_author_eras_2026_09_23", "archive_no_split_2026_09_24_r2")
# The characterization each release needs: (record, variance split, tie rule)
# of the handoff manifest. The no-split release is the detector's default.
RELEASE_CHOICES = {
    "archive_author_eras_2026_09_23": {
        ("archive_author_eras_2026_09_23", "booked_when_tau_usable",
         "first_minimum")},
    "archive_no_split_2026_09_24_r2": {
        ("archive_no_split_2026_09_24_r2", "off", "selector_order"),
        (None, "off", "selector_order")},
}
LEDGER_SCHEMA = {"name": "rfisher-archive-ledger", "version": 1}
# The registers the two releases were priced under (see the module docstring).
FROZEN_POLICY = ("data", "policy_2026_archive")


def frozen_policy():
    """The selector policy and science register of the two archive releases."""
    return _policy.load(files(__package__).joinpath(*FROZEN_POLICY))
PRODUCER_REPOSITORY = "WVURAIL/RFIsher"
PRODUCER_MODULE = "rfisher.records.chime_atsc_2026.compat_tables"
PARAMETERS = ("aperp", "apar")
# The chain's delay key, as the frozen policy records it, takes no suppression.
NO_DELAY_FILTER = {"none": 0.0}
TARGET_YEARS = 1.0
DIAGNOSTIC_BASIS = "least residual on the calibration surface (no feasible point)"
SELECTED_BASIS = "selected point"
SKIPPED_NOTE = "selection skipped: no tolerance or no calibration frames"
DRIFT_NOTE = "drift diagnostic: "
EXCH_SKIPPED = "; exchangeability skipped: "
TOLERANCE_SOURCE = "authenticated no-filter bank"
SECTION_ORDER = (
    "geometry", "product", "archive_inferred_events", "era",
    "evaluation_contract", "blocks", "anchor", "anchor_calibration",
    "anchor_evaluation", "anchor_era", "anchor_previous", "containment",
    "chain", "chain_archive", "tolerance", "null", "null_evaluation",
    "selection", "operating", "held_out", "flaggers", "screening")
# Keys the detector's ledger added after the releases (left out of the
# frozen layout, which never had them).
DETECTOR_ADDITIONS = {
    "geometry": ("band_role",),
    "archive_inferred_events": ("external_record",),
    "era": ("off_independently_verified", "off_population_check",
            "off_population_null_like", "off_population_r68",
            "off_signal_free"),
}
EXCHANGE_KEYS = ("exch_rho", "exch_bulk", "exch_frames", "exch_test_bins",
                 "exch_trials", "exch_measured", "exch_predicted",
                 "exch_max_over_designated")
CHANNEL_TOLERANCE_COLUMNS = (
    "channel", "z_low", "z_high", "bins", "r_tol_dilation", "r_tol_aperp",
    "apar_over_aperp_ledger", "dilation_binding",
    "r_tol_apar", "tolerance_basis", "refusal")
SELECTION_COLUMNS = (
    "channel", "freq_id", "era", "anchor_bin", "bulk_size", "r_tol",
    "floor_db", "floor_evidence", "floor_population", "calibration_frames",
    "evaluation_frames", "frames_without_time", "status", "refusal",
    "claim_status", "rho", "q_rho", "eta_q16", "eta",
    "masked_fraction_calibration", "r_sys_calibration", "R_calibration",
    "cost", "plateau_members", "plateau_eta_low", "plateau_eta_high",
    "diagnostic_basis", "diagnostic_rho", "diagnostic_eta_q16",
    "diagnostic_eta", "diagnostic_masked_fraction", "diagnostic_r_sys",
    "diagnostic_R", "diagnostic_cost", "anchor_sentinel", "stability_status",
    "stability_reason", "stability_points_checked", "stability_points_skipped",
    "chain_gain", "residual_convention", "r_sys_unmasked_calibration",
    "masked_fraction_evaluation", "masked_fraction_evaluation_q16",
    "masked_fraction_evaluation_q84", "r_sys_evaluation",
    "r_sys_evaluation_q16", "r_sys_evaluation_q84",
    "bootstrap_blocks_evaluation", "r_sys_unmasked_evaluation",
    "kept_evaluation", "R_evaluation", "survey_flag_rate_evaluation",
    "false_alarm_rate", "false_alarm_basis")
OPERATING_COLUMNS = (
    "channel", "frontier_points", "r_floor", "margin",
    "keep_everything_r_sys", "suppression_factor", "suppression_db",
    "operating_rho", "operating_eta_q16", "operating_eta",
    "operating_masked_fraction", "operating_kept", "operating_r_sys",
    "operating_cost", "knee_rho", "knee_eta_q16", "knee_eta",
    "knee_masked_fraction", "knee_kept", "knee_r_sys", "knee_cost", "status",
    "notes")
POINT_COLUMNS = ("rho", "rank_fraction", "eta_q16", "eta", "frames", "kept",
                 "masked_fraction", "r_sys", "tolerance_fraction", "cost",
                 "feasible")
FRONTIER_COLUMNS = ("channel", "eta_c", "frames", "kept", "masked_fraction",
                    "r_sys", "R", "evaluable")
COARSE_GRID_SIZE = 108
MIN_KEPT = 30


class NotReproducible(ValueError):
    """The frozen layout needs a value the handoff does not carry."""


# ---------------------------------------------------------------- writing
def _repr_cell(value):
    """The releases' table cell: empty for NaN and None, repr for a float."""
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return ""
    return repr(value) if isinstance(value, float) else value


def _write_csv(rows: Sequence[Mapping], path: Path) -> Path | None:
    """The releases' ``_write_csv``: columns in first-seen order."""
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
        writer = csv.DictWriter(fh, fieldnames=keys, lineterminator="\n")
        writer.writeheader()
        for r in rows:
            writer.writerow({k: _repr_cell(r.get(k)) for k in keys})
    return path


def _jsonable(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    return value


def _num(value) -> float:
    try:
        return float(value) if value is not None else math.nan
    except (TypeError, ValueError):
        return math.nan


# ---------------------------------------------------------------- inputs
@dataclass
class Inputs:
    """What the layout is written from."""

    release: str
    characterization: Path
    manifest: Mapping
    summary: dict            # band -> [oc_summary rows]
    fine: dict               # band -> [fine calibration OC rows]
    coarse: dict             # band -> [coarse surface calibration OC rows]
    ladder: dict             # band -> [coarse ladder evaluation OC rows]
    ledger: dict             # band -> the detector's channel record
    ledger_names: dict       # band -> its file name
    run: Mapping
    chain_csv: tuple         # (header, rows) of the detector's chain.csv
    tolerances: dict         # band -> the rule scenario's tolerance row
    per_bin: list            # the authenticated per-bin table
    model: RadioFisherBAO
    policy: Any
    bands: dict = field(default_factory=dict)


def read_inputs(release: str, characterization: str | Path,
                tolerances: str | Path, project: str | Path) -> Inputs:
    """Read the characterization directory and the rule tolerances."""
    if release not in RELEASES:
        raise ValueError(f"unknown release {release!r}; one of {RELEASES}")
    root = Path(characterization)
    model = RadioFisherBAO(project)
    oc = handoff.read_characterization(
        root, r_reference=model.r_reference,
        residual_shapes=model.residual_shapes)
    declared = (oc.manifest.get("record"),
                oc.manifest["integration_model"].get("variance_split"),
                oc.manifest.get("tie_rule"))
    if declared not in RELEASE_CHOICES[release]:
        raise ValueError(f"{root}: characterized as {declared} (record, "
                         f"variance split, tie rule), not as {release!r}")
    summary, fine, coarse, ladder = {}, {}, {}, {}
    for s in oc.summary:
        summary.setdefault(str(s["band_id"]), []).append(s)
    for r in oc.table:
        band = str(r["band_id"])
        if r["candidate_set"] == "coarse_ladder" and r["block"] == "evaluation":
            ladder.setdefault(band, []).append(r)
        if r["block"] != "calibration":
            continue
        if r["candidate_set"] == interval.FINE:
            fine.setdefault(band, []).append(r)
        elif r["candidate_set"] == "coarse_surface":
            coarse.setdefault(band, []).append(r)
    ledger, names = {}, {}
    for path in sorted((root / "ledger" / "channels").glob("ch*_fid*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        ledger[str(record["channel"])] = record
        names[str(record["channel"])] = path.name
    run = json.loads((root / "ledger" / "run.json").read_text(encoding="utf-8"))
    with (root / "tables" / "chain.csv").open(newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        chain_header = next(reader)
        chain_rows = [row for row in reader]
    tol_path = Path(tolerances)
    tol_path = tol_path / "tolerances.csv" if tol_path.is_dir() else tol_path
    tol_rows = handoff.read_tolerances(tol_path, oc.bands)
    rule = {t["band_id"]: t for t in tol_rows if t["role"] == "rule"}
    per_bin = tolerance_table.load(packaged_table())
    return Inputs(release, root, oc.manifest, summary, fine, coarse, ladder,
                  ledger, names, run, (chain_header, chain_rows), rule,
                  per_bin, model, frozen_policy(), oc.bands)


# ---------------------------------------------------------------- tolerance
def channel_tolerance_row(inp: Inputs, band: str) -> dict:
    """The frozen ``channel_tolerances.csv`` row of one band."""
    edges = inp.bands[band]
    z_low, z_high = redshift_range(float(edges["low_mhz"]),
                                   float(edges["high_mhz"]))
    no_filter = [r for r in inp.per_bin if r["world"] == "none"]
    bins = tuple(sorted({int(r["bin_index"]) for r in no_filter
                         if float(r["z_lo"]) < z_high
                         and float(r["z_hi"]) > z_low}))
    covered_to = z_low
    for lo, hi in sorted({(float(r["z_lo"]), float(r["z_hi"]))
                          for r in no_filter if int(r["bin_index"]) in bins}):
        if lo > covered_to + 1e-10:
            break
        covered_to = max(covered_to, hi)
    coverage_ok = covered_to >= z_high - 1e-10
    values = {p: tolerance_of(no_filter, "none", bins, p) if coverage_ok
              else math.nan for p in PARAMETERS}
    refusal = ("forecast bins do not cover the full channel" if not coverage_ok
               else "one or more target-time parameter tolerances refused"
               if any(not math.isfinite(v) for v in values.values()) else "")
    aperp, apar = values["aperp"], values["apar"]
    dilation = (min(aperp, apar) if all(math.isfinite(v) and v > 0
                                        for v in (aperp, apar)) else math.nan)
    binding = ("refused: both dilation tolerances required at the target time"
               if not math.isfinite(dilation) else
               "aperp" if aperp <= apar else "apar")
    rule = inp.tolerances.get(band)
    if rule is not None and not (
            (math.isnan(dilation) and math.isnan(rule["r_tol"]))
            or dilation == rule["r_tol"]):
        raise NotReproducible(f"band {band}: the rule tolerance "
                              f"{rule['r_tol']!r} is not the dilation "
                              f"tolerance {dilation!r}")
    return {"channel": int(band), "z_low": z_low, "z_high": z_high,
            "r_tol_apar": apar,
            "tolerance_basis": f"{TOLERANCE_SOURCE}; {TARGET_YEARS:g} on-sky "
                               "year; minimum over every overlapping bin",
            "refusal": refusal, "bins": ";".join(str(b) for b in bins),
            "r_tol_dilation": dilation, "r_tol_aperp": aperp,
            "apar_over_aperp_ledger": (apar / aperp if math.isfinite(aperp)
                                       else math.nan),
            "dilation_binding": binding}


def write_channel_tolerances(rows: Sequence[Mapping], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(CHANNEL_TOLERANCE_COLUMNS),
                                lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _repr_cell(row[k]) for k in
                             CHANNEL_TOLERANCE_COLUMNS})
    return path


# ---------------------------------------------------------------- selection
@dataclass
class Priced:
    """One band's science pricing, where the frozen run priced it."""

    band: str
    r_tol: float
    surface: Mapping
    points: list
    selection: interval.Selection
    status: str


def _selection_bands(inp: Inputs) -> list[str]:
    out = []
    for band in sorted(inp.bands, key=int):
        rule = inp.tolerances.get(band)
        record = inp.ledger.get(band)
        surface = (record or {}).get("sections", {}).get("surface")
        if rule is None or not math.isfinite(rule["r_tol"]) or not surface:
            continue
        if not surface.get("calibration_frames") or not math.isfinite(
                _num(surface.get("chain_gain"))):
            continue
        out.append(band)
    return out


def price(inp: Inputs, band: str) -> Priced:
    r_tol = float(inp.tolerances[band]["r_tol"])
    surface = inp.ledger[band]["sections"]["surface"]
    rows = interval.fine_candidates(inp.fine.get(band, []), inp.policy)
    pts = interval.points(rows, r_tol, inp.policy)
    chosen = interval.select(pts, inp.policy)
    if surface["status"] == "refused":
        status = "refused"
    else:
        status = {"no_feasible_threshold": "no feasible point",
                  "no_evaluable_threshold": "no evaluable point"}.get(
            chosen.status, "feasible")
    if status == "feasible":
        raise NotReproducible(
            f"band {band}: a feasible point; its evaluation-block replay is "
            "the detector's (characterize replay), which the handoff does not "
            "carry")
    return Priced(band, r_tol, surface, pts, chosen, status)


def selection_row(inp: Inputs, p: Priced) -> dict:
    s, rec = p.surface, inp.ledger[p.band]
    has_diag = s.get("least_residual_rho") is not None
    diag_r = _num(s.get("least_residual_r_sys"))
    ev_r = _num(s.get("r_sys_evaluation"))
    row = {"channel": int(p.band), "freq_id": rec["freq_id"],
           "era": s["era"], "anchor_bin": s["anchor_bin"],
           "bulk_size": s["bulk_size"], "r_tol": p.r_tol,
           "floor_db": _num(s["floor_db"]),
           "floor_evidence": s["floor_evidence"],
           "floor_population": s["floor_population"],
           "calibration_frames": s["calibration_frames"],
           "evaluation_frames": s["evaluation_frames"],
           "frames_without_time": s["frames_without_time"],
           "status": p.status, "refusal": s["refusal"],
           "claim_status": s["claim_status"], "rho": None, "q_rho": math.nan,
           "eta_q16": None, "eta": math.nan,
           "masked_fraction_calibration": math.nan,
           "r_sys_calibration": math.nan, "R_calibration": math.nan,
           "cost": math.nan, "plateau_members": None,
           "plateau_eta_low": math.nan, "plateau_eta_high": math.nan}
    row.update({
        "diagnostic_basis": DIAGNOSTIC_BASIS if has_diag else "",
        "diagnostic_rho": s.get("least_residual_rho"),
        "diagnostic_eta_q16": s.get("least_residual_eta_q16"),
        "diagnostic_eta": _num(s.get("least_residual_eta")),
        "diagnostic_masked_fraction": _num(s.get(
            "least_residual_masked_fraction")),
        "diagnostic_r_sys": diag_r,
        "diagnostic_R": diag_r / p.r_tol if has_diag else math.nan,
        "diagnostic_cost": _num(s.get(
            "least_residual_exposure_cost_uniform_loss")),
        "anchor_sentinel": s["anchor_sentinel"],
        "stability_status": s["stability_status"],
        "stability_reason": s["stability_reason"],
        "stability_points_checked": s["stability_points_checked"],
        "stability_points_skipped": s["stability_points_skipped"],
        "chain_gain": _num(s["chain_gain"]),
        "residual_convention": s["residual_convention"]})
    row.update({
        "r_sys_unmasked_calibration": _num(s["r_sys_unmasked_calibration"]),
        "masked_fraction_evaluation": _num(s["masked_fraction_evaluation"]),
        "masked_fraction_evaluation_q16": _num(
            s["masked_fraction_evaluation_q16"]),
        "masked_fraction_evaluation_q84": _num(
            s["masked_fraction_evaluation_q84"]),
        "r_sys_evaluation": ev_r,
        "r_sys_evaluation_q16": _num(s["r_sys_evaluation_q16"]),
        "r_sys_evaluation_q84": _num(s["r_sys_evaluation_q84"]),
        "bootstrap_blocks_evaluation": s["bootstrap_blocks_evaluation"],
        "r_sys_unmasked_evaluation": _num(s["r_sys_unmasked_evaluation"]),
        "kept_evaluation": s["kept_evaluation"],
        "R_evaluation": ev_r / p.r_tol if math.isfinite(ev_r) else math.nan,
        "survey_flag_rate_evaluation": _num(s["survey_flag_rate_evaluation"]),
        "false_alarm_rate": _num(s["false_alarm_rate"]),
        "false_alarm_basis": s["false_alarm_basis"]})
    return row


def selection_section(inp: Inputs, p: Priced, row: Mapping) -> dict:
    """The ledger's frozen ``selection`` section of a priced band."""
    s = p.surface
    out = {k: v for k, v in row.items() if k not in ("channel", "freq_id")}
    min_r = _num(s.get("min_r_sys"))
    if math.isfinite(min_r) and not min_r > p.r_tol:
        raise NotReproducible(f"band {p.band}: the surface reaches r_tol; its "
                              "feasible count needs the full surface")
    out.update({
        "surface_points": s["surface_points"], "min_r_sys": min_r,
        "min_r_sys_rho": s.get("min_r_sys_rho"),
        "min_r_sys_eta": _num(s.get("min_r_sys_eta")),
        "min_r_sys_masked_fraction": _num(s.get("min_r_sys_masked_fraction")),
        "min_R": min_r / p.r_tol if math.isfinite(min_r) else math.nan,
        "feasible_points": 0,
        "keep_everything_r_sys_calibration": _num(
            s["keep_everything_r_sys_calibration"]),
        "keep_everything_r_sys_evaluation": _num(
            s["keep_everything_r_sys_evaluation"]),
        "anchor_source": s["anchor_source"], "gain_basis": s["gain_basis"]})
    coarse = _num(s.get("coarse_min_r_sys"))
    flag = _num(s.get("coarse_r_sys_at_flag"))
    out.update({
        "coarse_min_R": coarse / p.r_tol if math.isfinite(coarse) else math.nan,
        "coarse_min_R_eta": _num(s.get("coarse_min_r_sys_eta")),
        "coarse_min_R_masked_fraction": _num(
            s.get("coarse_min_r_sys_masked_fraction")),
        "coarse_R_at_flag": flag / p.r_tol if math.isfinite(flag) else math.nan})
    for k, v in s.items():
        if k.startswith("drift_"):
            out[k] = v
    return out


MAX_POINTS_PER_RHO = 200
TIE_REL_TOL = 1e-9


def _tied(a: float, b: float) -> bool:
    return math.isclose(float(a), float(b), rel_tol=TIE_REL_TOL, abs_tol=0.0)


def _rank_least(indices, rows, release: str):
    """The rank's least-residual index under the release's own rule: the first
    exact minimum (author eras, e041d5e), or residuals within 1e-9 tied and
    broken by masked fraction, then multiplier (no split r2, f72bf34)."""
    finite = [i for i in indices if math.isfinite(rows[i]["r_sys"])]
    if not finite:
        return None
    if release == "archive_author_eras_2026_09_23":
        return min(finite, key=lambda i: rows[i]["r_sys"])
    low = min(rows[i]["r_sys"] for i in finite)
    return min((i for i in finite if _tied(rows[i]["r_sys"], low)),
               key=lambda i: (rows[i]["masked_fraction"], rows[i]["eta_q16"]))


def frozen_thinning(inp: Inputs, band: str, points: Sequence) -> list:
    """The candidates the release's surface file lists.

    The release thinned each rank to at most 200 candidates evenly spaced in
    eta, plus the rank's least-residual candidate and the selected point. The
    handoff thins the same way and also keeps its marked points (the knee).
    Each written row's candidate order counts every evaluable candidate, so its
    index within its rank is known, and a marked row the release did not list
    is left out.
    """
    evaluable = {s["threshold_family"]: int(s["candidates_evaluable"])
                 for s in inp.summary.get(band, [])
                 if s["candidate_set"] == interval.FINE}
    by_rank: dict = {}
    for pt in points:
        by_rank.setdefault(int(pt.row["rho"]), []).append(pt)
    out = []
    for rho in sorted(by_rank):
        members = sorted(by_rank[rho], key=lambda q: int(q.row["eta_q16"]))
        n = evaluable[f"rho={rho}"]
        start = int(members[0].row["candidate_order"])
        index = [int(q.row["candidate_order"]) - start for q in members]
        if n <= MAX_POINTS_PER_RHO:
            spaced = set(range(n))
        else:
            spaced = {int(round(i * (n - 1) / (MAX_POINTS_PER_RHO - 1)))
                      for i in range(MAX_POINTS_PER_RHO)}
        rows = [q.row for q in members]
        least = _rank_least(range(len(rows)), rows, inp.release)
        out += [q for k, q in enumerate(members)
                if index[k] in spaced or k == least]
    return out


def operating_points_rows(inp: Inputs, p: Priced) -> list[dict]:
    """The frozen ``channels/chNN/operating_points.csv`` rows (the listed
    fine candidates, R priced against the band's tolerance)."""
    rows = []
    for pt in frozen_thinning(inp, p.band, p.points):
        r = pt.row
        rows.append({"channel": int(p.band), "rho": int(r["rho"]),
                     "rank_fraction": float(r["rank_fraction"]),
                     "eta_q16": int(r["eta_q16"]), "eta": float(r["eta"]),
                     "frames": int(r["frames"]), "kept": int(r["kept"]),
                     "masked_fraction": float(r["masked_fraction"]),
                     "r_sys": float(r["r_sys"]), "tolerance_fraction": pt.R,
                     "cost": pt.cost, "feasible": pt.feasible,
                     "selected": False})
    return rows


def write_operating_points(rows: Sequence[Mapping], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["channel", *POINT_COLUMNS,
                                                "selected"],
                                lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: (repr(v) if isinstance(v, float) else v)
                             for k, v in row.items()})
    return path


def coarse_frontier_rows(inp: Inputs, p: Priced) -> list[dict]:
    """The frozen ``coarse_frontier.csv`` rows: every grid value of the coarse
    rule, R against the band's tolerance."""
    rows = inp.coarse.get(p.band, [])
    if not rows:
        return []
    if len(rows) != COARSE_GRID_SIZE:
        raise NotReproducible(
            f"band {p.band}: {len(rows)} coarse candidates are written, the "
            f"frozen frontier lists all {COARSE_GRID_SIZE} grid values "
            "(the handoff writes evaluable candidates only)")
    out = []
    for r in rows:
        value = float(r["r_sys"])
        out.append({"channel": int(p.band), "eta_c": float(r["eta"]),
                    "frames": int(r["frames"]), "kept": int(r["kept"]),
                    "masked_fraction": float(r["masked_fraction"]),
                    "r_sys": value,
                    "R": value / p.r_tol if (math.isfinite(value)
                                             and p.r_tol > 0) else math.nan,
                    "evaluable": int(r["kept"]) >= MIN_KEPT})
    return out


def write_operating_point(knee: Mapping, band: str, path: Path) -> Path:
    """The releases' per-band ``operating_point.csv`` (the knee report)."""
    row = {"channel": int(band), **knee}
    keys = list(OPERATING_COLUMNS) + [k for k in row
                                      if k not in OPERATING_COLUMNS]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=keys, lineterminator="\n")
        writer.writeheader()
        writer.writerow({k: (repr(v) if isinstance(v, float) else
                             ("" if v is None else v))
                         for k, v in ((k, row.get(k, "")) for k in keys)})
    return path


# ---------------------------------------------------------------- screening
# The screening rule of the releases (rfisher_results/archive/screening.py at
# 7b0067b), verbatim: its classes, thresholds and reason texts are the
# frozen screening.csv.
OCCUPANCY_WALL_MASKED_FRACTION = 0.95
OCCUPANCY_WALL_FLAG_RATE = 0.90
RECOVERY = "recovery candidate"
BOUND_FLOOR = "measurement-bound on floor"
BOUND_TAU = "measurement-bound on tau_c"
WALL = "occupancy-wall excision candidate"
OFF_ERA = "off-era"
CLASSES = (RECOVERY, BOUND_FLOOR, BOUND_TAU, WALL, OFF_ERA)


@dataclass(frozen=True)
class ScreeningInputs:
    off_era: bool
    selection_status: str
    tolerance_fraction: float
    masked_fraction: float
    survey_flag_rate: float
    floor_evidence: str
    correlation_quality: str
    refusal: str = ""
    claim_status: str = "screening"
    era_state: str = ""
    era_level_db: float = float("nan")
    anchor_sentinel: str = ""
    stability_status: str = ""


@dataclass(frozen=True)
class Screening:
    screening_class: str
    closing_condition: str
    reasons: tuple[str, ...]
    thresholds: dict

    def as_row(self) -> dict:
        return {"screening_class": self.screening_class,
                "closing_condition": self.closing_condition,
                "screening_reasons": "; ".join(self.reasons)}


def screen(inputs: ScreeningInputs, *,
           wall_masked_fraction: float = OCCUPANCY_WALL_MASKED_FRACTION,
           wall_flag_rate: float = OCCUPANCY_WALL_FLAG_RATE) -> Screening:
    thresholds = {"occupancy_wall_masked_fraction": wall_masked_fraction, "occupancy_wall_flag_rate": wall_flag_rate}
    reasons: list[str] = []
    feasible = inputs.selection_status == "feasible" and inputs.tolerance_fraction <= 1.0
    floor_ok = inputs.floor_evidence == "measured"
    tau_ok = inputs.correlation_quality in ("measured", "bounded_above")

    def selection_clauses() -> list[str]:
        out = [f"selection: {inputs.selection_status}" + (" on the calibration surface" if inputs.selection_status != "feasible" else "")]
        if inputs.stability_status or inputs.refusal:
            out.append(f"drift screen: {inputs.stability_status or 'refused'}" + (f" ({inputs.refusal})" if inputs.refusal else ""))
        if inputs.claim_status:
            out.append(f"claim status {inputs.claim_status}")
        if inputs.anchor_sentinel:
            out.append(f"anchor sentinel: {inputs.anchor_sentinel}")
        return out

    if inputs.off_era:
        reasons.append("current era is a transmitter-off era; values are floors, not verdicts")
        reasons.extend(selection_clauses())
        return Screening(OFF_ERA, "era transition: the next sign-on", tuple(reasons), thresholds)

    at_wall = (inputs.survey_flag_rate >= wall_flag_rate) or (feasible and inputs.masked_fraction >= wall_masked_fraction)
    if at_wall and not (feasible and inputs.masked_fraction < wall_masked_fraction):
        if inputs.survey_flag_rate >= wall_flag_rate:
            reasons.append(f"survey flag rate {inputs.survey_flag_rate:.3f} >= {wall_flag_rate}: transmitter present in nearly every frame")
            if inputs.era_state and inputs.era_state != "proxy-high":
                level = f" (median level {inputs.era_level_db:.2f} dB)" if math.isfinite(inputs.era_level_db) else ""
                reasons.append(f"era state {inputs.era_state}{level}: a weak carrier present in nearly every frame")
        if feasible and inputs.masked_fraction >= wall_masked_fraction:
            reasons.append(f"selected point masks {inputs.masked_fraction:.3f} of frames: formally feasible, vacuous")
        reasons.extend(selection_clauses())
        return Screening(WALL, "none: excision, with the pilot bin kept as a monitoring tap", tuple(reasons), thresholds)

    if feasible:
        reasons.append(f"selected point inside tolerance on the dilation tier (R = {inputs.tolerance_fraction:.3g})")
        reasons.extend(selection_clauses()[1:])
        if floor_ok and tau_ok:
            reasons.append(f"floor measured; correlation time {inputs.correlation_quality}")
            return Screening(RECOVERY, "transfer gate: the online exact-replay agreement", tuple(reasons), thresholds)
        if not floor_ok:
            reasons.append(f"floor is {inputs.floor_evidence}: no verified off era")
            return Screening(BOUND_FLOOR, "measured floor from a verified off state", tuple(reasons), thresholds)
        reasons.append(f"correlation time {inputs.correlation_quality}: chain booked at the sidereal-day cap")
        return Screening(BOUND_TAU, "measured correlation time", tuple(reasons), thresholds)

    reasons.extend(selection_clauses())
    if not floor_ok:
        reasons.append(f"floor is {inputs.floor_evidence}")
        return Screening(BOUND_FLOOR, "measured floor from a verified off state", tuple(reasons), thresholds)
    if not tau_ok:
        reasons.append(f"correlation time {inputs.correlation_quality}")
        return Screening(BOUND_TAU, "measured correlation time", tuple(reasons), thresholds)
    reasons.append("floor and correlation time measured; no admissible point at this tolerance")
    return Screening(WALL, "none: no admissible operating point", tuple(reasons), thresholds)


def anchor_note(containment: Mapping | None) -> str:
    """The containment sentinel's reasons (the releases' run.py wording)."""
    if not containment:
        return ""
    reasons = []
    if containment.get("anchor_folds_out_of_span"):
        reasons.append("fine anchor aliases the out-of-span feature at "
                       f"{containment['out_of_span_offset_hz']:.0f} Hz by one "
                       "coarse bin")
    if containment.get("anchor_lobe_disagree"):
        reasons.append(f"fine anchor {containment['anchor_lobe_offset_bins']:+.1f}"
                       " bins from the PSD in-span lobe")
    return "; ".join(reasons)


def _off_dates(events: Mapping) -> tuple[str, str]:
    """``(off_through, off_from)`` from the archive-inferred events."""
    off_from = next((m for m, e in events.items() if e == "sign-off"), "")
    on = next((m for m, e in events.items() if e == "sign-on"), "")
    off_through = ""
    if on:
        y, m = (int(x) for x in on.split("-"))
        index = y * 12 + m - 1 - 1
        off_through = f"{index // 12:04d}-{index % 12 + 1:02d}"
    return off_through, off_from


def screening_for(inp: Inputs, band: str, priced: Priced | None
                  ) -> tuple[Screening, dict]:
    sections = inp.ledger[band]["sections"]
    era, chain = sections["era"], sections.get("chain")
    occupancy = sections["occupancy"]
    note = anchor_note(sections.get("containment"))
    surface = sections.get("surface") or {}
    if surface and priced is not None and surface.get("anchor_sentinel") != note:
        raise NotReproducible(f"band {band}: the anchor sentinel differs from "
                              "the containment record")
    flag_rate = _num(occupancy["survey_flag_rate_era"])
    tau_quality = chain["tau_quality"] if chain else "unmeasured"
    floor_evidence = (surface.get("floor_evidence") if surface else None) or \
        next(s["floor_evidence"] for s in inp.summary[band])
    inputs = ScreeningInputs(
        off_era=bool(era["off_era_current"]),
        selection_status=priced.status if priced else "refused",
        tolerance_fraction=math.nan, masked_fraction=math.nan,
        survey_flag_rate=flag_rate, floor_evidence=floor_evidence,
        correlation_quality=tau_quality,
        refusal=(surface.get("refusal") if priced else "no selection"),
        claim_status=(surface.get("claim_status") if priced else ""),
        era_state=era.get("current_state") or "",
        era_level_db=_num(era.get("current_level_median_db")),
        anchor_sentinel=note,
        stability_status=(surface.get("stability_status") if priced else ""))
    result = screen(inputs)
    off_through, off_from = _off_dates(
        sections["archive_inferred_events"]["events"])
    ev_r = _num(surface.get("r_sys_evaluation")) if priced else math.nan
    has_eval = priced is not None and surface.get("least_residual_rho") is not None
    extra = {"survey_flag_rate_era": flag_rate,
             "off_era_current": bool(era["off_era_current"]),
             "off_through": off_through, "off_from": off_from,
             "evaluation_masked_fraction_at_diagnostic":
                 _num(surface.get("masked_fraction_evaluation"))
                 if has_eval else math.nan,
             "evaluation_R_at_diagnostic":
                 ev_r / priced.r_tol if (has_eval and math.isfinite(ev_r))
                 else math.nan}
    return result, extra


# ---------------------------------------------------------------- ledger
def _drop(section: Mapping | None, keys: Sequence[str]) -> Mapping | None:
    if section is None:
        return None
    return {k: v for k, v in section.items() if k not in keys}


def _chain_section(section: Mapping | None, delay_key: str,
                   delay_db: float) -> Mapping | None:
    if section is None:
        return None
    return {**section, "delay_key": delay_key, "delay_suppression_db": delay_db}


def _null_section(section: Mapping, priced: bool) -> Mapping:
    out = dict(section)
    basis = out.get("exchangeability_rank_basis", "")
    if not priced:
        for k in EXCHANGE_KEYS:
            out.pop(k, None)
        notes = str(out.get("notes") or "")
        if EXCH_SKIPPED in notes:
            out["notes"] = notes.split(EXCH_SKIPPED)[0]
        out["exchangeability_rank_basis"] = ""
    elif basis:
        out["exchangeability_rank_basis"] = "diagnostic point"
    return out


def _notes(record: Mapping, priced: bool) -> list[str]:
    notes = list(record["notes"])
    if priced:
        return notes
    return [n for n in notes if not n.startswith(DRIFT_NOTE)] + [SKIPPED_NOTE]


def _delay(inp: Inputs) -> tuple[str, float]:
    """The chain's delay key and its suppression: the frozen policy's key,
    which must be the no-filter one (no credit is taken)."""
    key = str(inp.policy.value("transfer.delay_suppression.default_key"))
    if key not in NO_DELAY_FILTER:
        raise NotReproducible(f"the frozen policy's delay key {key!r} takes a "
                              "filter credit; post-processing is not modelled")
    return key, NO_DELAY_FILTER[key]


def ledger_record(inp: Inputs, band: str, priced: Priced | None,
                  sections_science: Mapping) -> dict:
    """The frozen channel record of one band."""
    record = inp.ledger[band]
    det = record["sections"]
    delay_key, delay_db = _delay(inp)
    flaggers = det.get("flaggers")
    if flaggers is not None and priced is not None and \
            flaggers.get("diagnostic_basis"):
        flaggers = {**flaggers, "diagnostic_basis": DIAGNOSTIC_BASIS}
    built = {
        "geometry": _drop(det["geometry"], DETECTOR_ADDITIONS["geometry"]),
        "product": det["product"],
        "archive_inferred_events": _drop(
            det["archive_inferred_events"],
            DETECTOR_ADDITIONS["archive_inferred_events"]),
        "era": _drop(det["era"], DETECTOR_ADDITIONS["era"]),
        "evaluation_contract": det["evaluation_contract"],
        "blocks": det["blocks"], "anchor": det["anchor"],
        "anchor_calibration": det["anchor_calibration"],
        "anchor_evaluation": det["anchor_evaluation"],
        "anchor_era": det["anchor_era"],
        "anchor_previous": det["anchor_previous"],
        "containment": det["containment"],
        "chain": _chain_section(det["chain"], delay_key, delay_db),
        "chain_archive": _chain_section(det["chain_archive"], delay_key,
                                        delay_db),
        "tolerance": sections_science["tolerance"],
        "null": _null_section(det["null"], priced is not None),
        "null_evaluation": det["null_evaluation"],
        "selection": sections_science["selection"],
        "operating": sections_science["operating"],
        "held_out": det["held_out"], "flaggers": flaggers,
        "screening": sections_science["screening"],
    }
    return {"channel": record["channel"], "freq_id": record["freq_id"],
            "product": record["product"],
            "product_sha256": record["product_sha256"],
            "sections": {k: built[k] for k in SECTION_ORDER},
            "notes": _notes(record, priced is not None)}


def _flat(record: Mapping) -> dict:
    out = {"channel": record["channel"], "freq_id": record["freq_id"],
           "product": record["product"],
           "product_sha256": record["product_sha256"]}
    for prefix, row in record["sections"].items():
        if row is None:
            out[f"{prefix}_present"] = False
            continue
        for k, v in row.items():
            out[f"{prefix}_{k}"] = v
    out["notes"] = "; ".join(record["notes"])
    return out


def write_ledger(records: Sequence[Mapping], run: Mapping, directory: Path
                 ) -> dict:
    """The releases' ledger writer: one JSON per band, run.json, ledger.csv."""
    (directory / "channels").mkdir(parents=True, exist_ok=True)
    records = sorted(records, key=lambda r: r["channel"])
    for rec in records:
        path = directory / "channels" / f"ch{rec['channel']:02d}_fid{rec['freq_id']}.json"
        path.write_text(json.dumps(_jsonable(rec), indent=1) + "\n",
                        encoding="utf-8")
    run_doc = {"schema": LEDGER_SCHEMA, **_jsonable(run),
               "channels": [f"channels/ch{r['channel']:02d}_fid{r['freq_id']}.json"
                            for r in records]}
    (directory / "run.json").write_text(json.dumps(run_doc, indent=1) + "\n",
                                        encoding="utf-8")
    rows = [_flat(_jsonable(r)) for r in records]
    keys: list[str] = []
    for row in rows:
        for k in row:
            if k not in keys:
                keys.append(k)
    with (directory / "ledger.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=keys, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: ("" if row.get(k) is None else
                                 repr(row[k]) if isinstance(row[k], float)
                                 else row.get(k, "")) for k in keys})
    return {"records": len(records)}


def run_record(inp: Inputs, started: str | None = None) -> dict:
    """The frozen ``run.json`` fields, from the detector's run and this one."""
    det = inp.run
    identity = producer_identity(
        {"characterization/manifest.json": handoff.sha256_file(
            inp.characterization / "manifest.json")}, inp.policy.sha256())
    detector = det.get("producer") or {}
    producer = {
        "repository": PRODUCER_REPOSITORY, "commit": identity["commit"],
        "dirty": identity["dirty"], "dirty_files": identity["dirty_files"],
        "module": PRODUCER_MODULE, "source_digest": source_digest(),
        "source_roots": {"RFIsher/src": str(Path(__file__).resolve().parents[3]),
                         "pilot_proxy": str(detector.get("source_root", ""))},
        "policy_sha256": inp.policy.sha256(), "commit_at_end": identity["commit"],
        "source_changed_during_run": False}
    provisional = {}
    for k, v in (det.get("provisional") or {}).items():
        provisional[k] = v
        if k == "stability.maximum_systematic_residual_ratio":
            provisional["occupancy_wall_masked_fraction"] = \
                OCCUPANCY_WALL_MASKED_FRACTION
    return {
        "generated": started or det.get("generated"),
        "producer": producer,
        "products_dir": det.get("products_dir"),
        "products": det.get("products"),
        "channels": det.get("channels"),
        "campaign_last_month": det.get("campaign_last_month"),
        "era_config": det.get("era_config"),
        "era_config_digest": det.get("era_config_digest"),
        "era_overrides": det.get("era_overrides"),
        "era_overrides_sha256": det.get("era_overrides_sha256"),
        "bootstrap": det.get("bootstrap"),
        "provisional": provisional,
        "errors": det.get("errors"),
        "seconds": det.get("seconds"),
    }


# ---------------------------------------------------------------- the layout
def write_archive_layout(release: str, characterization: str | Path,
                         tolerances: str | Path, project: str | Path,
                         out: str | Path) -> dict:
    """Write the frozen archive layout of ``release`` into ``out``.

    ``characterization`` is the detector's characterization directory (with
    its ``tables/``, ``channels/`` and ``ledger/``), ``tolerances`` the band
    tolerance table of the archive (``rfisher tolerance bands``).
    """
    inp = read_inputs(release, characterization, tolerances, project)
    out = Path(out)
    tables, channels = out / "tables", out / "channels"
    priced = {b: price(inp, b) for b in _selection_bands(inp)}
    tol_rows = {b: channel_tolerance_row(inp, b)
                for b in sorted(inp.bands, key=int)}
    write_channel_tolerances(list(tol_rows.values()),
                             tables / "channel_tolerances.csv")
    selection_rows, screening_rows, operating_rows = [], [], []
    records = []
    for band in sorted(inp.bands, key=int):
        p = priced.get(band)
        sel_row = selection_row(inp, p) if p else None
        ch_dir = channels / f"ch{int(band):02d}"
        science = {"tolerance": {k: v for k, v in tol_rows[band].items()
                                 if k != "channel"},
                   "selection": None, "operating": None}
        if p is not None:
            selection_rows.append(sel_row)
            write_operating_points(operating_points_rows(inp, p),
                                   ch_dir / "operating_points.csv")
            frontier = coarse_frontier_rows(inp, p)
            _write_csv(frontier, ch_dir / "coarse_frontier.csv")
            science["selection"] = selection_section(inp, p, sel_row)
            knee = inp.ledger[band]["sections"].get("knee")
            if knee is not None and p.points:
                write_operating_point(knee, band, ch_dir / "operating_point.csv")
                operating_rows.append({"channel": int(band), **knee})
                science["operating"] = knee
        result, extra = screening_for(inp, band, p)
        screening_rows.append({"channel": int(band), **result.as_row()})
        science["screening"] = {**result.as_row(), **extra}
        records.append(ledger_record(inp, band, p, science))
    _write_csv(selection_rows, tables / "selection.csv")
    _write_chain(inp, tables / "chain.csv")
    _write_csv(screening_rows, tables / "screening.csv")
    _write_csv(operating_rows, tables / "operating_points.csv")
    write_ledger(records, run_record(inp), out / "ledger")
    rungs = []
    for band in sorted(inp.bands, key=int):
        summary = next((s for s in inp.summary.get(band, [])
                        if s["candidate_set"] == "coarse_ladder"), None)
        if summary is not None:
            rungs += ladder_pricing.ladder_rows(band, inp.ladder.get(band, []),
                                                summary, tol_rows[band])
    ladder_pricing.write_ladder_pricing(rungs, out / "coarse" /
                                        "ladder_pricing.csv")
    return {"priced": sorted(priced, key=int), "bands": len(inp.bands)}


def _write_chain(inp: Inputs, path: Path) -> Path:
    """The detector's chain.csv with the delay key and its suppression put
    back (the rule scenario's), cells copied as the detector wrote them."""
    delay_key, delay_db = _delay(inp)
    header, rows = inp.chain_csv
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(list(header) + ["delay_key", "delay_suppression_db"])
    for row in rows:
        writer.writerow(list(row) + [delay_key, repr(float(delay_db))])
    path.write_text(buf.getvalue(), encoding="utf-8")
    return path
