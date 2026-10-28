# Paper/code contract

RFIsher computes a response to a fully coherent residual. Its strength is
supplied directly in the forecast-exposure normalization. Stacking, gamma
estimation, temporal-gain fits, and the previous calibrated PilotProxy threshold
workflow are outside the current scope. Their existing code is retained for
historical work; RFIsher does not call it.

| Paper step | Code | Verification |
|---|---|---|
| CHIME/cosmology inputs and retained exposure | `inputs.py`, `baselines.py`, `pk_cache.py` | Input hashes, baseline reconstruction, Overview reproduction |
| Unit residual template within horizon support | `residual.coherent_shelf` | `tests/test_residual.py`: normalization and finite-grid integral |
| Clean Fisher block plus bias projection | `forecast` adapter; `radiofisher.quadrature` | Table reproduction; RadioFisher residual-hook tests |
| Fit six parameters, combine dilations into `D_V` | `tolerance` adapter; `radiofisher.summarize_fisher` and `project` | `tests/test_tolerance.py`: signed cancellation, covariance, ill-conditioning |
| Finite-amplitude expected-likelihood check | `nonlinear.FiniteBAOModel` | Nonlinear derivative/limit tests, bound cache and report tests |
| Saved numerical table | `table.py`, `data/channel_table.json` | Channel 19 regression and additional CI channels |

Unqualified module paths are under `src/rfisher/`. `a_tol` is the **first-order** tolerance.
Finite-amplitude or containment caps are separate from this response table.
The channel-16 quadrature and channel-19 containment checks the paper reports
are recorded with the manuscript; the default quadrature alone does not qualify
every nonlinear fit.

## Names and units

- `response_dv` is the signed response of `ln(alpha_V)`, with
  `alpha_V = D_V_fid / D_V`. The physical distance shift in clean-error units
  is `-a * response_dv`; the decision compares `a * abs(response_dv)`.
  The table field `bias_dv_per_unit_a` (schema v2) stores the unnormalized
  `ln(alpha_V)` projection, with that sign.
- `s_NL` is **damping variance**, in Mpc squared. The physical configuration `sigma_nl` is a length in Mpc.
- `_Pres` is the residual projection row, not a fitted parameter. Remove it
  before inversion. The residual is absent from the fitted clean covariance.
- `coherent_shelf` assumes full coherence across measurements of a Fourier
  cell. The strength `a` multiplies that template directly, with no measured
  gamma or fitted temporal gain. Its normalization uses the noise at the
  forecast exposure. It is not a per-frame detector proxy.
- `sigma_dv` is the clean statistical uncertainty on the distance measurement;
  it is not an uncertainty on the modeled systematic bias.
- The table uses 8,760 retained hours. Primary paper calendar time is
  `1 / kappa` years for that exposure. No operating-duty factor is implicit.
- The residual's wedge support is not wedge excision; no delay filter is applied.

The Python entry point is `from rfisher.tolerance import tolerance`.
Matrices and tables label the damping coordinate `s_NL`; the table schema is
`rfisher-channel-table-v2`. The shipped table's `provenance` block records the
RFIsher and RadioFisher commits and the input hashes it was built with. The
regression checks rebuild channel 19 (`tests/test_table.py`) and channels 14, 29
and 37 (CI) with the current code and match the shipped rows within their
tolerances.

RadioFisher owns the shared units, instrument geometry, covariance integrands,
direct BAO derivative, segmented quadrature, and covariance/bias result API.
RFIsher owns the DTV residual, fitted parameter choice, D_V weights, and
residual-specific integration boundary. Its `forecast` and `tolerance` modules
are study adapters. `radiofisher.summarize_fisher` computes the clean covariance
and first-order bias; `FisherResult.project` propagates both through the supplied
Jacobian. RFIsher then reports the D_V response and tolerance.

Both the linear forecast and finite check consume `forecast.quadrature_segments`,
which delegates the nodes and weights to `radiofisher.quadrature`. The finite
check validates the upstream `DirectBAODerivative` template, step, and cutoff,
and binds those settings and source files into its cache identity. Upgrading
requires a fresh cache. The original shipped table and its provenance remain
reference data.
The two Overview loops assemble independent bin blocks; only the array reductions
are vectorized. They do not allocate one large multi-bin integrand.

## Repository organization

`src/` contains the supported calculation, `tests/` its scientific checks,
`tools/` explicit validation and documentation generators, and `docs/figures/`
the checked-in reader aids. `pyproject.toml` pins RadioFisher to one commit for
reproducibility; a saved table keeps the upstream revision recorded in its
provenance.
