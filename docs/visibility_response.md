# Response of the 10-second visibility product

`rfisher_results.validation.visibility_response` carries the coherent complex mean and centered covariance through an explicitly supplied, fixed idealized science response. It does not infer telescope calibration or equate a normalized coherent amplitude with the forecast's additive covariance power.

The input is the same-policy, same-support visibility ensemble at the 10-second boundary. No delay cut or sidereal-mean subtraction receives cleaning credit. A fixed idealized response translates endpoint contamination into a science requirement; it is not an additional proposed mitigation stage.

## Quantities and assumptions

For complex visibilities, provide the mean, Hermitian centered covariance C and symmetric pseudocovariance P. `complex_moments_to_real` retains their full real/imaginary covariance in the order `[Re(v), Im(v)]`. P must be supplied explicitly because selection can produce improper complex data.

For a fixed real symmetric quadratic kernel Q and real visibility vector x with mean m and covariance C,

    E[x.T Q x] = tr(Q C) + m.T Q m.

The two terms remain separate in the result. For Gaussian x, the covariance of two such statistics is

    Cov(q_a, q_b) = 2 tr(Q_a C Q_b C) + 4 m.T Q_a C Q_b m.

The expectation requires only second moments. The covariance formula uses a Gaussian closure and must be validated with independent injections for the selected ensemble. Arbitrary frame masking does not guarantee that closure. Supply the complete conditional moments, including any change in thermal noise caused by the selection; do not add an independent residual covariance unless independence is justified.

`linear_parameter_response` takes a caller-supplied science Jacobian and statistic covariance, fits all declared parameters, and reports the signed bias and full sampling covariance. Growth is a nuisance parameter in that joint fit. Both dilation components can then be compared with a separately declared clean reference. The function neither certifies a channel nor manufactures an observing time from the retained frame fraction.

## Reproduce the synthetic check

From this repository, using an environment with NumPy and pytest:

    PYTHONPATH=src python -m pytest -q tests/test_visibility_response.py
    PYTHONPATH=src python scripts/validate_visibility_response.py --output ../output/dissertation-implementation-2026-09-19/visibility-response

The simulation uses known six-dimensional Gaussian visibility moments and fixed illustrative kernels and derivatives. It validates moment accounting and the linear fit. Its arbitrary units and synthetic derivatives are not a CHIME BAO forecast. The output records source hashes, seed, acceptance limits, separate bias contributions, covariance and fit results.

## Still needed for physical channel decisions

- Calibrated, identity-matched baseline/frequency/polarization visibilities and joint valid counts under the actual frame policy.
- The idealized instrument/sky response and both dilation derivatives on that same support, with full nuisance marginalization and consistent physical units.
- Noise, signal and residual injections that test selection, the covariance closure, estimator response and confidence coverage.
- Representative temporal/era support; compact short captures cannot supply continuous physical 10-second moments.
- A justified optimistic bound over the declared masking class for an exclusion. Passing this component test is not that bound.
