# Verification benches

The companion RadioFisher fork now has its own numerical benches and
per-module coverage gates. Its source identity is checked against the banks,
and the current cosmology is tested against the published parameter table.
See [cosmologies](cosmologies.md) for Bull, Foreman and current defaults.

Run these commands from the repository root with Python 3.10 or newer:

```bash
python -m pip install -e ".[test]" -r requirements/test-coverage.txt
python -m pip check
ruff check .
python -m pytest -q --cov --cov-report=term-missing:skip-covered --cov-report=json --cov-report=html
python scripts/check_test_coverage.py
```

The coverage report includes every Python module in `rfisher`, including
modules never imported by the tests. The gate requires 85% combined
statement/branch coverage overall, at least 70% per module, and stronger
thresholds on scalar validation, the verdict's deployable set and selector,
its screen, sensitivities and handoff checks, and forecasts. A missing module or a statement-only report fails the gate.
Open `htmlcov/index.html` to inspect individual missed statements and
branches. The suite needs no pilot-proxy checkout: the detector's outputs
enter as golden handoffs under `golden/handoff/`.

CI runs these gates on Python 3.10, 3.12 and 3.14. Only the bank subpackage
`src/rfisher/forecast/radiofisher_bao/bank/` enters the Fisher banks'
scientific source digest, so tests, coverage settings, documentation and every
other module can change without re-stamping a bank. An edit under `bank/`
fails `scripts/restamp_bank_provenance.py --check`, which CI runs as a
blocking step.

## Component map

All paths below are relative to `tests/`. Existing benches and the added
independent checks complement one another; coverage alone is not a claim of
scientific correctness.

| Components | Main benches and independent checks |
|---|---|
| `forecast.radiofisher_bao.api`, `cli`, package initialization | `forecast/test_api.py`, `test_cli.py`, `test_init.py`, `forecast/test_forecast_goldens.py`, `test_readme.py`: argument validation, unit conversion, artifact routing, backend-free forecasts, the one `rfisher` command, the README quickstart and the minimal example, and the forecast values recorded at e041d5e (exact floats under the numerics they were recorded with, a relative 1e-12 elsewhere) |
| `bank.backend` | `forecast/test_backend.py`, `forecast/test_backend_binding.py`, `forecast/test_backend_discovery.py`, `forecast/test_without_git.py`: checkout precedence, exact capability contracts, import reuse and mixed-checkout refusal, and a forecast on a host without git |
| `bank.banks`, `bank.build` | `forecast/test_fisherbank_schema.py`, `forecast/test_fisherbank_preflight.py`, `forecast/test_bank_builder_bench.py`, `forecast/test_bank_interpolation_bench.py`, `forecast/test_build_command.py`, `forecast/test_bank_manifest.py`, `forecast/test_restamp.py`: strict schemas/provenance, the one-glob source manifest and its import closure, the re-stamp, the build command's grid and overrides, parameter drift, unordered worker results, every matrix element against an analytic thermal model, below/above-grid behavior |
| `forecast.radiofisher_bao.significance` | `forecast/test_significance.py`, `forecast/test_forecast_boundary_bench.py`, `test_numerical_benches.py`: dense-inverse oracles, correlated multibin information, distance errors, singular constraints, target inversion, direct-backend refusal |
| `bank.cosmologies`, `bank.pk_cache` | `forecast/test_current_cosmology.py`, `forecast/test_pkcache.py`, `forecast/test_pkcache_lifecycle.py`: published fiducial values, default/reproduction routing, neutrino accounting, authoritative densities, cache units and independent normalization, content identity, reuse, corruption, regeneration and missing optional CAMB |
| `bank.experiments`, `layout` | `forecast/test_experiments.py`, `forecast/test_layout.py`: experiment reconstruction, time conventions, feed geometry, frequency scaling and annular pair-count conservation |
| `science_model`, `forecast.radiofisher_bao.model`, `response`, `tolerance` | `forecast/test_model.py`, `tolerance/test_rule.py`, `tolerance/test_table.py`, `tolerance/test_bands.py`, `tolerance/test_boundary.py`, `tolerance/test_response_offline.py`: bands to bins against the frozen archive tables, the rule's refusal accounting, the table's layout and v3 provenance, the refusal of a table whose recorded inputs changed, band tolerances against the frozen values, and the identifier boundary of the general layers |
| `legacy_masks`, `scenarios` | `forecast/test_legacy_masks.py`, `forecast/test_scenarios.py`, `test_numerical_benches.py`: physical bands, the July 2026 rate table and its provenance, overlap/refusal rules, masking/excision, arithmetic and harmonic band reductions versus a frequency-cell oracle |
| `policy` | `test_policy.py`: every entry of the 7b0067b selection policy in the science register or the selector policy with its value (or listed as a detector or deleted entry), the dead-reference gate and the side gate |
| `verdict.handoff`, `interval`, `screening`, `archive` | `verdict/test_handoff.py`, `verdict/test_interval.py`, `verdict/test_screening.py`, `verdict/test_archive.py`, `verdict/test_verdict_boundary.py`: the handoff's schema pin and refusals, the split property against the selector of 7b0067b on its synthetic fixtures, the thinned-surface guard (a manifest that does not call the surface complete reads thinned), the screen's precedence with the 23 x undetermined of the archive, its guards (a refused family carries no keep and no excision, a floor is verified only when every family says so, a limit on the bulk or at another alpha is not certified), the union's least point, the refusal of a non-rule tolerance row, and the verdict's imports, file opens and identifiers |
| `tolerance.reference` | `tolerance/test_reference.py`: the vendored capture references by sha, the record's lambda strings and the per-bin tolerances the capture reads |
| `bank.templates` | `forecast/test_templates.py`: analytic templates and their refusal rules |
| `bank._validation`, `bank.resources` | `forecast/test_validation.py`, `forecast/test_resources.py`: strict scalar types, the bank pins, packaged data and wheel resources |
| `plots` | `test_plots.py`: every public forecast figure rendered headlessly, plotted numerical values, axes, masks, zero-information markers and PDF/PNG output |
| `records.chime_atsc_2026` archive layouts (`compat_tables`, `ladder_pricing`) | `records/test_compat_tables.py`, `records/test_compat_layout.py`, `records/test_archive_screening.py`: the frozen rows of both archive releases on a two-band golden (without their delay-filter scenarios and f sigma_8 columns, retired with stage P), the layout written end to end, and the releases' screening rule |
| `records.chime_atsc_2026` capture records | `records/test_capture_identity.py`, `records/test_capture_handoff.py`, `records/test_capture_oc.py`, `records/test_capture_rules.py`, `records/test_capture_copies.py`, `records/test_capture_release.py`: from the golden capture handoff and the record's explicit tables, the table of record (9867551a) and its v7 input, the r2 to r5.2 ruling runs, the copies and the r5.2 release byte for byte under the numerics of record (its post-processing readings retired with stage P, and the five files that lost post-processing content pinned at their new bytes) (numpy 2.3 or later; under an older numpy the tables are still compared byte for byte), the reader's objects against the release producer's, the handoff written from pilot-proxy's capture output, the rules of the producer's own tests, and the handoff's refusals |
| `records.chime_atsc_2026.cadence_report` | `records/test_cadence_report.py`: the detector's report and the table of record give the frozen `CADENCE_REPORT.md` byte for byte |
| Handoff schemas, examples, documents and the repository | `test_schemas.py`, `test_examples.py`, `test_doc_snippets.py`, `test_decision_register.py`, `test_register_evidence.py`, `test_repository_hygiene.py`: the vendored archive and capture schemas and pilot-proxy's golden handoffs by sha, the verdict example on the golden handoff, the tolerance page's snippets, the register page against the registers, the register evidence against the frozen policy copy, and the repository's file names, paths and removed-path references |
| `records.results_tree`, `response` | `records/test_results_tree.py`, `response/test_visibility.py`, `response/test_visibility_command.py`: where generated results live, and the visibility response's known moments |
| Response report and release scripts | `tolerance/test_bias_estimators.py`, `tolerance/test_bias_workflows.py`, `tolerance/test_current_bias_authentication.py`, `forecast/test_templates.py`, `test_run_forecast.py`, `test_forecast_template_comparison.py`, `test_render_forecast_template_assets.py`; includes real historical/current response-bank builds and reference-tampering rejection |
| Threshold-calibration bridge (`scripts/threshold_calibration_bridge/`) | `test_threshold_bridge.py`: the byte copies carry their recorded sha256, and the scenario evaluator reproduces the package's zero-residual scenario at the current thresholds from its 24 vendored input rows |
| Coverage gate itself | `test_coverage_gate.py`: missing/new modules, branch regressions, low-coverage components hidden by larger modules and unreadable reports |

