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

1. A detector project produces exact per-frame fine-power terms and residual
   measurements. Era discovery and invalid-frame bookkeeping retain only the
   accepted rows from the latest station and receiver state.
2. Conditioning turns the exact integer decision into the minimum Q16
   multiplier that keeps each frame at each supported one-based rank.
3. `preparation.prepare_threshold_family` requires every rank supported by
   every accepted frame. It derives the exact Q16 multiplier grids, splits the
   era at its calendar midpoint, builds pooled and early/late histograms, and
   runs the deterministic drift screen.
4. `preparation.select_prepared_threshold` verifies the evidence and calls
   `thresholds.optimize_threshold`, which takes the histograms and science
   tolerance and selects the `(rho, eta)` operating point. The returned claim
   retains the source identity and policy digest.
5. The selected mask fraction and residual enter a `Scenario`, which maps
   them onto physical frequency intervals.
6. Each forecast bin receives a surviving-volume fraction and an effective
   integration-time factor.
7. A Fisher bank supplies the matrix at the requested effective time.
8. The forecast layer marginalizes the declared BAO parameters and reports a
   target significance, uncertainty, or time-to-target.
9. The bias-response workflow evaluates coherent contamination separately.

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
| `preparation` | Q16 family construction, deterministic drift screening, and evidence-bearing refusal |
| `selection_policy` | Versioned decision values, rationales, sensitivity values, and digest |
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
multiplier. Each bin records its count and calibrated systematic-residual
total. It may also record a calibrated variance-residual total. The histogram
carries the usable bulk size, which validates `rho` and gives the comparable
rank fraction `rho / (bulk_size + 1)`.

`rho` is a one-based rank. A strict prepared family contains every rank from
one through the minimum valid bulk count across the accepted rows; omitting a
supported rank is refused. Every accepted frame must have the same exposure,
so a fraction of frame counts is also the masked-exposure fraction. Across
ranks, the family must describe the same frame population, common bulk size,
full systematic total, and variance basis and total when present.

The detector comparison uses an integer Q16 multiplier. Preparation records
the minimum Q16 value that keeps each frame without converting the exact
rational decision to a floating ratio. Each rank's grid begins at Q16 integer
one and includes every unique deployable decision boundary observed for that
rank. The displayed `eta` is the exact integer divided by `65536`; selection
uses the recorded integer boundary and does not interpolate a rectangular
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

Frame validity, era choice, correlation treatment, and proxy-to-science
transfer calibration begin outside the numerical selector. Era dates,
rejected-frame counts, and source identities remain product metadata. They do
not become inputs to `thresholds.optimize_threshold`.
`prepare_threshold_family` receives accepted latest-era rows and performs the
calendar split, support accounting, histogram construction, and drift screen.
`assess_histogram_stability` is the lower-level comparison only: it does not
split rows or establish that the supplied halves came from one era.

The current early/late check compares point estimates against declared drift
limits. It is deterministic and is not a statistical equivalence test.
Operational use also requires a derived per-half support rule and block-based
uncertainty whose interval lies inside the declared margins. Those decisions
remain open. The strict wrapper also refuses stale policy identity, a
non-latest era, invalid or unequal-exposure frames, mask-dependent non-additive
residual corrections, and inadequate score, correlation, or science-transfer
evidence. A permitted screening selection returns `claim_status="screening"`
with its source identity and policy digest.

The current survey archive lacks the exact per-frame fine-power terms needed
to reconstruct the Q16 decision boundaries. Its floating summary cannot be
promoted to this strict contract; the detector processing must be rerun with
the exact fields retained.

The numerical values and unresolved decisions are in the
[threshold decision register](threshold-decision-register.md). The pure
selector remains available as a numerical kernel; it does not by itself prove
that preparation occurred.

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
