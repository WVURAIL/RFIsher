#!/usr/bin/env python3
"""Known-moment synthetic check of the explicit visibility response interface."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from rfisher_results.validation import visibility_response as response


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(20260919)
    count = 250000
    clean_cov = np.diag([1., .8, 1.2, .7, 1., .9])
    residual_cov = np.diag([.03, .01, .02, .02, .04, .01])
    mean = np.array([.1, .2, 0, -.1, 0, .1])
    kernels = np.array([np.diag(np.eye(6)[j] + np.eye(6)[j+3]) for j in range(3)])
    clean = rng.multivariate_normal(np.zeros(6), clean_cov, count)
    contaminated = clean + rng.multivariate_normal(mean, residual_cov, count)
    qc = np.einsum("ni,aij,nj->na", clean, kernels, clean)
    qo = np.einsum("ni,aij,nj->na", contaminated, kernels, contaminated)
    analytic = response.quadratic_contamination(np.zeros(6), clean_cov, mean,
                                                clean_cov+residual_cov, kernels)
    jacobian = np.array([[1., .1, 1.], [.2, 1., .7], [.5, -.2, 1.8]])
    names = ["synthetic_dilation_parallel", "synthetic_dilation_perpendicular", "synthetic_growth"]
    fit = response.linear_parameter_response(jacobian, analytic["clean_statistic_covariance"],
                                             analytic["statistic_bias"],
                                             analytic["observed_statistic_covariance"],
                                             parameter_names=names)
    empirical_bias = (qo-qc).mean(0)
    empirical_cov = np.cov(qo.T)
    bias_se = np.std(qo-qc, axis=0, ddof=1)/np.sqrt(count)
    max_bias_z = float(np.max(np.abs(empirical_bias-analytic["statistic_bias"])/bias_se))
    covariance_error = float(np.linalg.norm(empirical_cov-analytic["observed_statistic_covariance"])
                             / np.linalg.norm(analytic["observed_statistic_covariance"]))
    passed = max_bias_z < 5 and covariance_error < .025
    def lists(values):
        return {key: value.tolist() if isinstance(value, np.ndarray) else value
                for key, value in values.items()}
    sources = [Path(__file__).resolve(), Path(response.__file__).resolve()]
    result = {"schema_version":1,"experiment":"fixed idealized quadratic response; synthetic moments",
              "physical_response_qualified":False,"samples":count,"seed":20260919,
              "coordinate_order":"three real then three imaginary visibility components",
              "units":"arbitrary synthetic visibility units; not physical channel calibration",
              "operator_scope":"fixed idealized statistic; no downstream cleaning",
              "analytic":lists(analytic),"fit":lists(fit),
              "empirical_statistic_bias":empirical_bias.tolist(),
              "empirical_statistic_covariance":empirical_cov.tolist(),
              "empirical_parameter_bias":(fit["response"]@empirical_bias).tolist(),
              "maximum_bias_standard_errors":max_bias_z,
              "relative_statistic_covariance_error":covariance_error,
              "criteria":{"maximum_bias_standard_errors":5.,"relative_covariance_error":.025},
              "passed":passed,
              "sources":[{"path":str(p),"sha256":hashlib.sha256(p.read_bytes()).hexdigest()} for p in sources]}
    (args.output/"validation.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"passed":passed,"maximum_bias_standard_errors":max_bias_z,
                      "relative_statistic_covariance_error":covariance_error}))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
