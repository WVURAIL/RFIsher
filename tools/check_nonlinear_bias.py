#!/usr/bin/env python3
"""Run frozen finite-amplitude expected-likelihood checks, saving every start."""

import argparse
import hashlib
import json
import os
import platform
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import radiofisher
import scipy

import rfisher
from rfisher import bands, forecast, nonlinear
from rfisher.nonlinear import build_model
from rfisher.pk_cache import file_sha256


def write(path, value):
    """Publish one complete, payload-checked receipt without overwriting results."""
    if path.exists():
        raise FileExistsError(path)
    value = dict(value, record_path_name=path.name)
    value["record_sha256"] = payload_digest(value)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    with temporary.open("x", encoding="utf-8", newline="\n") as f:
        json.dump(value, f, indent=2, allow_nan=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    if path.exists():
        raise FileExistsError(path)
    temporary.replace(path)


def payload_digest(value):
    clean = {k: v for k, v in value.items() if k != "record_sha256"}
    return hashlib.sha256(
        json.dumps(clean, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def read_receipt(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("record_path_name") != path.name or data.get("record_sha256") != payload_digest(data):
        raise ValueError("result payload or filename differs: " + str(path))
    return data


def verify_frozen_sources(protocol, frozen_inputs):
    roots = {
        "RFIsher": Path(rfisher.__file__).resolve().parents[2],
        "RadioFisher": Path(radiofisher.__file__).resolve().parents[2],
    }
    checked = {}
    for key, entry in protocol["provenance"]["files"].items():
        repo, rel = key.split("/", 1)
        snapshot = frozen_inputs / key
        if file_sha256(snapshot) != entry["sha256"]:
            raise ValueError("frozen input snapshot differs: " + key)
        if repo in roots and file_sha256(roots[repo] / rel) != entry["sha256"]:
            raise ValueError("frozen source/data differs: " + key)
        checked[key] = entry["sha256"]
    return checked


def load_bound(path, execution_hash):
    data = read_receipt(path)
    if data["execution_sha256"] != execution_hash:
        raise ValueError("existing result belongs to another execution: " + str(path))
    return data


def base_record(output, channel, point_id, execution, protocol):
    base = output / f"ch{channel}" / "base"
    expected = dict(execution, level="base", quadrature=protocol["numerical_protocol"]["base_quadrature"])
    expected["fit_command"] = list(execution["fit_command"])
    expected["fit_command"][expected["fit_command"].index("--level") + 1] = "base"
    ep = base / "execution.json"
    if read_receipt(ep)["contract"] != expected:
        raise ValueError("base result execution does not match refinement")
    result = load_bound(base / f"{point_id}.json", file_sha256(ep))
    if result["point"]["id"] != point_id:
        raise ValueError("base point identity differs")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--frozen-table", type=Path, required=True)
    parser.add_argument("--frozen-inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--channel", type=int, required=True)
    parser.add_argument("--level", choices=["base", "refined"], default="base")
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    points = [p for p in protocol["points"] if p["channel"] == args.channel]
    if not points:
        raise ValueError("channel not in frozen protocol")
    checked = verify_frozen_sources(protocol, args.frozen_inputs)
    table_entry = protocol["provenance"]["files"]["dtv-paper2-bao-bound/data/channel_table.json"]
    if file_sha256(args.frozen_table) != table_entry["sha256"]:
        raise ValueError("frozen table differs")
    table = next(r for r in json.loads(args.frozen_table.read_text())["channels"] if r["channel"] == args.channel)
    out = args.output / f"ch{args.channel}" / args.level
    out.mkdir(parents=True, exist_ok=True)
    orders = protocol["numerical_protocol"]["base_quadrature" if args.level == "base" else "refined_quadrature"]
    execution = {
        "schema": "finite_bao_execution_v1",
        "protocol_sha256": file_sha256(args.protocol),
        "implementation": {
            str(nonlinear.__file__): file_sha256(nonlinear.__file__),
            str(Path(__file__).resolve()): file_sha256(__file__),
        },
        "frozen_sources": checked,
        "frozen_table_sha256": file_sha256(args.frozen_table),
        "runtime": {"python": sys.version, "numpy": np.__version__, "scipy": scipy.__version__, "platform": platform.platform()},
        "fit_command": [
            sys.executable,
            str(Path(__file__).resolve()),
            "--protocol",
            str(args.protocol),
            "--frozen-table",
            str(args.frozen_table),
            "--frozen-inputs",
            str(args.frozen_inputs),
            "--output",
            str(args.output),
            "--channel",
            str(args.channel),
            "--level",
            args.level,
        ],
        "thread_environment": {
            name: os.environ.get(name) for name in ["OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"]
        },
        "channel": args.channel,
        "level": args.level,
        "quadrature": orders,
        "optimizer": {"method": "L-BFGS-B", "ftol": 1e-15, "gtol": 1e-9, "maxiter": 600, "maxls": 50},
        "scope": protocol["scope"],
    }
    ep = out / "execution.json"
    if ep.exists():
        if read_receipt(ep)["contract"] != execution:
            raise ValueError("execution identity differs")
    else:
        write(
            ep,
            {
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "initial_invocation": sys.argv,
                "contract": execution,
            },
        )
    eh = file_sha256(ep)
    started = time.perf_counter()
    p = forecast.prepare(bands.channel(args.channel))
    model, identity = build_model(p, out / "quadrature", **orders)
    seconds = time.perf_counter() - started
    pre = out / "preflight.json"
    if pre.exists():
        preflight = load_bound(pre, eh)
    else:
        check = model.derivative_check()
        H = model.curvature(model.theta0, 0)
        scale = np.sqrt(np.diag(model.fisher))
        herror = float(np.max(np.abs((H - model.fisher) / np.outer(scale, scale))))
        response = float((2 * model.linear_shift[2] + model.linear_shift[3]) / 3 / model.sigma_dv)
        table_errors = {
            "sigma_dv": abs(model.sigma_dv / table["sigma_dv"] - 1),
            "response_dv": abs(response / table["response_dv"] - 1),
        }
        preflight = {
            "execution_sha256": eh,
            "nodes": len(model.k),
            "build_seconds": seconds,
            "derivatives": check,
            "fiducial_signal_ratio_max_error": float(np.max(np.abs(model.signal_ratio(model.theta0) - 1))),
            "clean_hessian_normalized_max_error": herror,
            "table_relative_errors": table_errors,
            "theta0": model.theta0.tolist(),
            "sigma": model.scale.tolist(),
            "sigma_dv": model.sigma_dv,
            "response_dv": response,
            "linear_shift": model.linear_shift.tolist(),
            "a_tol": model.a_tol,
            "fisher": model.fisher.tolist(),
            "covariance": model.covariance.tolist(),
            "bias_row": model.bias_row.tolist(),
            "domain": model.domain(),
            "quadrature_identity": identity,
            "pass_derivative_and_table_gates": bool(
                np.max(np.abs(model.signal_ratio(model.theta0) - 1)) <= 1e-12
                and max(check["numeric_relative_l2"] + check["piecewise_gradient_relative_l2"]) <= 1e-3
                and herror <= 1e-3
                and max(table_errors.values()) <= 1e-3
            ),
        }
        write(pre, preflight)
    print(
        json.dumps(
            {
                "channel": args.channel,
                "level": args.level,
                "nodes": len(model.k),
                "build_seconds": seconds,
                "preflight_pass": preflight["pass_derivative_and_table_gates"],
            }
        ),
        flush=True,
    )
    if args.preflight_only or not preflight["pass_derivative_and_table_gates"]:
        return
    points = sorted(points, key=lambda v: (v["a"], v["id"]))
    previous = model.theta0.copy()
    for point in points:
        if args.level == "refined" and not point["refine_and_multistart"]:
            base = args.output / f"ch{args.channel}" / "base" / f"{point['id']}.json"
            if base.exists():
                got = base_record(args.output, args.channel, point["id"], execution, protocol)
                best = got.get("best")
                if best is not None:
                    previous = np.array(best["theta"])
            continue
        summary_path = out / f"{point['id']}.json"
        if summary_path.exists():
            got = load_bound(summary_path, eh)
            if got.get("best") is not None:
                previous = np.array(got["best"]["theta"])
            continue
        a = point["a"]
        starts = {"fiducial": model.theta0.copy()}
        if a > 0:
            starts["fisher"] = model.theta0 + a * model.linear_shift
        if point["refine_and_multistart"]:
            starts["continuation"] = previous.copy()
        results = []
        for name, start in starts.items():
            path = out / f"{point['id']}.{name}.json"
            if path.exists():
                result = load_bound(path, eh)
            else:
                tick = time.perf_counter()
                try:
                    fit = model.fit(a, start=start)
                    theta = np.array(fit["theta"])
                    try:
                        H = model.curvature(theta, a) * np.outer(model.scale, model.scale)
                        eigen = np.linalg.eigvalsh(H).tolist()
                    except ValueError:
                        eigen = None
                    fit["scaled_hessian_eigenvalues"] = eigen
                    fit["interior_stationary_minimum"] = bool(
                        not fit["active_bounds"]
                        and fit["fisher_metric_gradient_norm"] <= 1e-5
                        and eigen is not None
                        and min(eigen) > 0
                    )
                    result = {
                        "execution_sha256": eh,
                        "point": point,
                        "start": name,
                        "start_theta": start.tolist(),
                        "result": fit,
                        "seconds": time.perf_counter() - tick,
                        "status": "completed",
                    }
                except Exception as exc:  # noqa: BLE001 - retain every failed fit as an explicit result.
                    result = {
                        "execution_sha256": eh,
                        "point": point,
                        "start": name,
                        "start_theta": start.tolist(),
                        "seconds": time.perf_counter() - tick,
                        "status": "failed",
                        "error": repr(exc),
                    }
                write(path, result)
            results.append(result)
            print(
                json.dumps(
                    {
                        "point": point["id"],
                        "level": args.level,
                        "start": name,
                        "status": result["status"],
                        "seconds": result["seconds"],
                        "gradient_norm": result.get("result", {}).get("fisher_metric_gradient_norm"),
                    }
                ),
                flush=True,
            )
        fits = [r["result"] for r in results if r["status"] == "completed"]
        best = min(fits, key=lambda v: v["objective"]) if fits else None
        accepted = [v for v in fits if v["interior_stationary_minimum"]]
        spread = 0.0
        if len(accepted) > 1:
            coordinates = np.array(
                [
                    [v["theta"][2] / model.scale[2], v["theta"][3] / model.scale[3], v["log_dv_shift"] / model.sigma_dv]
                    for v in accepted
                ]
            )
            spread = float(np.max(np.ptp(coordinates, axis=0)))
        summary = {
            "execution_sha256": eh,
            "point": point,
            "starts": list(starts),
            "best": best,
            "accepted_stationary_starts": len(accepted),
            "accepted_start_max_spread_sigma": spread,
            "ambiguous": spread >= 0.01,
            "qualification_pending_aggregation": True,
        }
        if best is not None:
            previous = np.array(best["theta"])
            summary["finite_log_distance_over_clean_sigma"] = best["log_dv_shift"] / table["sigma_dv"]
            summary["linear_log_distance_over_clean_sigma"] = -a * table["response_dv"]
            if 0 < point["a_over_atol"] <= 0.01:
                delta = np.array(best["shift"])
                linear = a * model.linear_shift
                difference = delta - linear
                q = delta / (point["a_over_atol"] * model.scale)
                q0 = point["a_tol"] * model.linear_shift / model.scale
                norm = float(np.sqrt(difference @ model.fisher @ difference / (linear @ model.fisher @ linear)))
                summary["small_amplitude"] = {
                    "q": q.tolist(),
                    "q0": q0.tolist(),
                    "fisher_relative_slope_error": norm,
                    "coordinate_pass": bool(np.all(np.abs(q - q0) <= 0.01 * np.maximum(1, np.abs(q0)))),
                    "fisher_norm_pass": norm <= 0.01,
                }
            if args.level == "refined":
                bp = args.output / f"ch{args.channel}" / "base" / f"{point['id']}.json"
                if not bp.exists():
                    raise ValueError("refinement lacks the matching base result")
                base = base_record(args.output, args.channel, point["id"], execution, protocol)
                b = base.get("best")
                if b is not None:
                    changes = [
                        (best["theta"][2] - b["theta"][2]) / table["dilations"]["sigma"][0],
                        (best["theta"][3] - b["theta"][3]) / table["dilations"]["sigma"][1],
                        (best["log_dv_shift"] - b["log_dv_shift"]) / table["sigma_dv"],
                    ]
                    summary["quadrature_change_sigma"] = changes
                    summary["quadrature_pass"] = max(abs(v) for v in changes) < 0.01
        write(summary_path, summary)


if __name__ == "__main__":
    main()
