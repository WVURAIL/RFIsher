# Empirical calibration and null-validation power

`rfisher_results.validation.null_calibration` implements the declared strict
higher-quantile rank, its continuous same-null IID order-statistic reference,
exact binomial-cap acceptance counts, beta-binomial predictive tail and the
union-bound probability of accepting a dependent mixed policy family.

Calibration randomness and validation randomness are separate. At 4,000
calibration draws and nominal 1%, rank 3,961 gives Beta(40,3961) for the true
exceedance probability over repeated continuous-null calibration samples.
This is not a posterior for an inspected threshold. Strict discrete ties
make this reference stochastically conservative only under the same-law IID
assumptions. A pointwise or simultaneous confidence bound is distinct from
the probability that an experiment will demonstrate its target cap.

The completed study is in
`../../results/fine_null_diagnostics_2026-09-09/README.md`. It recounts all
1,334 primary rows without changing their gates, compares all six stored
floating stages to exact Q16 decisions, and separately checks fixed-transform
float at the common Q16 boundary. It generates no new campaign trials.

Use `scripts/analyze_fine_null_calibration.py --help` for the two-step
descriptive-plan freeze and analysis interface, and
`scripts/plot_fine_null_calibration.py` for the two reference/design figures.
The study release includes source snapshots, input hashes, the independent
recount and mathematical audit, and full result tables. Hypothetical designs
require fresh declared calibration/evaluation identities; do not append
trials to a fixed-count inspected experiment or retune its threshold family.

Run `python -m pytest -q tests/test_null_calibration.py` for the focused rank,
integration, gate-boundary and dependent-family tests. These operations need
CPU only; set numerical-library thread limits to one alongside an active
GPU campaign.
