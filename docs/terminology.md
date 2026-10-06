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
| η_Pfa (the false-alarm limit, reported only) | `eta_pfa` |
| η_eval | `eta_eval` |
| r_tol | `r_tol` (`tolerance_basis` says which basis) |
| η_sci | `eta_sci` |
| 𝒟 (deployable set) | `interval_low`, `interval_high`, `interval_status`, `in_deployable_set` |
| R = r_sys/r_tol | `R` |
| "selector" | `rfisher.verdict.interval.select` |
| "OC table" | `operating_characteristic_v1` |

The science side's own terms:

- **r_tol and its bases.** `grid_T1yr_stability_gated` (the archive's table:
  the forecast on its year grid, gated by the stability test),
  `exact_time_reference_2026-09-09` (the capture's, integrated at T*). The
  capture's table of record was priced at identity on
  `coarse_world_sensitivity_2026-09-09`, which no verdict reads. See
  [cosmology-entry.md](cosmology-entry.md).
- **G**, the coherence gain of a residual integrated over the survey; at
  G = 1 the residual adds incoherently.
- **Scenario**, never "world": the condition the forecast is priced in. There
  is one, `none` (no delay filter), of role `rule`.
- **Post-processing** is not modelled: no delay filter, ground filter or other
  downstream suppression multiplies a residual. "Credit" is not a term of the
  model; it survives in frozen tokens and in the text of the 2026 records.
- **The deployable set** is the feasible candidates at or above `eta_eval`;
  the false-alarm limit `eta_pfa` is a reported diagnostic, not a bound.

## Frozen tokens of the science side

- the tolerance table's `world` column and the per-bin table that carries it
  (`src/rfisher/data/tolerances/tolerance_T1yr.csv`, pinned with its
  provenance), and the wide tolerance columns (`r_tol_dilation` and the rest)
  of the frozen archive layouts (whose `worlds.csv` and f sigma_8 columns the
  releases keep and these records no longer write);
- the release basis name `coarse_world_sensitivity_2026-09-09`;
- `rfisher_results.archive.psd window spectra v1`, `rfisher-archive-ledger`,
  `rfisher-archive-report`, `WVURAIL/RFIsher`;
- in the capture records of the 2026 campaign: `WORLD` and `GROUND_CREDIT`
  (identity switches: the table of record was priced in the 200 ns world with
  the ground credit), the releases' `credit_readings/`, the
  capture handoff's `lb_priced` column (the within-dump bound this side
  prices) and its `eta` (a rung of the coarse ladder, not a deployable
  threshold).
