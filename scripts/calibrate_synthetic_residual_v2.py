#!/usr/bin/env python3
"""Versioned 300/200-block residual study with distinct calibration/eval targets.

Preserves the v1 study and tolerance arithmetic. All previous draws are
excluded. The generator is resumed only after checking existing prescribed
shards; no failed block, seed, case, or bound can be replaced or extended.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess

import numpy as np

_SPEC = importlib.util.spec_from_file_location("_residual_v1", Path(__file__).with_name("calibrate_synthetic_residual.py"))
_V1 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_V1)
sha = _V1.sha
CALIBRATION_SEEDS = tuple(range(20261001, 20261016))
EVALUATION_SEEDS = tuple(range(20261016, 20261026))
EFFECTIVE_SEED_MASK = (1 << 63) - 1


def now():
    return datetime.now(timezone.utc).isoformat()


def write_new(path, value):
    # Encode before creating a file, so a nonfinite value cannot leave a stub.
    content = json.dumps(value, indent=2, allow_nan=False) + "\n"
    with Path(path).open("x") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def write_pinned(path, value):
    write_new(path, value)
    with path.with_suffix(".sha256").open("x") as stream:
        stream.write(sha(path) + "\n")


def read_pinned(path):
    if sha(path) != path.with_suffix(".sha256").read_text().strip():
        raise ValueError(f"frozen document digest changed: {path}")
    return json.loads(path.read_text())


def frame_seed(seed, population, index, geometry):
    fields = [int(seed), "mask_frontier_frame", population,
              int(geometry["physical_channel"]),
              int(round(geometry["offset_fine_bins"] * 1_000_000)),
              int(geometry["num_streams"]), int(index)]
    payload = json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "little")


def population_counts(plan):
    return {"off": plan["blocks_per_seed"] * plan["off_frames_per_block"],
            "floor": plan["unused_floor_frames_per_seed"],
            **{"on_m" + str(abs(level)).replace(".", "p"):
               plan["blocks_per_seed"] * plan["on_frames_per_block"]
               for level in plan["shelves_db"]}}


def validate_seed_partition(plan):
    """Check actual raw and 63-bit generator seeds before producing any data."""
    raw, effective = set(), set()
    for name in plan["development_shards"]:
        with np.load(name, allow_pickle=False) as data:
            seeds = list(map(int, data["frame_seed"]))
        # Identical development observations may have archival copies, but
        # every one remains excluded from both prospective stages.
        raw.update(seeds)
        effective.update(seed & EFFECTIVE_SEED_MASK for seed in seeds)
    development_raw = len(raw)
    development_effective = len(effective)
    stage_counts = {}
    for stage in ("calibration", "evaluation"):
        count = 0
        for seed in plan[f"{stage}_seeds"]:
            for population, size in population_counts(plan).items():
                for index in range(size):
                    value = frame_seed(seed, population, index, plan["geometry"])
                    mapped = value & EFFECTIVE_SEED_MASK
                    if value in raw or mapped in effective:
                        raise ValueError("prescribed frame seed overlaps development or another planned frame (raw or effective63-bit)")
                    raw.add(value)
                    effective.add(mapped)
                    count += 1
        stage_counts[stage] = count
    return {"development_raw_seeds": development_raw,
            "development_effective_seeds": development_effective,
            "planned_frames_including_unused_floor": stage_counts,
            "effective_seed_mapping": "frame_seed & ((1<<63)-1)",
            "planned_raw_and_effective_disjoint": True}


def generator_runtime(executable):
    code = "import sys,json,numpy,cupy;print(json.dumps({'executable':sys.executable,'python':sys.version,'numpy':numpy.__version__,'cupy':cupy.__version__,'cuda_runtime':cupy.cuda.runtime.runtimeGetVersion()}))"
    return json.loads(subprocess.check_output([str(executable), "-c", code], text=True))


def freeze(output, prior, generator_python, *, input_iq=None, waveform_audit=None,
           waveform_evidence=None, additional_development=()):
    previous = prior / "residual"
    old = read_pinned(previous / "plan.json")
    old_bound = read_pinned(previous / "calibration.json")
    old_eval = json.loads((previous / "evaluation.json").read_text())
    if old_bound["plan_sha256"] != sha(previous / "plan.json") or old_eval["calibration_sha256"] != sha(previous / "calibration.json"):
        raise ValueError("previous study identities disagree")
    # Authenticate all previous raw shards, including its 90-per-stage unused
    # floor observations; the earlier frontier/follow-up are already listed.
    development = [Path(p) for p in old["development_shards"]]
    for stage in ("calibration", "evaluation"):
        expected = {str(previous / stage / f"seed-{seed}" / "frames" / (label + ".npz"))
                    for seed in old[f"{stage}_seeds"]
                    for label in ["off", "floor", *["on_m"+str(abs(x)).replace(".","p") for x in old["shelves_db"]]]}
        actual = {str(p) for p in (previous / stage).glob("seed-*/frames/*.npz")}
        if actual != expected:
            raise ValueError("previous generation has missing or unexpected shards")
        development.extend(Path(p) for p in sorted(actual))
    expected_old = {**old["inputs"], **old_bound["inputs"], **old_eval["inputs"]}
    for path in development:
        if str(path) not in expected_old or sha(path) != expected_old[str(path)]:
            raise ValueError(f"previous development shard changed: {path}")
    development.extend(Path(p).resolve() for p in additional_development)
    development = sorted(set(development))
    iq = Path(input_iq or old["input_iq"]).resolve()
    audit = Path(waveform_audit or old["waveform_audit"]).resolve()
    template_path = previous / "calibration" / f"seed-{old['calibration_seeds'][0]}" / "study_config.json"
    template = json.loads(template_path.read_text())
    # New waveform paths are explicit and content-pinned. They never rewrite
    # the identity or interpretation of any previous generator observation.
    template["inputs"].update(input_iq=str(iq), input_iq_sha256=sha(iq), waveform_audit_sha256=sha(audit))
    repo = Path(__file__).resolve().parents[1]
    files = [Path(p) for p in old["inputs"] if p.endswith(".py")]
    for path in files:
        if sha(path) != old["inputs"][str(path)]:
            raise ValueError(f"preserved generator/helper source changed: {path}")
    files += development + [previous / name for name in ["plan.json", "calibration.json", "evaluation.json"]]
    files += [template_path, iq, audit, Path(template["inputs"]["weights_path"]), Path(__file__).resolve(),
              repo / "scripts/calibrate_synthetic_residual.py",
              repo / "src/rfisher_results/validation/tolerance.py", repo / "src/rfisher_results/validation/coverage.py"]
    if waveform_evidence is not None:
        files.append(Path(waveform_evidence).resolve())
    executable = str(Path(generator_python).expanduser().absolute())
    plan = {"schema": "rfisher-digital-residual-tolerance-plan-v2",
            "frozen_utc": now(), "scope": old["scope"],
            "method": "Maximum of300 independent joint truth-minus-original-claim scores; fixed15-case family; unsupported scores are infinity and refuse a finite maximum. No padding, case deletion, seed replacement or evaluation-driven extension.",
            "calibration_content": .99, "calibration_confidence": .95,
            "evaluation_target": .95, "evaluation_confidence": .95,
            "calibration_blocks": 300, "evaluation_blocks": 200,
            "calibration_seeds": list(CALIBRATION_SEEDS), "evaluation_seeds": list(EVALUATION_SEEDS),
            "blocks_per_seed": 20, "off_frames_per_block": 75, "on_frames_per_block": 25,
            "unused_floor_frames_per_seed": 30, "minimum_retained": 30,
            "shelves_db": old["shelves_db"], "policies": old["policies"], "floor_linear": old["floor_linear"],
            "geometry": old["geometry"], "reference_directory": old["reference_directory"],
            "proxy_directory": old["proxy_directory"], "generator_python": executable,
            "generator_runtime": generator_runtime(executable),
            "generator_configuration_template": template,
            "input_iq": str(iq), "waveform_audit": str(audit),
            "waveform_evidence": str(Path(waveform_evidence).resolve()) if waveform_evidence else None,
            "previous_input_iq": old["input_iq"], "previous_waveform_audit": old["waveform_audit"],
            "independence_unit": old["independence_unit"], "null_scenario": old["null_scenario"],
            "evaluation_endpoint": "All15 cases supported and covered in each of200 disjoint evaluation blocks. The one-sided95% exact binomial lower joint success limit must be at least0.95 (196/200 successes, at most4 failures). Calibration-content0.99 is reported separately.",
            "development_shards": [str(p) for p in development],
            "inputs": {str(p): sha(p) for p in sorted(set(files))}}
    plan["seed_partition"] = validate_seed_partition(plan)
    validate_protocol(plan)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("a new study requires an empty output directory")
    output.mkdir(parents=True, exist_ok=True)
    write_pinned(output / "plan.json", plan)
    print("Frozen", output / "plan.json", sha(output / "plan.json"), flush=True)


def validate_protocol(plan):
    expected = {"schema": "rfisher-digital-residual-tolerance-plan-v2",
                "calibration_content": .99, "calibration_confidence": .95,
                "evaluation_target": .95, "evaluation_confidence": .95,
                "calibration_blocks": 300, "evaluation_blocks": 200,
                "blocks_per_seed": 20, "off_frames_per_block": 75,
                "on_frames_per_block": 25, "unused_floor_frames_per_seed": 30,
                "minimum_retained": 30, "calibration_seeds": list(CALIBRATION_SEEDS),
                "evaluation_seeds": list(EVALUATION_SEEDS), "shelves_db": [-10., -44., -50., -55.]}
    for key, value in expected.items():
        if plan.get(key) != value:
            raise ValueError(f"v2 protocol differs from the specified study: {key}")
    if plan["geometry"]["num_streams"] != 2048 or plan["geometry"]["reduced_geometry"]:
        raise ValueError("production2048-stream geometry required")
    if len(plan["policies"]) != 3 or not math.isfinite(plan["floor_linear"]) or plan["floor_linear"] < 0:
        raise ValueError("invalid frozen policies or floor")


def load_plan(output):
    plan = read_pinned(output / "plan.json")
    validate_protocol(plan)
    for name, expected in plan["inputs"].items():
        if sha(name) != expected:
            raise ValueError(f"frozen input changed: {name}")
    if validate_seed_partition(plan) != plan["seed_partition"]:
        raise ValueError("seed partition changed")
    return plan


def load_bound(output):
    bound = _V1.load_bound(output)
    if bound.get("schema") != "rfisher-digital-residual-calibration-v2":
        raise ValueError("not a v2 calibrated bound")
    calibration = bound["calibration"]
    if (calibration["content"], calibration["confidence"], calibration["calibration_blocks"], calibration["order_rank"]) != (.99, .95, 300, 300):
        raise ValueError("calibration contract changed")
    return bound


def expected_config(plan, seed):
    config = json.loads(json.dumps(plan["generator_configuration_template"]))
    config.pop("config_sha256", None)
    config["campaign"].update(seed=seed, frames_on=population_counts(plan)["on_m10p0"],
                              frames_off=population_counts(plan)["off"], frames_floor=population_counts(plan)["floor"])
    return config


def validate_config(path, plan, seed):
    config = json.loads(path.read_text())
    digest = config.pop("config_sha256")
    actual = hashlib.sha256(json.dumps(config, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if actual != digest:
        raise ValueError("generator configuration digest changed")
    expected = expected_config(plan, seed)
    for key in ("schema_version", "geometry", "calibration", "campaign", "policy", "inputs"):
        if config.get(key) != expected.get(key):
            raise ValueError(f"generator configuration changed: {key}")
    # The new freeze probes the actual numerical runtime. Platform descriptions
    # can vary without changing the explicitly pinned generator/software bytes.
    if config["software"]["numpy"] != plan["generator_runtime"]["numpy"]:
        raise ValueError("generator numpy runtime changed")
    if config["software"]["python"] != plan["generator_runtime"]["python"].split()[0]:
        raise ValueError("generator Python runtime changed")
    return digest


def audit_seed(directory, plan, seed, boundary, *, complete):
    expected = population_counts(plan)
    files = {p.stem: p for p in (directory / "frames").glob("*.npz")}
    if set(files)-set(expected) or (complete and set(files) != set(expected)):
        raise ValueError("missing or unexpected prescribed population shards")
    config_path = directory / "study_config.json"
    if not config_path.exists():
        if files or complete:
            raise ValueError("population shard has no generator configuration")
        return {}
    digest = validate_config(config_path, plan, seed)
    identities = {str(config_path): sha(config_path)}
    for label, path in sorted(files.items()):
        size = expected[label]
        with np.load(path, allow_pickle=False) as archive:
            arrays = {k: archive[k] for k in archive.files}
        shapes = {"required_multiplier_q16": (size, plan["geometry"]["bulk_size"]),
                  "fine_power_u64": (size, 3, plan["geometry"]["fine_bins"]),
                  "coarse_marginals_u64": (size, 3), "frame_seed": (size,),
                  "normalized_excess": (size,), "shelf_estimate_db": (size,), "clip_fraction": (size,), "meta_json": ()}
        if set(arrays) != set(shapes):
            raise ValueError("unexpected population array fields")
        for key, shape in shapes.items():
            if arrays[key].shape != shape:
                raise ValueError(f"population array shape changed: {key}")
        for key in ("required_multiplier_q16", "fine_power_u64", "coarse_marginals_u64", "frame_seed"):
            if arrays[key].dtype != np.dtype("uint64"):
                raise ValueError(f"population integer dtype changed: {key}")
        if not np.isfinite(arrays["clip_fraction"]).all() or np.any((arrays["clip_fraction"]<0) | (arrays["clip_fraction"]>1)):
            raise ValueError("invalid clipping fractions")
        if np.isinf(arrays["shelf_estimate_db"]).any() or not np.isfinite(arrays["normalized_excess"]).all():
            raise ValueError("invalid shelf/excess values")
        meta = json.loads(arrays["meta_json"].item())
        if meta["seed"] != seed or meta["population"] != label or meta["frames"] != size or meta["config_sha256"] != digest:
            raise ValueError("population metadata identity mismatch")
        if datetime.fromisoformat(meta["created_utc"]) <= boundary:
            raise ValueError("population was generated before its required freeze")
        for key in ("num_streams", "reduced_geometry", "physical_channel", "offset_fine_bins", "anchor_bin", "bulk_size"):
            if meta[key] != plan["geometry"][key]:
                raise ValueError(f"population geometry changed: {key}")
        expected_truth = 0. if label in ("off", "floor") else 10**(-float(label[4:].replace("p", "."))/10)
        if meta["injected_linear"] != expected_truth or meta["always_masked_sentinel"] != 0:
            raise ValueError("population injection/sentinel changed")
        prescribed = np.array([frame_seed(seed, label, i, plan["geometry"]) for i in range(size)], dtype=np.uint64)
        if not np.array_equal(arrays["frame_seed"], prescribed):
            raise ValueError("population does not contain the exact prescribed frame seeds")
        identities[str(path)] = sha(path)
    return identities


def verify_preserved(identities):
    for name, expected in identities.items():
        if sha(name) != expected:
            raise ValueError(f"previously recorded generation artifact changed: {name}")


def audit_stage(output, plan, stage, *, complete):
    if stage not in ("calibration", "evaluation"):
        raise ValueError("unknown stage")
    destination = output / stage
    allowed = {f"seed-{s}" for s in plan[f"{stage}_seeds"]}
    if {p.name for p in destination.glob("seed-*")}-allowed:
        raise ValueError("unexpected generation seed directory")
    boundary = datetime.fromisoformat(plan["frozen_utc"])
    if stage == "evaluation":
        boundary = datetime.fromisoformat(load_bound(output)["frozen_utc"])
    start_path = destination / "generation-start.json"
    if start_path.exists():
        start = read_pinned(start_path)
        expected_bound = sha(output/"calibration.json") if stage == "evaluation" else None
        if start["plan_sha256"] != sha(output/"plan.json") or start["calibration_sha256"] != expected_bound:
            raise ValueError("generation start belongs to another plan or bound")
        started = datetime.fromisoformat(start["started_utc"])
        if started < boundary:
            raise ValueError("generation began before its required freeze")
        boundary = started
    identities = {}
    for seed in plan[f"{stage}_seeds"]:
        identities.update(audit_seed(destination/f"seed-{seed}", plan, seed, boundary, complete=complete))
    # Hash receipts protect every previously recorded complete/partial shard.
    for path in sorted((destination/"attempts").glob("*.json")):
        record = read_pinned(path)
        if record["plan_sha256"] != sha(output/"plan.json") or record["stage"] != stage:
            raise ValueError("generation receipt belongs to another plan/stage")
        verify_preserved(record["artifacts"])
    return identities


def generator_command(output, plan, stage, seed):
    geometry, calibration = plan["geometry"], plan["generator_configuration_template"]["calibration"]
    counts = population_counts(plan)
    command = [plan["generator_python"], "tools/mask_residual_frontier.py", "--stage", "generate", "--gpu", "--resume",
               "--output-dir", str(output/stage/f"seed-{seed}"), "--input-iq", plan["input_iq"], "--waveform-audit", plan["waveform_audit"],
               "--shelf-snr-db", *map(str, plan["shelves_db"]), "--duty-cycle", ".25", "--rho", "62", "--seed", str(seed)]
    settings = {"num-streams": geometry["num_streams"], "physical-channel": geometry["physical_channel"],
                "offset-fine-bins": geometry["offset_fine_bins"], "input-scale": geometry["input_scale"],
                "designated-half-width": geometry["designated_half_width"], "guard-fine-bins": geometry["guard_fine_bins"],
                "spectral-sense": geometry["spectral_sense"], "frames-on": counts["on_m10p0"], "frames-off": counts["off"], "frames-floor": counts["floor"],
                "weights-path": plan["generator_configuration_template"]["inputs"]["weights_path"],
                "iq-sample-rate-hz": plan["generator_configuration_template"]["inputs"]["iq_sample_rate_hz"],
                "pilot-below-data-db": calibration["pilot_below_data_db"], "bin-enbw-hz": calibration["bin_enbw_hz"],
                "dtv-bandwidth-hz": calibration["dtv_bandwidth_hz"], "pilot-capture-efficiency": calibration["pilot_capture_efficiency"]}
    for key, value in settings.items():
        command.extend(["--"+key, str(value)])
    return command


def record_attempt(destination, plan_hash, stage, event, identities, **extra):
    directory = destination / "attempts"
    directory.mkdir(exist_ok=True)
    number = len(list(directory.glob("*.json"))) + 1
    write_pinned(directory / f"{number:04d}-{event}.json", {
        "schema": "rfisher-residual-generation-receipt-v2", "recorded_utc": now(),
        "plan_sha256": plan_hash, "stage": stage, "event": event,
        "artifacts": identities, **extra})


def generate(output, stage, *, resume=False):
    plan = load_plan(output)
    if stage == "calibration" and (output/"calibration.json").exists():
        raise ValueError("calibration is already frozen; generation cannot continue")
    bound = load_bound(output) if stage == "evaluation" else None
    if generator_runtime(plan["generator_python"]) != plan["generator_runtime"]:
        raise ValueError("generator runtime changed since freeze")
    destination = output / stage
    plan_hash = sha(output/"plan.json")
    bound_hash = sha(output/"calibration.json") if bound else None
    if destination.exists():
        if not resume:
            raise FileExistsError("existing generation requires explicit --resume")
        start = read_pinned(destination/"generation-start.json")
        if start["plan_sha256"] != plan_hash or start["calibration_sha256"] != bound_hash:
            raise ValueError("generation started under a different plan or bound")
    else:
        destination.mkdir()
        write_pinned(destination/"generation-start.json", {"started_utc": now(), "plan_sha256": plan_hash, "calibration_sha256": bound_hash})
    existing = audit_stage(output, plan, stage, complete=False)
    record_attempt(destination, plan_hash, stage, "start", existing, resume=resume)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(plan["proxy_directory"])/"src")
    boundary = datetime.fromisoformat(bound["frozen_utc"] if bound else plan["frozen_utc"])
    try:
        for seed in plan[f"{stage}_seeds"]:
            directory = destination/f"seed-{seed}"
            present = set(p.stem for p in (directory/"frames").glob("*.npz"))
            if present == set(population_counts(plan)):
                print("Verified complete seed, skipped", seed, flush=True)
                continue
            command = generator_command(output, plan, stage, seed)
            print("RUN", " ".join(command), flush=True)
            subprocess.run(command, cwd=plan["proxy_directory"], env=env, check=True)
            verify_preserved(existing)
            updated = audit_seed(directory, plan, seed, boundary, complete=True)
            existing.update(updated)
            record_attempt(destination, plan_hash, stage, "seed-complete", updated, seed=seed)
    except BaseException as error:
        # Preserve complete shards left by an interrupted generator. An invalid
        # partial NPZ is refused; this workflow never deletes/replaces it.
        try:
            partial = audit_stage(output, plan, stage, complete=False)
            record_attempt(destination, plan_hash, stage, "interrupted", partial, error_type=type(error).__name__)
        except Exception as audit_error:
            record_attempt(destination, plan_hash, stage, "interrupted-invalid", existing,
                           error_type=type(error).__name__, audit_error_type=type(audit_error).__name__)
        raise
    identities = audit_stage(output, plan, stage, complete=True)
    verify_preserved(existing)
    completed = destination/"generation-complete.json"
    if completed.exists():
        old = read_pinned(completed)
        if old["artifacts"] != identities or old["plan_sha256"] != plan_hash or old["calibration_sha256"] != bound_hash:
            raise ValueError("completed generation changed")
    else:
        write_pinned(completed, {"finished_utc": now(), "plan_sha256": plan_hash, "calibration_sha256": bound_hash, "artifacts": identities})
    print("Verified generation complete", stage, flush=True)


def completed_inputs(output, plan, stage):
    complete_path = output/stage/"generation-complete.json"
    result = read_pinned(complete_path)
    if result["plan_sha256"] != sha(output/"plan.json"):
        raise ValueError("generation completion belongs to another plan")
    expected_bound = sha(output/"calibration.json") if stage == "evaluation" else None
    if result["calibration_sha256"] != expected_bound:
        raise ValueError("generation completion belongs to another bound")
    identities = audit_stage(output, plan, stage, complete=True)
    if result["artifacts"] != identities:
        raise ValueError("completed generation artifact set changed")
    return {**identities, str(complete_path): sha(complete_path),
            str(output/stage/"generation-start.json"): sha(output/stage/"generation-start.json")}


def fit(output):
    from rfisher_results.validation.tolerance import calibrate_joint_additive

    if (output/"evaluation").exists():
        raise ValueError("evaluation already exists before calibration freeze")
    plan = load_plan(output)
    identities = completed_inputs(output, plan, "calibration")
    blocks, _ = _V1.read_blocks(output, "calibration", plan)
    if len(blocks) != plan["calibration_blocks"]:
        raise ValueError("calibration block count changed")
    calibration = calibrate_joint_additive(blocks, content=plan["calibration_content"],
                                           confidence=plan["calibration_confidence"], min_retained=plan["minimum_retained"])
    if calibration["order_rank"] != 300:
        raise ValueError("calibration no longer uses the predeclared maximum")
    write_pinned(output/"calibration.json", {"schema": "rfisher-digital-residual-calibration-v2",
                 "frozen_utc": now(), "plan_sha256": sha(output/"plan.json"), "scope": plan["scope"],
                 "calibration": calibration, "inputs": identities})
    print("Frozen calibration", calibration["status"], calibration["correction"], flush=True)


def separate_evaluation_endpoint(evaluation, plan):
    """Keep the inherited 0.99 field truthful and name the separate0.95 target."""
    if evaluation["content"] != plan["calibration_content"] or evaluation["confidence"] != plan["evaluation_confidence"]:
        raise ValueError("inherited evaluator contract changed")
    return {"evaluation_target": plan["evaluation_target"], "evaluation_confidence": plan["evaluation_confidence"],
            "evaluation_target_demonstrated": evaluation["joint_success_probability_lower"] >= plan["evaluation_target"],
            "calibration_content": plan["calibration_content"],
            "calibration_content_demonstrated_in_evaluation": evaluation["requested_content_demonstrated"],
            "interpretation": "The inherited evaluation.requested_content_demonstrated tests calibration content0.99; the prospective primary evaluation_target_demonstrated tests the separately frozen0.95 target."}


def evaluate(output):
    from rfisher_results.validation.tolerance import evaluate_joint_additive

    plan, bound = load_plan(output), load_bound(output)
    identities = completed_inputs(output, plan, "evaluation")
    blocks, _ = _V1.read_blocks(output, "evaluation", plan)
    if len(blocks) != plan["evaluation_blocks"]:
        raise ValueError("evaluation block count changed")
    evaluation = evaluate_joint_additive(bound["calibration"], blocks)
    endpoint = separate_evaluation_endpoint(evaluation, plan)
    write_pinned(output/"evaluation.json", {"schema": "rfisher-digital-residual-evaluation-v2",
                 "evaluated_utc": now(), "plan_sha256": sha(output/"plan.json"),
                 "calibration_sha256": sha(output/"calibration.json"), "scope": plan["scope"],
                 **endpoint, "evaluation": evaluation, "inputs": identities})
    print(json.dumps(endpoint), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["freeze", "generate-calibration", "fit", "generate-evaluation", "evaluate"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prior-release", type=Path)
    parser.add_argument("--generator-python", type=Path)
    parser.add_argument("--input-iq", type=Path)
    parser.add_argument("--waveform-audit", type=Path)
    parser.add_argument("--waveform-evidence", type=Path)
    parser.add_argument("--additional-development-shard", type=Path, action="append", default=[])
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    if args.stage == "freeze":
        if args.prior_release is None or args.generator_python is None:
            parser.error("freeze requires --prior-release and --generator-python")
        freeze(output, args.prior_release.resolve(), args.generator_python,
               input_iq=args.input_iq, waveform_audit=args.waveform_audit,
               waveform_evidence=args.waveform_evidence, additional_development=args.additional_development_shard)
    elif args.stage.startswith("generate-"):
        generate(output, args.stage.removeprefix("generate-"), resume=args.resume)
    elif args.stage == "fit":
        fit(output)
    else:
        evaluate(output)


if __name__ == "__main__":
    main()
