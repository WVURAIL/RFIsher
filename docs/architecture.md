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
   manifest.json                              |                       Planck 2018, banks, the no-filter response bank
   (operating_characteristic_v1)              v  sigma(T*) and the bias per unit residual, per parameter and bin
          |                                tolerance/   r_tol = min over required parameters and bins of zeta sigma / |b|
          |                                   v
          |                               tolerances.csv  (the only science input of the verdict)
          v                                   v
       verdict/  handoff.py checks the files; interval.py eta_sci, the deployable set, the selector;
                 screening.py keep / excise / undetermined
   capture_operating_characteristic_v1 --> records/chime_atsc_2026/  the capture ruling of record and its copies
```

Cosmology lives in `forecast/` and `tolerance/`. `verdict/` imports neither
and reads one tolerance file; `records/` holds the code of record of the 2026
campaign, kept runnable and not part of the library's interface.

## Main components

| Package | Role |
|---|---|
| `rfisher.science_model` | the `ScienceModel` protocol a science model satisfies |
| `rfisher.forecast.radiofisher_bao` | the one science model: the RadioFisher BAO adapter (`model.py`), its banks (`bank/`, the whole bank source manifest), the response (`response.py`), the BAO-band coherence gain (`coherence_gain.py`) and the forecast API (`api.py`, `scenarios.py`, `significance.py`) |
| `rfisher.tolerance` | the rule (`rule.py`), its reduction to bands (`bands.py`), the table and its provenance (`table.py`), and the frozen reference tolerances of the capture (`reference.py`) |
| `rfisher.verdict` | the archive verdict: `handoff.py`, `interval.py`, `screening.py`, `archive.py` |
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

The supported RadioFisher backend exposes three experiment-dictionary hooks:

- `noise_freq_weight`: surviving-time weight as a function of frequency;
- `noise_freq_mode`: `invvar` or `fourier` band reduction; and
- `vol_frac`: surviving survey-volume fraction.

A `NaN` weight marks an excised slice. Unknown or missing required
capabilities fail before a masked direct evaluation begins. The hooks are
no-ops when absent, so the unmodified backend result remains the clean
forecast. The `P_res` capability adds the unit-residual response row of the
bias-response banks (see above).

The delay filter has no hook and does not enter the forecast: no
post-processing of the residual is modelled. The tolerance is priced on the
no-filter response bank (`model.SCENARIO_BANKS`); the bank builder still
accepts a mode cut (`--kfg-fac`), which prices lost radial modes and nothing
else. RFIsher owns every *number*, *decision*, and *dataset* behind a
configuration: which field, band, time, and duty cycle define it (the
experiment registry, `rfisher.forecast.radiofisher_bao.bank.experiments`).

For the scenarios represented by the current bank, the masking hooks reduce
to the same effective-time and volume factors used by bank interpolation.
`scripts/verify_bank.py` checks the two paths, including a full-survey
comparison. Direct evaluation is how the model would be extended to a new
dimension of the Fisher integrand; radial-mode coupling from spectral gaps
would be the first.

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
scripts/                bank verification and re-stamping, coverage, and the threshold-calibration bridge
data/                   research comparison banks
docs/                   architecture, the handoff, cosmology entry, tolerance, releases, schemas
docs/releases/          manifests of the immutable release roots
examples/               the minimal forecast and the verdict of a handoff
out/                    ignored scratch; the results tree lives outside (releases.md)
tests/                  package, verdict, record and workflow tests; tests/golden/ the vendored fixtures
```

Generated results, including the immutable release roots, live outside the
repository in the workspace `results/` tree; see the
[release index](releases.md) before changing anything there. Scripts
write their scratch output to the ignored `out/`. Detector kernels, the
characterization and new survey-product generation are the detector side's.
