"""Synthetic observed-score masks and same-support visibility response.

The fixed study is described by SAME_MASK_SYNTHETIC_PROTOCOL.md. These are
score-level synthetic coordinates, not a physical telescope/DSP simulation.
"""
from __future__ import annotations

import numpy as np

from .visibility import (complex_moments_to_real, linear_parameter_response,
                         quadratic_moments)

WORDS = (1311, 3277, 8192, 32768, 131072, 524288, 2**64 - 1)
NAMES = ("synthetic_parallel_dilation", "synthetic_perpendicular_dilation",
         "synthetic_growth")
SCENARIOS = ("clean_control", "intermittent_coherent", "persistent_coherent")
STEPS = (.04, .02)
FRAME_COUNT = 100
BLOCK_SECONDS = 10
REFERENCE_BLOCKS = 1024
MIN_SUPPORT = 256
SIZES = {10: 1024, 20: 4096, 21: 4096, 30: 8192, 40: 32768, 50: 512}
REPLICATES = 64
BOOTSTRAPS = 512
PROTOCOL_SHA256 = "00395c3a5314d85c5f4e45674de1ec175bab1bf43a5ffd86cfeb11f4d4443f95"
L = np.array([[1., 0, 0], [.3, np.sqrt(.91), 0], [.2, .15, np.sqrt(.9375)]])
D = np.array([[1., .2, .3], [.2, 1., .3], [.3, .3, 1.]])
RFI = np.array([1+.2j, .7-.4j, .3+.6j])


def rng(stage, scenario, replicate=0):
    return np.random.Generator(np.random.PCG64(
        np.random.SeedSequence([20261003, stage, scenario, replicate])))


def scores(observed):
    """The observable pilot power only; latent components are not arguments."""
    values = np.ceil(65536 * (abs(observed[..., 0])**2
                             + .1 * abs(observed[..., 1])**2))
    if not np.isfinite(values).all() or (values < 0).any() or (values >= 2**64).any():
        raise ValueError("observed score outside uint64 domain")
    return values.astype(np.uint64)


def mask_from_scores(values, word=None, *, reject_all=False):
    if values.dtype != np.uint64:
        raise ValueError("scores must be exact uint64")
    if reject_all:
        if word is not None:
            raise ValueError("reject_all has no numeric threshold")
        return np.zeros(values.shape, dtype=bool)
    if type(word) is not int or not 1 <= word <= 2**64 - 1:
        raise ValueError("finite threshold must be a positive uint64 integer")
    return values <= np.uint64(word)


def endpoint(clean, observed, keep):
    """Paired endpoints use exactly the same observed-stream mask."""
    if clean.shape != observed.shape or clean.shape[:-1] != keep.shape:
        raise ValueError("counterfactual and mask shapes do not match")
    count = keep.sum(axis=1)
    supported = count >= 2
    result = []
    for stream in (clean, observed):
        values = np.full((len(count), 3), np.nan + 1j*np.nan)
        values[supported] = (stream * keep[..., None]).sum(axis=1)[supported] / count[supported, None]
        result.append(values)
    return count, *result


def _draw(generator, blocks, scenario):
    shape = (blocks, FRAME_COUNT, 3)
    nr, ni, sr, si = (generator.standard_normal(shape) for _ in range(4))
    noise = (.8*nr + .6j*ni) @ L.T
    signal = ((sr + 1j*si)/np.sqrt(2)) @ L.T
    state = np.zeros((blocks, FRAME_COUNT), dtype=bool)
    if scenario == 1:
        state[:, 0] = generator.random(blocks) < .2
        for frame in range(1, FRAME_COUNT):
            draw = generator.random(blocks)
            state[:, frame] = np.where(state[:, frame-1], draw >= .2, draw < .05)
    elif scenario == 2:
        state[:] = True
    elif scenario != 0:
        raise ValueError("unknown synthetic scenario")
    contamination = (0., 2., .25)[scenario] * state[..., None] * RFI
    return noise, signal, contamination


def _streams(draw, theta):
    noise, signal, contamination = draw
    power = .3 + D @ np.asarray(theta)
    if (power <= 0).any():
        raise ValueError("synthetic signal power must be positive")
    clean = noise + signal * np.sqrt(power)
    return clean, clean + contamination


