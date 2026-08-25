# CHIME/BAO reference application

RFIsher ships one complete reference application: the integration-time cost
and contamination-residual tolerance of ATSC DTV masking for a CHIME 21 cm BAO
forecast. This application demonstrates the framework; it does not make the
installed target metric independent of BAO.

## Fiducial forecast

The default bank follows the CHIME Overview forecast in Amiri et al. (2022,
Appendix A):

- as-built 4 by 256 cylinder geometry;
- 31,000 square degrees;
- total system temperature of 55 K;
- Planck-2018 cosmology with explicit baryon, cold-dark-matter, and neutrino
  densities;
- CHIME Overview H I evolution models;
- one BAO amplitude per redshift bin; and
- foreground setting `epsilon_fg = 0` for the released CHIME-2022 bank.

The unmasked calculation is checked before any masking model is applied. At
one on-sky year it reproduces the published per-bin fractional `D_V` errors of
0.47--1.03%.

The package also includes a matched P-ACT-LB cosmology bank. Strict-v2
Bull-2015 Planck-2013 banks at `epsilon_fg = 1e-6` and `1e-5` remain research
comparison artifacts rather than installed defaults.

## Time convention

All reference tables quote on-sky years at the Overview normalization:

```text
1 on-sky year = 8,760 hours.
```

The CSV files carry raw hours. The demonstrated 2019-practice duty factor is
0.152, so an on-sky duration is about 6.6 times shorter than the corresponding
calendar duration at that duty factor. Do not double-count the additional
night masking reported by Amiri et al. (2025), because its RFI component
overlaps the scenarios evaluated here.

Absolute Fisher times inherit the idealizations of the instrument and
foreground model. Relative masking penalties are the principal comparison.

## Masking input

The legacy detector-rate scenario uses the quarterly table distributed as
package data. Exposure-weighted historical fractions include approximately:

- channel 17: 33%;
- channel 31: 24%;
- channels 32 and 35: 14%;
- channel 33: 10%; and
- most remaining channels: at or below 4%.

Channels 24 and 30 were refused because their calibrated zero points were
unavailable and the transmitter was effectively always on. The table assigns
them a 97% placeholder, placing them above the default excision threshold.

These values come from a known half-sample-rate-mistuned detector epoch. They
are not DTV occupancy measurements. The reference outputs retain them as a
historical reproducibility baseline. Use corrected survey products for any
current occupancy statement. The full detector and product distinction is in
[masking-cost.md](masking-cost.md).

## System-temperature input

The absolute CHIME calibration file is not distributed in this repository.
It contains 400--800 MHz measurements from two 2019 calibrator transits, with
a band median of 54.6 K and a DTV-band median of 56.5 K. The forecast uses
`Tsys_tot = 55 K`, which lies inside the measured 10th--90th percentile.

Because the released comparisons are expressed as ratios, the missing
absolute calibration file changes no verdict. It is needed for absolute shelf
and floor conversion and for an independent system-temperature check.
`scripts/tsys_calibration.py` performs that validation when the file is
available.

## Masking-only results

Run `scripts/run_forecast.py` to regenerate `out/required_times.csv`,
`out/bin_level_targets.csv`, and `out/results.md`.

| Scenario | Time penalty relative to clean | Time for 2% transverse distance at `z = 1.40--1.50` |
|---|---:|---:|
| No masking | 1.00x | 0.32 on-sky yr |
| Legacy detector rate table | 1.03x | 0.42 on-sky yr |
| 50% of the DTV band masked | 1.15x | 0.63 on-sky yr |
| 97% of the DTV band masked | 1.25x | about 10 on-sky yr |
| 50% of the entire CHIME band masked | 2.00x | not reported |
| Channel 30 excised | 1.008x | 0.36 on-sky yr |
| Channel 30 retained, Fourier convention | 1.06x | 1.96 on-sky yr |

The legacy rate-table mask costs about 3% at survey level and about 34% for
the distance measurement in the most affected bin. Retaining a slice masked
97% of the time requires about 33 times the integration to recover its clean
depth. Excision instead costs a 16% volume loss in one redshift bin and about
0.8% at survey level.

Even masking 97% of the full DTV band increases the survey-level time by only
about 25%, because frequencies below 470 MHz and above 608 MHz carry much of
the total BAO detection information. This survey-wide statement does not make
the affected redshift bins scientifically interchangeable with the clean
case.

## Fiducial comparisons

The matched Planck-2018 and P-ACT-LB banks require 208.8 and 186.9 clean
on-sky hours, respectively, for the survey-level five-sigma target. Across
the survey and both reported bin-level metrics, masking penalties differ by
at most 0.420% between those cosmologies.

In the Bull-2015 foreground comparison, increasing `epsilon_fg` by a factor of
ten moves the clean survey time by 3.1% and the tested masking penalties by at
most 1.12%.

## Contamination-residual result

The masking-only tables do not decide whether a detector threshold is useful.
For the measured channel-35 scalar chain, adding the contamination residual
moves the legacy rate-table survey penalty from 1.032x to 1.133x and the
`z = 1.40--1.50` penalty from 1.347x to 2.14x. The full budget, interval, and
coherence assumptions are in
[contamination-residuals.md](contamination-residuals.md).

The model-only bias release evaluates four unit-normalized analytic residual
families over every DTV-overlapping redshift bin. It is a sensitivity envelope,
not a measured template selection. See the
[forecast-completion contract](forecast-completion.md) and
[release index](releases.md).

## Generated figures

The main masking-cost driver writes:

- `fig1_significance_vs_time`: survey significance versus observing time;
- `fig2_required_time_vs_masking`: years to the BAO targets versus masked DTV
  fraction;
- `fig3_channel_masking`: per-channel masked fractions and retained-time
  multipliers; and
- `fig4_perbin_significance`: the redshift-bin significance profile.

The dissertation-specific driver under `scripts/dissertation/` writes the
time-versus-masking, policy-case, convergence, two-walls, and analytic-template
figures from their committed tables.

## Application-specific caveats

- The 3- and 5-sigma amplitude metrics are BAO detection statements, not
  distance-precision statements. Per-bin dilation errors are reported
  separately.
- Masking is a per-frequency duty cycle and excision is a scalar volume loss.
  The model omits the full spectral window from frequency gaps.
- A contamination residual treated as excess variance must be incoherent.
  Coherent contamination uses the bias-response workflow.
- The four analytic residual shapes are hypotheses normalized to thermal
  noise, not empirical visibility templates.
- Frequency-, baseline-, and sidereal-dependent templates require new
  authenticated telescope data and a response interface exposing those
  coordinates.
- Physical densities are explicit and must be supplied as a complete triplet
  when overridden. Total matter includes massive neutrinos unless the source
  explicitly declares otherwise.

The numerical tables are guarded by `scripts/check_paper_numbers.py` and
`scripts/check_dissertation_numbers.py`. Exact commands are in
[reproducibility.md](reproducibility.md).
