"""Deterministic conditioning, support, inference and provenance checks."""
import json
from pathlib import Path

import numpy as np
import pytest

from rfisher import cli
from rfisher.response import same_mask as sm
from rfisher.response import same_mask_report as report


def fixture(n=512, words=7, shift=0.):
    t = np.arange(n)*.31
    q = np.stack([2+.3*np.sin(t), 2.5+.2*np.cos(1.2*t), 3+.25*np.sin(.7*t+.4)], axis=1)
    phase = np.exp(1j*np.stack([t*.3, t*.4, t*.6], axis=1))
    clean = np.repeat((np.sqrt(q)*phase)[:, None], words, axis=1)
    observed = np.repeat((np.sqrt(q+shift)*phase)[:, None], words, axis=1)
    data = {"kept": np.full((n, words), 100, dtype=np.int16), "clean": clean, "observed": observed}
    for name in ("injected_clean", "injected_observed", "frozen_observed"):
        data[name] = np.empty((n, 2, 3, 2, words, 3))
        for step_index, step in enumerate(sm.STEPS):
            for parameter in range(3):
                for sign_index, sign in enumerate((-1, 1)):
                    base = abs(clean if name == "injected_clean" else observed)**2
                    factor = .8 if name == "frozen_observed" else 1.
                    data[name][:, step_index, parameter, sign_index] = base + factor*sign*step*sm.D[:, parameter]
    return data


def test_observable_score_and_exact_boundaries():
    observed = np.array([[[0, 0, 10], [1, 0, 0]]], complex)
    score = sm.scores(observed)
    np.testing.assert_array_equal(score, [[0, 65536]])
    np.testing.assert_array_equal(sm.mask_from_scores(score, 65535), [[True, False]])
    np.testing.assert_array_equal(sm.mask_from_scores(score, 65536), [[True, True]])
    assert not sm.mask_from_scores(score, reject_all=True).any()
    values = np.array([2**53, 2**53+1, 2**64-1], dtype=np.uint64)
    np.testing.assert_array_equal(sm.mask_from_scores(values, 2**53), [True, False, False])
    assert sm.mask_from_scores(values, 2**64-1).all()
    for word in (0, -1, 2**64, True, 1.):
        with pytest.raises(ValueError):
            sm.mask_from_scores(score, word)
    with pytest.raises(ValueError):
        sm.mask_from_scores(score, 1, reject_all=True)
    with pytest.raises(ValueError):
        sm.mask_from_scores(score.astype(float), 1)
    for value in (np.nan, np.inf, 1e30):
        with pytest.raises(ValueError):
            sm.scores(np.full((1, 1, 3), value))


def test_same_mask_counterfactual_and_missing_endpoint_support():
    clean = np.arange(18).reshape(3, 2, 3).astype(complex)
    observed = clean+1j
    keep = np.array([[False, False], [True, False], [True, True]])
    count, vc, vo = sm.endpoint(clean, observed, keep)
    np.testing.assert_array_equal(count, [0, 1, 2])
    assert np.isnan(vc[:2]).all() and np.isnan(vo[:2]).all()
    np.testing.assert_allclose(vo[2]-vc[2], 1j)
    with pytest.raises(ValueError):
        sm.endpoint(clean, observed[:2], keep)
    with pytest.raises(ValueError, match="support"):
        sm.statistics(abs(vc)**2, minimum=2)


def test_dropped_blocks_are_priced_not_only_retained_frames():
    q = np.array([[1., 2, 3], [2., 4, 5], [4., 3, 8], [3., 8, 4]])
    complete = sm.statistics(q, minimum=2)
    missing = sm.statistics(np.r_[q, np.full_like(q, np.nan)], minimum=2)
    np.testing.assert_allclose(missing["wall_covariance"], 2*complete["wall_covariance"])
    np.testing.assert_allclose(missing["mean"], complete["mean"])


