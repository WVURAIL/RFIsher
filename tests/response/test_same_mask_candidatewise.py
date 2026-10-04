"""Deterministic fixtures for the single candidate-specific protocol."""
import json
from pathlib import Path

import numpy as np
import pytest
from scipy.stats import binom

from rfisher import cli
from rfisher.response import same_mask as sm
from rfisher.response import same_mask_candidatewise as study
from rfisher.response import same_mask_report as base
from test_same_mask import DeterministicDraws, fixture


def test_fixed_family_allocation_requires_maximum_order_statistic():
    rank = study.order_rank()
    assert rank == 4096
    p = 1-.04/21
    assert binom.sf(rank-1, 4096, p) <= .01/21
    assert binom.sf(rank-2, 4096, p) > .01/21
    assert 21*p**4096 < .01
    with pytest.raises(ValueError, match="budget"):
        study.order_rank(512)
    for args in ((0,), (10, 0), (10, 21, 0), (10, 21, .04, 1)):
        with pytest.raises(ValueError):
            study.order_rank(*args)


def test_fixed_scales_and_infinity_are_not_success_conditioned():
    point = np.array([.1, -.2, 100.])
    np.testing.assert_array_equal(study.fixed_scales(point), [1, 1, 100])
    np.testing.assert_array_equal(study.fixed_scales([0, 0, .5]), [1, 1, 1])
    low, high, critical = study.root_interval(point, [0, .1, .2], rank=3)
    assert critical == .2
    np.testing.assert_allclose(low, [-.1, -.4, 80])
    np.testing.assert_allclose(high, [.3, 0, 120])
    roots = np.zeros(4096)
    roots[-1] = np.inf
    with pytest.raises(ValueError, match="infinite"):
        study.root_interval(point, roots, rank=study.order_rank())
    for roots in ([np.nan], [-1], [-np.inf]):
        with pytest.raises(ValueError, match="roots"):
            study.root_interval(point, roots, rank=1)
    for point in ([0, 0], [0, 0, -1], [0, 0, np.inf]):
        with pytest.raises(ValueError):
            study.fixed_scales(point)
    low, _, _ = study.root_interval([0, 0, .5], [1], rank=1)
    assert low[2] == 0


def test_seed_namespace_is_new_and_reproducible():
    draw = study.rng(20, 0).integers(0, 2**32, 10)
    np.testing.assert_array_equal(draw, study.rng(20, 0).integers(0, 2**32, 10))
    assert not np.array_equal(draw, sm.rng(20, 0).integers(0, 2**32, 10))
    for args in ((21, 0), (20, 1), (20, 0, 1)):
        assert not np.array_equal(draw, study.rng(*args).integers(0, 2**32, 10))


def test_explicit_factories_reach_generated_data_and_postcalibration_resamples(monkeypatch):
    calls = []
    def generator_factory(*args):
        calls.append(args)
        return DeterministicDraws()
    monkeypatch.setitem(sm.SIZES, 10, 4)
    generated = sm.generate(10, 2, 3, words=(sm.WORDS[-1],), rng_factory=generator_factory)
    assert calls == [(10, 2, 3)] and generated["kept"].shape == (4, 1)
    class FixedIndices:
        def integers(self, low, high, size):
            return np.arange(size)
    def resample_factory(*args):
        calls.append(args)
        return FixedIndices()
    monkeypatch.setattr(sm, "BOOTSTRAPS", 4)
    interval = base.fixed_interval(fixture(), 0, np.eye(3), np.ones(3), 50, 2, 7,
                                   rng_factory=resample_factory)
    assert calls[-1] == (60, 2, 50007)
    assert interval["usable_resamples"] == 4 and interval["critical_value"] == 0


def rows_for_bootstrap():
    return [[{"index": i, "status": "supported_point", "point_coordinates": np.array([0., 0., 100.]),
              "fixed_scales": np.array([1., 1., 100.])} for i in range(7)] for _ in range(3)]


