#!/usr/bin/env python3
"""Freeze, fit and evaluate a new conditional channel29 retained-set experiment.

Generation is a separate source-pinned pilot-proxy command. Existing releases
are never edited. A calibration receipt freezes an outcome, including refusal;
it is not a physically qualified followup calibration bundle.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from rfisher_results.validation.channel29_controls import (
    ETA_DENOMINATOR, ETA_NUMERATOR, FLOOR_LINEAR, PRIMARY_CASES,
    REFERENCE_NORM_SUM_SQ, SHELF_CONVERSION, TARGET_NORM_SQ,
    assemble_cases, canonical_digest, frame_seed, maximum_kept_shelf,
    population_measurement,
)
from rfisher_results.validation.tolerance import calibrate_joint_additive, evaluate_joint_additive

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_SHA = "d6cf969313e361a5dd3b59f3bb4601f216c48e1f374bf9da1685feaaab8753e3"
POPULATIONS = [
    {"name": "off", "shelf_db": None, "reference_projection_gamma": 0., "count_per_block": 96},
    *[{"name": f"on_m{level}", "shelf_db": -float(level), "reference_projection_gamma": 0., "count_per_block": 32} for level in (50, 44, 10)],
    {"name": "clean_m35", "shelf_db": -35., "reference_projection_gamma": 0., "count_per_block": 128},
    {"name": "blind_m35_ref01", "shelf_db": -35., "reference_projection_gamma": .1, "count_per_block": 128},
    {"name": "ref_only01", "shelf_db": None, "reference_projection_gamma": .1, "count_per_block": 128},
]
PRIMARY = [p["name"] for p in POPULATIONS[:4]]
STAGES = {
    "calibration": {"blocks": 100, "populations": PRIMARY},
    "evaluation": {"blocks": 100, "populations": PRIMARY},
    "stress": {"blocks": 1, "populations": [p["name"] for p in POPULATIONS[4:]]},
}
STATISTICS = {
    "calibration_content": .97, "calibration_confidence": .95,
    "evaluation_target": .95, "evaluation_confidence": .95,
    "minimum_retained": 32, "minimum_retention": .25,
    "calibration_blocks": 100, "evaluation_blocks": 100,
    "evaluation_required_successes": 99,
    "method": "Maximum of100 independent joint truth-minus-original-floor scores over five fixed dependent cases. Unsupported cases score infinity. Evaluate all100 fresh blocks; require99 joint successes. No extension, replacement or deletion after outcomes.",
}


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def aware(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.utcoffset() is None:
        raise ValueError("timestamps must be timezone aware")
    return result


def check_seed_partition(output, plan):
    with np.load(output / "preflight/seed-exclusions.npz", allow_pickle=False) as z:
        old_raw = set(map(int, z["raw_seed"]))
        old_effective = set(map(int, z["effective_seed63"]))
    expected = []
    populations = {p["name"]: p for p in plan["populations"]}
    for stage, settings in {**plan["stages"], "audit": {"blocks": 1, "populations": plan["audit"]["populations"]}}.items():
        for b in range(settings["blocks"]):
            for pop in settings["populations"]:
                n = 1 if stage == "audit" else populations[pop]["count_per_block"]
                for i in range(n):
                    raw = frame_seed(plan["protocol_sha256"], stage, b, pop, i)
                    expected.append((stage, b, pop, i, raw, raw % (1 << 63)))
    raw = [r[4] for r in expected]
    effective = [r[5] for r in expected]
    if len(set(raw)) != len(raw) or len(set(effective)) != len(effective):
        raise ValueError("collision in planned frame identities")
    if old_raw.intersection(raw) or old_effective.intersection(effective):
        raise ValueError("planned frame identity reuses development randomness")
    with np.load(output / "preflight/planned-frame-seeds.npz", allow_pickle=False) as z:
        actual = list(zip(z["stage"].tolist(), z["block"].tolist(), z["population"].tolist(), z["frame"].tolist(), z["raw_seed"].tolist(), z["effective_seed63"].tolist()))
    if set(actual) != set(expected) or len(actual) != len(expected):
        raise ValueError("seed allocation differs from frozen coordinate grid")
    return {"frames": len(raw), "development_raw_exclusions": len(old_raw),
            "development_effective63_exclusions": len(old_effective), "passed": True}


def freeze(output, prepared):
    if (output / "plan.json").exists():
        raise ValueError("plan already exists")
    manifest = read(prepared)
    protocol_path = ROOT / "results/channel29_followup_2026-09-09/frozen/protocol.json"
    protocol = read(protocol_path)
    if protocol["protocol_sha256"] != PROTOCOL_SHA:
        raise ValueError("candidate protocol changed")
    if protocol["policy"]["eta_numerator"] != ETA_NUMERATOR or protocol["policy"]["eta_denominator"] != ETA_DENOMINATOR:
        raise ValueError("candidate selector changed")
    for key, value in (("target_norm_sq", TARGET_NORM_SQ), ("reference_norm_sum_sq", REFERENCE_NORM_SUM_SQ)):
        if protocol["geometry"][key] != value:
            raise ValueError("candidate norms changed")
        if manifest[key] != value:
            raise ValueError("prepared detector norms differ from candidate")
    if manifest["inputs"]["weights"]["sha256"] != protocol["geometry"]["weight_bank_sha256"]:
        raise ValueError("prepared weight bank differs from candidate")
    if manifest["packed_profile_sha256"] != protocol["geometry"]["weights_hash"]:
        raise ValueError("prepared channel weight profile differs from candidate")
    inputs = dict(manifest["inputs"])
    extra = {"candidate_protocol": protocol_path, "prepare_manifest": Path(prepared),
             "seed_exclusions": output / "preflight/seed-exclusions.npz",
             "planned_seeds": output / "preflight/planned-frame-seeds.npz",
             "seed_manifest": output / "preflight/manifest.json"}
    inputs.update({k: {"path": str(p.resolve()), "sha256": sha(p)} for k, p in extra.items()})
    sources = dict(manifest["source_artifacts"])
    for p in [Path(__file__), *[ROOT / "RFIsher/src/rfisher_results/validation" / n for n in ("channel29_controls.py", "tolerance.py", "coverage.py")]]:
        sources[str(p.resolve())] = {"sha256": sha(p)}
    plan = {
        "schema": "channel29-residual-controls-v1", "status": "plan_frozen",
        "frozen_at": now(), "protocol_sha256": PROTOCOL_SHA,
        "geometry": {"channel": 29, "num_streams": 2048, "K": 128,
                     "windows_per_stream": 128, "spectral_sense": "normal",
                     "input_scale": 3.299831645537222},
        "inputs": inputs, "source_artifacts": sources, "runtime": manifest["runtime"],
        "populations": POPULATIONS, "stages": STAGES,
        "audit": {"populations": [p["name"] for p in POPULATIONS], "frames_per_population": 1},
        "evaluation_prerequisite": {"receipt_path": str((output / "calibration-receipt.json").resolve())},
        "primary_cases": PRIMARY_CASES, "statistics": STATISTICS,
        "assignment": {"floor_linear": FLOOR_LINEAR, "shelf_conversion": SHELF_CONVERSION,
                       "maximum_possible_kept_shelf": maximum_kept_shelf(),
                       "all_kept_original_assignments_equal_floor": True},
        "policy": protocol["policy"],
        "scope": "Conditional digital realized retained-set nominal pre-quantization data-shelf mean relative to uncontaminated thermal power; not a post-filter visibility residual, physical calibration, survey population mean or future CHIME holdout.",
        "reference_model": "Primary cases have audited ATSC plus independent thermal noise, including ATSC's own reference leakage, but no extra reference tone. Stress cases add fixed gamma0.1 reference-projection power per ideal reference relative to uncontaminated expected thermal power; no truth renormalization.",
        "coordinate_model": "Reference-PFB output is already in normalized coordinates, so synthetic spectral_sense=normal. CHIME archive raw sense=-1 requires its recorded reversal; it is not applied twice here.",
        "stress_endpoint": "Three predeclared128-frame diagnostic controls outside the primary guarantee. Report retained truth versus original and calibrated bounds, including failures. Never refit or enlarge the primary bound from these outcomes.",
        "health_scope": "All synthetic frames counted; nonzero-reference validity enforced. Clipping measured but never used for posthoc sample deletion. No telescope health/map population is simulated.",
        "physical_calibration_qualified": False, "arms_telescope_confirmation": False,
    }
    plan["seed_partition"] = check_seed_partition(output, plan)
    if manifest["geometry"] != plan["geometry"]:
        raise ValueError("prepared geometry differs from planned controls")
    plan["plan_sha256"] = canonical_digest(plan, "plan_sha256")
    for p, record in sources.items():
        digest = record["sha256"] if isinstance(record, dict) else record
        if sha(p) != digest:
            raise ValueError(f"source changed before freeze: {p}")
        dest = output / "source_snapshots" / Path(p).relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, dest)
    write_new(output / "plan.json", plan)
    print(json.dumps({"plan_sha256": plan["plan_sha256"], "frozen_at": plan["frozen_at"], "seed_partition": plan["seed_partition"]}))


def load_plan(output):
    plan = read(output / "plan.json")
    if plan["schema"] != "channel29-residual-controls-v1" or plan["status"] != "plan_frozen" or plan["plan_sha256"] != canonical_digest(plan, "plan_sha256"):
        raise ValueError("plan identity mismatch")
    if plan["protocol_sha256"] != PROTOCOL_SHA or plan["statistics"] != STATISTICS or plan["populations"] != POPULATIONS or plan["stages"] != STAGES:
        raise ValueError("experiment changed")
    if plan["primary_cases"] != json.loads(json.dumps(PRIMARY_CASES)):
        raise ValueError("primary case family changed")
    for item in plan["inputs"].values():
        if sha(item["path"]) != item["sha256"]:
            raise ValueError(f"input changed: {item['path']}")
    for p, record in plan["source_artifacts"].items():
        digest = record["sha256"] if isinstance(record, dict) else record
        if sha(p) != digest:
            raise ValueError(f"source changed: {p}")
    check_seed_partition(output, plan)
    return plan


def load_stage(output, plan, stage):
    settings = plan["stages"][stage]
    definitions = {p["name"]: p for p in plan["populations"]}
    boundary = aware(plan["frozen_at"])
    if stage in ("evaluation", "stress"):
        receipt = load_receipt(output, plan)
        boundary = aware(receipt["frozen_at"])
    expected_paths = {output / stage / f"block-{b:04d}" / f"{name}.npz"
                      for b in range(settings["blocks"]) for name in settings["populations"]}
    if set((output / stage).glob("block-*/*.npz")) != expected_paths:
        raise ValueError("missing or unexpected prescribed shards")
    blocks, populations, identities = {}, {}, {}
    current_time = datetime.now(timezone.utc)
    for b in range(settings["blocks"]):
        block_rows = {}
        for name in settings["populations"]:
            path = output / stage / f"block-{b:04d}" / f"{name}.npz"
            definition = definitions[name]
            digest = sha(path)
            if path.with_suffix(".npz.sha256").read_text().strip() != digest:
                raise ValueError("generation shard digest mismatch")
            with np.load(path, allow_pickle=False) as z:
                meta = json.loads(str(z["meta_json"].item()))
                for k, value in (("plan_sha256", plan["plan_sha256"]), ("protocol_sha256", PROTOCOL_SHA), ("stage", stage), ("block_index", b), ("population", name), ("frames", definition["count_per_block"]), ("nominal_injected_data_shelf_db", definition["shelf_db"]), ("reference_projection_gamma", definition["reference_projection_gamma"])):
                    if meta[k] != value:
                        raise ValueError(f"shard identity changed: {k}")
                if meta["geometry"] != plan["geometry"] or meta["target_norm_sq"] != TARGET_NORM_SQ or meta["reference_norm_sum_sq"] != REFERENCE_NORM_SUM_SQ:
                    raise ValueError("shard detector geometry differs from plan")
                expected_truth = 0. if definition["shelf_db"] is None else 10.**(definition["shelf_db"]/10.)
                if meta["nominal_injected_data_shelf_linear"] != expected_truth:
                    raise ValueError("shard nominal injected truth differs")
                if aware(meta["started_utc"]) <= boundary or aware(meta["completed_utc"]) < aware(meta["started_utc"]):
                    raise ValueError("generation preceded its freeze boundary")
                if aware(meta["completed_utc"]) > current_time:
                    raise ValueError("generation completion is in the future")
                seeds = [frame_seed(PROTOCOL_SHA, stage, b, name, i) for i in range(definition["count_per_block"])]
                if z["frame_seed"].tolist() != seeds or z["frame_seed_effective63"].tolist() != [s % (1 << 63) for s in seeds]:
                    raise ValueError("frame seeds changed")
                if z["coarse_marginals_u64"].shape != (len(seeds), 3):
                    raise ValueError("frame count changed")
                block_rows[name] = population_measurement(z["coarse_marginals_u64"], shelf_db=definition["shelf_db"], clip_fraction=z["clip_fraction"])
            identities[str(path.relative_to(output))] = digest
        key = f"{stage}:{b:04d}"
        populations[key] = block_rows
        if stage != "stress":
            blocks[key] = assemble_cases(block_rows)
    return blocks, populations, identities


def load_receipt(output, plan):
    receipt = read(output / "calibration-receipt.json")
    if receipt["schema"] != "channel29-residual-calibration-receipt-v1" or receipt["status"] != "calibration_frozen" or receipt["plan_sha256"] != plan["plan_sha256"] or receipt["receipt_sha256"] != canonical_digest(receipt, "receipt_sha256"):
        raise ValueError("invalid calibration receipt")
    if sha(receipt["calibration"]["path"]) != receipt["calibration"]["sha256"]:
        raise ValueError("calibration outcome changed")
    if aware(receipt["frozen_at"]) <= aware(plan["frozen_at"]):
        raise ValueError("calibration receipt predates plan")
    if aware(receipt["frozen_at"]) > datetime.now(timezone.utc):
        raise ValueError("calibration receipt is in the future")
    calibration = read(receipt["calibration"]["path"])
    if calibration["schema"] != "channel29-digital-retained-set-bound-v1" or calibration["plan_sha256"] != plan["plan_sha256"]:
        raise ValueError("calibration payload belongs to another experiment")
    if calibration["source_shards"] != receipt["calibration_outputs"]:
        raise ValueError("calibration source identities differ from receipt")
    if not aware(plan["frozen_at"]) < aware(calibration["frozen_at"]) <= aware(receipt["frozen_at"]):
        raise ValueError("calibration payload timestamp is out of order")
    for relative, digest in receipt["calibration_outputs"].items():
        if sha(output / relative) != digest:
            raise ValueError("calibration source shard changed")
    return receipt


def fit(output):
    plan = load_plan(output)
    audit_path = output / "audit/device_audit.json"
    if audit_path.with_suffix(".json.sha256").read_text().strip() != sha(audit_path):
        raise ValueError("device audit digest mismatch")
    audit = read(audit_path)
    if audit["plan_sha256"] != plan["plan_sha256"] or audit["passed"] is not True or len(audit["rows"]) != 7:
        raise ValueError("complete passing device audit is required")
    blocks, populations, identities = load_stage(output, plan, "calibration")
    result = calibrate_joint_additive(blocks, content=.97, confidence=.95, min_retained=32)
    bound = {"schema": "channel29-digital-retained-set-bound-v1", "frozen_at": now(),
             "plan_sha256": plan["plan_sha256"], "calibration": result,
             "absolute_retained_set_upper": max(0., FLOOR_LINEAR + result["correction"]) if result["correction"] is not None else None,
             "populations": populations, "measurements": blocks,
             "source_shards": identities, "scope": plan["scope"],
             "physical_calibration_qualified": False, "arms_telescope_confirmation": False}
    path = output / "calibration.json"
    write_new(path, bound)
    receipt = {"schema": "channel29-residual-calibration-receipt-v1", "status": "calibration_frozen",
               "plan_sha256": plan["plan_sha256"], "frozen_at": now(),
               "calibration": {"path": str(path.resolve()), "sha256": sha(path)},
               "calibration_outputs": identities}
    receipt["receipt_sha256"] = canonical_digest(receipt, "receipt_sha256")
    write_new(output / "calibration-receipt.json", receipt)
    print(json.dumps({k: bound[k] for k in ("absolute_retained_set_upper", "frozen_at")}))
    print(json.dumps({k: result[k] for k in ("status", "correction", "order_rank", "achieved_confidence", "unsupported_blocks")}))


def evaluate(output):
    plan = load_plan(output)
    receipt = load_receipt(output, plan)
    bound = read(receipt["calibration"]["path"])
    blocks, populations, identities = load_stage(output, plan, "evaluation")
    if bound["calibration"]["status"] == "calibrated":
        result = evaluate_joint_additive(bound["calibration"], blocks)
        demonstrated = result["joint_success_probability_lower"] >= .95
    else:
        result = {"status": "no_finite_calibration", "trials": 100, "successes": 0, "failures": 100, "joint_success_probability_lower": 0.}
        demonstrated = False
    report = {"schema": "channel29-digital-retained-set-evaluation-v1", "completed_at": now(),
              "plan_sha256": plan["plan_sha256"], "receipt_sha256": receipt["receipt_sha256"],
              "evaluation": result, "evaluation_target": .95,
              "evaluation_target_demonstrated": demonstrated,
              "calibration_content": .97,
              "interpretation": "97% calibration content and95% evaluation target are separate; requested_content_demonstrated inside evaluation tests97%, not the primary95% target.",
              "populations": populations, "measurements": blocks, "source_shards": identities,
              "scope": plan["scope"], "physical_calibration_qualified": False, "arms_telescope_confirmation": False}
    write_new(output / "evaluation.json", report)
    print(json.dumps({"successes": result["successes"], "trials": result["trials"], "joint_lower": result["joint_success_probability_lower"], "target_demonstrated": demonstrated}))


def stress(output):
    plan = load_plan(output)
    receipt = load_receipt(output, plan)
    bound = read(receipt["calibration"]["path"])
    _, populations, identities = load_stage(output, plan, "stress")
    upper = bound["absolute_retained_set_upper"]
    rows = populations["stress:0000"]
    for row in rows.values():
        truth = row["truth_kept_mean"]
        row["original_floor_covers_kept_truth"] = truth <= FLOOR_LINEAR if truth is not None else None
        row["digital_primary_bound_covers_kept_truth"] = truth <= upper if truth is not None and upper is not None else None
        row["primary_guarantee_applies"] = False
    report = {"schema": "channel29-digital-reference-stress-v1", "completed_at": now(),
              "plan_sha256": plan["plan_sha256"], "receipt_sha256": receipt["receipt_sha256"],
              "absolute_primary_bound": upper, "populations": rows, "source_shards": identities,
              "scope": plan["stress_endpoint"], "bound_refit": False}
    write_new(output / "stress.json", report)
    print(json.dumps(rows))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("freeze", "verify", "fit", "evaluate", "stress"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prepared", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if args.stage == "freeze":
        if args.prepared is None:
            parser.error("freeze needs --prepared")
        freeze(output, args.prepared.resolve())
    elif args.stage == "verify":
        plan = load_plan(output)
        print(json.dumps({"plan_sha256": plan["plan_sha256"], "verified": True}))
    else:
        {"fit": fit, "evaluate": evaluate, "stress": stress}[args.stage](output)


if __name__ == "__main__":
    main()
