# Local finite-amplitude check

The FiniteBAOModel helper provides a focused check of the BAO-only local
response. Tests compare its derivatives, likelihood gradient, and Hessian
with the six-coordinate Fisher calculation. The table remains first order.
The helper accepts supplied mode arrays; no campaign runner or checkpoint
system is included. A finite-amplitude result is specific to this model and
does not establish physical calibration of a detector proxy.


The dissertation's checked channel amplitudes are recorded in
`../dissertation/data/assembly/channel_limits.json`, with a compact
`power_limits.json` for threshold selection. These require the separate
measurement-to-covariance calibration described there.

The fitter enforces the physical bounds after converting from scaled
optimizer coordinates. This avoids rejecting an exact zero damping variance
when subtraction roundoff reconstructs it as a tiny negative value. A bound
reached this way is still reported in `active_bounds`.
