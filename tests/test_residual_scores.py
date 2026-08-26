"""Exact residual-score bridge tests."""
from __future__ import annotations

from functools import cmp_to_key
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from rfisher.residual_scores import (
    ResidualScoreBundle, ResidualScoreRefused, build_residual_score_bundle,
    load_residual_score_bundle, required_multipliers_for_frame)
from rfisher.preparation import CalibrationEvidence
from rfisher.thresholds import ALWAYS_MASKED_Q16, MAX_MULTIPLIER_Q16


REHEARSAL_PRODUCT = Path(
    "/home/djg/rail/pilot_proxy_runs/"
    "local_archive_rehearsal_844_f9ab7d7cfb13/_per_pilot/844.npz")
REHEARSAL_SHA256 = (
    "fc65f6566bc5ab215c688c43955b854cd30e9a0f7d8b92b779e3a02dd69db94d")


def _decision_contract():
    return {
        "fine_measurement": {
            "method": "exact_fine_power_terms",
            "role": "measurement_only_no_scan_time_decision",
            "terms_field": "fine_power_u64",
        },
        "fine_candidate_decision": {
            "method": "fine_order_statistic_cfar",
            "active": False,
        },
    }


def _detector_contract():
    return {
        "schema_version": "pilotproxy_detector_contract_v1",
        "num_weight_terms": 3,
        "power_accumulator": "uint64",
    }


def _synthetic_product(path, *, frames=48):
    powers = np.full((frames, 3, 256), 20, dtype=np.uint64)
    for frame in range(frames):
        powers[frame, 0] += np.arange(256, dtype=np.uint64) + frame
        powers[frame, 1] += np.arange(256, dtype=np.uint64) % 7
        powers[frame, 2] += np.arange(256, dtype=np.uint64) % 11
    half = frames // 2
    unit_index = np.repeat(np.arange(2, dtype=np.int32), [half, frames - half])
    frame_in_unit = np.concatenate((
        np.arange(half, dtype=np.int32),
        np.arange(frames - half, dtype=np.int32)))
    lower = np.full((frames, 1), 100, dtype=np.uint64)
    upper = np.full((frames, 1), 120, dtype=np.uint64)
    np.savez(
        path,
        schema_name=np.asarray("pilotproxy_per_pilot_product"),
        schema_revision=np.asarray(5, dtype=np.int64),
        schema_version=np.asarray("pilotproxy_per_pilot_product_v5"),
        source_event_key_schema_version=np.asarray(
            "pilotproxy_namespaced_source_event_key_v1"),
        decision_contract_json=np.asarray(json.dumps(_decision_contract())),
        detector_contract_json=np.asarray(json.dumps(_detector_contract())),
        fine_status=np.asarray("enabled"),
        fine_num_bins=np.asarray(256, dtype=np.int64),
        fine_power_u64=powers,
        pilot_in_band=np.asarray([1], dtype=np.uint8),
        frame_index=np.arange(frames, dtype=np.int64),
        p_target_u64=np.full((frames, 1), 130, dtype=np.uint64),
        p_ref_lower_u64=lower,
        p_ref_upper_u64=upper,
        p_ref_sum_u64=lower + upper,
        valid=np.ones((frames, 1), dtype=np.uint8),
        frame_unit_index=unit_index,
        frame_in_unit=frame_in_unit,
        unit_order=np.asarray(["unit-early", "unit-late"]),
        unit_keys=np.asarray(["unit-early", "unit-late"]),
        source_event_keys=np.asarray(["archive:event:early",
                                      "archive:event:late"]),
        archive_version=np.asarray(["v1", "v1"]),
        unit_git_version_tag=np.asarray(["release", "release"]),
        unit_input_map_sha256=np.asarray(["5" * 64, "6" * 64]),
        unit_collection_server=np.asarray(["server-a", "server-b"]),
        unit_scope=np.asarray(["scope.a", "scope.a"]),
        unit_event_id=np.asarray([100, 200], dtype=np.int64),
        unit_time0_fpga=np.asarray([1000, 2000], dtype=np.uint64),
        unit_time0_ctime=np.asarray([1704067200.0, 1735689600.0]),
        unit_delta_time=np.full(2, 1.0 / 390625.0, dtype=np.float64),
        sample_rate_hz=np.asarray(390625.0, dtype=np.float64),
        nfft=np.asarray(16384, dtype=np.int64),
        physical_channel=np.asarray([14], dtype=np.int32),
        freq_id=np.asarray([844], dtype=np.int64),
        detector_version=np.asarray("pilot-proxy/test current-v5"),
        weights_hash=np.asarray("1" * 64),
        weight_bank_sha256=np.asarray("2" * 64),
        weight_manifest_sha256=np.asarray("3" * 64),
        weight_coefficients_sha256=np.asarray("4" * 64),
    )
    return powers


