# Terminology

The science side's symbols with the names the code uses for them, and its
frozen tokens. The detector side's page (pilot-proxy `docs/TERMINOLOGY.md`)
has the full table, the words that have one meaning only and the detector's
frozen tokens; the rows below appear there with the same code names.

## Symbols and code names

| Dissertation | Code |
|---|---|
| f | `masked_fraction` |
| C = (1 + r_var)/(1 − f) | `rfisher.verdict.interval.cost` |
| r_sys, r_sys at G = 1 | `r_sys`, `r_sys_incoherent` |
| η_Pfa (the false-alarm limit) | `eta_pfa` |
| η_eval | `eta_eval` |
| r_tol | `r_tol` (`tolerance_basis` says which basis) |
| S | `suppression_db` |
| η_sci | `eta_sci` |
| 𝒟 (deployable set) | `interval_low`, `interval_high`, `interval_status`, `in_deployable_set` |
| R = r_sys/r_tol | `R` |
| "selector" | `rfisher.verdict.interval.select` |
| "OC table" | `operating_characteristic_v1` |

The science side's own terms:

- **r_tol and its bases.** `grid_T1yr_stability_gated` (the archive's table:
  the forecast on its year grid, gated by the stability test),
  `exact_time_reference_2026-09-09` (the capture's, integrated at T*), and
  `coarse_world_sensitivity_2026-09-09` (the capture's deployed-scenario
  reference). See [cosmology-entry.md](cosmology-entry.md).
- **G**, the coherence gain of a residual integrated over the survey; at
  G = 1 the residual adds incoherently.
- **Scenario**, never "world": a delay-filter suppression S with its role,
  `rule` (the verdict rests on it) or `sensitivity` (reported beside it).
- **Post-processing sensitivity**: an assumed downstream suppression that this
  work does not measure (the delay filter S, the ground filter, G → 1),
  applied only in `rfisher.verdict.sensitivity`. "Credit" is not a term of the
  model; it survives in frozen tokens and in the text of the 2026 records.
- **The deployable set** is the feasible candidates at or above
  `max(eta_pfa, eta_eval)`; `lower_bound_source` says which bound applied.

## Frozen tokens of the science side

- the tolerance table's `world` column and the per-bin table that carries it
  (`src/rfisher/data/tolerances/filter_scenarios_T1yr.csv`, pinned with its
  provenance), `worlds.csv` with its `none_*` and `deployed_*` columns, and the
  wide tolerance columns (`r_tol_dilation` and the rest) of the frozen archive
  layouts;
- the release basis name `coarse_world_sensitivity_2026-09-09`;
- `rfisher_results.archive.psd window spectra v1`, `rfisher-archive-ledger`,
  `rfisher-archive-report`, `WVURAIL/RFIsher`;
- in the capture records of the 2026 campaign: `GROUND_CREDIT`,
  `credit_readings/`, the credit readings of revisions 2 and 3, the
  capture handoff's `lb_priced` column (the within-dump bound this side
  prices) and its `eta` (a rung of the coarse ladder, not a deployable
  threshold).
