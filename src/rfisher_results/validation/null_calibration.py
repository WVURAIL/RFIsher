"""Order-statistic calibration and fixed-sample binomial acceptance diagnostics.

These are design/reference calculations, not permission to extend or retune an
experiment after evaluation. Policies may share trials: no independence between
policies is assumed by the family lower bound.
"""
from __future__ import annotations

from fractions import Fraction
import math

import numpy as np
from scipy.stats import beta, betabinom, binom
from scipy.special import logsumexp


def higher_rank(trials: int, nominal_pfa: float) -> int:
    """One-based rank for ceil((1-p)*(n-1)), calculated without float rounding."""
    if isinstance(trials, bool) or not isinstance(trials, int) or trials < 1:
        raise ValueError("trials must be a positive integer")
    p = Fraction(str(nominal_pfa))
    if not 0 < p < 1:
        raise ValueError("nominal_pfa must lie strictly between zero and one")
    v = (1-p)*(trials-1)
    return (v.numerator + v.denominator - 1)//v.denominator + 1


def calibration_reference(trials: int, nominal_pfa: float) -> dict:
    """Continuous-IID repeated-calibration distribution of strict exceedance p.

    If T is order statistic r from n draws, 1-F(T) ~ Beta(n-r+1,r).
    This is a sampling distribution, not a posterior or a confidence interval
    conditional on one observed threshold. For atoms and a strict comparison,
    it provides an upper stochastic reference under the same IID null law.
    """
    rank = higher_rank(trials, nominal_pfa)
    a, b = trials-rank+1, rank
    return {"trials": trials, "rank": rank, "beta_a": a, "beta_b": b,
            "mean_pfa": float(beta.mean(a, b)),
            "sd_pfa": float(beta.std(a, b)),
            "central_95_pfa": beta.ppf([.025, .975], a, b).tolist(),
            "assumption": "continuous IID scores; calibration and validation share the same null law"}


def accepted_count_limit(trials: int, cap: float, *, family_tests: int = 1334,
                         confidence: float = .95) -> int:
    """Largest k whose one-sided Bonferroni Clopper--Pearson upper <= cap.

    CP inversion is equivalent to BinomialCDF(k; n, cap) <= alpha/family.
    Returns -1 if even zero observed events cannot demonstrate the cap.
    """
    if trials < 1 or int(trials) != trials or family_tests < 1 or int(family_tests) != family_tests:
        raise ValueError("positive integer trial and family counts required")
    if not 0 < cap < 1 or not 0 < confidence < 1:
        raise ValueError("cap and confidence must lie strictly between zero and one")
    alpha = (1-confidence)/family_tests
    lo, hi = -1, trials
    while hi-lo > 1:
        k = (lo+hi)//2
        if binom.cdf(k, trials, cap) <= alpha:
            lo = k
        else:
            hi = k
    return lo


def gate_count_limit(trials: int, nominal_pfa: float, *, family_tests: int = 1334,
                     confidence: float = .95, cap_multiple: float = 2.) -> int:
    """Full low-tail acceptance region, including pointwise CP width.

    Refuses a noncontiguous region instead of presuming cap-only acceptance.
    """
    end = accepted_count_limit(trials, cap_multiple*nominal_pfa,
                               family_tests=family_tests, confidence=confidence)
    if end < 0:
        return -1
    k = np.arange(end+1)
    alpha = (1-confidence)/2
    lower = np.zeros(end+1)
    lower[1:] = beta.ppf(alpha, k[1:], trials-k[1:]+1)
    upper = beta.isf(alpha, k+1, trials-k)
    accepted = upper-lower <= nominal_pfa
    indices = np.flatnonzero(accepted)
    if not len(indices):
        return -1
    last = int(indices[-1])
    if not np.all(accepted[:last+1]):
        raise ValueError("acceptance region is not a contiguous lower tail")
    return last


def prospective_power(calibration_trials: int, validation_trials: int,
                      nominal_pfa: float, *, family_tests: int = 1334) -> dict:
    """Reference power for fresh independent calibration and validation."""
    ref = calibration_reference(calibration_trials, nominal_pfa)
    limit = gate_count_limit(validation_trials, nominal_pfa, family_tests=family_tests)
    # Sum the rejection tail directly: 1-CDF loses precision for large designs.
    failure = float(np.exp(logsumexp(betabinom.logpmf(
        np.arange(limit+1, validation_trials+1), validation_trials,
        ref['beta_a'], ref['beta_b'])))) if limit >= 0 else 1.
    failure = min(1., max(0., failure))
    power = 1-failure
    return {"calibration_trials": calibration_trials, "validation_trials": validation_trials,
            "nominal_pfa": nominal_pfa, "accepted_exceedances_max": limit,
            "single_policy_power": power, "single_policy_failure_probability": failure,
            "reference": "continuous same-null IID order-statistic calibration and fresh fixed-size validation"}


def family_power_lower_bound(policy_failure_probabilities: list[float]) -> float:
    """Union-bound lower bound; valid without independence among policies."""
    if any(not math.isfinite(p) or not 0 <= p <= 1 for p in policy_failure_probabilities):
        raise ValueError("failure probabilities must be finite and within [0,1]")
    return max(0., 1-math.fsum(policy_failure_probabilities))