def test_failed_candidate_does_not_abort_other_slots_and_reference_is_shared(monkeypatch):
    monkeypatch.setattr(study, "BOOTSTRAPS", 4)
    monkeypatch.setattr(sm, "resample", lambda value, generator: value)
    calls = []
    def target(value):
        calls.append(value)
        if len(calls) == 2:
            raise ValueError("reference unsupported")
        return np.ones(3)
    monkeypatch.setattr(sm, "reference_variance", target)
    def estimate(value, index, diagnostics=False):
        if value == 0 and index == 1:
            raise ValueError("unstable primary injection derivative")
        return {"index": index}
    monkeypatch.setattr(sm, "estimate", estimate)
    monkeypatch.setattr(sm, "coordinates", lambda estimate, target: np.array([.1, 0., 100.]))
    rows = rows_for_bootstrap()
    rows[2][0]["status"] = "point_refused"
    roots, failures, reference = study.bootstrap([0, 1, 2], 99, rows)
    assert len(calls) == 4 and reference == {"reference unsupported": 1}
    assert np.isinf(roots[:, 0, 1]).all()
    assert failures[0, 1] == {"unstable primary injection derivative": 3}
    assert np.isinf(roots[1]).all()
    assert np.isfinite(roots[[0, 2, 3], 1, 1]).all()
    assert np.isinf(roots[:, 2, 0]).all()
    assert not failures[1, 1]


def finite_row(index, time, status="calibration_feasible"):
    return {"index": index, "threshold_kind": "finite", "status": status,
            "time_point_blocks": time, "time_lower_blocks": time-1, "time_upper_blocks": time+1}


def test_admitted_minimum_does_not_claim_unavailable_competitors_fail():
    rows = [finite_row(0, 101), finite_row(1, 100), finite_row(2, 90, "uncertainty_refused")]
    chosen = study.select(rows)
    assert chosen["selected_index"] == 1
    assert chosen["status"] == "point_minimum_among_admitted"
    assert chosen["global_grid_optimum_status"] == "unresolved_competitor_inference"
    assert chosen["unresolved_competitor_indices"] == [2]
    rows[2]["status"] = "bias_proven_infeasible"
    assert study.select(rows)["global_grid_optimum_status"] == "unresolved_admitted_ordering"
    rows[0]["time_lower_blocks"] = 200
    assert study.select(rows)["global_grid_optimum_status"] == "conditionally_resolved_declared_grid"
    rows[0]["time_point_blocks"] = 100
    assert study.select(rows)["selected_index"] == 0
    assert study.select([finite_row(0, 1, "point_refused")])["selected_index"] is None


def small_fixture_protocol(monkeypatch):
    monkeypatch.setattr(study, "BOOTSTRAPS", 8)
    monkeypatch.setattr(study, "order_rank", lambda count: count)
    monkeypatch.setattr(sm, "BOOTSTRAPS", 8)
    monkeypatch.setattr(sm, "REPLICATES", 2)
    for stage in sm.SIZES:
        monkeypatch.setitem(sm.SIZES, stage, 512)


def test_calibration_refusals_preserve_all_slots_and_no_infinity_json(monkeypatch):
    small_fixture_protocol(monkeypatch)
    original = sm.estimate
    def fail_one(value, index, diagnostics=True, **kwargs):
        if index == 1 and not diagnostics:
            raise ValueError("unstable derivative")
        return original(value, index, diagnostics=diagnostics, **kwargs)
    monkeypatch.setattr(sm, "estimate", fail_one)
    cal, roots = study.calibrate([fixture()]*3, fixture(words=1))
    assert roots.shape == (8, 3, 7)
    assert cal["bootstrap"]["fixed_family_size"] == 21
    for group in cal["rows"]:
        assert group[1]["status"] == "uncertainty_refused"
        assert group[1]["bootstrap"]["infinite_roots"] == 8
        assert group[1]["time_upper_blocks"] is None
        assert group[0]["status"] == "calibration_feasible"
        assert group[-1]["status"] == "no_science_information"
    assert "Infinity" not in base.encoded(cal)
    assert all(s["global_grid_optimum_status"] == "unresolved_competitor_inference" for s in cal["selections"])
    monkeypatch.setattr(sm, "reference_variance", lambda value: (_ for _ in ()).throw(ValueError("reference refused")))
    refused, roots = study.calibrate([fixture()]*3, fixture(words=1))
    assert all(row["status"] == "point_refused" for group in refused["rows"] for row in group[:-1])
    assert np.isinf(roots).all()
    assert refused["bootstrap"]["reference_refusals"] == {"reference refused": 8}


