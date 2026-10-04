# Same-mask synthetic science bridge: fixed protocol

Status: reviewed and frozen before trials; no Monte Carlo trial preceded this protocol.
Base: RFIsher `1d969b20185bd5a52956727d420522b1cbe0c29b`.
Pre-trial clarification: the evaluation family and shared-reference conditional
coverage calculation below were specified during independent protocol review,
before any generated trial or result.

## Question and permitted conclusion

Can a causal threshold, acting on an observable noisy pilot, be carried through
the same simulated visibility samples to a correctly accounted two-parameter
precision/bias frontier, including dropped frames and dropped 10-second blocks?
The output will identify the least modeled observing time among the supported
feasible members of a fixed threshold grid, or report why no such selection is
supported. It will also measure the errors made by uniform-retention pricing,
Gaussian covariance closure, and freezing the mask during signal injections.

This is a score-level synthetic, fixed idealized response experiment. It is
not the PilotProxy DSP, a CHIME/CHORD forecast, a physical channel calibration,
or a new channel ruling. Its two dilation coordinates and growth nuisance are
illustrative response parameters. Existing accepted experiments remain frozen.
There is no automatic knee selection, downstream cleaning, or telescope claim.

## Generative model fixed before trials

Each independent block contains 100 frames at 0.1-second spacing. Blocks are
independent; correlation inside a block is retained. No claim of a real
instrument's temporal law is attached to these synthetic 10-second blocks.
Each frame has three complex visibility coordinates. Let

    L = [[1, 0, 0], [0.3, sqrt(0.91), 0],
         [0.2, 0.15, sqrt(0.9375)]]
    D = [[1, 0.2, 0.3], [0.2, 1, 0.3], [0.3, 0.3, 1]]
    clean(theta) = (0.8*n_real + 0.6j*n_imag) @ L.T
                   + ((s_real + 1j*s_imag)/sqrt(2) @ L.T)
                     * sqrt(0.3 + D @ theta)
    observed(theta) = clean(theta) + amplitude * state * r
    r = [1+0.2j, 0.7-0.4j, 0.3+0.6j]

The four Gaussian draws are independent standard normal coordinates. The
thermal term is deliberately improper complex data, so pseudocovariance
cannot silently be set to zero. Parameter order is synthetic parallel
dilation, synthetic perpendicular dilation, and synthetic growth. All three
parameters participate in every fit; growth has no separate veto.

Three predeclared scenarios share the construction, not random draws:

| Scenario | Amplitude | State law |
|---|---:|---|
| Clean control | 0 | always off |
| Intermittent coherent contamination | 2 | stationary Markov duty 0.2, on-to-off probability 0.2, off-to-on probability 0.05 |
| Persistent coherent contamination | 0.25 | always on |

Markov state starts from its stationary distribution independently in every
block. Fixed phase is intentional: a nonzero complex mean must be priced
separately from centered scatter. No parameter is adjusted to produce a
successful selection.

## Observable policy and exact threshold family

The detector sees only the current observed pilot power

    score = ceil(65536 * (abs(observed[0])**2
                          + 0.1*abs(observed[1])**2)).

Scores are checked before conversion to uint64. A finite threshold keeps a
frame exactly when `score <= eta_q16`; integer comparison is authoritative.
It never reads emitter state, amplitude, clean samples, future samples, or
parameter truth. Those variables belong only to simulation construction and
diagnostics. This deliberately simple observed statistic is not called CFAR
or assigned a PilotProxy detector profile.

The fixed finite grid is the integer words
`[1311, 3277, 8192, 32768, 131072, 524288, 18446744073709551615]`.
The final word provides the finite keep-all endpoint for valid generated
scores. The explicit `reject_all` limit is also evaluated: it retains zero
samples and has no finite science information or observing time. It is not
encoded as zero, a failed detector decision, or a numerical infinity.

For each finite candidate, average the kept frames within each block. A block
with fewer than two kept frames has no supported visibility moment and is
marked unavailable. Record kept-frame counts, valid-block indicators, and
unconditional valid-block fractions; never replace unavailable moments by
zero. Candidate inference requires at least 256 valid calibration blocks and
an identifiable three-parameter response. The separate requirement of 256 valid
evaluation blocks is validation only: it cannot change the frozen choice.
Lack of support, an unstable response, bias failure, and an empty feasible set
have separate statuses. The computational grid is not all causal policies.

## Paired counterfactual and same-mask response

For diagnosis, apply each observed-stream mask to both its observed frames and
their paired clean frames. They therefore have exactly the same support. This
clean counterfactual is available because the simulated components are known;
it identifies the calibration a physical application would need. It is never
subtracted from the stream as a mitigation step. The science statistics are
the three squared complex endpoint amplitudes, `q_j = abs(V_j)**2`.

Measure the full clean and observed complex means, covariance and
pseudocovariance on supported blocks. Use the empirical covariance of `q`
(fourth-order information) for the primary science calculation. Separately
compare the Gaussian-closure covariance from `rfisher.response.visibility`;
a failed closure remains a reported result, not a reason to change the model.

