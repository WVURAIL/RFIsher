#!/usr/bin/env python3
"""Freeze, fit and independently test a digital residual tolerance bound.

All earlier observations are development data. New calibration draws precede
the bound freeze; evaluation generation requires that frozen bound. Nothing in
this workflow changes a physical archive floor or authorizes a science policy.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess

import numpy as np


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(8*1024*1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_new(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def freeze(output, prior, generator_python):
    output.mkdir(parents=True, exist_ok=True)
    old = json.loads((prior/"synthetic/plan.json").read_text())
    reference = Path(old["reference_directory"])
    proxy = reference.parents[2]
    repo = Path(__file__).resolve().parents[1]
    config = json.loads((reference/"study_config.json").read_text())
    # Earlier frame seeds can never re-enter calibration or evaluation.
    development_shards = sorted(reference.glob("frames/*.npz")) + sorted(prior.glob("synthetic/seed-*/frames/*.npz"))
    files = [Path(name) for name in old["inputs"]
             if str(proxy) in name or name.endswith("study_config.json")]
    files += development_shards + [prior/"synthetic/plan.json", Path(__file__).resolve(),
                                  repo/"src/rfisher_results/validation/tolerance.py",
                                  repo/"src/rfisher_results/validation/coverage.py"]
    code = "import sys,json,numpy,cupy;print(json.dumps({'executable':sys.executable,'python':sys.version,'numpy':numpy.__version__,'cupy':cupy.__version__,'cuda_runtime':cupy.cuda.runtime.runtimeGetVersion()}))"
    runtime = json.loads(subprocess.check_output([str(generator_python), "-c", code], text=True))
    plan = {
        "schema": "rfisher-digital-residual-tolerance-plan-v1",
        "frozen_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Digital, realized kept-set mean prediction bound, conditional on the fixed generator/waveform, geometry, floor, policies and finite scenarios. Not a physical residual, per-frame bound, survey population-mean interval or operational calibration.",
        "method": "For each independent block, take max over all 15 cases of truth_kept_mean minus original assigned_kept_mean; unsupported cases give +infinity. Use the predeclared one-sided nonparametric order statistic. Bound each case by max(0, original assignment + correction).",
        "content": .95, "confidence": .95, "minimum_retained": 30,
        "calibration_seeds": [20260920, 20260921, 20260922],
        "evaluation_seeds": [20260923, 20260924, 20260925],
        "blocks_per_seed": 20, "off_frames_per_block": 75, "on_frames_per_block": 25,
        "shelves_db": old["shelves_db"], "policies": old["policies"],
        "null_scenario": "The same 75 off frames alone, evaluated under each policy; dependent within a block, not extra independent trials.",
        "independence_unit": "A block of 75 independent off frames plus 25 independent on frames at each of four levels; all policies share those draws. Different blocks use disjoint frame seeds.",
        "evaluation_endpoint": "All 15 cases supported and injected kept-set means <= their calibrated upper bounds; report every attempted block and exact one-sided binomial lower joint success limit. No tuning or extension after evaluation.",
        "empirical_validation_criterion": "The one-sided 95% lower joint success limit must be >=0.95 to demonstrate the target in evaluation; otherwise report inconclusive/failed support without refitting.",
        "floor_linear": old["floor_linear"], "geometry": config["geometry"],
        "reference_directory": str(reference), "proxy_directory": str(proxy),
        "generator_python": str(generator_python), "generator_runtime": runtime,
        "input_iq": config["inputs"]["input_iq"],
        "waveform_audit": str(proxy/"generated/atsc/atsc_waveform_audit_settled.json"),
        "development_shards": [str(path) for path in development_shards],
        "inputs": {str(path): sha(path) for path in sorted(set(files))},
    }
    write_new(output/"plan.json", plan)
    (output/"plan.sha256").write_text(sha(output/"plan.json")+"\n")
    print("Frozen", output/"plan.json", sha(output/"plan.json"), flush=True)


def load_plan(output):
    path = output/"plan.json"
    if sha(path) != (output/"plan.sha256").read_text().strip():
        raise ValueError("protocol digest changed")
    plan = json.loads(path.read_text())
    for name, expected in plan["inputs"].items():
        if sha(name) != expected:
            raise ValueError(f"frozen input changed: {name}")
    return plan


def load_bound(output):
    path = output/"calibration.json"
    if sha(path) != (output/"calibration.sha256").read_text().strip():
        raise ValueError("calibrated bound digest changed")
    result = json.loads(path.read_text())
    if result["plan_sha256"] != sha(output/"plan.json"):
        raise ValueError("bound belongs to a different plan")
    if result["calibration"]["status"] != "calibrated":
        raise ValueError("no finite calibrated bound")
    for name, expected in result["inputs"].items():
        if sha(name) != expected:
            raise ValueError(f"calibration input changed: {name}")
    return result


def generate(output, stage):
    plan = load_plan(output)
    bound = load_bound(output) if stage == "evaluation" else None
    destination = output/stage
    destination.mkdir(exist_ok=False)
    write_new(destination/"generation-start.json", {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "plan_sha256": sha(output/"plan.json"),
        "calibration_sha256": sha(output/"calibration.json") if bound else None})
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(plan["proxy_directory"])/"src")
    for seed in plan[f"{stage}_seeds"]:
        command = [plan["generator_python"], "tools/mask_residual_frontier.py", "--stage", "generate",
                   "--gpu", "--output-dir", str(destination/f"seed-{seed}"),
                   "--input-iq", plan["input_iq"], "--waveform-audit", plan["waveform_audit"],
                   "--shelf-snr-db", *map(str, plan["shelves_db"]), "--duty-cycle", ".25",
                   "--rho", "62", "--num-streams", "2048", "--physical-channel", "14",
                   "--offset-fine-bins", "0", "--frames-on", "500", "--frames-off", "1500",
                   "--frames-floor", "30", "--seed", str(seed), "--no-resume"]
        print("RUN", " ".join(command), flush=True)
        subprocess.run(command, cwd=plan["proxy_directory"], env=env, check=True)


def read_blocks(output, stage, plan):
    used = set()
    previous = [Path(p) for p in plan["development_shards"]]
    if stage == "evaluation":
        previous += list((output/"calibration").glob("seed-*/frames/*.npz"))
    for path in previous:
        with np.load(path, allow_pickle=False) as z:
            used.update(map(int, z["frame_seed"]))
    boundary = datetime.fromisoformat(plan["frozen_utc"])
    if stage == "evaluation":
        boundary = datetime.fromisoformat(load_bound(output)["frozen_utc"])
    blocks, identities = {}, {}
    for seed in plan[f"{stage}_seeds"]:
        populations = {}
        files = sorted((output/stage/f"seed-{seed}"/"frames").glob("*.npz"))
        if len(files) != 6:
            raise ValueError("incomplete/unexpected population shards")
        for path in files:
            with np.load(path, allow_pickle=False) as z:
                meta = json.loads(z["meta_json"].item())
                seeds = list(map(int, z["frame_seed"]))
                if len(set(seeds)) != len(seeds) or used.intersection(seeds):
                    raise ValueError("frame-seed reuse across development/calibration/evaluation")
                used.update(seeds)
                if meta["seed"] != seed or datetime.fromisoformat(meta["created_utc"]) <= boundary:
                    raise ValueError("unplanned seed or generation before freeze")
                for key in ("num_streams", "reduced_geometry", "physical_channel", "offset_fine_bins", "anchor_bin", "bulk_size"):
                    if meta[key] != plan["geometry"][key]:
                        raise ValueError(f"geometry changed: {key}")
                name = meta["population"]
                if name != path.stem or name in populations:
                    raise ValueError("population identity mismatch")
                expected = 1500 if name == "off" else 30 if name == "floor" else 500
                if len(seeds) != expected:
                    raise ValueError("population frame count mismatch")
                populations[name] = {"required": z["required_multiplier_q16"],
                                     "shelf": z["shelf_estimate_db"], "truth": meta["injected_linear"]}
            identities[str(path)] = sha(path)
        off = populations["off"]
        if off["truth"] != 0:
            raise ValueError("null truth is not zero")
        for block in range(plan["blocks_per_seed"]):
            rows = {}
            b, a = plan["off_frames_per_block"], plan["on_frames_per_block"]
            off_slice = slice(block*b, (block+1)*b)
            for level in [None, *plan["shelves_db"]]:
                req = off["required"][off_slice]
                shelf = off["shelf"][off_slice]
                truth = np.zeros(b)
                if level is not None:
                    on = populations["on_m"+str(abs(level)).replace(".", "p")]
                    if not np.isclose(on["truth"], 10**(level/10), rtol=1e-12, atol=0):
                        raise ValueError("injection truth mismatch")
                    on_slice = slice(block*a, (block+1)*a)
                    req = np.concatenate([req, on["required"][on_slice]])
                    shelf = np.r_[shelf, on["shelf"][on_slice]]
                    truth = np.r_[truth, np.full(a, on["truth"])]
                prediction = np.full(len(shelf), plan["floor_linear"])
                finite = np.isfinite(shelf)
                prediction[finite] = np.maximum(10**(shelf[finite]/10), plan["floor_linear"])
                for policy in plan["policies"]:
                    kept = np.ones(len(shelf), bool)
                    if policy["rho"] is not None:
                        q16 = req[:, policy["rho"]-1]
                        kept = (q16 != 0) & (q16 <= policy["eta_q16"])
                    case = f"{'null' if level is None else str(level)}:{policy['name']}"
                    rows[case] = {"kept": int(kept.sum()),
                                  "claim": float(prediction[kept].mean()) if kept.any() else None,
                                  "truth": float(truth[kept].mean()) if kept.any() else None}
            blocks[f"{stage}:{seed}:{block}"] = rows
    return blocks, identities


def fit(output):
    from rfisher_results.validation.tolerance import calibrate_joint_additive

    plan = load_plan(output)
    blocks, identities = read_blocks(output, "calibration", plan)
    calibration = calibrate_joint_additive(blocks, content=plan["content"], confidence=plan["confidence"],
                                           min_retained=plan["minimum_retained"])
    result = {"schema": "rfisher-digital-residual-calibration-v1",
              "frozen_utc": datetime.now(timezone.utc).isoformat(), "plan_sha256": sha(output/"plan.json"),
              "scope": plan["scope"], "calibration": calibration, "inputs": identities}
    write_new(output/"calibration.json", result)
    (output/"calibration.sha256").write_text(sha(output/"calibration.json")+"\n")
    print(json.dumps({k:v for k,v in calibration.items() if k not in ("blocks", "calibration_block_ids", "case_ids")}), flush=True)


def evaluate(output):
    from rfisher_results.validation.tolerance import evaluate_joint_additive

    plan, frozen = load_plan(output), load_bound(output)
    blocks, identities = read_blocks(output, "evaluation", plan)
    evaluation = evaluate_joint_additive(frozen["calibration"], blocks)
    result = {"schema": "rfisher-digital-residual-evaluation-v1", "plan_sha256": sha(output/"plan.json"),
              "calibration_sha256": sha(output/"calibration.json"), "scope": plan["scope"],
              "evaluation": evaluation, "inputs": identities}
    write_new(output/"evaluation.json", result)
    print("Evaluation written", output/"evaluation.json", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["freeze", "generate-calibration", "fit", "generate-evaluation", "evaluate"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prior-release", type=Path)
    parser.add_argument("--generator-python", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if args.stage == "freeze":
        if args.prior_release is None or args.generator_python is None:
            parser.error("freeze requires --prior-release and --generator-python")
        freeze(output, args.prior_release.resolve(), args.generator_python.expanduser().absolute())
    elif args.stage.startswith("generate-"):
        generate(output, args.stage.removeprefix("generate-"))
    elif args.stage == "fit":
        fit(output)
    else:
        evaluate(output)


if __name__ == "__main__":
    main()
