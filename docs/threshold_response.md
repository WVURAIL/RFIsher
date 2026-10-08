# Threshold response

`rfisher response threshold` exports the detector's complete supported
calibration curve: threshold in, residual proxy and exposure loss out.
Generate the handoff with `pilot-proxy characterize archive --fine-surface
complete`. Then, for example:

```sh
rfisher response threshold \
  --characterization science-characterization \
  --characterization control-characterization \
  --clean-years 1 --out threshold-response
```

The output directory must be new. It contains `response.csv`,
`bandstatus.csv`, and `manifest.json`. Every declared band retains a status,
including controls and bands without a supported curve. The manifest keeps
the source summaries, era and geometry information, residual reference,
integration model, and hashes. Residuals retain the producer's floor and
coherence assumptions and are labeled diagnostic proxies, not physical bounds.
Curves remain specific to their source detector configuration. Matching
`rho` and bulk size does not establish matching pilot anchors or bulk-bin
indices; a matched DSP overlay requires those additional geometry records.

Rows and the manifest explicitly declare
`evidence_kind: conditional_screening_allowance`,
`physical_response_qualified: false`, `science_selection_eligible: false`,
and `residual_contains_sensitivity_floor: true`. The sensitivity floor is a
measurement limitation, not detected interference. Combining it with an
assumed coherence duration must not turn a quiet channel into measured RFI.
Neither a proxy above tolerance nor failure of every proxy candidate proves
physical infeasibility or justifies permanent masking. A proxy below tolerance
also does not qualify a physical threshold.

Consumers considering science selection should first call
`rfisher.response.evidence.require_science_selection_evidence(record)`.
It raises `UnqualifiedResponseError` for these rows and for old rows without
explicit evidence metadata. A matched-null detector contrast also remains
ineligible until its physical transfer is calibrated. The guard checks a
qualification declaration; it does not perform or authenticate that calibration.
Only a declared `physical_same_mask_response` with both qualification and
selection flags true and the sensitivity-floor flag false passes this boundary.
The physical selector must then minimize observing time among candidates that
meet tolerance. No admission is not a least-residual fallback or an instruction
to reject all data. In the clean limit, interference bias is zero while thermal
variance still sets the required observing time.

Use `--band 29 --family rho=63` to restrict the curve. Add
`--eta-q16 262144` for an exact stored threshold; repeat the option for more
points. An unstored word is refused, even on a flat part of the curve.
Thresholds are compared as integers, including values above floating-point
integer precision. Evaluation rows never supply calibration lookups.

The retained fraction is `kept / frames`. The uniform-loss estimate is
`T_required_uniform_years = clean_years * frames / kept`, assuming lost
frames are distributed evenly. This is an exposure calculation, not a BAO
forecast. No tolerance, false-alarm assumption, or optimizer is applied.

The Python API offers `read_forward(paths)`, `sweep(response, ...)`,
`query(response, band=..., family=..., eta_q16=...)`, and
`write_forward(response, out, ...)` in `rfisher.response.threshold`.
