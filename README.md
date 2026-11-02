# RFIsher

RFIsher computes the first-order BAO distance bias from flat additive DTV
power: F delta_theta = B, with residual power replacing one model derivative
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

The nonlinear module is a focused local BAO-model validation helper, separate
from table generation. See docs/PAPER_CODE_MAP.md.
