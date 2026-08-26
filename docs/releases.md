# Release index

RFIsher currently has two immutable forecast-completion release roots. They
share artifact basenames but represent different provenance states. Neither
directory should be renamed, moved, rewritten, or collapsed into the other.

## Software API v3

Version 3.0.0 removes the former `baonoise` Python namespace and console
commands, ambiguous compatibility wrappers, and the pre-v1 bias-tolerance JSON
shape. Current code uses `rfisher`, exact Q16 threshold identities, and the
versioned bias-report schema exclusively. This software cleanup does not
rewrite historical `baonoise` provenance keys or schema identifiers in the
immutable artifacts below.

### Migrating from v2

| v2 surface | v3 replacement |
|---|---|
| `import baonoise` | `import rfisher` |
| `rfisher.compat` | `rfisher.backend` |
| `baonoise-forecast`, `baonoise-build-bank` | `rfisher-forecast`, `rfisher-build-bank` |
| `api.tolerance_curve` | `api.masking_cost_curve` |
| `channels.measured_mask_fractions`, `measured_mask_table` | `legacy_rate_fractions`, `legacy_rate_table` |
| `scenarios.measured` | `legacy_rate_table_scenario` or `survey_product_scenario`, chosen explicitly |
| `MaskDecision.noise_gain` | `MaskDecision.residual_reduction` |
| `threshold_curve` keys `eta`, `best_eta` | `thresholds`, `best_threshold` |
| `at_threshold(..., eta=...)` | `at_threshold(..., threshold_label=...)` |
| floating `build_residual_score_histogram` | exact `build_q16_residual_score_histogram` |
| `MULTIPLIER_Q`, `MULTIPLIER_ONE` | `Q16_FRACTION_BITS`, `Q16_SCALE` |
| `bias_tolerance.py --json-format ...` | the sole versioned report schema; bank-grid refusal is unconditional |

The removed convenience aggregators in `layout` and `residual` had no live
callers. Compose their underlying explicit operations if an external workflow
still needs equivalent behavior.

The ordinary dissertation inputs `out/three_worlds.csv` and
`scripts/dissertation/data/bao_era_points.csv` are also authenticated pre-v3
scientific snapshots. Their embedded source hashes identify the code that
produced their values; they are checked against those recorded identities, not
against the current cleanup tree. Do not restamp them. Regenerate a new
snapshot only when the archived products are available to run the full
pipeline.

## Existing releases

### First release

The first release is stored directly in `out/` under the
`forecast_completion_*` basenames. Its manifest is:

```text
out/forecast_completion_release_manifest.json
```

This is the frozen historical release. Its four evidence ledgers were built at
their recorded source states. Later cleanup must not restamp those identities
or regenerate the files in place.

The release contains:

- four all-DTV-bin evidence ledgers;
- template-comparison, channel-mapping, and status CSV files;
- PNG and PDF tolerance figures;
- caption text;
- a TeX summary; and
- the manifest's referenced schema document.

`out/forecast_completion_evidence.json` is a smaller bounded evidence example
and is not one of the 12 manifest entries.

### Reconciliation release

The current reconciled release is:

```text
out/forecast_completion_20260824_reconciliation/
```

Its manifest is:

```text
out/forecast_completion_20260824_reconciliation/forecast_completion_release_manifest.json
```

It retains the same 12 release basenames, records `epsilon_fg = 0` for all four
response families, and uses one clean RFIsher evaluation source state across
the ledgers. Four small response banks may exist locally under its ignored
`banks/` directory. They are build prerequisites, not release artifacts, and
must not be committed as part of the bundle.

The dissertation repository vendors both releases under its own `evidence/`
directory. Those copies are independently covered by the dissertation
manifest and are also immutable.

## Why both remain

The reconciliation release did not erase the first release. It corrected and
made explicit the shared scientific evaluation identity while preserving the
original result as an auditable historical state.

Some derived files happen to be byte-identical across the two roots, while the
evidence ledgers, status tables, comparison table, and manifest record
different provenance. Byte equality of an individual figure is not a reason
to deduplicate an authenticated release.

Each manifest records paths as well as content hashes. Moving a file would
change the represented bundle even if its bytes stayed fixed.

## Rules for existing roots

- Do not regenerate either release in place.
- Do not change its schema identifiers or provenance field names.
- Do not rename its files to match the preferred current namespace.
- Do not add local banks to the manifest.
- Do not replace the first release with links to the reconciliation release.
- Validate a release from the source state recorded in its evidence, not by
  forcing current source to reproduce an older source digest.
- If a scientific or presentation change is needed, create a new dated
  release.

## Future layout

New release bundles should no longer be mixed with ordinary generated files
at the root of `out/`. Use:

```text
releases/
  <application>/
    YYYY-MM-DD-<description>/
      README.md
      manifest.json
      schema/
      evidence/
      tables/
      figures/
```

For the shipped application, `<application>` should be `chime-bao`. A release
README should state:

- scientific scope and target;
- input and source identities;
- whether inputs are measured, bounded, modeled, or refused;
- exact generation and verification commands;
- artifact inventory and manifest contract; and
- any prior release it supersedes without deleting.

Ordinary regenerated results can remain under `out/` or move to a future
`artifacts/working/` directory. They should not be called releases unless they
have a manifest, immutable input identities, and a documented validation
boundary.

Future schema names and provenance keys should use the current RFIsher
identity. Existing schema-v2 identifiers remain unchanged for compatibility
and historical verification.

## Related documentation

- [Reproducibility commands](reproducibility.md)
- [Forecast-completion contract](forecast-completion.md)
- [CHIME/BAO application](chime-bao-application.md)
- [Architecture and provenance boundary](architecture.md)
