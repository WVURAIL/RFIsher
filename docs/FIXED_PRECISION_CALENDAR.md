# Fixed precision and calendar budgets

`rfisher response calendar --input candidates.json --output NEW.json` evaluates
supplied same-mask physical responses against the study's fixed clean-reference
precision. It complements `forecast.required_time`, whose target is BAO
amplitude detection significance. It does not derive a physical response from
detector retention, a spectral peak, or an archival screening allowance.

For every declared dilation parameter, an evaluated candidate/time pair passes
when both conditions hold, including equality:

```
sigma(candidate, time) <= sigma(clean reference)
abs(bias(candidate, time)) <= sigma(clean reference)
```

Tolerance is fixed at 1 for this study. The error on the right is the same fixed
reference for every candidate and time. A candidate's improved precision does
not silently tighten that budget. Bias remains signed in the output, although
admission uses its magnitude. The clean reference must state its observing time
(the dissertation uses 8,760 on-sky hours), estimator, and science domain.

Required on-sky hours already include mask-induced loss of information and any
modeled stochastic residual. Calendar years are `on_sky_hours / (duty *
hours_per_calendar_year)`. The study uses duty 0.152, 8,766 hours per mean
calendar year, and budgets of 10 and 100 calendar years. Retention is not charged
again. Duty is a declared extrapolation of historical availability, not a
forecast of future telescope operation.

## Domain and response requirements

The nominal `science_bins` must be identical for the reference and every
candidate. These labels identify the full comparison domain, not just bins that
happen to survive a candidate mask. Nonempty `excluded_pilot_bins` must also be
identical and disjoint from science support. The supplied response must account
for any missing information within that domain.

Use `parameter_scope: per_forecast_bin` and names such as `bin0:aperp`,
`bin0:apar`, `bin1:aperp`, `bin1:apar` when more than one forecast bin overlaps the
channel. Both dilations in every declared forecast bin are required. A
`joint_domain` reference instead requires exactly `aperp` and `apar` from an
explicit, independently justified joint estimator. The command does not combine
per-bin errors into a joint fit. Nor does it silently substitute an
allocation-only target for the dissertation's full forecast-bin target.

Both the reference and candidate responses carry the explicit qualification
declaration used by `response.evidence`. Unqualified declarations remain visible
but cannot admit a time point. Each also cites entries from `evidence_files`.
The command verifies the bytes of these local files before writing the report.
File hashes prove identity, not physical calibration: reviewers still need to
establish the estimator, units, matched clean reference, masks, covariance,
time dependence, and transfer to the dilation parameters. The pure
`evaluate_document` API validates declarations but does not read evidence files.

## Input example

The following structure is illustrative. Its numerical values and placeholder
digest are not channel measurements and are not an executable physical claim.

```json
{
  "schema": "rfisher_physical_calendar_candidates_v1",
  "channel": 20,
  "evidence_files": [
    {"id": "response", "path": "reviewed-response.json", "sha256": "REPLACE_WITH_REAL_SHA256"}
  ],
  "reference": {
    "parameter_scope": "per_forecast_bin",
    "forecast_bins": ["bin0", "bin1"],
    "parameter_names": ["bin0:aperp", "bin0:apar", "bin1:aperp", "bin1:apar"],
    "parameter_units": ["dimensionless", "dimensionless", "dimensionless", "dimensionless"],
    "sigma": [0.01, 0.02, 0.015, 0.025],
    "on_sky_hours": 8760,
    "science_bins": ["declared-sister-domain-bin-a", "declared-sister-domain-bin-b"],
    "excluded_pilot_bins": ["pilot-bearing-bin"],
    "provenance": {"evidence_ids": ["response"], "description": "Reviewed clean reference on the stated domain"},
    "evidence": {
      "evidence_kind": "physical_same_mask_response",
      "physical_response_qualified": true,
      "science_selection_eligible": true,
      "residual_contains_sensitivity_floor": false
    }
  },
  "context": {
    "tolerance": 1,
    "duty": 0.152,
    "hours_per_calendar_year": 8766,
    "budgets_calendar_years": [10, 100]
  },
  "fallback_threshold": {"kind": "finite", "eta_q16": "6644482"},
  "candidates": [{
    "id": "reviewed-word",
    "threshold": {"kind": "finite", "eta_q16": "6644482"},
    "science_bins": ["declared-sister-domain-bin-a", "declared-sister-domain-bin-b"],
    "excluded_pilot_bins": ["pilot-bearing-bin"],
    "response_provenance": {"evidence_ids": ["response"], "description": "Same-mask bias and statistical errors, including information loss"},
    "evidence": {
      "evidence_kind": "physical_same_mask_response",
      "physical_response_qualified": true,
      "science_selection_eligible": true,
      "residual_contains_sensitivity_floor": false
    },
    "evaluations": [{
      "on_sky_hours": 13324.32,
      "status": "available",
      "bias": [0.001, -0.002, 0.003, 0.004],
      "sigma": [0.01, 0.02, 0.015, 0.025]
    }]
  }]
}
```

An unavailable point instead has exactly `on_sky_hours`, `status: unavailable`,
and a nonempty `reason`. An empty evaluation list is incomplete evidence. Neither
case is interpreted as zero bias. Nonfinite values, duplicate identities/times,
unknown top-level fields, malformed exact words, and inconsistent domains are
refused. The output file must not already exist.

## What selection establishes

For each calendar budget the report selects the earliest qualified feasible
point among the supplied candidates and times. It records all exact-time ties;
candidate ID provides a deterministic representative. It does not interpolate,
assume monotonic response, or extrapolate a variance law. Unknown times,
unqualified candidates, and unsupplied thresholds prevent a claim of a global
physical optimum even if one tested feasible point is available.

If no qualified evaluated point fits a budget, `threshold_assignment` retains
the explicit `fallback_threshold`. A numeric zero threshold is allowed and
remains different from the `reject_all` limiting threshold: under strict
exceedance, a zero score can survive numeric zero. `reject_all` provides no
channel information and cannot carry a finite-precision evaluation. This
command never invents all-threshold infeasibility or automatically turns missing
data into an excision. It also never activates a threshold.
