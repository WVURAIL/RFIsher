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

The maintained workflow is:

1. A detector project produces masked-time fractions and, when available,
   contamination-residual measurements with provenance.
2. `Scenario` maps those quantities onto physical frequency intervals.
3. Each forecast bin receives a surviving-volume fraction and an effective
   integration-time factor.
4. A Fisher bank supplies the matrix at the requested effective time.
5. The forecast layer marginalizes the declared BAO parameters and reports a
   target significance, uncertainty, or time-to-target.
6. The bias-response workflow evaluates coherent contamination separately.

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
| `residual` | Contamination-residual statistics, coherence, budgets, and policy decisions |
| `products` | External survey-product registry and path resolution |
| `channels` | ATSC channel and physical-frequency conversion |
| `survey` and `layout` | CHIME experiment definition, bins, time conventions, and baselines |
| `compat` | RadioFisher checkout discovery, binding, and capability checks |
| `pkcache` | Content-verified matter-power-spectrum caches |

The preferred import namespace is `rfisher`. The earlier namespace remains a
compatibility surface for existing banks, scripts, and downstream consumers.

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