def _bulk(*bins):
    result = np.zeros(256, dtype=bool)
    result[list(bins)] = True
    return result


def _exact_oracle(powers, *, anchor, width, bulk):
    designated = [(anchor + offset) % 256
                  for offset in range(-width, width + 1)]
    num = [2 * int(value) for value in powers[0]]
    den = [int(left) + int(right)
           for left, right in zip(powers[1], powers[2])]

    def compare(left, right):
        difference = num[left] * den[right] - num[right] * den[left]
        return (-1 if difference < 0 else 1 if difference > 0
                else left - right)

    ranked = [index for index in np.flatnonzero(bulk) if den[index] > 0]
    ranked.sort(key=cmp_to_key(compare))
    out = []
    for rank_bin in ranked:
        required = 1
        for designated_bin in designated:
            if den[designated_bin] <= 0 or num[designated_bin] == 0:
                continue
            if num[rank_bin] == 0:
                required = ALWAYS_MASKED_Q16
                break
            top = num[designated_bin] * (1 << 16) * den[rank_bin]
            bottom = num[rank_bin] * den[designated_bin]
            required = max(required, (top + bottom - 1) // bottom)
            if required > MAX_MULTIPLIER_Q16:
                required = ALWAYS_MASKED_Q16
                break
        out.append(required)
    return tuple(out)


def _measured(name):
    return CalibrationEvidence(
        state="measured", method=name, source="synthetic fixture",
        artifact_sha256="a" * 64)


def test_every_rank_matches_independent_exact_oracle():
    generator = np.random.default_rng(41)
    powers = generator.integers(
        0, 1 << 30, size=(3, 256), dtype=np.uint64)
    powers[1, 72] = 0
    powers[2, 72] = 0
    bulk = np.zeros(256, dtype=bool)
    bulk[np.arange(3, 220, 3)] = True
    bulk[[19, 20, 21]] = False
    expected = _exact_oracle(powers, anchor=20, width=1, bulk=bulk)

    actual = required_multipliers_for_frame(
        powers, anchor_bin=20, designated_half_width=1, bulk_mask=bulk)

    assert actual == expected
    assert len(actual) == np.count_nonzero(bulk) - 1


def test_randomized_exact_arithmetic_matches_oracle():
    generator = np.random.default_rng(731)
    cases = [(0, 3), (255, 4), (127, 0), (1, 127)]
    limit = np.iinfo(np.uint64).max
    for case in range(20):
        anchor, width = cases[case % len(cases)]
        powers = generator.integers(
            0, limit, size=(3, 256), dtype=np.uint64)
        designated = {(anchor + offset) % 256
                      for offset in range(-width, width + 1)}
        available = np.asarray(
            [index for index in range(256) if index not in designated])
        bulk = np.zeros(256, dtype=bool)
        bulk[available[generator.random(available.size) < 0.45]] = True
        if not bulk.any():
            bulk[int(available[0])] = True
        bulk_bins = np.flatnonzero(bulk)
        if bulk_bins.size > 1:
            powers[1, bulk_bins[0]] = 0
            powers[2, bulk_bins[0]] = 0
            powers[0, bulk_bins[1]] = 0
        if bulk_bins.size > 3:
            powers[:, bulk_bins[3]] = powers[:, bulk_bins[2]]
        powers[0, anchor] = limit
        powers[1, anchor] = 1
        powers[2, anchor] = 0

        expected = _exact_oracle(
            powers, anchor=anchor, width=width, bulk=bulk)
        actual = required_multipliers_for_frame(
            powers, anchor_bin=anchor, designated_half_width=width,
            bulk_mask=bulk)

        assert actual == expected


def test_always_masked_sentinel_has_safe_round_trip(tmp_path):
    product = tmp_path / "product.npz"
    powers = _synthetic_product(product, frames=4)
    powers[:, :, :] = 0
    powers[:, 0, 0] = 100
    powers[:, 1, 0] = 1
    powers[:, 2, 0] = 1
    powers[:, 1, 2] = 1
    powers[:, 2, 2] = 1
    with np.load(product, allow_pickle=False) as archive:
        fields = {name: archive[name] for name in archive.files}
    fields["fine_power_u64"] = powers
    np.savez(product, **fields)

    bundle = build_residual_score_bundle(
        product, np.ones(4, dtype=bool), anchor_bin=0,
        designated_half_width=0, bulk_mask=_bulk(2))
    output = bundle.save(tmp_path / "scores.npz")
    loaded = load_residual_score_bundle(output)

    assert loaded.required_multiplier_q16.dtype == np.dtype(np.uint64)
    assert np.all(loaded.required_multiplier_q16 == 0)
    assert np.all(loaded.always_masked)
    assert tuple(loaded.requirements_by_rho()[1]) == (ALWAYS_MASKED_Q16,) * 4
    with np.load(output, allow_pickle=False) as archive:
        assert all(archive[name].dtype.kind != "O" for name in archive.files)


def test_synthetic_bundle_reloads_and_enters_preparation(tmp_path):
    product = tmp_path / "product.npz"
    _synthetic_product(product)
    bulk = _bulk(10, 11, 12, 13)
    bundle = build_residual_score_bundle(
        product, np.ones(48, dtype=bool), anchor_bin=0,
        designated_half_width=0, bulk_mask=bulk)
    loaded = load_residual_score_bundle(bundle.save(tmp_path / "scores.npz"))

    assert loaded.frame_count == 48
    assert loaded.supported_rho_count == 4
    assert loaded.manifest["source"]["product_sha256"] == hashlib.sha256(
        product.read_bytes()).hexdigest()
    assert loaded.manifest["calibration"]["anchor_bin"] == 0
    producer = loaded.manifest["producer"]
    assert producer["package"] == "rfisher"
    assert producer["package_version"] == "2.0.0"
    assert set(producer["source_files"]) == {
        "src/rfisher/residual_scores/bundle.py",
        "src/rfisher/thresholds.py",
    }
    root = Path(__file__).resolve().parents[1]
    expected_files = {
        label: hashlib.sha256((root / label).read_bytes()).hexdigest()
        for label in sorted(producer["source_files"])
    }
    assert producer["source_files"] == expected_files
    source_digest = hashlib.sha256(
        b"rfisher-residual-score-producer-v1\0")
    for label, file_sha256 in expected_files.items():
        source_digest.update(label.encode("utf-8"))
        source_digest.update(b"\0")
        source_digest.update(bytes.fromhex(file_sha256))
    assert producer["source_sha256"] == source_digest.hexdigest()
    assert loaded.content_sha256 == bundle.content_sha256
    assert set(loaded.requirements_by_rho()) == {1, 2, 3, 4}

    prepared = loaded.prepare_threshold_family(
        np.full(48, 0.02),
        variance_residuals=np.zeros(48),
        era_label="synthetic-current-era",
        latest_era=True,
        additive_residuals=True,
        score=_measured("exact score"),
        correlation=_measured("correlation"),
        transfer=_measured("transfer"),
        max_cost_ratio=1.1,
        max_systematic_residual_ratio=1.1,
        minimum_half_retained_frames=10,
        minimum_observed_months=1,
        minimum_span_days=1e-6,
    )
    assert prepared.source_id == loaded.source_id
    assert set(prepared.histograms_by_rho) == {1, 2, 3, 4}


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"schema_revision": np.asarray(4, dtype=np.int64)},
         "unsupported source schema"),
        ({"fine_status": np.asarray("disabled_by_option")},
         "fine measurement is not enabled"),
        ({"fine_power_u64": np.zeros((48, 3, 256), dtype=np.float64)},
         "fine_power_u64"),
    ],
)
def test_incompatible_source_is_refused(tmp_path, change, message):
    product = tmp_path / "product.npz"
    _synthetic_product(product)
    with np.load(product, allow_pickle=False) as archive:
        fields = {name: archive[name] for name in archive.files}
    fields.update(change)
    np.savez(product, **fields)

    with pytest.raises(ResidualScoreRefused, match=message):
        build_residual_score_bundle(
            product, np.ones(48, dtype=bool), anchor_bin=0,
            designated_half_width=0, bulk_mask=_bulk(2, 4))