def test_primary_response_fits_all_parameters_and_preserves_comparisons():
    data = fixture(shift=.01)
    estimate = sm.estimate(data, 0)
    np.testing.assert_allclose(estimate["jacobian"], sm.D, atol=1e-12)
    np.testing.assert_allclose(estimate["clean_counterfactual_jacobian"], sm.D, atol=1e-12)
    np.testing.assert_allclose(estimate["frozen_mask_jacobian"], .8*sm.D, atol=1e-12)
    np.testing.assert_allclose(estimate["bias"], np.linalg.solve(sm.D, np.full(3, .01)), atol=1e-12)
    assert estimate["covariance"].shape == (3, 3)
    assert estimate["gaussian_closure"]["status"] == "diagnostic"
    target = sm.reference_variance(fixture(words=1))
    assert sm.coordinates(estimate, target).shape == (3,)
    for target in ([0, 1, 1], [np.inf, 1, 1]):
        with pytest.raises(ValueError):
            sm.coordinates(estimate, target)
    estimate["covariance"][:] = np.inf
    with pytest.raises(ValueError, match="nonfinite"):
        sm.coordinates(estimate, np.ones(3))


def test_unstable_singular_and_unsupported_responses_refuse():
    unstable = fixture()
    unstable["injected_observed"][:, 0] *= 2
    with pytest.raises(ValueError, match="unstable"):
        sm.estimate(unstable, 0)
    singular = fixture()
    singular["injected_observed"][:, :, 2] = singular["injected_observed"][:, :, 1]
    with pytest.raises(ValueError):
        sm.estimate(singular, 0)
    unsupported = fixture(n=20)
    with pytest.raises(ValueError, match="support"):
        sm.estimate(unsupported, 0)
    comparison = fixture()
    comparison["frozen_observed"][:, :, 2] = comparison["frozen_observed"][:, :, 1]
    assert sm.estimate(comparison, 0)["frozen_mask"]["status"] == "refused"


def test_simultaneous_family_retains_failures_and_zero_scale_rule():
    point = np.array([0., 2.])
    samples = np.array([[0., 1.], [0., 2.], [0., 3.], [0., 4.]])
    low, high, critical = sm.simultaneous_bounds(point, samples, requested=4)
    assert low[0] == high[0] == 0 and critical > 0
    with pytest.raises(ValueError, match="95%"):
        sm.simultaneous_bounds(point, samples[:3], requested=4)
    with pytest.raises(ValueError, match="zero"):
        sm.simultaneous_bounds(point, np.array([[1., 2.]]*4), requested=4)
    with pytest.raises(ValueError, match="invalid"):
        sm.simultaneous_bounds(point, np.full((4, 2), np.nan), requested=4)


def test_exact_minimum_not_two_percent_plateau_and_uncertain_order():
    rows = [{"index": i, "status": "calibration_feasible", "time_point_blocks": value,
             "time_lower_blocks": value-2, "time_upper_blocks": value+2}
            for i, value in enumerate((101, 100, 110))]
    result = sm.select(rows)
    assert result["selected_index"] == 1
    assert result["status"] == "ordering_unresolved"
    assert result["plausible_minimizers"] == [0, 1]
    assert result["validation_time_blocks"] == 102
    rows[0]["time_point_blocks"] = 100
    assert sm.select(rows)["selected_index"] == 0
    assert sm.select([])["selected_index"] is None
    assert sm.select(rows[2:])["status"] == "conditional_grid_minimum"


def test_fixed_evaluation_requires_both_dilations_and_supported_exposure():
    interval = {"lower": np.array([-.2, -.1, 1, 1]), "upper": np.array([.2, .1, 100, 100])}
    assert report.evaluation_status(interval, 1024) == "requirements_met_conditionally"
    assert report.evaluation_status(interval, 1) == "unsupported_small_exposure"
    assert report.evaluation_status(interval, 9000) == "extrapolated_exposure_model_only"
    interval["upper"][1] = 1.1
    assert report.evaluation_status(interval, 1024).startswith("bias")
    interval["upper"][1] = .1
    interval["upper"][3] = 1100
    assert report.evaluation_status(interval, 1024).startswith("precision")


