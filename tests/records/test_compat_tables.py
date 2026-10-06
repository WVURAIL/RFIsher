"""The frozen archive layout, on a two-band golden extract of both archive releases.

The author-eras release, whose characterization booked the variance split, is retired with stage P; its extract stays
in the golden, and only the no-split release r2 is compared.

The golden (tests/golden/records/archive_layout_18_33.json.gz) holds, for
bands 18 and 33, the detector's handoff inputs and the rows the releases
wrote. The layout writer's rows must equal the frozen ones cell for cell.
The whole layout, every band and file, is compared at the gate.

Retired with stage P (2026-10-06: post-processing is not modelled, and the
growth rate sets no tolerance): the delay-filter scenarios (``worlds.csv`` and
the ledger's ``worlds`` section) and the f sigma_8 tolerance columns. The
golden keeps the frozen rows whole; :func:`retired` projects those fields out
before the comparison, and every other cell is compared as before.
"""
from __future__ import annotations

import csv
import gzip
import io
import json
import math
from pathlib import Path

import pytest

from rfisher import policy
from rfisher.forecast.radiofisher_bao.model import RadioFisherBAO, packaged_table
from rfisher.records.chime_atsc_2026 import compat_tables as ct
from rfisher.records.chime_atsc_2026 import ladder_pricing
from rfisher.tolerance import table as tolerance_table
from rfisher.verdict import handoff

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "projects" / "chime_bao"
GOLDEN = ROOT / "tests" / "golden" / "records" / "archive_layout_18_33.json.gz"


@pytest.fixture(scope="module")
def golden():
    return json.loads(gzip.decompress(GOLDEN.read_bytes()))


RETIRED_COLUMNS = ("r_tol_fs8", "fs8_status")
RETIRED_SECTIONS = ("worlds",)


def retired(frozen):
    """A frozen row, ledger record or tradeoffs row without the retired fields."""
    if "sections" in frozen:
        sections = {k: v for k, v in frozen["sections"].items() if k not in RETIRED_SECTIONS}
        sections["tolerance"] = retired(sections["tolerance"])
        return {**frozen, "sections": sections}
    return {k: v for k, v in frozen.items()
            if k not in RETIRED_COLUMNS and not k.startswith("growth_")}


def _typed(rows, key):
    spec = handoff.schema()[key]
    kinds = {c["name"]: c["type"] for c in spec}
    return [{k: handoff._cast(kinds[k], v) for k, v in r.items()} for r in rows]


def _inputs(golden, release):
    doc = golden["releases"][release]
    bands = {b["band_id"]: b for b in doc["manifest"]["bands"]
             if b["band_id"] in golden["bands"]}
    summary, fine, ladder, ledger, rule = {}, {}, {}, {}, {}
    for band, entry in doc["bands"].items():
        summary[band] = _typed(entry["summary"], "x-oc-summary-columns")
        rows = _typed(entry["rows"], "x-oc-table-columns")
        fine[band] = [r for r in rows if r["candidate_set"] == "fine_surface"]
        ladder[band] = [r for r in rows if r["candidate_set"] == "coarse_ladder"]
        ledger[band] = entry["record"]
        tol = entry["tolerance"][0]
        rule[band] = {**tol, "r_tol": float(tol["r_tol"]) if tol["r_tol"]
                      else math.nan}
    return ct.Inputs(
        release=release, characterization=ROOT, manifest=doc["manifest"],
        summary=summary, fine=fine, coarse={}, ladder=ladder, ledger=ledger,
        ledger_names={}, run={}, chain_csv=((), []), tolerances=rule,
        per_bin=tolerance_table.load(packaged_table()),
        model=RadioFisherBAO(PROJECT), policy=ct.frozen_policy(),
        bands=bands)


def test_recorded_rank_policy_is_independent_of_the_current_policy():
    assert ct.frozen_policy().value("selector.fine_rank") == "all"
    assert policy.load(PROJECT).value("selector.fine_rank") == 63


def _render(row):
    """A table cell as the releases' _write_csv writes it."""
    return {k: ("" if v is None or (isinstance(v, float) and not math.isfinite(v))
                else repr(v) if isinstance(v, float) else str(v))
            for k, v in row.items()}


def _json(value):
    """A section as the ledger writes it (NaN becomes null)."""
    return json.loads(json.dumps(ct._jsonable(value)))


RELEASES = pytest.mark.parametrize("release", ct.RELEASES)


@RELEASES
def test_channel_tolerances_are_the_frozen_rows(golden, release):
    inp = _inputs(golden, release)
    for band in golden["bands"]:
        frozen = golden["releases"][release]["bands"][band]["frozen"]
        assert _render(ct.channel_tolerance_row(inp, band)) == \
            retired(frozen["channel_tolerances"][0])


