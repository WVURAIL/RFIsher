"""Evaluate supplied physical responses against fixed precision and calendar budgets.

This consumes, rather than derives or qualifies, same-mask parameter responses.
It selects among evaluated times only and never infers all-threshold exclusion.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from decimal import Decimal
from pathlib import Path

from .evidence import UnqualifiedResponseError, require_science_selection_evidence

SCHEMA = "rfisher_physical_calendar_candidates_v1"
OUTPUT_SCHEMA = "rfisher_fixed_precision_calendar_review_v1"


def _keys(value, expected, label):
    if not isinstance(value, dict) or set(value) != set(expected.split()):
        raise ValueError(f"{label} requires exactly: {expected}")


def _number(value, label, *, positive=False):
    try:
        finite = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError(f"{label} must be finite numeric data")
    if positive and value <= 0:
        raise ValueError(f"{label} must be positive")
    return value


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty text")
    return value


def _labels(value, label):
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a nonempty list")
    for item in value:
        _text(item, label)
    if len(set(value)) != len(value):
        raise ValueError(f"{label} contains duplicates")
    return value


def _vector(value, size, label, *, positive=False):
    if not isinstance(value, list) or len(value) != size:
        raise ValueError(f"{label} must have {size} entries")
    return [_number(item, label, positive=positive) for item in value]


def _threshold(value):
    if not isinstance(value, dict):
        raise ValueError("threshold must be a mapping")
    if value.get("kind") == "reject_all":
        _keys(value, "kind", "reject_all threshold")
    elif value.get("kind") == "finite":
        _keys(value, "kind eta_q16", "finite threshold")
        word = value["eta_q16"]
        if (not isinstance(word, str) or not re.fullmatch(r"0|[1-9][0-9]{0,19}", word)
                or int(word) >= 2**64):
            raise ValueError("eta_q16 must be an exact uint64 decimal string")
    else:
        raise ValueError("threshold kind must be finite or reject_all")
    return dict(value)


def _provenance(value, identities):
    _keys(value, "evidence_ids description", "provenance")
    references = _labels(value["evidence_ids"], "provenance evidence_ids")
    _text(value["description"], "provenance description")
    if not set(references) <= identities:
        raise ValueError("provenance refers to unknown evidence files")


def _evidence_files(files):
    if not isinstance(files, list) or not files:
        raise ValueError("evidence_files must be nonempty")
    ids = []
    for row in files:
        _keys(row, "id path sha256", "evidence file")
        ids.append(_text(row["id"], "evidence id"))
        _text(row["path"], "evidence path")
        if not isinstance(row["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"]):
            raise ValueError("evidence sha256 must be 64 lowercase hexadecimal digits")
    if len(set(ids)) != len(ids):
        raise ValueError("evidence file IDs must be unique")
    return set(ids)


def _reference(reference, evidence_ids):
    _keys(reference, "parameter_scope forecast_bins parameter_names parameter_units sigma "
          "science_bins excluded_pilot_bins on_sky_hours provenance evidence", "reference")
    names = _labels(reference["parameter_names"], "parameter_names")
    bins = _labels(reference["forecast_bins"], "forecast_bins")
    scope = reference["parameter_scope"]
    if scope == "per_forecast_bin":
        expected = {f"{b}:{p}" for b in bins for p in ("aperp", "apar")}
    elif scope == "joint_domain":
        expected = {"aperp", "apar"}
    else:
        raise ValueError("parameter_scope must be per_forecast_bin or joint_domain")
    if set(names) != expected:
        raise ValueError("both dilations must be represented for the declared parameter scope")
    if reference["parameter_units"] != ["dimensionless"] * len(names):
        raise ValueError("dilation parameters must declare dimensionless units")
    _vector(reference["sigma"], len(names), "reference sigma", positive=True)
    science = _labels(reference["science_bins"], "reference science_bins")
    pilots = _labels(reference["excluded_pilot_bins"], "reference excluded_pilot_bins")
    if set(science) & set(pilots):
        raise ValueError("pilot bins cannot enter reference science support")
    _number(reference["on_sky_hours"], "reference on_sky_hours", positive=True)
    _provenance(reference["provenance"], evidence_ids)
    if not isinstance(reference["evidence"], dict):
        raise ValueError("reference evidence must be a mapping")
    return names


def _qualified(evidence):
    if not isinstance(evidence, dict):
        raise ValueError("response evidence must be a mapping")
    try:
        require_science_selection_evidence(evidence)
    except UnqualifiedResponseError as exc:
        return str(exc)
    return None


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def evaluate_document(document):
    """Review declared responses; pure API does not authenticate evidence bytes.

    Bias is compared with the fixed clean reference error, not the candidate's
    changing error. Every declared dilation must also reach that precision.
    Nominal science support is identical; candidate responses already include
    mask-induced information loss. No extra retention factor is applied.
    """
    _keys(document, "schema channel reference context candidates fallback_threshold evidence_files", "document")
    if document["schema"] != SCHEMA:
        raise ValueError(f"schema must be {SCHEMA}")
    if type(document["channel"]) is not int or document["channel"] < 0:
        raise ValueError("channel must be a nonnegative integer")
    evidence_ids = _evidence_files(document["evidence_files"])
    reference = document["reference"]
    names = _reference(reference, evidence_ids)
    reference_refusal = _qualified(reference["evidence"])
    context = document["context"]
    _keys(context, "tolerance duty hours_per_calendar_year budgets_calendar_years", "context")
    if _number(context["tolerance"], "tolerance") != 1:
        raise ValueError("this study fixes tolerance at 1")
    duty = _number(context["duty"], "duty", positive=True)
    if duty > 1:
        raise ValueError("duty cannot exceed 1")
    year_hours = _number(context["hours_per_calendar_year"], "hours_per_calendar_year", positive=True)
    budgets = context["budgets_calendar_years"]
    if not isinstance(budgets, list) or not budgets:
        raise ValueError("budgets_calendar_years must be nonempty")
    for budget in budgets:
        _number(budget, "budget", positive=True)
    if len(set(budgets)) != len(budgets):
        raise ValueError("duplicate calendar budgets")
    fallback = _threshold(document["fallback_threshold"])
    candidates = document["candidates"]
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("candidates must be nonempty")
    seen_ids, seen_thresholds, rows, feasible = set(), set(), [], []
    conversion = Decimal(str(duty)) * Decimal(str(year_hours))
    for candidate in candidates:
        _keys(candidate, "id threshold evidence science_bins excluded_pilot_bins response_provenance evaluations", "candidate")
        identity = _text(candidate["id"], "candidate id")
        threshold = _threshold(candidate["threshold"])
        encoded = _canonical(threshold)
        if identity in seen_ids or encoded in seen_thresholds:
            raise ValueError("candidate IDs and threshold assignments must be unique")
        seen_ids.add(identity)
        seen_thresholds.add(encoded)
        science = _labels(candidate["science_bins"], "candidate science_bins")
        pilots = _labels(candidate["excluded_pilot_bins"], "candidate excluded_pilot_bins")
        if set(science) != set(reference["science_bins"]) or set(pilots) != set(reference["excluded_pilot_bins"]):
            raise ValueError("candidate and reference must use the same pilot-excluded nominal science domain")
        _provenance(candidate["response_provenance"], evidence_ids)
        candidate_refusal = _qualified(candidate["evidence"])
        refusal = reference_refusal or candidate_refusal
        evaluations = candidate["evaluations"]
        if not isinstance(evaluations, list):
            raise ValueError("evaluations must be a list")
        if threshold["kind"] == "reject_all" and evaluations:
            raise ValueError("reject_all cannot claim finite science precision on the channel")
        row = {"id": identity, "threshold": threshold, "evidence_refusal": refusal,
               "evaluations": [], "response_provenance": candidate["response_provenance"]}
        times = set()
        for point in evaluations:
            if not isinstance(point, dict):
                raise ValueError("evaluation must be a mapping")
            status = point.get("status")
            expected = "on_sky_hours status bias sigma" if status == "available" else "on_sky_hours status reason"
            _keys(point, expected, "evaluation")
            if status not in {"available", "unavailable"}:
                raise ValueError("evaluation status must be available or unavailable")
            hours = _number(point["on_sky_hours"], "on_sky_hours", positive=True)
            if hours in times:
                raise ValueError("duplicate candidate evaluation times")
            times.add(hours)
            years = float(Decimal(str(hours)) / conversion)
            _number(years, "converted calendar years", positive=True)
            record = {"on_sky_hours": hours, "calendar_years": years, "input_status": status}
            if status == "unavailable":
                record.update(status="unavailable", reason=_text(point["reason"], "unavailable reason"))
            else:
                bias = _vector(point["bias"], len(names), "bias")
                sigma = _vector(point["sigma"], len(names), "sigma", positive=True)
                bias_ok = [abs(b) <= target for b, target in zip(bias, reference["sigma"])]
                precision_ok = [s <= target for s, target in zip(sigma, reference["sigma"])]
                record.update(bias=bias, sigma=sigma, bias_within_fixed_target=bias_ok,
                              precision_reached=precision_ok,
                              failed_bias_parameters=[n for n, ok in zip(names, bias_ok) if not ok],
                              failed_precision_parameters=[n for n, ok in zip(names, precision_ok) if not ok])
                record["status"] = ("unqualified_response" if refusal else "feasible_evaluated_point"
                                    if all(bias_ok) and all(precision_ok) else "fails_at_evaluated_time")
                if record["status"] == "feasible_evaluated_point":
                    feasible.append((hours, identity, threshold, record))
            row["evaluations"].append(record)
        row["evaluations"].sort(key=lambda p: p["on_sky_hours"])
        if threshold["kind"] == "reject_all":
            row["status"] = "permanent_mask_endpoint_no_channel_information"
        elif refusal:
            row["status"] = "unqualified_response"
        elif not evaluations or any(p["status"] == "unavailable" for p in row["evaluations"]):
            row["status"] = "incomplete_evaluated_response"
        else:
            row["status"] = "evaluated_grid_only"
        rows.append(row)
    feasible.sort(key=lambda item: (item[0], item[1]))
    decisions = []
    for budget in sorted(budgets):
        allowed_hours = Decimal(str(budget)) * conversion
        admitted = [entry for entry in feasible if Decimal(str(entry[0])) <= allowed_hours]
        selected = admitted[0] if admitted else None
        ties = [entry[1] for entry in admitted if entry[0] == selected[0]] if selected else []
        decisions.append({
            "budget_calendar_years": budget, "available_on_sky_hours": float(allowed_hours),
            "status": "minimum_among_qualified_evaluated_points" if selected else "no_qualified_evaluated_point_within_budget",
            "scientific_candidate_id": selected[1] if selected else None,
            "scientific_threshold": selected[2] if selected else None,
            "required_on_sky_hours_at_evaluated_point": selected[0] if selected else None,
            "required_calendar_years_at_evaluated_point": selected[3]["calendar_years"] if selected else None,
            "tied_candidate_ids": ties,
            "threshold_assignment": selected[2] if selected else fallback,
            "assignment_basis": "qualified_evaluated_point" if selected else "preserved_provisional_assignment",
            "unresolved_candidates": [r["id"] for r in rows if r["status"] in {"incomplete_evaluated_response", "unqualified_response"}],
            "continuous_time_optimum_established": False,
            "all_threshold_infeasibility_established": False,
        })
    result = {
        "schema": OUTPUT_SCHEMA, "channel": document["channel"],
        "scope": "Declared fixed-target physical responses on an evaluated candidate/time grid only.",
        "reference": reference, "context": context, "candidates": rows, "budget_decisions": decisions,
        "fallback_threshold": fallback, "input_digest": hashlib.sha256(_canonical(document).encode()).hexdigest(),
        "evidence_bytes_authenticated": False, "qualification_independently_established": False,
        "physical_response_derived_by_this_command": False, "threshold_activated": False,
        "limitations": ["Qualification declarations require independent scientific review; hashes identify bytes only.",
                        "No interpolation, extrapolation, hidden noise floor, or extra retention penalty is applied.",
                        "Unobserved times and thresholds remain unresolved, even when a tested minimum is available.",
                        "A failed or missing tested response does not prove that every threshold is infeasible."],
    }
    _canonical(result)
    return result


def _sha(path):
    hasher = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def write_report(input_path, output_path):
    """Authenticate declared local files and write a new, non-overwriting report."""
    input_path, output_path = Path(input_path).resolve(), Path(output_path).resolve()
    raw = input_path.read_bytes()
    document = json.loads(raw, object_pairs_hook=_unique)
    report = evaluate_document(document)
    verified = []
    for record in document["evidence_files"]:
        path = (input_path.parent / record["path"]).resolve()
        if _sha(path) != record["sha256"]:
            raise ValueError(f"evidence hash mismatch for {record['id']}")
        verified.append({**record, "resolved_path": str(path)})
    input_digest = hashlib.sha256(raw).hexdigest()
    if _sha(input_path) != input_digest:
        raise ValueError("input document changed during verification")
    report.update(evidence_bytes_authenticated=True, authenticated_files=verified,
                  input_file={"path": str(input_path), "sha256": input_digest})
    with output_path.open("x") as stream:
        stream.write(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return report


def main(argv=None, prog="rfisher response calendar"):
    parser = argparse.ArgumentParser(prog=prog, description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = write_report(args.input, args.output)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps({"channel": result["channel"], "decisions": result["budget_decisions"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
