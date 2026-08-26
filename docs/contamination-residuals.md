# Contamination residuals

A mask has two outcomes: it discards exposure and it changes the contamination
left in retained data. RFIsher calls the second quantity the contamination
residual. A detector threshold can be evaluated as a scientific operating
point only when both outcomes are present.

## Incoherent variance model

Let `r` be retained contamination power relative to contemporaneous thermal
noise:

```text
r = P_res / P_N.
```

If the contamination residual behaves as incoherent excess variance, a slice
masked for fraction `f` has the effective-time factor

```text
(1 - f) / (1 + r).
```

The contamination residual is optional. With no residual supplied, every
masking-only reference result is unchanged.

```python
from rfisher import api

fc = api.load()
mask = {35: 0.48}
residual = {35: 0.59}

api.required_time(fc, mask, residuals=residual, target=5.0)
```

This construction is not conservative for coherent contamination. A coherent
term can bias a fitted parameter even when its variance contribution appears
small; that case uses the bias-response path described below.

## Threshold selection boundary

Threshold selection uses two inputs for one channel:

1. `histograms_by_rho`, built from the channel's latest stable era; and
2. `science_tolerance`, the accepted systematic-residual level.

Preparation happens before selection. It removes invalid frames, verifies
that the chosen era is stable, handles residual correlation, applies the
proxy-to-science transfer calibration, and emits one complete residual-score
histogram for each candidate rank `rho`. Each histogram covers the same frame
population and records the common usable bulk size. Its bins are bounded by
candidate `eta` values, with a final overflow bin, and each bin carries:

- the number of frames;
- the sum of calibrated systematic-residual contributions; and
- the sum of calibrated variance-residual contributions, when measured.

The rank `rho` is one-based. All accepted frames have the same duration and
exposure, so count fractions are exposure fractions. Across ranks, the frame
population, bulk size, full systematic total, and optional variance basis and
total must agree.
Candidate `eta` grids may differ by rank; every supplied pair is evaluated
without interpolation.

The selector does not need a separate sample count. For a candidate `eta`, it
sums the bins at or below that boundary:

```text
N = sum(all bin counts)
f = 1 - N_kept / N
r_sys = sum(kept systematic totals) / N_kept
r_var = sum(kept variance totals) / N_kept
```

It evaluates every supplied `(rho, eta)` pair with a supported retained
population and compares

```text
(1 + r_var) / (1 - f)
```

subject to `r_sys <= science_tolerance`. Candidates retaining fewer than 30
frames are not evaluated. Among points within 2% of the minimum cost, the
selector prefers lower `r_sys`, less masking, lower `rho`, then lower `eta`.
It reports both `rho` and `rho / (bulk_size + 1)`. If the histograms do not
contain variance totals, the objective is the masking-only cost
`1 / (1 - f)`. The systematic residual still enforces the tolerance; it is
not substituted for the missing variance term.

The stored residual totals must be additive: a retained prefix sum divided by
its frame count must already be the calibrated residual for that subset. If
correlation or transfer must be estimated again after masking, preparation
must do that work before producing the histogram; the compressed selector
cannot infer it.

Era start and end dates, rejected-frame counts, and source provenance remain
metadata on the prepared product. They are needed to reproduce and audit the
calibration, but they are not inputs to `thresholds.optimize_threshold`.
`residual.threshold_sweep` and the raw-product scripts retain their role as
preparation and reference paths; they are not the pure selection boundary.
The prepared histograms can be reused across systematic-budget choices:
testing a smaller `zeta` changes only `science_tolerance`.

## Residual budget

The released scalar budget maps a pilot-proxy survey product to `r` through
four terms:

1. the transmitter-on shelf;
2. the retained-frame bound;
3. ground or `m = 0` filtering;
4. delay filtering and the residual correlation time.

For the channel-35 reference product, the representative chain is:

| Term | Value | Status |
|---|---:|---|
| Transmitter-on shelf | -10.6 dB | measured |
| Retained-frame bound | -26.2 dB | bounded by the single-frame floor |
| Ground / `m = 0` filter | -20.6 dB | measured decomposition |
| Delay filter | -3.6 to -11.4 dB | analysis choice |
| Coherence | +27.5 dB | measured, 46 min |
| `P_res / P_N` | 0.59 | 0.41--0.74 interval |

The retained-frame quantity is a bound, not a direct measurement of the
surviving shelf. A frame with no pilot excess can only place that shelf below
the single-frame sensitivity floor.

Run the budget with:

```bash
python scripts/residual_budget.py 521.npz --off-through 2021-08 --plot
```

## Sidereal decomposition

The ground-filter term is derived from a decomposition keyed by sidereal day
and acquisition. For the channel-35 reference cohort of 5,647 acquisitions on
1,438 sidereal days:

| Timescale | Shelf-power share | Treatment |
|---|---:|---|
| Constant | 94.52% | removed as `m = 0` |
| Inter-day drift | 4.62% | removed within each day |
| Intra-day | 0.85% | survives |
| Sub-acquisition | 0.02% | survives and averages down |

