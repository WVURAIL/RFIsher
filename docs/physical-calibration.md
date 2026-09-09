# Physical calibration and independent validation

The corrected September 8 archive release still has no accepted operational
policy. Additional local work is released separately under
`results/calibration_followup_2026-09-08` and
`results/calibration_next_2026-09-08`, with further work under
`results/calibration_progress_2026-09-09` in the parent workspace. Historical
results and response banks are unchanged. These checks live in
`rfisher_results.validation` so that evidence tooling does not invalidate
the banks' scientific-source identity.

## Channel 29 follow-up after the corrected reanalysis

The fresh September 9 reanalysis reproduced the corrected archive and added
fixed coarse-retention comparisons. A channel 29 candidate is now specified in
[channel29-followup.md](channel29-followup.md), with a new metadata-only cohort
checker and a development exclusion set expanded from 9,214 to 9,335 events.
The additional 121 events were already used in the completed campaign.

The candidate/design freeze is separate from the later physical-calibration
freeze and prospective confirmation. Its exact coarse threshold and provisional
planning rules confer no physical or operational acceptance. The study and
frozen protocol are in `../results/channel29_followup_2026-09-09/` in the parent
workspace. The first candidate-specific retained-set control study is complete
below. Physical residual calibration and matched in-band visibility transfer
remain open.

### Channel 29 retained-set controls: failed reduced-bound validation

`../results/channel29_residual_controls_2026-09-09/` preserves a separately
frozen study of the exact coarse candidate through the full 2,048-stream packed
detector. Seven full-frame CPU/GPU packing and coarse-power checks agree
exactly. The study uses 100 calibration blocks, 100 fresh evaluation blocks,
five fixed null/intermittent cases, and separate reference-contamination
controls. Its 38,791 prescribed frame identities, including seven audit frames,
are distinct from recorded development identities. The README, three-page PDF,
source snapshots and independent recount retain the complete scope and data.

The candidate cutoff caps each kept positive-excess shelf at `8.18028e-6`,
below the assigned floor `2.1551920577866108e-5`; every kept frame therefore
receives that same original assignment. The maximum of 100 joint calibration
errors fits an absolute retained-set upper candidate of
`6.057908361096407e-6`, targeting 97% content with 95.2447% calibration
confidence. Independent evaluation gives **97/100 joint successes** and a
**92.43%** one-sided 95% lower limit. The separately predeclared **95%
evaluation target is not demonstrated**. All three failures are supported
variable-amplitude cases; no case has insufficient support, and every case
retains at least 51 evaluation frames. The original floor covers 100/100
primary blocks. No bound refit, padding, sample extension or archive replacement
follows this result. Calibration confidence and finite evaluation answer
different questions; the latter does not establish true coverage below 95%.

Two additional scope checks prevent generalization. Pooling the steady -50 dB
evaluation population gives 1,716/3,200 retained frames (53.625%) with known
ATSC truth `1e-5`, above the fitted intermittent-case candidate even without
extra reference tones. These pooled populations are descriptive, not new
independently supported block tests. In the separate -35 dB stress control,
baseline references retain 0/128 frames; added reference tones retain 128/128
at the same ATSC truth `3.1622776601683794e-4`, 14.67 times the original floor.
Each ideal reference receives added projection power 0.1 times its expected
uncontaminated thermal power; actual packed-weight leakage and coherent cross
terms are recorded. Zero ATSC truth in the reference-only control excludes
the tones' own interference and does not certify an interference-free frame.

The original floor's primary-case coverage does not qualify a physical floor,
and the smaller candidate must not replace it. Physical calibration requires
an applicable duty-cycle/amplitude family, independent reference-quality and
thermal-baseline evidence, and matched in-band visibility/noise and filter
injections. A small target/reference ratio alone is insufficient. These are
nominal prequantization digital labels, not measured telescope residuals or a
new CHIME holdout; no physical calibration bundle or confirmation interval is
activated. The counterexamples do not establish their prevalence in CANFAR or
prove channel 29 recoverable or irrecoverable.

## In-band voltage development step

The [one-event coherence prototype](inband-coherence.md) now computes actual
complex cross-products for 32 fixed inputs in 15 adjacent in-band voltage
shards. Its 0.2943-second development record, exact byte snapshots, dual
sample-code diagnostics and independent recount advance the implementation.
The event remains excluded from independent validation. Gains, delays,
packet validity, full-allocation coverage and actual-cleaner response remain
open; no physical residual or forecast credit follows from this result.

