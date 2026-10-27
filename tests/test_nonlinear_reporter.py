"""Qualification must fail closed on provenance, missing fits, and wrong branches."""

import copy
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

TOOLS = Path(__file__).parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
try:
    SPEC = importlib.util.spec_from_file_location("nonlinear_reporter", TOOLS / "report_nonlinear_bias.py")
    reporter = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(reporter)
finally:
    sys.path.pop(0)

PROTOCOL_HASH = "c" * 64
TABLE_KEY = "dtv-paper2-bao-bound/data/channel_table.json"
THETA0 = np.array([1.0, 49.0, 1.0, 1.0, 0.8, 1.0])
LINEAR = np.array([0.1, 0.2, 1.0, 1.0, 0.3, 0.4])


def make_protocol(channels=(14,), full=False):
    points = []
    for channel in channels:
        for fraction in [0, 0.001, 0.01, 1] if full else [0.001, 1]:
            points.append(
                {
                    "id": f"ch{channel}_fraction_{fraction}",
                    "channel": channel,
                    "kind": "fixed_fraction",
                    "a": fraction * 0.001,
                    "a_tol": 0.001,
                    "a_over_atol": fraction,
                    "refine_and_multistart": fraction == 1,
                }
            )
        if full and channel != 31:
            for window, fraction in [("full", 0.7), ("last", 0.9)]:
                points.append(
                    {
                        "id": f"ch{channel}_{window}",
                        "channel": channel,
                        "kind": "actual_guard",
                        "window": window,
                        "a": fraction * 0.001,
                        "a_tol": 0.001,
                        "a_over_atol": fraction,
                        "refine_and_multistart": True,
                    }
                )
    return {
        "points": points,
        "provenance": {"files": {TABLE_KEY: {"sha256": "d" * 64}, "RFIsher/data.dat": {"sha256": "e" * 64}}},
        "numerical_protocol": {
            "base_quadrature": {"order_k": 8, "order_mu": 16},
            "refined_quadrature": {"order_k": 16, "order_mu": 32},
        },
        "scope": "Synthetic receipts test qualification logic, not numerical accuracy.",
        "limitations": ["No measured fits in this fixture."],
    }


def make_table(protocol):
    return {
        point["channel"]: {"sigma_dv": 0.5, "response_dv": 2.0, "dilations": {"sigma": [0.2, 0.3]}}
        for point in protocol["points"]
    }


def make_contract(protocol, channel, level):
    return {
        "protocol_sha256": PROTOCOL_HASH,
        "channel": channel,
        "level": level,
        "quadrature": protocol["numerical_protocol"][f"{level}_quadrature"],
        "implementation": {"/src/nonlinear.py": "a" * 64, "/tools/check_nonlinear_bias.py": "b" * 64},
        "frozen_sources": {key: entry["sha256"] for key, entry in protocol["provenance"]["files"].items()},
        "frozen_table_sha256": protocol["provenance"]["files"][TABLE_KEY]["sha256"],
        "runtime": {"python": "test"},
        "optimizer": {"method": "L-BFGS-B"},
        "thread_environment": {"OMP_NUM_THREADS": "1"},
        "fit_command": ["python", "runner", "--channel", str(channel), "--level", level],
    }


def make_fit(point):
    shift = point["a"] * LINEAR
    theta = THETA0 + shift
    return {
        "objective": -(point["a"] ** 2),
        "theta": theta.tolist(),
        "shift": shift.tolist(),
        "log_dv_shift": float(-(2 * np.log(theta[2]) + np.log(theta[3])) / 3),
        "active_bounds": [],
        "fisher_metric_gradient_norm": 1e-9,
        "scaled_hessian_eigenvalues": [1.0] * 6,
    }


