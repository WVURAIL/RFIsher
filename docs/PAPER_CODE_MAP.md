# Paper/code contract

This map traces each step of the paper to its code and its check. RFIsher computes a
conditional response to an assumed residual. The detector's transfer, a coherence lifetime,
and the cross-day sky and RFI covariance are not measured here. PilotProxy selects the
paper's candidate words.

| Paper step | Code | Verification |
|---|---|---|
| CHIME/cosmology inputs and retained exposure | `inputs.py`, `baselines.py`, `pk_cache.py` | Input hashes, baseline reconstruction, Overview reproduction |
| Unit residual template on the horizon wedge | `residual.coherent_shelf` | `tests/test_residual.py`: normalization and finite-grid integral |
| Clean Fisher block plus bias projection | `forecast.prepare`, `forecast.integrate` | Table reproduction; RadioFisher residual-hook tests |
| Fit six parameters, form `D_V` from the dilations | `tolerance.tolerance` | `tests/test_tolerance.py`: signed cancellation, covariance, ill-conditioning |
| Finite-amplitude expected-likelihood check | `nonlinear.FiniteBAOModel` | Nonlinear derivative/limit tests, bound cache and report tests |
| Saved numerical table | `table.py`, `data/channel_table.json` | Channel 19 regression and additional CI channels |

Module paths are under `src/rfisher/`. `a_tol` is the first-order tolerance, and the
finite-amplitude and containment caps enter the threshold rule as their own inputs.
The channel-16 quadrature check and the channel-19 containment check that the paper
reports are recorded with the manuscript. The default quadrature alone does not qualify
every nonlinear fit.

## Names and units

- `response_dv` is the signed response of `ln(alpha_V)`, with
  `alpha_V = D_V_fid / D_V`. The physical distance shift in clean-error units
  is `-a * response_dv`, and the decision compares `a * abs(response_dv)`.
  The table field `bias_dv_per_unit_a` (schema v2) stores the unnormalized
  `ln(alpha_V)` projection, with that sign.
- `s_NL` is the damping variance in Mpc squared. The configuration value `sigma_nl` is the damping length in Mpc.
- `_Pres` is the residual projection row and is never fitted. It is removed
  before inversion, so the fitted clean covariance has no residual term.
- `coherent_shelf` is the name of an assumed template. Its name implies no
  intrinsic coherent fraction for gamma and no measured value of G.
- The table uses 8760 retained hours. For that exposure, the paper's primary
  calendar time is `1 / kappa` years, with no operating-duty factor.
- The residual has its support in the wedge. No wedge modes are excised, and
  no delay filter is applied.

The Python entry point is `from rfisher.tolerance import tolerance`.
Matrices and tables label the damping coordinate `s_NL`, and the table schema is
`rfisher-channel-table-v2`. In the shipped table, the `provenance` block records
the RFIsher and RadioFisher commits and the input hashes it was built with. With
the current code, the regression checks rebuild channel 19 (`tests/test_table.py`)
and channels 14, 29, and 37 (CI) and match the shipped rows to their tolerances.

RadioFisher owns the shared units, the instrument geometry, and the covariance
integrands. RFIsher owns the DTV residual, the fitted parameter set, and the
segmented quadrature. Both the linear forecast and the finite check take their
nodes from `forecast.quadrature_segments`. The two Overview loops assemble the
independent bin blocks, and only the array reductions are vectorized, so no
large multi-bin integrand is allocated.

## Repository layout

`src/` holds the supported calculation, `tests/` its scientific checks, `tools/`
the validation and documentation generators, and `docs/figures/` the checked-in
figures for readers. `pyproject.toml` pins RadioFisher to one commit so the table
can be reproduced, and a saved table records the upstream revision in its
provenance.