## What makes the numerical benches independent

Seeded benches compare Fisher outputs with dense matrix inverses; integrate
frequency cells instead of reusing scenario interval reduction; and integrate
baseline density back to an independently enumerated pair count. The selector
is checked against the recorded outcomes of the 7b0067b selector rather than
against itself. Seeds, small synthetic inputs and temporary output directories
make these checks repeatable and suitable for CI. The detector's own benches
(frame replay, block resampling, era discovery) are pilot-proxy's.

Small backend and CAMB doubles test interface contracts and unit conversions.
They do not replace real-backend validation or certify a new cosmology.

The capture record tests derive nothing: every measured input is the golden
capture handoff, and each output is compared with the frozen release by
sha256.

## Optional integration and release evidence

Use `pytest -ra` to see every skip reason. External inputs must remain explicit:

- `RADIOFISHER_DIR` selects the reviewed backend checkout. CI's separate
  `radiofisher-integration` job checks direct predictions and bank pins against
  its pinned revision, runs `scripts/verify_bank.py`, the forecast goldens and
  `scripts/restamp_bank_provenance.py --check`, and rebuilds the tolerance
  table with `rfisher tolerance build`, which must match the committed bytes.
- `RFISHER_OUT` selects generated release tables. The release regressions need
  the files listed in [releases](releases.md).
- `RFISHER_ARCHIVE_RESULTS` selects archive evidence for tests that support the
  override. Some historical tests retain a fixed local archive path and report
  a skip when that evidence is absent.
- TeX/Poppler font and byte-stability tests need their rendering toolchain. The
  separate `dissertation-figure` CI job installs it and refuses unexpected
  rendering skips. The added core plot benches use Matplotlib without TeX.
- The wheel smoke job installs the built package outside the checkout and
  exercises its entry points and packaged resources.

A passing synthetic suite does not make a screening threshold operational.
The measured calibration, transfer and block-support requirements still apply.
Likewise, a bank source-digest failure requires reviewing/rebuilding the bank
against the intended scientific source; weakening a hash assertion or merely
updating its expected value does not repair stale provenance.

The coverage denominator is the installed package. Script entry points
have the targeted tests listed above; coverage is not claimed for every line of
one-off research, figure-generation or rebuild scripts, or for external projects.
