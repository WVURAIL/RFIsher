#!/usr/bin/env python3
"""Freeze metadata selection, then measure bounded native voltage correlations.

Run with OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 and PYTHONPATH=src.
The stored selected bytes are the reproducible payload; original large HDF5
files are identified by metadata/stat, not represented as whole-file hashed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import platform
import sys

import h5py
import numpy as np

from rfisher_results.validation.voltage_coherence import (
    decode_excess8, pair_moments, summarize_moments,
)

KEYS = ("count", "sum_x", "power_x", "cross")
POLICIES = ("all", "exclude_00")


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path, value):
    with Path(path).open("x") as f:
        json.dump(value, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")


def utc():
    return datetime.now(timezone.utc).isoformat()


def header(path):
    path = Path(path).resolve()
    st = path.stat()
    with h5py.File(path, "r") as f:
        if set(f.keys()) != {"baseband", "index_map"} or set(f["index_map"].keys()) != {"input"}:
            raise ValueError("unexpected archive schema; explicitly review new flags/coordinates")
        data, inputs = f["baseband"], f["index_map/input"][:]
        axes = [a.decode() if isinstance(a, bytes) else str(a) for a in data.attrs["axis"]]
        if data.dtype != np.uint8 or data.ndim != 2 or data.shape[1] != 2048 or axes != ["time", "input"]:
            raise ValueError("unsupported voltage shape, dtype or axes")
        if inputs.dtype.names != ("chan_id", "correlator_input") or len(inputs) != 2048:
            raise ValueError("unsupported input map")
        if len(np.unique(inputs["chan_id"])) != 2048 or len(np.unique(inputs["correlator_input"])) != 2048:
            raise ValueError("duplicate input identities")
        dt = float(f.attrs["delta_time"])
        freq_id, freq = int(f.attrs["freq_id"]), float(f.attrs["freq"])
        if dt != 2.56e-6 or freq != 800 - freq_id*0.390625:
            raise ValueError("frequency/sample-period convention differs")
        first = int(f.attrs["time0_fpga_count"])
        meta = {
            "path": str(path), "size_bytes": st.st_size, "mtime_ns": st.st_mtime_ns,
            "freq_id": freq_id, "frequency_mhz": freq,
            "event_id": int(f.attrs["event_id"]), "shape": list(data.shape),
            "dtype": str(data.dtype), "axes": axes,
            "fpga_start": first, "fpga_stop": first + data.shape[0],
            "delta_time_seconds": dt,
            "time0_ctime": float(f.attrs["time0_ctime"]),
            "time0_ctime_offset": float(f.attrs["time0_ctime_offset"]),
            "input_map_sha256": hashlib.sha256(inputs.tobytes()).hexdigest(),
            "input_map_dtype": inputs.dtype.descr,
            "archive_version": str(f.attrs.get("archive_version", "unknown")),
            "git_version_tag": str(f.attrs.get("git_version_tag", "unknown")),
            "packet_flags_available": False, "gain_delay_calibration_available": False,
        }
    return meta, inputs


def freeze(workspace, study):
    workspace, study = Path(workspace).resolve(), Path(study).resolve()
    if study.exists():
        raise FileExistsError(study)
    records = []
    reference = None
    for freq_id in range(600, 615):
        path = workspace / f"datasets/baseband/astro_1153713684/baseband_1153713684_{freq_id}.h5"
        info, inputs = header(path)
        if info["event_id"] != 1153713684 or info["freq_id"] != freq_id:
            raise ValueError("unexpected event/frequency identity")
        if reference is None:
            reference = inputs
        elif reference.tobytes() != inputs.tobytes():
            raise ValueError("input maps differ")
        records.append(info)
    start = max(d["fpga_start"] for d in records)
    stop = min(d["fpga_stop"] for d in records)
    if stop <= start:
        raise ValueError("no shared FPGA interval")
    # Exact Decimal conversion of the stored float values avoids cancellation
    # of epoch-sized ctime values before adding the separate small offsets.
    t0 = Decimal(records[0]["time0_ctime"]) + Decimal(records[0]["time0_ctime_offset"])
    differences = []
    for d in records:
        t = Decimal(d["time0_ctime"]) + Decimal(d["time0_ctime_offset"])
        delta = (t-t0) - Decimal(d["fpga_start"]-records[0]["fpga_start"])*Decimal(d["delta_time_seconds"])
        differences.append(float(abs(delta)))
    if max(differences) > 1e-12:
        raise ValueError("FPGA and corrected ctime disagree")
    selected = [128*g+j for g in range(16) for j in (0, 1)]
    identities = [{"array_index": i, "chan_id": int(reference[i]["chan_id"]),
                   "correlator_input": reference[i]["correlator_input"].decode("ascii")}
                  for i in selected]
    exclusion = workspace/"results/channel29_followup_2026-09-09/metadata/exclusions.json"
    exclusions = json.loads(exclusion.read_text())
    def event_present(value):
        if isinstance(value, dict):
            return any(event_present(k) or event_present(v) for k, v in value.items())
        if isinstance(value, list):
            return any(event_present(v) for v in value)
        return str(value) == "1153713684"
    if not event_present(exclusions):
        raise ValueError("development event missing from exclusion record")
    module = workspace/"RFIsher/src/rfisher_results/validation/voltage_coherence.py"
    code = [Path(__file__).resolve(), module]
    evidence = [workspace/"pilot-proxy/src/pilot_proxy/chime/baseband_format.py",
                workspace/"kotekan/python/kotekan/scripts/baseband_archiver.py",
                workspace/"kotekan/lib/stages/basebandReadout.cpp", exclusion]
    plan = {
        "schema": "inband-native-coherence-v1", "frozen_utc": utc(),
        "scope": "One previously inspected development event; descriptive raw digital moments",
        "physical_calibration": False, "independent_validation": False,
        "event_id": 1153713684, "frequencies": records, "inputs": identities,
        "selection_rule": "array indices 128*g+{0,1}, g=0..15; no amplitude-based selection",
        "representative_array_claim": False,
        "common_fpga_start": start, "common_fpga_stop": stop,
        "samples": stop-start, "delta_time_seconds": records[0]["delta_time_seconds"],
        "maximum_ctime_fpga_discrepancy_seconds": max(differences),
        "blocks": [[a, min(a+4096, stop-start)] for a in range(0, stop-start, 4096)],
        "selected_plot_pairs": [[0, 1], [0, 16], [16, 17]],
        "nominal_edges_mhz": [559.9609375, 565.8203125],
        "target_mhz": [560., 566.], "uncovered_upper_target_mhz": 0.1796875,
        "packing": "complex128((byte>>4)-8 + 1j*((byte&15)-8)); native convention",
        "orientation": "No conjugation, reversal, delay or gain applied; raw native phases",
        "policies": {"all": "all stored samples, including possible fill",
                     "exclude_00": "exclude byte 0x00 per input; code-conditioned sensitivity, not packet validity"},
        "validity_limit": "0x00 may be absent fill or legitimate (-8,-8). 0x88 is complex digital zero.",
        "moments": "sum x_i conj(x_j), sum x_i and sum |x_i|^2 on identical common pair support",
        "uncertainty": "Descriptive contiguous-block variation only; no iid sample count or confidence interval",
        "source_sha256": {str(p): sha(p) for p in code},
        "format_reference_sha256": {str(p): sha(p) for p in evidence},
        "producer_limit": "Local format code is supporting evidence, not verified exact historical producer",
        "payload_identity": "Selected contiguous uint8 [time,input] bytes hashed and saved; source whole-file hashes not claimed",
    }
    study.mkdir(parents=True)
    (study/"source_snapshots").mkdir()
    for p in code+evidence:
        (study/"source_snapshots"/p.name).write_bytes(p.read_bytes())
    write_json(study/"plan.json", plan)
    print(json.dumps({"frozen": str(study), "plan_sha256": sha(study/"plan.json"),
                      "samples": stop-start, "inputs": len(selected)}, sort_keys=True), flush=True)


def run(study):
    study = Path(study).resolve()
    plan = json.loads((study/"plan.json").read_text())
    for p, expected in plan["source_sha256"].items():
        if sha(p) != expected:
            raise ValueError(f"frozen implementation changed: {p}")
    data_dir = study/"data"
    data_dir.mkdir()  # Exclusive: no overwrite/resume across a changed procedure.
    os.nice(10)
    selected = [d["array_index"] for d in plan["inputs"]]
    ninput, nblock = len(selected), len(plan["blocks"])
    records = []
    for info in plan["frequencies"]:
        actual, _ = header(info["path"])
        if json.loads(json.dumps(actual)) != info:
            raise ValueError("input header/stat changed since freeze")
        arrays = {"packed": np.empty((plan["samples"], ninput), dtype=np.uint8),
                  "zero_code_count": np.zeros((nblock, ninput), dtype=np.int64),
                  "digital_zero_count": np.zeros((nblock, ninput), dtype=np.int64),
                  "all_inputs_zero_code_count": np.zeros(nblock, dtype=np.int64),
                  "some_inputs_zero_code_count": np.zeros(nblock, dtype=np.int64),
                  "component_rail_count": np.zeros((nblock, ninput, 2), dtype=np.int64)}
        for policy in POLICIES:
            for key in KEYS:
                dtype = np.int64 if key == "count" else (np.float64 if key == "power_x" else np.complex128)
                arrays[f"{policy}_{key}"] = np.zeros((nblock, ninput, ninput), dtype=dtype)
        offset = plan["common_fpga_start"] - info["fpga_start"]
        with h5py.File(info["path"], "r") as f:
            for b, (start, stop) in enumerate(plan["blocks"]):
                # Each contiguous disk read is bounded to <=8 MiB; no giant
                # full-array decoded voltage buffer or GPU allocation is used.
                packed = f["baseband"][offset+start:offset+stop, :][:, selected]
                arrays["packed"][start:stop] = packed
                x = decode_excess8(packed)
                arrays["zero_code_count"][b] = (packed == 0).sum(axis=0)
                arrays["digital_zero_count"][b] = (packed == 0x88).sum(axis=0)
                zero_per_row = (packed == 0).sum(axis=1)
                arrays["all_inputs_zero_code_count"][b] = (zero_per_row == ninput).sum()
                arrays["some_inputs_zero_code_count"][b] = ((zero_per_row > 0) & (zero_per_row < ninput)).sum()
                arrays["component_rail_count"][b, :, 0] = ((x.real == -8) | (x.real == 7)).sum(axis=0)
                arrays["component_rail_count"][b, :, 1] = ((x.imag == -8) | (x.imag == 7)).sum(axis=0)
                for policy in POLICIES:
                    moments = pair_moments(x, None if policy == "all" else packed != 0)
                    for key in KEYS:
                        arrays[f"{policy}_{key}"][b] = moments[key]
        if Path(info["path"]).stat().st_mtime_ns != info["mtime_ns"] or Path(info["path"]).stat().st_size != info["size_bytes"]:
            raise ValueError("input changed during extraction")
        dest = data_dir / f"ch{info['freq_id']:04d}.npz"
        with dest.open("xb") as f:
            np.savez_compressed(f, **arrays)
        record = {"freq_id": info["freq_id"], "frequency_mhz": info["frequency_mhz"],
                  "path": str(dest.relative_to(study)), "sha256": sha(dest),
                  "selected_packed_sha256": hashlib.sha256(arrays["packed"].tobytes()).hexdigest(),
                  "selected_bytes": int(arrays["packed"].nbytes),
                  "all_inputs_zero_code_samples": int(arrays["all_inputs_zero_code_count"].sum()),
                  "some_inputs_zero_code_samples": int(arrays["some_inputs_zero_code_count"].sum()),
                  "zero_code_fraction": float(np.mean(arrays["packed"] == 0)),
                  "zero_code_fraction_by_input": (arrays["zero_code_count"].sum(axis=0)/plan["samples"]).tolist(),
                  "digital_zero_fraction": float(np.mean(arrays["packed"] == 0x88)),
                  "component_rail_fraction": (arrays["component_rail_count"].sum(axis=(0,1))/(plan["samples"]*ninput)).tolist(),
                  "policies": {}}
        pairs = np.triu_indices(ninput, 1)
        for policy in POLICIES:
            pooled = {key: arrays[f"{policy}_{key}"].sum(axis=0) for key in KEYS}
            stats = summarize_moments(pooled)
            values = np.abs(stats["coherency"][pairs])
            finite = values[np.isfinite(values)]
            record["policies"][policy] = {
                "defined_pairs": int(finite.size), "total_pairs": int(values.size),
                "median_abs_coherency": float(np.median(finite)) if finite.size else None,
                "maximum_abs_coherency": float(np.max(finite)) if finite.size else None,
                "minimum_pair_count": int(pooled["count"][pairs].min()),
                "maximum_pair_count": int(pooled["count"][pairs].max()),
                "zero_auto_input_slots": np.flatnonzero(np.diag(pooled["power_x"]) == 0).tolist(),
            }
        records.append(record)
        print(json.dumps(record), flush=True)
    write_json(study/"summary.json", {"schema": "inband-native-coherence-summary-v1",
               "completed_utc": utc(), "plan_sha256": sha(study/"plan.json"),
               "python": sys.version, "numpy": np.__version__, "h5py": h5py.__version__,
               "platform": platform.platform(), "frequencies": records,
               "physical_calibration": False, "independent_validation": False})


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
        freeze(args.workspace, args.study)
    else:
        run(args.study)


if __name__ == "__main__":
    main()
