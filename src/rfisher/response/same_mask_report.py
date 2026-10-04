"""Fixed-budget synthetic study, authenticated reports and offline revalidation."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import platform
import sys

import numpy as np
import scipy
from scipy.stats import beta

from . import same_mask as sm
from . import visibility

SCHEMA = "rfisher_same_mask_synthetic_v1"


class InferenceRefused(ValueError):
    """Retain bootstrap accounting even when its inference is unavailable."""
    def __init__(self, reason, accounting):
        super().__init__(reason)
        self.accounting = accounting


def environment():
    return {"numpy": np.__version__, "scipy": scipy.__version__,
            "python_implementation": platform.python_implementation(),
            "python_major_minor": list(sys.version_info[:2])}


def settings():
    return {"sizes": {str(k): v for k, v in sm.SIZES.items()},
            "replicates": sm.REPLICATES, "bootstrap_resamples": sm.BOOTSTRAPS,
            "threshold_words": list(map(str, sm.WORDS)), "steps": list(sm.STEPS),
            "frames_per_block": sm.FRAME_COUNT, "block_seconds": sm.BLOCK_SECONDS,
            "reference_blocks": sm.REFERENCE_BLOCKS, "minimum_support": sm.MIN_SUPPORT,
            "generator_chunk_blocks": 128}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def plain(value):
    if isinstance(value, np.ndarray):
        return plain(value.tolist())
    if isinstance(value, (complex, np.complexfloating)):
        return {"real": float(value.real), "imaginary": float(value.imag)}
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [plain(v) for v in value]
    if isinstance(value, np.generic):
        return plain(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        raise ValueError("nonfinite report value; give the result an explicit refusal")
    return value


def encoded(value):
    return json.dumps(plain(value), sort_keys=True, indent=2, allow_nan=False) + "\n"


def sources():
    from rfisher import cli
    modules = (sm, visibility, cli)
    files = {"same_mask_report.py": Path(__file__),
             **{Path(module.__file__).name: Path(module.__file__) for module in modules}}
    return {name: digest(path) for name, path in files.items()}


def bootstrap_calibration(data, reference, point, included):
    generators = [sm.rng(60, scenario, 20000) for scenario in range(3)]
    ref_generator = sm.rng(60, 99, 21000)
    samples, failures = [], Counter()
    for _ in range(sm.BOOTSTRAPS):
        boot = [sm.resample(value, generator) for value, generator in zip(data, generators)]
        boot_reference = sm.resample(reference, ref_generator)
        try:
            target = sm.reference_variance(boot_reference)
            samples.append(np.concatenate([
                sm.coordinates(sm.estimate(boot[scenario], index, diagnostics=False), target)
                for scenario, index in included]))
        except ValueError as exc:
            failures[str(exc).split(":")[0]] += 1
    accounting = {"requested": sm.BOOTSTRAPS, "usable": len(samples), "refusal_counts": dict(failures)}
    try:
        low, high, critical = sm.simultaneous_bounds(point, samples)
    except ValueError as exc:
        raise InferenceRefused(str(exc), accounting) from exc
    return low, high, dict(accounting, critical_value=critical)


def calibrate(data, reference):
    try:
        target = sm.reference_variance(reference)
    except ValueError as exc:
        rows = [[{"index": i, "eta_q16": str(word), "threshold_kind": "finite",
                  "status": "reference_refused", "reason": str(exc)} for i, word in enumerate(sm.WORDS)]
                + [{"index": len(sm.WORDS), "threshold_kind": "reject_all", "eta_q16": None,
                    "status": "no_science_information", "time_point_blocks": None}]
                for _ in range(3)]
        return {"target_variance": None, "reference_exposure_blocks": sm.REFERENCE_BLOCKS,
                "rows": rows, "bootstrap": {"status": "reference_refused", "reason": str(exc)},
                "selections": [sm.select(group) for group in rows]}
    rows, included, vector = [], [], []
    for scenario, value in enumerate(data):
        group = []
        for index, word in enumerate(sm.WORDS):
            row = {"index": index, "eta_q16": str(word), "threshold_kind": "finite"}
            try:
                estimate = sm.estimate(value, index)
                coord = sm.coordinates(estimate, target)
                row.update(status="supported_point", estimate=estimate,
                           point_coordinates=coord, time_point_blocks=int(np.ceil(coord[2])),
                           naive_uniform_time_blocks=sm.REFERENCE_BLOCKS/estimate["retained_frame_fraction"])
                for alternative in ("gaussian_closure", "frozen_mask"):
                    alt = estimate[alternative]
                    if alt["status"] != "refused":
                        try:
                            alt["coordinates"] = sm.coordinates(alt, target)
                        except ValueError as exc:
                            estimate[alternative] = {"status": "refused", "reason": str(exc)}
                included.append((scenario, index))
                vector.extend(coord)
            except ValueError as exc:
                row.update(status="point_refused", reason=str(exc))
            group.append(row)
        group.append({"index": len(sm.WORDS), "threshold_kind": "reject_all",
                      "eta_q16": None, "status": "no_science_information",
                      "time_point_blocks": None, "reason": "zero retained samples; no finite observing time"})
        rows.append(group)
    bootstrap = {"status": "no_supported_points"}
    if included:
        try:
            lower, upper, bootstrap = bootstrap_calibration(data, reference, np.asarray(vector), included)
            bootstrap["status"] = "computed"
            for position, (scenario, index) in enumerate(included):
                low, high = lower[3*position:3*position+3], upper[3*position:3*position+3]
                row = rows[scenario][index]
                row.update(bias_ratio_lower=low[:2], bias_ratio_upper=high[:2],
                           time_lower_blocks=max(0., float(low[2])), time_upper_blocks=float(high[2]))
                row["status"] = ("calibration_feasible" if np.all(np.maximum(abs(low[:2]), abs(high[:2])) <= 1)
                                 else "bias_requirement_unresolved_or_failed")
        except ValueError as exc:
            bootstrap = {"status": "refused", "reason": str(exc),
                         **getattr(exc, "accounting", {})}
            for scenario, index in included:
                rows[scenario][index]["status"] = "uncertainty_refused"
    return {"target_variance": target, "reference_exposure_blocks": sm.REFERENCE_BLOCKS,
            "rows": rows, "bootstrap": bootstrap,
            "selections": [sm.select(group) for group in rows]}


def fixed_coordinates(data, index, response, target):
    clean = sm.statistics(abs(data["clean"][:, index])**2)
    observed = sm.statistics(abs(data["observed"][:, index])**2)
    bias = response @ (observed["mean"]-clean["mean"])
    covariance = response @ observed["wall_covariance"] @ response.T
    values = np.r_[bias[:2]/np.sqrt(target[:2]), np.diag(covariance)[:2]/target[:2]]
    if not np.isfinite(values).all():
        raise ValueError("nonfinite fixed-response metric")
    return values


def fixed_interval(data, index, response, target, stage, scenario, replicate=0, *, rng_factory=None):
    point = fixed_coordinates(data, index, response, target)
    generator = (sm.rng if rng_factory is None else rng_factory)(60, scenario, 1000*stage+replicate)
    samples, failures = [], Counter()
    for _ in range(sm.BOOTSTRAPS):
        try:
            samples.append(fixed_coordinates(sm.resample(data, generator), index, response, target))
        except ValueError as exc:
            failures[str(exc).split(":")[0]] += 1
    accounting = {"requested_resamples": sm.BOOTSTRAPS, "usable_resamples": len(samples),
                  "resample_refusals": dict(failures)}
    try:
        low, high, critical = sm.simultaneous_bounds(point, samples)
    except ValueError as exc:
        raise InferenceRefused(str(exc), accounting) from exc
    return dict(accounting, point=point, lower=low, upper=high, critical_value=critical)


def evaluation_status(interval, blocks):
    if blocks < 512:
        return "unsupported_small_exposure"
    if blocks > 8192:
        return "extrapolated_exposure_model_only"
    if np.any(np.maximum(abs(interval["lower"][:2]), abs(interval["upper"][:2])) > 1):
        return "bias_requirement_unresolved_or_failed"
    if np.any(interval["upper"][2:] > blocks):
        return "precision_requirement_unresolved_or_failed"
    return "requirements_met_conditionally"


def binomial_interval(successes, trials):
    if not 0 <= successes <= trials or trials <= 0:
        raise ValueError("invalid coverage count")
    return [0. if successes == 0 else float(beta.ppf(.025, successes, trials-successes+1)),
            1. if successes == trials else float(beta.ppf(.975, successes+1, trials-successes))]


def containment(interval, reference):
    lo, hi = np.asarray(interval["lower"]), np.asarray(interval["upper"])
    point = np.asarray(reference["point"])
    ref_lo, ref_hi = np.asarray(reference["lower"]), np.asarray(reference["upper"])
    return {"center": bool(np.all((lo <= point) & (point <= hi))),
            "entire_reference_rectangle": bool(np.all((lo <= ref_lo) & (ref_hi <= hi))),
            "intersects_reference_rectangle": bool(np.all((lo <= ref_hi) & (ref_lo <= hi)))}


def evaluate(calibration, load, *, interval_factory=None):
    interval_factory = fixed_interval if interval_factory is None else interval_factory
    target = np.asarray(calibration["target_variance"])
    results = []
    for scenario, selected in enumerate(calibration["selections"]):
        grid = []
        observed = load(30, scenario)
        for row in calibration["rows"][scenario]:
            diagnostic = {"index": row["index"], "threshold_kind": row["threshold_kind"],
                          "eta_q16": row["eta_q16"], "status": "calibration_response_unavailable"}
            if row["threshold_kind"] == "reject_all":
                diagnostic["status"] = "no_science_information"
            elif "estimate" in row:
                try:
                    response = np.asarray(row["estimate"]["response"])
                    diagnostic.update(status="fixed_response_point_diagnostic_only",
                                      coordinates=fixed_coordinates(observed, row["index"], response, target))
                except ValueError as exc:
                    diagnostic.update(status="evaluation_support_refused", reason=str(exc))
            grid.append(diagnostic)
        index = selected["selected_index"]
        if index is None:
            results.append({"status": "not_evaluated_no_frozen_candidate", "selected_index": None,
                            "fixed_grid_diagnostics": grid})
            continue
        response = np.asarray(calibration["rows"][scenario][index]["estimate"]["response"])
        result = {"selected_index": index, "validation_time_blocks": selected["validation_time_blocks"],
                  "fixed_grid_diagnostics": grid,
                  "coverage_condition": "frozen response, target, policy and realized shared reference center"}
        try:
            interval = interval_factory(load(30, scenario), index, response, target, 30, scenario)
            result.update(interval=interval, status=evaluation_status(interval, selected["validation_time_blocks"]))
        except ValueError as exc:
            result.update(status="evaluation_refused", reason=str(exc),
                          bootstrap_accounting=getattr(exc, "accounting", {}))
        try:
            reference = interval_factory(load(40, scenario), index, response, target, 40, scenario)
            result["reference_interval"] = reference
        except ValueError as exc:
            result.update(coverage_status="reference_refused", coverage_reason=str(exc),
                          reference_bootstrap_accounting=getattr(exc, "accounting", {}))
            results.append(result)
            continue
        coverage, failures = [], Counter()
        for replicate in range(sm.REPLICATES):
            try:
                interval = interval_factory(load(50, scenario, replicate), index, response, target,
                                          50, scenario, replicate)
                coverage.append({"replicate": replicate, "status": "computed", "interval": interval,
                                 **containment(interval, reference)})
            except ValueError as exc:
                failures[str(exc).split(":")[0]] += 1
                coverage.append({"replicate": replicate, "status": "refused", "reason": str(exc),
                                 "bootstrap_accounting": getattr(exc, "accounting", {}),
                                 "center": False, "entire_reference_rectangle": False,
                                 "intersects_reference_rectangle": False})
        count = sum(row["center"] for row in coverage)
        bounds = binomial_interval(count, sm.REPLICATES)
        result.update(coverage_replicates=coverage, coverage_refusals=dict(failures),
                      reference_center_containment=count,
                      definite_reference_region_containment=sum(row["entire_reference_rectangle"] for row in coverage),
                      possible_reference_region_containment=sum(row["intersects_reference_rectangle"] for row in coverage),
                      conditional_binomial_interval=bounds,
                      coverage_status=("diagnostic_target_not_excluded" if not failures and bounds[0] <= .95 <= bounds[1]
                                       else "coverage_unresolved_or_failed"))
        result["conditional_validation"] = (result["status"] == "requirements_met_conditionally"
                                            and result["coverage_status"] == "diagnostic_target_not_excluded")
        results.append(result)
    return results


def block_name(stage, scenario, replicate=0):
    return f"blocks/stage{stage}_scenario{scenario}_replicate{replicate}.npz"


def load_blocks(root, stage, scenario, replicate=0):
    with np.load(root / block_name(stage, scenario, replicate), allow_pickle=False) as archive:
        data = {key: archive[key] for key in archive.files}
    n, k = sm.SIZES[stage], 1 if stage == 21 else len(sm.WORDS)
    shapes = {"kept": (n, k), "clean": (n, k, 3), "observed": (n, k, 3)}
    if stage in (20, 21):
        shapes.update({name: (n, 2, 3, 2, k, 3) for name in
                       ("injected_clean", "injected_observed", "frozen_observed")})
    if set(data) != set(shapes) or any(data[key].shape != shape for key, shape in shapes.items()):
        raise ValueError("saved stage summary shape/field mismatch")
    kept = data["kept"]
    if kept.dtype.kind not in "iu" or ((kept < 0) | (kept > sm.FRAME_COUNT)).any():
        raise ValueError("invalid saved frame support")
    for key in ("clean", "observed"):
        if data[key].dtype.kind != "c" or np.isinf(data[key]).any():
            raise ValueError("invalid saved complex endpoint")
        finite = np.isfinite(data[key])
        if not np.array_equal(finite, np.repeat((kept >= 2)[..., None], 3, axis=2)):
            raise ValueError("saved endpoint validity disagrees with joint support")
    for key in set(data)-{"clean", "observed", "kept"}:
        finite = np.isfinite(data[key])
        if data[key].dtype.kind != "f" or np.isinf(data[key]).any() or np.any(finite != finite[..., :1]) or np.any(data[key][finite] < 0):
            raise ValueError("invalid saved injected moment")
    return data


def result(calibration, evaluations):
    return {"schema": SCHEMA, "scope": "score-level synthetic; local theta=0; no physical channel ruling",
            "physical_response_qualified": False, "unconditional_optimum_coverage_claimed": False,
            "protocol_sha256": sm.PROTOCOL_SHA256, "calibration": calibration, "evaluation": evaluations}


def product_texts(outcome):
    columns = ("scenario", "threshold_kind", "eta_q16", "status", "reason", "time_point_blocks",
               "time_lower_blocks", "time_upper_blocks", "valid_blocks", "valid_block_fraction",
               "retained_frame_fraction", "naive_uniform_time_blocks")
    with io.StringIO(newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for scenario, group in zip(sm.SCENARIOS, outcome["calibration"]["rows"]):
            for row in group:
                values = dict(row, **{k: v for k, v in row.get("estimate", {}).items() if k in columns})
                writer.writerow({key: values.get(key, scenario if key == "scenario" else "") for key in columns})
        table = handle.getvalue()
    lines = ["SAME-MASK SYNTHETIC SCIENCE BRIDGE", "",
             "Score-level synthetic study; not a telescope or physical BAO result.",
             "Observed score only; same-support clean counterfactual is a simulation diagnostic, not cleaning.",
             "Full recomputed-mask observed injection response is primary; all three parameters are fitted.",
             "Empirical fourth moments and valid-block probability price wall-clock exposure.",
             "Targets: clean 1,024-block reference; no observing-time cap; no automatic knee.",
             "Calibration minimizes whole 10-second blocks; continuous ratios remain diagnostic.",
             "Independent evaluation cannot reselect. Uncertain order remains unresolved.",
             "Coverage conditions on the frozen response, target, policy and realized shared reference center.",
             "No unconditional coverage of a selected optimum or physical Jacobian is claimed.", ""]
    for scenario, selection, evaluation in zip(sm.SCENARIOS, outcome["calibration"]["selections"], outcome["evaluation"]):
        lines.extend([scenario, f"  Calibration: {selection['status']}; selected index: {selection['selected_index']}.",
                      f"  Independent evaluation: {evaluation['status']}."])
        if selection["selected_index"] is not None:
            lines.append(f"  Point minimum: {selection['point_minimum_blocks']} blocks; frozen validation time: "
                         f"{selection['validation_time_blocks']} blocks ({10*selection['validation_time_blocks']} synthetic seconds).")
            lines.append(f"  Coverage: {evaluation.get('coverage_status', 'unavailable')}; "
                         f"center containment {evaluation.get('reference_center_containment', 'unavailable')}/{sm.REPLICATES}.")
        lines.append("")
    lines.append("All refusals and approximation differences remain in result.json and candidates.csv. No new trials follow a failure.")
    return {"result.json": encoded(outcome), "candidates.csv": table, "REPORT.txt": "\n".join(lines)+"\n"}


def products(root, outcome):
    for name, content in product_texts(outcome).items():
        (root / name).write_text(content, encoding="utf-8", newline="")


def expected_files():
    files = {"PROTOCOL.md", "run_identity.json", "calibration.json", "result.json", "candidates.csv", "REPORT.txt"}
    for stage in (10, 20, 21, 30, 40, 50):
        for scenario in (range(1) if stage == 21 else range(3)):
            for replicate in (range(sm.REPLICATES) if stage == 50 else range(1)):
                files.add(block_name(stage, scenario, replicate))
    return files


def run(root, protocol):
    root, protocol = Path(root), Path(protocol)
    if digest(protocol) != sm.PROTOCOL_SHA256:
        raise ValueError("protocol differs from the reviewed pre-trial protocol")
    if root.exists():
        raise ValueError("output directory must be new")
    source_hashes = sources()
    root.mkdir(parents=True)
    (root / "blocks").mkdir()
    (root / "PROTOCOL.md").write_bytes(protocol.read_bytes())
    (root / "run_identity.json").write_text(encoded({"schema": SCHEMA, "sources": source_hashes,
                                                     "settings": settings(), "environment": environment(),
                                                     "protocol_sha256": sm.PROTOCOL_SHA256}))
    for stage in (10, 20, 21, 30, 40, 50):
        for scenario in (range(1) if stage == 21 else range(3)):
            for replicate in (range(sm.REPLICATES) if stage == 50 else range(1)):
                value = sm.generate(stage, scenario, replicate, injections=stage in (20, 21),
                                    words=(sm.WORDS[-1],) if stage == 21 else sm.WORDS)
                np.savez_compressed(root / block_name(stage, scenario, replicate), **value)
        print(f"saved fixed stage {stage}", flush=True)
        if stage == 21:
            calibration = calibrate([load_blocks(root, 20, s) for s in range(3)], load_blocks(root, 21, 0))
            (root / "calibration.json").write_text(encoded(calibration), encoding="utf-8")
            print("calibration selection frozen before independent evaluation", flush=True)
    evaluations = evaluate(calibration, lambda stage, scenario, replicate=0: load_blocks(root, stage, scenario, replicate))
    outcome = result(calibration, evaluations)
    products(root, outcome)
    if sources() != source_hashes or digest(protocol) != sm.PROTOCOL_SHA256:
        raise ValueError("source/protocol changed during trial; output remains incomplete")
    files = {path.relative_to(root).as_posix(): digest(path) for path in sorted(root.rglob("*")) if path.is_file()}
    manifest = {"schema": SCHEMA, "sources": source_hashes, "protocol_sha256": sm.PROTOCOL_SHA256,
                "files_sha256": files, "environment": environment(), "settings": settings(), "complete": True}
    (root / "manifest.json").write_text(encoded(manifest), encoding="utf-8")
    return outcome


def validate(root):
    root = Path(root)
    manifest = json.loads((root / "manifest.json").read_text())
    if (manifest.get("schema") != SCHEMA or manifest.get("complete") is not True
            or manifest.get("sources") != sources() or manifest.get("protocol_sha256") != sm.PROTOCOL_SHA256):
        raise ValueError("study identity or source provenance mismatch")
    if manifest.get("environment") != environment() or manifest.get("settings") != settings():
        raise ValueError("study numerical environment or fixed settings mismatch")
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()} - {"manifest.json"}
    if set(manifest.get("files_sha256", {})) != expected_files() or actual != expected_files():
        raise ValueError("study artifact inventory mismatch")
    for name, expected in manifest["files_sha256"].items():
        path = root / name
        if Path(name).is_absolute() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("artifact path escapes study")
        if digest(path) != expected:
            raise ValueError(f"artifact hash mismatch: {name}")
    if digest(root / "PROTOCOL.md") != sm.PROTOCOL_SHA256:
        raise ValueError("saved protocol mismatch")
    calibration = calibrate([load_blocks(root, 20, s) for s in range(3)], load_blocks(root, 21, 0))
    if plain(calibration) != json.loads((root / "calibration.json").read_text()):
        raise ValueError("saved calibration differs from independent reconstruction")
    evaluations = evaluate(calibration, lambda stage, scenario, replicate=0: load_blocks(root, stage, scenario, replicate))
    reconstructed = result(calibration, evaluations)
    for name, content in product_texts(reconstructed).items():
        if (root / name).read_bytes() != content.encode("utf-8"):
            raise ValueError(f"saved product differs from independent reconstruction: {name}")
    for name, expected in manifest["files_sha256"].items():
        if digest(root / name) != expected:
            raise ValueError("artifact changed during revalidation")
    if manifest["sources"] != sources():
        raise ValueError("source changed during revalidation")
    return reconstructed


def main(argv=None, prog="rfisher response same-mask"):
    parser = argparse.ArgumentParser(prog=prog, description=__doc__.split("\n")[0])
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--out", type=Path, help="new directory for the fixed-budget trial")
    action.add_argument("--validate", type=Path, help="authenticate and reconstruct saved outcomes without new trials")
    parser.add_argument("--protocol", type=Path, help="reviewed pre-trial protocol (required with --out)")
    args = parser.parse_args(argv)
    if args.out and args.protocol is None:
        parser.error("--out requires --protocol")
    if args.validate and args.protocol is not None:
        parser.error("--validate uses the saved protocol")
    try:
        outcome = validate(args.validate) if args.validate else run(args.out, args.protocol)
    except (ValueError, OSError, KeyError) as exc:
        parser.error(str(exc))
    print(encoded({"schema": outcome["schema"], "physical_response_qualified": False,
                   "selections": outcome["calibration"]["selections"]}))
    return 0
