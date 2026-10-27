# Finite BAO-only expected-likelihood check

This check tests the first-order bias of the forecast at finite residual strength. Here, the six coordinates of the forecast are fitted to a contaminated *expected covariance*. The check leaves the channel table and the operating policy unchanged, and it does not estimate finite-sample statistical bias or calibrate the physical DTV transfer.

## Model and coordinates

With the active forecast switches, the dilations shift only the BAO template. The finite signal is

```
Cs(theta) = Tb^2 Pnw(k) / (r^2 rnu sigma8^2)
            * (bs8 + fs8 mu^2)^2 * exp(-k^2 mu^2 s)
            * [1 + A fbao(k_alpha)]
k_alpha = k sqrt(alpha_perp^2 (1-mu^2) + alpha_parallel^2 mu^2)
```

where `k_alpha = k` for modes whose unshifted `k` is at most `0.03 Mpc^-1`, as in the explicit derivative clamp of the forecast. The smooth spectrum, RSD angle, volume, noise, foreground, residual, and mode cuts are held at their fiducial values. RadioFisher's full `Csignal` at changed dilations would add terms that the published switches exclude, so the check refuses all other settings of the switches.

The matrix coordinate `s_NL = sigma_nl^2` is the damping variance in Mpc squared, with a fiducial value of 49. For growth and bias, the coordinates are `fs8 = f D sigma8` and `bs8 = bHI D sigma8`. Since the Fisher derivatives alone do not specify a unique finite extension, this model is declared explicitly as one finite, nonlinear extension of the BAO-only tangent model.

The saved BAO template is piecewise linear. This interpolant is differentiated directly, and its weighted relative error against the central-difference derivative of the forecast is reported. A failed derivative check stays failed, and the forecast tangent is never used in its place.

## Expected likelihood and normalization

The objective relative to the fiducial model is

```
L(theta;a) - L(theta0;a)
    = sum w [log(1+t) - (1+epsilon)t/(1+t)]
w = 2 Vfac k^2 dk dmu
```

where `C0` is the clean fiducial total covariance, `R` is the unit residual, `t = (Cs(theta) - Cs0)/C0`, and `epsilon = a R/C0`. Here, `w` holds the quadrature weights of `forecast.integrate`, with no extra factor of one half. With these weights, the clean Hessian equals the clean Fisher matrix, and the fiducial gradient is `-a B`. Thus, the small-amplitude shift is `a F^-1 B`. Near zero, the clean divergence is evaluated with a series that avoids cancellation. Both the gradient of the finite model and its local Hessian between interpolation knots are analytic.

The finite distance shifts are `delta log(DV) = -(2 log(alpha_perp) + log(alpha_parallel))/3` and `delta DV/DV = expm1(delta log(DV))`. These signs follow the inverse-distance convention of the dilation coordinates.

## Domain and qualification

The frozen study holds the BAO amplitude, damping variance, growth, and bias nonnegative. Its amplitude ceiling keeps `1 + A fbao` strictly positive over the whole saved template. For the dilations, the numerical search box is `[0.5, 1.5]`, and no observational prior is applied. Active bounds, nonstationary points, competing solutions, and unstable quadrature are reported for each fit, since optimizer success alone does not qualify a fit.

An external protocol declares, before any measured fit, the channel and amplitude points, the multistarts, the base and refined quadratures, the derivative and table checks, the small-amplitude tests on all six coordinates, and the stationarity and refinement tolerances. The runner records the exact protocol, the implementation, the original input hashes, the runtime, and the outcome of each start. A passing local numerical check holds only for this expected-covariance model in its declared domain, and general physical or statistical coverage is not tested.

## Reproducibility and interruptions

`build_model` checkpoints the independent radial segments. The cache identity binds the source modules, the runtime, the prepared cosmology and experiment settings, the interpolation tables, the residual geometry and its standard factory, and the quadrature. To bound the summation error, the clean Fisher matrix and bias row are summed in fixed blocks of 65536 modes. In the retained-mode check, the errors are scaled by the full covariance, so no relative test is made against nearly canceled entries. Each compressed payload binds its identity and segment limits and is checked on read. Temporary files have unique names, so an interrupted write does not block the next attempt, and completed files are replaced atomically. Changed inputs or source need a new cache directory.

Unit tests for the check are run with `python -m pytest tests/test_nonlinear.py`. The campaign runner is `tools/check_nonlinear_bias.py`, and its `--help` lists the frozen protocol and input snapshot it needs. Large grids and study results are kept out of the repository, and the frozen publication tables are never overwritten.
