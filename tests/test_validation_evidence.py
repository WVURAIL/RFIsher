from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pytest

from rfisher_results.validation.coverage import binomial_lower, evaluate_replicates
from rfisher_results.validation.holdout import audit_future_cohort
from rfisher_results.validation.null_states import StateRecord, join_null_state
from rfisher_results.validation.visibility import (
    compare_beamformed_files, frequency_coverage, paired_complex_summary, propagate_linear_moments,
)


def test_exact_coverage_does_not_call_sixty_successes_certainty():
    assert binomial_lower(60, 60) == pytest.approx(.05**(1/60))
    assert .95 < binomial_lower(60, 60) < .96
    assert binomial_lower(60, 60, alpha=.05/12) < .92
    assert binomial_lower(0, 60) == 0
    assert binomial_lower(0, 0) is None


def test_unsupported_replicates_are_not_dropped_from_success_denominator():
    rows = [{"id": "empty", "kept": 0, "claim": None, "truth": None},
            {"id": "under", "kept": 30, "claim": .9, "truth": 1.},
            {"id": "good", "kept": 40, "claim": 1., "truth": 1.}]
    result = evaluate_replicates(rows)
    assert result["trials"] == 3
    assert result["successes"] == result["underbooked"] == result["unsupported"] == 1
    assert result["success_probability_lower_marginal"] == binomial_lower(1, 3)
    with pytest.raises(ValueError, match="unique"):
        evaluate_replicates([rows[2], rows[2]])


@pytest.mark.parametrize("row", [
    {"id": "a", "kept": 30, "claim": np.nan, "truth": 0},
    {"id": "a", "kept": 30, "claim": 1, "truth": -1},
    {"id": "a", "kept": 0, "claim": 0, "truth": 0},
])
def test_invalid_coverage_means_refuse(row):
    with pytest.raises(ValueError):
        evaluate_replicates([row])


def test_actual_band_b_edges_have_no_dtv_overlap():
    centre = 707.8125 - np.arange(256)*.390625
    report = frequency_coverage(centre, np.full(256, .390625))
    assert report["nominal_edges_mhz"] == [608.0078125, 708.0078125]
    assert report["target_overlap_mhz"] == 0
    assert not report["covers_entire_target"]
    # Overlapping bins cover their union, not the sum of their widths.
    assert frequency_coverage([1, 2], [2, 2], target=(0, 3))["target_overlap_mhz"] == 3


def test_common_support_prevents_mask_changes_from_looking_like_attenuation():
    before = np.array([1+1j, 1000+0j, np.nan+0j, 0j])
    after = np.array([1+1j, 0j, 1j, 3j])
    result = paired_complex_summary(before, after, [1, 1, 1, 0], [1, 0, 1, 1])
    assert result["common_valid_cells"] == 1
    assert result["before_only_valid_cells"] == 1
    assert result["after_only_valid_cells"] == 2
    assert result["difference_energy_over_before"] == 0
    assert result["after_energy_over_before"] == 1


def test_complex_rotation_preserves_power_but_changes_coherent_mean():
    # Conjugating the wrong side or propagating only diagonal powers fails here.
    operator = np.array([[1, 1j], [0, 2j]])
    mean = np.array([1, 1j])
    covariance = np.array([[2, 1j], [-1j, 2]])
    mu, cov = propagate_linear_moments(operator, mean, covariance)
    np.testing.assert_allclose(mu, [0, -2])
    np.testing.assert_allclose(cov, [[6, 6], [6, 8]])
    with pytest.raises(ValueError, match="semidefinite"):
        propagate_linear_moments(np.eye(2), mean, [[1, 2], [2, 1]])
    with pytest.raises(ValueError, match="Hermitian"):
        propagate_linear_moments(np.eye(2), mean, [[1, 1j], [1j, 1]])


START = datetime(2026, 1, 1, tzinfo=timezone.utc)
END = START + timedelta(seconds=10)


def record(transmitter="A", start=START, end=END, state="off", reviewed=True):
    return StateRecord(transmitter, start, end, state, "a"*64, "b"*64 if reviewed else None)


def test_one_signoff_never_proves_allocation_null():
    result = join_null_state(START, END, ["A", "B"], [record()], candidate_scope_review_sha256="c"*64)
    assert result["null_state"] == "unknown"
    assert result["transmitter_states"] == {"A": "off", "B": "unknown"}


def test_null_requires_full_time_scope_and_reviewed_independence():
    for records, scope in [([record()], None), ([record(reviewed=False)], "c"*64),
                           ([record(end=END-timedelta(seconds=1))], "c"*64)]:
        assert join_null_state(START, END, ["A"], records, candidate_scope_review_sha256=scope)["null_state"] == "unknown"
    middle = START + timedelta(seconds=5)
    records = [record(end=middle), record(start=middle)]
    assert join_null_state(START, END, ["A"], records, candidate_scope_review_sha256="c"*64)["null_state"] == "off_for_reviewed_scope"
    records.append(record(start=middle, state="on"))
    assert join_null_state(START, END, ["A"], records, candidate_scope_review_sha256="c"*64)["null_state"] == "unknown"