def generate(stage, scenario, replicate=0, *, injections=False, words=WORDS):
    """Generate only the fixed protocol budget; no public reduced-trial option."""
    generator = rng(stage, scenario, replicate)
    n, k = SIZES[stage], len(words)
    output = {"kept": np.zeros((n, k), dtype=np.int16),
              "clean": np.full((n, k, 3), np.nan+1j*np.nan),
              "observed": np.full((n, k, 3), np.nan+1j*np.nan)}
    if injections:
        for name in ("injected_observed", "injected_clean", "frozen_observed"):
            output[name] = np.full((n, 2, 3, 2, k, 3), np.nan)
    # Chunk size is fixed because it participates in generator draw order.
    for start in range(0, n, 128):
        end = min(start + 128, n)
        draw = _draw(generator, end-start, scenario)
        clean, observed = _streams(draw, np.zeros(3))
        observed_score = scores(observed)
        masks = [mask_from_scores(observed_score, int(word)) for word in words]
        for index, keep in enumerate(masks):
            kept, vc, vo = endpoint(clean, observed, keep)
            output["kept"][start:end, index] = kept
            output["clean"][start:end, index] = vc
            output["observed"][start:end, index] = vo
        if not injections:
            continue
        for step_index, step in enumerate(STEPS):
            for parameter in range(3):
                for sign_index, sign in enumerate((-1, 1)):
                    theta = np.zeros(3)
                    theta[parameter] = sign * step
                    vc, vo = _streams(draw, theta)
                    injected_scores = scores(vo)
                    for index, word in enumerate(words):
                        keep = mask_from_scores(injected_scores, int(word))
                        _, clean_endpoint, observed_endpoint = endpoint(vc, vo, keep)
                        _, _, frozen = endpoint(vc, vo, masks[index])
                        at = (slice(start, end), step_index, parameter, sign_index, index)
                        for key, values in (("injected_clean", clean_endpoint),
                                            ("injected_observed", observed_endpoint),
                                            ("frozen_observed", frozen)):
                            output[key][at] = abs(values)**2
    return output


def statistics(values, minimum=MIN_SUPPORT):
    valid = np.isfinite(values).all(axis=1)
    count = int(valid.sum())
    if count < minimum:
        raise ValueError(f"insufficient supported blocks: {count} < {minimum}")
    q = values[valid]
    fraction = count / len(values)
    return {"mean": q.mean(axis=0), "covariance": np.cov(q, rowvar=False, ddof=1),
            "fraction": fraction, "count": count,
            "wall_covariance": np.cov(q, rowvar=False, ddof=1)/fraction}


def jacobian(data, index, key="injected_observed", step_index=1, minimum=MIN_SUPPORT):
    columns = []
    for parameter in range(3):
        means = [statistics(data[key][:, step_index, parameter, sign, index], minimum)["mean"]
                 for sign in range(2)]
        columns.append((means[1]-means[0])/(2*STEPS[step_index]))
    return np.stack(columns, axis=1)


def estimate(data, index, *, minimum=MIN_SUPPORT, diagnostics=True):
    clean = statistics(abs(data["clean"][:, index])**2, minimum)
    observed = statistics(abs(data["observed"][:, index])**2, minimum)
    j = jacobian(data, index, minimum=minimum)
    wide = jacobian(data, index, step_index=0, minimum=minimum)
    norm = np.linalg.norm(j)
    difference = float(np.linalg.norm(j-wide)/norm) if norm else np.inf
    if not np.isfinite(difference) or difference > .25:
        raise ValueError(f"unstable primary injection derivative: relative difference {difference:g}")
    # Both step-size responses must remain identifiable, with the existing
    # response module's unregularized conditioning check.
    for derivative in (wide, j):
        fit = linear_parameter_response(derivative, clean["wall_covariance"],
                                        observed["mean"]-clean["mean"], observed["wall_covariance"],
                                        parameter_names=NAMES)
    result = {"bias": fit["bias"], "covariance": fit["covariance"],
              "response": fit["response"], "jacobian": j, "wide_jacobian": wide,
              "derivative_relative_difference": difference,
              "valid_blocks": observed["count"], "valid_block_fraction": observed["fraction"],
              "retained_frame_fraction": float(data["kept"][:, index].mean()/FRAME_COUNT)}
    if diagnostics:
        clean_v = data["clean"][:, index]
        clean_v = clean_v[np.isfinite(clean_v).all(axis=1)]
        clean_mean = clean_v.mean(axis=0)
        clean_centered = clean_v-clean_mean
        result.update(clean_complex_mean=clean_mean,
                      clean_complex_covariance=clean_centered.T @ clean_centered.conj()/(len(clean_v)-1),
                      clean_pseudocovariance=clean_centered.T @ clean_centered/(len(clean_v)-1))
        vc = data["observed"][:, index]
        vc = vc[np.isfinite(vc).all(axis=1)]
        mean = vc.mean(axis=0)
        centered = vc-mean
        covariance = centered.T @ centered.conj()/(len(vc)-1)
        pseudo = centered.T @ centered/(len(vc)-1)
        real_mean, real_cov = complex_moments_to_real(mean, covariance, pseudo)
        kernels = np.array([np.diag(np.eye(6)[i]+np.eye(6)[i+3]) for i in range(3)])
        gaussian = quadratic_moments(real_mean, real_cov, kernels)
        result.update(observed_complex_mean=mean, observed_complex_covariance=covariance,
                      observed_pseudocovariance=pseudo,
                      empirical_statistic_covariance=observed["covariance"],
                      gaussian_statistic_covariance=gaussian["covariance"],
                      gaussian_covariance_relative_error=float(np.linalg.norm(gaussian["covariance"]-observed["covariance"])
                                                               /np.linalg.norm(observed["covariance"])),
                      clean_counterfactual_jacobian=jacobian(data, index, "injected_clean", minimum=minimum),
                      frozen_mask_jacobian=jacobian(data, index, "frozen_observed", minimum=minimum))
        for label, derivative, actual in (
                ("gaussian_closure", j, gaussian["covariance"]/observed["fraction"]),
                ("frozen_mask", result["frozen_mask_jacobian"], observed["wall_covariance"])):
            try:
                alternative = linear_parameter_response(derivative, clean["wall_covariance"],
                                                        observed["mean"]-clean["mean"], actual,
                                                        parameter_names=NAMES)
                result[label] = {"status": "diagnostic", "bias": alternative["bias"],
                                 "covariance": alternative["covariance"]}
            except ValueError as exc:
                result[label] = {"status": "refused", "reason": str(exc)}
    return result