def save_study(root, protocol, contract_change=None, fit_change=None, preflight_change=None):
    """Write the study with the production receipt writer and its filename and payload binding."""
    for channel in sorted({p["channel"] for p in protocol["points"]}):
        for level in ["base", "refined"]:
            folder = root / f"ch{channel}" / level
            folder.mkdir(parents=True)
            contract = make_contract(protocol, channel, level)
            if contract_change:
                contract_change(contract)
            ep = folder / "execution.json"
            reporter.write(ep, {"contract": contract})
            execution_hash = reporter.file_sha256(ep)
            preflight = {
                "execution_sha256": execution_hash,
                "pass_derivative_and_table_gates": True,
                "sigma": [1.0] * 6,
                "sigma_dv": 1000.0,
                "linear_shift": LINEAR.tolist(),
                "fisher": np.eye(6).tolist(),
            }
            if preflight_change:
                preflight_change(preflight)
            reporter.write(folder / "preflight.json", preflight)
            for point in protocol["points"]:
                if point["channel"] != channel or (level == "refined" and not point["refine_and_multistart"]):
                    continue
                starts = ["fiducial"] + (["fisher"] if point["a"] else [])
                if point["refine_and_multistart"]:
                    starts.append("continuation")
                fits = []
                for start in starts:
                    fit = make_fit(point)
                    if fit_change:
                        fit_change(fit, point, level, start)
                    fits.append(fit)
                    reporter.write(
                        folder / f"{point['id']}.{start}.json",
                        {
                            "execution_sha256": execution_hash,
                            "point": point,
                            "start": start,
                            "status": "completed",
                            "result": fit,
                        },
                    )
                reporter.write(
                    folder / f"{point['id']}.json",
                    {
                        "execution_sha256": execution_hash,
                        "point": point,
                        "starts": starts,
                        "best": min(fits, key=lambda fit: fit["objective"]),
                    },
                )


def build(root, protocol, **kwargs):
    return reporter.build_report(protocol, PROTOCOL_HASH, root, make_table(protocol), **kwargs)


def high_row(report):
    return next(row for row in report["results"] if row["a_over_atol"] == 1)


def test_full_52_point_plan_is_complete_and_uses_original_table(tmp_path):
    protocol = make_protocol((14, 16, 18, 21, 25, 26, 29, 32, 31), full=True)
    save_study(tmp_path, protocol)
    report = build(tmp_path, protocol)
    assert report["study_complete"]
    assert report["protocol_points"] == report["complete_protocol_points"] == 52
    assert report["numerically_qualified_points"] == 52
    assert set(report["channel_small_amplitude_checks"]) == {str(c) for c in make_table(protocol)}
    row = high_row(report)
    assert row["finite_log_distance_over_clean_sigma"] == pytest.approx(-np.log1p(0.001) / 0.5)
    assert row["linear_log_distance_over_clean_sigma"] == pytest.approx(-0.002)


def test_boundary_best_cannot_be_replaced_by_interior_higher_objective(tmp_path):
    protocol = make_protocol()

    def change(fit, point, level, start):
        if point["a_over_atol"] == 1 and start == "fiducial":
            fit["active_bounds"] = ["A:lower"]
            fit["objective"] -= 1

    save_study(tmp_path, protocol, fit_change=change)
    row = high_row(build(tmp_path, protocol))
    assert row["all_starts_completed"]
    assert not row["selected_stationary"]
    assert row["selected_active_bounds"] == ["A:lower"]
    assert not row["numerically_qualified"]
    assert row["within_one_clean_sigma"] is None


def test_ambiguous_multistart_uses_frozen_table_sigma_not_preflight_sigma(tmp_path):
    protocol = make_protocol()

    def change(fit, point, level, start):
        if point["a_over_atol"] == 1 and start == "fisher":
            fit["theta"][2] += 0.004  # 0.02 of the table's sigma_perp (0.2) and 0.004 of the preflight sigma (1.0)
            fit["objective"] += 1

    save_study(tmp_path, protocol, fit_change=change)
    row = high_row(build(tmp_path, protocol))
    assert row["selected_stationary"]
    assert row["max_accepted_start_spread_sigma"] == pytest.approx(0.02)
    assert not row["numerically_qualified"]


@pytest.mark.parametrize("level", ["base", "refined"])
def test_wrong_quadrature_is_refused_even_in_partial_mode(tmp_path, level):
    protocol = make_protocol()

    def change(contract):
        if contract["level"] == level:
            contract["quadrature"] = {"order_k": 3, "order_mu": 5}

    save_study(tmp_path, protocol, contract_change=change)
    with pytest.raises(ValueError, match="quadrature"):
        build(tmp_path, protocol, allow_incomplete=True)


@pytest.mark.parametrize("field", ["frozen_sources", "frozen_table_sha256", "protocol_sha256"])
def test_wrong_frozen_identity_is_refused(tmp_path, field):
    protocol = make_protocol()

    def change(contract):
        contract[field] = {} if field == "frozen_sources" else "f" * 64

    save_study(tmp_path, protocol, contract_change=change)
    with pytest.raises(ValueError, match="protocol"):
        build(tmp_path, protocol)


