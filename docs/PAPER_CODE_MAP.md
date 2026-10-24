# Paper/code contract

RFIsher computes a conditional response to an assumed residual. It does not
measure the detector's transfer, a coherence lifetime, or the cross-day sky/RFI
covariance. The paper's candidate words are selected in PilotProxy.

| Paper step | Code | Verification |
|---|---|---|
| CHIME/cosmology inputs and retained exposure | `inputs.py`, `baselines.py`, `pk_cache.py` | Input hashes, baseline reconstruction, Overview reproduction |
| Unit residual template within horizon support | `residual.coherent_shelf` | `tests/test_residual.py`: normalization and finite-grid integral |
| Clean Fisher block plus bias projection | `forecast.prepare`, `forecast.integrate` | Table reproduction; RadioFisher residual-hook tests |
| Fit six parameters, combine dilations into `D_V` | `tolerance.tolerance` | `tests/test_tolerance.py`: signed cancellation, covariance, ill-conditioning |
| Finite-amplitude expected-likelihood check | `nonlinear.FiniteBAOModel` | Nonlinear derivative/limit tests, bound cache and report tests |
| Saved numerical table | `table.py`, `data/channel_table.json` | Channel 19 regression and additional CI channels |

Module paths are under `src/rfisher/`. `a_tol` is the **first-order** tolerance.
Finite-amplitude or containment caps are separate inputs to the threshold rule.
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
- `coherent_shelf` names an assumed template. Its name is not evidence that
  gamma is an intrinsic coherent fraction or that G has been measured.
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

RadioFisher owns the shared units, instrument geometry and covariance integrands.
RFIsher owns the DTV residual, fitted parameter set and segmented quadrature.
Both the linear forecast and finite check consume `forecast.quadrature_segments`.
The two Overview loops assemble independent bin blocks; only the array reductions
are vectorized. They do not allocate one large multi-bin integrand.

## Repository organization

`src/` contains the supported calculation, `tests/` its scientific checks,
`tools/` explicit validation and documentation generators, and `docs/figures/`
the checked-in reader aids. `pyproject.toml` pins RadioFisher to one commit for
reproducibility; a saved table keeps the upstream revision recorded in its
provenance.
