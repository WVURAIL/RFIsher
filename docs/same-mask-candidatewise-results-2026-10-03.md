# Candidate-specific synthetic study: bounded clean-control result

The single predeclared follow-up admitted two thresholds in the clean control
and selected its keep-all word by minimum point-estimated observing time.
Neither contaminated scenario admitted a threshold. **The ordering of the two
admitted clean thresholds and the optimum over the entire grid both remain
unresolved.** This supplies no contaminated-signal recovery policy or physical
channel ruling.

The [assumption audit](same-mask-assumptions.md) distinguishes these conditional
model forecasts from uncertainty/robustness assessment and site qualification.
The studies' 95% choices are methodological assumptions, not the science
tolerances or a universal completion requirement.

The [protocol](CANDIDATEWISE_SYNTHETIC_PROTOCOL.md) was reviewed and frozen
before fresh draws. The original study's
[whole-family inference refusal](same-mask-results-2026-10-03.md) remains
unchanged. This follow-up kept the model, threshold grid, support/response
gates, tolerances and stage sizes, while using independent seeds and the
declared candidate-specific uncertainty rule. No samples, seeds, thresholds
or gates were changed after observing the outcome. This is the final campaign
in the bounded follow-up; there is no extension or further trial here.

## The selected clean-control point

The admitted finite words were `524288` and `18446744073709551615` (keep-all).
The latter had the smaller point requirement: 1,079.479 continuous blocks,
rounded upward to **1,080 whole 10-second synthetic blocks**. Its upper time
bound was 1,368.815 blocks, so independent evaluation assessed the frozen
**1,369-block exposure**. The independent clean reference set precision at
1,024 blocks; it was not an exposure cap.

The other admitted word had a point requirement of 1,273 whole blocks. Their
uncertainty ranges overlap, so even their relative ordering is unresolved.
Five additional clean-control thresholds lack an admitted result. Choosing
the point minimum among admitted candidates therefore does not establish an
entire-grid minimum, an optimum over untested thresholds, or an observing time
for any real channel.

At the frozen 1,369-block exposure, independent evaluation met the declared
conditional requirements for both dilation coordinates: both bias bounds
were zero, and the upper bounds on required exposure were 1,075.994 and 1,175.354
blocks. This uses the declared asymptotic wall-block covariance scaling; the
exposure lies within its declared 512–8,192-block qualification range. The response,
precision target and policy stay frozen at local signal coordinates zero.
It is not an unconditional validation of the estimated response or selected
optimum.

## Coverage remains a limited diagnostic

Of 64 independent coverage replicates, **57 contained the realized shared
reference center: 89.1%**. The conditional Clopper–Pearson interval was
`[0.787542774, 0.954878980]`. It includes 0.95, so the protocol's diagnostic
did not exclude its nominal target. **That does not demonstrate 95% coverage.**
The interval is broad and conditions on the frozen response, target, policy
and realized reference center.

All 64 replicates retained their denominator and had 512 usable diagnostic
resamples. Separately, 52 intervals contained the entire uncertain reference
rectangle and 59 intersected it. These counts retain reference uncertainty
without recasting the conditional binomial interval as an unconditional
coverage guarantee. The machine field `conditional_validation=true` means
only that the predeclared conditional evaluation and diagnostic gates passed.

## Refusals and contaminated scenarios

All 21 finite slots kept their error allocations. Every slot stored 4,096
extended roots, and no failed root was discarded. There were no shared
reference failures.

| Final calibration classification | Slots |
|---|---:|
| Admitted, both in clean control | 2 |
| Bias interval wholly outside the allowed range, contaminated keep-all only | 2 |
| Finite but unresolved bias requirement | 2 |
| Uncertainty refused because at least one root was infinite | 9 |
| Original point refused | 6 |

The lowest word had only 33, 29 and 30 supported calibration blocks in the
three scenarios, below 256. The next word failed the original derivative
stability gate in each scenario. The nine uncertainty refusals retained
candidate-specific derivative failures; one also retained a Fisher-matrix
conditioning failure. Even a single infinite root refused its slot under
the declared maximum-order rule. A wide finite rectangle can also remain
unresolved without proving a tolerance failure.

Each contaminated scenario's keep-all bias interval was outside the allowed
range under the declared nominal synthetic inference. Its six other finite
candidates remained unavailable or unresolved. Thus no admission does not
establish that every threshold is infeasible, and it does not recommend the
reject-all limit. Reject-all separately retains zero samples and has no
science information or finite observing time.

The saved comparisons also retain why the full response matters. For the
clean `524288` word, continuous point requirements were 1,272.286 blocks for
the recomputed-mask empirical response, 1,027.424 for naive retained-fraction
scaling, 1,280.765 with Gaussian closure, and 1,084.275 with the frozen-mask
response. These are labeled point diagnostics, not alternative qualified
policies. The selected keep-all empirical point was 1,079.479 blocks versus
1,024 from naive scaling and 1,104.789 from Gaussian closure.

## Preserved evidence and reproducibility

The saved study occupies 148,650,233 bytes outside the checkout at
`output/local-dissertation-validation-2026-10-03/science-candidatewise-validation/`
in the workspace. It includes both protocols, source/settings/environment
identity, every stage summary, all extended roots, candidate CSV and final
report. Its manifest SHA-256 is
`997e0ea3c4dcf64df18c7d788184e70d97380d772e9cfdda8be62f38c3baba1d`.
The frozen follow-up protocol SHA-256 is
`e4fe585d16567081f55a43bfbab63db4d9634b680456606834e87a3ab50a9299`.
The numerical environment was CPython 3.12, NumPy 2.5.2 and SciPy 1.18.1.

[Reproduction instructions](same-mask-candidatewise.md) include authenticated
saved-summary reconstruction. The sibling `candidatewise-validation/`
directory preserves program-check logs, the pretrial identity, a read-only
saved-outcome ledger, and independent review/reconstruction records. Program
checks distinguish implementation behavior from empirical coverage or
physical qualification. Representative telescope measurements and a physical
same-mask response remain external requirements.
