# Tolerance: masking cost and contamination residual

A mask has two outcomes: it discards exposure, and it changes the
contamination left in the retained data. This page gives the models RFIsher
uses for both: the masking cost (retained time and excised survey volume) and
the contamination residual (incoherent excess variance, and the coherent bias
path behind the tolerance table).

# Masking cost

Masking removes exposure. RFIsher translates that loss into effective
integration time and, for excised frequency ranges, surviving survey volume.
This calculation is separate from the contamination residual left in retained
data.

## Per-slice model

For a slice masked for a fraction `f` of observing time,

```text
t_eff = t * (1 - f)
P_N,eff = P_N / (1 - f).
```

The first relation is the primary model. The second is the equivalent
thermal-noise statement. A masking scenario is treated as a duty cycle that is
uncorrelated with the sky signal. Seasonal or sidereal clustering has the same
first-order time cost but can add mode coupling that is not represented by
this scalar model.

## Excision

A slice at or above the scenario's excision threshold is removed from the
analysis. Its cost is the overlapped fraction of the redshift bin's Fisher
information volume; it does not degrade the thermal noise of the surviving
band.

Per-channel scenarios use an excision threshold of 50% by default. Uniform
scenarios are retained-time stress tests by default and therefore do not
excise. Supply `excise_threshold` explicitly when uniform excision is the
intended policy:

```python
from rfisher.forecast.radiofisher_bao import api, scenarios

fc = api.load()
kept = api.scenario_from(uniform=0.75, band=scenarios.DTV_BAND)
excised = api.scenario_from(
    uniform=0.75,
    band=scenarios.DTV_BAND,
    excise_threshold=0.50,
)
```

Complete frequency gaps also mix radial Fourier modes. The released forecast
uses a scalar volume loss; it does not claim to replace a full spectral-window
or quadratic-estimator calculation.

## Combining slices within a bin

Two declared conventions reduce heterogeneous masked fractions within one
forecast bin.

### Time convention

The default `time` convention uses sample counting or inverse-variance
weighting:

```text
w_bar = mean(1 - f).
```

It is the standard assumption when surviving samples can be weighted
optimally.

### Fourier convention

The `fourier` convention uses the arithmetic mean of per-slice thermal-noise
power:

```text
w_bar = 1 / mean(1 / (1 - f)).
```

It is a deliberately pessimistic reduction for retained heterogeneous slices.
The two conventions agree for uniform masking. They bracket the released
first-order treatments, but they are not universal bounds on every mapmaker or
power-spectrum estimator.

## Physical frequency intervals

ATSC channel numbers are a convenience adapter. The scenario model itself
uses physical frequency intervals, so other bands can share a bank when they
overlap its frequency coverage:

```python
from rfisher.forecast.radiofisher_bao import api, scenarios

band = scenarios.FrequencyBand(
    "example_downlink", 617.0, 652.0, label="Example downlink")
scenario = scenarios.Scenario(
    "example",
    "example downlink",
    frequency_fractions={band: 0.15},
)

fc = api.load()
api.required_time(fc, scenario, target=5.0)
```

A scenario wholly outside the bank's frequency coverage has exactly unit
penalty by construction. The high-level API warns because the same result can
also signal a frequency-unit mistake.

## Mask-product provenance

A masked fraction is meaningful only beside the rule and detector geometry
that produced it. The historical quarterly table the original forecast used
(`src/rfisher/data/survey_quarterly_rates_all23.csv`, written on 2026-07-18 from the first
production trawl with the coarse rule `F > mu_hat + 0.012 * mu0`) records a
legacy detector epoch, not DTV occupancy: its weight bank placed the
coarse-channel center at Nyquist, half the sample rate from the true
position, which suppressed the pilots by 39 to 47 dB on every channel but
channel 30, and its 97 % values for channels 24 and 30 are placeholders for
refused channels. It is kept as the reproducible baseline of the July 2026
forecast validation (`scripts/run_forecast.py`, `scripts/verify_bank.py`) and
supports no occupancy statement. Current masked fractions come from the
detector side's operating characteristic (pilot-proxy's handoff), with the
rule and the geometry recorded beside them. The comparison that exposed the
mismatch, and the product loader of the time, are in the history
(`docs/masking-cost.md@f56916a`).

## What this calculation does not establish

Masking cost alone is monotone: remove less data and the time penalty falls.
It cannot select a detector threshold because it does not say how dirty the
retained data are. Threshold selection requires the contamination-residual
term described in [the contamination residual](#contamination-residual).
Latest-era preparation packages that information as one complete
residual-score histogram for every rank supported by every accepted frame.
The candidate boundaries are exact Q16 multipliers derived from the detector
comparison, not a floating or geometric `eta` grid. The selector takes those
histograms and the science tolerance, derives `f` from the bin counts, and
evaluates `(1 + r_var) / (1 - f)` over feasible `(rho, eta)` pairs with at
least 30 retained frames. A fixed 2% cost plateau avoids a spurious choice on
a flat surface. If no variance-residual totals are present, the selector uses
`1 / (1 - f)` and does not treat the systematic residual as an estimate of
variance.

The 30-frame floor and 2% plateau are provisional project policies, not
universal statistical constants. Their rationales and required sensitivity
runs are recorded in
[decision-register.md](decision-register.md).
The separate early/late retained-frame floor is still open and must be derived
from the precision required of the drift calculation. Passing the current
deterministic drift screen is not an equivalence result; operational use also
requires block-based uncertainty and adopted drift limits.

The current archive lacks the exact per-frame fine-power fields needed to
construct the Q16 candidate family. Historical masking results remain valid
for their stated rules, but they cannot be relabeled as strict prepared-family
selections without a detector rerun.

The masking calculation also does not include:

- the full radial-mode coupling from spectral gaps;
- a sky-dependent mask window;
- coherent contamination bias; or
- an empirical visibility covariance not present in the supplied products.

Run `scripts/run_forecast.py` to regenerate the reference application's
masking-cost tables and figures. See
[application-chime.md](application-chime.md) for their interpretation.

# Contamination residual

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
from rfisher.forecast.radiofisher_bao import api

fc = api.load()
mask = {35: 0.48}
residual = {35: 0.59}

api.required_time(fc, mask, residuals=residual, target=5.0)
```

This construction is not conservative for coherent contamination. A coherent
term can bias a fitted parameter even when its variance contribution appears
small; that case uses the bias-response path described below.

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

The verdict prices a candidate threshold by the same model, as the cost
`C = (1 + r_var) / (1 - f)` of `rfisher.verdict.interval.cost`; the historical
per-channel readings of this test, and the sidereal and correlation-time
budgets of the 2026-08 screening chain, are in the history
(`docs/contamination-residuals.md@f56916a`).

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
