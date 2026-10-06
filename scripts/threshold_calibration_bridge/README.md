# Threshold-calibration bridge (2026-10-04)

Byte copies of the two science-side producers of the conditional calibration
package `output/threshold-calibration-bridge-2026-10-04`, kept as they ran so
that their recorded identities hold:

| File | sha256 | Recorded in |
|---|---|---|
| `threshold_bridge.py` | `49f17f32...` | `model/results/REGIONS.json` and `PLAN.json` (`source_sha256`) |
| `evaluate_scenario.py` | `eee305b2...` | `CLEAN_LIMIT_CURRENT.json` (`provenance.evaluator_sha256`) |

`threshold_bridge.py` writes the conditional coefficient regions
(`model/results/REGIONS.json`, which the dissertation vendors) from the
package's exact score summaries (`scores/`, built from pilot-proxy's
current-era scores) and the native paired-mode forecast. It runs only in the
layout it was written for: it imports `paired_mode_forecast.py` from
`output/native-threshold-expansion-2026-10-04/model-review` (which reads this
repository's bank code) and reads the RadioFisher checkout at a fixed path.
Neither is part of this repository, so it is not run here.

`evaluate_scenario.py` checks a declared constant and score coefficient
against the bias and precision bounds of every required parameter, on the
saved regions. It reads only the package's `model/results/REGIONS.json` and
`scores/`, and it selects no threshold. Run it from the package directory, as
`SCENARIO_USAGE.txt` there says. `tests/test_threshold_bridge.py` reproduces
the package's zero-residual scenario at the current thresholds
(`CLEAN_LIMIT_CURRENT.json`) from its 24 input rows, vendored under
`tests/golden/threshold_bridge/`.
