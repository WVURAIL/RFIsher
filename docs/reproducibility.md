# Reproducibility

This page collects the commands needed to install RFIsher, verify the shipped
banks and result tables, rebuild supported banks, and regenerate the current
evidence products. The immutable release roots are indexed separately in
[releases.md](releases.md).

## Install

```bash
git clone https://github.com/WVURAIL/RFIsher
cd RFIsher
python -m pip install -e ".[test]"
```

The three installed CHIME banks and packaged masking table work without a
RadioFisher checkout:

```bash
python examples/minimal_example.py
rfisher forecast --uniform 0.25
rfisher forecast --cosmology pact2025 --uniform 0.25
rfisher forecast --cosmology planck2018 --uniform 0.25
rfisher tolerance show
```

Matter-power caches are also packaged. Install the optional CAMB dependency
only when generating or refreshing a cache:

```bash
python -m pip install -e ".[pk]"
```

The default is `cmbspa2026`; `planck2018` reproduces Foreman's reference.
Bull's `planck2013` banks use their separate `bull2015` configuration.
See [cosmologies](cosmologies.md) for the parameter source and model conventions.

## RadioFisher checkout

RadioFisher is required for bank construction and direct backend validation.
Use the reviewed commit recorded by the released banks:

```bash
git clone https://github.com/WVURAIL/RadioFisher ../RadioFisher
git -C ../RadioFisher checkout 12a1616637dd46638055f2d6d77788c7214914b2
export RADIOFISHER_DIR=../RadioFisher
```

The sibling checkout is discovered automatically, but setting
`RADIOFISHER_DIR` makes the intended source explicit. Backend binding rejects
a calculation that mixes code from one checkout with configuration data from
another.

## Standard verification

```bash
python -m pytest tests/ -q
python scripts/verify_bank.py
python scripts/restamp_bank_provenance.py --check
rfisher tolerance build --project projects/chime_bao --out /tmp/tolerances
cmp src/rfisher/data/tolerances/filter_scenarios_T1yr.csv /tmp/tolerances/filter_scenarios_T1yr.csv
```

`scripts/verify_bank.py` covers interpolation, physics checks, and agreement
between bank evaluation and direct RadioFisher calls. The provenance check
confirms that every bank records the current digest of the bank subpackage
and matches its pin. The last two lines rebuild the tolerance table from the
four packaged response banks; it must match the committed bytes.

Byte-for-byte reproduction of the frozen forecast-completion figures uses the
renderer recorded in the PNG metadata:

```bash
python -m pip install -e ".[test]" -c requirements/render.txt
```

Other supported Matplotlib versions can render current figures, but are not
expected to reproduce version-dependent compressed image bytes.

On a WSL checkout, use a Linux temporary directory if the test runner's
default temporary path is on a mounted Windows filesystem:

```bash
TMPDIR=/tmp python -m pytest tests/ -q
```

## Detector outputs

RFIsher reads no survey product. pilot-proxy characterizes each band of an
archive run into a directory (`manifest.json`, `oc_table.csv`,
`oc_summary.csv`, schema `operating_characteristic` v1, with its `tables/`,
`channels/` and `ledger/`), and the capture campaign's measurements enter as a
capture handoff (`manifest.json`, schema `capture_handoff_measurements` v0).
Their readers check every file's sha256 against the manifest, the columns
against the schema, and the reference residual and band edges against the
science profile, and refuse a mismatch.

The shipped tables, evidence ledgers and release roots live in the results
tree outside the repository (see [releases.md](releases.md)); point the
release regression tests at it, or they skip:

```bash
export RFISHER_OUT=~/rail/results/forecasts/rfisher_out_c1302f4
```

## Rebuild the shipped banks

The supported entry point displays the strict bank-builder surface:

```bash
rfisher build-bank --help
```

The canonical five-bank recipe is:

```bash
NPROC=24 RADIOFISHER_DIR=../RadioFisher \
  bash scripts/rebuild_shipped_banks.sh /tmp/rfisher-bank-rebuild
```

It produces:

- the installed Planck-2018 CHIME bank;
- the installed P-ACT-LB CHIME bank;
- the installed CMBSPA2026 CHIME bank;
- the Bull-2015 Planck-2013 `epsilon_fg = 1e-6` comparison bank; and
- the matched Bull-2015 `epsilon_fg = 1e-5` comparison bank.