def test_explicit_masks_are_not_inferred_or_repaired(tmp_path):
    product = tmp_path / "product.npz"
    _synthetic_product(product)
    selected = np.ones(48, dtype=bool)
    selected[3] = False
    with np.load(product, allow_pickle=False) as archive:
        fields = {name: archive[name] for name in archive.files}
    fields["valid"] = fields["valid"].copy()
    fields["valid"][3, 0] = 0
    fields["valid"][4, 0] = 0
    np.savez(product, **fields)

    with pytest.raises(ResidualScoreRefused, match="invalid source frame"):
        build_residual_score_bundle(
            product, selected, anchor_bin=0, designated_half_width=0,
            bulk_mask=_bulk(2, 4))
    with pytest.raises(ResidualScoreRefused, match="exclude every designated"):
        build_residual_score_bundle(
            product, np.zeros(48, dtype=bool), anchor_bin=0,
            designated_half_width=0, bulk_mask=_bulk(0, 2))


def test_nonlocal_source_requires_acquisition_provenance(tmp_path):
    product = tmp_path / "product.npz"
    _synthetic_product(product)
    with np.load(product, allow_pickle=False) as archive:
        fields = {name: archive[name] for name in archive.files}
    fields["unit_git_version_tag"] = np.asarray(["release", ""])
    np.savez(product, **fields)

    with pytest.raises(ResidualScoreRefused, match="nonlocal source units"):
        build_residual_score_bundle(
            product, np.ones(48, dtype=bool), anchor_bin=0,
            designated_half_width=0, bulk_mask=_bulk(2, 4))


