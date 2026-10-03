# Adapting the science side

The detector side ([pilot-proxy](https://github.com/WVURAIL/pilot-proxy),
`docs/ADAPTING.md` there) describes four tiers of adaptation. Tiers (a) to (c)
(a new telescope, another emitter with a narrowband marker, an emitter with no
marker) change only that repository: as long as its handoff validates against
the vendored schema, nothing here changes. Tier (d), a new science model, is
this repository's.

## Tier (d): a new science model

A science model is any object with the attributes and methods of the
`ScienceModel` protocol (`src/rfisher/science_model.py`): its `parameters`
(`required`, which set a tolerance, and `reported`, which are listed), its
`scenarios` (each with a `role`, `rule` or `sensitivity`, and the suppression
`suppression_db` it assumes), `target_years`, `zeta`, the stability test's
`year_grid` and `maximum_tolerance_ratio`, its `bins()` and
`bins_for_band(low_mhz, high_mhz)`, the `response(scenario, bin, hours)` that
gives each parameter's error and bias per unit residual, the `accept` test, and
an `identity()` that the tolerance table's provenance records. It also
declares what a tolerance is a tolerance on: `r_reference` (a residual power
ratio per frame, in a stated reference) and `residual_shapes`; the verdict
refuses a detector handoff whose manifest declares another.

The one model today is `rfisher.forecast.radiofisher_bao.model.RadioFisherBAO`
(RadioFisher, the `chime2022` experiment, Planck 2018). A new one goes under
`src/rfisher/forecast/<name>/` with its profile under `projects/<name>/`:

- `science_model.yaml`: the adapter, its parameters, target time, scenarios and
  `r_reference`, naming the register entries that hold its numbers;
- `science_register.json`: the science entries (every one `side: science`;
  the loader `rfisher.policy` refuses a detector entry);
- `selector_policy.json`: the selector's entries (the cost plateau, the
  tie-break, the precedence, the fine ranks it reads).

`rfisher tolerance build --project projects/<name>` writes its per-bin table
and `rfisher tolerance bands` reduces it to `tolerances.csv`; the verdict reads
that file and the detector's handoff and nothing of the model. `rfisher.tolerance`
and `rfisher.verdict` name no parameter, bin or scenario of a particular model.

## What stays project-specific

RadioFisher, the `chime2022` experiment, the BAO parameter names and the
filter-scenario names (`src/rfisher/forecast/radiofisher_bao/`,
`projects/chime_bao/`); the capture ruling of the 2026 campaign and its
amendments (`src/rfisher/records/chime_atsc_2026/`); the frozen tokens of
[terminology.md](terminology.md).