@pytest.mark.parametrize("field", ["implementation", "runtime", "optimizer", "thread_environment"])
def test_mixed_cross_channel_execution_is_refused(tmp_path, field):
    protocol = make_protocol((14, 16))

    def change(contract):
        if contract["channel"] == 16:
            key = next(iter(contract[field]))
            contract[field][key] = "f" * 64 if field == "implementation" else "changed"

    save_study(tmp_path, protocol, contract_change=change)
    with pytest.raises(ValueError, match="mixed execution"):
        build(tmp_path, protocol)


def test_refined_command_must_match_base(tmp_path):
    protocol = make_protocol()

    def change(contract):
        if contract["level"] == "refined":
            contract["fit_command"][0] = "different-python"

    save_study(tmp_path, protocol, contract_change=change)
    with pytest.raises(ValueError, match="base/refined"):
        build(tmp_path, protocol)


def test_missing_refinement_requires_explicit_partial_mode_and_never_substitutes_base(tmp_path):
    protocol = make_protocol()
    save_study(tmp_path, protocol)
    point = protocol["points"][-1]
    (tmp_path / "ch14" / "refined" / f"{point['id']}.json").unlink()
    with pytest.raises(reporter.IncompleteStudyError, match="refined"):
        build(tmp_path, protocol)
    report = build(tmp_path, protocol, allow_incomplete=True)
    row = high_row(report)
    assert not report["study_complete"]
    assert report["complete_protocol_points"] == 1
    assert row["selected_level"] == "refined"
    assert row["finite_log_distance_over_clean_sigma"] is None
    assert not row["numerically_qualified"]
    assert not row["all_starts_completed"]
    assert set(row["unavailable"]) == {"refined"}


def test_missing_planned_start_is_not_silently_dropped(tmp_path):
    protocol = make_protocol()
    save_study(tmp_path, protocol)
    point = protocol["points"][-1]
    (tmp_path / "ch14" / "base" / f"{point['id']}.continuation.json").unlink()
    with pytest.raises(reporter.IncompleteStudyError, match="continuation"):
        build(tmp_path, protocol)


def test_tampered_result_is_never_accepted_in_partial_mode(tmp_path):
    protocol = make_protocol()
    save_study(tmp_path, protocol)
    path = tmp_path / "ch14" / "base" / f"{protocol['points'][0]['id']}.fiducial.json"
    value = json.loads(path.read_text())
    value["result"]["theta"][0] += 1
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="payload"):
        build(tmp_path, protocol, allow_incomplete=True)


def test_failed_preflight_can_be_reported_only_as_explicitly_incomplete(tmp_path):
    protocol = make_protocol()
    save_study(tmp_path, protocol, preflight_change=lambda pre: pre.update(pass_derivative_and_table_gates=False))
    with pytest.raises(reporter.IncompleteStudyError, match="preflight failed"):
        build(tmp_path, protocol)
    report = build(tmp_path, protocol, allow_incomplete=True)
    assert report["complete_protocol_points"] == report["numerically_qualified_points"] == 0
    assert not report["study_complete"]


def test_small_amplitude_failure_disqualifies_otherwise_valid_highpoint(tmp_path):
    protocol = make_protocol()

    def change(fit, point, level, start):
        if point["a_over_atol"] == 0.001:
            fit["shift"] = (2 * np.asarray(fit["shift"])).tolist()

    save_study(tmp_path, protocol, fit_change=change)
    report = build(tmp_path, protocol)
    assert not report["channel_small_amplitude_checks"]["14"]["pass"]
    assert not high_row(report)["numerically_qualified"]


def test_implementation_hash_map_requires_both_sources():
    protocol = make_protocol()
    contract = make_contract(protocol, 14, "base")
    del contract["implementation"]["/src/nonlinear.py"]
    with pytest.raises(ValueError, match="implementation hashes"):
        reporter.validate_contract(contract, 14, "base", protocol, PROTOCOL_HASH, {})


def test_original_table_refinement_scale_is_enforced(tmp_path):
    protocol = make_protocol()

    def change(fit, point, level, start):
        if level == "refined":
            fit["theta"][3] += 0.006

    save_study(tmp_path, protocol, fit_change=change)
    row = high_row(build(tmp_path, protocol))
    assert row["quadrature_change_sigma"][1] == pytest.approx(0.02)
    assert not row["quadrature_pass"]
    assert not row["numerically_qualified"]


def test_duplicate_protocol_point_ids_are_refused(tmp_path):
    protocol = make_protocol()
    protocol["points"].append(copy.deepcopy(protocol["points"][0]))
    with pytest.raises(ValueError, match="unique point IDs"):
        build(tmp_path, protocol)
