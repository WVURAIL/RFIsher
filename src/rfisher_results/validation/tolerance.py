"""Joint upper tolerance limits for frozen residual claims on independent blocks.

For each block, the score is the largest ``truth - claim`` over a fixed set
of cases. An order statistic bounds this score with predeclared population
content and calibration confidence. This covers a future block under the same
IID block-generating distribution; it is not a confidence limit for a mean.
Cases may share data within a block. Blocks must be independent, and the
claim rule and case family must be fixed before calibration. Identity checks
cannot establish these assumptions or physical applicability.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from numbers import Integral, Real

from scipy.stats import binom

from .coverage import binomial_lower


def _probability(value, name):
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite probability")
    value = float(value)
    if not math.isfinite(value) or not 0 < value < 1:
        raise ValueError(f"{name} must lie strictly between zero and one")
    return value


def _identities(values, name):
    if not values or any(not isinstance(v, str) or not v for v in values):
        raise ValueError(f"{name} must be nonempty string identities")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")
    return sorted(values)


def _validated_blocks(blocks, *, minimum_retained):
    if isinstance(minimum_retained, bool) or not isinstance(minimum_retained, Integral) or minimum_retained < 1:
        raise ValueError("minimum retained support must be a positive integer")
    if not isinstance(blocks, Mapping):
        raise ValueError("blocks must map block identities to case mappings")
    block_ids = _identities(list(blocks), "block identities")
    case_ids = None
    rows = []
    for block_id in block_ids:
        cases = blocks[block_id]
        if not isinstance(cases, Mapping):
            raise ValueError("each block must map case identities to measurements")
        actual_cases = _identities(list(cases), "case identities")
        if case_ids is None:
            case_ids = actual_cases
        elif actual_cases != case_ids:
            raise ValueError("every block must contain exactly the same case identities")
        measurements = {}
        unsupported = []
        errors = []
        for case_id in case_ids:
            row = cases[case_id]
            if not isinstance(row, Mapping) or not {"claim", "truth", "kept"} <= row.keys():
                raise ValueError("case measurements require claim, truth and kept")
            kept = row["kept"]
            if isinstance(kept, bool) or not isinstance(kept, Integral) or kept < 0:
                raise ValueError("kept must be a nonnegative integer")
            claim, truth = row["claim"], row["truth"]
            if kept:
                for value in (claim, truth):
                    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value) or value < 0:
                        raise ValueError("nonempty kept sets require finite nonnegative means")
                claim, truth = float(claim), float(truth)
            elif claim is not None or truth is not None:
                raise ValueError("empty kept-set means must be unavailable")
            measurements[case_id] = {"claim": claim, "truth": truth, "kept": int(kept)}
            if kept < minimum_retained:
                unsupported.append(case_id)
            else:
                errors.append(truth - claim)
        rows.append({
            "id": block_id, "cases": measurements,
            "unsupported_cases": unsupported,
            # None serializes an unsupported (+infinity) score without NaN/Inf.
            "joint_error": None if unsupported else max(errors),
        })
    return block_ids, case_ids, rows


def calibrate_joint_additive(blocks, *, content=.95, confidence=.95, min_retained=30):
    """Fit a signed correction using a distribution-free upper tolerance limit.

    With n calibration blocks, choose the smallest rank k for which
    ``P[Binomial(n, content) <= k-1] >= confidence``. The k-th ordered joint
    error is q, and a future case receives ``max(0, claim + q)``. Negative q
    is allowed. Ties are conservative. Unsupported blocks score +infinity;
    a selected infinite score or an insufficient n refuses a finite bound.

    The result records all identities and the original measurements. Callers
    must bind data, claim code, policies and generator settings with hashes.
    """
    content = _probability(content, "content")
    confidence = _probability(confidence, "confidence")
    block_ids, case_ids, rows = _validated_blocks(blocks, minimum_retained=min_retained)
    count = len(rows)
    rank = next((k for k in range(1, count + 1) if binom.cdf(k - 1, count, content) >= confidence), None)
    correction = None
    reasons = []
    if rank is None:
        reasons.append("insufficient calibration blocks for requested content and confidence")
    else:
        scores = sorted(math.inf if r["joint_error"] is None else r["joint_error"] for r in rows)
        if not math.isfinite(scores[rank - 1]):
            reasons.append("selected tolerance order statistic is unsupported; no finite correction")
        else:
            correction = scores[rank - 1]
    return {
        "schema": "rfisher-joint-additive-tolerance-v1",
        "status": "refused" if reasons else "calibrated",
        "correction": correction,
        "content": content, "confidence": confidence,
        "achieved_confidence": float(binom.cdf(rank - 1, count, content)) if rank else None,
        "maximum_attainable_confidence": -math.expm1(count * math.log(content)),
        "order_rank": rank, "calibration_blocks": count,
        "minimum_retained": int(min_retained),
        "case_ids": case_ids, "calibration_block_ids": block_ids,
        "unsupported_blocks": sum(bool(r["unsupported_cases"]) for r in rows),
        "refusal_reasons": reasons, "blocks": rows,
        "scope": "future IID block from the same frozen generator and case family; not a population-mean confidence limit or physical calibration",
        "upper_rule": "max(0, original_claim + correction)",
    }


def evaluate_joint_additive(calibration, blocks):
    """Audit a frozen finite calibration on fresh disjoint evaluation blocks.

    Success requires support and truth at most the calibrated upper bound in
    every case. Only the joint indicator receives a confidence claim; the
    per-case summaries are descriptive. Unsupported cases count as failures.
    """
    if not isinstance(calibration, Mapping) or calibration.get("schema") != "rfisher-joint-additive-tolerance-v1":
        raise ValueError("unrecognized tolerance calibration")
    if calibration.get("status") != "calibrated":
        raise ValueError("a refused calibration cannot provide finite upper bounds")
    correction = calibration.get("correction")
    if isinstance(correction, bool) or not isinstance(correction, Real) or not math.isfinite(correction):
        raise ValueError("a finite signed correction is required")
    confidence = _probability(calibration.get("confidence"), "confidence")
    content = _probability(calibration.get("content"), "content")
    expected_cases = _identities(calibration.get("case_ids", []), "calibration case identities")
    calibration_ids = _identities(calibration.get("calibration_block_ids", []), "calibration block identities")
    block_ids, case_ids, rows = _validated_blocks(blocks, minimum_retained=calibration.get("minimum_retained"))
    if case_ids != expected_cases:
        raise ValueError("evaluation case family differs from the calibrated family")
    if set(block_ids) & set(calibration_ids):
        raise ValueError("calibration and evaluation block identities overlap")
    successes = unsupported = underbooked = base_successes = 0
    case_summaries = {c: {"trials": len(rows), "successes": 0, "unsupported": 0, "underbooked": 0, "base_successes": 0, "rows": []} for c in case_ids}
    evaluated_rows = []
    for row in rows:
        block_success = base_success = True
        block_underbooked = False
        evaluated_cases = {}
        for case_id, values in row["cases"].items():
            supported = case_id not in row["unsupported_cases"]
            raw_upper = values["claim"] + correction if values["kept"] else None
            if raw_upper is not None and not math.isfinite(raw_upper):
                raise ValueError("upper-bound arithmetic overflow")
            upper = max(0., raw_upper) if raw_upper is not None else None
            success = bool(supported and values["truth"] <= upper)
            base = bool(supported and values["truth"] <= values["claim"])
            block_success &= success
            base_success &= base
            block_underbooked |= supported and not success
            result = {**values, "upper": upper, "supported": supported, "success": success, "base_success": base}
            evaluated_cases[case_id] = result
            summary = case_summaries[case_id]
            summary["successes"] += int(success)
            summary["base_successes"] += int(base)
            summary["unsupported"] += int(not supported)
            summary["underbooked"] += int(supported and not success)
            summary["rows"].append({"block_id": row["id"], **result})
        successes += int(block_success)
        base_successes += int(base_success)
        unsupported += int(bool(row["unsupported_cases"]))
        # A block can be both unsupported in one case and underbooked in another.
        underbooked += int(block_underbooked)
        evaluated_rows.append({"id": row["id"], "success": bool(block_success), "base_success": bool(base_success), "unsupported_cases": row["unsupported_cases"], "cases": evaluated_cases})
    lower = binomial_lower(successes, len(rows), alpha=1-confidence)
    return {
        "schema": "rfisher-joint-additive-evaluation-v1",
        "correction": float(correction), "content": content, "confidence": confidence,
        "trials": len(rows), "successes": successes, "failures": len(rows)-successes,
        "unsupported_blocks": unsupported, "underbooked_blocks": underbooked,
        "base_successes": base_successes,
        "joint_success_probability_lower": lower,
        "requested_content_demonstrated": lower >= content,
        "case_ids": case_ids, "evaluation_block_ids": block_ids,
        "cases": case_summaries, "blocks": evaluated_rows,
        "scope": calibration.get("scope"),
    }
