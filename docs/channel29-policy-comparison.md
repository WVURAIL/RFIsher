# Channel 29: practical fine and coarse masks

The September 9 comparison follows the failed retained-set residual control
study. It asks what the existing archive accounting assigns to practical fine
and coarse masks on the same historical frames. It does not adopt the failed
tighter bound, certify a physical residual, or replace the frozen coarse
candidate. The release is in the parent workspace at
`results/channel29_policy_comparison_2026-09-09`.

## Result and verification

All 21 policies were replayed. At the 50% calibration target, coarse retains
43.63% during evaluation; fine ranks 32/63/94/125 retain
48.45/49.52/51.15/58.01%, with assigned allowances
2.70/3.18/5.62/23.97 times the floor. The coarse median receives the floor.
The coarse 75th-percentile sensitivity retains 71.73% with 1.091 times the
floor, but this post-development comparison does not replace the candidate.
No modeled deployed growth ratio passes; the smallest remains 2.016.

All 5,053,625 Q16 requirements and 42 policy masks match an independent raw-power
recount. The two focused test files contain 70 passing checks, including exact
sentinel/tie arithmetic and same-mask exposure accounting. These verify software
and calculations, not physical calibration. The two-page PDF and all policy
rows are retained with the release.

## Fixed comparison

The channel 29 product, original health gate, current era, acquisition split,
stated floor and saved chain gain are unchanged. The two blocks contain 20,218
calibration and 20,211 historical evaluation frames. They share no acquisition
identities, but both have already informed development. The latter is therefore
not an untouched confirmation set.

The fine selector uses the previously recorded calibration PSD fallback anchor
202, its five designated bins 200–204, and the static 125-bin bulk. The
calibration fine anchor 198 and the full-era descriptive anchor 197 are different
quantities; neither replaces the recorded selector fallback. Four one-based
ranks are fixed at 32, 63, 94 and 125, corresponding to the ceiling of 1/4, 1/2,
3/4 and all of the bulk. Rank 125 includes the bulk maximum and is retained as
a sensitivity case, with no claim that its reference is uncontaminated.

Each rank and the coarse statistic receive thresholds at calibration retention
quantiles 25%, 50%, 75% and 90%. A common keep-all control gives 21 policies.
No rank, threshold or policy is selected using the evaluation outcomes.

Fine thresholds use the exact integer higher order statistic
`sorted_scores[ceil(q*(N-1))]`. Scores and ties remain integers. Serialized
always-masked bits are decoded separately from legitimate low scores; they
stay in the calibration population. An unavailable threshold or rank is not
replaced by an easier one. Coarse thresholds preserve the previous float
higher-quantile convention and are replayed by exact rational integer
comparison. Actual retention, including quantization and ties, is reported.

The plan and source identities are saved before fine scoring. The thresholds
and calibration score identity are saved before evaluation scoring. These
timestamps document execution order; they do not turn a previously inspected
archive into prospectively blinded evidence.

## What the reported residual means

Every policy uses the same frame allowance: the maximum of its finite coarse
shelf estimate and the original floor, or the floor when the shelf estimate
is unavailable. Retained means use the exposure of that exact mask. This
coarse-derived allowance favors selecting on the statistic that defines it.
A lower assigned value therefore does not prove that coarse masking leaves
less physical interference than fine masking.

The mask-only cost is available exposure divided by retained exposure. For
these equal-duration frames it equals available count divided by kept count.
It prices the on-sky time needed to restore one retained on-sky year under
unchanged retention, excluding telescope duty, science-mode losses and changes
in covariance. A 25% retention reference is a provisional planning value,
not a user-adopted scientific requirement.

The no-filter and modeled deployed comparisons use the same saved gain and
one-year forecast template within each world. The latter's 11.4 dB power
suppression remains hypothetical. No-filter dilation refusals stay unpriced.
Changing the mask can change coherence, noise covariance and signal response;
those effects require matched visibility measurements and are not fitted here.

Calibration-half drift ratios and calibration-to-evaluation changes are
descriptive point diagnostics. They do not override the original family gate,
provide simultaneous confidence intervals, or establish stationarity of a
floor-clamped physical residual.

## Reproduction

From the parent workspace, using the recorded analysis environment:

```sh
output/fisher-fixes-2026-09-08/analysis-venv/bin/python \
  RFIsher/scripts/compare_channel29_policies_v1.py \
  --release results/canfar_reanalysis_2026-09-09 \
  --output /absolute/path/to/new-analysis-directory
```

The output directory must be new. Original products are completely rehashed;
the score bundles bind source rows, geometry, acquisition provenance and exact
Q16 requirements. The numerical manifest preserves all policies, refusal
states, masks, contexts, overlaps, budgets and executed source copies.

## Visibility work remains separate

The accompanying readiness inventory found no matched in-band complex
visibility/complete-cleaner delivery. It did identify fifteen adjacent packed
voltage shards from one existing development event with 0.2943 seconds of
shared FPGA samples. A bounded coherence prototype is possible with those
files. Their partial allocation coverage, absent complete cleaner provenance
and single-event duration cannot establish physical calibration or independent
confirmation. The readiness note records the minimum matched input package.
