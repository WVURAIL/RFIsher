"""Evaluate a declared calibration scenario on the saved bounded candidate grid.

This does not estimate calibration coefficients, assign a physical ETA, or change
the working thresholds. Coefficients are dimensionless in the model contract.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODELS = (
    "independent_averaging_covariance",
    "persistent_gaussian_covariance",
    "persistent_coherent_mean",
)


def evaluate(row, constant, score):
    if any(not math.isfinite(v) or v < 0 for v in (constant, score)):
        raise ValueError("Calibration coefficients must be finite and nonnegative.")
    output = {
        "channel": row["channel"], "candidate_id": row["candidate_id"],
        "threshold": row["threshold"], "roles": row["roles"],
        "evaluated_calendar_years": row["calendar_years"],
        "retained_probability": row["retained_probability"],
        "passes_at_evaluated_duration": False, "parameters": [],
    }
    if row["status"] in ("no_retained_exposure", "unavailable_numerical_response"):
        return {**output, "status": row["status"]}
    if not row["parameters"]:
        raise ValueError("Nonempty exposure has no saved parameter response.")
    g = row["g"]["float"] if row["g"] is not None else None
    if score > 0 and g is None:
        return {**output, "status": "score_transfer_unavailable"}
    effective = constant + (g * score if score > 0 else 0)
    power = effective * effective if row["model"] == "persistent_coherent_mean" else effective
    if not math.isfinite(power):
        raise ValueError("Scenario coefficient exceeds the numerical range.")
    components = []
    for parameter in row["parameters"]:
        bias = parameter["signed_bias_per_unit_power"] * power
        v0, v1, v2 = parameter["variance_polynomial"]
        variance = v0 + (v1 + v2 * power) * power
        if not math.isfinite(bias) or not math.isfinite(variance):
            raise ValueError("Scenario response exceeds the numerical range.")
        sigma = math.sqrt(variance)
        target = parameter["reference_sigma"]
        bias_ratio = abs(bias) / target
        sigma_ratio = sigma / target
        components.append({
            "parameter": parameter["parameter"], "signed_bias": bias,
            "sigma": sigma, "fixed_reference_sigma": target,
            "absolute_bias_ratio": bias_ratio, "sigma_ratio": sigma_ratio,
            "bias_passes": bias_ratio <= 1, "precision_passes": sigma_ratio <= 1,
        })
    passed = all(p["bias_passes"] and p["precision_passes"] for p in components)
    return {
        **output, "status": "evaluated_conditional_scenario", "parameters": components,
        "effective_coefficient": effective,
        "passes_at_evaluated_duration": passed,
        "worst_absolute_bias_ratio": max(p["absolute_bias_ratio"] for p in components),
        "worst_sigma_ratio": max(p["sigma_ratio"] for p in components),
    }


def summarize_budget(rows):
    """Take the union of whole-domain passes at earlier evaluated durations."""
    groups = {}
    for row in rows:
        groups.setdefault((row["channel"], row["candidate_id"]), []).append(row)
    summaries = []
    for _, values in sorted(groups.items()):
        passed = [r["evaluated_calendar_years"] for r in values
                  if r["passes_at_evaluated_duration"]]
        first = values[0]
        summaries.append({
            "channel": first["channel"], "candidate_id": first["candidate_id"],
            "threshold": first["threshold"], "roles": first["roles"],
            "passes_by_budget_on_evaluated_grid": bool(passed),
            "first_passing_evaluated_calendar_years": min(passed) if passed else None,
            "passing_evaluated_calendar_years": sorted(passed),
            "tested_calendar_years": sorted(r["evaluated_calendar_years"] for r in values),
            "minimum_observing_time_established": False,
        })
    return summaries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, choices=MODELS)
    parser.add_argument("--shape", required=True, choices=("noise_shaped", "low_kparallel"))
    parser.add_argument("--calendar-years", required=True, type=int, choices=(10, 100),
                        help="Budget; evaluate all saved durations at or below this value.")
    parser.add_argument("--constant", required=True, type=float)
    parser.add_argument("--score", required=True, type=float)
    parser.add_argument("--channel", type=int, choices=range(14, 38))
    parser.add_argument("--current-only", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists; choose a new path.")
    if any(not math.isfinite(v) or v < 0 for v in (args.constant, args.score)):
        parser.error("Coefficients must be finite and nonnegative.")
    source_bytes = (ROOT / "model/results/REGIONS.json").read_bytes()
    source = json.loads(source_bytes)
    current = {}
    score_hashes = {}
    for channel in range(14, 38):
        score_bytes = (ROOT / f"scores/ch{channel}.json").read_bytes()
        current[channel] = json.loads(score_bytes)["current_threshold"]
        score_hashes[f"ch{channel}.json"] = hashlib.sha256(score_bytes).hexdigest()
    rows = [
        r for r in source["rows"]
        if r["model"] == args.model and r["shape"] == args.shape
        and r["calendar_years"] <= args.calendar_years
        and (args.channel is None or r["channel"] == args.channel)
        and (not args.current_only or r["threshold"] == current[r["channel"]])
    ]
    evaluated = [evaluate(r, args.constant, args.score) for r in rows]
    result = {
        "schema": "conditional_calibration_scenario_v1",
        "model": args.model, "shape": args.shape, "budget_calendar_years": args.calendar_years,
        "declared_constant_coefficient": args.constant,
        "declared_score_coefficient": args.score,
        "coefficients_estimated_from_data": False,
        "physical_response_qualified": False, "threshold_assignments_changed": False,
        "minimum_observing_time_established": False,
        "scope": "A declared scenario on the saved bounded grid. Budget feasibility is the union of whole-domain passes at sampled durations at or below the budget; earliest sampled success is not the continuous minimum time.",
        "provenance": {
            "regions_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "evaluator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "score_manifest_sha256": hashlib.sha256((ROOT / "scores/MANIFEST.json").read_bytes()).hexdigest(),
            "current_threshold_source_sha256": score_hashes,
        },
        "rows": evaluated,
        "candidates": summarize_budget(evaluated),
    }
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({
        "evaluated_duration_rows": len(result["rows"]),
        "passes_at_evaluated_duration": sum(r["passes_at_evaluated_duration"] for r in result["rows"]),
        "candidates_passing_by_budget_on_evaluated_grid": sum(c["passes_by_budget_on_evaluated_grid"] for c in result["candidates"]),
        "physical_response_qualified": False,
    }))


if __name__ == "__main__":
    main()
