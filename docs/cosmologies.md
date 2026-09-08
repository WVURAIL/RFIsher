# Forecast cosmologies

The three primary fiducials have different purposes:

| Use | Name | Survey configuration | Selection |
|---|---|---|---|
| Bull reference configuration | `planck2013` | `bull2015` | Explicit historical bank |
| Foreman/CHIME Overview reference configuration | `planck2018` | `chime2022` | `api.load(cosmology="planck2018")` |
| New forecasts | `cmbspa2026` | `chime2022` | `api.load()` or `rfisher-forecast` without a cosmology argument |

The implemented fiducials have these values (density fractions rounded here;
the bank metadata retains the full values):

| Parameter | Bull | Foreman | Current |
|---|---:|---:|---:|
| H0 [km/s/Mpc] | 67.0 | 67.32 | 68.32 |
| Omega_m | 0.316 | 0.3158 | 0.301440 |
| Omega_b | 0.049 | 0.049389 | 0.048217 |
| n_s | 0.962 | 0.96605 | 0.9742 |
| sigma_8 | 0.834 | 0.812 | 0.8117 |
| Sum of neutrino masses [eV] | 0 | 0.06 | 0.06 |

The additional `pact2025` bank remains available for earlier comparisons.
It is not a default. Survey geometry, H I modeling and cosmology are recorded
separately: the new cosmology uses the Foreman survey/H I prescription so that
changing cosmology does not silently change the instrument or H I model.

The backend audit corrected derivatives as well as updating the fiducial.
In particular, all-constraints forecasts now include the BAO shift in
distance derivatives. The regenerated Bull banks therefore use Bull's
cosmology and H I profile with corrected numerical code; frozen historical
results retain the source identities under which they were computed.

The corrected growth/bias column labels also matter for our Foreman-configured bank.
In the September 2026 rebuild, the clean-survey BAO significance and median
distance error are unchanged, while the median per-bin uncertainty in
`f*sigma8` at 10,000 hours is 2.79 times the value from the pre-audit bank.
The old growth column represented the bias derivative. Previously generated
growth-error and tolerance tables therefore remain historical artifacts;
new growth claims based on these local artifacts require recomputation with the
corrected bank.

These comparisons are between our pre-audit and rebuilt local banks, not between
our calculations and either author's published results. The audit has not
established errors in Bull's or Foreman's papers, traced the defects to the code
revisions used for publication, or reproduced their exact publication pipelines.
The reference configurations preserve historical fiducials and modeling choices;
their names alone do not certify reproduction of a published result. Updating
the fiducial cosmology is separate from correcting defects in our code.

The bias-response evaluator accepts `planck2018`, `pact2025`, and `cmbspa2026`
and authenticates their parameters, cache and reference metadata. Response banks
are generated separately; for a new current-fiducial response calculation:

```bash
python scripts/build_bank.py --config chime2022 --cosmology cmbspa2026 \
  --epsilon-fg 0 --p-res 1.0 --dense-knee \
  --out data/fisher_bank_chime2022_cmbspa2026_pres_dense.npz
python scripts/bias_tolerance.py \
  --bank data/fisher_bank_chime2022_cmbspa2026_pres_dense.npz \
  --json out/bias_current2026.json
```

The retained response-bank examples that explicitly name `planck2018` are
historical reproductions. A missing or changed 2026 reference fails
authentication; older fiducials can omit their optional empty reference.

## Current fiducial

The selected August 2026 flat ΛCDM combination is the fourth numerical column
of [Omori et al., Table 8](https://arxiv.org/html/2608.31136v1#S7.T8):
combined SPT/ACT/Planck lensing, SPT/ACT/Planck primary CMB, and DESI DR2 BAO.
We use its posterior means: `h=0.6832`, `ombh2=0.022506`, `omch2=0.11755`,
`ns=0.9742`, `sigma_8=0.8117`, with fixed total neutrino mass `0.06 eV`.
These are a reproducible fiducial point, not a new likelihood fit or a joint
maximum-likelihood parameter vector.

Total matter includes massive neutrinos exactly once. Fractional densities
are derived from the physical densities and `h`, with flat closure and
`w0=-1`, `wa=0`. The backend's `N_eff=3.046` numerical convention remains
explicit in the cache; it is not a fitted constraint from Table 8. CAMB's
linear matter spectrum is normalized to the specified `sigma_8`. Its seed
`As` and optical depth are generator settings, not extra posterior inputs.
Background forecast distances retain RadioFisher's low-redshift approximation
without radiation; the CAMB power spectrum includes its radiation treatment.

`RadioFisher.get_cosmology()` owns the new preset. RFIsher uses that factory
and records the paper, table, combination and statistic in bank provenance.
Both projects test the numbers and neutrino-density accounting. Cache metadata
records CAMB settings/version and independently verifies the numerical table.

## Reproduction and rebuilding

`resources.DEFAULT_BANK`, `DEFAULT_BANK_NAME`, and `resources.bank_file()`
all select the current fiducial. Use `PLANCK2018_BANK`, `PLANCK2018_BANK_NAME`,
or `bank_file("planck2018")` for the Foreman reference. Historical dissertation
checks select that reference explicitly; forecast commands use the new default.
The delay-cut sweep also defaults to the current fiducial. When redrawing
previous sweep CSVs with `scripts/run_taucut_sweep.py --figures-only`, pass
the cosmology used to generate them (for the retained historical tables,
`--cosmology planck2018`); those CSVs do not identify their fiducial.

`scripts/rebuild_shipped_banks.sh` rebuilds all five artifacts: three CHIME
banks (current, Foreman, P-ACT) and two Bull foreground cases. It runs physics
and provenance checks before updating test pins. All banks must be rebuilt
after a change to either scientific source manifest; changing hashes alone
does not make an old bank valid. The checked-in release recipe requires clean
scientific source. A development build may record a dirty tree truthfully,
but must hold both source digests fixed throughout computation and pass the
same physics/provenance checks before replacing any packaged artifact.