def test_conditional_reference_containment_is_not_unconditional_coverage():
    interval = {"lower": np.zeros(4), "upper": np.ones(4)}
    reference = {"point": np.full(4, .5), "lower": np.full(4, -.1), "upper": np.full(4, .6)}
    assert report.containment(interval, reference) == {
        "center": True, "entire_reference_rectangle": False, "intersects_reference_rectangle": True}
    assert report.binomial_interval(0, 64)[0] == 0
    assert report.binomial_interval(64, 64)[1] == 1
    assert report.binomial_interval(60, 64)[0] < 60/64 < report.binomial_interval(60, 64)[1]
    with pytest.raises(ValueError):
        report.binomial_interval(65, 64)


def test_seed_namespaces_are_separate_and_resampling_preserves_pairing():
    a = sm.rng(20, 0).integers(0, 2**32, 10)
    np.testing.assert_array_equal(a, sm.rng(20, 0).integers(0, 2**32, 10))
    for namespace in ((21, 0), (20, 1), (20, 0, 1)):
        assert not np.array_equal(a, sm.rng(*namespace).integers(0, 2**32, 10))
    data = {"kept": np.arange(10)[:, None], "paired": 2*np.arange(10)[:, None]}
    resampled = sm.resample(data, sm.rng(60, 0))
    np.testing.assert_array_equal(resampled["paired"], 2*resampled["kept"])


class DeterministicDraws:
    def standard_normal(self, shape):
        return np.arange(np.prod(shape)).reshape(shape)%7/7

    def random(self, n):
        return np.linspace(0, 1, n)


def test_generator_paths_with_deterministic_draws_and_recomputed_masks(monkeypatch):
    for scenario in range(3):
        draw = sm._draw(DeterministicDraws(), 4, scenario)
        assert draw[0].shape == (4, 100, 3)
        assert np.any(draw[2]) == (scenario != 0)
    with pytest.raises(ValueError):
        sm._draw(DeterministicDraws(), 4, 3)
    with pytest.raises(ValueError):
        sm._streams(draw, [-10, 0, 0])
    monkeypatch.setitem(sm.SIZES, 10, 4)
    monkeypatch.setattr(sm, "rng", lambda *a: DeterministicDraws())
    def boundary_draw(generator, blocks, scenario):
        noise = np.zeros((blocks, 100, 3), complex)
        signal = noise.copy()
        signal[..., 0] = np.sqrt(.5/.3)
        return noise, signal, noise.copy()
    monkeypatch.setattr(sm, "_draw", boundary_draw)
    data = sm.generate(10, 1, injections=True)
    assert data["injected_observed"].shape == (4, 2, 3, 2, 7, 3)
    assert np.any(np.isfinite(data["injected_observed"]) != np.isfinite(data["frozen_observed"]))
    assert set(sm.generate(10, 0)) == {"kept", "clean", "observed"}


