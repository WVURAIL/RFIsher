"""``tab:census``: the transmitter-census envelope per physical channel.

The synthetic export exercises every path the reduction has: a channel whose
nearest licence-matched facility is farther than its nearest envelope record,
a nearest tie broken by callsign, a strongest-ERP tie broken by range, a
matched row carrying no ERP, an unmatched row carrying one, a channel with
records but no match, channels with no records at all, a co-located pair that
rounds onto one site, a record outside 14--36, and each of the schema
validations. The real export is read only when it is on this machine.
"""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from rfisher_results.archive.report import census, core

COLUMNS = ("schema_version", "rf_channel", "callsign", "service_class", "detectability_db", "distance_km",
           "bearing_deg", "frequency_tolerance", "chime_ch_index", "nominal_pilot_mhz", "city", "state_prov",
           "erp_kw", "evidence_status")

LICENSED = "reported_on_air_licensed"
CANDIDATE = "licensed_candidate"
UNVERIFIED = "reported_on_air_unverified"

# ch, callsign, service class, distance, bearing, erp, evidence
ROWS = [
    # channel 14: the nearest record is an unverified translator nearer than either matched row; the two
    # matched rows tie at 100.0 km (callsign breaks it) and share a site with a record that rounds onto it
    (14, "ZBBB-DT", "Full-power", 100.0, 10.0, "5.000", LICENSED),
    (14, "K14XX-D", "Translator (LPTV)", 50.0, 10.0, "", UNVERIFIED),
    (14, "ZAAA-DT", "Class A", 100.0, 10.0, "20.000", CANDIDATE),
    (14, "K14YY-D", "Translator (LPTV)", 100.04, 10.04, "", UNVERIFIED),
    # channel 15: a licence-matched row that carries no ERP
    (15, "ZCCC-1", "Relay", 200.0, 20.0, "", LICENSED),
    # channel 16: records but no licence match, and an unmatched row carrying an ERP
    (16, "K16ZZ-D", "Translator (LPTV)", 300.0, 30.0, "7.500", UNVERIFIED),
    # channel 17: two matched rows at the same ERP; the nearer one is the strongest facility
    (17, "ZDDD-LP", "LPTV", 10.0, 1.0, "1.000", CANDIDATE),
    (17, "ZEEE-LP", "Low-power (LPTV)", 20.0, 2.0, "1.000", CANDIDATE),
    # outside the monitored allocations: excluded from every count, never dropped silently
    (13, "ZFFF-DT", "Full-power", 5.0, 5.0, "9.000", UNVERIFIED),
]


def _write(tmp_path: Path, rows=ROWS, *, schema=census.SCHEMA_VERSION, provenance: str | None = None) -> Path:
    path = tmp_path / "census.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        for ch, callsign, service, distance, bearing, erp, evidence in rows:
            writer.writerow({"schema_version": schema, "rf_channel": ch, "callsign": callsign,
                             "service_class": service, "detectability_db": "", "distance_km": distance,
                             "bearing_deg": bearing, "frequency_tolerance": "None specified", "chime_ch_index": "",
                             "nominal_pilot_mhz": "nan", "city": "Somewhere", "state_prov": "BC", "erp_kw": erp,
                             "evidence_status": evidence})
    if provenance is not None:
        (tmp_path / "PROVENANCE.md").write_text(provenance, encoding="utf-8")
    return path


def _fragment(tmp_path, monkeypatch, **kwargs):
    monkeypatch.setenv(census.ENV, str(_write(tmp_path, **kwargs)))
    # build() reads nothing from the run: an empty one is enough, which is the contract this asserts
    return census.build(core.Run(tmp_path, {}, ()))


def _values(frag):
    return {n.key: n.value for n in frag.numbers}


def _row_count(frag):
    """Terminated table lines: the header row, 23 channel rows and the band row (the two-line
    ``\\shortstack`` headers carry ``\\\\`` of their own, so counting them will not do)."""
    return sum(1 for line in frag.tex.splitlines() if line.endswith(r"\\"))


def _cells(frag, first):
    line = next(x for x in frag.tex.splitlines() if x.startswith(f"{first} &"))
    return [c.strip() for c in line[:-2].split("&")]


def test_census_path_prefers_the_environment(tmp_path, monkeypatch):
    monkeypatch.delenv(census.ENV, raising=False)
    assert census.census_path() == census.DEFAULT_CSV
    monkeypatch.setenv(census.ENV, str(tmp_path / "elsewhere.csv"))
    assert census.census_path() == tmp_path / "elsewhere.csv"


