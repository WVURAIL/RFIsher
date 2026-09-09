# Channel 29: frozen candidate follow-up

The next step after the September 9 CANFAR reanalysis is a frozen **coarse
candidate design**. The protocol and metadata checks do not accept a calibrated
science policy. The release is in the parent workspace at
`results/channel29_followup_2026-09-09/`; the earlier reanalysis remains unchanged.

The new exclusion ledger contains **9,335 acquisitions**, including **121**
missing from the older physical-evidence plan. All frequency shards of an event
stay together, including quarantined or unscored inputs. The local metadata
audit identified no untouched CHIME cohort. A new processing date does not make
an old acquisition new evidence.

## Frozen selector and reference

Channel 29, frequency ID 614, uses the exact rational
`eta = 4508969069674235 / 4503599627370496 = 1.0011922556950015`.
The development geometry has target/reference squared norms 6372/12713,
128-sample detector windows, 2,048 summed input streams, a 16,384-sample frame,
and sample rate 390,625 Hz. Geometry, spectral sense, weight identities, input
map and the detector/decision contracts are bound in the protocol.

Reject an eligible frame exactly when

```
p_target * 12713 * eta_denominator > 6372 * p_ref_sum * eta_numerator
```

Equality is kept only if the frame is valid, healthy and in the trusted cohort.
A false rejection flag does not make an invalid frame usable. The existing
`ResidualProductView.rejected_at_multiplier()` implements the coarse comparison;
this threshold is not rounded into a fine Q16 policy. Equal frame exposure is
required before count retention can be interpreted as exposure retention.

The original calibration retained 50%; the already inspected evaluation retained
43.6347%. Its whole-block exposure-cost ratio is **1.145878**. The smaller
**1.013871** ratio between the original calibration halves is a different
comparison. Both are recorded. A floor-clamped residual ratio of one is not a
measurement of physical stationarity.

## Two freezes and explicit planning rules

The first freeze records the candidate threshold, geometry, source hashes,
development exclusions and experimental hypotheses. Its status is
`candidate_frozen`; physical calibration remains pending. Short independent
control and injection experiments can begin before seasonal confirmation.
All such attempts become development/calibration exclusions.

A later, separately frozen calibration artifact must bind the same candidate,
geometry and policy, its measured method/evidence, and every additional
calibration acquisition. The confirmation interval is then resolved
mechanically: the next UTC midnight after that freeze through 730 days later,
with two fixed 365-day halves. An acquisition must fit wholly within one half.
This is a **new planning duration and fixed-window partition**, not the old
observed-time-midpoint algorithm. It allows room for six populated months and
a 270-day span per half. It does not imply one retained on-sky year of exposure.

The candidate rules are provisional research choices:

- Minimum retention: **25%**, a planning default pending a user-adopted target;
  the corresponding mask-only exposure cost is at most four.
- Each confirmation half: at least 30 retained frames, six populated months,
  and 270 days of pre-policy eligible support. A populated month has at least
  30 eligible frames from five acquisitions on three distinct days. The
  30 retained-frame minimum is checked separately.
- Drift: symmetric cost/residual ratios between the two fixed future halves,
  with provisional point limits of 1.05/1.10. Original-calibration versus
  confirmation drift is reported separately.
- Uncertainty: 95% is a declared target. The actual dependence blocks,
  simultaneous interval method and coverage evidence must be measured and
  frozen with the calibration before confirmation. Frames are not independent
  trials; separate marginal intervals are not joint 95% coverage. Unsupported
  resamples remain failures rather than being discarded.
- Residual controls: target 95% joint block coverage at 95% calibration
  confidence, with independent validation. A correction fitted to the earlier
  digital experiment is not imported into telescope data.

The primary hypothesis is both dilation budgets at zeta=1 in the 200 ns forecast
world; growth and zeta=0.5/0.3/0.1 are specified secondary/sensitivity results.
The world's **11.4 dB suppression remains hypothetical**. No measured filter
credit is enabled by freezing it. Actual in-band signal/noise/RFI transfer,
coherent mean, stochastic covariance, science response and same-mask exposure
are still required. Missing evidence is inconclusive, never a numerical pass.

The fixed interval is not extended after seeing outcomes. Insufficient support
at its end remains inconclusive. Changes require a new version and fresh
confirmation data. Changes in input map, geometry or the causal era monitor
halt the candidate; later data do not retroactively rewrite its assignments.

## Reproducible commands

Use the environment recorded in the release. From the workspace, a new design
requires a **new output path**; the original freeze is never overwritten:

```sh
set -e
cd /home/djg/rail
PY=output/fisher-fixes-2026-09-08/analysis-venv/bin/python
export PYTHONPATH=/home/djg/rail/RFIsher/src:/home/djg/rail/pilot-proxy/src
"$PY" RFIsher/scripts/freeze_channel29_followup.py freeze \
  --study results/canfar_reanalysis_2026-09-09 \
  --metadata results/channel29_followup_2026-09-09/metadata \
  --product products/chime_pilots_rebuild_20260829/products/_per_pilot/614.npz \
  --output /absolute/path/to/a/new/frozen-candidate
```

The builder authenticates the prior study and metadata manifests and rehashes
one development product before decoding only its small geometry fields. It
records actual freeze time, source copies and hashes. The protocol checksum
provides integrity, not an externally notarized preregistration.

Metadata-only candidate audit:

```sh
"$PY" RFIsher/scripts/freeze_channel29_followup.py audit \
  --protocol results/channel29_followup_2026-09-09/frozen/protocol.json \
  --units /path/to/candidate-unit-metadata.json \
  --output /absolute/path/to/new/cohort-audit.json
```

The input is a list, or an object with a `units` list. Every unit requires a
complete `event`, unique `unit_id`, and trustworthy timezone-aware acquisition
`start`/`end`. Frequency shards of the same event must report the same complete
acquisition interval. Missing timestamps, development reuse, pre-freeze starts,
future-dated records, conflicting event intervals and boundary crossings refuse
eligibility. Timestamps are never inferred from filenames.

An optional `--calibration` supplies a separately sealed
`rfisher-coarse-calibration-v1` metadata bundle. Passing its hashes does not
establish calibration quality. The audit reports candidate metadata checks,
confirmation metadata checks and whether the interval is complete separately.
It always leaves `scientific_certification` and `operational_acceptance` false.

## Remaining work

- [x] Freeze the exact coarse candidate and metadata eligibility rules.
- [x] Repair the development exclusion set and test reuse/time refusals.
- [ ] Calibrate the retained-set residual mapping with independent controls.
- [x] Complete the first candidate-specific digital controls and independent
  evaluation. The tighter bound failed its predeclared criterion (97/100,
  one-sided 95% lower limit 92.43%); steady-source and reference-contamination
  checks limit its scope. Physical calibration remains open.
- [x] Compare 21 practical fine/coarse policies on the same archived blocks,
  allowance and exposure. This retrospective comparison does not change the
  frozen candidate or establish physical superiority of either detector.
- [ ] Measure in-band coherence and full visibility/filter transfer.
- [ ] Freeze the resulting calibration and uncertainty method before confirmation.
- [ ] Run prospective confirmation with all support, drift and science gates.

The next executable development item is a bounded coherence prototype from the
existing partial-band, 0.2943-second voltage event, as documented in
`results/channel29_policy_comparison_2026-09-09/readiness/README.md` in the parent
workspace. Matched in-band data and complete cleaner provenance are still needed
for physical transfer. The metadata checker cannot substitute for them.
