# Candidate-specific synthetic inference: frozen protocol

Status: **Reviewed pre-trial protocol; freeze before the single authorized campaign.** Prepared
2026-10-03. Freeze the approved text, implementation identity and fresh output
directory before generating any new draws. This is one bounded follow-up to an
uncertainty-method failure, not an amendment to the completed study.

## Scope and unchanged design

The original [frozen protocol](SAME_MASK_SYNTHETIC_PROTOCOL.md), SHA-256
`00395c3a5314d85c5f4e45674de1ec175bab1bf43a5ffd86cfeb11f4d4443f95`, governs every
detail except the explicit changes below. Its outputs remain unchanged. The
[original interpretation](same-mask-results-2026-10-03.md) records
5/512 usable whole-family calibration resamples, no selected policy, and no
proof that all thresholds violate tolerance.

Keep the same three scenarios, score-level signal/noise model, seven exact
finite threshold words, reject-all limit, same-mask counterfactuals, full
three-parameter response, empirical fourth moments, and wall-block pricing.
Keep the minimum 256 supported blocks, injection steps 0.02 and 0.04, derivative
disagreement limit 0.25, identifiability checks, reference precision at 1,024
blocks, bias allowance of one reference standard deviation, and no time cap.
No regularization, frozen-mask substitution, physical calibration, or changed
scientific tolerance is introduced. Reject-all has no science information or
finite observing time; it is not a remedy for unavailable inference.

Replace study-wide bootstrap availability with separate inference for each of
the fixed **21 scenario/finite-threshold slots**. Unavailable slots retain their
error allocations and uninformative intervals. Do not remove them from the
family or transfer their allocations to other slots.

## Fresh draws and fixed budget

Use PCG64 with `SeedSequence([20261004, stage, scenario, replicate])`, preserving
the original stage/scenario IDs and bootstrap substream conventions. The new
namespace applies to every stage, including independent reference and bootstrap
draws. Do not reuse original samples or outcomes for estimation or selection.

| Stage | Blocks per scenario | Change |
|---|---:|---|
| Development, 10 | 1,024 | New draws; mechanical checks only |
| Calibration, 20 | 4,096 | New draws |
| Independent clean reference, 21 | 4,096, clean only | New draws |
| Evaluation, 30 | 8,192 | New draws; frozen policy and fixed-grid diagnostics |
| Reference evaluation, 40 | 32,768 | New draws |
| Coverage, 50 | 64 independent replicates of 512 | New draws |
| Calibration bootstrap, 60 | **4,096 resamples** | New candidate-specific rule below |
| Post-calibration bootstrap, 60 | 512 per analysis | Original conditional diagnostic rule |

Within a calibration resample, preserve paired whole-block indices across a
scenario's thresholds, observed/clean endpoints, and injections. Scenarios are
resampled independently. Independently resample stage 21 once per bootstrap
replicate and share its resulting target across all slots. Replicates are IID
conditional on the original calibration/reference samples; slots need not be
independent. Compute every available slot rather than stopping a replicate at
another slot's failure. Record per-slot and reference failures separately.

## Fixed scales, failed roots, and intervals

For slot j, retain the original three-coordinate point vector

`x_j = (signed bias_1 / sigma_ref,1, signed bias_2 / sigma_ref,2, T_j)`,

where `T_j` is the continuous maximum of the two per-wall-block variance/target
variance ratios. Before any bootstrap draws, fix the positive scales

`s_j = (1, 1, max(1, T_j))`.

These are deterministic normalizations, not estimated standard errors. This is
an explicit interval-shape change from the original bootstrap-SD scaling. It
keeps each slot's three-coordinate max roots IID conditional on the original
data; estimating scales from the same roots would invalidate that IID argument.

Recompute each resample's support, primary response, covariance, bias, independent
reference target, and coordinate vector using the unchanged gates. Define

`R_j,b = max_c abs(x*_j,b,c - x_j,c) / s_j,c`.

Any failed/nonfinite resampled estimate or target gives `R_j,b = +infinity`.
A reference failure affects every slot for that replicate; a candidate failure
affects that candidate only. A refused original point gets an uninformative
interval immediately. Never discard failed roots, condition on successful
roots, replace them, or relax a gate. All 4,096 requested roots count.

If the critical value `q_j` defined below is finite, return the rectangle
`x_j,c +/- q_j * s_j,c`; intersect its time coordinate with `[0, infinity)`.
Otherwise return unavailable bias bounds `(-infinity, +infinity)` and time
`[0, infinity)`, with explicit reasons/counts. Machine-readable output must
encode unavailable/infinite bounds explicitly without invalid JSON numbers.

## Error allocation and checked order rank

