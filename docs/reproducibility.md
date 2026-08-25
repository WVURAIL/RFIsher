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

The two installed CHIME banks and packaged masking table work without a
RadioFisher checkout:

```bash
python examples/minimal_example.py
rfisher-forecast --uniform 0.25
rfisher-forecast --cosmology pact2025 --uniform 0.25
```

Matter-power caches are also packaged. Install the optional CAMB dependency
only when generating or refreshing a cache:

```bash
python -m pip install -e ".[pk]"
```

## RadioFisher checkout

RadioFisher is required for bank construction and direct backend validation.
Use the reviewed branch recorded by the released banks:

```bash
git clone https://github.com/WVURAIL/RadioFisher ../RadioFisher
git -C ../RadioFisher checkout pilot-proxy
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
python scripts/check_paper_numbers.py
python scripts/restamp_bank_pins.py --check
```

`scripts/verify_bank.py` covers interpolation, physics checks, and agreement
between bank evaluation and direct RadioFisher calls. The paper-number gate
regenerates every quoted value from the tracked output tables.

On a WSL checkout, use a Linux temporary directory if the test runner's
default temporary path is on a mounted Windows filesystem:

```bash
TMPDIR=/tmp python -m pytest tests/ -q
```

## Product-dependent work

Point the product registry at the corrected archived survey products:

```bash
export RFISHER_PRODUCT_DIRS=~/rail/datasets/canfar_archive_per_pilot
```

The archived and current pilot-proxy products can share filename patterns
while using different schemas. Confirm the intended product set before a
threshold, coherence, or dissertation calculation.

## Rebuild the shipped banks

The supported entry point displays the strict bank-builder surface:

```bash
rfisher-build-bank --help
```

The canonical four-bank recipe is:

```bash
NPROC=24 RADIOFISHER_DIR=../RadioFisher \
  bash scripts/rebuild_shipped_banks.sh /tmp/rfisher-bank-rebuild
```

It produces:

- the installed Planck-2018 CHIME bank;
- the installed P-ACT-LB CHIME bank;
- the Bull-2015 Planck-2013 `epsilon_fg = 1e-6` comparison bank; and
- the matched Bull-2015 `epsilon_fg = 1e-5` comparison bank.

The schema-v2 banks preserve their recorded compatibility source paths. The
recipe updates the corresponding test hashes, regenerates
`out/foreground_sensitivity.csv`, and runs the paper-number gate.

Run a bank build only from clean, committed RFIsher and RadioFisher trees. Do
not edit package source or packaging metadata during a build. A source-tree
change must result in a new recorded identity rather than a restamped old
calculation.

The Bull banks retain their released 27-point logarithmic grid over
1--1,000,000 hours plus the exact `10**3.5`-hour point needed by the 3,300-hour
interpolation check.

## Masking-cost outputs

```bash
python scripts/run_forecast.py
python scripts/fg_sensitivity.py
```

The main driver regenerates the reference figures, CSV tables, and
`out/results.md`. Interpretation and input limitations are documented in
[chime-bao-application.md](chime-bao-application.md).

## Dissertation number gate

Run the gate against a LaTeX checkout and the matching pilot-proxy summary:

```bash
python scripts/check_dissertation_numbers.py \
  --tex /path/to/dissertation \
  --summary-json /path/to/pilot-proxy/data/provenance/dissertation_summary_v3.json
```

A text extraction can provide an advisory check, but the LaTeX source is
authoritative because extracted table cells can be reordered. Gate failures
name the expected source table and rounding convention. `--baseline <file>`
can be used as a temporary ratchet while an existing failure list is reduced.

## Optional bias-response banks

The large `_Pres` banks are local research prerequisites and are not installed
or committed. Build the four matched banks before running the associated
workflows:

```bash
python scripts/build_bank.py --config chime2022 --cosmology planck2018 \
  --epsilon-fg 0 --p-res 1.0 --dense-knee \
  --out data/fisher_bank_chime2022_pres_dense.npz
python scripts/build_bank.py --config chime2022 --cosmology planck2018 \
  --epsilon-fg 0 --p-res 1.0 --kfg-fac 22 --dense-knee \
  --out data/fisher_bank_chime2022_pres_kfg22_dense.npz
python scripts/build_bank.py --config chime2022 --cosmology planck2018 \
  --epsilon-fg 0 --p-res 1.0 --kfg-fac 44 --dense-knee \
  --out data/fisher_bank_chime2022_pres_kfg44_dense.npz
python scripts/build_bank.py --config chime2022 --cosmology planck2018 \
  --epsilon-fg 0 --p-res 1.0 --kfg-fac 80 --dense-knee \
  --out data/fisher_bank_chime2022_pres_kfg80_dense.npz

python scripts/bias_tolerance.py --zeta 1.0
python scripts/plot_convergence.py --out out/
python scripts/three_worlds.py
```

These workflows require strict-v2 `bias_response` artifacts with the CHIME
Overview profile, Planck-2018, and unit normalization `P_res = 1.0`.

## Forecast-completion evidence

The complete estimator, time-scaling families, refusal ledger, and exact
three-point evidence-bank commands are documented in
[forecast-completion.md](forecast-completion.md). After producing the four
all-bin evidence ledgers, rebuild the comparison and rendered assets with:

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