def test_tampered_bundle_is_refused(tmp_path):
    product = tmp_path / "product.npz"
    _synthetic_product(product)
    bundle_path = build_residual_score_bundle(
        product, np.ones(48, dtype=bool), anchor_bin=0,
        designated_half_width=0, bulk_mask=_bulk(2, 4)).save(
            tmp_path / "scores.npz")
    with np.load(bundle_path, allow_pickle=False) as archive:
        fields = {name: archive[name] for name in archive.files}
    fields["required_multiplier_q16"] = fields[
        "required_multiplier_q16"].copy()
    fields["required_multiplier_q16"][0, 0] += 1
    np.savez(bundle_path, **fields)

    with pytest.raises(ResidualScoreRefused, match="identity check"):
        load_residual_score_bundle(bundle_path)

    loaded = build_residual_score_bundle(
        product, np.ones(48, dtype=bool), anchor_bin=0,
        designated_half_width=0, bulk_mask=_bulk(2, 4))
    changed = loaded.required_multiplier_q16.copy()
    changed[0, 0] += 1
    with pytest.raises(ResidualScoreRefused, match="identity check"):
        ResidualScoreBundle(
            manifest_json=loaded.manifest_json,
            source_row_index=loaded.source_row_index,
            frame_index=loaded.frame_index,
            frame_time=loaded.frame_time,
            acquisition_index=loaded.acquisition_index,
            exposure_seconds=loaded.exposure_seconds,
            rho=loaded.rho,
            required_multiplier_q16=changed,
            always_masked=loaded.always_masked)

    producer_path = loaded.save(tmp_path / "producer.npz")
    with np.load(producer_path, allow_pickle=False) as archive:
        producer_fields = {name: archive[name] for name in archive.files}
    manifest = json.loads(str(producer_fields["manifest_json"].item()))
    manifest["producer"]["package_version"] = "0.0.0"
    core = dict(manifest)
    core.pop("content_sha256")
    encoded_core = json.dumps(
        core, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False)
    manifest["content_sha256"] = hashlib.sha256(
        encoded_core.encode("utf-8")).hexdigest()
    producer_fields["manifest_json"] = np.asarray(json.dumps(
        manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False))
    np.savez(producer_path, **producer_fields)

    with pytest.raises(ResidualScoreRefused, match="producer provenance"):
        load_residual_score_bundle(producer_path)