The recipe requires every numerical member of a rebuilt bank to equal the
committed bank's byte for byte (`scripts/restamp_bank_provenance.py
--same-arrays`), verifies the rebuilt banks, and updates their test hashes
with `scripts/restamp_bank_provenance.py --repin` followed by the five bank
paths. The four packaged response banks are never rebuilt by it: they take
the metadata re-stamp (`restamp_bank_provenance.py --subset` with their four
`BANK=OUT` pairs), committed before the recipe runs, so that its closing
`--check` covers all nine banks.

Run a bank build only from clean, committed RFIsher and RadioFisher trees. Do
not edit the bank subpackage during a build. A bank records the digest of
`src/rfisher/forecast/radiofisher_bao/bank/`, and nothing outside it enters
that digest.

The nine banks were re-stamped once, when the bank code moved into that
subpackage: `scripts/restamp_bank_provenance.py` rewrote only their
`meta.npy` members, recording the new source digest and, in a `restamp`
block, the commit and digest that built them. Their arrays are the ones that
build computed.

The Bull banks retain their released 27-point logarithmic grid over
1--1,000,000 hours plus the exact `10**3.5`-hour point needed by the 3,300-hour
interpolation check.

## Masking-cost outputs

```bash
python scripts/run_forecast.py
```

The main driver regenerates the reference figures, CSV tables, and
`out/results.md`. Interpretation and input limitations are documented in
[chime-bao-application.md](chime-bao-application.md).

## Response banks and the tolerance table

The four filter-scenario response banks (`_Pres` banks) are packaged in
`src/rfisher/data/response_banks/`. They were built with:

```bash
rfisher build-bank --config chime2022 --cosmology planck2018 \
  --epsilon-fg 0 --p-res 1.0 --dense-knee \
  --out fisher_bank_chime2022_pres_dense.npz
rfisher build-bank --config chime2022 --cosmology planck2018 \
  --epsilon-fg 0 --p-res 1.0 --kfg-fac 22 --dense-knee \
  --out fisher_bank_chime2022_pres_kfg22_dense.npz
rfisher build-bank --config chime2022 --cosmology planck2018 \
  --epsilon-fg 0 --p-res 1.0 --kfg-fac 44 --dense-knee \
  --out fisher_bank_chime2022_pres_kfg44_dense.npz
rfisher build-bank --config chime2022 --cosmology planck2018 \
  --epsilon-fg 0 --p-res 1.0 --kfg-fac 80 --dense-knee \
  --out fisher_bank_chime2022_pres_kfg80_dense.npz
```

These are strict-v2 `bias_response` artifacts with the CHIME Overview
profile, Planck-2018, and unit normalization `P_res = 1.0`. The per-bin
tolerance table `src/rfisher/data/tolerances/filter_scenarios_T1yr.csv` is
computed from them by

```bash
rfisher tolerance build --project projects/chime_bao --out DIR
rfisher tolerance bands --project projects/chime_bao --bands BANDS.csv --out DIR
rfisher tolerance bias --zeta 1.0
```

`build` refuses to change the bytes of an existing table unless it is given
`--accept-new`. `bands` reduces the table to one tolerance per band and
scenario for the bands listed in `BANDS.csv` (columns `band_id`, `low_mhz`,
`high_mhz`). It prices only screened bands: a `role` column, when present,
must read `screened` on every row, and the caller passes only the screened
bands of the frequency plan. Before it reads the table, `bands` recomputes every digest the
table's provenance records that needs no bank opened (the tolerance and model
code, the profile, the science register, the bank subpackage and the bytes of
the response banks) and refuses the table if any has changed; `rfisher
tolerance show --project projects/chime_bao` does the same, and the archive
reads the table only through that check. `bias` prints the full response report of one bank. Build
replacement banks in a staging directory, and authenticate them with
`rfisher.forecast.radiofisher_bao.response.load_response_bank` before they
replace the packaged ones. A changed source digest requires a new
calculation, not new metadata on old matrices.

### Archive verdict and release layouts

Given a characterization directory `CHAR` written by pilot-proxy, price its
bands and screen them:

```bash
rfisher tolerance bands --project projects/chime_bao --bands CHAR/manifest.json --out TOL
rfisher verdict archive --project projects/chime_bao --characterization CHAR \
  --tolerances TOL --out SCIENCE
