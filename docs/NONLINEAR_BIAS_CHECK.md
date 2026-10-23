# Finite BAO-only expected-likelihood check

This diagnostic fits all six coordinates used by the existing forecast to a contaminated **expected covariance**. It does not change the channel table or operating policy, estimate finite-sample statistical bias, or calibrate the physical DTV transfer.

## Model and coordinates

The active forecast switches retain only dilation of the BAO template. The finite signal is

```
Cs(theta) = Tb^2 Pnw(k) / (r^2 rnu sigma8^2)
            * (bs8 + fs8 mu^2)^2 * exp(-k^2 mu^2 s)
            * [1 + A fbao(k_alpha)]
k_alpha = k sqrt(alpha_perp^2 (1-mu^2) + alpha_parallel^2 mu^2)
```

For original modes with `k <= 0.03 Mpc^-1`, `k_alpha=k`, matching the forecast's explicit derivative clamp. The smooth spectrum, RSD angle, volume, noise, foreground, residual, and mode cuts remain at their fiducial values. Calling RadioFisher's full `Csignal` at changed dilations would introduce terms excluded by the published switches; this diagnostic therefore refuses those other switch combinations.

The matrix coordinate `s_NL = sigma_nl^2` is the damping variance, in Mpc squared; its fiducial value is 49. The growth and bias coordinates are `fs8=f D sigma8` and `bs8=bHI D sigma8`. This is a genuine nonlinear, explicitly declared finite extension of the BAO-only tangent model. The Fisher derivatives alone do not specify a unique finite extension.

The saved BAO template is piecewise linear. The diagnostic differentiates that actual interpolant and reports its weighted difference from the forecast centered-difference derivative. It does not replace a failed derivative agreement check with the forecast tangent.

## Expected likelihood and normalization

Let `C0` be the clean fiducial total covariance, `R` the unit residual, `t=(Cs(theta)-Cs0)/C0`, and `epsilon=a R/C0`. The objective relative to the fiducial model is

```
L(theta;a) - L(theta0;a)
    = sum w [log(1+t) - (1+epsilon)t/(1+t)]
w = 2 Vfac k^2 dk dmu
```

These are the same quadrature weights as `forecast.integrate`; no extra factor of one half is introduced. The clean Hessian equals the clean Fisher matrix, and the fiducial gradient is `-a B`. The small-amplitude shift is consequently `a F^-1 B`. The implementation uses a cancellation-resistant series for the clean divergence near zero, the finite analytic gradient, and the local Hessian between interpolation knots.

The finite distance shifts are `delta log(DV)=-(2 log(alpha_perp)+log(alpha_parallel))/3` and `delta DV/DV=expm1(delta log(DV))`. These signs follow the inverse-distance convention of the dilation coordinates.

## Domain and qualification

The frozen study uses nonnegative BAO amplitude, damping variance, growth, and bias. Its amplitude ceiling keeps `1+A fbao` strictly positive across the entire saved template. Dilations have an explicit numerical search box `[0.5,1.5]`; it is not an observational prior. Active boundaries, nonstationarity, competing solutions, and unstable quadrature are reported rather than qualified by optimizer success alone.

The external protocol declares the channel/amplitude points, multistarts, base and refined quadratures, derivative and table checks, all-six small-amplitude tests, stationarity, and refinement tolerances before measured fits. The runner records the exact protocol, implementation, original input hashes, runtime, and per-start outcomes. A passing local numerical check would apply only to this expected-covariance model and its declared domain, not general physical or statistical coverage.

## Reproducibility and interruptions

`build_model` checkpoints independent radial segments. Cache identities bind the source modules, runtime, prepared cosmology and experiment settings, interpolation tables, residual geometry and standard factory, and quadrature. The clean Fisher matrix and bias row are summed in fixed 65,536-mode blocks; retained-mode invariants use the full covariance scales to avoid relative tests against nearly canceled entries. Each compressed payload binds its identity and segment limits and is checked on read. Unique temporary filenames keep an interrupted write from blocking the next attempt; completed files are replaced atomically. Changed inputs or source require a new cache directory.

Run the focused checks with `python -m pytest tests/test_nonlinear.py`. The campaign runner is `tools/check_nonlinear_bias.py`; its `--help` lists the required frozen protocol and input snapshot. Keep large grids and experimental results outside the repository. Do not overwrite the frozen publication tables.