Measure the full observed-statistic Jacobian using paired injections
at `theta_j = +/-0.04` and `+/-0.02`, all other parameters zero. At every
injection, recompute observed pilot scores, masks, support, and both endpoints.
The primary derivative uses 0.02; 0.04 is a fixed finite-difference sensitivity
check. It includes signal-driven changes in the retained contamination. This
response is known through the generator's independent synthetic calibration;
that calibration is not thereby available for a physical channel. Also compute
the recomputed-mask clean-counterfactual derivative and the frozen-baseline-mask
observed derivative as named comparisons. Neither can replace the primary
response after a failure. Report all matrices and their differences. Refuse a
candidate if either primary step-size response is nonfinite/unidentifiable or
if the two recomputed primary derivatives
differ by more than 25% in relative Frobenius norm. Do not silently regularize
or remove the growth column to rescue a fit.

The fit uses the conditional clean statistic covariance and the recomputed
observed-statistic Jacobian. Its bias is the fitted response applied to the
observed-minus-clean mean statistic on the same mask; its actual sampling
covariance uses the observed empirical statistic covariance. This includes
selection-induced changes to thermal noise. Independence of a residual and
thermal noise is never assumed.

## Observing time and uncertainty

Let `p` be a candidate's valid-block probability and `C_q` the conditional
statistic covariance. Its per-wall-clock-block mean covariance is `C_q/p`,
not covariance multiplied by a retained-frame fraction. Equivalent ratio-mean
influence values are `I_valid*(q-mean(q))/p`. These paired block influence
values also provide uncertainty for clean/observed differences with missing
blocks. This is asymptotic ratio-mean exposure scaling. Retained frames within
a block do not count as independent confidence samples. All response and
coverage statements are local to theta=0, not a validated nonlinear fit away
from that point.

The clean control at the keep-all threshold defines reference precision at
1,024 complete 10-second blocks (10,240 synthetic seconds). This is one clean
reference exposure, not a maximum observing budget or a physical clean year.
The two target standard deviations come from the full three-parameter fit.
The allowed absolute bias in each dilation is its clean reference standard
deviation (`zeta=1`). Fixed-phase ensemble bias does not average away in the
declared independent-block model; variance scales with the number of blocks.

For each supported candidate, compute required whole blocks from the maximum
of the two variance/target-variance ratios. Report separate precision and bias
requirements. A candidate is admitted only if simultaneous calibration
uncertainty bounds satisfy both bias requirements. Use paired, whole-block
bootstrap resampling of all calibration outputs, including clean-reference
and injected response outputs, with 512 fixed resamples. A 95% max-standardized
deviation bound across the predeclared candidate/dilation bias and time
quantities supplies the simultaneous interval. Record all singular/refused
resamples; require at least 95% usable resamples, otherwise refuse inference.
Do not suppress infinite or unavailable time results.

The bootstrap vector has three coordinates for each candidate with finite,
supported, identifiable point estimates: signed parallel bias / its clean
reference sigma; signed perpendicular bias / its clean reference sigma; and
the continuous required-block count (maximum of both variance/target-variance
ratios, before ceiling). The family spans all three scenarios and all seven
finite words. Point-refused slots remain explicit refusals in the full output
family and cannot be selected. Every resample recomputes responses, means,
covariances, reference targets and ratios. A failure or unavailable/infinite
time in any included slot makes the entire resample unusable, rather than
shrinking its family. Resample the independent clean-reference calibration
independently, sharing its same target draw across all candidates.

Each coordinate's scale is its usable bootstrap sample standard deviation
(ddof=1). The critical value is the 95th percentile (`method="higher"`) of the
resample maxima of absolute departures from the point vector divided by those
scales. A zero-scale coordinate contributes zero only if every usable value
equals the point value exactly; otherwise inference is refused. Bounds are
point +/- critical value times scale. Bias feasibility uses the larger absolute
endpoint for each dilation. Report continuous time bounds, clipping only the
lower bound at zero, and ceiling whole-block times.

Select the exact minimum estimated required time in whole 10-second blocks
among admitted candidates: apply the ceiling before comparing candidates, and
break equal whole-block counts by ascending candidate order. Retain the
continuous required-block ratio as a diagnostic, not a sub-block operating
time. There is no 2%
plateau. Report the minimum conservative time bound as well. If intervals do
not resolve the ordering, label the optimum statistically unresolved and list
the plausible minimizers while freezing the deterministic candidate for the
independent check. It is only a minimum on this declared finite grid and model.
Evaluate the frozen candidate at its conservative whole-block time upper bound;
retain its point-estimated minimum separately. Validation cannot choose another
candidate. Report whether that exposure is in the 512 to 8,192 block range of
the finite evaluation design. Below 512, refuse an asymptotic validation claim;
above 8,192, label the time prediction as extrapolation under the declared
independent-block model. Neither condition permits extra trials or reselection.

Also report the naive prediction `T_ref / retained_frame_fraction`, and the
Gaussian-closure and frozen-mask alternatives, without using any alternative
to repair a failed primary result.

