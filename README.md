# RFIsher

RFIsher computes the first-order BAO distance bias from additive residual
power, by default flat DTV power: F delta_theta = B, with residual power replacing one model derivative
in B (Amara & Refregier, 2008, equations 7-8). The clean covariance is unchanged.

The residual template is P_DTV = 1 mK^2 at every forecast mode. Its amplitude
a is additive covariance power in mK^2. The response is bias / sigma per mK^2,
and a_tol = 1 / abs(response_dv). These are first-order model tolerances.

Quadrature weights supply the integration measure. Do not divide by the
number of numerical grid points. Refining that grid must leave the residual
power unchanged.

## Run

    rfisher table --out out/table --workers 4
    rfisher figures --table out/table/channel_table.json --out out/figures
    rfisher overview --out out/reference
    python -m pytest -q

The table uses the adopted cosmology, inter-cylinder baselines, six fitted
parameters (A, s_NL, alpha_perp, alpha_parallel, fs8, bs8), and 8,760 retained
hours. The Overview command verifies the clean reference forecast.

Schema v3 identifies the additive-power normalization. Earlier tables must
not be interpreted in these units. The simple model assigns temperature Tsys*x to the retained shelf ratio x
and distributes its squared amplitude uniformly over the supported forecast
modes. Each row records the resulting coefficient in a = power_scale*x**2.
This is a stated normalization assumption, not a measured sky calibration.

## Other bands, residuals and targets

The DTV study is the default case. Any set of channels is given as a CSV
with the columns channel, low_mhz and high_mhz and an optional role, and it
is passed with `--bands`. Every band must lie below the 21 cm rest frequency.

The residual template is a function f(k, mu, cn, cs) that returns the
residual power in mK^2 at each forecast mode. The tolerance is then in units
of the template amplitude, and the temperature normalization of the flat DTV
template is recorded as None. A template with a sharp edge in k or mu needs
that edge in the quadrature. Named templates are kept in
`residual.TEMPLATES`, which holds only `flat` at present. A template is passed
in Python as `template=` or on the command line as `--template flat` or
`--template package.module:function`.

The D_V tolerance is always computed. With `--target`, each row also gives
the tolerance on aperp, apar or fs8, and `target_tolerance` accepts any
weighted sum of the fitted parameters.

    rfisher table --out out/custom --bands my_bands.csv --target apar

## Using another Fisher code

A Fisher backend is a function of (band, template, telescope) that returns
F with a '_Pres' row and column, the parameter names, z_center and a
normalization that may be None. RadioFisher is the default backend, and
others are added to `forecast.BACKENDS` or passed to `build_table` as
`backend=`. For a single forecast,
`rfisher.tolerance.target_tolerance(F, names, weights, fitted,
bias_projection=B)` takes the Fisher matrix F without the residual and the
projection B in the order of names.

## Telescopes

CHIME is the only telescope at present. A new telescope is added to
`inputs.TELESCOPES` with its RadioFisher experiment and baseline density.
CHORD and HIRAX are dish arrays, so they first need a dish noise model in
RadioFisher.

The nonlinear module is a focused local BAO-model validation helper, separate
from table generation. See docs/PAPER_CODE_MAP.md.
