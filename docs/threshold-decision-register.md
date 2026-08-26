# Threshold decision register

The threshold calculation itself still has only two scientific inputs:

1. a prepared residual-score histogram family; and
2. the science tolerance.

Everything else is preparation evidence. RFIsher records those choices in
`selection_policy`, gives each a stable identifier, and embeds the complete
snapshot and its SHA-256 digest in a prepared family. Run:

```bash
python scripts/threshold_decisions.py
python scripts/threshold_decisions.py --json
python scripts/threshold_decisions.py --check-operational
```

The last command currently exits nonzero by design. The archive supports a
screening calculation, but several choices required for an operational
calibration remain provisional, open, or conditional.

## Status meanings

| Status | Meaning |
|---|---|
| `derived` | Follows from a definition or arithmetic identity |
| `locked` | Adopted with adequate project evidence for its stated role |
| `provisional` | Used by the current screen but still needs sensitivity or holdout evidence |
| `open` | No value has been adopted |
| `conditional` | A stated closure assumption, not a measurement |
| `historical` | Preserved only to reproduce an earlier calculation |

The justification basis is separate. A value can be a policy choice even when
the method surrounding it is standard. A compiled default is not evidence.

## Science budget

| Decision | Current value | Status | Why |
|---|---:|---|---|
| `science.systematic_budget.primary_zeta` | 1.0 | provisional | The paper permits a modeled shift as large as one statistical standard deviation. This is deliberately permissive and is not a universal criterion. |
| `science.systematic_budget.sensitivity_zeta` | 0.5, 0.3, 0.1 | locked | These expose successively tighter budgets without rebuilding channel histograms. |
| Fisher response time perturbation | ±10% | provisional | It probes interpolation and cancellation sensitivity. |
| Maximum response-tolerance drift | 1.20x | provisional | Larger movement triggers a refusal in the current bias-response workflow. |
| Maximum response condition number | `1e12` | provisional | More weakly constrained modes are treated as unresolved; sensitivity values are `1e10`, `1e12`, and `1e14`. |
| Relative null-space cutoff | `sqrt(float64 epsilon)` = `1.4901161193847656e-8` | provisional | It separates numerical null-space overlap from roundoff; sensitivity values include machine epsilon and `1e-6`. |
| Minimum retained-bin volume fraction | `1e-6` | provisional | A nearly empty redshift slice is skipped rather than passed as a numerically tiny Fisher matrix. Sensitivity values include zero, `1e-8`, and `1e-4`. |
| Default response estimator | per-bin Appendix A | locked | This is the paper path; the combined multibin estimator remains an explicit alternative. |
| Default response time scaling | noise normalized at each time | provisional | It represents a stationary finite-correlation residual; fixed physical power at a reference time is the declared alternative. |

