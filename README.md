# RFIsher

RFIsher determines how much residual digital television (DTV) power each 6 MHz channel can
carry before it biases a 21 cm baryon acoustic oscillation (BAO) measurement by more than
its own uncertainty.

For each channel, RFIsher runs one [RadioFisher](https://github.com/WVURAIL/RadioFisher)
forecast at the channel's own redshift. The forecast uses CHIME as described in the CHIME
Overview, the inter-cylinder baselines that CHIME's analyses use, the specified cosmology,
and one retained year of data. The two fitted BAO dilations give the one number the CHIME
Overview reports, the volume-averaged distance D_V
(`ln α_V = 2/3 ln α⊥ + 1/3 ln α∥`), and the forecast gives its clean uncertainty σ. A
coherent DTV residual of unit strength is then added through RadioFisher's residual hook,
and the forecast returns the bias it causes in D_V. Since the bias is proportional to the
residual's strength `a`, each channel reduces to one *response* (bias ÷ σ per unit
strength) and one *tolerance*:

    a_tol = 1 / |response_dv|

That is, a residual weaker than `a_tol` has a first-order assigned bias below its σ.

The table of these numbers is RFIsher's main output. Since the table does not depend on
the detector's calibration, a new threshold, era, or mask never needs a new table. A new
table is needed only for a new cosmology, telescope, residual model, or retained-time anchor.

The optional [finite BAO-only likelihood check](docs/NONLINEAR_BIAS_CHECK.md)
tests the local bias approximation against an explicitly defined nonlinear
model. Failed fits and numerical checks are recorded with the successful ones, and the
published table is left fixed. The check does not calibrate the physical residual or the
sampling coverage.

![RFIsher call graph](docs/rfisher_functions.svg)

## Use

Start in a new directory with Git and Python 3.10 or newer. These steps need
no telescope data, credentials, GPU, or TeX installation.

```bash
git clone https://github.com/WVURAIL/RFIsher.git
cd RFIsher
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[test]"
```

The install selects the recorded RadioFisher revision. Keep that pin to reproduce the
table, and develop RadioFisher's latest source in another environment. First, read the
shipped table:

```bash
python - <<'PY'
import rfisher
table = rfisher.read_table()
row = next(r for r in table["channels"] if r["channel"] == 19)
print(f"Channel 19: response = {row['response_dv']:.0f}, a_tol = {row['a_tol']:.3g}")
a = 8.4e-8  # example residual strength, for illustration only
bias_over_sigma = a * abs(row["response_dv"])
print(f"First-order bias / sigma = {bias_over_sigma:.3g}")
PY
```

This prints approximately `response = 8344, a_tol = 0.00012` and
`First-order bias / sigma = 0.000701`. Next, rebuild one channel and check it:

```bash
rfisher table --channels 19 --workers 1 --out out/first-run
rfisher figures --table out/first-run/channel_table.json --out out/first-run/figures
python -m pytest tests/test_table.py -q
```

The forecast writes `channel_table.json` and `channel_table.csv`. With `--table`,
the figure command reads this new table, and without it the shipped table.
Lastly, the tests compare the rebuilt channel with the shipped result to the
numerical tolerances given under Tests.

The full calculation is run with:

```bash
rfisher table --out out/all --workers 12
rfisher figures --table out/all/channel_table.json --out out/all/figures
rfisher overview --out out/overview --workers 12
```

