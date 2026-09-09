#!/usr/bin/env python3
"""Freeze and inspect one failed, partial RX-only capture; never accept it."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import numpy as np
from rfisher_results.validation.sdr_capture import narrow_feature, projection, joint_tone_line


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda: f.read(1048576), b""):
            h.update(b)
    return h.hexdigest()


def write(path, value):
    with Path(path).open("x") as f:
        json.dump(value, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")


def freeze(workspace, study):
    source = workspace / "results/noise_signal_references_2026-09-09/hardware/triplet01-noise"
    receipt = json.loads((source / "receipt.json").read_text())
    worker = json.loads((source / "worker-status.json").read_text())
    files = {}
    for name, digest in receipt["artifacts"].items():
        p = source / name
        if sha(p) != digest:
            raise ValueError("Archived identity differs: " + str(p))
        files[str(p)] = digest
    files[str(source / "receipt.json")] = sha(source / "receipt.json")
    module = workspace / "RFIsher/src/rfisher_results/validation/sdr_capture.py"
    sources = [Path(__file__).resolve(), module]
    amendment = {
        "schema": "retained-sdr-failed-rx-only-amendment-v1",
        "frozen_utc": datetime.now(timezone.utc).isoformat(),
        "original_plan_sha256": sha(study / "plan.json"),
        "reason": "Additional failed RX-only capture discovered after original smoke analysis; original plan and measurements remain unchanged.",
        "selection_frozen_before_additional_payload_analysis": True,
        "source": str(source), "input_sha256": files,
        "source_sha256": {str(p): sha(p) for p in sources},
        "worker": worker,
        "readback_limit": "Before-readout registers indicate TX disabled; after-readout register evidence is absent. No TX stream or payload attempted; initialization included internal TX gain calibration.",
        "status": "Failed qualified transport; partial retained diagnostic only. accepted.cfile is a filename, not acceptance.",
        "sample_encoding": "little-endian complex64",
        "tone_hz": 100000., "line_hz": 309900.,
        "windows_sample_offsets_in_retained_prefix": {"early": [0,60000], "middle": [800000,860000], "late": [1560000,1620000]},
        "selection_basis": "Three fixed 30 ms windows spread through the retained prefix; chosen from metadata before IQ read and all precede the terminal drop-reporting chunk. This is still a failed run, not a qualified noise baseline.",
        "all_chunk_rule": "Retain every received chunk contributing to accepted.cfile, including partial first and terminal drop-reporting chunks. Verify byte equality against the corresponding raw timestamp interval. Report per-chunk 100k/309.9k projections and mean power with original flags.",
        "feature_rule": "Use original frozen narrow_feature and joint_tone_line definitions; no line-origin inference, physical power, independent-block uncertainty, or actual ATSC pilot/reference conclusion.",
        "scientific_acceptance": False, "hardware_access": False,
    }
    write(study / "amendment-tx-disabled.json", amendment)
    snapshot = study / "source_snapshots" / Path(__file__).name
    snapshot.write_bytes(Path(__file__).read_bytes())
    print(json.dumps({"amendment_sha256": sha(study / "amendment-tx-disabled.json"), "inputs": len(files)}))


def run(study):
    os.nice(10)
    path = study / "amendment-tx-disabled.json"
    plan = json.loads(path.read_text())
    if sha(study / "plan.json") != plan["original_plan_sha256"]:
        raise ValueError("Original plan changed")
    for group in ("source_sha256", "input_sha256"):
        for p, digest in plan[group].items():
            if sha(p) != digest:
                raise ValueError("Frozen identity changed: " + p)
    source, w = Path(plan["source"]), plan["worker"]
    rx = np.fromfile(source / "rx.cfile", dtype="<c8")
    retained = np.fromfile(source / "accepted.cfile", dtype="<c8")
    startup = np.fromfile(source / "startup.cfile", dtype="<c8")
    if len(retained) != w["accepted_samples"] or len(rx) != w["captured_samples"]:
        raise ValueError("Sample count mismatch")
    if not np.isfinite(retained).all():
        raise ValueError("Nonfinite partial record")
    rate = w["rx_rate_hz"]
    chunks = [json.loads(s) for s in (source / "rx-chunks.jsonl").read_text().splitlines()]
    rows, cursor = [], 0
    for row in chunks:
        n = row["accepted_samples_from_chunk"]
        if not n:
            continue
        offset = row["accepted_file_sample_offset"]
        if offset != cursor:
            raise ValueError("Retained prefix chunk offsets not contiguous")
        timestamp = w["accepted_first_timestamp"] + offset
        local = timestamp - row["timestamp"]
        if not 0 <= local < local+n <= row["received_count"]:
            raise ValueError("Retained timestamp interval does not fit raw chunk")
        start = row["file_sample_offset"] + local
        x = retained[offset:offset+n].astype(np.complex128)
        equal = retained[offset:offset+n].tobytes() == rx[start:start+n].tobytes()
        if not equal:
            raise ValueError("Retained prefix differs from timestamp-bound raw bytes")
        result = {k: row[k] for k in ("chunk_index", "timestamp", "timestamp_gap", "dropped_delta", "underrun_delta", "overrun_delta", "action", "accepted_file_sample_offset", "accepted_samples_from_chunk")}
        result.update({"accepted_sample_timestamp": timestamp, "raw_file_sample_offset": start,
                       "raw_bytes_equal": equal, "center_seconds_relative_retained_start": (offset+n/2)/rate,
                       "mean_power": float(np.mean(abs(x)**2)),
                       "tone_projection_power": abs(projection(x, rate, plan["tone_hz"]))**2,
                       "line_projection_power": abs(projection(x, rate, plan["line_hz"]))**2})
        rows.append(result)
        cursor += n
    if cursor != len(retained):
        raise ValueError("Retained chunks do not account for all bytes")
    windows = {}
    for name, (a,b) in plan["windows_sample_offsets_in_retained_prefix"].items():
        x = retained[a:b]
        tone = narrow_feature(x, rate, plan["tone_hz"])
        line = narrow_feature(x, rate, plan["line_hz"])
        overlaps = [r["chunk_index"] for r in rows if r["accepted_file_sample_offset"] < b and r["accepted_file_sample_offset"]+r["accepted_samples_from_chunk"] > a and (r["dropped_delta"] or r["underrun_delta"] or r["overrun_delta"] or r["timestamp_gap"])]
        windows[name] = {"sample_offsets": [a,b], "timestamps": [w["accepted_first_timestamp"]+a,w["accepted_first_timestamp"]+b],
                         "seconds_relative_retained_start": [a/rate,b/rate], "samples": len(x),
                         "overlapping_reported_fault_chunks": overlaps,
                         "mean_power": float(np.mean(abs(x.astype(np.complex128))**2)), "tone": tone, "line": line,
                         "joint_projection": joint_tone_line(x, rate, plan["tone_hz"], line["fitted_frequency_hz"])}
    offset, count = w["qualification_overlap_startup_sample_offset"], w["qualification_samples"]
    equal = startup[offset:offset+count].tobytes() == rx[:count].tobytes()
    if not equal:
        raise ValueError("Qualification duplicate differs")
    result = {"schema": "retained-failed-rx-only-diagnostics-v1", "amendment_sha256": sha(path),
              "completed_utc": datetime.now(timezone.utc).isoformat(), "python": sys.version, "numpy": np.__version__,
              "measurement_status": "failed_transport_partial_prefix_diagnostics_only", "scientific_acceptance": False,
              "source_success": w["success"], "accepted_interval_passed": w["accepted_interval_passed"],
              "tx_disabled_register_readbacks": w["tx_disabled_register_readbacks"],
              "tx_attempted": w["tx_attempted"], "tx_chain_active_for_payload": w["tx_chain_active_for_payload"],
              "sample_rate_hz_readback": rate, "rx_frequency_hz_readback": w["rx_frequency_hz"],
              "retained_samples": len(retained), "requested_samples": w["record_samples_requested"],
              "retained_duration_seconds": len(retained)/rate,
              "raw_prefix_samples": len(rx), "raw_prefix_finite": bool(np.isfinite(rx).all()),
              "raw_status_next_timestamp_matches_full_rx_count": w["next_rx_timestamp"]-w["first_rx_timestamp"] == len(rx),
              "status_timestamp_note": "The final fault-reporting chunk was stored, but next_rx_timestamp was not advanced past it. Chunk records provide the saved-data accounting; the failed run is not promoted.",
              "startup_dropped": w["startup_rx_dropped"], "qualified_dropped": w["qualified_rx_dropped"],
              "qualification_duplicate_equal_bytes": equal, "qualification_duplicate_samples": count,
              "chunk_records": rows, "windows": windows,
              "atsc_science_bin_conclusion": "not determined by this failed 2 MHz smoke-geometry capture"}
    write(study / "partial-tx-disabled.json", result)
    print(json.dumps({"result": str(study / "partial-tx-disabled.json"), "retained_chunks": len(rows), "windows": windows}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("freeze")
    p.add_argument("--workspace", type=Path, required=True)
    p.add_argument("--study", type=Path, required=True)
    p = sub.add_parser("run")
    p.add_argument("--study", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "freeze":
        freeze(args.workspace.resolve(), args.study.resolve())
    else:
        run(args.study.resolve())


if __name__ == "__main__":
    main()
