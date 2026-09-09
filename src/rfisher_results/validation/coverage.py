"""Coverage bookkeeping for disjoint, predeclared experimental replicates."""
from __future__ import annotations

import math
from numbers import Integral

from scipy.stats import beta


def binomial_lower(successes: int, trials: int, *, alpha: float = .05) -> float | None:
    """One-sided Clopper-Pearson limit under independent Bernoulli trials.

    The caller must establish independence and freeze the rule being tested.
    This function cannot turn correlated frontier points into independent trials.
    """
    if any(isinstance(n, bool) or not isinstance(n, Integral) for n in (successes, trials)):
        raise ValueError("counts must be integers")
    if not 0 <= successes <= trials or not 0 < alpha < 1:
        raise ValueError("invalid counts or alpha")
    if not trials:
        return None
    return float(beta.ppf(alpha, successes, trials-successes+1)) if successes else 0.


def evaluate_replicates(replicates, *, minimum_retained=30, alpha=.05, comparisons=1):
    """Count unsupported replicates separately and as unconditional failures.

    'Success' means sufficient retained support AND claim >= injected truth.
    It says nothing about a population mean outside the specified experiment.
    Bonferroni limits permit dependence between the predeclared cases, while
    still requiring independent replicates within each case.
    """
    for count in (minimum_retained, comparisons):
        if isinstance(count, bool) or not isinstance(count, Integral) or count < 1:
            raise ValueError("support and comparisons must be positive integers")
    if not 0 < alpha < 1:
        raise ValueError("alpha must lie strictly between zero and one")
    seen = set()
    successes = unsupported = underbooked = 0
    ratios = []
    for row in replicates:
        key = row["id"]
        if not isinstance(key, str) or not key or key in seen:
            raise ValueError("replicate identities must be nonempty and unique")
        seen.add(key)
        kept = row["kept"]
        if isinstance(kept, bool) or not isinstance(kept, Integral) or kept < 0:
            raise ValueError("retained counts must be nonnegative integers")
        claim, truth = row["claim"], row["truth"]
        if kept:
            if any(value is None or not math.isfinite(value) or value < 0 for value in (claim, truth)):
                raise ValueError("nonempty kept sets require finite nonnegative claim and truth")
        elif claim is not None or truth is not None:
            raise ValueError("empty kept-set means must be unavailable")
        if kept < minimum_retained:
            unsupported += 1
            continue
        if claim >= truth:
            successes += 1
        else:
            underbooked += 1
        if truth > 0:
            ratios.append(claim/truth)
    return {
        "trials": len(seen), "supported": successes + underbooked,
        "unsupported": unsupported, "underbooked": underbooked, "successes": successes,
        "minimum_claim_over_positive_truth": min(ratios) if ratios else None,
        "success_probability_lower_marginal": binomial_lower(successes, len(seen), alpha=alpha),
        "success_probability_lower_simultaneous": binomial_lower(successes, len(seen), alpha=alpha/comparisons),
        "alpha": alpha, "comparisons": comparisons,
    }
