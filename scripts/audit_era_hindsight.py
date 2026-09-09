#!/usr/bin/env python3
"""Replay frozen monthly era inputs with successively later cutoffs."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

from rfisher_results.validation.eras import audit_era_document


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    source = args.results_dir.resolve()
    out = args.out.resolve()
    if out == source or source in out.parents:
        raise ValueError("write a separate result directory; never alter the source release")
    paths = sorted((source / "channels").glob("ch*/eras.json"))
    if not paths:
        raise ValueError("source has no channels/ch*/eras.json")
    if out.exists() and any(out.iterdir()):
        raise ValueError("output must be empty; audit releases are never overwritten")
    out.mkdir(parents=True, exist_ok=True)
    results = []
    inputs = {}
    for path in paths:
        doc = json.loads(path.read_text())
        results.append(audit_era_document(doc))
        inputs[str(path)] = {"sha256": sha256(path), "bytes": path.stat().st_size}
    results.sort(key=lambda r: r["channel"])
    if len({r["channel"] for r in results}) != len(results):
        raise ValueError("duplicate physical channel in source documents")
    aggregate = {
        "channels": len(results), "prefixes": sum(r["months"] for r in results),
        "populated_channel_months": sum(r["populated_months"] for r in results),
        "assignment_revision_events": sum(r["revision_events"] for r in results),
        "channels_with_revisions_older_than_two_populated_months": [
            r["channel"] for r in results if r["revisions_older_than_two_populated_months"]],
        "max_revision_age_months": max(r["max_revision_age_months"] for r in results),
        "max_final_boundary_stable_lag_months": max(r["max_final_boundary_stable_lag_months"] for r in results),
        "all_final_segmentations_reproduced": all(r["source_segmentation_reproduced"] for r in results),
    }
    report = {
        "schema": "era-prefix-audit-v1", "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "retrospective prefix sensitivity audit", "scientific_certification": False,
        "source_release": str(source), "inputs": inputs, "aggregate": aggregate,
        "method": [
            "Each prefix uses only the recorded months at or before its cutoff and the source digested EraConfig.",
            "Compare each existing month by state, era start and opening evidence; ordinary era-end extension is not a revision.",
            "Month-local features use weight-normalized coarse ratios, nominal-window fine peaks and recorded input maps; no fitted archive anchor is an input.",
            "The archived rule, data and policy were developed retrospectively. Prefixing does not make this an untouched validation.",
            "Source JSON omits software-tag identities; they are not used by segment(). Input-map identities are preserved.",
            "Reported final-boundary lags use the complete series to identify which boundaries eventually survive.",
            "No monthly aggregate timestamps or raw frame products are independently re-derived by this audit.",
            "No independent station-state record is supplied and no operating-policy gate is changed.",
        ],
        "channels": results,
    }
    (out / "era-prefix-audit.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    fields = ["channel", "months", "populated_months", "final_eras", "revision_events", "distinct_revised_months",
              "max_revision_age_months", "revisions_older_than_two_populated_months", "final_boundaries",
              "max_final_boundary_stable_lag_months", "source_segmentation_reproduced"]
    with (out / "era-prefix-summary.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)
    repo = Path(__file__).resolve().parents[1]
    code = [Path(__file__).resolve(), repo / "src/rfisher_results/validation/eras.py",
            repo / "src/rfisher_results/archive/eras.py", repo / "src/rfisher_results/archive/blocks.py",
            repo / "src/rfisher_results/archive/products.py", repo / "tests/test_validation_eras.py"]
    sources = {}
    for path in code:
        relative = path.relative_to(repo)
        target = out / "source-snapshot" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        sources[str(path)] = {"sha256": sha256(path), "snapshot": str(target.relative_to(out))}
    manifest = {"schema": "era-prefix-audit-manifest-v1", "inputs": inputs, "sources": sources,
                "files": {str(path.relative_to(out)): sha256(path) for path in sorted(out.rglob("*")) if path.is_file()}}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(aggregate, indent=2))


if __name__ == "__main__":
    main()