The bias-over-statistical-error form follows Amara and Réfrégier
([2008](https://doi.org/10.1111/j.1365-2966.2007.12731.x)); the numerical
choice of `zeta` remains survey policy.
The response-solver gates follow standard conditioning practice, but their
exact numerical values remain sensitivity choices
([Higham 2002](https://doi.org/10.1137/1.9780898718027)).

## Latest-era definition

| Decision | Current value | Status | Why |
|---|---:|---|---|
| Summary | Monthly median of per-acquisition `10 log10(mean F / mu0)` | provisional | It suppresses the transient tail before looking for station-state changes. |
| Split score | strongest `abs(z) * abs(step)` | provisional | It combines a rank shift and a material level shift. |
| Minimum observed months | 6 per side | provisional | It rejects short seasonal excursions. |
| Minimum elapsed span | 270 days per side | provisional | It requires the first and last observation on each side to be separated by most of a year. This is elapsed span, not 270 days containing data, and is computed from timestamps rather than `30.44 days/month`. |
| Minimum level step | 2 dB | provisional | It targets transmitter changes rather than ordinary propagation scatter. |
| Rank threshold | `abs(z) >= 4` | provisional | It is conservative for one comparison but is not a globally calibrated change-point probability after scanning dates. |
| Maximum eras | 5 | provisional | It limits recursive over-segmentation without pretending to be a formal penalty. |
| Era used for thresholding | latest | locked | Earlier station states do not describe the current channel. |
| Receiver-state intersection | unset | open | Station and receiver configuration eras still need a common boundary. |

Mann and Whitney define the rank statistic
([1947](https://doi.org/10.1214/aoms/1177730491)). Pettitt shows why a scanned
change point is a global problem rather than many independent rank tests
([1979](https://doi.org/10.2307/2346729)). The current numerical guardrails are
archive-specific and remain sensitivity parameters.

## Within-era drift

`preparation.prepare_threshold_family` splits accepted latest-era rows at the
calendar midpoint, freezes one score, correlation, and transfer calibration,
and builds the two histogram families. The lower-level
`preparation.assess_histogram_stability` only compares supplied halves; it
does not perform the split or verify their origin. The comparison covers every
selector-evaluable `(rho, multiplier_q16)` pair and does not receive `zeta`.

| Decision | Current value | Status | Why |
|---|---:|---|---|
| Split | latest-era calendar midpoint | locked | Frame cadence changed over the archive; an equal-count split would mix different time spans. |
| Surface | every selector-evaluable candidate pair | derived | A selected point cannot bypass the early/late check. Points with fewer than 30 pooled retained frames are outside the numerical selector and are skipped. |
| Calendar support | 6 observed months and 270 elapsed days per half | provisional | Month count records calendar coverage; elapsed span is the time between the first and last accepted frame, not a count of observed days. |
| Minimum retained frames per half | unset | open | Early and late residual precision needs its own derivation. Candidate sensitivity values are 15, 30, 50, and 100; the pooled selector floor is not a justification. |
| Maximum early/late cost ratio | unset | open | It must reflect a science-materiality margin. Candidate sensitivity values are 1.02, 1.05, and 1.10. |
| Maximum early/late systematic-residual ratio | unset | open | It must come from transfer uncertainty or a residual-budget allocation. Candidate sensitivity values are 1.05, 1.10, and 1.20. |
| Block-based uncertainty evidence | unset | open | The preparation path can resample acquisition or sidereal-day blocks separately within each era half and bound the maximum ratio on the complete candidate surface. No block unit, minimum block count, seed, replicate count, coverage, or per-channel result has been adopted yet. |

The deterministic point-estimate drift screen remains available for screening
compatibility. It returns `refused_unconfigured` until the per-half floor and
both drift limits are declared. Operational evidence also requires a
`BlockResamplingPlan` and aligned frame block IDs. Every resample must retain
the declared per-half frame floor at every selector-evaluable point. A block
that crosses the calendar split, too few blocks, too few successful resamples,
or either surface-wide upper bound above its declared margin is a structured
refusal. The replicate count must resolve the requested upper tail, and at
least `ceil(coverage * replicates)` draws must support the complete surface.
Schuirmann motivates the need for declared equivalence margins
([1987](https://doi.org/10.1007/BF01068419)); Künsch motivates resampling whole
dependent blocks ([1989](https://doi.org/10.1214/aos/1176347265)).

On the current 23-channel archive, the calendar-support gates alone refuse the
latest eras of channels 19 and 24: each channel-19 half has about 249 elapsed
days, and channel 24 has only five observed months in its late half. Channel
30 is the edge case with six observed months and about 313 elapsed days in its
late half. These are policy outcomes, not uncertainty estimates.

## Shelf persistence and correlation treatment

The current statistic is acquisition-mean linear shelf power, using valid
positive-excess frames with finite shelf estimates. That population is
threshold-conditioned and is not an independently false-alarm-calibrated
sample.

| Decision | Current value | Status |
|---|---:|---|
| Primary trim and probes | p90; p75, p90, p95 | provisional |
| Maximum trim movement | 2.0x for timescale and surviving power | provisional |
| Minimum support | 100 selected frames, 100 sidereal days, 200 same-day pairs | provisional |
| Lag edges | 0, 300, 900, 1800, 2700, 3600, 5400, 7200, 14400, 28800 s | provisional |
| Populated lag bin | at least 40 raw pairs | provisional |
| Minimum populated bins | 3 | provisional |
| Plateau | lags above 7200 s | provisional |
| Persistence crossing | `1 - 1/e` of the plateau | provisional |
| Resampling | 200 whole-sidereal-day replicates, seed 20260807 | provisional count; locked seed |
| Interval | p16--p84 | provisional |
| Refusal bound | one sidereal day, no common-mode credit | provisional |
| Cadence-matched coverage | unset | open |
| Integrated autocorrelation validation | unset | open |

Whole-block resampling preserves dependence
([Künsch 1989](https://doi.org/10.1214/aos/1176347265)). Structure functions
can remove a white measurement-noise contribution
([Simonetti, Cordes, and Heeschen 1985](https://doi.org/10.1086/163418)), but
finite duration and gaps can create false breaks
([Emmanoulopoulos et al. 2010](https://doi.org/10.1111/j.1365-2966.2010.16328.x)).
Raw pair counts are not effective sample sizes because one acquisition appears
in many pairs.

The released `tau / frame_time` mapping is now explicitly named the
rectangular coherent-block model. A `1/e` persistence crossing is not a
general variance-inflation factor. Variance after averaging depends on the
integrated autocorrelation or direct block sums
([Bartlett 1946](https://doi.org/10.2307/2983611),
[Geyer 1992](https://doi.org/10.1214/ss/1177011137)). The current mapping is
preserved for screening reproducibility and cannot support an operational
claim until that validation is supplied.

## Transfer and histogram construction

| Decision | Current value | Status | Consequence |
|---|---:|---|---|
| Nominal pilot below shelf | 11.3 dB | provisional | Standard waveform conversion; receiver-specific departure remains possible. |
| Pilot capture efficiency | 1.0 | conditional | Unity is a closure assumption pending receiver measurement. |
| Shelf-to-systematic gain | 1.0 | conditional | No measured visibility-domain transfer exists. |
| Shelf-to-variance gain | 1.0 | conditional | No measured covariance transfer exists. |
| Fine-stage credit | 10.0 dB | provisional | Ten decibels is a rounded screening scenario. An earlier equal-norm row-sum study found 9.32 and 9.77 dB at two false-alarm levels; those values are sensitivity checks, not a measured range for the complete current detector. |
| Default delay-filter credit | none | locked | The forecast does not model this foreground-removal stage, so the default claims no suppression. Nonzero scenarios remain explicit what-if bounds. |
| Residual score | minimum Q16 multiplier that keeps the frame | derived | It follows the exact integer cross-multiplication and represents zero-reference cases without floating division. |
| Designated-set calibration | unset | open | The latest-era pilot anchor and width still need held-out calibration. |
| Candidate `rho` grid | every one-based rank through the minimum valid bulk count | derived | Every accepted frame supports every included rank; omitting a supported rank is refused. |
| Rank index mapping | `rho = cfar_rank + 1` | derived | The detector field is a zero-based array index; `rho` is the corresponding one-based order-statistic rank. |
| Minimum Q16 multiplier | integer 1, or `eta = 1 / 65536` | locked | This is the smallest positive multiplier accepted by the exact detector decision; it is not `eta = 1`. |
| Candidate multiplier grid | integer 1 and every unique deployable required Q16 value | derived | This is the exact empirical decision staircase. Values are not rounded to a floating or geometric grid. |
| Equal-exposure frames | required | derived | Only then is a count fraction an exposure fraction. |
| Additive residual totals | required | derived | Otherwise histogram prefix sums are not sufficient. |

A required value of `2**64` is the always-masked sentinel. It is not a
deployable multiplier and remains in the histogram overflow bin.

If correlation or transfer must be re-estimated after each hypothetical mask,
the compressed histogram contract is invalid. Preparation must then evaluate
the time-ordered series at every candidate and export a candidate-response
table. It must not force a mask-dependent correction into additive bins.

The current survey archive lacks the exact per-frame target, lower-reference,
and upper-reference `fine_power_u64` terms required to derive the Q16 keep
boundary at each rank. Its floating fine summary cannot reproduce the integer
decision, including its zero-reference and tie behavior. Operational Q16
preparation therefore requires a detector rerun with the exact fields retained.

## Numerical selector

| Decision | Current value | Status | Why |
|---|---:|---|---|
| Minimum retained frames | 30 | provisional | Candidates below this support are not evaluated. Sensitivity values are 30, 50, and 100. |
| Cost plateau | 1.02x minimum | provisional | Points inside two percent are treated as practically tied. Sensitivity values include 1.00, 1.01, 1.02, and 1.05. |
| Feasibility boundary | `r_sys <= tolerance` | derived | The science tolerance is a closed upper bound. |
| Tie order | lower `r_sys`, less masking, lower `rho`, lower `multiplier_q16` | locked | It first protects science margin, then exposure, then simpler settings. |
| False-alarm allocation | unset | open | It must come from the allowed loss of clean exposure, including mask dilation. |
| Required injection recovery | unset | open | Detection power must be verified after the false-alarm allocation is fixed. |

The false-alarm-first separation follows Neyman and Pearson
([1933](https://doi.org/10.1098/rsta.1933.0009)). No generic probability has
been inserted merely because one is needed.

## Historical report controls

The older archive reports remain reproducible, but their grids and support
cuts are not operational defaults. They are registered with `historical`
status so a report cannot silently acquire a new value:

| Report control | Preserved value | Replacement |
|---|---:|---|
| Coarse multiplier sweep | 1.00--1.10 by 0.01; 1.10--2.00 by 0.05; 16 geometric points to 300 | Exact empirical Q16 change points |
| Raw multiplier sweep | 1.0 plus 24 geometric points from 1.05 to 500 | Exact empirical Q16 change points |
| Positive-excess reference | eta = 1 | Exact identity `F > mu0` |
| Era calibration sweep | 1.0 plus 90 geometric points from 1.01 to 60 | Exact empirical Q16 change points |
| Two-walls multiplier sweep | 17 linear points from 1.0 to 1.8 plus 12 geometric points from 2 to 300 | Exact empirical Q16 change points |
| Prototype rank range | upper half of the usable bulk | Every supported rank |
| Prototype anchor | rejected-minus-quiet median excess, with median-peak fallback | Held-out per-channel calibration, still open |
| Prototype multiplier tie | nearest 1.0 after rounding distance to 9 decimal places | Residual-first exact Q16 tie order |
| Prototype designated half-width | 2 fine bins | Held-out per-channel calibration, still open |
| Diagnostic cohort floor | 100 frames | Precision-derived support rule, still open |
| Recent occupancy window | 3 inclusive calendar years, no earlier than 2018 | Latest accepted era |
| Operating-point report target | transverse dilation tolerance | Caller-supplied science tolerance |
| Floor-projection report target | growth-rate tolerance | Caller-supplied science tolerance |
| Floor-projection cohort | channels 32--36 | Declared analysis cohort |
| Floor-projection scenarios | coarse, fine, fine plus first-peak delay bound, fine plus second-peak delay bound | Declared report scenarios |
| Persistence-reference channel | channel 33 | Data-derived timescale from the declared reference product |
| Forecast response samples | 1, 2, 3, 5, and 8 on-sky years | Continuous response interpolation with its own stability gate |
| Standalone bias-report samples | 0.25, 1, 5, and 10 on-sky years | User-requested evaluation times |
| Three-scenario parameters | `aperp`, `apar`, `fs8` | Declared report outputs |
| Three-scenario response grid | 19 log points over `10^0`--`10^6` h plus 8 over `10^3.5`--`10^5.83` h | Response interpolation with its stability gate |
| Three-scenario cohort | channels 29, 32, 33, and 35 | Declared analysis cohort |
| Three-scenario worlds | none, first-peak bound, second-peak bound, deployed-cut scenario | Declared ordered report scenarios |

## Refusal behavior

`thresholds.optimize_threshold` remains the two-input numerical kernel.
`preparation.select_prepared_threshold` is the evidence-bearing entry point.
It refuses:

- a stale decision digest;
- a partial rank family or a family without exact Q16 boundaries;
- an era other than the latest one;
- unfiltered invalid frames;
- unequal exposure;
- mask-dependent non-additive corrections;
- missing or failed within-era drift support;
- inadequate score, correlation, or transfer evidence; and
- an operational claim while any required decision remains provisional,
  open, or conditional.

Required open decisions include the per-half retained-frame floor, both drift
limits, designated-set calibration, false-alarm and recovery targets, and the
remaining correlation and transfer validation. Block unit, minimum blocks,
seed, replicate count, and coverage remain explicit run controls that need a
recorded justification rather than library defaults.
Conditional evidence can be used only with `allow_screening=True`. The
returned selection then carries `claim_status="screening"`, its source
identity, and the policy digest; the option cannot upgrade its evidence.