## Independent stages and fixed sample budget

Use NumPy PCG64 and seed construction `SeedSequence([20261003, stage, scenario,
replicate])`. Stages have distinct integers and no shared draws. Parameter
injections within a calibration block intentionally reuse that block's draws
for paired finite differences. Latent truth never determines the threshold.

| Stage | ID | Complete blocks per scenario | Permitted use |
|---|---:|---:|---|
| Development | 10 | 1,024 | mechanical checks only; no threshold/grid/model/acceptance tuning |
| Calibration | 20 | 4,096 | response, uncertainty and frozen selection |
| Clean-reference calibration | 21 | 4,096, clean scenario only | independent keep-all reference precision and response |
| Evaluation | 30 | 8,192 | evaluate the frozen candidate and all fixed-grid diagnostics; no reselection |
| Reference evaluation | 40 | 32,768 | independent high-statistics centers for coverage diagnostics |
| Coverage evaluation | 50 | 64 independent replicates of 512 | interval coverage for the fixed calibrated response and fixed policy |
| Bootstrap | 60 | 512 resamples per analysis | calibration, evaluation and reference uncertainty; fixed response after calibration |

Scenario integers are 0, 1 and 2 in table order. Bootstrap replicate namespaces
are `1000*source_stage + replicate`, with replicate 0 for calibration,
evaluation and reference, and 0 through 63 for coverage. Resampling the clean
reference uses distinct scenario integer 99. No bootstrap pairs independent
scenarios. It preserves pairing only among counterfactuals, thresholds and
signal injections belonging to the same generated block. The clean reference
comes from stage 21, independently of every stage-20 candidate, and its
resampled target is shared across the simultaneous family.

The evaluation, reference and each coverage replicate use a fixed four-coordinate
vector: the two signed bias/reference-sigma ratios and the two per-wall-block
parameter-variance/reference-variance ratios. The response matrix, clean-reference
targets, selected word and reported time are all frozen from calibration.
Resample paired clean/observed whole blocks 512 times; use the same 95% max-
standardized-deviation rule, zero-scale rule and 95%-usable-resample requirement
as calibration, over these four coordinates. No injected response is refitted
and no policy is selected in evaluation. The stage-21 reference-target sampling
uncertainty belongs to the calibration bootstrap; these post-calibration
intervals explicitly condition on the frozen target as well as the response.
The stage-30 check passes only if both absolute bias upper bounds are at most
one and both variance-ratio upper bounds are at most the frozen validation
block count, with adequate support and the declared exposure qualification.
An interval straddling a requirement is unresolved, not passing.

Stage 40 supplies one independently estimated four-coordinate reference center
and its four-coordinate simultaneous bootstrap interval. For every stage-50
replicate, record whether its interval contains that entire center. The point
coverage count has a two-sided 95% Clopper-Pearson binomial interval across all
64 requested independent replicates; an unavailable replicate counts as not
covering and is separately reported. This binomial statement CONDITIONS on the
realized, shared reference center, target and response. It is not an
unconditional interval for coverage of an unknown population parameter.

Report reference-center uncertainty separately: count replicate intervals that
contain the entire stage-40 confidence rectangle, and those intersecting it in
every coordinate. These are respectively definite/possible containment counts
if the population center lies in that rectangle, not a marginal confidence
interval obtained by treating the shared reference as 64 independent draws.
The declared diagnostic target is 95% point coverage; record whether 0.95 lies
inside the conditional Clopper-Pearson interval, without using inclusion to
claim proof of nominal coverage. Refuse a validation claim when it is excluded
or reference/replicate inference lacks support. No unconditional coverage of a
reselected optimum or physical Jacobian is claimed. Calibration-Jacobian
uncertainty remains separately reported by its bootstrap and derivative-size
check. Do not spend additional samples after any failure.

Run each stage once after implementation checks. Record failures, missing
support and departures from approximations. No parameter, threshold, seed,
sample size or acceptance limit is tuned after inspecting results. A genuine
implementation bug requires an explicit protocol/result erratum and a new
output directory; old outputs remain intact. New scientific questions require
a separately reviewed protocol.

## Reproducibility and meaningful implementation checks

Implement a narrow `rfisher response same-mask` command with explicit new
output directory, protocol/configuration identity, source hashes, seeds,
stage sizes, units and refusal/status fields. Write compact per-candidate CSV,
machine-readable JSON, a readable report, and a manifest. Revalidation must
authenticate the protocol and sources and independently reconstruct derived
time/selection/status products from saved sufficient block summaries. No
accepted archive record, capture product, or telescope bundle is an input.

Before new trials, test exact equality/zero/uint64 thresholds and reject-all,
support accounting and missing blocks, same-mask counterfactual identity,
recomputed versus frozen masks under injected signal, full nuisance fits,
both-component feasibility, deterministic exact minima and unresolved ties,
seed separation, provenance mismatch refusal, and output revalidation. Use
small deterministic fixtures for these tests. Existing visibility-response
unit tests remain in scope; do not duplicate their Gaussian-only experiment.
