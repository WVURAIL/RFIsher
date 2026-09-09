#!/usr/bin/env python3
"""Prepare a conservative exclusion ledger and a pending physical-data plan."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from rfisher_results.validation.holdout import audit_future_cohort


def prepare(inventories):
    events, inputs = set(), {}
    for path in inventories:
        digest = hashlib.sha256()
        count = 0
        with path.open("rb") as stream:
            for line in stream:
                digest.update(line)
                if not line.strip():
                    continue
                row = json.loads(line)
                event = row.get("event")
                if not isinstance(event, str) or not event.strip():
                    raise ValueError(f"missing event identity in {path}, row {count+1}")
                events.add(event)
                count += 1
        inputs[str(path.resolve())] = {"sha256": digest.hexdigest(), "rows": count}
    if not events:
        raise ValueError("empty development inventory")
    return {
        "schema": "rfisher-physical-evidence-plan-v1", "status": "pending_inputs",
        "accepted_policy_frozen_utc": None,
        "exclusion_policy": "Conservatively exclude every acquisition listed by the supplied development inventories, across all frequency shards. This ledger alone does not establish blindness. A future cohort must also follow the accepted policy/calibration freeze.",
        "excluded_event_ids": sorted(events), "excluded_acquisitions": len(events),
        "inputs": inputs,
        "current_cohort_audit": audit_future_cohort(events, [], frozen_at=None),
        "required_evidence": {
            "independent_states": {
                "status": "not_supplied", "fields": ["transmitter_id", "physical_channel", "start_utc", "end_utc", "state", "source_sha256", "independence_review_sha256", "candidate_scope_review_sha256"],
                "rule": "Timezone-aware half-open intervals; join full acquisition duration against all reviewed candidates. Missing, conflicting, unreviewed or partial coverage remains unknown.",
            },
            "visibility_and_filter_transfer": {
                "status": "no_in_scope_calibration", "target_band_mhz": [470., 608.],
                "required": ["complex visibilities with physical baseline/frequency/time coordinates and units",
                             "common acquisition membership, masks, valid-sample counts and exposure",
                             "actual filter matrices plus ordered pipeline configuration and software identities",
                             "known injected sky/RFI signal before and after the full fitting/filtering procedure",
                             "coherent mean, stochastic covariance and retained science response measured separately"],
            },
            "residual_confidence": {
                "status": "physical_coverage_unmeasured",
                "required": ["fixed residual definition, confidence target and policy before evaluation",
                             "independent controls with known truth and declared acquisition/day blocks",
                             "all attempted replicates, including unsupported/refused cases",
                             "simultaneous coverage or predeclared multiplicity treatment across candidate policies"],
            },
            "prospective_evaluation": {
                "status": "no_accepted_policy_or_candidate_cohort",
                "required": ["accepted calibration/policy artifact identities and freeze timestamp",
                             "future acquisitions with trustworthy start times and reviewed history",
                             "no acquisition overlap with any development/calibration source",
                             "same-policy exposure, transfer and joint forecast gates; no refitting on holdout"],
            },
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.inventory)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(f"Excluded {result['excluded_acquisitions']} known acquisitions; physical evidence remains pending.")


if __name__ == "__main__":
    main()