The sidereal-day boundary is load-bearing. Splitting at acquisition boundaries
instead places day-to-day drift in the surviving term, understates filtering
by about 7 dB, and then counts the same power again in coherence.

## Correlation time

`residual.correlation_time` estimates the contamination-residual correlation
time from a thermal-noise-corrected, same-sidereal-day structure function of
acquisition-mean shelf power. It reads the `(1 - 1/e)` crossing and uses a
day-block bootstrap.

Each acquisition mean carries estimation variance `V_fast / n_frames`. That
term is subtracted from squared differences so sparse acquisitions do not
imitate a short correlation time. Bootstrap resampling keeps each day's time
ordering intact; shuffling acquisitions would destroy the structure being
measured.

The estimator refuses rather than guessing. Its gates require:

- enough same-day pairs and enough days;
- a crossing at a lag resolved by the acquisition cadence;
- correlation time stable across trim level; and
- surviving power stable across trim level.

Channel 35 passes: its answer moves by only 1.08x over the tested 75--95% trim
range. Channels 34 and 36 are tail-dominated and fail. For them, the top 1% of
frames carry 99.5% and 91.4% of the linear variance, respectively, so the
estimated moment is controlled by the trim boundary. A refusal receives no
ground-filter credit; the fallback carries all shelf power at the one-sidereal-
day cap and is labeled `[BOUND]`.

## Time-scaling families

The bias workflow keeps two physical limits distinct.

### Thermal-noise normalized at each time

The reported amplitude `r(t)` is held constant while time changes. Residual
power and thermal-noise power both average down approximately as `1/t`. This
is the stationary, finite-correlation-time limit used by the historical
convergence calculation.

### Fixed physical amplitude at a reference time

The reported amplitude is `r_ref = P_res / P_N(t_ref)`. Physical residual
power is held fixed while thermal noise falls, so

```text
r(t) / r_ref = t / t_ref.
```

This is the deliberately conservative persistent-residual limit. The two
families agree at `t_ref` and answer different questions away from it. Neither
family proves that a measured pilot residual has the assumed persistence;
that requires visibility-domain time and coherence measurements.

## Does masking pay?

Reducing the contamination residual is not sufficient. The reduction must be
worth the discarded exposure. For unmasked residual `r_unmasked`, retained
residual `r_masked`, and masking fraction `f`, masking pays in the incoherent
variance model only when

```text
net = (1 + r_unmasked) / (1 + r_masked) * (1 - f) > 1.
```

`residual.mask_benefit` evaluates this decision per channel. The raw-product
`residual.threshold_sweep` reference path follows it as the detector threshold
moves; prepared operating-point selection uses `thresholds.optimize_threshold`.

At the deployed `F > mu0` decision for the two channels with a measurable
transmitter-off epoch:

| Channel | Masked fraction | Residual change | Cleaning gain | Exposure cost | Net |
|---:|---:|---:|---:|---:|---:|
| 35 | 0.988 | 20.7 to 0.563 | 13.9x | 85.7x | 0.162 |
| 34 | 0.995 | 51.4 to 5.03 | 8.7x | 214.9x | 0.041 |

Both decisions fail the cost test. The contamination reduction is real, but
it is bought with much more exposure than it saves. `scenarios.from_mask_decisions`
builds the selective policy: it masks where the decision pays and carries the
full contamination where masking is declined. It never drops a declined
channel merely to make the forecast look cleaner. `force=True` constructs the
uniform policy for comparison.

For the channel-35 reference chain, including the measured contamination
residual moves the result from:

| Scope | Masking only | Masking plus contamination residual |
|---|---:|---:|
| Survey | 1.032x | 1.133x, interval 1.111--1.147 |
| `z = 1.40--1.50` | 1.347x | 2.14x, interval 1.90--2.34 |

At the sidereal-day bound the corresponding penalties would be about 1.25x
and 26x. Measuring coherence therefore changes the worst-bin conclusion by
about an order of magnitude.

## Coherent bias path

RadioFisher's `P_res` hook adds a `_Pres` response row to the Fisher matrix.
RFIsher records such a bank as a strict-v2 `bias_response` artifact and
rejects it from the ordinary `Forecast` and `api.load()` path. The dedicated
workflow evaluates the parameter shift per unit contamination amplitude,
tests whether the response overlaps discarded null modes, and reports a
tolerance only for accepted points.

The released analytic response families are:

- scalar thermal-noise shaped;
- `low_kparallel`;
- `wedge_like`; and
- `k_shell_localized`.

They are equally unit-normalized sensitivity hypotheses, not probabilities
and not measured channel templates. Frequency-localized, baseline-localized,
and sidereal-coherent empirical templates remain refused because the current
callable interface lacks the required physical coordinates and authenticated
visibility residuals.

The exact estimators, named schema values, stability fields, and release
commands are in the
[forecast-completion contract](forecast-completion.md). Bank construction and
verification commands are collected in [reproducibility.md](reproducibility.md).
