#!/usr/bin/env python3
"""Audit complete numerical-fit receipts and report every frozen protocol point."""

import argparse
import csv
import json
from pathlib import Path

import numpy as np
from check_nonlinear_bias import load_bound, read_receipt, write

from rfisher.pk_cache import file_sha256


class IncompleteStudyError(RuntimeError):
    """A planned fit is unavailable; invalid provenance is a separate error."""


def validate_contract(contract, channel, level, protocol, protocol_hash, common):
    """Bind every execution to the protocol and one implementation/runtime."""
    if contract["protocol_sha256"] != protocol_hash or contract["channel"] != channel or contract["level"] != level:
        raise ValueError("point execution is outside the frozen protocol")
    if contract["quadrature"] != protocol["numerical_protocol"][f"{level}_quadrature"]:
        raise ValueError("execution quadrature differs from frozen protocol")
    frozen = {key: value["sha256"] for key, value in protocol["provenance"]["files"].items()}
    if contract["frozen_sources"] != frozen:
        raise ValueError("execution frozen input hashes differ from protocol")
    if contract["frozen_table_sha256"] != frozen["dtv-paper2-bao-bound/data/channel_table.json"]:
        raise ValueError("execution table hash differs from frozen protocol")
    implementation = contract["implementation"]
    if (
        not isinstance(implementation, dict)
        or sorted(key.replace("\\", "/").split("/")[-1] for key in implementation)
        != ["check_nonlinear_bias.py", "nonlinear.py"]
        or any(
            not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value)
            for value in implementation.values()
        )
    ):
        raise ValueError("execution requires complete implementation hashes")
    identity = {key: contract[key] for key in ["implementation", "runtime", "optimizer", "thread_environment"]}
    if common and common != identity:
        raise ValueError("mixed execution implementation/runtime identities require a separate report")
    common.update(identity)


def stationary(fit):
    eigen = fit.get("scaled_hessian_eigenvalues")
    return bool(
        not fit.get("active_bounds")
        and np.isfinite(fit.get("fisher_metric_gradient_norm", np.inf))
        and fit["fisher_metric_gradient_norm"] <= 1e-5
        and eigen is not None
        and len(eigen) == 6
        and np.all(np.isfinite(eigen))
        and min(eigen) > 0
    )


def audit_point(root, channel, level, point, protocol, protocol_hash, clean, receipts, common):
    folder = root / f"ch{channel}" / level
    ep = folder / "execution.json"
    execution = read_receipt(ep)
    contract = execution["contract"]
    validate_contract(contract, channel, level, protocol, protocol_hash, common)
    eh = file_sha256(ep)
    receipts[str(ep.relative_to(root))] = eh
    pre_path = folder / "preflight.json"
    pre = load_bound(pre_path, eh)
    receipts[str(pre_path.relative_to(root))] = file_sha256(pre_path)
    if not pre["pass_derivative_and_table_gates"]:
        raise IncompleteStudyError(f"channel {channel} {level}: preflight failed; fit receipts are unavailable")
    path = folder / f"{point['id']}.json"
    summary = load_bound(path, eh)
    receipts[str(path.relative_to(root))] = file_sha256(path)
    if summary["point"] != point:
        raise ValueError("point parameters differ from frozen protocol")
    expected = ["fiducial"]
    if point["a"] > 0:
        expected.append("fisher")
    if point["refine_and_multistart"]:
        expected.append("continuation")
    if summary["starts"] != expected:
        raise ValueError("missing or extra planned starts")
    records = []
    for name in expected:
        path = folder / f"{point['id']}.{name}.json"
        record = load_bound(path, eh)
        receipts[str(path.relative_to(root))] = file_sha256(path)
        if record["point"] != point or record["start"] != name:
            raise ValueError("start identity differs")
        records.append(record)
    fits = [r["result"] for r in records if r["status"] == "completed"]
    best = min(fits, key=lambda r: r["objective"]) if fits else None
    if best != summary["best"]:
        raise ValueError("reported best is not the lowest recorded objective")
    accepted = [f for f in fits if stationary(f)]
    spread = 0.0
    if len(accepted) > 1:
        coordinates = np.array(
            [
                [
                    f["theta"][2] / clean["dilations"]["sigma"][0],
                    f["theta"][3] / clean["dilations"]["sigma"][1],
                    f["log_dv_shift"] / clean["sigma_dv"],
                ]
                for f in accepted
            ]
        )
        spread = float(np.max(np.ptp(coordinates, axis=0)))
    selected_qualified = bool(
        best is not None
        and stationary(best)
        and spread < 0.01
        and len(fits) == len(expected)
        and pre["pass_derivative_and_table_gates"]
    )
    return {
        "best": best,
        "preflight": pre,
        "contract": contract,
        "selected_interior_stationary": bool(best is not None and stationary(best)),
        "all_starts_completed": len(fits) == len(expected),
        "accepted_start_spread_sigma": spread,
        "qualified_before_channel_and_refinement_checks": selected_qualified,
    }