def test_admission_distinguishes_proven_bias_failure_from_overlap(monkeypatch):
    small_fixture_protocol(monkeypatch)
    def fixed_roots(data, ref, rows):
        return np.full((8, 3, 7), .1), {(s, i): {} for s in range(3) for i in range(7)}, {}
    monkeypatch.setattr(study, "bootstrap", fixed_roots)
    original = sm.coordinates
    def shifted(estimate, target):
        values = original(estimate, target)
        values[0] = 1.5 if estimate["bias"][0] > .01 else 1.
        return values
    monkeypatch.setattr(sm, "coordinates", shifted)
    cal, _ = study.calibrate([fixture(shift=.1), fixture(), fixture()], fixture(words=1))
    assert cal["rows"][0][0]["status"] == "bias_proven_infeasible"
    assert cal["rows"][1][0]["status"] == "bias_requirement_unresolved"
    assert all(s["selected_index"] is None for s in cal["selections"])


def test_cli_end_to_end_authenticates_roots_products_and_unused_stages(tmp_path, monkeypatch, capsys):
    small_fixture_protocol(monkeypatch)
    calls = []
    def deterministic(stage, scenario, replicate=0, **kwargs):
        calls.append((stage, kwargs["rng_factory"]))
        value = fixture(words=len(kwargs.get("words", sm.WORDS)))
        return value if stage in (20, 21) else {k: value[k] for k in ("kept", "clean", "observed")}
    monkeypatch.setattr(sm, "generate", deterministic)
    protocol = Path(__file__).parents[2]/"docs"/"CANDIDATEWISE_SYNTHETIC_PROTOCOL.md"
    out = tmp_path/"study"
    assert cli.main(["response", "same-mask-candidatewise", "--out", str(out), "--protocol", str(protocol)]) == 0
    assert all(factory is study.rng for _, factory in calls)
    assert study.main(["--validate", str(out)]) == 0
    outcome = json.loads((out/"result.json").read_text())
    assert outcome["physical_response_qualified"] is False
    assert "Frozen threshold: kind=finite; eta_q16=" in (out/"REPORT.txt").read_text()
    assert "saved fixed candidatewise stage 50" in capsys.readouterr().out
    with pytest.raises(ValueError, match="new"):
        study.run(out, protocol)
    manifest = json.loads((out/"manifest.json").read_text())
    def reseal(name):
        changed = dict(manifest, files_sha256=dict(manifest["files_sha256"]))
        changed["files_sha256"][name] = base.digest(out/name)
        (out/"manifest.json").write_text(json.dumps(changed))
    original = (out/"REPORT.txt").read_bytes()
    (out/"REPORT.txt").write_bytes(original+b"changed")
    with pytest.raises(ValueError, match="hash"):
        study.validate(out)
    reseal("REPORT.txt")
    with pytest.raises(ValueError, match="reconstruction"):
        study.validate(out)
    (out/"REPORT.txt").write_bytes(original)
    (out/"manifest.json").write_text(json.dumps(manifest))
    root_bytes = (out/"calibration_roots.npz").read_bytes()
    with np.load(out/"calibration_roots.npz") as values:
        roots = values["roots"]
    roots[0, 0, 0] += 1
    np.savez_compressed(out/"calibration_roots.npz", roots=roots)
    reseal("calibration_roots.npz")
    with pytest.raises(ValueError, match="roots"):
        study.validate(out)
    (out/"calibration_roots.npz").write_bytes(root_bytes)
    name = base.block_name(10, 0)
    np.savez_compressed(out/name, kept=np.zeros((1, 1)))
    reseal(name)
    with pytest.raises(ValueError, match="shape"):
        study.validate(out)
    (out/"manifest.json").write_text(json.dumps(dict(manifest, sources={})))
    with pytest.raises(ValueError, match="provenance"):
        study.validate(out)
    (out/"manifest.json").write_text(json.dumps(dict(manifest, environment={})))
    with pytest.raises(ValueError, match="environment"):
        study.validate(out)
    (out/"manifest.json").write_text(json.dumps(dict(manifest, files_sha256={})))
    with pytest.raises(ValueError, match="inventory"):
        study.validate(out)


@pytest.mark.parametrize("arguments", [["--out", "x"], ["--validate", "x", "--protocol", "y"], ["--validate", "absent"]])
def test_cli_refusals(arguments):
    with pytest.raises(SystemExit):
        study.main(arguments)
