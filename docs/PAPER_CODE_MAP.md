# Forecast contract and handoff

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
The paper's later channel-16 quadrature and channel-19 containment checks remain
in the manuscript's frozen follow-up records; default quadrature alone does not
claim that every nonlinear fit is qualified.

## Names and units

- `response_dv` is signed; the decision compares `a * abs(response_dv)`.
- `sigma_NL` is a legacy matrix label for **damping variance** `s_NL`, in
  Mpc squared. The physical configuration `sigma_nl` is a length in Mpc.
- `_Pres` is the residual projection row, not a fitted parameter. Remove it
  before inversion. The residual is absent from the fitted clean covariance.
- `coherent_shelf` names an assumed template. Its name is not evidence that
  gamma is an intrinsic coherent fraction or that G has been measured.
- The table uses 8,760 retained hours. Primary paper calendar time is
  `1 / kappa` years for that exposure. No operating-duty factor is implicit.
- The residual's wedge support is not wedge excision; no delay filter is applied.

The ordinary Python entry point is `from rfisher.tolerance import tolerance`.
For compatibility the package's `rfisher.tolerance` module is also callable;
new code should use the explicit function import. The matrix labels and saved
JSON keys remain stable for existing data and external consumers.

## Repository organization

`src/` contains the supported calculation, `tests/` its scientific checks,
`tools/` explicit validation and documentation generators, and `docs/figures/`
the checked-in reader aids. Frozen tables retain their recorded upstream
revision. RFIsher pins RadioFisher for reproducibility; reviewing a later
RadioFisher cleanup does not silently change that dependency.
