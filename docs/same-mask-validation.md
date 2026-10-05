# Same-mask synthetic science validation

Reproduce the completed original study from source commit
`185e033adb082f1b496eb183a46c249cb47e4b60`; its manifest authenticates that
implementation. The separately frozen
[candidate-specific follow-up](same-mask-candidatewise.md) uses its own
command, seed namespace, protocol and outputs. New source does not silently
replace the original study's authenticated source or refusal outcome.

The [fixed protocol](SAME_MASK_SYNTHETIC_PROTOCOL.md) declares a bounded
score-level experiment connecting observable threshold decisions, supported
10-second complex visibility endpoints, signal response and observing time.
It extends the separate detector-frontier and fixed Gaussian-moment checks;
it is not a physical channel calibration or a new channel ruling.

The [first fixed-budget result](same-mask-results-2026-10-03.md) refused joint
uncertainty inference (5 of 512 resamples usable). It established no selected
or empirically validated operating point; the saved failure is retained.

From a checkout, with RFIsher's normal dependencies:

```sh
PYTHONPATH=src python -B -m rfisher.cli response same-mask \
  --protocol docs/SAME_MASK_SYNTHETIC_PROTOCOL.md \
  --out ../science-validation
PYTHONPATH=src python -B -m rfisher.cli response same-mask \
  --validate ../science-validation
```

The output directory must be new. The command has no sample-size, threshold,
seed or acceptance-limit tuning flags. Its protocol hash must match the
reviewed protocol. All block summaries, refusals and bootstrap accounting are
saved. A complete manifest binds source files, numerical environment,
settings, protocol and the exact artifact inventory. Validation authenticates
those inputs and reconstructs calibration, selected-policy evaluation, the
candidate CSV and readable report without generating new draws.

`calibration.json` freezes each candidate choice before evaluation draws.
`result.json` retains the complex moments, empirical and Gaussian covariance
comparison, recomputed and frozen-mask responses, uncertainty and coverage
diagnostics. `candidates.csv` and `REPORT.txt` are reviewable summaries.
`blocks/` preserves the sufficient endpoint and injected-statistic summaries;
`run_identity.json` remains useful if a run fails before producing a complete
manifest. Revalidation deliberately refuses changed sources or numerical
environments instead of silently certifying a different calculation.

Selection minimizes **whole 10-second blocks** on the fixed finite grid;
continuous required-block ratios remain diagnostic. A point minimum, its
conservative evaluation exposure, uncertain candidate ordering, and an
independently validated result are distinct fields. No automatic knee or
2% plateau selects the candidate. The reject-all limit has no finite science
information. An unavailable or failed calculation is preserved as a refusal.

The primary response uses signal injections with recomputed observed-stream
masks and empirical fourth-order covariance. The clean counterfactual is
available only through the synthetic generator, and no post-processing
sensitivity is applied for subtraction. Coverage statements condition on the
frozen response, target, policy and realized independent reference center,
locally at theta=0. They do not certify unconditional coverage of a chosen
optimum or a physical telescope response. See the protocol for support,
exposure and uncertainty limits.
