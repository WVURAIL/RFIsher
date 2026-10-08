# Release index

## Science-side releases and how to replay them

Each frozen output the science side reproduces, with the commit to replay it
from (a worktree, `git worktree add <dir> <commit>`), the interpreter of
record and the row of the refactor's equivalence table (DESIGN F.2) that
reproduces it. A release directory under the workspace `results/` tree is
named, not its path. The release environment is Python 3.12.3 with
numpy 2.5.2; the capture release r5.2 was built under numpy 2.3.5 (the
dissertation environment), and the record tests hold every byte of it under
numpy 2.3 and later.

| Row | Release | What is reproduced | Replay commit | Interpreter of record |
|---|---|---|---|---|
| 1c to 1f | `archive_author_eras_2026-09-23` (science layer) | the chain, selection, screening and operating-point tables, the tolerance and worlds tables, the ledger, from pilot-proxy's characterization and the verdict (`rfisher records archive-layout --release archive_author_eras_2026_09_23`, under the frozen policy copy) | f56916a | release environment |
| 20 | `archive_no_split_2026-09-24_r2` (science layer) | the same at the off setting (`--release archive_no_split_2026_09_24_r2`) | f56916a | release environment |
| 2 | the shipped tolerance table `src/rfisher/data/tolerances/filter_scenarios_T1yr.csv@f56916a` | `rfisher tolerance build`, byte for byte, with its provenance | f56916a | release environment |
| 3 | the coarse ladder pricing of `archive_author_eras_2026-09-23` | `records/chime_atsc_2026/ladder_pricing.py` on pilot-proxy's coarse ladder | f56916a | release environment |
| 7 | the table of record (9867551a) and its v7 input (fd718463) | `rfisher records table-of-record` and `records capture-ruling --rule record`, from the capture handoff, `gain_bao.csv` and the v7 table | this commit | release environment |
| 8 | the channel 24 basis of the era redate | `records cohort-basis` | this commit | archive environment |
| 21 | `capture_ruling_a19_2026-09-25_r5_2` (49 files), and the rulings of revisions a18 to r5.1 through their rule files (`projects/chime_bao/capture_rules/`) | `rfisher records capture-release --rule r5_2` with the capture handoff and the explicit record tables, without the post-processing readings (below) | this commit | dissertation environment (numpy 2.3.5) |
| 6 | the cadence report of record (`CADENCE_REPORT.md`) | pilot-proxy's `capture cadence-report`, then `rfisher records cadence-report` with the table of record | this commit | release environment |
| 12c | the forecast-template figure of `forecast_completion_20260824_reconciliation` | `scripts/render_forecast_template_assets.py@f56916a --preserve-release-metadata` | f56916a | release environment |
| 13 | the visibility response endpoint validation | `rfisher response visibility` (`response/visibility.py`, 0d041bfd) | f56916a | baonoise environment (numpy 2.5.1) |

Post-processing is not modelled, so the replays at this commit leave out the
releases' post-processing content (stage P, 2026-10-06), which the frozen
releases keep: the credit readings `credit_readings/r3` and `r2`,
`postprocessing_sensitivity.csv`, `promotion_least_corners.csv` and
`PROMOTION_EVIDENCE.md` of r5.2, the credit columns of its
`robustness_a18.csv` and `ch24_per_bin_a19.csv`, channel 24's archive-share
reading, the amendment 8 robustness record with both credits, revision 2's
200 ns duration reading, the archive layouts' delay-filter scenarios
(`worlds.csv`) and f sigma_8 tolerance columns, and the author-eras layout
(rows 1c to 1f and 3), whose characterization booked the variance split. Every other file of row 21
is the release's byte for byte. The shipped tolerance table is now
`src/rfisher/data/tolerances/tolerance_T1yr.csv`: the no-filter dilation rows
of the archive table of row 2 (`filter_scenarios_T1yr.csv` at f56916a, csv
sha256 3985dd59), value for value.

The earlier capture revisions are frozen releases (`capture_ruling_a18_2026-09-24`
and its revisions r2 to r4, `capture_ruling_a19_2026-09-25_r5` and `_r5_1`);
their rulings are reproduced through the rule files, and their tables are not
rebuilt.

## Frozen releases with a manifest here

Each of these lives in the workspace `results/` tree, outside the repository,
and is immutable: never regenerate one in place, rename its files or change its
schema identifiers; a scientific change is a new dated release. The repository
keeps a copy of each manifest under `docs/releases/`.

| Release | Date | Manifest copy | What it holds |
|---|---|---|---|
| `forecast_completion_*` (first release) | before 2026-08-24 | `forecast_completion_first_release.manifest.json` | four all-DTV-bin evidence ledgers, the template comparison, mapping and status tables, the tolerance figures, caption and TeX summary |
| `forecast_completion_20260824_reconciliation` | 2026-08-24 | `forecast_completion_20260824_reconciliation.manifest.json` | the same 12 basenames with `epsilon_fg = 0` and one evaluation source state; it corrects the first release and does not replace it |
| `calibration_followup_2026-09-08` | 2026-09-08 | `calibration_followup_2026-09-08.manifest.json` | a fresh-draw digital protocol, frame shards, a GPU/CPU arithmetic audit and a pending physical-data plan; no operational policy |
| `calibration_next_2026-09-08` | 2026-09-08 | `calibration_next_2026-09-08.manifest.json` | a joint digital tolerance experiment (59/60 joint successes, below its 95 % target), regulatory sidecars and an era audit |
| `archive_v5_2026-09-08_corrected` | 2026-09-08 | `archive_2026-09-08_corrected.manifest.json` | the corrected 23-channel retrospective archive analysis; no channel receives an operating point |
| `calibration_progress_2026-09-09` | 2026-09-09 | `calibration_progress_2026-09-09.manifest.json` | waveform startup reconciliation, a 197/200 joint residual study and recovered producer histories |

The code that wrote the forecast-completion releases left the head on
2026-10-08 (`docs/forecast-completion.md@c7c3949` and its scripts); replay
them at f56916a as row 12c does. The physical-calibration workflow of the
calibration releases is `docs/physical-calibration.md@f56916a`. The 3.0.0
migration notes (the retired `baonoise` namespace and wrappers) are this file
at c7c3949. The dissertation keeps its own copies of the forecast-completion
releases; they are independently covered by its manifest.

New release bundles go under `releases/<application>/YYYY-MM-DD-<description>/`
in the results tree, with a README stating scope, input identities, exact
commands and the manifest contract. Ordinary regenerated results are not
releases.

## Related documentation

- [Reproducibility commands](reproducibility.md)
- [CHIME/BAO application](application-chime.md)
- [Architecture and provenance boundary](architecture.md)
