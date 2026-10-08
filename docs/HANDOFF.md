# The handoff: what the science side reads

This page is for an engineer who wants to know what this repository reads
from the detector's output, and where in the code each step is. The detector
side ([pilot-proxy](https://github.com/WVURAIL/pilot-proxy)) has the matching
page, `docs/HANDOFF.md` there, for what crosses the boundary and how it is
made. The current method is the tolerance, the fixed-precision calendar
(`FIXED_PRECISION_CALENDAR.md`) and the capture ruling of record
(`rfisher records`).

## What is read

Files only:

- a detector handoff directory in the layout `operating_characteristic_v1`
  (`oc_table.csv`, `oc_summary.csv`, `manifest.json`), checked by
  `rfisher.verdict.handoff` against the vendored schema
  (`src/rfisher/data/schemas/operating_characteristic_v1.schema.json`, pinned
  by `tests/test_schemas.py`) and against the residual reference and shapes
  the science profile declares. `rfisher response threshold` exports the
  saved curves of a complete handoff ([threshold_response.md](threshold_response.md)),
  and the frozen archive layouts (`rfisher records archive-layout`) price an
  archive handoff with one `tolerances.csv`;
- a capture handoff in the layout `capture_operating_characteristic_v1`, read
  by the capture records below.

`rfisher.verdict` imports nothing from `rfisher.forecast`, `rfisher.tolerance`
or `rfisher.records` (`tests/verdict/test_verdict_boundary.py`). Cosmology
enters through `rfisher.forecast` and `rfisher.tolerance`, and two things
leave them: `tolerances.csv` and the BAO-band coherence gain, the latter for
the capture ruling of record only.

## Reading path

| Order | Module | Question it answers |
|---|---|---|
| 1 | `src/rfisher/science_model.py` | What must a science model supply? |
| 2 | `src/rfisher/tolerance/rule.py` | How does the forecast become `r_tol`? (the only cosmology step) |
| 3 | `src/rfisher/tolerance/table.py` | What crosses into the records? |
| 4 | `src/rfisher/verdict/handoff.py` | How are the detector's files checked? |

The capture records of the 2026 campaign, in order:

| Order | Module | What it does |
|---|---|---|
| 1 | `src/rfisher/records/chime_atsc_2026/capture_oc.py` | writes the capture handoff from pilot-proxy's `capture_operating_characteristic_v1` and the measurement tables of lanes pilot-proxy does not run |
| 2 | `src/rfisher/records/chime_atsc_2026/capture_handoff.py` | reads it, checks every file against the manifest and the detector constants against the record's, and refuses the record's own tables inside it |
| 3 | `src/rfisher/records/chime_atsc_2026/capture_ruling.py` | the capture ruling of record, its logic as the release producer wrote it, under a rule file (`projects/chime_bao/capture_rules/`) |

The record's own tables (the table of record and its v7 input) and the
BAO-basis coherence times are explicit inputs of those records
(`--record-table`, `--input-table`, `--gain-bao`), not handoff files.

The frozen archive layouts price under a frozen copy of the registers
(`src/rfisher/records/chime_atsc_2026/data/policy_2026_archive/`) with the
candidate pricing and selector of `rfisher.verdict.interval`, so a change of
the project registers never moves the layouts of record. The historical
scalar screen that once read this handoff band by band
(`src/rfisher/verdict/screening.py@54f3adb`) is not part of the current
method.
