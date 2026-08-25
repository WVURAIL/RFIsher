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
from rfisher import api, scenarios

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
from rfisher import api, scenarios

band = scenarios.FrequencyBand("example_downlink", 617.0, 652.0)
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
that produced it. The package carries two distinct sources:

1. a historical quarterly CSV used by the original forecast; and
2. corrected-geometry survey products supplied explicitly by the caller.

The historical table was written on 2026-07-18 from the first production
trawl with the coarse rule

```text
F > mu_hat + 0.012 * mu0.
```

Its weight bank placed the coarse-channel center at Nyquist. That convention
was later found to be offset by half the sample rate: pilots were suppressed
by 39--47 dB at the line on every channel except channel 30, whose pilot lies
near the self-canceling quarter-rate position. The CSV therefore records a
legacy detector epoch, not DTV occupancy. Its 97% values for channels 24 and
30 are refused-channel placeholders rather than measured rates.

The historical rows remain useful as a reproducible baseline, but they must
not support an occupancy statement. Use corrected products for current
detector claims:

```python
from rfisher import channels, scenarios

products = ["506.npz", "521.npz", "537.npz"]
table = channels.mask_table_from_products(products)
scenario = scenarios.survey_product_scenario(products)
```

Set `RFISHER_PRODUCT_DIRS` to a platform-separated list of product search
directories when paths should be resolved through the registry.

## Why the two sources disagree

The following comparison exposed the geometry mismatch:

```bash
python scripts/compare_mask_tables.py 506.npz 521.npz 537.npz --forecast
```

| Channel | Historical CSV | Corrected products | Ratio |
|---:|---:|---:|---:|
| 34 | 0.0231 | 0.9909 | 43x |
| 35 | 0.1380 | 0.8370 | 6x |
| 36 | 0.0115 | 0.9991 | 87x |

This is not one detector evaluated at a different threshold. The corrected
products declare the raw positive-excess rule `F > mu0`; no single threshold
on their statistic reproduces the CSV. Their exposure counts also differ.

`channels.MaskTable` keeps the provenance beside the values. In particular,
the historical table is traceable but is marked as not being an occupancy
measurement:

```python
from rfisher import channels

current = channels.mask_table_from_products(["506.npz", "521.npz", "537.npz"])
historical = channels.legacy_rate_table()

current.is_traceable
current.is_occupancy_measurement
historical.is_traceable
historical.is_occupancy_measurement
```

The product loader also refuses:

- products made by different detector kernels or masking rules;
- two products that cover the same channel; and
- implicit mixing of corrected products with historical CSV backfill.

Use `fill_missing="csv"` only when that mixed provenance is intentional and
must be recorded. Use `fill_missing="omit"` to forecast only the covered
channels.

## What this calculation does not establish

Masking cost alone is monotone: remove less data and the time penalty falls.
It cannot select a detector threshold because it does not say how dirty the
retained data are. Threshold selection requires the contamination-residual
term described in [contamination-residuals.md](contamination-residuals.md).

The masking calculation also does not include:

- the full radial-mode coupling from spectral gaps;
- a sky-dependent mask window;
- coherent contamination bias; or
- an empirical visibility covariance not present in the supplied products.

Run `scripts/run_forecast.py` to regenerate the reference application's
masking-cost tables and figures. See
[chime-bao-application.md](chime-bao-application.md) for their interpretation.
