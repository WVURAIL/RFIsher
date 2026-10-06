# The handoff: what the science side does with the detector's files

This page is for an engineer who wants to know what this repository computes
from the detector's output, and where in the code each step is. The detector
side ([pilot-proxy](https://github.com/WVURAIL/pilot-proxy)) has the matching
page, `docs/HANDOFF.md` there, for what crosses the boundary and how it is
made.

## What the verdict reads

Files only, and two of them in kind:

- one detector handoff directory in the layout `operating_characteristic_v1`
  (`oc_table.csv`, `oc_summary.csv`, `manifest.json`), checked against the
  vendored schema (`src/rfisher/data/schemas/operating_characteristic_v1.schema.json`,
  pinned by `tests/test_schemas.py`) and against the residual reference and
  shapes the science profile declares;
- one tolerance file, `tolerances.csv`, one row per band with `r_tol`, its
  binding parameter and bin and the tolerance basis, in the rule scenario (no
  delay filter); a row of any other role is refused.

`rfisher.verdict` imports nothing from `rfisher.forecast`, `rfisher.tolerance`
or `rfisher.records`, and a verdict run opens no data file but those, besides the project's registers
(`tests/verdict/test_verdict_boundary.py`). Cosmology enters through
`rfisher.forecast` and `rfisher.tolerance`, and two things leave them:
`tolerances.csv`, for both verdicts, and the BAO-band coherence gain, for the
capture ruling of record only.

## Reading path

| Order | Module | Question it answers |
|---|---|---|
| 1 | `src/rfisher/science_model.py` | What must a science model supply? |
| 2 | `src/rfisher/tolerance/rule.py` | How does the forecast become `r_tol`? (the only cosmology step) |
| 3 | `src/rfisher/tolerance/table.py` | What crosses into the verdict? |
| 4 | `src/rfisher/verdict/handoff.py` | How are the detector's files checked? |
| 5 | `src/rfisher/verdict/interval.py` | `eta_sci`, the deployable set and the selector |
| 6 | `src/rfisher/verdict/screening.py` | keep, excise or undetermined |

The capture records of the 2026 campaign, in order:

| Order | Module | What it does |
|---|---|---|
| 1 | `src/rfisher/records/chime_atsc_2026/capture_oc.py` | writes the capture handoff from pilot-proxy's `capture_operating_characteristic_v1` and the measurement tables of lanes pilot-proxy does not run |
| 2 | `src/rfisher/records/chime_atsc_2026/capture_handoff.py` | reads it, checks every file against the manifest and the detector constants against the record's, and refuses the record's own tables inside it |
| 3 | `src/rfisher/records/chime_atsc_2026/capture_ruling.py` | the capture ruling of record, its logic as the release producer wrote it, under a rule file (`projects/chime_bao/capture_rules/`) |

The record's own tables (the table of record and its v7 input) and the
BAO-basis coherence times are explicit inputs of those records
(`--record-table`, `--input-table`, `--gain-bao`), not handoff files.

## Selection

This section describes the selector as the code has it at this commit.
Later changes to how a threshold is chosen are made here and in the code
together.

For one band, family and scenario (`rfisher.verdict.interval`):

- every candidate of the family is priced against the scenario's tolerance:
  `R = r_sys / r_tol`, feasible when `r_sys <= r_tol`
  (`selection.tolerance_equality_is_feasible` keeps equality feasible), and its
  cost is `C = (1 + r_var) / (1 - f)` (`cost`);
- `eta_sci` is the largest feasible threshold, the science limit;
- the deployable set is the feasible candidates with `eta` at or above
  `max(eta_pfa, eta_eval)`: the detector's false-alarm limit where its
  handoff has one, otherwise the tightest evaluable threshold (the summary
  says which, `lower_bound_source`);
- the selector takes the candidates of the deployable set whose cost is within
  `selection.cost_plateau_ratio` (1.02) of the least, then the least by
  `selection.tie_break`: the kept residual, the masked fraction, then the
  detector's declared candidate order (`candidate_order`, rank then
  multiplier);
- the fine families it reads are set by `selector.fine_rank`
  (`projects/chime_bao/selector_policy.json`), read in one place,
  `fine_candidates`; its value is 63, the detector's fixed median rank.
  The threshold multiplier is the only per-channel parameter.

`rfisher.verdict.screening` then reads the families of a band in the declared
precedence (`selector.precedence`): a refused tolerance or a refused detector
family first, then keep, excise and undetermined. No post-processing of the
residual is modelled: no delay filter, ground filter or other downstream
suppression enters a verdict. The archive's frozen release layouts price
under a frozen copy of these registers
(`src/rfisher/records/chime_atsc_2026/data/policy_2026_archive/`), so a change
of the selector moves the verdict and never the layouts of record.
