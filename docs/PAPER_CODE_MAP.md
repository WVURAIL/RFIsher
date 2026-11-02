# Calculation and validation

| Step | Implementation | Check |
|---|---|---|
| Fixed cosmology, instrument and exposure | inputs.py, baselines.py | Input checks; clean Overview reproduction |
| Flat unit additive residual in mK^2 | residual.unit_power | Noise independence and grid-invariant normalization |
| Clean Fisher matrix and residual projection | forecast.py; RadioFisher quadrature | Quadrature convergence; upstream reference |
| Six-parameter solve and distance projection | tolerance.py; RadioFisher results | Known-answer covariance and bias tests |
| First-order channel tolerance | table.py | Rebuilt schema-v3 table |
| Local finite-amplitude model | nonlinear.py | Derivative, gradient and Hessian checks |

The dilation convention is alpha_V = D_V(fid) / D_V, so the physical distance
bias has the opposite sign to response_dv. The tolerance uses its magnitude.
The residual is additive covariance power. Noise, baseline density, the
foreground mode limit, and nonlinear scale belong to the clean forecast.
The integration grid is not a physical sample count.
The table uses 8,760 retained hours. Retaining fraction kappa costs 1/kappa
reference exposures.
