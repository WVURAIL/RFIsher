"""Boundary tests for the source-bound control runner; no GPU or production draws."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

SPEC = importlib.util.spec_from_file_location(
    "channel29_control_runner", Path(__file__).parents[1] / "scripts/calibrate_channel29_controls_v1.py"
)
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def allocation(tmp_path):
    plan = {"protocol_sha256": M.PROTOCOL_SHA,
            "populations": [{"name": "off", "count_per_block": 1}],
            "stages": {"calibration": {"blocks": 1, "populations": ["off"]},
                       "evaluation": {"blocks": 1, "populations": ["off"]}},
            "audit": {"populations": ["off"]}}
    rows = [(s, 0, "off", 0, M.frame_seed(M.PROTOCOL_SHA, s, 0, "off", 0))
            for s in ("calibration", "evaluation", "audit")]
    folder = tmp_path / "preflight"
    folder.mkdir()
    np.savez(folder / "seed-exclusions.npz", raw_seed=np.array([], dtype=np.uint64),
             effective_seed63=np.array([], dtype=np.uint64))
    values = {"stage": np.array([r[0] for r in rows]), "block": np.array([0] * 3),
              "population": np.array(["off"] * 3), "frame": np.array([0] * 3),
              "raw_seed": np.array([r[4] for r in rows], dtype=np.uint64),
              "effective_seed63": np.array([r[4] % (1 << 63) for r in rows], dtype=np.uint64)}
    np.savez(folder / "planned-frame-seeds.npz", **values)
    return plan, rows, values


def test_seed_partition_checks_complete_distinct_coordinate_grid(tmp_path):
    plan, _, _ = allocation(tmp_path)
    assert M.check_seed_partition(tmp_path, plan)["frames"] == 3


def test_effective_seed_alias_to_prior_draw_is_refused(tmp_path):
    plan, rows, _ = allocation(tmp_path)
    seed = rows[0][4]
    np.savez(tmp_path / "preflight/seed-exclusions.npz",
             raw_seed=np.array([seed ^ (1 << 63)], dtype=np.uint64),
             effective_seed63=np.array([seed % (1 << 63)], dtype=np.uint64))
    with pytest.raises(ValueError, match="reuses development"):
        M.check_seed_partition(tmp_path, plan)


@pytest.mark.parametrize("change", ["missing", "duplicate", "coordinate", "effective"])
def test_changed_reserved_grid_is_refused(tmp_path, change):
    plan, _, values = allocation(tmp_path)
    if change == "missing":
        values = {k: v[:-1] for k, v in values.items()}
    elif change == "duplicate":
        values = {k: np.append(v, v[:1]) for k, v in values.items()}
    elif change == "coordinate":
        values["frame"][0] = 1
    else:
        values["effective_seed63"][0] ^= np.uint64(1)
    np.savez(tmp_path / "preflight/planned-frame-seeds.npz", **values)
    with pytest.raises(ValueError, match="coordinate grid"):
        M.check_seed_partition(tmp_path, plan)


@pytest.mark.parametrize("which", ["input", "source"])
def test_load_plan_refuses_changed_bound_file(tmp_path, monkeypatch, which):
    artifact = tmp_path / "source.txt"
    artifact.write_text("original")
    plan = {"schema": "channel29-residual-controls-v1", "status": "plan_frozen",
            "protocol_sha256": M.PROTOCOL_SHA, "statistics": M.STATISTICS,
            "populations": M.POPULATIONS, "stages": M.STAGES,
            "primary_cases": json.loads(json.dumps(M.PRIMARY_CASES)),
            "inputs": {}, "source_artifacts": {}}
    if which == "input":
        plan["inputs"]["waveform"] = {"path": str(artifact), "sha256": M.sha(artifact)}
    else:
        plan["source_artifacts"][str(artifact)] = {"sha256": M.sha(artifact)}
    plan["plan_sha256"] = M.canonical_digest(plan, "plan_sha256")
    dump(tmp_path / "plan.json", plan)
    artifact.write_text("changed")
    monkeypatch.setattr(M, "check_seed_partition", lambda *_: None)
    with pytest.raises(ValueError, match="changed"):
        M.load_plan(tmp_path)


def receipt_fixture(tmp_path):
    plan = {"plan_sha256": "a" * 64, "frozen_at": "2026-01-01T00:00:00Z",
            "stages": {"calibration": {"blocks": 1, "populations": ["off"]}}}
    shard = tmp_path / "calibration/block-0000/off.npz"
    shard.parent.mkdir(parents=True)
    np.savez(shard, marker=np.array([1], dtype=np.int64))
    bindings = {str(shard.relative_to(tmp_path)): M.sha(shard)}
    bound = {"schema": "channel29-digital-retained-set-bound-v1", "plan_sha256": plan["plan_sha256"],
             "frozen_at": "2026-01-03T00:00:00Z", "source_shards": bindings,
             "physical_calibration_qualified": False, "arms_telescope_confirmation": False,
             "calibration": {"status": "refused", "correction": None}}
    payload = tmp_path / "calibration.json"
    dump(payload, bound)
    receipt = {"schema": "channel29-residual-calibration-receipt-v1", "status": "calibration_frozen",
               "plan_sha256": plan["plan_sha256"], "frozen_at": "2026-01-04T00:00:00Z",
               "calibration": {"path": str(payload), "sha256": M.sha(payload)},
               "calibration_outputs": bindings}
    receipt["receipt_sha256"] = M.canonical_digest(receipt, "receipt_sha256")
    dump(tmp_path / "calibration-receipt.json", receipt)
    return plan, bound, receipt


def test_refused_outcome_can_be_frozen_without_becoming_a_finite_bound(tmp_path):
    plan, _, _ = receipt_fixture(tmp_path)
    assert M.load_receipt(tmp_path, plan)["status"] == "calibration_frozen"


@pytest.mark.parametrize("change", ["other_plan", "other_schema", "missing_sources"])
def test_receipt_must_bind_actual_calibration_contract(tmp_path, change):
    plan, bound, receipt = receipt_fixture(tmp_path)
    if change == "other_plan":
        bound["plan_sha256"] = "b" * 64
    elif change == "other_schema":
        bound["schema"] = "unrelated-calibration-v0"
    else:
        bound["source_shards"] = {}
    dump(tmp_path / "calibration.json", bound)
    receipt["calibration"]["sha256"] = M.sha(tmp_path / "calibration.json")
    receipt["receipt_sha256"] = M.canonical_digest(receipt, "receipt_sha256")
    dump(tmp_path / "calibration-receipt.json", receipt)
    with pytest.raises(ValueError):
        M.load_receipt(tmp_path, plan)


def test_changed_calibration_shard_is_refused(tmp_path):
    plan, _, _ = receipt_fixture(tmp_path)
    (tmp_path / "calibration/block-0000/off.npz").write_bytes(b"changed")
    with pytest.raises(ValueError, match="shard changed"):
        M.load_receipt(tmp_path, plan)


def stage_fixture(tmp_path, stage="calibration"):
    plan = {"plan_sha256": "a" * 64, "frozen_at": "2026-01-01T00:00:00Z",
            "geometry": {"channel": 29, "num_streams": 2048, "K": 128},
            "stages": {stage: {"blocks": 1, "populations": ["off"]}},
            "populations": [{"name": "off", "shelf_db": None, "reference_projection_gamma": 0., "count_per_block": 2}]}
    meta = {"plan_sha256": plan["plan_sha256"], "protocol_sha256": M.PROTOCOL_SHA,
            "stage": stage, "block_index": 0, "population": "off", "frames": 2,
            "nominal_injected_data_shelf_db": None, "reference_projection_gamma": 0.,
            "nominal_injected_data_shelf_linear": 0., "geometry": plan["geometry"],
            "target_norm_sq": M.TARGET_NORM_SQ, "reference_norm_sum_sq": M.REFERENCE_NORM_SUM_SQ,
            "started_utc": "2026-01-02T00:00:00Z", "completed_utc": "2026-01-02T00:01:00Z"}
    seeds = [M.frame_seed(M.PROTOCOL_SHA, stage, 0, "off", i) for i in range(2)]
    arrays = {"meta_json": np.array(json.dumps(meta)), "frame_seed": np.array(seeds, dtype=np.uint64),
              "frame_seed_effective63": np.array([s % (1 << 63) for s in seeds], dtype=np.uint64),
              "coarse_marginals_u64": np.array([[100, 100, 100]] * 2, dtype=np.uint64),
              "clip_fraction": np.zeros(2)}
    path = tmp_path / stage / "block-0000/off.npz"
    path.parent.mkdir(parents=True)
    np.savez(path, **arrays)
    path.with_suffix(".npz.sha256").write_text(M.sha(path))
    return plan, meta, arrays, path


@pytest.mark.parametrize("change", ["population", "seed", "before_freeze", "future_completion", "geometry", "norm", "truth"])
def test_stage_refuses_identity_and_time_changes(tmp_path, monkeypatch, change):
    plan, meta, arrays, path = stage_fixture(tmp_path)
    monkeypatch.setattr(M, "assemble_cases", lambda _: {})
    monkeypatch.setattr(M, "now", lambda: "2026-01-05T00:00:00Z")
    if change == "population":
        meta["population"] = "different"
    elif change == "seed":
        arrays["frame_seed"][0] ^= np.uint64(1)
    elif change == "before_freeze":
        meta["started_utc"] = plan["frozen_at"]
    elif change == "future_completion":
        meta["completed_utc"] = "2099-01-01T00:00:00Z"
    elif change == "geometry":
        meta["geometry"] = {"channel": 14}
    elif change == "norm":
        meta["target_norm_sq"] = 6338
    else:
        meta["nominal_injected_data_shelf_linear"] = .1
    arrays["meta_json"] = np.array(json.dumps(meta))
    np.savez(path, **arrays)
    path.with_suffix(".npz.sha256").write_text(M.sha(path))
    with pytest.raises(ValueError):
        M.load_stage(tmp_path, plan, "calibration")


def test_evaluation_cannot_start_before_calibration_receipt(tmp_path, monkeypatch):
    plan, _, _, _ = stage_fixture(tmp_path, "evaluation")
    monkeypatch.setattr(M, "load_receipt", lambda *_: {"frozen_at": "2026-01-03T00:00:00Z"})
    with pytest.raises(ValueError, match="freeze boundary"):
        M.load_stage(tmp_path, plan, "evaluation")


def test_shard_grid_cannot_silently_omit_a_prescribed_population(tmp_path):
    plan, _, _, path = stage_fixture(tmp_path)
    path.unlink()
    with pytest.raises(ValueError, match="missing or unexpected"):
        M.load_stage(tmp_path, plan, "calibration")


def test_consistent_stage_can_be_read_without_certifying_physical_performance(tmp_path, monkeypatch):
    plan, _, _, _ = stage_fixture(tmp_path)
    monkeypatch.setattr(M, "assemble_cases", lambda _: {})
    _, populations, identities = M.load_stage(tmp_path, plan, "calibration")
    assert populations["calibration:0000"]["off"]["frames"] == 2
    assert len(identities) == 1


def test_sidecar_mismatch_refused_before_array_decode(tmp_path, monkeypatch):
    plan, _, _, path = stage_fixture(tmp_path)
    path.with_suffix(".npz.sha256").write_text("0" * 64)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("array decoder must not run before checksum verification")

    monkeypatch.setattr(M.np, "load", forbidden)
    with pytest.raises(ValueError, match="digest mismatch"):
        M.load_stage(tmp_path, plan, "calibration")


@pytest.mark.parametrize("change", ["failed", "wrong_plan", "incomplete", "digest"])
def test_fit_requires_authenticated_complete_passing_device_audit_before_data(tmp_path, monkeypatch, change):
    plan = {"plan_sha256": "a" * 64}
    audit = {"plan_sha256": plan["plan_sha256"], "passed": True,
             "rows": [{"population": p["name"]} for p in M.POPULATIONS]}
    if change == "failed":
        audit["passed"] = False
    elif change == "wrong_plan":
        audit["plan_sha256"] = "b" * 64
    elif change == "incomplete":
        audit["rows"] = audit["rows"][:-1]
    path = tmp_path / "audit/device_audit.json"
    dump(path, audit)
    path.with_suffix(".json.sha256").write_text("0" * 64 if change == "digest" else M.sha(path))
    monkeypatch.setattr(M, "load_plan", lambda _: plan)

    def forbidden(*_args):
        raise AssertionError("calibration data must stay unread until device-audit gate passes")

    monkeypatch.setattr(M, "load_stage", forbidden)
    with pytest.raises(ValueError):
        M.fit(tmp_path)