def small_amplitude_gate(point, audit):
    best, pre = audit["best"], audit["preflight"]
    if best is None:
        return {"pass": False}
    delta = np.asarray(best["shift"])
    linear = point["a"] * np.asarray(pre["linear_shift"])
    fisher = np.asarray(pre["fisher"])
    difference = delta - linear
    error = float(np.sqrt(difference @ fisher @ difference / (linear @ fisher @ linear)))
    q = delta / (point["a_over_atol"] * np.asarray(pre["sigma"]))
    q0 = point["a_tol"] * np.asarray(pre["linear_shift"]) / np.asarray(pre["sigma"])
    coordinate_errors = np.abs(q - q0) / np.maximum(1.0, np.abs(q0))
    return {
        "fisher_relative_slope_error": error,
        "coordinate_scaled_errors": coordinate_errors.tolist(),
        "pass": bool(
            error <= 0.01
            and np.all(coordinate_errors <= 0.01)
            and audit["qualified_before_channel_and_refinement_checks"]
        ),
    }


def build_report(protocol, protocol_hash, results, table, allow_incomplete=False):
    """Audit every planned point; partial mode never relaxes provenance checks."""
    if not protocol["points"] or len({p["id"] for p in protocol["points"]}) != len(protocol["points"]):
        raise ValueError("protocol requires nonempty, unique point IDs")
    receipts, audits, channel_gates, missing, common = {}, {}, {}, {}, {}
    for point in protocol["points"]:
        channel = point["channel"]
        record = audits[point["id"]] = {}
        levels = ["base", "refined"] if point["refine_and_multistart"] else ["base"]
        for level in levels:
            try:
                record[level] = audit_point(
                    results, channel, level, point, protocol, protocol_hash, table[channel], receipts, common
                )
            except (FileNotFoundError, IncompleteStudyError) as exc:
                if not allow_incomplete:
                    raise IncompleteStudyError(f"{point['id']} {level}: {exc}") from exc
                missing.setdefault(point["id"], {})[level] = str(exc)
        if "base" in record and "refined" in record:
            base, refined = record["base"], record["refined"]
            expected = dict(
                base["contract"], level="refined", quadrature=protocol["numerical_protocol"]["refined_quadrature"]
            )
            expected["fit_command"] = list(base["contract"]["fit_command"])
            expected["fit_command"][expected["fit_command"].index("--level") + 1] = "refined"
            if expected != refined["contract"]:
                raise ValueError("base/refined execution contracts differ")
        if point["kind"] == "fixed_fraction" and point["a_over_atol"] == 0.001:
            channel_gates[str(channel)] = (
                small_amplitude_gate(point, record["base"])
                if "base" in record
                else {"pass": False, "reason": "small-amplitude fit unavailable"}
            )
    if set(channel_gates) != {str(p["channel"]) for p in protocol["points"]}:
        raise ValueError("protocol lacks a small-amplitude recovery point for a channel")
    rows = []
    for point in protocol["points"]:
        record = audits[point["id"]]
        base = record.get("base")
        selected_level = "refined" if point["refine_and_multistart"] else "base"
        selected = record.get(selected_level)
        best = selected["best"] if selected is not None else None
        complete = point["id"] not in missing
        changes = None
        refinement_pass = not point["refine_and_multistart"]
        if point["refine_and_multistart"] and best is not None and base is not None and base["best"] is not None:
            clean = table[point["channel"]]
            changes = [
                (best["theta"][2] - base["best"]["theta"][2]) / clean["dilations"]["sigma"][0],
                (best["theta"][3] - base["best"]["theta"][3]) / clean["dilations"]["sigma"][1],
                (best["log_dv_shift"] - base["best"]["log_dv_shift"]) / clean["sigma_dv"],
            ]
            refinement_pass = max(abs(v) for v in changes) < 0.01
        qualified = bool(
            complete
            and channel_gates[str(point["channel"])]["pass"]
            and refinement_pass
            and all(a["qualified_before_channel_and_refinement_checks"] for a in record.values())
        )
        finite = best["log_dv_shift"] / table[point["channel"]]["sigma_dv"] if best is not None else None
        linear = -point["a"] * table[point["channel"]]["response_dv"]
        rows.append(
            {
                "id": point["id"],
                "channel": point["channel"],
                "kind": point["kind"],
                "window": point.get("window"),
                "a": point["a"],
                "a_over_atol": point["a_over_atol"],
                "complete": complete,
                "unavailable": missing.get(point["id"], {}),
                "numerically_qualified": qualified,
                "finite_log_distance_over_clean_sigma": finite,
                "linear_log_distance_over_clean_sigma": linear,
                "finite_minus_linear_sigma": finite - linear if finite is not None else None,
                "within_one_clean_sigma": abs(finite) <= 1 if qualified else None,
                "quadrature_change_sigma": changes,
                "quadrature_pass": refinement_pass,
                "selected_level": selected_level,
                "selected_active_bounds": best["active_bounds"] if best else None,
                "selected_stationary": bool(selected is not None and selected["selected_interior_stationary"]),
                "all_starts_completed": complete and all(a["all_starts_completed"] for a in record.values()),
                "max_accepted_start_spread_sigma": max(
                    (a["accepted_start_spread_sigma"] for a in record.values()), default=None
                ),
            }
        )
    return {
        "schema": "finite_bao_qualification_report_v1",
        "protocol_sha256": protocol_hash,
        "frozen_table_sha256": protocol["provenance"]["files"]["dtv-paper2-bao-bound/data/channel_table.json"][
            "sha256"
        ],
        "reporter_sha256": file_sha256(__file__),
        "protocol_points": len(rows),
        "complete_protocol_points": sum(r["complete"] for r in rows),
        "study_complete": not missing,
        "allow_incomplete": allow_incomplete,
        "execution_identity": common or None,
        "numerically_qualified_points": sum(r["numerically_qualified"] for r in rows),
        "channel_small_amplitude_checks": channel_gates,
        "results": rows,
        "receipt_sha256": receipts,
        "scope": protocol["scope"],
        "limitations": protocol["limitations"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--frozen-table", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Include unavailable points, never relaxing identity or numerical qualification checks.",
    )
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    expected_table = protocol["provenance"]["files"]["dtv-paper2-bao-bound/data/channel_table.json"]["sha256"]
    if file_sha256(args.frozen_table) != expected_table:
        raise ValueError("report normalization table differs from the frozen table")
    table = {r["channel"]: r for r in json.loads(args.frozen_table.read_text(encoding="utf-8"))["channels"]}
    report = build_report(protocol, file_sha256(args.protocol), args.results, table, args.allow_incomplete)
    rows = report["results"]
    write(args.output, report)
    csv_path = args.output.with_suffix(".csv")
    with csv_path.open("x", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(
        json.dumps(
            {
                k: report[k]
                for k in ["complete_protocol_points", "numerically_qualified_points", "channel_small_amplitude_checks"]
            }
        )
    )


if __name__ == "__main__":
    main()