def test_per_channel_reduction_and_tie_breaks(tmp_path, monkeypatch):
    frag = _fragment(tmp_path, monkeypatch)
    v = _values(frag)
    # channel 14: 4 records, 2 primary (Full-power + Class A), 2 secondary, 2 matched
    assert _cells(frag, "14") == ["14", "4", "2", "2", "2", "ZAAA-DT", "100.0", "10.0", "20.0"]
    assert v["ch03.census.records.ch14"] == 4 and v["ch03.census.primary.ch14"] == 2
    assert v["ch03.census.secondary.ch14"] == 2 and v["ch03.census.matched.ch14"] == 2
    # the 100.0 km tie between ZBBB-DT and ZAAA-DT breaks on the callsign
    assert v["ch03.census.nearest_matched.ch14"] == "ZAAA-DT"
    assert v["ch03.census.erp_max_kw.ch14"] == 20.0 and v["ch03.census.erp_max_callsign.ch14"] == "ZAAA-DT"
    # the nearest envelope record is nearer than the nearest matched one: recorded, not printed
    assert v["ch03.census.nearest_record.ch14"] == "K14XX-D"
    assert v["ch03.census.nearest_record_km.ch14"] == 50.0
    assert v["ch03.census.nearest_record_evidence.ch14"] == UNVERIFIED
    assert "K14XX-D" not in frag.tex
    # channel 17: the ERP tie breaks to the nearer facility, and 1.000 kW prints to three significant figures
    assert _cells(frag, "17")[5:] == ["ZDDD-LP", "10.0", "1.0", "1.00"]
    assert v["ch03.census.erp_max_callsign.ch17"] == "ZDDD-LP"
    assert next(n for n in frag.numbers if n.key == "ch03.census.erp_max_kw.ch17").precision == 2


def test_absent_facilities_print_the_dash(tmp_path, monkeypatch):
    frag = _fragment(tmp_path, monkeypatch)
    v = _values(frag)
    d = core.DASH
    # channel 15: matched but no ERP -- the facility prints, the ERP dashes
    assert _cells(frag, "15") == ["15", "1", "0", "1", "1", "ZCCC-1", "200.0", "20.0", d]
    assert "ch03.census.erp_max_kw.ch15" not in v
    # channel 16: records but no licence match -- all four facility cells dash
    assert _cells(frag, "16") == ["16", "1", "0", "1", "0", d, d, d, d]
    assert "ch03.census.nearest_matched.ch16" not in v
    # channel 20: no record at all -- the counts are zero and the facility cells dash
    assert _cells(frag, "20") == ["20", "0", "0", "0", "0", d, d, d, d]
    assert v["ch03.census.records.ch20"] == 0
    assert "ch03.census.nearest_record.ch20" not in v


def test_band_row_sites_and_notes(tmp_path, monkeypatch):
    frag = _fragment(tmp_path, monkeypatch)
    v = _values(frag)
    # 8 in-band records (the channel-13 row is excluded), 2 primary, 6 secondary, 5 matched
    assert _cells(frag, "14--36") == ["14--36", "8", "2", "6", "5", "ZDDD-LP", "10.0", "1.0", "20.0"]
    assert v["ch03.census.records"] == 8 and v["ch03.census.matched"] == 5
    assert v[f"ch03.census.{UNVERIFIED}"] == 3 and v[f"ch03.census.{LICENSED}"] == 2
    assert v[f"ch03.census.{CANDIDATE}"] == 3
    # (100.04, 10.04) rounds onto (100.0, 10.0): six sites in band, two of them on channel 14
    assert v["ch03.census.sites"] == 6
    rows, _, _ = census.summarise(census.read_census(tmp_path / "census.csv"))
    assert {r["channel"]: r["sites"] for r in rows}[14] == 2
    assert v["ch03.census.channels"] == 23 and v["ch03.census.max_distance_km"] == 300.0
    assert v["ch03.census.channels_without_match"] == 20            # every channel but 14, 15 and 17
    assert v["ch03.census.channels_nearest_matched_farther"] == 1    # channel 14 only
    assert v["ch03.census.schema_version"] == census.SCHEMA_VERSION
    assert frag.tex.count("\\midrule") == 2 and _row_count(frag) == 25   # header + 23 channels + the band row
    notes = " | ".join(frag.notes)
    assert "1 licence-matched record(s) carry no erp_kw" in notes
    assert "1 record(s) carry an erp_kw without a licence-matched evidence state" in notes
    assert "1 export record(s) lie outside physical channels 14--36 (channel(s) [13])" in notes
    assert "no licence-matched row on channel(s) 16, 18, 19, 20" in notes
    assert "on 1 of 23 channels the nearest licence-matched facility is farther" in notes


