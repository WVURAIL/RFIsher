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

Use `--band 29 --family rho=63` to restrict the curve. Add
`--eta-q16 262144` for an exact stored threshold; repeat the option for more
points. An unstored word is refused, even on a flat part of the curve.
Thresholds are compared as integers, including values above floating-point
integer precision. Evaluation rows never supply calibration lookups.

The retained fraction is `kept / frames`. The uniform-loss estimate is
`T_required_uniform_years = clean_years * frames / kept`, assuming lost
frames are distributed evenly. This is an exposure calculation, not a BAO
forecast. No tolerance, false-alarm assumption, or optimizer is applied.
The new complete handoff is forward-only; `verdict archive` refuses it.

The Python API offers `read_forward(paths)`, `sweep(response, ...)`,
`query(response, band=..., family=..., eta_q16=...)`, and
`write_forward(response, out, ...)` in `rfisher.response.threshold`.
