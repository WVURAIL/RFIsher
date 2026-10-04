# Same-mask synthetic study: inference refused

The fixed-budget study completed, but **no candidate received a simultaneous
uncertainty certificate**. Only 5 of 512 calibration bootstrap resamples were
usable; 507 failed the predeclared primary-Jacobian step-size stability check.
The protocol required at least 487 usable resamples. Its whole-family rule
therefore refused inference for every otherwise supported point, including
the clean control.

This is a failure to establish the study's uncertainty guarantee. It is not
evidence that all thresholds violate a science tolerance, that clean data are
infeasible, or that the reject-all limit should be chosen. No candidate was
selected, so there is no selected-policy held-out validation or policy coverage
result. All declared evaluation/reference/coverage draws were preserved; the
fixed-grid held-out point diagnostics remain unqualified diagnostics. No new
physical channel ruling follows from this score-level simulation.

## What was retained

The [reviewed protocol](SAME_MASK_SYNTHETIC_PROTOCOL.md) and
[reproduction instructions](same-mask-validation.md) describe the observable
score, seven finite thresholds, reject-all limit, independent stages and
unchanged sample budget. The implementation carries recomputed observed-stream
masks through paired complex visibility endpoints, empirical fourth-order
covariance, all three fitted parameters, and wall-clock exposure accounting.
Its minimum is in whole 10-second blocks on the declared finite grid.

Of the 21 finite scenario/threshold slots:

- 16 had supported, identifiable point estimates but were refused by the
  common uncertainty gate.
- Three lowest-threshold slots had only 28, 28 and 32 supported calibration
  blocks, below the required 256.
- Two additional slots failed the step-size stability check at their original
  point estimate.

The three reject-all records separately have zero retained samples, no science
information and no finite observing time. They are endpoint accounting, not recommendations.

The clean keep-all point illustrates why global refusal must not be read as
scientific infeasibility: its paired contamination bias is exactly zero, all
4,096 calibration blocks are supported, and its primary derivative's relative
step-size difference is approximately 0.000039. It still receives no certificate
because the declared uncertainty family includes less stable thresholds. Its
point-estimated 1,078 whole-block requirement is not a validated minimum or an
accepted operating point.

## Attribution from exact replay

An external observer recorded the first failing candidate during deterministic
replay of the **same original 512 resamples** from saved summaries and seeds.
No new resamples, model changes or replacement thresholds were introduced.

| Scenario | Exact threshold word | First-failure count |
|---|---:|---:|
| Clean control | 3277 | 445 |
| Clean control | 8192 | 28 |
| Intermittent coherent contamination | 8192 | 26 |
| Intermittent coherent contamination | 524288 | 2 |
| Persistent coherent contamination | 8192 | 5 |
| Persistent coherent contamination | 32768 | 1 |

Each failed resample stops at its first unstable included candidate; this is
not a count of every candidate that would fail in that resample. The clean
3277-word point has 687 supported blocks and a point derivative difference of
0.221, close to the fixed 0.25 limit. Its behavior is evidence of sensitivity
in the finite-sample derivative/inference procedure, not a physical residual
measurement. The original aggregate failure histogram is unchanged.

## Verification and limits

Authenticated reconstruction passed for calibration, the final result, the
candidate CSV and readable report. It generated no new simulated data. The
protocol and all original outputs remain unchanged. Deterministic tests cover
integer decisions, signal-induced changes in masks, joint support, nuisance
fits, both dilation constraints, whole-block minima, missingness, conditional
coverage bookkeeping and provenance refusals. These checks validate program
behavior; they do not turn this empirical inference refusal into a successful
policy validation.

The saved study occupies 148,195,567 bytes outside the source checkout at
`output/local-dissertation-validation-2026-10-03/science-validation/` in the
workspace. Its manifest SHA-256 is
`000bddddd71418ee33f0134514316bf7b60d80242c19ec7c66bcd5cf6bbe8304`.
The frozen protocol SHA-256 is
`00395c3a5314d85c5f4e45674de1ec175bab1bf43a5ffd86cfeb11f4d4443f95`.
The numerical environment was CPython 3.12, NumPy 2.5.2 and SciPy 1.18.1.
The sibling `science-bootstrap-attribution.json` records the replay observer's
hash and its attribution limits; `science-revalidation-diagnostic.json` records
the successful authenticated reconstruction.

Any attempt to improve derivative estimation or change the simultaneous
inference family requires a separately reviewed protocol and new output
directory. The completed run must not be retuned, extended or selectively
reinterpreted as a successful selection. Physical application still requires
an independently calibrated same-mask response and representative telescope
measurements; neither is supplied here.
