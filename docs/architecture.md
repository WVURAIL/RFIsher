# Architecture and scope

RFIsher is an analysis layer between measured contamination decisions and a
Fisher forecast. It evaluates two distinct effects:

1. data removed by masking or excision; and
2. a contamination residual left in retained data.

The shipped implementation applies that layer to CHIME 21 cm BAO forecasts
and ATSC DTV contamination. The scenario and bank contracts admit other
frequency intervals and compatible banks, but the installed target metric,
instrument builders, and direct-validation paths remain CHIME/BAO-specific.

## Data flow

The target selector workflow is:

1. A detector project produces per-frame scores and residual measurements.
2. Latest-era preparation rejects invalid frames, verifies stability, handles
   correlation, applies the science transfer calibration, and emits one
   complete residual-score histogram per candidate rank `rho`.
3. `thresholds.optimize_threshold` takes those histograms and a science
   tolerance, then selects the `(rho, eta)` operating point.
4. The selected mask fraction and residual enter a `Scenario`, which maps
   them onto physical frequency intervals.
5. Each forecast bin receives a surviving-volume fraction and an effective
   integration-time factor.
6. A Fisher bank supplies the matrix at the requested effective time.
7. The forecast layer marginalizes the declared BAO parameters and reports a
   target significance, uncertainty, or time-to-target.
8. The bias-response workflow evaluates coherent contamination separately.

This separation is deliberate. Detector design and survey-product generation
belong in pilot-proxy; the Fisher calculation belongs in RadioFisher; RFIsher
owns the scientific-cost mapping, validation, and evidence records between
them.

## Main components

| Component | Responsibility |
|---|---|
| `api` | Short load, scenario, significance, and required-time calls |
| `scenarios` | Frequency intervals, masking fractions, residual ratios, and excision policy |
| `fisherbank` | Versioned forecast and bias-response banks with interpolation |
| `forecast` | BAO marginalization, significance curves, and time inversion |
| `residual` | Raw-product statistics, coherence, budgets, and reference threshold sweeps |
| `thresholds` | Pure `(rho, eta)` selection from calibrated residual-score histograms |
| `products` | External survey-product registry and path resolution |
| `channels` | ATSC channel and physical-frequency conversion |
| `survey` and `layout` | CHIME experiment definition, bins, time conventions, and baselines |
| `compat` | RadioFisher checkout discovery, binding, and capability checks |
| `pkcache` | Content-verified matter-power-spectrum caches |

The preferred import namespace is `rfisher`. The earlier namespace remains a
compatibility surface for existing banks, scripts, and downstream consumers.

## Threshold boundary

The pure threshold selector has two inputs: `histograms_by_rho` and
`science_tolerance`. A histogram is complete for one candidate `rho`: its bins
cover every prepared frame, including the overflow above the last candidate
`eta`. Each bin records its count and calibrated systematic-residual total.
It may also record a calibrated variance-residual total. The histogram carries
the usable bulk size, which validates `rho` and gives the comparable rank
fraction `rho / (bulk_size + 1)`.

`rho` is a one-based rank. Every accepted frame must have the same duration and
exposure, so a fraction of frame counts is also the masked-exposure fraction.
Across ranks, the family must describe the same frame population, common bulk
size, full systematic total, and variance basis and total when present. The
selector rejects the family when those checkable invariants disagree.
Each rank may supply its own ordered `eta` grid. The selector compares the
recorded `(rho, eta)` pairs directly and does not interpolate a rectangular
surface.

For each `(rho, eta)`, the selector sums the retained bins. It derives the
frame count, masked fraction `f`, retained systematic residual `r_sys`, and,
when present, retained variance residual `r_var`. A candidate must retain at
least 30 frames, and feasible points satisfy `r_sys <= science_tolerance`. The
cost is

```text
(1 + r_var) / (1 - f).
```

If variance totals are absent, the selector minimizes the masking-only cost
`1 / (1 - f)`. It does not treat `r_sys` as `r_var`.
Among points within 2% of the minimum cost, selection prefers lower `r_sys`,
less masking, lower `rho`, then lower `eta`, so mapping order cannot change the
result.

The residual totals are sufficient statistics only when they are additive:
their retained prefix sum divided by the retained count must equal the
calibrated residual for that subset. A correlation or transfer model that must
be refit after masking belongs in preparation and cannot use this compressed
form.

