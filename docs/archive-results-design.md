# Archive results: design

How the dissertation's archive-dependent stubs are filled from the
September 2026 CANFAR campaign products (`pilotproxy_per_pilot_product_v5`,
23 channels, `~/rail/products/chime_pilots_rebuild_20260829/products/_per_pilot/`).
Drafted 2026-09-07 from a reading of the four repositories and the data.
Companion to the dissertation's `RESULTS_PLAN.md` and `STUBS.md`.

The results layer that does this is the package `rfisher_results.archive`.
It lives beside `rfisher` (never inside it: the shipped banks pin a digest
of `src/rfisher/`) and follows the conventions of the rest of
`rfisher_results`: one module per source or analysis, pure loaders separate
from renderers, CSV writers with `repr()` floats and blank NaNs, no
console-script entry, tests per module.

## 1. What the products make exact

Every v5 product retains the exact `uint64` coarse powers per frame
(`p_target_u64`, `p_ref_lower_u64`, `p_ref_upper_u64`, `p_ref_sum_u64`) and
the exact fine-power terms (`fine_power_u64`, shape `(N, 3, 256)`: target,
lower reference, upper reference per padded fine bin). Two consequences
shape everything below.

- The coarse decision at any multiplier is the integer comparison
  `p_target * reference_norm_sum_sq > eta * target_norm_sq * p_ref_sum`;
  `rfisher.pilotproxy.ResidualProductView.rejected_at_multiplier` already
  does it. The stored `reject_mask` is that comparison at `eta = 1` (the
  survey flag, `F > mu_0`), a mechanical bootstrap default, never a policy.
- The fine statistic `T[f] = 2 S_0[f] / (S_1[f] + S_2[f])` is the deployed
  fixed-point statistic, formed from the retained terms; ranks and Q16
  multipliers are exact rationals (`rfisher.residual_scores.bundle`).

Two things the products do not carry: `mu_0` (it is
`2 * target_norm_sq / reference_norm_sum_sq`, derived, never read) and a
shelf level on kept frames (`estimated_data_shelf_snr_db` is finite exactly
where the normalized excess `Q - 1` is positive, i.e. on rejected frames).
The second is a property of the estimator, not a defect: the kept-frame
floor of a channel is therefore a statement about a null population
(section 6), not a minimum over kept frames.

## 2. Coordinates

Every frequency in tables and figures is the RF offset from the channel's
nominal (synthesized) pilot, positive towards higher RF. This is the
convention of `census_psd.csv` and of the chapter 3 census figure.

The fine axis does not measure that quantity directly. The same K-tap weight
vector is applied to every window with no phase continuation, so the
window-axis (fine) spectrum measures the carrier frequency modulo
`f_s / K` about the nearest coarse-grid frequency. The fine bin of an
exactly-nominal pilot is therefore a deterministic channel constant, the
grid residual, which `pilot_proxy.detector_geometry.predicted_pilot_fine_bin`
computes and every product records as the centre of `fine_designated_bins`
(e.g. channel 36: bin 62, +739.7 Hz in the fine-array direction). A measured
fine anchor is converted to an RF offset from nominal as

    rf_offset_hz = -(fine_offset_hz - grid_residual_hz)        (sense = -1)

with the fine offset unwrapped about the grid residual. Two consequences:

- The fine-span edge at `+-f_s / 2K` is an aliasing boundary about the grid
  origin, not a distance from the tone. Nothing is attenuated or clipped
  there. The superseded prose that reads fine-axis positions as distances
  from the synthesized tone (channel 32 "at 90% of the span edge", "outside
  the K = 256 span") is a coordinate confusion and is corrected by the
  tables, not reproduced.
- `E_K(c)` of chapter 4 is defined "around the nominal target"; centred on
  the nominal pilot the three spans are nested and `E_K` is non-increasing
  in `K`, as the text asserts. Centred on `K`-specific grid origins it would
  not be. The containment analysis therefore works in the RF coordinate on
  the per-frame 23.84 Hz spectra, where all three spans are visible.

Per-frame spectrum axis: `psd_frame_db_i16` bins are in numpy FFT order,
bin 0 the coarse-channel centre, width `f_s / 16384 = 23.84185791 Hz`,
raw axis inverted relative to RF (all 23 products carry `sense = -1`), so
an RF offset `df` from the channel centre sits at receiver bin
`round(-df / 23.84186) mod 16384`; the nominal pilot sits at the real-valued
receiver bin `p0 = -(pilot_frequency_hz - chime_frequency_hz) / 23.84186`.
Decode: `psd = psd_db_reference[:, None] * 10 ** (code / 1000)`, NaN where
`code == psd_db_invalid_code` (-32768). The array is up to 1.3 GB per
channel and is processed in row chunks, one channel at a time.

## 3. Definitions carried over from the text (verbatim where it matters)

Rank and multiplier (ch06 §detection:rule). Sort the `|B|` bulk values of a
frame ascending; `T_(rho)` is the rho-th, `q_rho = rho / (|B| + 1)`.
Designated set `D = {(f_a + k) mod 256 : |k| <= 2}`. Bulk `B`: alternate
(independent) bins, excluding `D`, census-marked persistent features and
zero-denominator bins; an even-parity anchor leaves 125 bulk bins, an odd
one 126. Reject `H_0` iff `max_{f in D} T[f] > eta T_(rho)`. `eta_q16` is an
integer; the grid of candidates is the Q16 integer 1 plus every unique
observed multiplier at which a frame's exact decision changes; floating
`eta = eta_q16 / 2^16` is display only. `Z_i(rho) = max_D T_i / T_i,(rho)`.

Histogram family, masked fraction, cost, plateau, selection (ch06 §80-127,
ch09 §545-574, ch08 §344-351): `f(rho, eta) = 1 - K_rho(eta) / N_rho`;
`r_sys` and `r_var` are kept-frame means of per-frame residuals; a
candidate with fewer than 30 kept frames is not evaluated;
`C(rho, eta) = (1 + r_var) / (1 - f)` over candidates with
`r_sys <= r_tol`; `P = {C <= 1.02 C_min}`; the selected pair is the member
of `P` with lexicographically smallest `(r_sys, f, rho, eta)`. Sensitivity
values: 30/50/100 frames, plateau 1.00/1.01/1.02/1.05. "Plateau width" is
not defined by the text; this design reports it as the number of `P`
members at `rho*` and the `eta` range they span, and says so.

Null model (ch05 §141-156): fine per-bin `T ~ F(4096, 8192)`, mean 1.00024,
standard deviation 2.71%; coarse `F ~ F(524288, 1048576)`, mean 1.000002,
standard deviation 0.239%. Width factor = measured width over the i.i.d.
width, raw (standard deviation) and robust core (left-side scale about the
median with the `NULL_SCALE_PROBES` convention). Tail fraction beyond three
core widths. Exchangeability: on quiet frames a null bin outside the bulk,
tested against the rank `rho` of the bulk, exceeds it at rate
`(|B| + 1 - rho) / (|B| + 1)`; the bins tested are the designated window
(within one frame, exactly `|B| - rho` of the bulk's own bins exceed the
rank of the others whatever their distribution, so a bulk bin tested against
the remaining bulk is a tautology).

Null sources in order of strength (ch08 §253-263): verified transmitter-off
era; independently identified quiet subset; control or reference-bin
surrogate; synthetic or model-only; unavailable (refuse). A bulk-read null
declares its mixture assumption beside the number.

Anchor (ch08 eq:calibration:anchor):
`f_a = argmax_f [median(T_f^on) - median(T_f^quiet)]` over coarse-detected
(`reject_mask = 1`) and coarse-quiet (`valid`, `reject_mask = 0`) frames of
the current era; plain-median fallback where no defensible quiet cohort
exists, labelled as such. The averaged-spectrum dominant lobe is a
different estimand, reported beside it.

Era procedure (ch08 §78-117), policy values with sensitivity values:
month populated with >= 30 valid frames from >= 5 acquisitions on >= 3
days (sensitivity 3/5/10 acquisitions); monthly median of per-frame
`10 log10(F / mu_0)`; proxy-high >= 1 dB, proxy-low <= 0.5 dB, ambiguous
between (sensitivity 0.5/1/2 dB); station change = monthly fine-peak
location shift >= 3 fine bins (36 Hz) within `f_pred +- 30` bins;
instrument change = change of recorded software tag or input map;
persistence 2 consecutive populated months; ambiguous months inherit
agreeing populated neighbours, otherwise open a transition; boundary
placed between the last month of the old state and the first of the new,
with an unpopulated gap's span as its uncertainty; no proxy-low month means
eras bounded only by station/instrument changes and a null declared as
mixture or refused; "sign-on/sign-off" only where a station record confirms,
otherwise "spectral-state transition"; the latest archive-observed stable
era is the "current era", flagged stale-latest when it ends before the
snapshot. Inputs exclude anything era-calibrated.

Straddle loss: `-10 log10 |D_K(delta)|^2` with `D_K` the Dirichlet kernel of
ch04 eq:dirichlet and `delta` the RF offset of the measured pilot from
nominal in coarse bins (`|offset| K / f_s`); `|D_K(1/2)|^2 = -3.92 dB` at a
half bin. Fine-grid scalloping is bounded near 0.9 dB by the factor-2
padding and reported separately if at all.

`K*` (ch04 eq:param:kstar): `max{K = 2^j : E_K(c) >= E_min for every
supported channel}`, `E_min = 0.9` with 0.8 and 0.95 as sensitivity values;
a channel failing at every `K` is a sentinel and does not drag the choice;
the binding channel is named. Note the detector supports `K in {64, 128}`
only (bit growth); `K = 256` is a containment comparison, not a runnable
configuration.

## 4. Pipeline per channel

Every step reads the product lazily (`numpy.load` without copying) and
records which frames it used and why.

1. **Frames.** `valid` frames, further restricted by pilot-proxy's frame
   health gate (`pilotproxy_archive_frame_health_gate_v1`) when
   `pilot_proxy.archive_health` is importable; the ledger records which
   gate applied and how many frames it removed (192 of 770,478 on v5).
2. **Eras** (`archive.eras`). The section 8.1 procedure as versioned
   configuration; output one row per era per channel (start, end, state,
   transition evidence class, boundary uncertainty, stale-latest, units,
   frames, months with frames / months spanned) and the current-era frame
   mask. The ppcal segmentation (2 dB step, rank z 4, 6 months) is retained
   only as a sensitivity comparison. Indeterminate cases (long ambiguous
   runs on channels whose null sits 0.4-1 dB above `mu_0`) are reported as
   such, not resolved by hand.
3. **Blocks** (`archive.blocks`). The current era is split into a
   calibration block and an evaluation block on whole acquisitions in
   chronological order, at the acquisition that balances frame counts, so
   calibration precedes evaluation the way offline calibration precedes
   online use. Each block must satisfy the section 8.1 month minimums on
   its own or the selector reports insufficient support. Uncertainties are
   block bootstraps that resample whole acquisitions with a recorded seed;
   frames are never resampled individually.
4. **Anchors and containment** (`archive.anchors`, `archive.psd`). The
   on-minus-quiet anchor on the calibration block with its acquisition
   bootstrap; the argmax is taken over all 256 bins and also within the
   `f_pred +- 30` acquisition window, and a disagreement is reported as an
   alias of an out-of-span feature (channel 33's co-channel carrier at
   -3.7 kHz). From the per-frame spectra: era-mean spectrum, dominant lobe,
   per-frame peak-offset distribution, `E_K(c)` for `K in {64, 128, 256}`,
   straddle loss, margin to the span edge, reference-region contamination,
   the `K*` rule and the disposition. The previous era's anchor where one
   exists.
5. **Null calibration** (`archive.nulls`). On the calibration block: the
   bulk `B` from the measured anchor, the fine bulk centre and widths (raw
   and robust core) against the i.i.d. widths, the coarse centre `F / mu_0`
   against 1 with its width factor, tail fraction beyond three core widths,
   the null source label and mixture declaration, the floor (off-era 90th
   percentile shelf where a verified off era exists; otherwise the stated
   sigma-implied substitute, labelled), and on the evaluation block the
   exchangeability rate at the selected rank.
6. **Selection** (`archive.selection`). Calibration block ->
   `build_residual_score_bundle(product, selected_frames, anchor_bin,
   designated_half_width=2, bulk_mask)` -> per-frame systematic residuals
   (shelf-or-floor linear: `10^(shelf/10)` on frames with a finite shelf,
   the channel floor otherwise) -> `prepare_threshold_family` ->
   `select_prepared_threshold(allow_screening=True)`. Then the evaluation
   block replayed at the selected `(rho*, eta*_q16)`: masked fraction,
   retained residual, `R = r_sys / r_tol`, and the empirical false-alarm
   rate on channels with an off era. `r_tol` per channel is the operable
   dilation tier `min(r_perp, r_par)` over the channel's overlapping bins
   at `zeta = 1`, from the frozen forecast-completion ledgers (the logic of
   `scripts/channel_tolerances.py`), with the `f sigma_8` tier beside it.
7. **Screening class** (one function, registered): off-era (current era is
   proxy-low after a sign-off or the carrier is absent); recovery candidate
   (selected point feasible on the dilation tier with the named validations
   in place); measurement-bound on floor (infeasible or bound with a stated
   rather than measured floor); measurement-bound on `tau_c` (refused
   correlation time, chain at the sidereal cap); occupancy-wall excision
   candidate (feasible only with masked fraction near unity, or no
   admissible point on a persistently occupied channel).
8. **Ledger.** One machine-readable row per channel (JSON, plus CSV views)
   carrying every column above with its status, from which the chapter 8,
   9 and 11 tables, the appendix C counts and the `numbers.json` for the
   `\rerun{}` markers are generated. The prose never quotes a number the
   ledger does not carry.

## 5. Outputs and where they go

A dated results tree beside the frozen one, never inside it:
`~/rail/results/archive_v5_<YYYY-MM-DD>/` with `ledger/`, `tables/`
(booktabs `tabular` bodies as `.tex` fragments, and the CSVs behind them),
`figures/`, `numbers/` and a `SHA256SUMS`. The dissertation vendors PDFs
and `.tex` fragments with a manifest row naming this repository and the
producing commit; the results tree is backed up with the others.

## 6. Decisions this design takes provisionally (register them or change them)

These are choices the text leaves open. Each is recorded in the ledger with
its status; changing one is a new run.

- Stability screen limits, all `open` in the register: minimum retained
  frames per half 30, maximum cost ratio 1.05, maximum systematic ratio
  1.10 (the middle of each registered sensitivity list). Status
  provisional.
- The health gate is applied (frames the gate excludes are not selected).
- Block split: chronological, whole acquisitions, balanced frame counts.
  Bootstrap: 1000 replicates, seed 20260907, 16/84 and 2.5/97.5
  percentiles, minimum 8 blocks per half.
- Anchor: argmax over all bins is the estimator of record (the text's);
  the windowed argmax and the PSD position of the recovered line are
  reported beside it and a disagreement sets the sentinel. Minimum cohort
  30 frames per side; fallback to the plain median below that.
- Pilot-associated energy for `E_K`: excess over a robust baseline of the
  era-mean spectrum within `+-15 kHz` of nominal, excluding `+-60 Hz`
  around the instrumental channel-centre line; hard windows on the PSD
  grid with half-bin edges interpolated. The neighbourhood `W = +-15 kHz`
  is the census window and is a declared choice.
- Disposition: supported when an in-span lobe is recovered, it is the
  dominant excess within `W` outside the centre line, `E_128 >= E_min` and
  reference contamination is below 5% (the self-leakage bound); supported
  with sentinel when a lobe is recovered but a stronger out-of-span feature
  exists, `E_128 < E_min`, contamination is at or above 5%, or the fine
  anchor aliases an out-of-span feature; unsupported when no in-span lobe
  is recoverable in the current era.
- Instrument change: a change of `unit_input_map_sha256`; the software tag
  changes 56-59 times per channel and is reported as a sensitivity only.
- The floor on channels without a verified off era is the sigma-implied
  substitute and is labelled `stated`; no reference-surrogate floor is
  introduced without a registered method.
- Null-scale probes. The register's `floor.null_scale_probes` (32%, 5%,
  0.3% with deviates 1, 1.96, 2.97) are the one-sided percentiles of the
  *kept half* about `mu_0`, which is how `rfisher.residual.null_scale` applies
  them (the kept frames are the null's lower half, so their 32nd percentile
  is the null's 16th). Simulated on an ideal null they recover the width to
  1%; applied to a full null about its median they would return 0.84 of it,
  which is what an earlier note of this design wrongly reported as a bug.
  `archive.nulls` follows the register for the sigma-implied floor
  (`kept_half_null`: frames with `Q <= 1` on the calibration block) and
  describes the whole era's bulk with the full-null percentiles (15.87 / 2.5 /
  0.15) beside it. On a channel whose carrier is present in most frames the
  bulk's median lies above `mu_0` and its left side is the detections' lower
  tail (channel 33: bulk width factor 25 against a kept-half factor near 1),
  so the floor is read from the kept half.
- Off population. The frames of the recorded off epoch inside the
  procedure's proxy-low eras are the null population, and the floor is their
  90th-percentile shelf (`measured`), as chapter 8 says; whether that
  population also reads as a null (coarse centre within 2% of `mu_0`, core
  width factor at most 5: `nulls.null_like`) is reported beside it
  (`off_null_like`, `off_check`). Channels 20 and 27 fail the check (centres
  1.11 and 1.03, width factors 19 and 10: a carrier persists after the
  recorded sign-off) and keep their measured floors (-26.9 and -25.4 dB, the
  conservative numbers) and their off-era class; the tables say so.
- Which stated floor. On channels without an off era the sigma-implied floor
  is read from the kept half about `mu_0` (the register's convention) only
  when the calibration block's bulk centre lies within 2% of `mu_0` and the
  three probes agree to a factor 3 (`nulls.KEPT_SPREAD_LIMIT`); otherwise
  from the bulk's left-side scale about its median (the chapter 8 mixture
  read), labelled `bulk left side (not H0)`. Channel 33's calibration block
  (bulk median 1.0715, 97% rejected) is the case: its 2.7% "kept" frames are
  the carrier-on distribution's lower tail. `floor_basis` and both values are
  in every row. The superseded feasibility of channel 33 rested on the
  mu_0-implied floor (-44.7 dB, from `|mu_0 - 1|`) and a blanket 10 dB
  fine-stage credit, neither of which this analysis uses.
- The residual convention is floor-bounded: a frame with a shelf estimate
  carries `max(10^(shelf/10), floor)`, a frame without one the floor. The
  residual is a functional of the coarse statistic alone, so the coarse rule
  is the lower envelope of the (f, r_sys) plane by construction; the coarse
  frontier (`channels/chNN/coarse_frontier.csv`, `selection.coarse_min_R`)
  is written beside the fine surface and the chapter 9 sentence claiming the
  fine selection measures a competitive intermediate point is the author's
  to reword.
- The chain is evaluated on the current era (the previous on era for an
  off-era channel) by `chain.residual_chain_on_frames` (a temporary copy of
  the product with `valid` cleared outside the era, the unchanged
  `rfisher.residual` functions), as chapter 9 states; the archive-wide chain
  is recorded beside it (`chain_archive`). On channel 33 the era-restricted
  correlation time is refused where the archive-wide one was bounded.
- Diagnostic replay. Where no point is feasible, the least-residual point of
  the calibration surface is replayed on the evaluation block as a declared
  diagnostic (`selection.diagnostic_*`), never as a selection, so a verified
  off era reports a false-alarm rate at a stated point.
- Anchors. The table's anchor is the current era's (eq 8.1, with its
  bootstrap); the selector's is the calibration block's (held out from the
  evaluation block); both are recorded (`anchor`, `anchor_calibration`). The
  on-minus-quiet estimator is used only where the mask's coarse bulk sits at
  `mu_0` (`quiet_cohort_is_null`), else the plain median of the on cohort. An
  out-of-window anchor is an alias only when it folds onto the out-of-span
  feature by one coarse bin. A suspect anchor (disagreeing with the in-span
  lobe by more than the designated half-width, folding, or with bootstrap
  mode mass below 0.5) excludes the nominal window from the fine null's bulk
  and hands the selector the spectrum's in-span lobe bin, labelled.
- Frames without a recorded time are excluded from every block (one block
  definition for blocks, anchors, nulls and selection);
  `blocks.frames_without_time_excluded` counts them.
- Eras carry the peak location's least-squares drift (bins/month) and range
  per era: on channels 15, 17, 31 and 35 the "station change" boundaries
  are a slow monotonic drift of 0.2-0.6 bins/month sliced by the running
  median, and the within-era range exceeds the designated half-width; the
  rule is the text's and is kept, the columns let the author judge it. An
  instrument map entering in the campaign's last month is reported as
  unconfirmed (`unconfirmed_instrument_change_last_month`).
- Provenance: the producer's commit, dirty flag and a digest of this
  package's sources are read before the run starts and written to
  `run.json`; a commit that moves during the run is flagged.
- Off-era channels read the anchor of record and the containment from the
  previous (on) era, labelled as such; the selection and the null are on the
  off era itself (false-alarm basis).
- The within-era drift screen (`rfisher.preparation`) refuses every archive
  channel (sparse small-eta candidates, or halves below six months / 270
  days). The selector still runs on the prepared histograms and the point is
  reported as `diagnostic` with the refusal beside it; nothing is labelled
  `screening` or `operational`.
- Spectrum axis. The per-frame spectra are read on the receiver's circular
  axis centred on the pilot (`psd.centred_offset_hz`), as the detector's
  K-tap FFT reads them: on channels 21 and 32 the pilot is within `W` of a
  coarse-channel edge and the far side of the window is aliased content,
  recorded by `edge_distance_hz`, `window_aliased_hz` and `ref_aliased_K`.
- Anchor against lobe. The fine anchor is compared with the spectrum's
  in-span lobe (`anchor_lobe_offset_bins`); a difference beyond the designated
  half-width sets the sentinel with its own reason.

## 7. Decisions that stay with the author

- Whether "masked fraction at the bootstrap rule" appears in the chapter 9
  tables at all, or only the survey-flag rate as an occupancy indicator
  (STUBS.md contradicts itself; the author's stated intent is occupancy).
- The coordinate correction of section 2 changes the meaning, not just the
  value, of the ch04, ch06 and ch08 sentences about anchors near the span
  edge; the tables will carry both coordinates and the prose needs the
  author.
- Whether the section 8.1 thresholds (1 dB / 0.5 dB) stand given the
  ambiguous-month fractions the v5 data show on shelf-lifted channels.
- Confirmation of the provisional stability limits above.

## 8. Build order

1. `archive.products`, `archive.blocks` (this commit).
2. `archive.eras`, `archive.psd`, `archive.anchors`, each with tests and a
   validation run over the 23 products.
3. `archive.nulls`, `archive.tolerances`.
4. `archive.selection`, `archive.screening`, `archive.ledger`.
5. Table fragments, figures, `numbers.json`, the marker matcher; then the
   dissertation edits, the number-gate re-pinning and the vendoring.

## 9. The report: stub tables from the ledger

`rfisher_results.archive.report` renders one fragment per stub table from the
ledger alone, with a `numbers.json` beside it and an `export_manifest.json`
(schema `rfisher-archive-report`, producing commit, run identity, artifact
digests) for the dissertation's importer. Cells are plain `tabular` rows; the
chapter keeps the `table` environment, caption and label. Every builder is a
pure function of `report.Run`; the columns below name the ledger keys
(`section.key`) each cell reads.

| fragment | label | columns (ledger keys) |
|---|---|---|
| `calibration_eras` | tab:calibration:eras | era.current_first_month .. current_last_month, current_state, current_boundary_uncertainty_months, current_evidence with the current era's `record_agreement` and `unmatched_station_records`, stale_latest (stale_lag_months), earlier eras (tables/eras.csv spans), current_frames, coverage (eras.csv `coverage` of the current era), current_peak_drift_bins_per_month and current_peak_range_bins (marked where the range exceeds `anchors.DESIGNATED_HALF_WIDTH`), unconfirmed_instrument_change_last_month |
| `calibration_anchors` | tab:calibration:anchors | anchor.anchor_bin, anchor_rf_offset_hz, method, boot_rf_hz_q16/q84, source; containment.dominant_refined_offset_hz, dominant_db, in_span_refined_offset_hz, anchor_lobe_offset_bins; peak_abs_median/p90/p99_hz; anchor_previous.anchor_rf_offset_hz, shift_from_previous_bins |
| `calibration_containment` | fig:calibration:containment (compact table) | containment.frames_in_span_K, e_K, straddle_loss_db_K, margin_hz_K, ref_contamination_K (+ ref_aliased_K), disposition, reasons; K* rows from tables/kstar.csv |
| `calibration_nulls` | tab:calibration:nulls | null.era_frames, bulk_size, null_source, mixture_declared, coarse_centre, coarse_core_sigma, coarse_raw/core_width_factor, fine_raw/core_width_factor, coarse_tail_fraction, kept_width_factor, exch_rho, exch_measured, exch_predicted, floor_db, floor_evidence, floor_population; the plate label |
| `blocked_evaluation` | ch05 blocked-evaluation stub | blocks.calibration/evaluation months and frames, null.coarse_centre and core width against null_evaluation.*, the drift (difference), blocks.*_finite_estimate_rate, selection.masked_fraction_evaluation_q16/q84 |
| `held_out_summary` | ch06 held-out stub | selection.rho, eta, masked_fraction_calibration, masked_fraction_evaluation (+q16/q84), r_sys_evaluation (+q16/q84), R_evaluation, false_alarm_rate, claim_status |
| `tolerance_eta` | tab:tolerance:eta | selection.era, bulk_size, rho, q_rho, eta, eta_q16, masked_fraction_calibration, floor_db (evidence, population), r_sys_calibration, r_tol, R_calibration, cost, plateau_members/eta_low/eta_high, status + claim_status + refusal; chain.tau_quality marks bounds |
| `tolerance_channels` | tab:tolerance:channels | geometry.allocation_low/high_mhz, tolerance.z_low/z_high, geometry.pilot_hz (monitored bin), era span, screening.survey_flag_rate_era, selection.masked_fraction_evaluation, chain.on_shelf_db, null.coarse_frames, null.floor_db, chain.intraday_share, ground_filter_db, tau_quality/tau_c_minutes, selection.r_sys_unmasked_evaluation (r_keep), r_sys_evaluation (r_proxy), R_evaluation, r_sys_evaluation / tolerance.r_tol_fs8 (unpriced where fs8_status says so), screening.screening_class |
| `conclusions_matrix` | tab:conclusions:matrix | counts of screening.screening_class; handover policy derived from the class (excision candidates: excised interior + monitoring tap; others kept-and-masked); band-level masked fraction (frame-weighted over kept channels) and the time-cost factor 1/(1-f) |
| `archive_atlas_counts` | tab:archive:atlas-counts | product.n_frames, n_valid, health_excluded (health_reasons), era.current_frames, selection.kept_evaluation + calibration kept (frames x (1-f)), plate digest (pending the plates) |
| `headline` | numbers only | counts by class, off-era channels, K* (kstar.csv), fraction of channels whose coarse centre is within 0.1 dB of mu_0, width-factor ranges |

Not produced by this run and named as pending in the manifest: the four-world
table (needs the delay-cut banks rebuilt under the 3.0.0 identity), the
cross-build record and the archive accounting paragraph (product QA, from
pilot-proxy's inventory), and the plate digests (the plates are rendered from
`channels/chNN/spectra_window.json` by the figure step).