## Local visibility evidence

The September 8 collaboration delivery contains two `HybridVisStream` stacks
and six `FitFormedBeamEW` products. The recorded source is
`fir.alliancecan.ca`, not CANFAR. All eight frequency maps have nominal edges
608.0078125–708.0078125 MHz, with zero overlap with the dissertation's
470–608 MHz DTV interval. Nominal channel edges do not measure a PFB response.
The [draco container definitions](https://github.com/radiocosmology/draco/blob/main/draco/core/containers.py)
describe the NS-beamformed visibility and fitted-source containers; this schema
reference alone does not identify the exact producer. The later history audit
below recovers the final task graph and recorded package revisions.

The paired all-days and p1 reductions cannot be compared as matched experiments:
the without-HyFoRes versions include LSD 2164, absent from their with-HyFoRes
counterparts. Their source positions also differ. Re-stack the same days before
interpreting a difference; intersecting labels cannot remove a day already
averaged into a stack. The p0 pair has the same 49 days, coordinate agreement
within a declared `1e-10` degree roundoff tolerance, and 107,724 common valid
cells out of 139,264. Its inverse-variance weights differ.

For p0, the equal-cell complex least-squares gain is approximately
`0.955293 - 0.0000925j`; difference energy is `0.045043` times the before-product
energy. These are descriptive changes in fitted source amplitudes on common
support, not DTV attenuation or injected science-signal response. Cells mix
sources, frequencies and baselines and are not independent repetitions.
No uncertainty or covariance estimate is inferred from the two weights.
The history audit additionally finds different upstream revisions:
`rev_03_lsd_00/apply_chisq_mask_sumthreshold_sep_pol` for nominal "without"
products and `rev_12/load_gain` for "with" products. Even p0 is therefore not
an isolated one-cleaner treatment comparison.

Run the reproducible preflight from this repository with `h5py` installed
alongside the usual RFIsher dependencies (`pip install h5py`):

```bash
PYTHONPATH=src python scripts/validate_collaboration_transfer.py \
  --input ../datasets/chime_collab --output /new/output/collaboration-transfer.json
```

The six small products are fully SHA256-verified. The two approximately 99 GB
stacks receive metadata inspection; their delivery checksums are recorded but
are not claimed to have been independently reverified by this run.
Output creation is exclusive to preserve prior evidence.

`propagate_linear_moments(A, mu, C)` implements `A mu` and `A C A^H` with
finite, Hermitian and positive-semidefinite checks. Signal, noise and coherent
contamination require distinct inputs. A fitted cleaner must be rerun with
known injected signals; a saved matrix alone does not measure the effect of
refitting. Physical calibration additionally needs in-band visibilities,
units, valid counts/exposure, pipeline order/configuration, and independent
controls. No foreground-filter credit is enabled by this tooling.

### Saved filter matrices

The second follow-up samples four predetermined 256-by-256 filter matrices
from the same out-of-band visibility stacks: p0/p1, each at XX/RA 0 degrees
and YY/RA 180 degrees, with the stored EW coordinate approximately 22.
Under the declared convention `y = A @ x`, 24.78–25.21% of matrix energy
is off diagonal. Unit-norm constant, frequency-ramp and eight-cycle ripple
inputs have output energies at most `1.60e-15`; central-bin impulses retain
0.764–0.794. The maximum energy gain over unit inputs is 1.032–1.121.
These four examples establish that one scalar cannot describe all responses
of the sampled matrices; they are not representative campaign statistics.

For the hypothetical input covariance `C = I`, `trace(A A^H)/256` is
0.533–0.553. This is a conditional calculation, not a measured noise model.
Only 198–209 bins have both positive weight and count, and some nonzero
matrix rows lack this support. The stored visibility vectors are preserved
without applying A again because their processing state is unknown. The
earlier application state and fitting history still need confirmation. The
new source trace establishes the matrix convention and final processing steps,
but does not establish a physical transfer measurement.

The evidence and copied inspector/verifier are in
`../results/calibration_next_2026-09-08/visibility/`. There are 321 saved-array
identity and numerical replay checks, not 321 independent experiments. To
repeat the bounded reads, copy both scripts to a fresh output directory:

```bash
python /new/output/inspect_saved_filters.py \
  --input ../datasets/chime_collab/vis_ns_stream_2019alt_2026-09-08 \
  --output /new/output
python /new/output/verify_saved_slices.py
```

Use the recorded NumPy/h5py runtime with BLAS/OpenMP threads set to one.
The whole approximately 99 GB source files were not rehashed. No DTV or
HyFoRes transfer credit follows from these fixed-matrix tests.

### Recovered producer history

The HDF5 `history/config` and `history/versions` attributes identify the final
stacking graph and package revisions: draco `945187ff50a4281213f900319b955dec4a8df3a9`
and ch_pipeline `8040f8da25eede840b37ea46a7df020a97498cc6`.
Pinned official source confirms `y=A@x`. The sidereal stacker averages optional
filter matrices with output-frequency-dependent count coefficients, alongside
visibilities; it does not apply those matrices at that stage. The subsequent
RA240–255 degree real/imaginary median subtraction changes visibilities and
validity weights but leaves the saved matrix unchanged. That matrix omits the
median operation and is not the complete response of the delivered product.

The original DAYENU task supports saving without applying. Its upstream
parameters and apply/save state remain unavailable locally; directory names
such as `no_filter` are not substituted for that missing evidence. The rev09
saved matrices also cannot be linked as the actual cleaner for the rev12 versus
rev03 beamformed comparison. Recover intermediate histories and run injections
through the actual composite pipeline before interpreting physical transfer.

The new `../results/calibration_progress_2026-09-09/visibility/` record preserves
decoded histories, source URLs/commits/hashes, a bounded upstream search and
82 metadata/source checks. No large numerical array payload was read and the
approximately 99 GB files were not rehashed.

## Digital repeatability experiment

`scripts/validate_synthetic_coverage.py` has separate `freeze`, `generate` and
`evaluate` stages. The plan fixes the original floor, three policies, four
injection levels, three new seeds and 60 disjoint 100-frame replicates per
case before generating data. Each replicate contains 25 on and 75 off frames
at the full 2048-stream geometry. The original floor is not refitted from
the new floor shards. Those 90 extra generated frames are unused.

The policies are keep-all, the original rank-62 loud-shelf half-allowance point
(`eta_q16=107166595`), and rank-62 95% empirical retention of the original null
pool (`eta_q16=69642`). The last is a training quantile, not a guaranteed null
retention rate. All policies and the floor are conditional on the original
digital waveform and detector calibration.

The endpoint is sufficient support and assigned kept-set mean at least the
known injected kept-set mean. Every unsupported replicate counts against the
unconditional success bound. Frame seeds must be disjoint from development
and all other fresh shards. Policies and shelf levels reuse off frames;
their outcomes must not be pooled as independent trials. Exact one-sided
binomial limits are reported per case and with Bonferroni adjustment across
the twelve predeclared cases. Even 60/60 successes give a marginal 95% lower
limit of about 95.13%, and a simultaneous limit of only about 91.27%.
Neither is physical coverage on telescope data, a population-mean confidence
interval, or assurance that a policy meets its science allowance.

The completed run has 60 supported successes in each case and no under-booking.
The smallest assigned/positive-truth ratio is 1.18751. The released plan binds
the original runner, preserved in `source-snapshot/validate_synthetic_coverage.py`.
That runner resolved the GPU interpreter to `/usr/bin/python3.12`; its actual
NumPy 2.4.2 and CuPy 14.0.1 runtime is recorded. Subsequent invocations preserve
a supplied virtual-environment interpreter path. Reproducing an older frozen
plan requires its original source identities, including the archived runner.

Additional descriptive checks distinguish bookkeeping from threshold performance:
11/60 new 100-frame loud-shelf batches exceed the original `0.0125` allowance
in injected kept-set mean, and 27/60 exceed it in assigned mean. The original
training cohort had 2,000 frames; this is a batch-scale diagnostic, not a claim
about a survey population mean. The empirical-null threshold masks 270/4,500
fresh null frames (6%). These checks were added after the predeclared coverage
test and do not replace its endpoint or justify refitting on those frames.

Example stages, using new output paths and an available CuPy GPU runtime:

```bash
PYTHONPATH=src python scripts/validate_synthetic_coverage.py freeze \
  --reference ../pilot-proxy/docs/evidence/mask_residual_frontier_2026-09-07 \
  --output /new/output/synthetic
PYTHONPATH=src:../pilot-proxy/src python scripts/validate_synthetic_coverage.py generate \
  --output /new/output/synthetic --generator-python /path/to/gpu/python
PYTHONPATH=src python scripts/validate_synthetic_coverage.py evaluate \
  --output /new/output/synthetic
```

Use an absolute `PYTHONPATH` for generation if the command changes repositories.
The frozen input hashes must still match at generation and evaluation. A failed
or interrupted generation requires explicit investigation; it is not silently
resumed or overwritten.

## Joint residual calibration: historical v1 experiment

The `validation.tolerance` implementation and
`scripts/calibrate_synthetic_residual.py` separate development, calibration
and evaluation. The completed evaluation has **59/60 joint successes** and
a one-sided 95% lower success bound of **92.34%**. It did not demonstrate
the predeclared 95% validation target. The frozen correction is
`-2.0337794442186432e-05`; the sole failed block under-books the -44 dB
keep-all and loud-half cases by `1.240933418404173e-07` in linear units.
Every case has sufficient support (minimum 65); the baseline covers all 60
blocks. No correction or sample-size change followed evaluation. The frozen plan is
`../results/calibration_next_2026-09-08/residual/plan.json`; the earlier
repeatability experiment remains unchanged.

The plan fixes 60 calibration blocks and 60 fresh evaluation blocks. Each
block has 75 off frames and 25 on frames at each of four injection levels;
three fixed policies act on those mixtures and on the off-only population.
Thus there are 15 dependent cases per block. Independent blocks use disjoint
frame seeds, also excluded from the earlier development cohorts. The waveform,
2048-stream geometry, original floor, policies, case family and producing
code are bound before calibration.

For block b, let `s_b = max_case(truth_kept_mean - original_claim_kept_mean)`.
A case with fewer than 30 retained frames gives its block an infinite score.
For n calibration blocks, choose the smallest rank k satisfying
`P[Binomial(n, 0.95) <= k-1] >= 0.95`; the k-th ordered score is q.
The calibrated rule is `max(0, original_claim + q)`. The correction is signed:
a negative q can reduce over-booking, but is determined only from calibration.
An insufficient sample or an infinite selected score refuses a finite bound.
At n=60 the chosen rank is 60, the maximum calibration score.

Under independent, identically distributed blocks from the frozen generator,
this is an upper tolerance limit targeting 95% joint future-block coverage
with at least 95% calibration confidence. Dependence among the 15 cases is
handled by their within-block maximum, rather than counting them as 15
independent repetitions. Fresh evaluation reports the joint all-cases-success
indicator and its exact one-sided 95% binomial lower limit; the predeclared
empirical criterion requires that limit to reach 0.95. Unsupported blocks
count as failures. Evaluation cannot tune q, select another case family or
extend a disappointing trial count.

This targets the realized kept-set means in a future block under the same
digital model. It is not a per-frame bound, a survey population-mean interval,
physical calibration or proof that a science allowance is satisfied. Physical
use still requires appropriate truth-bearing controls and justified block
independence. Existing preparation and support/drift gates remain in force.

The following stages reproduce the historical v1 protocol in a new output
location with its frozen runtime and source identities. Reusing these seeds
is reproduction, not new independent validation. Subsequent studies must
exclude this entire cohort before choosing fresh seeds.

```bash
PYTHONPATH=src python scripts/calibrate_synthetic_residual.py freeze \
  --prior-release ../results/calibration_followup_2026-09-08 \
  --generator-python /path/to/gpu/python --output /new/output/residual
PYTHONPATH=src python scripts/calibrate_synthetic_residual.py generate-calibration \
  --output /new/output/residual
PYTHONPATH=src python scripts/calibrate_synthetic_residual.py fit \
  --output /new/output/residual
PYTHONPATH=src python scripts/calibrate_synthetic_residual.py generate-evaluation \
  --output /new/output/residual
PYTHONPATH=src python scripts/calibrate_synthetic_residual.py evaluate \
  --output /new/output/residual
```

<!-- BEGIN RESIDUAL_V2 -->
## Joint residual calibration: separate v2 experiment

The new `calibration_progress_2026-09-09` study has **197/200 joint successes** and a **96.1690%** one-sided 95% lower limit. Its predeclared 95% evaluation target is **demonstrated**. There are 0 unsupported and 3 under-booked blocks; minimum retention is 64. The original assignment covers 200/200 blocks. All outcomes, including failures, are retained. The historical 59/60 result above is unchanged.

`scripts/calibrate_synthetic_residual_v2.py` uses 300 independent calibration blocks and 200 fresh evaluation blocks, excluding all 38,770 prior frame seeds and their effective 63-bit identities. Its 15 dependent cases, original floor, waveform and 2,048-stream geometry are frozen. There are 87,500 used draws and 750 unused floor draws. A separate independent recount verifies every raw shard, all case means, input identities, generation order and the exact confidence calculation.

The maximum calibration score targets 99% content with `1 - 0.99**300 = 0.950959105929` confidence; its signed correction is `-2.0436228161274601e-05`. The evaluation target is separately 95% at 95% confidence (at least 196/200 successes). Even 200/200 cannot independently establish 99% content at that confidence. This conditional digital result does not qualify a physical floor or an archive operating policy. The release's `residual/README.md`, frozen plan and independent recount give the complete commands, counts and retained limitations.

<!-- END RESIDUAL_V2 -->

## Regulatory evidence for transmitter history

ISED, CRTC and FCC records provide an independent route without requiring
CANFAR access. `validation.regulatory` and `scripts/build_regulatory_evidence.py`
extract administrative evidence into separate sidecars; they do not promote
licence status to physical on/off labels or alter the dtv-census candidate
selection. The dated result in
`../results/calibration_next_2026-09-08/regulatory/` retains 544 FCC facilities
and 20,205 licence versions, plus 268 BC/Alberta UHF ISED rows. All 113 ISED
operational/auxiliary rows have joined date records. Historical renames,
deleted facilities and unresolved predecessor references still need review.

[CRTC Decision 2020-391](https://crtc.gc.ca/eng/archive/2020/2020-391.htm),
issued December 4, 2020, gives a concrete local lead: moving CHBC services
onto CHKL multiplexes in Kelowna, Penticton and Vernon. The corresponding
former-to-host physical channels are 27 to 24, 32 to 30 and 20 to 22.
The September 2 ISED export gives host certificate-effective dates of
October 7, 2021, while original on-air dates remain in 2013. Neither date
establishes the multiplex cutover. The old CHBC rows are now allotments;
this is not evidence that those allocations became RF quiet on that day.
The decision's application, 2019-1119-9, has now been retrieved completely;
it contains pre-approval proposals rather than the actual cutover record.

The complete original CRTC application bundles 2018-0936-0 and 2019-1119-9
supply a separate operational lead: Corus reports that 44 rebroadcast
transmitters shut down in October 2018, before the June 13, 2019 licence-deletion
order. Preserve the entire uncertain month; exact days, subsequent resumptions
and continuous off-state intervals are not established. The 44 identities are
listed in the original Appendix A. Historical maps identify CHAN-DT-6/channel 23
and CITM-DT/channel 21 as archive leads, subject to intervening-amendment checks.
The six CHBC/CHKL multiplex actors are not in this 44-transmitter cohort.
K20EH-D's exact suspension notification is identified, but its May 16, 2024
receipt date does not supply the still-unavailable actual cessation date.
The original documents, provenance/date distinctions and checks are in
`../results/calibration_progress_2026-09-09/regulatory/`.

Preserve fixed-width callsign/banner identities, channel/site scope, original
source, publication/filing date, effective date, timezone and uncertainty.
The [ISED field manual](https://ised-isde.canada.ca/site/spectrum-management-system/sites/default/files/attachments/2022/Broadcast_Database_Extract_Manual.pdf)
distinguishes on-air, certificate and approval/expiry dates. An expired
licence field, authorization, cancellation or missing snapshot row alone
cannot define an RF-off interval. If two snapshots differ without an explicit
effective date, the interval remains an uncertain administrative change.
A day-only date cannot supply an exact UTC switching instant.

Use reviewed operational reports to create physical state intervals. Keep
administrative hypotheses separate, and never choose their dates by the
receiver result that they are meant to independently explain. One station's
cessation does not establish an allocation-wide null: every plausible
cochannel transmitter and shared carrier remains part of the scope review.
The regulatory result README gives the complete offline extraction command,
source hashes and retained uncertainties. No verified RF-off interval has
been claimed by that extraction.

## Era hindsight and causal validation

`scripts/audit_era_hindsight.py` replays the fixed archived rule using only
recorded months through each cutoff. It reproduces all final source era spans,
states, opening evidence and populated-month membership. The 1,722 prefixes
across 23 channels contain 126 prior channel-month assignment revisions,
including 78 revisions of previously definite proxy-high/proxy-low assignments.
Those 78 include 47 state changes and 31 changes to era start/evidence only.
Ordinary extension of an era end is excluded from the count.

Channel 36's boundary assigned to August 2021 first appears when May 2023
monthly data are included, a 21-month lag. This is a lag in recorded monthly
prefixes, not a measured real-time detection latency. Month-local normalized
coarse statistics, nominal-window fine peaks and input maps are replay inputs;
fitted archive anchors/residuals are not. Raw aggregates, ingestion times and
the retrospectively developed rule are not independently rederived. These
correlated histories therefore diagnose hindsight, without providing an
untouched validation or justifying weaker support/drift gates.

```bash
PYTHONPATH=src python scripts/audit_era_hindsight.py \
  --results-dir ../results/archive_v5_2026-09-08_corrected \
  --out /new/output/era-prefix-audit
```

Keep retrospective segmentation as the historical view. For a causal use,
apply the following protocol. Its offline ledger is now implemented;
it is not an online state machine or an accepted operating policy:

1. Predetermine chronological development, calibration and evaluation periods,
   including calendar span, support requirements and acquisition grouping.
   Establish which completed monthly aggregates and external records were
   actually available at each cutoff.
2. Discover the candidate era and fix the claim/policy family on development
   data. Use a separate calibration period for the declared calibration rule.
   Freeze the accepted policy, calibration and exact era assignment before
   evaluation; store hashes and refusal reasons. Do not move the evaluation
   start after inspecting later data.
3. Freeze the change-monitor rule with that bundle. A later spectral or
   input-map change can stop future operation and initiate a new calibration
   version. Preserve every past evaluation sample and decision; a later era
   fit must not relabel or discard them.
4. Record inferred onset, observed confirmation, data availability and policy
   activation separately. Report uncertain transitions and detection delays.
   Regulatory effective dates can propose independent candidate changes, but
   their publication/availability dates determine when they could inform an
   operational decision.
5. Use rolling-origin historical replays to develop this workflow. Since the
   existing archive and procedure have been inspected, successful historical
   replays remain retrospective. Validate the frozen version on a genuinely
   new acquisition cohort before claiming prospective performance.

### Implemented candidate ledger

`validation.causal_eras` now supplies `freeze_candidate`, `append_monitor`,
`record_evaluation` and `verify_ledger`. It preserves frozen and as-known
assignments, stops on contradictory/ambiguous/stale/unsupported evidence or
map changes, latches that stop, and requires a new calibration identity for a
successor. Ancestor acquisition attempts remain excluded. Qualification and
actual policy activation are external: the helper emits candidates only.

`python scripts/replay_causal_eras.py --results-dir <corrected-results> \
  --cutoff-month 2021-04 --out /new/output/era` reproduces the demonstration.
All 23 final ledgers rebuild exactly from 536 frozen months and 1,186 later
updates. Eight candidates halt initially and 21 by the last observation;
channels 29/34 have no triggered halt in this fixture, not accepted policies.
The demonstration assumes next-month data availability, uses an explicitly
unqualified calibration fixture, and invents no acquisition evaluations.
Forty era tests pass. Actual ingestion times, independent future cohorts,
physical qualification and a live watchdog remain necessary. Source snapshots,
frozen/final ledgers and checks are in the new release's `era/` directory.

## External states and future acquisitions

`null_states.StateRecord` requires a source digest and timezone-aware validity
interval. `join_null_state` requires full off-state coverage for every declared
candidate, a reviewed independence artifact and a reviewed candidate scope.
Unknown, conflicting, unreviewed and partial coverage stays unknown. One
transmitter's sign-off cannot prove an allocation-wide null. Hashes authenticate
the supplied evidence; they cannot establish its correctness or independence.

`holdout.audit_future_cohort` groups frequency shards by acquisition, checks
development overlap and requires trustworthy timestamps after an accepted
policy/calibration freeze. Passing this check does not establish blindness or
authorize deployment. The already-inspected archive remains retrospective.

```bash
PYTHONPATH=src python scripts/prepare_validation_evidence.py \
  --inventory ../archive_inputs/chime-pilots-v5/inventory.source.jsonl \
  --inventory ../archive_inputs/chime-pilots-v5/inventory.jsonl \
  --output /new/output/physical-evidence-plan.json
```

The local plan conservatively excludes all 9,214 acquisitions in those
development inventories. Its policy freeze remains unset and its candidate
cohort empty. Reviewed physical state intervals, matched in-band transfer
measurements and physical coverage controls remain pending. Administrative
records and digital measurements are retained with their own evidence types.
Once independent inputs arrive, run these checks, measure the physical
quantities, obtain an accepted policy through the existing preparation gates,
and freeze that complete bundle before collecting the future cohort.