Frame validity, era choice, stability tests, correlation treatment, and
proxy-to-science transfer calibration belong to preparation. Era dates,
rejected-frame counts, and source identities remain product metadata. They do
not become selector arguments. `residual.threshold_sweep` and the raw-product
scripts remain preparation and reference paths rather than the pure selector.
The selector core implements this boundary, but the tracked survey products
predate the external histogram exporter. Their existing operating-point rows
remain historical results until preparation emits an accepted family.

## Fisher-bank contract

A strict schema-v2 bank contains:

```text
F, t_grid, zs, zc, paramnames, meta
```

For a fixed bin, total observing time enters the Fisher integrand through the
thermal-noise power

```text
P_N proportional to T_sys^2 / t_tot.
```

RFIsher therefore banks the full matrix over a time grid and reconstructs a
scenario by replacing `t_tot` with its effective time and multiplying by the
surviving volume. It interpolates `F(t) / t^2` in log time. This is exact in
the thermal-noise-dominated limit and is checked against direct RadioFisher
evaluations over the released grid.

The schema, rather than a particular builder, is the evaluation boundary. A
different builder can provide a compatible bank if it satisfies the same
time-scaling and surviving-volume assumptions. The current validator and
builders nevertheless recognize only the released Bull-2015 and CHIME-2022
configurations; accepting an arbitrary target or instrument requires a later
schema and API extension.

Two artifact kinds are kept distinct:

- `forecast` banks contain ordinary forecast parameters and are accepted by
  the high-level API;
- `bias_response` banks contain the `_Pres` response row and are accepted only
  by the dedicated contamination-bias workflow.

This prevents a response row from being marginalized as if it were an
ordinary fitted parameter.

## Direct backend path

The supported RadioFisher backend exposes three experiment-dictionary hooks:

- `noise_freq_weight`: surviving-time weight as a function of frequency;
- `noise_freq_mode`: `invvar` or `fourier` band reduction; and
- `vol_frac`: surviving survey-volume fraction.

A `NaN` weight marks an excised slice. Unknown or missing required
capabilities fail before a masked direct evaluation begins. The hooks are
no-ops when absent, so the unmodified backend result remains the clean
forecast.

For the scenarios represented by the current bank, these hooks reduce to the
same effective-time and volume factors used by bank interpolation.
`scripts/verify_bank.py` checks the two paths, including a full-survey
comparison. Direct evaluation remains useful when extending the model to a
new dimension, such as radial-mode coupling from spectral gaps.

## Provenance boundary

Every released bank records:

- baryon, cold-dark-matter, and neutrino densities;
- named cosmology and H I evolution profile;
- RadioFisher backend identity and capabilities;
- source-tree identities and manifests;
- matter-power cache settings and content hash;
- experiment settings and baseline hash; and
- artifact kind and forecast assumptions.

The existing schema-v2 identities are immutable. They retain their recorded
source paths and field names even as the preferred public namespace changes.
New provenance spellings require a new schema version; they must not be
backfilled into an existing bank or frozen release.

## Current target boundary

The shipped target is not generic. `Forecast` evaluates the BAO amplitude
`A`, either shared across bins in the Bull-2015 treatment or independently per
bin in the CHIME Overview Appendix-A treatment. The combined significance is
`A / sigma(A)` with fiducial `A = 1`. Per-bin distance and growth responses are
available through the associated research workflows.

A target-independent release would need, at minimum:

- a declared target or linear parameter combination in bank metadata;
- configurable nuisance-parameter exclusion and expansion rules;
- builders that are not restricted to the two CHIME configurations; and
- direct-validation adapters for the new instrument and estimator.

Until those contracts exist, other bands can be mapped onto the shipped
CHIME/BAO bank, but other scientific targets cannot be claimed as supported.

## Repository layout

```text
src/                 installed package namespaces and package data
scripts/             bank, evidence, verification, and application commands
scripts/dissertation dissertation-specific figures and compact tables
data/                 research comparison banks
docs/                 architecture, methods, release contracts, and schemas
paper/                BAO masking-cost manuscript source
out/                  tracked results and two immutable release roots
tests/                package and workflow regression tests
```

The `out/` directory contains historical material as well as working results;
see the [release index](releases.md) before changing anything there. Detector
kernels, non-pilot selection, and new survey-product generation remain outside
this repository. The [archived roadmap](archive/legacy-roadmap.md) records the
remaining cross-project evidence dependencies.
