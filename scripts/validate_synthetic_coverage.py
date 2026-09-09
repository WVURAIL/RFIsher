#!/usr/bin/env python3
"""Freeze, generate and evaluate a fresh-draw digital residual check.

This is a conditional experiment at fixed policies, not telescope calibration.
The plan is written before generation and must not be edited after inspection.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def write_new(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def freeze(reference, output):
    reference, output = reference.resolve(), output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = json.loads((reference / "frontier_report.json").read_text())
    config = json.loads((reference / "study_config.json").read_text())
    if config["geometry"]["reduced_geometry"]:
        raise ValueError("reference must use production geometry")
    with (reference / "frontier_points.csv").open() as stream:
        candidates = [row for row in csv.DictReader(stream)
                      if row["configuration"] == "snrm10p0_duty025"
                      and int(row["rho"]) == 62 and float(row["r_sys"]) <= .0125]
    selected = max(candidates, key=lambda row: int(row["kept"]))
    with np.load(reference / "frames/off.npz", allow_pickle=False) as shard:
        requirements = shard["required_multiplier_q16"][:, 61]
        # Zero in this product denotes an unkeepable frame, not a zero score.
        requirements = sorted(int(x) if x else 2**64 for x in requirements)
        null_q16 = requirements[math.ceil(.95 * len(requirements)) - 1]
    if null_q16 >= 2**64:
        raise ValueError("95% reference-null retention is not deployable")
    proxy = reference.parents[2]
    material = list(reference.glob("frames/*.npz")) + [
        reference / name for name in
        ("frontier_report.json", "study_config.json", "frontier_points.csv")]
    tracked = subprocess.check_output(["git", "-C", str(proxy), "ls-files", "-z"])
    material += [proxy / name for name in tracked.decode().split("\0")
                 if name.startswith(("src/", "tools/", "weights/"))
                 and (proxy / name).is_file()]
    material += [Path(config["inputs"]["input_iq"]), Path(__file__).resolve(),
                 proxy / "generated/atsc/atsc_waveform_audit_settled.json"]
    plan = {
        "schema": "rfisher-synthetic-coverage-plan-v1",
        "frozen_utc": datetime.now(timezone.utc).isoformat(),
        "claim_scope": "fresh pseudorandom draws conditional on the fixed digital generator, waveform and training floor; not physical confidence calibration",
        "reference_directory": str(reference),
        "reference_config_sha256": config["config_sha256"],
        "geometry": config["geometry"],
        "floor_linear": report["floor"]["floor_linear"],
        "floor_source": "original independent 1000-frame floor pool; never refitted",
        "policies": [
            {"name": "keep_all", "rho": None, "eta_q16": None},
            {"name": "reference_loud_half", "rho": 62,
             "eta_q16": int(selected["eta_q16"]), "reference_allowance": .0125},
            {"name": "reference_null_95pct", "rho": 62, "eta_q16": null_q16},
        ],
        "shelves_db": [-10., -44., -50., -55.],
        "duty_cycle": .25,
        "seeds": [20260909, 20260910, 20260911],
        "replicates_per_seed": 20,
        "on_frames_per_replicate": 25,
        "off_frames_per_replicate": 75,
        "minimum_retained_frames": 30,
        "alpha": .05,
        "independence_unit": "disjoint 100-frame replicate within each policy/shelf; policies and shelves share off frames and must not be pooled",
        "endpoint": "kept-set assigned mean is at least the known injected kept-set mean; unsupported replicates count as failures in the unconditional success bound",
        "interval": "one-sided exact binomial lower limit per case and Bonferroni simultaneous limit across all 12 predeclared cases",
        "inputs": {str(path): digest(path) for path in sorted(set(material))},
    }
    write_new(output / "plan.json", plan)
    (output / "plan.sha256").write_text(digest(output / "plan.json") + "\n")
    print(json.dumps({"plan": str(output / "plan.json"), "sha256": digest(output / "plan.json"),
                      "policies": plan["policies"]}, indent=2))


def load_plan(output):
    path = output / "plan.json"
    if digest(path) != (output / "plan.sha256").read_text().strip():
        raise ValueError("frozen plan hash changed")
    plan = json.loads(path.read_text())
    for name, expected in plan["inputs"].items():
        if digest(name) != expected:
            raise ValueError(f"frozen input changed: {name}")
    return plan


def generate(output, python):
    plan = load_plan(output)
    reference = Path(plan["reference_directory"])
    proxy = reference.parents[2]
    config = json.loads((reference / "study_config.json").read_text())
    for seed in plan["seeds"]:
        destination = output / f"seed-{seed}"
        if destination.exists():
            raise ValueError(f"refusing to overwrite or silently resume {destination}")
        command = [str(python), "tools/mask_residual_frontier.py", "--stage", "generate",
                   "--gpu", "--output-dir", str(destination), "--input-iq",
                   config["inputs"]["input_iq"], "--waveform-audit",
                   str(proxy / "generated/atsc/atsc_waveform_audit_settled.json"),
                   "--shelf-snr-db", *map(str, plan["shelves_db"]), "--duty-cycle", ".25",
                   "--rho", "62", "--frames-on", "500", "--frames-off", "1500",
                   "--frames-floor", "30", "--seed", str(seed), "--no-resume"]
        print("RUN", " ".join(command), flush=True)
        subprocess.run(command, cwd=proxy, check=True)


def evaluate(output):
    from rfisher_results.validation.coverage import evaluate_replicates

    plan = load_plan(output)
    reference = Path(plan["reference_directory"])
    used_seeds = set()
    for path in reference.glob("frames/*.npz"):
        with np.load(path, allow_pickle=False) as shard:
            used_seeds.update(map(int, shard["frame_seed"]))
    artifacts = {}
    cases = {(shelf, p["name"]): [] for shelf in plan["shelves_db"] for p in plan["policies"]}
    for seed in plan["seeds"]:
        directory = output / f"seed-{seed}"
        populations = {}
        for path in sorted((directory / "frames").glob("*.npz")):
            with np.load(path, allow_pickle=False) as shard:
                meta = json.loads(shard["meta_json"].item())
                frame_seeds = list(map(int, shard["frame_seed"]))
                if len(set(frame_seeds)) != len(frame_seeds) or used_seeds.intersection(frame_seeds):
                    raise ValueError("training/evaluation or within-evaluation seed reuse")
                used_seeds.update(frame_seeds)
                geometry = plan["geometry"]
                for key in ("num_streams", "reduced_geometry", "physical_channel", "offset_fine_bins", "anchor_bin", "bulk_size"):
                    if meta[key] != geometry[key]:
                        raise ValueError(f"geometry mismatch: {key}")
                if meta["seed"] != seed:
                    raise ValueError("unplanned generator seed")
                if datetime.fromisoformat(meta["created_utc"]) <= datetime.fromisoformat(plan["frozen_utc"]):
                    raise ValueError("evaluation predates the frozen plan")
                populations[meta["population"]] = {
                    "required": shard["required_multiplier_q16"],
                    "shelf": shard["shelf_estimate_db"],
                    "truth": meta["injected_linear"],
                }
            artifacts[str(path.resolve())] = digest(path)
        off = populations["off"]
        for shelf in plan["shelves_db"]:
            on = populations["on_m" + str(abs(shelf)).replace(".", "p")]
            if not np.isclose(on["truth"], 10**(shelf/10), rtol=1e-12, atol=0) or off["truth"] != 0:
                raise ValueError("injected truth mismatch")
            for index in range(plan["replicates_per_seed"]):
                a, b = plan["on_frames_per_replicate"], plan["off_frames_per_replicate"]
                shelf_values = np.r_[off["shelf"][index*b:(index+1)*b], on["shelf"][index*a:(index+1)*a]]
                required = np.concatenate([off["required"][index*b:(index+1)*b], on["required"][index*a:(index+1)*a]])
                if len(shelf_values) != a+b:
                    raise ValueError("incomplete replicate")
                claim = np.full(a+b, plan["floor_linear"])
                finite = np.isfinite(shelf_values)
                claim[finite] = np.maximum(10**(shelf_values[finite]/10), plan["floor_linear"])
                truth = np.r_[np.zeros(b), np.full(a, on["truth"])]
                for policy in plan["policies"]:
                    kept = np.ones(a+b, dtype=bool)
                    if policy["rho"] is not None:
                        req = required[:, policy["rho"]-1]
                        kept = (req != 0) & (req <= policy["eta_q16"])
                    cases[(shelf, policy["name"])].append({
                        "id": f"{seed}:{index}", "kept": int(kept.sum()),
                        "claim": float(claim[kept].mean()) if kept.any() else None,
                        "truth": float(truth[kept].mean()) if kept.any() else None,
                    })
    report = {"schema": "rfisher-synthetic-coverage-report-v1", "plan_sha256": digest(output / "plan.json"),
              "claim_scope": plan["claim_scope"], "cases": [], "inputs": artifacts}
    for (shelf, policy), replicates in cases.items():
        report["cases"].append({"shelf_db": shelf, "policy": policy,
            **evaluate_replicates(replicates, minimum_retained=plan["minimum_retained_frames"],
                                  alpha=plan["alpha"], comparisons=len(cases)),
            "replicates": replicates})
    write_new(output / "coverage-report.json", report)
    for case in report["cases"]:
        print({k: v for k, v in case.items() if k != "replicates"})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["freeze", "generate", "evaluate"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--generator-python", type=Path)
    args = parser.parse_args()
    if args.stage == "freeze":
        if args.reference is None:
            parser.error("freeze requires --reference")
        freeze(args.reference, args.output)
    elif args.stage == "generate":
        if args.generator_python is None:
            parser.error("generate requires --generator-python")
        # Resolving a venv's python symlink selects the base interpreter and
        # silently bypasses that environment's installed dependencies.
        generate(args.output.resolve(), args.generator_python.expanduser().absolute())
    else:
        evaluate(args.output.resolve())


if __name__ == "__main__":
    main()
