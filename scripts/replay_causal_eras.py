#!/usr/bin/env python3
"""Demonstrate offline causal-era versions on frozen historical monthly records.

Availability is explicitly assumed to be the next UTC month's start; this is
not reconstructed ingestion history or prospective validation. No acquisition
is invented or evaluated. The candidate calibration digest binds an unqualified
fixture specification, never an accepted physical calibration.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import platform
import shutil

import numpy
import scipy

from rfisher_results.validation.causal_eras import append_monitor, freeze_candidate, month_evidence, verify_ledger
from rfisher_results.validation.eras import monthly_records_from_document


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def month_start(month):
    year, offset = divmod(month, 12)
    return datetime(year, offset + 1, 1, tzinfo=timezone.utc)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--cutoff-month", required=True)
    args = parser.parse_args()
    year, month = map(int, args.cutoff_month.split("-"))
    if args.cutoff_month != f"{year:04}-{month:02}" or not 1 <= month <= 12:
        parser.error("cutoff month must be YYYY-MM")
    cutoff = year * 12 + month - 1
    close = month_start(cutoff + 1)
    source, out = args.results_dir.resolve(), args.out.resolve()
    if source == out or source in out.parents:
        parser.error("output must be separate from the source release")
    if out.exists() and any(out.iterdir()):
        parser.error("output must be empty; previous evidence is never overwritten")
    paths = sorted((source / "channels").glob("ch*/eras.json"))
    if not paths:
        parser.error("source must contain channels/ch*/eras.json")
    repo = Path(__file__).resolve().parents[1]
    producing = [Path(__file__).resolve(), repo / "src/rfisher_results/validation/causal_eras.py",
                 repo / "src/rfisher_results/validation/eras.py", repo / "src/rfisher_results/archive/eras.py",
                 repo / "src/rfisher_results/archive/blocks.py", repo / "src/rfisher_results/archive/products.py"]
    sources = {str(p): sha(p) for p in producing}
    inputs = {str(p): sha(p) for p in paths}
    out.mkdir(parents=True, exist_ok=True)
    plan = {
        "schema": "offline-causal-era-replay-plan-v1", "created_utc": datetime.now(timezone.utc).isoformat(),
        "cutoff_month": args.cutoff_month, "source_release": str(source), "inputs": inputs, "sources": sources,
        "availability_assumption": "Each recorded aggregate is available at the following UTC month's start; monitoring follows one minute later.",
        "candidate_calibration_status": "Unqualified offline fixture specification only; no fitted physical residual calibration or accepted policy.",
        "scope": "retrospective workflow demonstration on recorded month-local features; no raw aggregates, availability times or acquisition evaluations reconstructed",
        "runtime": {"python": platform.python_version(), "numpy": numpy.__version__, "scipy": scipy.__version__},
    }
    write_new(out / "plan.json", plan)
    calibration_digest = sha(out / "plan.json")
    summaries = []
    for path in paths:
        document = json.loads(path.read_text())
        config, records = monthly_records_from_document(document)
        evidence = [month_evidence(r, available_at=month_start(r.month + 1), source_sha256=inputs[str(path)],
                                   availability_basis="assumed_retrospective") for r in records]
        prefix = [e for e in evidence if e["record"]["month"] <= cutoff]
        if not prefix:
            summaries.append({"channel": document["channel"], "status": "no development months before fixed cutoff"})
            continue
        frozen = freeze_candidate(prefix, config, version_id=f"ch{document['channel']}-candidate-{args.cutoff_month}",
                                  cutoff_month=args.cutoff_month, frozen_at=close + timedelta(minutes=1),
                                  candidate_activation_at=close + timedelta(minutes=2),
                                  calibration_sha256=calibration_digest, source_identity=sources)
        channel = out / "channels" / f"ch{document['channel']}"
        write_new(channel / "freeze.json", frozen)
        ledger = frozen
        for row in evidence:
            if row["record"]["month"] <= cutoff:
                continue
            ledger = append_monitor(ledger, row, detected_at=month_start(row["record"]["month"] + 1)
                                     + timedelta(minutes=1))
        verify_ledger(ledger)
        if ledger["frozen_assignments"] != frozen["frozen_assignments"] or ledger["evaluations"]:
            raise AssertionError("replay changed commitments or invented acquisition evaluations")
        write_new(channel / "ledger.json", ledger)
        first_stop = next((d for d in ledger["monitor_decisions"] if d["reasons"]), None)
        summaries.append({
            "channel": document["channel"], "initial_status": frozen["status"], "status": ledger["status"],
            "frozen_months": len(prefix), "monitor_months": len(ledger["monitor_decisions"]),
            "initial_refusals": frozen["initial_refusals"], "halted_at": ledger["halted_at"],
            "first_stop_observed_month": first_stop["observed_month"] if first_stop else None,
            "first_stop_reasons": first_stop["reasons"] if first_stop else [],
            "new_boundary_observations": sum(bool(d["new_boundaries"]) for d in ledger["monitor_decisions"]),
            "committed_assignment_disagreement_observations": sum(bool(d["revised_prior_assignments"])
                                                                      for d in ledger["monitor_decisions"]),
            "frozen_assignments_preserved": True, "acquisition_evaluations": 0,
            "final_ledger_sha256": ledger["ledger_sha256"],
        })
    report = {"schema": "offline-causal-era-replay-v1", "plan_sha256": calibration_digest,
              "scientific_certification": False, "operational_acceptance": False,
              "channels": sorted(summaries, key=lambda r: r["channel"])}
    write_new(out / "summary.json", report)
    for path in producing + [repo / "tests/test_validation_causal_eras.py"]:
        target = out / "source-snapshot" / path.relative_to(repo)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    write_new(out / "manifest.json", {
        "inputs": inputs, "sources": sources,
        "files": {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob("*")) if p.is_file()},
    })
    print(json.dumps({"channels": len(summaries),
                      "frozen_months": sum(c.get("frozen_months", 0) for c in summaries),
                      "monitor_months": sum(c.get("monitor_months", 0) for c in summaries),
                      "initially_halted": sum(c.get("initial_status") == "halted_requires_recalibration" for c in summaries),
                      "finally_halted": sum(c["status"] == "halted_requires_recalibration" for c in summaries)}, indent=2))


if __name__ == "__main__":
    main()