def reference_variance(data, *, minimum=MIN_SUPPORT):
    return np.diag(estimate(data, 0, minimum=minimum, diagnostics=False)["covariance"])/REFERENCE_BLOCKS


def coordinates(estimation, target_variance):
    targets = np.asarray(target_variance)[:2]
    if not np.isfinite(targets).all() or (targets <= 0).any():
        raise ValueError("reference variances must be finite and positive")
    bias = estimation["bias"][:2]/np.sqrt(targets)
    time = float(np.max(np.diag(estimation["covariance"])[:2]/targets))
    value = np.r_[bias, time]
    if not np.isfinite(value).all() or time < 0:
        raise ValueError("unavailable or nonfinite required time")
    return value


def resample(data, generator):
    indices = generator.integers(0, len(data["kept"]), len(data["kept"]))
    return {key: values[indices] for key, values in data.items()}


def simultaneous_bounds(point, samples, *, requested=None):
    requested = BOOTSTRAPS if requested is None else requested
    point, samples = np.asarray(point), np.asarray(samples)
    if len(samples) < .95*requested:
        raise ValueError("fewer than 95% usable whole-family bootstrap resamples")
    if samples.shape[1:] != point.shape or not np.isfinite(samples).all() or not np.isfinite(point).all():
        raise ValueError("invalid simultaneous bootstrap family")
    scale = samples.std(axis=0, ddof=1)
    fixed = scale == 0
    if np.any(samples[:, fixed] != point[fixed]):
        raise ValueError("zero bootstrap scale differs from point estimate")
    standardized = np.zeros(samples.shape)
    standardized[:, ~fixed] = abs(samples[:, ~fixed]-point[~fixed])/scale[~fixed]
    critical = float(np.quantile(standardized.reshape(len(samples), -1).max(axis=1), .95, method="higher"))
    return point-critical*scale, point+critical*scale, critical


def select(rows):
    """Exact calibration minimum; unsupported/unavailable rows never enter."""
    feasible = [row for row in rows if row["status"] == "calibration_feasible"]
    if not feasible:
        return {"status": "no_admitted_candidate", "selected_index": None}
    chosen = min(feasible, key=lambda row: (row["time_point_blocks"], row["index"]))
    best_upper = min(row["time_upper_blocks"] for row in feasible)
    plausible = [row["index"] for row in feasible if row["time_lower_blocks"] <= best_upper]
    return {"status": "ordering_unresolved" if len(plausible) > 1 else "conditional_grid_minimum",
            "selected_index": chosen["index"], "point_minimum_blocks": chosen["time_point_blocks"],
            "validation_time_blocks": int(np.ceil(chosen["time_upper_blocks"])),
            "minimum_conservative_bound_blocks": int(np.ceil(best_upper)),
            "plausible_minimizers": plausible}