def test_cli_reconstruction_and_provenance_with_deterministic_summaries(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sm, "BOOTSTRAPS", 8)
    monkeypatch.setattr(sm, "REPLICATES", 2)
    for stage in sm.SIZES:
        monkeypatch.setitem(sm.SIZES, stage, 512)
    def saved_fixture(stage, scenario, replicate=0, **kwargs):
        value = fixture(words=len(kwargs.get("words", sm.WORDS)), shift=0.)
        return value if stage in (20, 21) else {k: value[k] for k in ("kept", "clean", "observed")}
    monkeypatch.setattr(sm, "generate", saved_fixture)
    protocol = Path(__file__).parents[2]/"docs"/"SAME_MASK_SYNTHETIC_PROTOCOL.md"
    out = tmp_path/"study"
    assert cli.main(["response", "same-mask", "--out", str(out), "--protocol", str(protocol)]) == 0
    assert report.main(["--validate", str(out)]) == 0
    saved = json.loads((out/"result.json").read_text())
    assert saved["physical_response_qualified"] is False
    assert saved["calibration"]["rows"][0][-1]["status"] == "no_science_information"
    assert "stage 50" in capsys.readouterr().out
    with pytest.raises(ValueError, match="new"):
        report.run(out, protocol)
    bad_protocol = tmp_path/"protocol.md"
    bad_protocol.write_text("changed")
    with pytest.raises(ValueError, match="protocol"):
        report.run(tmp_path/"other", bad_protocol)
    original = (out/"REPORT.txt").read_bytes()
    (out/"REPORT.txt").write_bytes(original+b"tampered")
    with pytest.raises(ValueError, match="hash"):
        report.validate(out)
    (out/"REPORT.txt").write_bytes(original)
    manifest = json.loads((out/"manifest.json").read_text())
    missing = dict(manifest, files_sha256=dict(manifest["files_sha256"]))
    del missing["files_sha256"]["REPORT.txt"]
    (out/"manifest.json").write_text(json.dumps(missing))
    with pytest.raises(ValueError, match="inventory"):
        report.validate(out)
    wrong_environment = dict(manifest, environment={})
    (out/"manifest.json").write_text(json.dumps(wrong_environment))
    with pytest.raises(ValueError, match="environment"):
        report.validate(out)
    changed = dict(manifest, files_sha256=dict(manifest["files_sha256"]))
    (out/"REPORT.txt").write_bytes(original+b"tampered")
    changed["files_sha256"]["REPORT.txt"] = report.digest(out/"REPORT.txt")
    (out/"manifest.json").write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="reconstruction"):
        report.validate(out)
    (out/"REPORT.txt").write_bytes(original)
    manifest["sources"]["same_mask.py"] = "0"*64
    (out/"manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="provenance"):
        report.validate(out)


def test_inference_refusal_keeps_bootstrap_failure_counts(monkeypatch):
    monkeypatch.setattr(sm, "BOOTSTRAPS", 4)
    monkeypatch.setattr(sm, "resample", lambda *a: fixture(n=2))
    with pytest.raises(report.InferenceRefused) as failure:
        report.fixed_interval(fixture(), 0, np.eye(3), np.ones(3), 30, 0)
    assert failure.value.accounting["requested_resamples"] == 4
    assert failure.value.accounting["usable_resamples"] == 0
    assert sum(failure.value.accounting["resample_refusals"].values()) == 4
    with pytest.raises(report.InferenceRefused) as failure:
        report.bootstrap_calibration([fixture()]*3, fixture(words=1), np.zeros(3), [(0, 0)])
    assert failure.value.accounting["usable"] == 0
    assert sum(failure.value.accounting["refusal_counts"].values()) == 4


def test_saved_stage_shapes_and_validity_are_checked(tmp_path, monkeypatch):
    monkeypatch.setitem(sm.SIZES, 10, 512)
    (tmp_path/"blocks").mkdir()
    data = fixture()
    data = {key: data[key] for key in ("kept", "clean", "observed")}
    path = tmp_path/report.block_name(10, 0)
    np.savez(path, **data)
    assert report.load_blocks(tmp_path, 10, 0)["kept"].shape == (512, 7)
    data["observed"][0, 0] = np.nan
    np.savez(path, **data)
    with pytest.raises(ValueError, match="validity"):
        report.load_blocks(tmp_path, 10, 0)
    data["kept"][0, 0] = 101
    np.savez(path, **data)
    with pytest.raises(ValueError, match="frame support"):
        report.load_blocks(tmp_path, 10, 0)
    data["kept"] = data["kept"][:2]
    np.savez(path, **data)
    with pytest.raises(ValueError, match="shape"):
        report.load_blocks(tmp_path, 10, 0)


@pytest.mark.parametrize("arguments", [["--out", "x"], ["--validate", "x", "--protocol", "y"], ["--validate", "absent"]])
def test_cli_refusals(arguments):
    with pytest.raises(SystemExit):
        report.main(arguments)


def test_report_serialization_refuses_nonfinite_values():
    assert report.plain(np.array([1+2j])) == [{"real": 1., "imaginary": 2.}]
    assert report.plain(np.int64(3)) == 3
    with pytest.raises(ValueError):
        report.encoded({"invalid": np.inf})
