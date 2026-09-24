# Descriptive temporal moments on native voltages

`rfisher_results.validation.lag_moments` provides non-circular temporal sufficient
sums for complex [time, series] arrays. `lag_moments` always uses late times
conjugate(early), intersects both samples' declared support without compressing
time, excludes nonfinite values and retains crossings of arbitrary storage
boundaries. `summarize_lags` returns native raw/centered population moments and
dimensionless centered/uncentered normalizations. `frame_moments` retains a short
terminal block and marks complete blocks separately.

Applying the same routines to instantaneous complex voltage cross-products
measures **visibility fluctuations**, a different observable from voltage
correlation. Visibility-series centering subtracts each overlapping window's
visibility mean; it does not center the underlying voltages. Neither path
estimates a physical covariance or confidence interval without a calibrated
measurement and statistical model.

The study `../../results/inband_lag_diagnostics_2026-09-09/README.md` records an
explicitly frozen descriptive plan, authenticated retained bytes, every lag's
sums/support, and an independent integer recount. The example uses all 15 saved
frequency bins, 32 selected inputs, three previously position-selected visibility
pairs and lags up to 32,768 native samples. Its binned visibility diagnostic uses
the **16,384-sample upgrade target**, including a separately reported short tail.
The one already inspected 0.294 s event is not independent validation and does
not establish minute-to-hour coherence, source identity or physical cleaner
transfer. The original event remains excluded from prospective validation.

Run the targeted tests with `python -m pytest -q tests/test_lag_moments.py`.
The measurement and plotting scripts are `scripts/measure_inband_lags_v1.py`
and `scripts/plot_inband_lags_v1.py`; see the study README for its fixed-source
reproduction contract. They require CPU only and single-thread BLAS settings.
