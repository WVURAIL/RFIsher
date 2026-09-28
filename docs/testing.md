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

The coverage report includes every Python module in `rfisher` and
`rfisher_results`, including modules never imported by the tests. The gate
requires 85% combined statement/branch coverage overall, at least 70% per
module, and stronger thresholds on scalar validation, NPZ loading, threshold
selection, forecasts, archive acceptance and block resampling. A missing
module or a statement-only report fails the gate. Multiprocessing coverage
counts archive worker execution as well as its parent process. Open
`htmlcov/index.html` to inspect individual missed statements and branches.

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
| `bank.experiments`, `layout`, `filter_scenarios` | `forecast/test_experiments.py`, `forecast/test_layout.py`, `forecast/test_filter_scenarios.py`: experiment reconstruction, time conventions, the delay-cut hooks, the filter scenarios and the science profile, feed geometry, frequency scaling and annular pair-count conservation |
| `science_model`, `forecast.radiofisher_bao.model`, `response`, `tolerance` | `forecast/test_model.py`, `tolerance/test_rule.py`, `tolerance/test_table.py`, `tolerance/test_bands.py`, `tolerance/test_boundary.py`, `tolerance/test_response_offline.py`: bands to bins against the frozen archive tables, the rule's refusal accounting, the table's layout and v3 provenance, the refusal of a table whose recorded inputs changed, band tolerances against the frozen values, and the identifier boundary of the general layers |
| `channels`, `scenarios` | `test_channels.py`, `test_scenarios.py`, `test_numerical_benches.py`: physical bands, overlap/refusal rules, masking/excision, arithmetic and harmonic band reductions versus a frequency-cell oracle |
| Historical `tolerances` constants | `test_tolerances.py`: all-channel coverage, documented binding bins and independent release-ledger comparisons when available |
| `thresholds`, `preparation`, `selection_policy` | `test_thresholds.py`, `test_preparation.py`, `test_selection_policy.py`, `test_threshold_boundary_bench.py`, `test_numerical_benches.py`: direct per-frame replay across ranks, adjacent uint64 boundaries, one-ULP tolerance checks, support and eligibility, deterministic ties, drift/resampling and claim provenance |
| `residual`, `bank.templates`, `residual_scores` | `test_residual.py`, `forecast/test_templates.py`, `test_residual_scores.py`, `test_floor_provenance.py`: coherent/incoherent paths, additive scores, exact integer reductions, residual floors and evidence/refusal rules |
| `pilotproxy`, `archive_acceptance` | `test_pilotproxy_v5.py`, `test_archive_acceptance_bench.py`: a complete synthetic 23-channel cohort, malformed/missing fields, mixed identities, sample/frame accounting, canonical JSON identity and CLI exit behavior |
| `incumbent` | `test_incumbent.py`, `test_incumbent_product_bench.py`: burst versus steady interference, exact SK null variance, acquisition boundaries and a common scoring population |
| `bank._validation`, `npzio`, `products`, `bank.resources` | `forecast/test_validation.py`, `test_npzio.py`, `test_products.py`, `forecast/test_resources.py`: strict scalar types, eager archive ownership, no pickle execution, product registries, packaged data, the nine bank pins and wheel resources |
| `plots` | `test_plots.py`: every public forecast figure rendered headlessly, plotted numerical values, axes, masks, zero-information markers and PDF/PNG output |
| Results `evaluations`, `estimator_transfer`, `census_psd`, `results_tree`, `cli`, `style` | Matching `test_results_*.py`, `test_results_cli.py`, `test_results_style.py`: pooling/calibration, result discovery, command routing, reproducible rendering, semantic legends and diagram layout |
| Archive `blocks`, `eras`, `anchors`, `nulls`, `psd`, `masked_spectra` | Matching `test_results_archive_*.py`: UTC/calendar support, chronological whole-acquisition splits, bootstrap multiplicities and quantiles, era discovery, calibration, containment and masked spectra |
| Archive `products`, `selection`, `operating`, `screening`, `flaggers`, `chain`, `tolerances`, `worlds` | Matching `test_results_archive_*.py`, `test_tolerance_ledger_bench.py`: product adaptation, selection/replay, held-out evaluation, threshold plateaus, policy comparisons, science-budget transfer, historical ledger parsing and refusal states |
| Archive `run`, `ledger`, `numbers` | `test_results_archive_run.py`, `test_archive_pipeline_bench.py`, `test_results_archive_ledger.py`, `test_results_archive_numbers.py`: spawned workers, complete populated-era selection and spectral replay, written ledgers, source identity and auditable numbers |
| Every archive `report` module | `test_results_archive_report_*.py`, `test_report_missing_components.py`: table/figure data, missing evidence, counts, denominators, band weighting, report manifests and number provenance |
| Response report and release scripts | `tolerance/test_bias_estimators.py`, `tolerance/test_bias_workflows.py`, `tolerance/test_current_bias_authentication.py`, `forecast/test_templates.py`, `test_run_forecast.py`, `test_forecast_template_comparison.py`, `test_dissertation_figures.py`, `test_render_forecast_template_assets.py`; includes real historical/current response-bank builds and reference-tampering rejection |
| Coverage gate itself | `test_coverage_gate.py`: missing/new modules, branch regressions, low-coverage components hidden by larger modules and unreadable reports |

## What makes the numerical benches independent

Seeded benches replay raw frames instead of reproducing histogram prefix sums;
compare Fisher outputs with dense matrix inverses; integrate frequency cells
instead of reusing scenario interval reduction; and integrate baseline density
back to an independently enumerated pair count. Seeds, small synthetic products
and temporary output directories make these checks repeatable and suitable for
CI. Bootstrap tests inspect the weights supplied to the statistic to prove that
whole acquisitions, rather than individual correlated frames, are resampled.

Small backend and CAMB doubles test interface contracts and unit conversions.
They do not replace real-backend validation or certify a new cosmology.

The opt-in `synthetic_archive_health` fixture supplies an importable provider
for generated products, including inside spawned workers. It is not autouse:
production health-provider absence and malformed-mask tests still exercise
their refusal paths. The populated-era bench checks that the chain fit sees
only calibration frames, then runs selection, operating-point choice and
spectral replay on the separate evaluation block.

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

The coverage denominator is the two installed packages. Script entry points
have the targeted tests listed above; coverage is not claimed for every line of
one-off research, figure-generation or rebuild scripts, or for external projects.