```

`verdict.csv` holds each family's deployable set and the band's union,
`verdict_points.csv` the rule scenario's priced candidates, `screen.csv` the
screen's step and outcome, `sensitivity.csv` the named sensitivities, and
`manifest.json` the sha256 of every file read and the producer's identity.

The two frozen archive releases are written in their own layouts from the same
inputs:

```bash
rfisher records archive-layout --release archive_author_eras_2026_09_23 \
  --characterization CHAR --tolerances TOL --project projects/chime_bao --out RELEASE
```

(`archive_no_split_2026_09_24_r2` for the release without the variance split.)
A band whose selection finds a feasible point is refused, because its
evaluation-block replay is the detector's and the handoff does not carry it.

### Capture ruling of record

From a capture handoff `HANDOFF` (the detector's measurement tables of the
2026 matched capture), the table of record before amendment 8 and the table of
record itself:

```bash
rfisher records table-of-record --handoff HANDOFF --out table_of_record_v7.csv
rfisher records capture-ruling --rule record --input table_of_record_v7.csv \
  --handoff HANDOFF --out table_of_record.csv --ch33-rescan
```

and the release of record r5.2, its credit readings included:

```bash
rfisher records capture-release --rule r5_2 --handoff HANDOFF \
  --record-table table_of_record.csv --evidence DECISION_EVIDENCE \
  --releases RESULTS --duration-reference SURVEY_DURATION_RUN --rel REL --run RUN
```

The rule files are `projects/chime_bao/capture_rules/` (`record`, `a18`, `r5`,
`r5_1`, `r5_2`, and the sensitivities `g1`, `r3` and `r2`). Under numpy 2.3 or
later every file equals the frozen release byte for byte. `records
cohort-basis`, `robustness`, `phase-limit`, `duration` and `postprocessing` run
the release's copies one at a time; each prints its usage on `--help`.

## Forecast-completion evidence

The complete estimator, time-scaling families, refusal ledger, and exact
three-point evidence-bank commands are documented in
[forecast-completion.md](forecast-completion.md). After producing the four
all-bin evidence ledgers, rebuild the comparison and rendered assets with
(the commands write to the repository's ignored `out/`; the shipped ledgers
are in the results tree):

```bash
PYTHONPATH=src python3 scripts/forecast_template_comparison.py \
  --evidence noise_shaped=out/forecast_completion_all_dtv_bins.json \
  --evidence low_kparallel=out/forecast_completion_all_dtv_bins_low_kparallel.json \
  --evidence wedge_like=out/forecast_completion_all_dtv_bins_wedge_like.json \
  --evidence k_shell_localized=out/forecast_completion_all_dtv_bins_k_shell_localized.json
PYTHONPATH=src python3 scripts/render_forecast_template_assets.py
```

For the dated reconciliation release, keep each evidence JSON beside its
comparison CSV. The renderer resolves evidence basenames relative to that CSV.
Its four small response banks stay local under the ignored `banks/` directory
and are not release artifacts. Pass `--preserve-release-metadata` only when
reproducing the immutable release PDF byte for byte.

The dated release uses `epsilon_fg = 0` for every scalar and named-template
bank. Omit `--dense-knee` for its three-time banks. Omit `--kfg-fac` when the
intended recorded value is `null`; zero is a distinct setting. Keep the scalar
baseline as `--p-res 1.0`, because changing it to a named template changes the
provenance classification.

## Deterministic dissertation figures

```bash
SOURCE_DATE_EPOCH=1786492800 FORCE_SOURCE_DATE=1 \
  python scripts/dissertation/figures.py --out /tmp/rfisher-figures
```

The PDF subset tags and metadata are stabilized so repeated rendering from
the same inputs is byte-identical. The forecast-template renderer additionally
checks the declared embedded font inventory.

## Source and artifact identity

Each strict-v2 bank records RFIsher and RadioFisher source manifests, working-
tree digests, commits, cache hashes, cosmology, experiment settings, baseline,
and artifact kind. Source text is normalized to LF for hashing.

Generated outputs, tests, prose documentation, and paper text are outside the
bank's scientific source digest. Some frozen evidence manifests additionally
record exact generator-script hashes; changing one of those scripts requires
a new release rather than rewriting an existing manifest.

Preserve LF endings for scripts and committed CSV files. Stage new dissertation
files before regenerating its repository manifest because that boundary is
defined by tracked paths.