`--workers` sets the number of processes. [The paper/code contract](docs/PAPER_CODE_MAP.md)
traces each quantity to its code, and PilotProxy's
[first-run walkthrough](https://github.com/WVURAIL/pilotproxy/blob/main/docs/FIRST_RUN.md)
continues from this response table to the paper's conditional thresholds.

## The CHIME Overview forecast

`rfisher overview` reproduces the CHIME Overview forecast as its scripts compute it.
RadioFisher's own `fisher()` is called for each redshift bin, with A, bσ8, fσ8, and the two
dilations free in each bin and the damping variance `s_NL` shared by all bins. The dilations
then give D_V. On the Overview's 15 bins, the clean one-year errors of 0.47% to
1.03% are reproduced to 0.0003 percentage points. The same forecast with 6 MHz bins over the
DTV range gives 1.18% to 1.52% per channel. Each 6 MHz bin is about a quarter as deep, so its
error is about twice as large.

The reproduction counts every baseline (RadioFisher's as-built density), as the Overview's
forecast does, so it matches the published numbers. Only the inter-cylinder baselines
are used for the tolerance table. CHIME's analyses drop the intra-cylinder pairs, which
carry noise cross-talk and a strong response to diffuse Galactic emission (CHIME
Collaboration 2025, arXiv:2511.19620), and the stack-to-proxy amplitude ratio used with the
table is measured between cylinders. Without the intra-cylinder baselines, the table's clean
σ(D_V) is 17% to 34% larger than on all baselines. On all baselines, the table agrees with
the reproduction to 1.5% on every channel. The table integrates more finely than the
reproduction and fits `s_NL` per channel.

![The CHIME Overview forecast as published, and with 6 MHz bins over the DTV range](docs/figures/overview_reference.png)

The forecast inputs have two cosmologies. For the table, the specified cosmology
`cmbspa2026` is used (SPT-3G, ACT, and Planck CMB with DESI DR2 BAO, from Omori et al. 2026,
arXiv:2608.31136v1, Table 8). For the reproduction, the Overview's Planck 2018 is used, so
that the reproduction can be checked against the published forecast. Only the cosmological
parameters and the P(k) table change between the two, and the HI models, damping scale, and
CHIME are the Overview's in both. In the specified cosmology, the 6 MHz errors are 7% to 8%
smaller (1.09% to 1.40% per channel).

```bash
rfisher overview --out out/overview --cosmology planck2018 --compare cmbspa2026
```

![The 6 MHz forecast in Planck 2018 and in the specified cosmology](docs/figures/overview_cosmology.png)

## The residual strength

The detector maps the retained shelf proxy to the table's strength with

    a = (gamma x_hi)^2 N G

where `x_hi` is the upper end of the retained per-input shelf proxy, `gamma` is the measured,
calibrated redundant-stack amplitude divided by the archive proxy, `N = 16384` is the frame
length, and `G` is an assumed effective temporal gain for an unmeasured cross-moment. `gamma`
is an amplitude ratio, and no intrinsic coherent fraction is inferred from it.
No coherence time or cross-day bound has been measured, so `G` is assumed.

To first order, the ratio of bias to σ is `a * abs(response_dv)`. Since the fitted dilation is
`alpha_V = D_V_fid / D_V`, the signed distance shift is
`delta ln D_V / sigma_dv = -a * response_dv`. The table field `bias_dv_per_unit_a`
(schema v2) stores the `ln(alpha_V)` projection, which has the opposite sign.

The table is normalized to 8760 retained hours. For the paper's primary calendar time,
the Overview's ideal year is assumed, so retaining a fraction `kappa` of the data
requires `1 / kappa` years for this reference exposure. An operating-duty penalty is
treated as an additional scenario. A forecast for a fixed calendar duration of `Y` years
uses `ttot = 8760 * Y * kappa` hours and must be recomputed at that exposure.

The threshold rule is in PilotProxy. Its finite-amplitude and channel-specific
transfer budgets are external inputs to the rule, and `a_tol` holds none of them.
`nonlinear.py` and the validation tools check the expected-likelihood model. These
checks do not cover the physical transfer or the cross-day DTV covariance (see
[the paper/code contract](docs/PAPER_CODE_MAP.md)).

## The model

The fixed forecast inputs are set in `inputs.py`. The cosmology is the specified
`cmbspa2026` (SPT-3G, ACT, and Planck CMB with DESI DR2 BAO), and its linear P(k) table is
checked against the cosmology before use. CHIME is modeled as in the CHIME Overview, with
4 cylinders × 256 feeds, T_sys = 55 K, 31000 deg², and 0.39 MHz channels. Only the
inter-cylinder baselines are used, and their density is built from the array layout (`baselines.py`,
`data/nx_CHIME_inter.dat`). Built from all pairs, the same code reproduces RadioFisher's
as-built density exactly. The exposure is 8760 h of retained data.

The fit (`tolerance.py`) has six free parameters: A, s_NL = σ_NL², α⊥, α∥, fσ8, and bσ8.
The rest are held at the fiducial. As in the CHIME Overview, the dilations give D_V, and the
first-order bias is compared with the clean σ of D_V. Where the biases of the two dilations
have opposite signs, they partly cancel in D_V. The response changes sign between channels
31 and 32, so the tolerances of those two channels are the loosest. The matrix coordinate
`s_NL` is the damping variance in Mpc squared, and the configuration value `sigma_nl` is the
damping length in Mpc.

The residual (`residual.py`) is an assumed flat 6 MHz template of residual power. This
template puts the same visibility on every baseline that measures a Fourier cell, and its
support is the horizon wedge. No wedge modes are excised, and no delay filter is applied.
Relative to the noise power, the residual is
`dP / C_N = a × N_ν × N_meas(k⊥) × f_w(k⊥)` for `|k∥| ≤ m k⊥ + π/L` and zero elsewhere.

The quadrature (`forecast.py`) is Gauss–Legendre in k and μ, split at every kink of the
integrand. Evaluation is batched by radial segment, which keeps the k-dependent angular
boundaries of each segment and bounds the memory use. The same node generator is used by
the finite check. Doubling either order changes the tolerance by less than 3 × 10⁻⁷.

## The table

The table has 24 channels, all in the specified cosmology. These are the DTV allocations
14 to 36 and channel 37, which carries no DTV and is the control. σ is the clean one-year
uncertainty of D_V in percent, and the response is signed.

| Channel | MHz | z | σ(D_V)/D_V (%) | Response | a_tol | |
|---|---|---|---|---|---|---|
| 14 | 470–476 | 2.003 | 1.63 | +2,947 | 3.39e-04 | [plate](docs/figures/channel_14.png) |
| 15 | 476–482 | 1.965 | 1.65 | +3,625 | 2.76e-04 | [plate](docs/figures/channel_15.png) |
| 16 | 482–488 | 1.929 | 1.66 | +4,232 | 2.36e-04 | [plate](docs/figures/channel_16.png) |
| 17 | 488–494 | 1.893 | 1.65 | +5,045 | 1.98e-04 | [plate](docs/figures/channel_17.png) |
| 18 | 494–500 | 1.858 | 1.62 | +6,371 | 1.57e-04 | [plate](docs/figures/channel_18.png) |
| 19 | 500–506 | 1.824 | 1.58 | +8,344 | 1.20e-04 | [plate](docs/figures/channel_19.png) |
| 20 | 506–512 | 1.791 | 1.55 | +10,810 | 9.25e-05 | [plate](docs/figures/channel_20.png) |
| 21 | 512–518 | 1.758 | 1.52 | +13,445 | 7.44e-05 | [plate](docs/figures/channel_21.png) |
| 22 | 518–524 | 1.726 | 1.50 | +15,850 | 6.31e-05 | [plate](docs/figures/channel_22.png) |
| 23 | 524–530 | 1.695 | 1.48 | +17,700 | 5.65e-05 | [plate](docs/figures/channel_23.png) |
| 24 | 530–536 | 1.665 | 1.47 | +18,602 | 5.38e-05 | [plate](docs/figures/channel_24.png) |
| 25 | 536–542 | 1.635 | 1.46 | +18,375 | 5.44e-05 | [plate](docs/figures/channel_25.png) |
| 26 | 542–548 | 1.606 | 1.46 | +16,976 | 5.89e-05 | [plate](docs/figures/channel_26.png) |
| 27 | 548–554 | 1.578 | 1.45 | +14,569 | 6.86e-05 | [plate](docs/figures/channel_27.png) |
| 28 | 554–560 | 1.550 | 1.44 | +11,502 | 8.69e-05 | [plate](docs/figures/channel_28.png) |
| 29 | 560–566 | 1.523 | 1.43 | +8,141 | 1.23e-04 | [plate](docs/figures/channel_29.png) |
| 30 | 566–572 | 1.496 | 1.43 | +4,739 | 2.11e-04 | [plate](docs/figures/channel_30.png) |
| 31 | 572–578 | 1.470 | 1.44 | +1,433 | 6.98e-04 | [plate](docs/figures/channel_31.png) |
| 32 | 578–584 | 1.445 | 1.45 | -1,609 | 6.22e-04 | [plate](docs/figures/channel_32.png) |
| 33 | 584–590 | 1.420 | 1.47 | -4,207 | 2.38e-04 | [plate](docs/figures/channel_33.png) |
| 34 | 590–596 | 1.395 | 1.48 | -6,339 | 1.58e-04 | [plate](docs/figures/channel_34.png) |
| 35 | 596–602 | 1.371 | 1.48 | -8,315 | 1.20e-04 | [plate](docs/figures/channel_35.png) |
| 36 | 602–608 | 1.348 | 1.47 | -10,621 | 9.42e-05 | [plate](docs/figures/channel_36.png) |
| 37 (control) | 608–614 | 1.325 | 1.47 | -13,364 | 7.48e-05 | [plate](docs/figures/channel_37.png) |

![Summary](docs/figures/summary.png)

Each plate shows the residual in Fourier space at the tolerated strength and the bias of
D_V against the residual's strength. Since the `docs/figures/` gallery is checked in, every
channel can be inspected without installing the software. No calculation reads these
images. The channel gallery is regenerated with `rfisher figures --out docs/figures`, and
the two Overview plots with
`rfisher overview --out docs/figures --cosmology planck2018 --compare cmbspa2026`.
Exploratory figures go in `out/`.

## Files

| File | Contents |
|---|---|
| `src/rfisher/bands.py` | the channels and their redshifts |
| `src/rfisher/inputs.py`, `pk_cache.py` | the fixed forecast inputs and the P(k) table check |
| `src/rfisher/baselines.py`, `data/nx_CHIME_inter.dat` | the inter-cylinder baseline density, built from the array layout |
| `src/rfisher/residual.py` | the coherent DTV residual |
| `src/rfisher/forecast.py` | one channel's Fisher matrix with the residual's bias row |
| `src/rfisher/tolerance.py` | σ and bias of D_V, response and tolerance |
| `src/rfisher/overview.py` | the CHIME Overview forecast, reproduced, and in 6 MHz channels |
| `src/rfisher/table.py`, `figures.py`, `cli.py` | the table, the figures, the command line |
| `src/rfisher/data/channel_table.json`, `.csv` | the shipped table, with provenance |
| `tools/generate_call_graph.py` | draws the call graph above |

## Tests

```bash
python -m pip install -e ".[test]"
python -m pytest -q
```

One test rebuilds channel 19 and compares it with the shipped table, σ to 1e-5 and the
responses to 1e-4 of the larger dilation response. Other numpy and scipy builds change the
result by a few parts in a million, and the partial cancellation in D_V magnifies this
change. CI also rebuilds channels 14, 29, and 37 with RadioFisher at the pinned commit.

## Figure colors

Plots and diagrams use the WVU colors of the
[Beamer template](https://github.com/WVURAIL/wvu_beamer_template), and
`src/rfisher/wvu_palette.py` is a standalone copy, updated with the template's
`tools/export_plot_palette.py`. Blue is used for measurements, and old gold gives contrast
for model curves and small labels. Further series use the WVU accents, with their own
markers or line styles where needed, and grayscale masks keep their binary meaning. A
journal's figure requirements take precedence over this palette. The palette has no effect
on the calculations or the shipped table.
