# Architecture and scope

RFIsher is the science side of the detector/science split: it turns a
cosmological forecast into a tolerance on a residual, and the detector's
operating characteristic into a verdict per band. The detector side is
[pilot-proxy](https://github.com/WVURAIL/pilot-proxy); what crosses between
them, and the reading path through each, are in [HANDOFF.md](HANDOFF.md) here
and in `docs/HANDOFF.md` there.

## Data flow

```text
 pilot-proxy handoff (files only)          RFIsher
   oc_table.csv, oc_summary.csv,           forecast/radiofisher_bao  the science model: RadioFisher, chime2022,
   manifest.json                              |                       Planck 2018, banks, delay-filter scenarios
   (operating_characteristic_v1)              v  sigma(T*) and the bias per unit residual, per parameter and bin
          |                                tolerance/   r_tol = min over required parameters and bins of zeta sigma / |b|
          |                                   v
          |                               tolerances.csv  (the only science input of the verdict)
          v                                   v
       verdict/  handoff.py checks the files; interval.py eta_sci, the deployable set, the selector;
                 screening.py keep / excise / undetermined; sensitivity.py the post-processing readings
   capture_operating_characteristic_v1 --> records/chime_atsc_2026/  the capture ruling of record and its copies
```

Cosmology lives in `forecast/` and `tolerance/`. `verdict/` imports neither
and reads one tolerance file; `records/` holds the code of record of the 2026
campaign, kept runnable and not part of the library's interface.

## Main components

| Package | Role |
|---|---|
| `rfisher.science_model` | the `ScienceModel` protocol a science model satisfies |
| `rfisher.forecast.radiofisher_bao` | the one science model: the RadioFisher BAO adapter (`model.py`), its banks (`bank/`, the whole bank source manifest), the response (`response.py`), the delay-filter scenarios (`filter_scenarios.py`), the BAO-band coherence gain (`coherence_gain.py`) and the forecast API (`api.py`, `scenarios.py`, `significance.py`) |
| `rfisher.tolerance` | the rule (`rule.py`), its reduction to bands (`bands.py`), the table and its provenance (`table.py`), and the frozen reference tolerances of the capture (`reference.py`) |
| `rfisher.verdict` | the archive verdict: `handoff.py`, `interval.py`, `screening.py`, `sensitivity.py`, `archive.py` |
| `rfisher.response` | the linear response of the masked visibility (`visibility.py`, byte-pinned) and its validation |
| `rfisher.records.chime_atsc_2026` | the capture ruling of record, its copies, the capture release r5.2, the cadence report's table of record section, and the writers of the frozen archive layouts |
| `rfisher.policy` | the side-checked loader of the two project registers |
| `rfisher.cli` | `rfisher forecast`, `build-bank`, `tolerance`, `verdict`, `response`, `records` |

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

The supported RadioFisher backend exposes five experiment-dictionary hooks:

- `noise_freq_weight`: surviving-time weight as a function of frequency;
- `noise_freq_mode`: `invvar` or `fourier` band reduction;
- `vol_frac`: surviving survey-volume fraction;
- `kpar_min_fn`: callable of redshift giving the smallest retained
  `|k_par|` in Mpc^-1, a hard line-of-sight excision applied beside the
  backend's own foreground, wedge, and non-linear cuts; and
- `kpar_transfer_fn`: callable of `(|k_par|, z)` giving the surviving
  signal-power fraction in `[0, 1]`, a soft version of the same cut.

A `NaN` weight marks an excised slice. Unknown or missing required
capabilities fail before a masked direct evaluation begins. The hooks are
no-ops when absent, so the unmodified backend result remains the clean
forecast.

The division of labour behind these hooks is fixed. The backend owns a
*dimension of the Fisher integrand*, expressed in quantities it already
uses: `radiofisher.delay_cut_kpar_min` and `delay_transfer_fn` map a
delay to `k_par` through `nu_line` and `H(z)` and know nothing about any
instrument. RFIsher owns every *number*, *decision*, and *dataset* that
fills that dimension in: which field, band, time, and duty cycle define a
configuration (the experiment registry,
`rfisher.forecast.radiofisher_bao.bank.experiments`), what a published
analysis's cut was, and the digitised filter response the soft cut reads
(`src/rfisher/data/chime2025_fig10_filter_residual.csv`, via
`rfisher.forecast.radiofisher_bao.filter_scenarios.delay_transfer`). The
hooks are forecast options, off by default; the shipped banks do not carry
them, and the sweep driver `scripts/run_taucut_sweep.py@2d682c1` was removed in 4.0.0.

The wedge-limited scenario (the foreground wedge, not the canceller, sets
the cut on long baselines) needs no new hook: it is the hard cut beside the
backend's existing horizon wedge, `expt['wedge'] = 'horizon'` (Seo &
Hirata 2016, the region `c tau <= |b|`), whose boundary is the horizon
delay `b/c` of a baseline mapped through the same delay-to-`k_par`
relation the cut uses. The decision to run it, and for which
configurations, lives in the driver (`WEDGE_CUT_CONFIGS`; `cut = "wedge"`
in the tables).

For the scenarios represented by the current bank, the masking hooks reduce
to the same effective-time and volume factors used by bank interpolation.
`scripts/verify_bank.py` checks the two paths, including a full-survey
comparison. Direct evaluation is how the model is extended to a new
dimension; the delay cut is the first such extension, and radial-mode
coupling from spectral gaps would be the next.

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
src/rfisher/            the package and its data (banks, P(k) caches, tolerances/, schemas/, response_banks/)
projects/chime_bao/     the science profile: science_model.yaml, the two registers, capture_rules/
scripts/                bank verification and re-stamping, coverage, the forecast-template and validation scripts
data/                   research comparison banks
docs/                   architecture, the handoff, cosmology entry, tolerance, releases, schemas
docs/releases/          manifests of the immutable release roots
examples/               the minimal forecast and the verdict of a handoff
out/                    ignored scratch; the results tree lives outside (releases.md)
tests/                  package, verdict, record and workflow tests; tests/golden/ the vendored fixtures
```

Generated results, including the immutable release roots, live outside the
repository in the results tree that `rfisher.records.results_tree` resolves;
see the [release index](releases.md) before changing anything there. Scripts
write their scratch output to the ignored `out/`. Detector kernels, the
characterization and new survey-product generation are the detector side's.
