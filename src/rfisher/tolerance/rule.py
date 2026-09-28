"""The tolerance rule: r_tol = zeta * sigma / |b| at the target time, if stable.

For every scenario, bin and parameter of a science model, the rule evaluates
the response on the model's year grid (with the target time added if it is
missing). At each time it asks the model once for the bias per unit residual
b and the error sigma of every parameter, and then, parameter by parameter,
for the stability test. A value is accepted when the tolerance moves by at
most the model's ``maximum_tolerance_ratio`` over the time perturbation and b
keeps one sign. A refused response refuses every parameter at that time; a
refused stability test refuses only its parameter.

Only the target time may supply a tolerance. A value accepted at another time
is counted in ``years_accepted`` but never substitutes for a refusal at the
target.
"""
from __future__ import annotations

import math

from rfisher.science_model import ScienceModel


def tolerance_rows(model: ScienceModel) -> list[dict]:
    """One row per scenario, bin and parameter, in the model's orders.

    The row keys are the columns of the per-bin table
    (``rfisher.tolerance.table.COLUMNS``); ``world`` holds the scenario name.
    """
    parameters = model.parameters.all
    zeta = float(model.zeta)
    limit = float(model.maximum_tolerance_ratio)
    target = float(model.target_years)
    years = tuple(float(v) for v in model.year_grid)
    rows = []
    if target not in years:                 # the declared target must be on the grid
        years = tuple(sorted(set(years) | {target}))
    for scenario in model.scenarios:
        # An unavailable or unauthenticated response stops the table; only
        # an evaluation inside the loops below may count as a refusal.
        model.load(scenario.name)
        for b in model.bins():
            accepted = {p: [] for p in parameters}
            refused = {p: 0 for p in parameters}
            at_target = {p: math.nan for p in parameters}
            for year in years:
                t = model.hours(year)
                try:
                    dth, sig = model.response(scenario.name, b.index, t)
                except Exception:
                    for p in parameters:
                        refused[p] += 1
                    continue
                for p in parameters:
                    try:
                        drift, nsign = model.accept(scenario.name, b.index, t, p)
                    except Exception:
                        refused[p] += 1
                        continue
                    if drift <= limit and nsign == 1:
                        value = zeta * sig[p] / abs(dth[p])
                        accepted[p].append((year, value))
                        if year == target:
                            at_target[p] = value
                    else:
                        refused[p] += 1
            for p in parameters:
                # Only the declared target time may supply an operational tolerance.
                if math.isfinite(at_target[p]):
                    value, used, on_target = at_target[p], target, True
                else:
                    value, used, on_target = math.nan, math.nan, False
                rows.append({"world": scenario.name, "bin_index": b.index,
                             "z_lo": b.low, "z_hi": b.high, "parameter": p,
                             "tolerance": float(value) if math.isfinite(value) else math.nan,
                             "at_target": on_target, "years_used": used,
                             "years_accepted": len(accepted[p]),
                             "years_refused": refused[p]})
    return rows
