# Dissertation figure tables (tolerance side)

Frozen snapshots behind `../figures.py`; the dissertation bundle vendors the
rendered PDFs.

| table | status |
|---|---|
| bao_time_vs_masking.csv | forecast-derived (pilot-proxy `tools/make_dissertation_tables.py --bao-time-vs-masking`, computed through this package's released forecast) |
| bao_policy_case.csv | curated snapshot (channel-33 residual-policy comparison; from the pilot-proxy summary export) |
| bao_convergence.csv | LEGACY BRIDGE recovered from the published vector artwork; replacement path: direct fixed-target tolerance calculation via the Pres research bank |
| bao_two_walls.csv | regenerated from the survey products by make_two_walls.py under the reconciled conventions (bridge retired; all 23 channels, evidence + tau columns) |
| bao_era_points.csv | compact export from calibrated_thresholds.py --era-points; channel 32 preserves its five-minute upper bound and channel 35 its measured coherence |

The convergence bridge reproduces the published curve exactly.  It remains
identified as a bridge until its direct regeneration lands.

Regenerate the current-era rows from the per-pilot cohort with:

```bash
PP_ANALYSIS=/path/to/pilot-proxy/analysis PP_SRC=/path/to/pilot-proxy/src python3 scripts/calibrated_thresholds.py --products /path/to/per-pilot-products --out /tmp/era-recovery --only 32,35 --era-points scripts/dissertation/data/bao_era_points.csv
```

Each row records the product filename, product SHA-256, detector schema and
version, combined analysis-source SHA-256, floor basis, raw residuals, and
dilation tolerance used to derive the quoted ratios.