@RELEASES
def test_selection_and_screening_are_the_frozen_rows(golden, release):
    inp = _inputs(golden, release)
    for band in golden["bands"]:
        frozen = golden["releases"][release]["bands"][band]["frozen"]
        priced = ct.price(inp, band)
        row = ct.selection_row(inp, priced)
        assert list(row) == list(ct.SELECTION_COLUMNS)
        assert _render(row) == frozen["selection"][0]
        result, extra = ct.screening_for(inp, band, priced)
        assert _render({"channel": int(band), **result.as_row()}) == \
            frozen["screening"][0]
        assert _json({**result.as_row(), **extra}) == \
            frozen["ledger"]["sections"]["screening"]
        section = ct.selection_section(inp, priced, row)
        assert _json(section) == frozen["ledger"]["sections"]["selection"]


@RELEASES
def test_the_ledger_record_is_the_frozen_one(golden, release):
    inp = _inputs(golden, release)
    for band in golden["bands"]:
        frozen = golden["releases"][release]["bands"][band]["frozen"]
        priced = ct.price(inp, band)
        tol = ct.channel_tolerance_row(inp, band)
        sel = ct.selection_row(inp, priced)
        result, extra = ct.screening_for(inp, band, priced)
        science = {"tolerance": {k: v for k, v in tol.items() if k != "channel"},
                   "selection": ct.selection_section(inp, priced, sel),
                   "operating": inp.ledger[band]["sections"]["knee"],
                   "screening": {**result.as_row(), **extra}}
        assert _json(ct.ledger_record(inp, band, priced, science)) == \
            retired(frozen["ledger"])


@RELEASES
def test_the_ladder_pricing_is_the_frozen_science(golden, release):
    inp = _inputs(golden, release)
    for band in golden["bands"]:
        frozen = golden["releases"][release]["bands"][band]["frozen"]
        summary = next(s for s in inp.summary[band]
                       if s["candidate_set"] == "coarse_ladder")
        rows = ladder_pricing.ladder_rows(band, inp.ladder[band], summary,
                                          ct.channel_tolerance_row(inp, band))
        buf = io.StringIO()
        keys = list(rows[0])
        writer = csv.DictWriter(buf, fieldnames=keys, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: ("" if v is None or (isinstance(v, float) and
                                                     not math.isfinite(v))
                                 else repr(v) if isinstance(v, float) else v)
                             for k, v in row.items()})
        got = list(csv.DictReader(io.StringIO(buf.getvalue())))
        expected = [retired(f) for f in frozen["tradeoffs"]]
        assert [{k: r.get(k, "") for k in f} for r, f in
                zip(got, expected)] == expected
        assert not any(k.startswith("growth_") for k in got[0])
        assert any(k.startswith("dilation_") for k in got[0])


def test_a_feasible_point_is_not_reproducible_from_the_handoff(golden):
    inp = _inputs(golden, ct.RELEASES[0])
    inp.tolerances["18"] = {**inp.tolerances["18"], "r_tol": 1e9}
    with pytest.raises(ct.NotReproducible, match="feasible"):
        ct.price(inp, "18")


def test_the_screening_rule_is_the_releases(golden):
    inputs = ct.ScreeningInputs(
        off_era=False, selection_status="feasible", tolerance_fraction=0.5,
        masked_fraction=0.2, survey_flag_rate=0.5, floor_evidence="measured",
        correlation_quality="measured")
    result = ct.screen(inputs)
    assert result.screening_class == ct.RECOVERY
    assert result.reasons[0] == ("selected point inside tolerance on the "
                                 "dilation tier (R = 0.5)")
    off = ct.screen(ct.ScreeningInputs(
        off_era=True, selection_status="refused", tolerance_fraction=math.nan,
        masked_fraction=math.nan, survey_flag_rate=0.1,
        floor_evidence="stated", correlation_quality="refused",
        refusal="no selection", claim_status=""))
    assert off.screening_class == ct.OFF_ERA
    assert ct._off_dates({"2021-11": "sign-on"}) == ("2021-10", "")
    assert ct._off_dates({"2024-12": "sign-off"}) == ("", "2024-12")
    assert ct._off_dates({"2020-01": "sign-on"}) == ("2019-12", "")


def test_the_command_refuses_an_existing_directory_and_a_wrong_record(
        tmp_path):
    from rfisher.cli import main

    with pytest.raises(SystemExit):
        main(["records", "archive-layout", "--release",
              "archive_no_split_2026_09_24_r2", "--characterization",
              str(tmp_path), "--tolerances", str(tmp_path), "--project",
              str(PROJECT), "--out", str(tmp_path)])
    golden = ROOT / "tests" / "golden" / "handoff" / "archive"
    with pytest.raises(SystemExit):   # the author-eras layout (booked variance split) is retired
        main(["records", "archive-layout", "--release",
              "archive_author_eras_2026_09_23", "--characterization",
              str(golden), "--tolerances", str(tmp_path / "t.csv"),
              "--project", str(PROJECT), "--out", str(tmp_path / "new2")])