Allocate nominal bootstrap statistical error `alpha_j = 0.04/21` and Monte
Carlo error `delta_j = 0.01/21` to each of the 21 slots. The within-slot max root
covers both signed biases and time jointly; these are not three additional
unadjusted tests. Bonferroni's union bound requires no independence across
slots, including their shared reference. [NIST's Bonferroni method](https://www.itl.nist.gov/div898/handbook/prc/section4/prc463.htm)

Let `p = 1 - alpha_j = 0.9980952380952381`, `B = 4096`, and sort all extended
roots increasingly. Choose the smallest one-based rank `k <= B` satisfying

`P[Binomial(B, p) >= k] <= delta_j`.

Then `q_j = R_j,(k)` is a conservative upper confidence endpoint for the
conditional bootstrap p-quantile. If no such rank exists or the order statistic
is infinite, refuse the candidate. To derive the bound, an order statistic
below the p-quantile requires at least k draws below that quantile; their count
has binomial probability bounded by the expression above. The IID
quantile/order-statistic argument is given in [NTIA TR-09-458, Section 4.2,
printed pages 22-23](https://its.ntia.gov/publications/download/TR-09-458.pdf).
For atoms/ties, including infinity, use the conservative inequality, not an
assumption of continuous roots.

Direct arithmetic gives:

| Quantity | Value |
|---|---:|
| `delta_j` | 0.0004761904761904762 |
| `P[Binomial(4096,p) >= 4096] = p^4096` | 0.000405924004749898 |
| `P[Binomial(4096,p) >= 4095]` | 0.003578948286153596 |
| Required rank | **4,096: the maximum root** |
| Union bound on MC failure at that rank | 0.008524404099747859 |

Thus **even one infinite root refuses that slot**. This is conservative by
design; it prevents failures from disappearing into a successful-only sample.
It does not cause a different candidate to fail. No normal approximation,
interpolated quantile, alternate rank, or bootstrap extension is permitted.

The conditional Monte Carlo quantile bound is finite-sample under exact IID
resampling and fixed original-data scales. Bootstrap statistical coverage is
still **nominal and subject to empirical assessment**, not an exact 95% coverage
theorem for this inverse-response estimator. Only if the ideal marginal
bootstrap intervals attain their allocated coverage would the statistical
0.04 and Monte Carlo 0.01 union budgets yield the intended family bound.
Bonferroni cannot cure an invalid marginal bootstrap, weak response, finite
difference bias, or model error.

## Admission, selection, and independent checks

Admit a slot only when it has finite inference and its entire two bias
intervals lie within `[-1,1]`. An interval overlapping both allowed and disallowed
values is unresolved; proven bias infeasibility requires at least one interval
to be wholly outside `[-1,1]`. Unavailable inference is never infeasibility.

Choose the exact minimum of `ceil(T_j)` among admitted candidates within each
scenario, breaking ties by original threshold index. Freeze its response,
target, word, and `ceil(time upper bound)` for validation. Retain continuous
time and the original comparison of admitted candidates' uncertainty ranges.
Call this a minimum **among admitted candidates**. A minimum over the entire
declared grid remains unresolved whenever an unavailable or not-proven-infeasible
competitor could have a shorter feasible time. A grid minimum is never proof
of an optimum over untested thresholds or physical observing conditions.

Keep the original evaluation/reference/coverage definitions and exposure
qualification unchanged: four fixed-response coordinates; 512 bootstrap
resamples per analysis; conditional shared-reference containment; all 64
coverage replicates in the denominator; and explicit failure accounting.
These remain conditional, per-policy diagnostics, not an added joint 95%
validation claim across scenarios or unconditional coverage of an optimum.
No calibration Jacobian is refitted and no threshold is reselected using those
stages. A straddling requirement, refused inference, failed coverage diagnostic,
or unsupported exposure cannot be reported as successful policy validation.

## Freeze, verification, and stopping rule

Before the one follow-up campaign, review/freeze this protocol and implementation;
test only deterministic fixtures for slot isolation, reference failures,
infinite roots, fixed scales, the exact rank and allocations, admission, and
global-ordering caveats. Record hashes, full seed identity, per-slot accounting,
scales, critical roots, bounds, selection, and refusal reasons in a fresh output
directory; preserve enough summaries for authenticated deterministic replay.

Run the fixed campaign once. Finish and retain its predeclared diagnostic
accounting even when a slot fails; then stop. No sample extensions, alternate
seeds, parameter/grid/gate/tolerance changes, held-out tuning, or repeated
attempts to obtain admission are permitted. If no candidate qualifies, report
that outcome. If a later validation stage fails, report the failed validation.
Any further scientific method change requires a separate future protocol and
does not revise either completed study. Accepted telescope evidence, channel
rulings, physical optimum fields, and manuscript claims remain unchanged.

## Implementation and historical reproduction

The versioned command is `rfisher response same-mask-candidatewise`. Its
manifest binds this protocol, all participating source files, settings and
numerical environment. Its explicit RNG factories use namespace 20261004 for
both generated data and every calibration/post-calibration resample.

Historical study reproduction remains pinned to RFIsher commit
`185e033adb082f1b496eb183a46c249cb47e4b60`. The follow-up uses shared model
helpers with explicit RNG/inference hooks; its new source identity does not
claim compatibility with the original study's source-authenticated artifacts.
The original protocol, source commit and completed outputs remain available
unchanged. No data from that completed study enter this follow-up's estimates.
