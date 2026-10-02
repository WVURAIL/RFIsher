# Decision register

Every science and selector choice of this project is an entry of one of two
registers under `projects/chime_bao/`, read through `rfisher.policy`, which
refuses an entry whose side is not `science`. Each entry has a stable id, a
value, its units, its basis, a status (`locked`, `provisional`, `open`,
`conditional`, `historical`), a rationale, its evidence and the values a sensitivity study
would try. The detector's choices (eras, the residual floor, the rank and
multiplier families, the drift margins) are entries of pilot-proxy's detector
register (`projects/chime_atsc/detector_register.json` there).

`src/rfisher/records/chime_atsc_2026/data/policy_2026_archive/` holds a frozen
copy of both registers as they were when the archive releases were written
(policy sha 05dfa2a6, the value their ledgers record): the frozen release
layouts are priced under that copy, so a change of an entry here moves the
verdict and never the layouts of record.

The tables below give each entry's id, value, status and evidence; the JSON
files hold the rest. A test (`tests/test_decision_register.py`) holds this page
to the registers: every table cell must match.

## Science register (`projects/chime_bao/science_register.json`)

| Id | Value | Status | Evidence |
|---|---|---|---|
| `archive_reference.bias_year_grid` | [0.25, 1.0, 5.0, 10.0] | historical | scripts/bias_tolerance.py@e041d5e |
| `archive_reference.forecast_year_grid` | [1.0, 2.0, 3.0, 5.0, 8.0] | historical | scripts/three_worlds.py@e041d5e |
| `archive_reference.three_worlds_parameters` | ["aperp", "apar", "fs8"] | historical | scripts/three_worlds.py@e041d5e |
| `science.response_solver.default_estimator` | "perbin_appendix_a" | locked | scripts/bias_tolerance.py@e041d5e; dissertation/chapters/ch09_tolerance.tex |
| `science.response_solver.default_time_scaling` | "noise_normalized_at_each_time" | provisional | scripts/bias_tolerance.py@e041d5e |
| `science.response_solver.maximum_condition_number` | 1000000000000.0 | provisional | https://doi.org/10.1137/1.9780898718027; src/rfisher/forecast.py@e041d5e |
| `science.response_solver.minimum_volume_fraction` | 1e-06 | provisional | src/rfisher/forecast.py@e041d5e |
| `science.response_solver.relative_nullspace_cutoff` | 1.4901161193847656e-08 | provisional | https://doi.org/10.1137/1.9780898718027; src/rfisher/forecast.py@e041d5e |
| `science.response_stability.maximum_tolerance_ratio` | 1.2 | provisional | scripts/bias_tolerance.py@e041d5e |
| `science.response_stability.time_fraction` | 0.1 | provisional | scripts/bias_tolerance.py@e041d5e |
| `science.systematic_budget.primary_zeta` | 1.0 | provisional | https://doi.org/10.1111/j.1365-2966.2007.12731.x |
| `science.systematic_budget.sensitivity_zeta` | [0.5, 0.3, 0.1] | locked | dissertation/chapters/ch09_tolerance.tex |
| `transfer.delay_suppression.default_key` | "none" | locked | src/rfisher/residual.py@7b0067b |
| `transfer.systematic_gain` | 1.0 | conditional | docs/tolerance.md |
| `transfer.variance_gain` | 1.0 | conditional | docs/tolerance.md |

## Selector policy (`projects/chime_bao/selector_policy.json`)

| Id | Value | Status | Evidence |
|---|---|---|---|
| `selection.cost_plateau_ratio` | 1.02 | provisional | src/rfisher/thresholds.py@7b0067b; src/rfisher/verdict/interval.py |
| `selection.tie_break` | ["systematic_residual", "masked_fraction", "candidate_order"] | locked | src/rfisher/thresholds.py@7b0067b; src/rfisher/verdict/interval.py |
| `selection.tolerance_equality_is_feasible` | true | derived | src/rfisher/thresholds.py@7b0067b; src/rfisher/verdict/interval.py |
| `selector.archive_exclusion_gain` | {"measured": "booked", "bounded": 1, "cap": 1} | locked | src/rfisher/verdict/screening.py |
| `selector.fine_rank` | 63 | locked | src/rfisher/verdict/interval.py |
| `selector.precedence` | ["tolerance refused", "detector refused", "keep", "excise", "undetermined"] | locked | src/rfisher/verdict/screening.py |
| `selector.sensitivity_limited_share` | 0.95 | provisional | src/rfisher/verdict/screening.py |
| `selector.unmeasured` | {"exclude": "most_favorable", "keep": "least_favorable"} | locked | src/rfisher/verdict/screening.py |