def test_provenance_digest_is_checked(tmp_path, monkeypatch):
    frag = _fragment(tmp_path, monkeypatch)
    assert "no PROVENANCE.md digest was found" in " | ".join(frag.notes)
    digest = next(n.value for n in frag.numbers if n.key == "ch03.census.export_sha256")
    assert len(digest) == 64
    frag = _fragment(tmp_path, monkeypatch, provenance=f"the export has SHA-256\n`{digest}`\n")
    assert "the export matches the sha256 PROVENANCE.md records for it" in " | ".join(frag.notes)
    assert [p.name for p in frag.inputs] == ["census.csv", "PROVENANCE.md"]
    frag = _fragment(tmp_path, monkeypatch, provenance=f"SHA-256 `{'a' * 64}`\n")
    assert "WARNING: PROVENANCE.md records sha256" in " | ".join(frag.notes)


@pytest.mark.parametrize("bad, message", [
    ([(14, "Z", "Full-power", 1.0, 2.0, "", "reported_on_air_maybe")], "unsupported evidence_status"),
    ([(14, "Z", "Booster", 1.0, 2.0, "", UNVERIFIED)], "unknown service_class"),
    ([(14, "Z", "Full-power", "nan", 2.0, "", UNVERIFIED)], "non-finite range or bearing"),
])
def test_a_row_the_schema_does_not_describe_raises(tmp_path, bad, message):
    with pytest.raises(ValueError, match=message):
        census.read_census(_write(tmp_path, rows=bad))


def test_an_absent_export_says_where_it_should_be(tmp_path):
    with pytest.raises(FileNotFoundError, match=r"nothing to render without it.*RFISHER_CENSUS_CSV"):
        census.read_census(tmp_path / "not-here.csv")


def test_a_foreign_schema_or_a_missing_column_raises(tmp_path):
    with pytest.raises(ValueError, match="unsupported census schema"):
        census.read_census(_write(tmp_path, schema="dtv_transmitter_census_v2"))
    path = tmp_path / "thin.csv"
    path.write_text("rf_channel,callsign\n14,Z\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing columns"):
        census.read_census(path)


# ------------------------------------------------------------------ the frozen export
REAL = census.DEFAULT_CSV
real_only = pytest.mark.skipif(not REAL.is_file(), reason=f"the frozen dtv-census export is not on this machine: {REAL}")


@real_only
def test_the_frozen_export_agrees_with_the_chapter(monkeypatch):
    monkeypatch.delenv(census.ENV, raising=False)
    frag = census.build(core.Run(Path("/nonexistent"), {}, ()))
    v = _values(frag)
    # the counts fig:census:map's caption quotes
    assert v["ch03.census.records"] == 499 and v["ch03.census.sites"] == 162
    assert v[f"ch03.census.{UNVERIFIED}"] == 421 and v[f"ch03.census.{LICENSED}"] == 67
    assert v[f"ch03.census.{CANDIDATE}"] == 11
    assert v["ch03.census.primary"] + v["ch03.census.secondary"] == 499
    assert v["ch03.census.secondary"] > v["ch03.census.primary"]     # the chapter's "secondary tier dominates"
    assert v["ch03.census.matched"] == 67 + 11
    # the chapter's own quoted rows
    assert v["ch03.census.records.ch33"] == 15                       # "channel 33 has 15 envelope rows"
    assert v["ch03.census.nearest_record_km.ch33"] == 101.4
    assert v["ch03.census.nearest_record.ch27"] == "K27OO-D" and v["ch03.census.nearest_record_km.ch27"] == 267.2
    assert v["ch03.census.nearest_record_km.ch36"] == 135.2
    assert v["ch03.census.nearest_matched.ch30"] == "CHKL-1"         # "CHKL-1 stands at 37.8 km"
    assert v["ch03.census.nearest_matched_km.ch30"] == 37.8
    assert v["ch03.census.nearest_matched"] == "CHKL-1" and v["ch03.census.nearest_matched_km"] == 37.8
    # channel 36 has no licence-matched row at all
    assert v["ch03.census.matched.ch36"] == 0 and "ch03.census.nearest_matched.ch36" not in v
    assert _cells(frag, "36")[5:] == [core.DASH] * 4
    assert _row_count(frag) == 25 and "the export matches the sha256" in " | ".join(frag.notes)
