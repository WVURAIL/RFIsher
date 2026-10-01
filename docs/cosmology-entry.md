# Where cosmology enters

For an engineer: the detector side hands over, for every candidate threshold
of a band, what masking costs and what it leaves behind (`f` and `r_sys`).
This page says what the science side compares `r_sys` with, and why.

## The tolerance r_tol, in words

The survey measures the BAO distance scale through two dilation parameters,
α⊥ (across the line of sight) and α∥ (along it), per redshift bin. A residual
of interference left in the data shifts their estimates. For a small residual
the shift is linear in its amplitude, like a gain error in a linear amplifier:
`Δθ = b · r`, where `b` is the parameter's bias per unit residual
(`bias_per_unit_residual` of the science model). The tolerance is the residual
whose bias equals the statistical uncertainty the survey would have anyway:

```text
r_tol = min over the required parameters and the bins the band overlaps of  ζ · σ_θ(T*) / |b_θ|
```

with ζ = 1 and `σ_θ(T*)` the parameter's one-sigma uncertainty after
T* = one on-sky year (`rfisher.tolerance.rule`). A band is held to the
strictest parameter and bin it touches. A residual at `r_tol` therefore biases
the binding parameter by one sigma of a one-year survey; `R = r_sys / r_tol`
says how many such sigmas a kept residual is worth.

## The suppression S

A delay filter in the analysis can attenuate a residual further before it
reaches the parameters. Each scenario of the science model (`none`, `peak1`,
`peak2`, `deployed`) states that attenuation as `S` in dB, from the relation
between delay and line-of-sight wavenumber. `S` is never folded into `r_tol`:
the tolerance table carries it in its own column, and the verdict reads a
scenario's `S` as a post-processing sensitivity beside the rule (this work does
not measure the filter).

## Why some bands have no archive tolerance

`r_tol` rests on the linear bias model. Before a tolerance is accepted, the
code checks that the model is stable there: it perturbs the integration time
by ± `science.response_stability.time_fraction` and requires that the
tolerance move by no more than `science.response_stability.maximum_tolerance_ratio`
and that the bias response not change sign. In redshift bins 1, 5, 7, 8 and 11
both distance-scale tolerances fail that test at T* = one year, and a band
inherits the refusal from any bin it overlaps. Bins 5, 7, 8 and 11 cover bands
14 to 17, 23 to 30 and 34 to 36: the 15 bands with no archive tolerance.
"Refused" does not mean the forecast has no uncertainty there; it means the
linear model is not trustworthy there after one year, and the method declines
to price the band rather than extrapolate.

## Why fσ8 is reported, not required

The science target is the distance scale (α⊥ and α∥). fσ8, the growth rate,
is constrained by the same forecast and its tolerance is finite on every band,
about six times stricter where both exist. The science model therefore lists
`required: [aperp, apar]` and `reported: [fs8]`; the tolerance components
carry fσ8 with `required = False`. Requiring it would make every `r_tol`
smaller, so it would only make a keep harder and would not change an
exclusion.

## Two bases: the grid and the exact time

The archive verdict reads the grid table, `grid_T1yr_stability_gated`: the
forecast evaluated on its year grid and gated by the stability test above. The
capture ruling of record reads the exact-time reference,
`exact_time_reference_2026-09-09`, integrated directly at T* and not gated the
same way. Channel 29 shows the difference: the grid refuses it (its bin 7 fails
the stability test), while the exact-time reference gives
r_tol = 0.027980 for it. Channel 33 has both: 0.015829 on the grid and
0.017469 at the exact time.

## The two entry points

Cosmology enters through `rfisher.forecast` (the RadioFisher BAO adapter, its
banks and scenarios) and `rfisher.tolerance` (the rule above and the table it
writes). Two things leave them: `tolerances.csv`, the only science input of
both verdicts, and the BAO-band coherence gain, which the capture ruling of
record alone reads.
