"""One fixed candidate-specific synthetic study with refusal-preserving inference."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from functools import partial
import io
import json
from pathlib import Path

import numpy as np
from scipy.stats import binom

from . import same_mask as sm
from . import same_mask_report as base

SCHEMA = "rfisher_same_mask_candidatewise_v1"
PROTOCOL_SHA256 = "e4fe585d16567081f55a43bfbab63db4d9634b680456606834e87a3ab50a9299"
HISTORICAL_COMMIT = "185e033adb082f1b496eb183a46c249cb47e4b60"
SEED_NAMESPACE = 20261004
BOOTSTRAPS = 4096
FAMILY_SIZE = 21
STATISTICAL_ERROR = .04
MONTE_CARLO_ERROR = .01


def rng(stage, scenario, replicate=0):
    return np.random.Generator(np.random.PCG64(
        np.random.SeedSequence([SEED_NAMESPACE, stage, scenario, replicate])))


def order_rank(resamples=BOOTSTRAPS, family=FAMILY_SIZE,
               alpha=STATISTICAL_ERROR, delta=MONTE_CARLO_ERROR):
    """Smallest conservative order rank, including extended-valued roots."""
    if type(resamples) is not int or resamples < 1 or family < 1 or not 0 < alpha < 1 or not 0 < delta < 1:
        raise ValueError("invalid fixed error allocation")
    probability = 1-alpha/family
    tails = binom.sf(np.arange(resamples), resamples, probability)
    admitted = np.flatnonzero(tails <= delta/family)
    if not len(admitted):
        raise ValueError("resample budget cannot support the allocated quantile endpoint")
    return int(admitted[0]+1)


def fixed_scales(point):
    point = np.asarray(point)
    if point.shape != (3,) or not np.isfinite(point).all() or point[2] < 0:
        raise ValueError("invalid original candidate coordinates")
    return np.array([1., 1., max(1., point[2])])


def root_interval(point, roots, *, rank):
    """No root is discarded: positive infinity is an explicit refusal."""
    roots = np.asarray(roots)
    scales = fixed_scales(point)
    if roots.ndim != 1 or not 1 <= rank <= len(roots) or np.isnan(roots).any() or (roots < 0).any():
        raise ValueError("invalid extended bootstrap roots")
    critical = float(np.partition(roots, rank-1)[rank-1])
    if not np.isfinite(critical):
        raise ValueError("allocated order statistic is infinite")
    low, high = np.asarray(point)-critical*scales, np.asarray(point)+critical*scales
    low[2] = max(0., low[2])
    if not np.isfinite(low).all() or not np.isfinite(high).all():
        raise ValueError("nonfinite interval bounds")
    return low, high, critical


def select(rows):
    selected = sm.select(rows)
    selected["admitted_ordering_status"] = selected["status"]
    selected["admitted_indices"] = [r["index"] for r in rows if r["status"] == "calibration_feasible"]
    unresolved = [r["index"] for r in rows if r["threshold_kind"] == "finite"
                  and r["status"] not in ("calibration_feasible", "bias_proven_infeasible")]
    selected["unresolved_competitor_indices"] = unresolved
    selected["proven_bias_infeasible_indices"] = [r["index"] for r in rows if r["status"] == "bias_proven_infeasible"]
    if selected["selected_index"] is None:
        selected["global_grid_optimum_status"] = "unresolved_no_admitted_candidate"
    else:
        selected["status"] = "point_minimum_among_admitted"
        selected["global_grid_optimum_status"] = (
            "unresolved_competitor_inference" if unresolved else
            "unresolved_admitted_ordering" if len(selected["plausible_minimizers"]) > 1 else
            "conditionally_resolved_declared_grid")
    return selected


def bootstrap(data, reference, rows):
    """Paired draws shared across slots; each slot retains every failed root."""
    roots = np.full((BOOTSTRAPS, 3, len(sm.WORDS)), np.inf)
    candidate_failures = {(s, i): Counter() for s in range(3) for i in range(len(sm.WORDS))}
    reference_failures = Counter()
    included = [(s, r["index"]) for s, group in enumerate(rows) for r in group
                if r["status"] == "supported_point"]
    generators = [rng(60, s, 20000) for s in range(3)]
    ref_generator = rng(60, 99, 21000)
    for replicate in range(BOOTSTRAPS):
        if replicate and replicate % 512 == 0:
            print(f"completed {replicate}/{BOOTSTRAPS} fixed calibration resamples", flush=True)
        samples = [sm.resample(value, gen) for value, gen in zip(data, generators)]
        ref_sample = sm.resample(reference, ref_generator)
        try:
            target = sm.reference_variance(ref_sample)
        except ValueError as exc:
            reference_failures[str(exc).split(":")[0]] += 1
            continue
        for scenario, index in included:
            try:
                estimate = sm.estimate(samples[scenario], index, diagnostics=False)
                coordinate = sm.coordinates(estimate, target)
                row = rows[scenario][index]
                root = np.max(abs(coordinate-row["point_coordinates"])/row["fixed_scales"])
                if not np.isfinite(root):
                    raise ValueError("nonfinite bootstrap root")
                roots[replicate, scenario, index] = root
            except ValueError as exc:
                candidate_failures[scenario, index][str(exc).split(":")[0]] += 1
    return roots, candidate_failures, reference_failures


def calibrate(data, reference):
    rows = []
    try:
        target = sm.reference_variance(reference)
        reference_reason = None
    except ValueError as exc:
        target, reference_reason = None, str(exc)
    for scenario, value in enumerate(data):
        group = []
        for index, word in enumerate(sm.WORDS):
            row = {"index": index, "eta_q16": str(word), "threshold_kind": "finite"}
            try:
                if reference_reason:
                    raise ValueError("original reference refused: "+reference_reason)
                estimate = sm.estimate(value, index)
                point = sm.coordinates(estimate, target)
                row.update(status="supported_point", estimate=estimate, point_coordinates=point,
                           fixed_scales=fixed_scales(point), time_point_blocks=int(np.ceil(point[2])),
                           naive_uniform_time_blocks=sm.REFERENCE_BLOCKS/estimate["retained_frame_fraction"])
                for alternative in ("gaussian_closure", "frozen_mask"):
                    alt = estimate[alternative]
                    if alt["status"] != "refused":
                        try:
                            alt["coordinates"] = sm.coordinates(alt, target)
                        except ValueError as exc:
                            estimate[alternative] = {"status": "refused", "reason": str(exc)}
            except ValueError as exc:
                row.update(status="point_refused", reason=str(exc))
            group.append(row)
        group.append({"index": len(sm.WORDS), "threshold_kind": "reject_all", "eta_q16": None,
                      "status": "no_science_information", "time_point_blocks": None,
                      "reason": "zero retained samples; no science information or finite observing time"})
        rows.append(group)
    roots, failures, reference_failures = bootstrap(data, reference, rows)
    rank = order_rank(BOOTSTRAPS)
    for scenario, group in enumerate(rows):
        for row in group[:-1]:
            index = row["index"]
            slot_roots = roots[:, scenario, index]
            row["bootstrap"] = {"requested": BOOTSTRAPS, "finite_roots": int(np.isfinite(slot_roots).sum()),
                                "infinite_roots": int(np.isinf(slot_roots).sum()),
                                "candidate_refusals": dict(failures[scenario, index]),
                                "reference_refusals": dict(reference_failures), "rank": rank,
                                "alpha_allocation": STATISTICAL_ERROR/FAMILY_SIZE,
                                "mc_allocation": MONTE_CARLO_ERROR/FAMILY_SIZE}
            row.update(bias_ratio_lower=None, bias_ratio_upper=None, time_lower_blocks=0.,
                       time_upper_blocks=None, bounds_status="unavailable_unbounded")
            if row["status"] != "supported_point":
                row["bootstrap"]["original_point_unavailable"] = True
                continue
            try:
                low, high, critical = root_interval(row["point_coordinates"], slot_roots, rank=rank)
                row.update(bias_ratio_lower=low[:2], bias_ratio_upper=high[:2],
                           time_lower_blocks=float(low[2]), time_upper_blocks=float(high[2]),
                           bounds_status="finite", critical_root=critical)
                row["status"] = ("calibration_feasible" if np.all(np.maximum(abs(low[:2]), abs(high[:2])) <= 1)
                                 else "bias_proven_infeasible" if np.any((low[:2] > 1) | (high[:2] < -1))
                                 else "bias_requirement_unresolved")
            except ValueError as exc:
                row.update(status="uncertainty_refused", reason=str(exc))
    return ({"target_variance": target, "reference_exposure_blocks": sm.REFERENCE_BLOCKS,
             "original_reference_refusal": reference_reason, "rows": rows,
             "bootstrap": {"requested_per_slot": BOOTSTRAPS, "fixed_family_size": FAMILY_SIZE,
                           "statistical_error": STATISTICAL_ERROR, "monte_carlo_error": MONTE_CARLO_ERROR,
                           "rank": rank, "reference_refusals": dict(reference_failures),
                           "failed_roots_retained": True, "statistical_coverage": "nominal_not_proven"},
             "selections": [select(group) for group in rows]}, roots)


def settings():
    return dict(base.settings(), calibration_bootstrap_resamples=BOOTSTRAPS,
                seed_namespace=SEED_NAMESPACE, fixed_family_size=FAMILY_SIZE,
                statistical_error=STATISTICAL_ERROR, monte_carlo_error=MONTE_CARLO_ERROR,
                order_rank=order_rank(BOOTSTRAPS), historical_source_commit=HISTORICAL_COMMIT)


def sources():
    return dict(base.sources(), same_mask_candidatewise=base.digest(Path(__file__)))


def evaluate(calibration, root):
    interval = partial(base.fixed_interval, rng_factory=rng)
    return base.evaluate(calibration,
                         lambda stage, scenario, replicate=0: base.load_blocks(root, stage, scenario, replicate),
                         interval_factory=interval)


def result(calibration, evaluations):
    return {"schema": SCHEMA, "scope": "score-level synthetic; local theta=0; no physical channel ruling",
            "physical_response_qualified": False, "unconditional_optimum_coverage_claimed": False,
            "bootstrap_coverage_is_nominal": True, "protocol_sha256": PROTOCOL_SHA256,
            "historical_source_commit": HISTORICAL_COMMIT, "calibration": calibration, "evaluation": evaluations}


def product_texts(outcome):
    columns = ("scenario", "threshold_kind", "eta_q16", "status", "reason", "time_point_blocks",
               "time_lower_blocks", "time_upper_blocks", "bounds_status", "valid_blocks", "valid_block_fraction",
               "retained_frame_fraction", "naive_uniform_time_blocks", "finite_roots", "infinite_roots")
    with io.StringIO(newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for scenario, group in zip(sm.SCENARIOS, outcome["calibration"]["rows"]):
            for row in group:
                merged = dict(row, **{k: v for k, v in row.get("estimate", {}).items() if k in columns},
                              **{k: v for k, v in row.get("bootstrap", {}).items() if k in columns})
                writer.writerow({key: merged.get(key, scenario if key == "scenario" else "") for key in columns})
        table = handle.getvalue()
    lines = ["CANDIDATE-SPECIFIC SAME-MASK SYNTHETIC STUDY", "",
             "One predeclared follow-up; the original global-refusal study remains unchanged.",
             "Synthetic observed scores, recomputed same-mask response and empirical fourth moments; no physical ruling.",
             "All 21 finite slots retain their error allocation. Failed roots are infinite, never dropped.",
             "Fixed 4096 calibration roots; conservative maximum order statistic; one failure refuses that slot.",
             "Statistical bootstrap coverage is nominal; the conditional Monte Carlo bound is distinct.",
             "Calibration chooses the whole-block point minimum among admitted candidates only.",
             "Unavailable competitors prevent a claim of the entire-grid optimum.",
             "Independent evaluation cannot reselect. Coverage conditions on a frozen response and shared reference.",
             "A clean 1024-block reference sets precision; no time cap, automatic knee or cleaning credit.", ""]
    for scenario_index, (scenario, selection, evaluation) in enumerate(zip(
            sm.SCENARIOS, outcome["calibration"]["selections"], outcome["evaluation"])):
        lines.extend([scenario, f"  Selection: {selection['status']}; index={selection['selected_index']}.",
                      f"  Entire grid: {selection['global_grid_optimum_status']}.",
                      f"  Unresolved competitors: {selection['unresolved_competitor_indices']}.",
                      f"  Independent evaluation: {evaluation['status']}."])
        if selection["selected_index"] is not None:
            chosen = outcome["calibration"]["rows"][scenario_index][selection["selected_index"]]
            lines.extend([f"  Frozen threshold: kind={chosen['threshold_kind']}; eta_q16={chosen['eta_q16']}.",
                          f"  Point minimum among admitted: {selection['point_minimum_blocks']} whole 10s blocks.",
                          f"  Frozen conservative exposure: {selection['validation_time_blocks']} whole 10s blocks.",
                          f"  Coverage: {evaluation.get('coverage_status', 'unavailable')}; "
                          f"center containment={evaluation.get('reference_center_containment', 'unavailable')}/{sm.REPLICATES}."])
        lines.append("")
    lines.append("No admission is not proof of all-threshold infeasibility or a reject-all recommendation. Stop after this campaign.")
    return {"result.json": base.encoded(outcome), "candidates.csv": table, "REPORT.txt": "\n".join(lines)+"\n"}


def expected_files():
    return base.expected_files() | {"ORIGINAL_PROTOCOL.md", "calibration_roots.npz"}


def run(root, protocol):
    root, protocol = Path(root), Path(protocol)
    original = protocol.parent / "SAME_MASK_SYNTHETIC_PROTOCOL.md"
    if base.digest(protocol) != PROTOCOL_SHA256 or base.digest(original) != sm.PROTOCOL_SHA256:
        raise ValueError("protocol differs from the reviewed pre-trial protocols")
    if root.exists():
        raise ValueError("output directory must be new")
    identity = {"schema": SCHEMA, "sources": sources(), "settings": settings(), "environment": base.environment(),
                "protocol_sha256": PROTOCOL_SHA256, "original_protocol_sha256": sm.PROTOCOL_SHA256}
    root.mkdir(parents=True)
    (root / "blocks").mkdir()
    (root / "PROTOCOL.md").write_bytes(protocol.read_bytes())
    (root / "ORIGINAL_PROTOCOL.md").write_bytes(original.read_bytes())
    (root / "run_identity.json").write_text(base.encoded(identity), encoding="utf-8")
    for stage in (10, 20, 21, 30, 40, 50):
        for scenario in (range(1) if stage == 21 else range(3)):
            for replicate in (range(sm.REPLICATES) if stage == 50 else range(1)):
                value = sm.generate(stage, scenario, replicate, injections=stage in (20, 21),
                                    words=(sm.WORDS[-1],) if stage == 21 else sm.WORDS, rng_factory=rng)
                np.savez_compressed(root / base.block_name(stage, scenario, replicate), **value)
        print(f"saved fixed candidatewise stage {stage}", flush=True)
        if stage == 21:
            calibration, roots = calibrate([base.load_blocks(root, 20, s) for s in range(3)], base.load_blocks(root, 21, 0))
            (root / "calibration.json").write_text(base.encoded(calibration), encoding="utf-8")
            np.savez_compressed(root / "calibration_roots.npz", roots=roots)
            print("candidatewise calibration frozen before independent evaluation", flush=True)
    outcome = result(calibration, evaluate(calibration, root))
    for name, content in product_texts(outcome).items():
        (root / name).write_text(content, encoding="utf-8", newline="")
    if sources() != identity["sources"] or base.digest(protocol) != PROTOCOL_SHA256 or base.digest(original) != sm.PROTOCOL_SHA256:
        raise ValueError("source/protocol changed during trial; output remains incomplete")
    files = {path.relative_to(root).as_posix(): base.digest(path) for path in sorted(root.rglob("*")) if path.is_file()}
    if set(files) != expected_files():
        raise ValueError("completed study artifact inventory mismatch")
    manifest = dict(identity, complete=True, files_sha256=files)
    (root / "manifest.json").write_text(base.encoded(manifest), encoding="utf-8")
    return outcome


def validate(root):
    root = Path(root)
    manifest = json.loads((root / "manifest.json").read_text())
    if (manifest.get("schema") != SCHEMA or manifest.get("complete") is not True
            or manifest.get("sources") != sources() or manifest.get("protocol_sha256") != PROTOCOL_SHA256
            or manifest.get("original_protocol_sha256") != sm.PROTOCOL_SHA256):
        raise ValueError("study identity or source provenance mismatch")
    if manifest.get("environment") != base.environment() or manifest.get("settings") != settings():
        raise ValueError("study numerical environment or fixed settings mismatch")
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()} - {"manifest.json"}
    if set(manifest.get("files_sha256", {})) != expected_files() or actual != expected_files():
        raise ValueError("study artifact inventory mismatch")
    for name, expected in manifest["files_sha256"].items():
        path = root / name
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("artifact path escapes study")
        if base.digest(path) != expected:
            raise ValueError(f"artifact hash mismatch: {name}")
    if base.digest(root / "PROTOCOL.md") != PROTOCOL_SHA256 or base.digest(root / "ORIGINAL_PROTOCOL.md") != sm.PROTOCOL_SHA256:
        raise ValueError("saved protocol mismatch")
    identity = {key: manifest[key] for key in ("schema", "sources", "settings", "environment", "protocol_sha256", "original_protocol_sha256")}
    if json.loads((root / "run_identity.json").read_text()) != identity:
        raise ValueError("saved pre-trial identity mismatch")
    for stage in (10, 20, 21, 30, 40, 50):
        for scenario in (range(1) if stage == 21 else range(3)):
            for replicate in (range(sm.REPLICATES) if stage == 50 else range(1)):
                base.load_blocks(root, stage, scenario, replicate)
    calibration, roots = calibrate([base.load_blocks(root, 20, s) for s in range(3)], base.load_blocks(root, 21, 0))
    if base.plain(calibration) != json.loads((root / "calibration.json").read_text()):
        raise ValueError("saved calibration differs from independent reconstruction")
    with np.load(root / "calibration_roots.npz", allow_pickle=False) as saved:
        if set(saved.files) != {"roots"} or not np.array_equal(saved["roots"], roots):
            raise ValueError("saved extended roots differ from reconstruction")
    outcome = result(calibration, evaluate(calibration, root))
    for name, content in product_texts(outcome).items():
        if (root / name).read_bytes() != content.encode("utf-8"):
            raise ValueError(f"saved product differs from independent reconstruction: {name}")
    for name, expected in manifest["files_sha256"].items():
        if base.digest(root / name) != expected:
            raise ValueError("artifact changed during revalidation")
    if manifest["sources"] != sources():
        raise ValueError("source changed during revalidation")
    return outcome


def main(argv=None, prog="rfisher response same-mask-candidatewise"):
    parser = argparse.ArgumentParser(prog=prog, description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--out", type=Path, help="new directory for the single fixed follow-up")
    action.add_argument("--validate", type=Path, help="authenticate and reconstruct without new draws")
    parser.add_argument("--protocol", type=Path, help="reviewed follow-up protocol; original sibling also required")
    args = parser.parse_args(argv)
    if args.out and args.protocol is None:
        parser.error("--out requires --protocol")
    if args.validate and args.protocol is not None:
        parser.error("--validate uses the saved protocols")
    try:
        outcome = validate(args.validate) if args.validate else run(args.out, args.protocol)
    except (ValueError, OSError, KeyError) as exc:
        parser.error(str(exc))
    print(base.encoded({"schema": SCHEMA, "physical_response_qualified": False,
                        "selections": outcome["calibration"]["selections"]}))
    return 0
