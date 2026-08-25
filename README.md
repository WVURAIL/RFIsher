# RFIsher

RFIsher evaluates masking cost and contamination-residual tolerance with
Fisher forecasts. Give it a frequency-dependent masking policy and an optional
contamination residual; it reports the observing-time cost, target
significance, and residual-amplitude tolerance.

The current release ships a CHIME, ATSC DTV, and 21 cm BAO reference
application. Its public scenario and bank boundaries are designed for other
bands and instruments, but its installed forecast targets and builders are
still CHIME/BAO-specific. RFIsher should not yet be described as a
target-independent Fisher package.

## Quickstart

Two provenance-complete CHIME banks ship with the package, so the basic
workflow does not require a RadioFisher checkout:

```python
from rfisher import api, scenarios

fc = api.load()                                   # Planck-2018 bank
mask = {17: 0.33, 30: 0.97, 31: 0.24}             # masked-time fractions

api.required_time(fc, mask, target=5.0)           # survey BAO target
api.required_time(fc, mask, target=5.0, zbin=6)   # one redshift bin
api.significance(fc, 2.0, mask)                   # after two on-sky years
api.masking_cost_curve(fc, band=scenarios.DTV_BAND)  # masking-cost curve
```

`examples/minimal_example.py` runs this calculation in a few seconds. A
continuous band works through the same scenario interface:

```python
n71 = scenarios.FrequencyBand("5g_n71_downlink", 617.0, 652.0)
scenario = scenarios.Scenario(
    "n71",
    "ATSC and 5G n71 downlink",
    fractions={17: 0.33, 31: 0.24},
    frequency_fractions={n71: 0.15},
)

api.required_time(fc, scenario, target=5.0)
```

Banks use the strict schema-v2 contract. Pre-provenance banks are rejected
and must be rebuilt.

## What is being priced

RFIsher keeps two costs separate:

- **Masking cost:** masking a fraction `f` retains `(1 - f)` of the effective
  integration time. Complete excision is priced as lost survey volume.
- **Contamination residual:** retained data can carry residual power `r`
  relative to thermal noise. In the incoherent variance model, the effective
  time factor becomes `(1 - f) / (1 + r)`.

Coherent contamination is a bias problem, not simply extra variance. The
dedicated bias-response workflow propagates it through a `_Pres` Fisher row
and refuses unsupported or numerically unstable evaluations.

## Shipped reference result

The reference application reproduces the CHIME Overview BAO forecast before
applying masking. Selected masking-only results are:

| Scenario | Survey time penalty | Time for 2% transverse distance at z=1.40-1.50 |
|---|---:|---:|
| No masking | 1.00x | 0.32 on-sky yr |
| Legacy detector rate table | 1.03x | 0.42 on-sky yr |
| 50% of the DTV band masked | 1.15x | 0.63 on-sky yr |
| Channel 30 excised | 1.008x | 0.36 on-sky yr |
| Channel 30 retained, Fourier convention | 1.06x | 1.96 on-sky yr |

The legacy table is a historical detector summary, not a DTV
occupancy measurement. Use corrected survey products for occupancy claims.
Absolute Fisher times are model-dependent; masking ratios are the more robust
comparison. See [the CHIME/BAO application](docs/chime-bao-application.md) for
the full inputs, results, and caveats.

## Documentation

- [Architecture and scope](docs/architecture.md) — component boundaries,
  bank contract, backend hooks, and the current generality limit.
- [Masking cost](docs/masking-cost.md) — retained-time and excision models,
  weighting conventions, and mask-product provenance.
- [Contamination residuals](docs/contamination-residuals.md) — variance and
  bias paths, coherence, threshold decisions, and refusal rules.
- [CHIME/BAO reference application](docs/chime-bao-application.md) — fiducial
  configuration, headline results, inputs, and application-specific caveats.
- [Reproducibility](docs/reproducibility.md) — installation, verification,
  bank builds, dissertation checks, and evidence regeneration.
- [Release index](docs/releases.md) — immutable existing releases and the
  layout for future releases.
- [Forecast-completion contract](docs/forecast-completion.md) — complete
  estimator, schema, and analytic-template details.

## Install and verify

```bash
git clone https://github.com/WVURAIL/RFIsher
cd RFIsher
python -m pip install -e ".[test]"
python -m pytest tests/ -q
python scripts/verify_bank.py
python scripts/check_paper_numbers.py
```

The command-line entry points are:

```bash
rfisher-forecast --uniform 0.25
rfisher-forecast --cosmology pact2025 --uniform 0.25
rfisher-build-bank --help
```

RadioFisher is needed only to build a bank or perform direct backend
validation. See [reproducibility](docs/reproducibility.md) for the pinned
checkout and exact commands.

## Project boundary

[pilot-proxy](https://github.com/WVURAIL/pilot-proxy) owns detector kernels,
survey-product generation, and the underlying masking measurements.
[RadioFisher](https://github.com/WVURAIL/RadioFisher) supplies the supported
Fisher backend. RFIsher validates those inputs, maps them to masking and
contamination-residual scenarios, and prices their scientific effect.

The immutable historical releases retain their original paths, filenames,
schema identifiers, and provenance fields. They are indexed in
[docs/releases.md](docs/releases.md).

## Citation

If this software feeds a publication, cite RadioFisher (Bull, Ferreira, Patel,
and Santos, *ApJ* 803, 21, 2015; arXiv:1405.1452) for the forecasting
formalism and pilot-proxy for the masking measurements. Project citation
metadata are in `CITATION.cff`.
