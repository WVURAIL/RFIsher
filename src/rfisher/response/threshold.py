"""Saved threshold -> residual proxy and uniform exposure response.

This reads complete supported calibration curves. It neither interpolates
thresholds nor selects a science policy. Residuals retain the producer's
floor and coherence assumptions; they are not physical bounds.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from ..provenance import producer_identity
from ..verdict import handoff
from .evidence import CONDITIONAL_SCREENING_EVIDENCE

MODEL_KEYS = ("r_reference", "residual_shape", "integration_model", "statistics",
              "mask_rule")
EVIDENCE = CONDITIONAL_SCREENING_EVIDENCE
RESPONSE_COLUMNS = (
    "source_id", "band_id", "band_low_mhz", "band_high_mhz", "band_role",
    "era_label", "era_start", "era_end", "era_state", "candidate_set",
    "population", "block", "threshold_family", "candidate_order", "statistic",
    "rho", "bulk_size", "rank_fraction", "eta_q16", "eta_exact", "eta",
    "frames", "kept", "masked", "kept_fraction", "masked_fraction",
    "exposure_cost_uniform_loss", "clean_years", "T_required_uniform_years",
    "r_sys", "r_var", "r_sys_incoherent", "r_unmasked", "floor_share",
    "residual_status", "source_claim_status", "source_refusal",
    "evidence_kind", "physical_response_qualified", "science_selection_eligible",
    "residual_contains_sensitivity_floor",
)
STATUS_COLUMNS = (
    "source_id", "band_id", "band_low_mhz", "band_high_mhz", "band_role",
    "complete_calibration_grid", "available_families", "supported_candidates",
    "exported_candidates", "status", "source_claim_status", "source_refusal",
)


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


@dataclass(frozen=True)
class ForwardResponse:
    """Checked source handoffs. Evaluation rows remain provenance only."""

    sources: tuple[handoff.Characterization, ...]

    @property
    def bands(self) -> dict[str, dict]:
        return {band: meta for source in self.sources
                for band, meta in source.bands.items()}


def read_forward(directories: Sequence[str | Path]) -> ForwardResponse:
    """Read compatible handoffs, including controls and empty/refused bands."""
    if not directories:
        raise handoff.HandoffError("at least one characterization is required")
    sources = tuple(handoff.read_characterization(path) for path in directories)
    model = {key: sources[0].manifest[key] for key in MODEL_KEYS}
    seen = set()
    for source in sources:
        for key, expected in model.items():
            if source.manifest[key] != expected:
                raise handoff.HandoffError(f"incompatible {key}: {source.root}")
        overlap = seen.intersection(source.bands)
        if overlap:
            raise handoff.HandoffError(f"duplicate bands across handoffs: {sorted(overlap)}")
        seen.update(source.bands)
    return ForwardResponse(sources)


def _clean_years(value: float) -> float:
    if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
        raise ValueError("clean_years must be positive and finite")
    return float(value)


def _summary(source, band: str, family: str) -> dict:
    return next(row for row in source.summary
                if row["band_id"] == band and row["candidate_set"] == "fine_surface"
                and row["threshold_family"] == family)


def sweep(response: ForwardResponse, *, band: str | None = None,
          family: str | None = None, clean_years: float = 1.0) -> list[dict]:
    """Return supported saved calibration rows without choosing a threshold."""
    years = _clean_years(clean_years)
    if band is not None and band not in response.bands:
        raise handoff.HandoffError(f"unknown band: {band}")
    rows = []
    for index, source in enumerate(response.sources):
        if not source.complete_calibration_grid:
            continue
        for saved in source.table:
            if (saved["candidate_set"] != "fine_surface" or
                    saved["block"] != "calibration" or
                    (band is not None and saved["band_id"] != band) or
                    (family is not None and saved["threshold_family"] != family)):
                continue
            summary = _summary(source, saved["band_id"], saved["threshold_family"])
            cost = saved["frames"] / saved["kept"]
            rows.append({**saved, "source_id": index,
                         "band_role": source.bands[saved["band_id"]].get("role", ""),
                         "kept_fraction": saved["kept"] / saved["frames"],
                         "clean_years": years, "T_required_uniform_years": years * cost,
                         "residual_status": "diagnostic proxy; not a physical bound",
                         **EVIDENCE,
                         "source_claim_status": summary["claim_status"],
                         "source_refusal": summary["refusal"]})
    return rows


def query(response: ForwardResponse, *, band: str, family: str, eta_q16: int,
          clean_years: float = 1.0) -> dict:
    """Look up one exact stored Q16 word; unstored words are refused."""
    if type(eta_q16) is not int or not 0 < eta_q16 < 2**64:
        raise ValueError("eta_q16 must be a positive unsigned 64-bit integer")
    rows = sweep(response, band=band, family=family, clean_years=clean_years)
    for row in rows:
        if row["eta_q16"] == eta_q16:
            return row
    raise handoff.HandoffError(
        f"no supported calibration candidate for band {band}, {family}, "
        f"eta_q16={eta_q16}; no snapping or interpolation is performed")


def _statuses(response: ForwardResponse, rows: list[dict]) -> list[dict]:
    statuses = []
    for index, source in enumerate(response.sources):
        for band, meta in source.bands.items():
            summaries = [row for row in source.summary if row["band_id"] == band
                         and row["candidate_set"] == "fine_surface"]
            families = (source.manifest["fine_surface_counts"][band]
                        if source.complete_calibration_grid else {})
            count = sum(families.values())
            exported = sum(row["band_id"] == band for row in rows)
            status = ("incomplete calibration surface" if not source.complete_calibration_grid
                      else "no supported calibration candidates" if not count
                      else "excluded by requested filters" if not exported
                      else "diagnostic proxy curve")
            statuses.append({"source_id": index, "band_id": band,
                             "band_low_mhz": meta["low_mhz"],
                             "band_high_mhz": meta["high_mhz"],
                             "band_role": meta.get("role", ""),
                             "complete_calibration_grid": source.complete_calibration_grid,
                             "available_families": ";".join(families),
                             "supported_candidates": count,
                             "exported_candidates": exported, "status": status,
                             "source_claim_status": ";".join(sorted({s["claim_status"]
                                                                      for s in summaries})),
                             "source_refusal": ";".join(sorted({s["refusal"]
                                                                 for s in summaries if s["refusal"]}))})
    return statuses


def _json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def write_forward(response: ForwardResponse, out: str | Path, *,
                  band: str | None = None, family: str | None = None,
                  eta_q16: Sequence[int] | None = None,
                  clean_years: float = 1.0) -> dict:
    """Write response.csv, bandstatus.csv and provenance into a new directory."""
    out = Path(out)
    if out.exists():
        raise ValueError(f"output directory exists: {out}")
    if eta_q16 is not None:
        if band is None or family is None:
            raise ValueError("exact eta_q16 queries require band and family")
        if len(set(eta_q16)) != len(eta_q16) or not eta_q16:
            raise ValueError("eta_q16 queries must be nonempty and unique")
        rows = [query(response, band=band, family=family, eta_q16=eta,
                      clean_years=clean_years) for eta in eta_q16]
    else:
        rows = sweep(response, band=band, family=family, clean_years=clean_years)
    statuses = _statuses(response, rows)
    read = {}
    for index, source in enumerate(response.sources):
        for name, digest in source.sha256.items():
            if handoff.sha256_file(source.root / name) != digest:
                raise handoff.HandoffError(f"source changed since read: {source.root / name}")
            read[f"source_{index}/{name}"] = digest
    out.mkdir(parents=True, exist_ok=False)
    files = {}
    for name, records, columns in (("response.csv", rows, RESPONSE_COLUMNS),
                                   ("bandstatus.csv", statuses, STATUS_COLUMNS)):
        (out / name).write_bytes(render(records, columns))
        files[name] = handoff.sha256_file(out / name)
    manifest = {
        "schema": "rfisher_threshold_response_v1", "files": files, "read": read,
        "row_count": len(rows), "band_count": len(statuses),
        "clean_years": _clean_years(clean_years),
        "filters": {"band": band, "family": family,
                    "eta_q16": list(eta_q16) if eta_q16 is not None else None},
        "residual_status": "diagnostic proxy; not a physical bound",
        **EVIDENCE,
        "residual_interpretation": "r_sys combines a sensitivity floor and "
                                   "source coherence assumptions; it is not a "
                                   "measured interference point estimate. A "
                                   "proxy exceeding tolerance does not establish "
                                   "physical infeasibility or justify reject-all.",
        "time_model": "T_required_uniform_years = clean_years * frames / kept; "
                      "uniformly distributed loss only, without a science-cost adjustment",
        "selection": "none; tolerance and threshold optimization are outside this export",
        "sources": [{"source_id": index, "path": str(source.root.resolve()),
                     "sha256": dict(source.sha256), "manifest": dict(source.manifest),
                     "summaries": source.summary,
                     "complete_calibration_grid": source.complete_calibration_grid}
                    for index, source in enumerate(response.sources)],
        "producer": producer_identity(read),
    }
    (out / "manifest.json").write_text(
        json.dumps(_json_safe(manifest), indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8")
    return {"rows": rows, "bands": statuses, "manifest": manifest}


def main(argv=None, prog: str = "rfisher response threshold") -> int:
    parser = argparse.ArgumentParser(prog=prog, description=__doc__)
    parser.add_argument("--characterization", type=Path, action="append", required=True,
                        help="complete handoff; repeat for science and control bands")
    parser.add_argument("--out", type=Path, required=True, help="new output directory")
    parser.add_argument("--band", help="optional exact band ID")
    parser.add_argument("--family", help="optional threshold family, e.g. rho=63")
    parser.add_argument("--eta-q16", type=int, action="append",
                        help="exact saved word; repeat; requires --band and --family")
    parser.add_argument("--clean-years", type=float, default=1.0,
                        help="clean integration target in years (default: 1)")
    args = parser.parse_args(argv)
    try:
        result = write_forward(read_forward(args.characterization), args.out,
                               band=args.band, family=args.family, eta_q16=args.eta_q16,
                               clean_years=args.clean_years)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(f"wrote {args.out}: {len(result['rows'])} calibration candidates, "
          f"{len(result['bands'])} bands")
    return 0