def test_on_state_and_half_open_boundaries():
    records = [record(), record(start=END, end=END+timedelta(seconds=1), state="on")]
    assert join_null_state(START, END, ["A"], records, candidate_scope_review_sha256="c"*64)["null_state"] == "off_for_reviewed_scope"
    assert join_null_state(START, END, ["A"], [record(state="on")])["null_state"] == "not_null"


def test_beam_pair_rejects_extra_day_and_axis_permutation(tmp_path):
    h5py = pytest.importorskip("h5py")

    def create(path, days, positions):
        with h5py.File(path, "w") as h:
            h.attrs["__memh5_subclass"] = "draco.core.containers.FitFormedBeamEW"
            h.attrs["lsd"] = days
            maps = {"object_id": [b"source"], "pol": [b"XX"], "freq": [700., 699.], "ew": [0.]}
            for axis, values in maps.items():
                h.create_dataset(f"index_map/{axis}", data=values)
            h.create_dataset("position", data=np.array([positions], dtype=[("ra", float), ("dec", float)]))
            for name, values in [("beam", np.ones((1, 1, 2, 1), complex)), ("weight", np.ones((1, 1, 2, 1)))]:
                ds = h.create_dataset(name, data=values)
                ds.attrs["axis"] = list(maps)

    before, after = tmp_path/"before.h5", tmp_path/"after.h5"
    create(before, [1, 2], (10., 20.))
    create(after, [1, 2], (10.+1e-14, 20.))
    assert not compare_beamformed_files(before, after)["refusal_reasons"]
    with h5py.File(after, "r+") as h:
        h.attrs["lsd"] = [1]
    result = compare_beamformed_files(before, after)
    assert result["diagnostics"] is None
    assert result["before_only_days"] == [2]
    with h5py.File(after, "r+") as h:
        h.attrs["lsd"] = [1, 2]
        h["index_map/freq"][:] = [699., 700.]
    assert "different freq coordinates" in compare_beamformed_files(before, after)["refusal_reasons"]


def test_holdout_cannot_reuse_an_event_at_another_frequency():
    units = [{"event": "123", "unit_id": "123:506", "start": END},
             {"event": "123", "unit_id": "123:521", "start": END}]
    result = audit_future_cohort(["123"], units, frozen_at=START)
    assert not result["passes_cohort_checks"]
    assert result["acquisitions"] == 1
    assert result["overlapping_event_ids"] == ["123"]


def test_holdout_refuses_missing_freeze_missing_times_and_pre_freeze_data():
    units = [{"event": "new", "unit_id": "new:506", "start": END}]
    assert not audit_future_cohort([], units, frozen_at=None)["passes_cohort_checks"]
    assert not audit_future_cohort([], units, frozen_at=END)["passes_cohort_checks"]
    assert audit_future_cohort([], units, frozen_at=START)["passes_cohort_checks"]
    units[0]["start"] = "2026-01-01"
    assert not audit_future_cohort([], units, frozen_at=START)["passes_cohort_checks"]
    assert not audit_future_cohort([], [], frozen_at=START)["passes_cohort_checks"]


def load_script(name):
    path = Path(__file__).resolve().parents[1]/"scripts"/f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generation_preserves_virtual_environment_interpreter(tmp_path, monkeypatch):
    runner = load_script("validate_synthetic_coverage")
    base = tmp_path/"base-python"
    base.touch()
    interpreter = tmp_path/"venv-python"
    interpreter.symlink_to(base)
    called = []
    monkeypatch.setattr(runner, "generate", lambda output, python: called.append(python))
    monkeypatch.setattr(sys, "argv", ["runner", "generate", "--output", str(tmp_path/"out"),
                                    "--generator-python", str(interpreter)])
    runner.main()
    assert called == [interpreter.absolute()]
    assert called[0] != base


def test_frozen_input_and_protocol_tampering_refuses(tmp_path):
    runner = load_script("validate_synthetic_coverage")
    source = tmp_path/"input.txt"
    source.write_text("original")
    plan = tmp_path/"plan.json"
    plan.write_text(json.dumps({"inputs": {str(source): runner.digest(source)}}))
    (tmp_path/"plan.sha256").write_text(runner.digest(plan))
    runner.load_plan(tmp_path)
    source.write_text("changed")
    with pytest.raises(ValueError, match="frozen input changed"):
        runner.load_plan(tmp_path)
    plan.write_text("{}")
    with pytest.raises(ValueError, match="plan hash changed"):
        runner.load_plan(tmp_path)


def test_physical_plan_excludes_events_across_all_frequency_shards(tmp_path):
    prepare = load_script("prepare_validation_evidence").prepare
    inventory = tmp_path/"inventory.jsonl"
    inventory.write_text('\n'.join(json.dumps(row) for row in [
        {"event": "old", "freq_id": 506}, {"event": "old", "freq_id": 521},
        {"event": "another", "freq_id": 506}]))
    plan = prepare([inventory])
    assert plan["excluded_acquisitions"] == 2
    assert plan["status"] == "pending_inputs"
    assert not plan["current_cohort_audit"]["passes_cohort_checks"]
    assert plan["inputs"][str(inventory)]["sha256"] == hashlib.sha256(inventory.read_bytes()).hexdigest()
