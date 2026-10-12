# RFIsher

How much residual DTV power each 6 MHz channel can carry before it biases a 21 cm BAO
measurement by more than its own uncertainty.

For each channel, RFIsher runs one [RadioFisher](https://github.com/WVURAIL/RadioFisher)
forecast at the channel's own redshift, with CHIME as in the CHIME Overview and one
retained year of data. The forecast gives the clean uncertainty σ of the two BAO
dilations, α⊥ and α∥. A coherent DTV residual of unit strength is added through
RadioFisher's residual hook, and the forecast returns the bias it causes in each
dilation. Bias is proportional to the residual's strength `a`, so each channel reduces
to one number per dilation, its **response** (bias ÷ σ per unit strength), and one
**tolerance**:

    a_tol = 1 / max(|response_aperp|, |response_apar|)

A residual weaker than `a_tol` biases both dilations by less than their σ.

The table of these numbers is RFIsher's only output. It does not depend on the
detector's calibration: a new threshold, era or mask never needs a new table. Only a
new cosmology, telescope, residual model or retained-time anchor does.

![RFIsher call graph](docs/rfisher_functions.svg)

## Use

```bash
python -m pip install -e .            # installs RadioFisher at the pinned commit
rfisher table --out out/              # all 24 channels, about a minute on 12 cores
rfisher figures --out out/figures     # the summary and one plate per channel
```

```python
import rfisher
table = rfisher.read_table()          # the shipped table
row = next(r for r in table["channels"] if r["channel"] == 19)
a = 8.4e-8                            # residual strength at a threshold (detector side)
bias_over_sigma = a * max(abs(row["response_aperp"]), abs(row["response_apar"]))
```

## How the detector side uses the table

For each candidate threshold, the archive histogram gives the DTV power `x` left in the
kept frames (relative to the noise on one input) and the kept fraction κ. Then:

1. The residual strength is `a = (c x)² × 16,384 × G`. Here `c` is the coherent fraction
   of the power, 16,384 the samples in one frame, and `G` the frames it stays coherent.
2. The bias in units of σ is `a × response`, for the larger-responding dilation.
3. The threshold passes if that is at most 1. The rule takes the knee if it passes,
   otherwise the passing threshold closest to the knee, otherwise word 0x1.
4. The calendar time to collect the retained year is `1 / κ` years.

κ never enters the forecast. The forecast is always for one retained year; κ only says
how long collecting it takes.

## The model

- **Inputs** (`inputs.py`): Planck 2018 with its linear P(k) table, checked against the
  cosmology before use; CHIME as in the CHIME Overview (4 cylinders × 256 feeds,
  T_sys = 55 K, 31,000 deg², 0.39 MHz channels, as-built baseline density); 8,760 h of
  retained data.
- **Fit** (`tolerance.py`): A, σ_NL, α⊥, α∥, fσ8 and bσ8 are fitted; the rest are held
  at the fiducial. The bias is first order and compared with the clean σ.
- **Residual** (`residual.py`): one transmitter's power as a flat 6 MHz shelf that stays
  coherent. It puts the same visibility on every baseline that measures a Fourier cell,
  so it sits inside the horizon wedge. Relative to the noise power,
  `dP / C_N = a × N_ν × N_meas(k⊥) × f_w(k⊥)` for `|k∥| ≤ m k⊥ + π/L`, and zero outside.
- **Quadrature** (`forecast.py`): Gauss–Legendre in k and μ, split at every kink of the
  integrand. Doubling either order changes the tolerance by less than 3 × 10⁻⁷.

## The table

24 channels: DTV allocations 14 to 36 and channel 37, which carries no DTV and
serves as the control. σ is the clean one-year uncertainty in percent; the responses are
signed.

| Channel | MHz | z | σ⊥ (%) | σ∥ (%) | Response α⊥ | Response α∥ | a_tol | Binds | |
|---|---|---|---|---|---|---|---|---|---|
| 14 | 470–476 | 2.003 | 2.48 | 2.55 | +1,273 | -3,514 | 2.85e-04 | α∥ | [plate](docs/figures/channel_14.png) |
| 15 | 476–482 | 1.965 | 2.50 | 2.55 | +676 | -2,021 | 4.95e-04 | α∥ | [plate](docs/figures/channel_15.png) |
| 16 | 482–488 | 1.929 | 2.51 | 2.55 | +190 | -582 | 1.72e-03 | α∥ | [plate](docs/figures/channel_16.png) |
| 17 | 488–494 | 1.893 | 2.49 | 2.54 | +127 | +638 | 1.57e-03 | α∥ | [plate](docs/figures/channel_17.png) |
| 18 | 494–500 | 1.858 | 2.42 | 2.53 | +761 | +1,501 | 6.66e-04 | α∥ | [plate](docs/figures/channel_18.png) |
| 19 | 500–506 | 1.824 | 2.34 | 2.51 | +2,187 | +1,959 | 4.57e-04 | α⊥ | [plate](docs/figures/channel_19.png) |
| 20 | 506–512 | 1.791 | 2.26 | 2.50 | +4,301 | +2,048 | 2.32e-04 | α⊥ | [plate](docs/figures/channel_20.png) |
| 21 | 512–518 | 1.758 | 2.20 | 2.49 | +6,814 | +1,859 | 1.47e-04 | α⊥ | [plate](docs/figures/channel_21.png) |
| 22 | 518–524 | 1.726 | 2.16 | 2.48 | +9,308 | +1,535 | 1.07e-04 | α⊥ | [plate](docs/figures/channel_22.png) |
| 23 | 524–530 | 1.695 | 2.14 | 2.47 | +11,394 | +1,214 | 8.78e-05 | α⊥ | [plate](docs/figures/channel_23.png) |
| 24 | 530–536 | 1.665 | 2.13 | 2.47 | +12,602 | +1,100 | 7.94e-05 | α⊥ | [plate](docs/figures/channel_24.png) |
| 25 | 536–542 | 1.635 | 2.11 | 2.47 | +12,589 | +1,365 | 7.94e-05 | α⊥ | [plate](docs/figures/channel_25.png) |
| 26 | 542–548 | 1.606 | 2.09 | 2.47 | +11,212 | +2,086 | 8.92e-05 | α⊥ | [plate](docs/figures/channel_26.png) |
| 27 | 548–554 | 1.578 | 2.06 | 2.46 | +8,521 | +3,241 | 1.17e-04 | α⊥ | [plate](docs/figures/channel_27.png) |
| 28 | 554–560 | 1.550 | 2.03 | 2.46 | +4,851 | +4,662 | 2.06e-04 | α⊥ | [plate](docs/figures/channel_28.png) |
| 29 | 560–566 | 1.523 | 1.99 | 2.45 | +725 | +6,078 | 1.65e-04 | α∥ | [plate](docs/figures/channel_29.png) |
| 30 | 566–572 | 1.496 | 1.95 | 2.44 | -3,356 | +7,241 | 1.38e-04 | α∥ | [plate](docs/figures/channel_30.png) |
| 31 | 572–578 | 1.470 | 1.94 | 2.44 | -6,956 | +7,976 | 1.25e-04 | α∥ | [plate](docs/figures/channel_31.png) |
| 32 | 578–584 | 1.445 | 1.96 | 2.45 | -9,762 | +8,186 | 1.02e-04 | α⊥ | [plate](docs/figures/channel_32.png) |
| 33 | 584–590 | 1.420 | 1.98 | 2.46 | -11,604 | +7,811 | 8.62e-05 | α⊥ | [plate](docs/figures/channel_33.png) |
| 34 | 590–596 | 1.395 | 1.99 | 2.47 | -12,533 | +6,849 | 7.98e-05 | α⊥ | [plate](docs/figures/channel_34.png) |
| 35 | 596–602 | 1.371 | 1.97 | 2.47 | -12,844 | +5,417 | 7.79e-05 | α⊥ | [plate](docs/figures/channel_35.png) |
| 36 | 602–608 | 1.348 | 1.93 | 2.46 | -13,002 | +3,771 | 7.69e-05 | α⊥ | [plate](docs/figures/channel_36.png) |
| 37 (control) | 608–614 | 1.325 | 1.87 | 2.46 | -13,325 | +2,189 | 7.50e-05 | α⊥ | [plate](docs/figures/channel_37.png) |

![Summary](docs/figures/summary.png)

Each plate shows where the residual sits in Fourier space at the tolerated strength,
how each dilation's bias grows with strength, and the dilation ellipse shifted by the
tolerated residual.

## Files

| File | Contents |
|---|---|
| `src/rfisher/bands.py` | the channels and their redshifts |
| `src/rfisher/inputs.py`, `pk_cache.py` | the fixed forecast inputs and the P(k) table check |
| `src/rfisher/residual.py` | the coherent DTV residual |
| `src/rfisher/forecast.py` | one channel's Fisher matrix with the residual's bias row |
| `src/rfisher/tolerance.py` | σ, bias per unit strength, response and tolerance |
| `src/rfisher/table.py`, `figures.py`, `cli.py` | the table, the figures, the command line |
| `src/rfisher/data/channel_table.json`, `.csv` | the shipped table, with provenance |
| `docs/diagram.py` | draws the call graph above |

## Tests

```bash
python -m pip install -e ".[test]"
python -m pytest -q
```

One test rebuilds channel 19 and checks it against the shipped table. CI also rebuilds
channels 14, 29 and 37 against RadioFisher at the pinned commit.
