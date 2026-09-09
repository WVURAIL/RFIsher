#!/usr/bin/env python3
"""Inventory the local collaboration delivery and check HyFoRes pairing."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import h5py

from rfisher_results.validation.visibility import compare_beamformed_files, frequency_coverage


def sha256(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8*1024*1024), b""):
            result.update(block)
    return result.hexdigest()


def inventory(root):
    expected = {}
    provenance = {}
    for sums in root.glob("*/SHA256SUMS"):
        provenance[str(sums)] = sha256(sums)
        for line in sums.read_text().splitlines():
            value, name = line.split(maxsplit=1)
            path = (sums.parent / name.strip().removeprefix("*")).resolve()
            if not path.is_relative_to(root):
                raise ValueError("checksum path escapes input collection")
            expected[path] = value
    for source in root.glob("*/source.json"):
        provenance[str(source)] = sha256(source)
    products = []
    for path in sorted(root.rglob("*.h5")):
        record = {"path": str(path), "bytes": path.stat().st_size,
                  "recorded_sha256": expected.get(path),
                  "hash_verification": "not independently rehashed in this run"}
        # Hash the small products completely; avoid another 198 GB read for
        # metadata-only inspection of the visibility stacks.
        if record["bytes"] < 64*1024*1024:
            record["computed_sha256"] = sha256(path)
            if expected.get(path) != record["computed_sha256"]:
                raise ValueError(f"missing/mismatched delivery checksum: {path}")
            record["hash_verification"] = "verified in this run"
        with h5py.File(path, "r") as h:
            freq = h["index_map/freq"][:]
            record.update(frequency_coverage(freq["centre"], freq["width"]))
            record["frequency_units_basis"] = "draco frequency-map convention: MHz; nominal edges only"
            record["class"] = str(h.attrs.get("__memh5_subclass", ""))
            record["sidereal_days"] = list(map(int, h.attrs["lsd"]))
            record["datasets"] = {name: {"shape": list(h[name].shape), "dtype": str(h[name].dtype),
                                         "axes": [x.decode() if isinstance(x, bytes) else str(x)
                                                  for x in h[name].attrs.get("axis", [])]}
                                  for name in ("vis", "filter", "vis_weight", "nsample", "beam", "weight") if name in h}
            record["has_full_frequency_covariance"] = any(name in h for name in ("freq_cov", "complex_freq_cov"))
        products.append(record)
    pairs = []
    for directory in sorted(root.glob("hyfores_beamformed_*")):
        for part in ("all", "p0", "p1"):
            name = f"beamformed_filt_fitha_{part}.h5"
            pair = compare_beamformed_files(directory / "without_hyfores" / name,
                                           directory / "with_hyfores" / name)
            pairs.append({"partition": part, **pair})
    return {"schema": "rfisher-collaboration-transfer-preflight-v1", "products": products,
            "pairs": pairs, "provenance_files": provenance,
            "physical_dtv_calibration_status": "unmeasured",
            "scope": "Metadata and paired source-fit diagnostics only. No DTV-band transfer, independent null, signal-injection response or visibility covariance measurement is claimed."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = inventory(args.input.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    for pair in report["pairs"]:
        print(pair["partition"], pair["refusal_reasons"] or pair["diagnostics"])


if __name__ == "__main__":
    main()