def test_driver_builds_the_same_safe_bundle(tmp_path):
    product = tmp_path / "product.npz"
    _synthetic_product(product, frames=4)
    selected_path = tmp_path / "selected.npy"
    bulk_path = tmp_path / "bulk.npy"
    np.save(selected_path, np.ones(4, dtype=bool))
    np.save(bulk_path, _bulk(2, 4))
    output = tmp_path / "scores.npz"

    result = subprocess.run(
        [sys.executable, "scripts/build_residual_score_bundle.py", str(product),
         "--selected-frames", str(selected_path), "--anchor-bin", "0",
         "--designated-half-width", "0", "--bulk-mask", str(bulk_path),
         "--output", str(output)],
        cwd=Path(__file__).resolve().parents[1], text=True,
        capture_output=True, check=False)

    assert result.returncode == 0, result.stderr
    assert "frames=4 rho=2" in result.stdout
    assert load_residual_score_bundle(output).frame_count == 4
    refused = subprocess.run(
        result.args, cwd=Path(__file__).resolve().parents[1], text=True,
        capture_output=True, check=False)
    assert refused.returncode == 2
    assert "pass --overwrite" in refused.stderr
    replaced = subprocess.run(
        [*result.args, "--overwrite"],
        cwd=Path(__file__).resolve().parents[1], text=True,
        capture_output=True, check=False)
    assert replaced.returncode == 0, replaced.stderr


@pytest.mark.skipif(not REHEARSAL_PRODUCT.exists(),
                    reason="local f9 rehearsal product is unavailable")
def test_existing_f9_rehearsal_scores_but_is_not_final_source():
    assert hashlib.sha256(REHEARSAL_PRODUCT.read_bytes()).hexdigest() \
        == REHEARSAL_SHA256
    with np.load(REHEARSAL_PRODUCT, allow_pickle=False) as archive:
        selected = archive["valid"].reshape(-1).astype(bool)
        powers = archive["fine_power_u64"][0]
    bulk = np.zeros(256, dtype=bool)
    bulk[2::2] = True

    assert required_multipliers_for_frame(
        powers, anchor_bin=0, designated_half_width=0,
        bulk_mask=bulk) == _exact_oracle(
            powers, anchor=0, width=0, bulk=bulk)
    assert int(np.count_nonzero(selected)) == 22
    with pytest.raises(ResidualScoreRefused, match="unit_git_version_tag"):
        build_residual_score_bundle(
            REHEARSAL_PRODUCT, selected, anchor_bin=0,
            designated_half_width=0, bulk_mask=bulk)
