# Same-mask study assumptions and the science objective

The science objective is a modeled minimum observing time subject to the
bias and precision requirements for both dilation parameters. Demonstrating
that an uncertainty procedure has nominal 95% coverage is an additional
methodological objective. **95% was introduced in the synthetic protocols;
it is not implied by the science objective, a universal dissertation
completion gate, or a prescribed risk level for an observing site.**

The accepted maximum normalized bias tolerance, **`zeta=1`, remains fixed**.
This review concerns confidence/coverage and how uncertainty is represented
around that science rule. It does not propose relaxing the tolerance ceiling.
The dissertation's
[accepted rationale](https://github.com/WVURAIL/dissertation/blob/cb1bb565b4325d8f5e2ab0975a390f5d10a963bb/chapters/ch09_tolerance.tex#L535-L546)
cites Amara and Réfrégier's bias-versus-statistical-error criterion and adopts
`zeta=1`. That rationale supports the adopted bias screen; it does not set a
confidence coefficient or supply a coverage guarantee.

The dissertation's
[decision contract](https://github.com/WVURAIL/dissertation/blob/cb1bb565b4325d8f5e2ab0975a390f5d10a963bb/DECISION_CONTRACT.md#decision-rule)
requires appropriate confidence bounds at a declared coverage for a
saveability ruling, without specifying 95%. Conditional point forecasts
therefore remain distinct from qualified science verdicts with supported
uncertainty. This audit preserves that evidence requirement.

This audit clarifies interpretation. It does not change either frozen
protocol, any saved estimate or classification, or the single-campaign
stopping rule. No replacement confidence level or new experiment is adopted.

## Three separate questions

1. **Conditional model forecast.** Given an identified same-mask response,
   covariance model, reference target and allowed bias, what exposure is
   required for each threshold? Which supported candidates satisfy both
   dilation constraints? These are model-dependent quantities, and a point
   forecast can exist without an uncertainty certificate.
2. **Uncertainty and robustness assessment.** How sensitive are those forecasts
   to finite calibration samples, response estimation, model assumptions and
   mask recomputation? Intervals, stability checks and coverage experiments
   assess this question. Their numerical confidence levels and acceptance
   rules require justification against the decision objective while preserving
   the fixed science tolerance.
3. **Site operating qualification.** Does a threshold have an independently
   supported physical response, representative input data and compatible
   operational configuration for its declared channel and era? Neither of
   these score-level simulations establishes that qualification.

The distinction preserves missing information. A supported but uncertified
point remains a conditional diagnostic. A refused or unidentified response
does not acquire a defined forecast by removing a confidence requirement.
Unavailable competitors also prevent a claim that a chosen point minimizes
time over the entire threshold family.

## Where the percentages entered

The [original protocol](SAME_MASK_SYNTHETIC_PROTOCOL.md) sets synthetic science
precision using an independent clean reference at 1,024 blocks. Allowed
absolute bias is one reference standard deviation in each dilation (`zeta=1`).
The citation-backed maximum bias allowance remains one. The synthetic
1,024-block reference defines toy units and does not replace the physical
clean-year target; neither supplies a 95% requirement. The synthetic observing
times are not physical observing-time forecasts.

[NIST's confidence-interval guidance](https://www.itl.nist.gov/div898/handbook/eda/section3/eda352.htm)
describes 90%, 95% and 99% as commonly used confidence coefficients. The
coefficient describes a procedure's repeated-sample behavior. That convention
does not choose the appropriate uncertainty rule for this scientific decision.

| Choice | Role in the frozen studies |
|---|---|
| 95th-percentile simultaneous bootstrap bound | Original calibration intervals; also retained for the fixed-response evaluation/reference/coverage-replicate intervals in both studies. |
| At least 95% usable bootstrap resamples | Separate inference-availability rule: at least 487 of 512. The follow-up replaces this calibration rule, while retaining it for post-calibration diagnostics. |
| Statistical family error 0.04 plus Monte Carlo family error 0.01 | Follow-up calibration allocation over all 21 slots. The intended combined error budget is 0.05 only if nominal marginal bootstrap coverage is valid. The Monte Carlo order-statistic bound alone does not prove it. |
| Nominal 95% coverage target | A diagnostic target for the frozen selected policy's intervals, conditional on its response, target and realized shared reference center. |
| Two-sided 95% Clopper–Pearson interval | Uncertainty around the measured coverage frequency from 64 replicates. This confidence level is a separate choice from the nominal coverage target. |

The implementation locations are
[`simultaneous_bounds`](../src/rfisher/response/same_mask.py),
[`fixed_interval`, `binomial_interval` and `evaluate`](../src/rfisher/response/same_mask_report.py),
and the follow-up's
[`order_rank`, `root_interval` and `calibrate`](../src/rfisher/response/same_mask_candidatewise.py).
The [follow-up protocol](CANDIDATEWISE_SYNTHETIC_PROTOCOL.md) records the exact
allocations, interval shape and resulting maximum-order rank.

## What the saved outcome does and does not establish

The clean keep-all selection met the frozen conditional evaluation rule at
its assessed 1,369-block exposure. Its 57/64 reference-center containment
rate was 89.1%, with conditional interval `[0.787542774, 0.954878980]`.
Including 0.95 means the declared diagnostic did not exclude that target;
it does not demonstrate 95% coverage. The saved
`conditional_validation=true` records the frozen rule's outcome, not a
general science or operating-policy certification.

Interval shape also matters independently of the percentage. The follow-up
uses fixed scales `(1, 1, max(1,T))` and one joint maximum root for both signed
biases and time. For clean word `32768`, the paired point bias is exactly zero
and all 4,096 roots are finite, but a critical root of approximately 10.804
widens both bias bounds to approximately `[-10.804, 10.804]`. The bias gate
remains unresolved because the joint rectangle is wide. This is conservatism
from the selected interval construction, not a measured nonzero clean bias.

A descriptive, post hoc reading of the saved point coordinates gives an
additional distinction. Six original points were refused independently of
the confidence level: three for low support and three for an unstable
finite-difference response. Nine uncertainty-refused slots still have finite
point forecasts. All five available clean-control points have zero paired
bias. For each contaminated scenario, however, all five available points
already exceed the fixed `zeta=1` bias allowance in at least one component.
The smallest maximum absolute normalized bias is 20.1866 for intermittent
contamination and 72.2191 for persistent contamination. Removing the 95%
requirement alone therefore creates no feasible saved contaminated point.
The two unavailable points in each contaminated scenario still prevent an
exhaustive exclusion. This reading introduces no new qualifying policy.

Other candidates have distinct limitations: low block support, unstable
finite-difference response, a refused inverse fit, or incomplete uncertainty
inference. These reasons remain separate from a measured violation of a bias
tolerance. The [result document](same-mask-candidatewise-results-2026-10-03.md)
retains them and the unresolved ordering/global minimum.

Before using these procedures for a new decision, the assumptions to justify
include the physical response model and reference exposure, the 256-block
support and 25% derivative-disagreement gates, finite threshold grid,
21-slot family versus separate scenario decisions, interval construction,
and the decision's treatment of uncertainty. With the declared error budgets
and 4,096-root maximum, even one failed root refuses a candidate. The local
signal expansion at `theta=0`, independent 10-second blocks, asymptotic `C_q/p`
exposure scaling and frozen-response/shared-reference coverage diagnostic
also delimit the model. The maximum normalized bias tolerance stays one.

A future uncertainty specification should justify the joint bias/precision
decision risk for a frozen policy assessed on independent data. Interval
coverage can remain a diagnostic without becoming an automatic dissertation
completion gate. No new level is adopted here. Any future review must preserve
the completed studies and distinguish model forecasts from robustness evidence
and site qualification; it cannot retroactively change the recorded outcomes.
