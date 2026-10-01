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

Three provenance-complete CHIME banks ship with the package, so the basic
workflow does not require a RadioFisher checkout:

```python
from rfisher.forecast.radiofisher_bao import api, scenarios

fc = api.load()                                   # the default cmbspa2026 bank
mask = {17: 0.33, 30: 0.97, 31: 0.24}             # masked-time fractions

api.required_time(fc, mask, target=5.0)           # survey BAO target
api.required_time(fc, mask, target=5.0, zbin=6)   # one redshift bin
api.significance(fc, 2.0, mask)                   # after two on-sky years
api.masking_cost_curve(fc, band=scenarios.DTV_BAND)  # masking-cost curve
```

`examples/minimal_example.py` runs this calculation in a few seconds. A
continuous band works through the same scenario interface:

```python
n71 = scenarios.FrequencyBand(
    "5g_n71_downlink", 617.0, 652.0, label="5G n71 downlink")
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

Threshold selection is split at the handoff. The detector (pilot-proxy)
characterizes each band: every candidate threshold with its masked fraction,
kept residual and evaluability, the false-alarm limit eta_Pfa (the higher
1 - alpha quantile of Q, alpha = 1e-3, on the band's own verified
signal-free population; a control band's quantile, such as Q37(1e-3), is a
surrogate and never a band's eta_Pfa), and the stability screen
(`oc_table.csv`, `oc_summary.csv` and
`manifest.json`, schema `operating_characteristic` v1). RFIsher prices that
surface against the band's tolerance and nothing else:

- `rfisher.verdict.interval` gives each family its science threshold eta_sci
  (the largest eta whose kept residual meets r_tol), the deployable set between
  max(eta_Pfa, eta_eval) and eta_sci, and the selection inside it: the least
  cost `(1 + r_var) / (1 - f)` within 2% of the minimum, ties broken by kept
  residual, masked fraction and candidate order;
- `rfisher.verdict.screening` applies the screen's precedence (tolerance
  refused, detector refused, keep only with a certified eta_Pfa, excise only
  when every family's deployable set is empty, otherwise undetermined);
- `rfisher.verdict.sensitivity` is the one place a sensitivity factor (a
  delay-filter or other post-processing credit) multiplies a residual.

The selector's constants are data (`projects/chime_bao/selector_policy.json`),
read through `rfisher.policy`; `selector.fine_rank` chooses the fine ranks the
selector reads. A small example is in
[`examples/verdict_from_oc_table.py`](examples/verdict_from_oc_table.py). Every
science choice is an entry of the project's two registers,
`projects/chime_bao/science_register.json` and `selector_policy.json`, with
its value, units, basis, status, rationale, evidence and sensitivity values;
the detector's choices are entries of pilot-proxy's register.

Given a characterization directory and the band tolerances:

```bash
rfisher tolerance bands --project projects/chime_bao --bands CHAR/manifest.json --out TOL
rfisher verdict archive --project projects/chime_bao --characterization CHAR --tolerances TOL --out SCIENCE
```

The code of record of the 2026 campaign is `rfisher records`: the frozen
archive release layouts, and the capture ruling of record (release r5.2 and
its table of record) from the capture handoff.

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
comparison. See [the CHIME/BAO application](docs/application-chime.md) for
the full inputs, results, and caveats.

## Documentation

- [Architecture and scope](docs/architecture.md) — component boundaries,
  bank contract, backend hooks, and the current generality limit.
- [Masking cost](docs/tolerance.md) — retained-time and excision models,
  weighting conventions, and mask-product provenance.
- [Contamination residuals](docs/tolerance.md) — variance and
  bias paths, histogram threshold selection, coherence, and refusal rules.
- [Threshold decision register](docs/decision-register.md): the
  earlier single register of preparation and selection choices, kept as a
  record; the current entries are the two project registers.
- [CHIME/BAO reference application](docs/application-chime.md) — fiducial
  configuration, headline results, inputs, and application-specific caveats.
- [Reproducibility](docs/reproducibility.md) — installation, verification,
  bank builds, dissertation checks, and evidence regeneration.
- [Verification benches](docs/testing.md) — component coverage, numerical
  oracles, CI coverage gates, and optional integration checks.
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
```

Generated results, including the two forecast-completion release roots, live
outside the repository. Point `RFISHER_OUT` at that results tree so the
release regression tests read the shipped copies; without it those tests
skip. See [releases](docs/releases.md).

The command-line entry points are:

New forecasts default to the August 2026 combined cosmology. Bull's Planck
2013 and Foreman's Planck 2018 inputs remain explicit reproduction options;
see [cosmologies](docs/cosmologies.md) for the three primary roles.

```bash
rfisher forecast --uniform 0.25
rfisher forecast --cosmology cmbspa2026 --uniform 0.25
rfisher build-bank --help
rfisher tolerance show
rfisher verdict archive --help
rfisher records --help
```

RadioFisher is needed only to build a bank or perform direct backend
validation. After installing the pinned checkout, run
`python scripts/verify_bank.py`. See
[reproducibility](docs/reproducibility.md) for the exact setup.

## Project boundary

[pilot-proxy](https://github.com/WVURAIL/pilot-proxy) owns detector kernels,
survey-product generation, and the underlying masking measurements.
[RadioFisher](https://github.com/WVURAIL/RadioFisher) supplies the supported
Fisher backend: the integrand and the instrument-agnostic hooks that cut or
weight it, in the backend's own units. RFIsher validates those inputs, maps
them to masking and contamination-residual scenarios, supplies every
survey-specific number, decision, and dataset the hooks consume, and prices
the scientific effect.

The immutable historical releases retain their original paths, filenames,
schema identifiers, and provenance fields. They are indexed in
[docs/releases.md](docs/releases.md).

## Citation

If this software feeds a publication, cite RadioFisher (Bull, Ferreira, Patel,
and Santos, *ApJ* 803, 21, 2015; arXiv:1405.1452) for the forecasting
formalism and pilot-proxy for the masking measurements. Project citation
metadata are in `CITATION.cff`.
