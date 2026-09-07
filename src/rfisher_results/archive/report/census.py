"""``tab:census`` (chapter 3, ``sec:dtv:environment``): the transmitter-census
envelope per physical DTV channel.

The whole table is a reduction of one frozen file, the vendored ``dtv-census``
export ``pilot-proxy/data/census/census.csv`` (schema
``dtv_transmitter_census_v1``, one row per emitter-channel record within 500
statute miles of DRAO), with ``PROVENANCE.md`` beside it read only to check the
export's recorded SHA-256 against the file actually reduced. Nothing here comes
from the archive run, from a product, or from a propagation model: the counts
are inclusive envelope records with their evidence state, not observed
carriers, and the census is not used as a detection claim.

Columns of ``census.tex`` (one row per physical channel 14--36, then a band row
labelled ``14--36``); the ``census.csv`` field each is reduced from is named::

  ch                 rf_channel
  records            rows carrying that rf_channel (the envelope count)
  prim. (primary)    of those, service_class in {Full-power, Class A} -- the
                     full-service tier the chapter calls "primary"
  sec. (secondary)   of those, service_class in {Relay, Translator (LPTV),
                     Low-power (LPTV), LPTV} -- the rebroadcast/low-power tier
                     the chapter calls "secondary" under Part 74. prim. + sec.
                     = records by construction; an unrecognised class raises
                     rather than being binned silently
  matched            of those, evidence_status in {reported_on_air_licensed,
                     licensed_candidate}: the rows the ISED overlay matched to
                     a licence. In this export the overlay is Canadian-only, so
                     this column counts BC/AB facilities and every US row is
                     unmatched
  nearest matched    callsign of the matched row with the smallest distance_km
                     (ties broken by callsign). Dashed where the channel has no
                     matched row
  range (km)         that row's distance_km
  bear. (deg)        that row's bearing_deg
  ERP (kW)           the largest erp_kw over the channel's matched rows -- the
                     licensed ERP of the strongest matched facility, "strongest"
                     by licensed power. Ties are broken by range then callsign.
                     Dashed where no matched row carries an erp_kw

The band row is the same reduction over all 23 channels at once: its nearest
matched facility and its strongest matched facility are in general different
facilities on different channels, and are not one row of the export.

Sites are the export's distinct source range--bearing pairs, rounded to the
0.1 km / 0.1 deg the file carries, the same key ``fig:census:map`` aggregates
on (the export carries range and bearing, never transmitter coordinates). The
site count is a band-level number only; the table prints no per-channel site
count.

Numbers are keyed ``ch03.census.<name>.chNN`` per channel and
``ch03.census.<name>`` for a band-level value. Four per-channel values are
recorded but *not* printed, because the chapter's prose quotes them while the
stub's columns do not ask for them: ``nearest_record``,
``nearest_record_km`` and ``nearest_record_evidence`` (the nearest envelope
row of any evidence state, which on most channels is nearer than the nearest
*matched* one), and ``erp_max_callsign`` (which facility the ERP column
belongs to).

``build(run)`` takes the run only for provenance: the fragment's content is a
property of the frozen export alone, and the argument exists so the module
satisfies the report's ``Builder`` signature and so ``export_manifest.json``
records which run the fragment was rendered beside. ``frag.inputs`` is the
census file and its ``PROVENANCE.md``, not the ledger.
"""
from __future__ import annotations

import csv
import hashlib
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from .core import DASH, Fragment, Run, booktabs, fmt, tex

NAME = "census"
LABEL = "tab:census"
KEY = "ch03.census"

ENV = "RFISHER_CENSUS_CSV"
REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CSV = REPO_ROOT.parent / "pilot-proxy" / "data" / "census" / "census.csv"

SCHEMA_VERSION = "dtv_transmitter_census_v1"
CHANNELS = tuple(range(14, 37))                  # the ATSC UHF allocations CHIME's band carries
PRIMARY_CLASSES = frozenset({"Full-power", "Class A"})
SECONDARY_CLASSES = frozenset({"Relay", "Translator (LPTV)", "Low-power (LPTV)", "LPTV"})
MATCHED_STATES = ("reported_on_air_licensed", "licensed_candidate")
EVIDENCE_STATES = ("reported_on_air_unverified",) + MATCHED_STATES
COLUMNS = ("schema_version", "rf_channel", "callsign", "service_class", "distance_km", "bearing_deg",
           "erp_kw", "city", "state_prov", "evidence_status")

HEADER = ["ch", "records", "prim.", "sec.", "matched", "nearest matched",
          r"\shortstack{range\\(km)}", r"\shortstack{bear.\\(deg)}", r"\shortstack{ERP\\(kW)}"]
ALIGN = "rrrrrlrrr"
_SHA_RE = re.compile(r"\b([0-9a-f]{64})\b")


def census_path() -> Path:
    """The frozen export to reduce: ``$RFISHER_CENSUS_CSV``, else the sibling pilot-proxy checkout."""
    configured = os.environ.get(ENV)
    return Path(configured).expanduser() if configured else DEFAULT_CSV


@dataclass(frozen=True)
class Record:
    """One emitter-channel record of the export."""

    channel: int
    callsign: str
    service_class: str
    distance_km: float
    bearing_deg: float
    erp_kw: float                # NaN where the row carries no licensed ERP
    evidence: str
    city: str
    state: str

    @property
    def primary(self) -> bool:
        return self.service_class in PRIMARY_CLASSES

    @property
    def matched(self) -> bool:
        """Adjudicated against a licence by the ISED overlay (the evidence field, not the ERP)."""
        return self.evidence in MATCHED_STATES

    @property
    def site(self) -> tuple[float, float]:
        """The export's source range--bearing key: it carries no transmitter coordinates."""
        return (round(self.distance_km, 1), round(self.bearing_deg, 1))


def _float(text: str) -> float:
    text = text.strip()
    if not text or text.lower() == "nan":
        return math.nan
    return float(text)


def read_census(path: Path | str) -> list[Record]:
    """Every row of the frozen export, validated against the pinned schema and evidence states."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"the frozen dtv-census export is not at {path}: the whole of {LABEL} is a reduction "
                                f"of it, so there is nothing to render without it. Set ${ENV} to the export, or put "
                                "a pilot-proxy checkout beside this repository")
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in COLUMNS if c not in (reader.fieldnames or ())]
        if missing:
            raise ValueError(f"{path}: census export is missing columns {missing}")
        out = []
        for line, row in enumerate(reader, start=2):
            schema = row["schema_version"].strip()
            if schema != SCHEMA_VERSION:
                raise ValueError(f"{path} line {line}: unsupported census schema {schema!r}")
            evidence = row["evidence_status"].strip()
            if evidence not in EVIDENCE_STATES:
                raise ValueError(f"{path} line {line}: unsupported evidence_status {evidence!r}")
            service = row["service_class"].strip()
            if service not in PRIMARY_CLASSES and service not in SECONDARY_CLASSES:
                raise ValueError(f"{path} line {line}: unknown service_class {service!r}: the primary/secondary "
                                 "split is a regulatory statement and will not bin an unrecognised class")
            distance, bearing = _float(row["distance_km"]), _float(row["bearing_deg"])
            if not (math.isfinite(distance) and math.isfinite(bearing)):
                raise ValueError(f"{path} line {line}: non-finite range or bearing")
            out.append(Record(int(row["rf_channel"]), row["callsign"].strip(), service, distance, bearing,
                              _float(row["erp_kw"]), evidence, row["city"].strip(), row["state_prov"].strip()))
    return out


def _nearest(records: Sequence[Record]) -> Record | None:
    return min(records, key=lambda r: (r.distance_km, r.callsign)) if records else None


def _strongest(records: Sequence[Record]) -> Record | None:
    """The largest licensed ERP; ties break to the nearer facility, then the callsign."""
    with_erp = [r for r in records if math.isfinite(r.erp_kw)]
    return min(with_erp, key=lambda r: (-r.erp_kw, r.distance_km, r.callsign)) if with_erp else None


def _group(records: Iterable[Record], channels: Sequence[int]) -> dict:
    """One channel's reduction: counts, the nearest matched row, the strongest matched row."""
    wanted = set(channels)
    rows = [r for r in records if r.channel in wanted]
    matched = [r for r in rows if r.matched]
    return {"records": len(rows), "primary": sum(1 for r in rows if r.primary),
            "secondary": sum(1 for r in rows if not r.primary), "matched": len(matched),
            "sites": len({r.site for r in rows}), "nearest_matched": _nearest(matched),
            "strongest": _strongest(matched), "nearest_record": _nearest(rows),
            "matched_without_erp": sum(1 for r in matched if not math.isfinite(r.erp_kw)),
            "unmatched_with_erp": sum(1 for r in rows if not r.matched and math.isfinite(r.erp_kw))}


def summarise(records: Sequence[Record], channels: Sequence[int] = CHANNELS) -> tuple[list[dict], dict, list[Record]]:
    """Per-channel rows, the band row, and any record outside ``channels`` (excluded, never dropped silently)."""
    rows = [dict(_group(records, [ch]), channel=ch) for ch in channels]
    band = _group(records, channels)
    band["evidence"] = {state: sum(1 for r in records if r.channel in set(channels) and r.evidence == state)
                        for state in EVIDENCE_STATES}
    band["channels"] = len(channels)
    band["channels_without_match"] = sum(1 for r in rows if r["matched"] == 0)
    band["channels_nearest_matched_farther"] = sum(
        1 for r in rows if r["nearest_matched"] is not None and r["nearest_record"] is not None
        and r["nearest_matched"].distance_km > r["nearest_record"].distance_km)
    band["max_distance_km"] = max((r.distance_km for r in records if r.channel in set(channels)), default=math.nan)
    return rows, band, [r for r in records if r.channel not in set(channels)]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def recorded_digest(provenance: Path) -> str:
    """The SHA-256 ``PROVENANCE.md`` records for the export, or ``''`` when it records none."""
    if not provenance.is_file():
        return ""
    found = _SHA_RE.search(provenance.read_text(encoding="utf-8"))
    return found.group(1) if found else ""


def _erp_cell(value: float) -> tuple[str, int]:
    """The ERP cell to three significant figures, with the decimals it actually printed."""
    text = fmt(value, 3, sig=True)
    return text, (len(text.split(".")[1]) if "." in text else 0)


def _facility_cells(frag: Fragment, row: dict, suffix: str, label) -> list[str]:
    """The nearest-matched callsign, range and bearing cells, and their numbers; dashes when absent."""
    near, column = row["nearest_matched"], "nearest matched"
    if near is None:
        return [DASH, DASH, DASH]
    where = {"channel": label}
    frag.add(f"{KEY}.nearest_matched{suffix}", near.callsign, kind="text", renderings=(near.callsign,),
             row=where, column=column)
    frag.add(f"{KEY}.nearest_matched_km{suffix}", near.distance_km, precision=1, row=where, column="range (km)")
    frag.add(f"{KEY}.nearest_matched_bearing_deg{suffix}", near.bearing_deg, precision=1, row=where,
             column="bearing (deg)")
    return [tex(near.callsign), fmt(near.distance_km, 1), fmt(near.bearing_deg, 1)]


def _erp_cells(frag: Fragment, row: dict, suffix: str, label) -> str:
    strongest = row["strongest"]
    if strongest is None:
        return DASH
    text, decimals = _erp_cell(strongest.erp_kw)
    where = {"channel": label}
    frag.add(f"{KEY}.erp_max_kw{suffix}", strongest.erp_kw, precision=decimals, renderings=(text,),
             row=where, column="ERP (kW)")
    frag.add(f"{KEY}.erp_max_callsign{suffix}", strongest.callsign, kind="text",
             renderings=(strongest.callsign,), row=where, column="")
    return text


def _row_cells(frag: Fragment, row: dict, suffix: str, label) -> list[str]:
    where = {"channel": label}
    for name, column in (("records", "records"), ("primary", "primary"), ("secondary", "secondary"),
                         ("matched", "matched")):
        frag.add(f"{KEY}.{name}{suffix}", row[name], kind="int", row=where, column=column)
    cells = [str(label), str(row["records"]), str(row["primary"]), str(row["secondary"]), str(row["matched"])]
    return cells + _facility_cells(frag, row, suffix, label) + [_erp_cells(frag, row, suffix, label)]


def build(run: Run) -> Fragment:
    """``tab:census`` from the frozen export; ``run`` is provenance only (see the module docstring)."""
    path = census_path()
    records = read_census(path)
    rows, band, out_of_band = summarise(records)

    frag = Fragment(NAME, LABEL, "")
    frag.inputs = [path]
    provenance = path.parent / "PROVENANCE.md"
    if provenance.is_file():
        frag.inputs.append(provenance)

    cells = []
    for row in rows:
        ch = row["channel"]
        cells.append(_row_cells(frag, row, f".ch{ch}", ch))
        near = row["nearest_record"]
        if near is not None:                       # recorded, not printed: the chapter's prose quotes these
            where = {"channel": ch}
            frag.add(f"{KEY}.nearest_record.ch{ch}", near.callsign, kind="text", renderings=(near.callsign,),
                     row=where, column="")
            frag.add(f"{KEY}.nearest_record_km.ch{ch}", near.distance_km, precision=1, row=where, column="")
            frag.add(f"{KEY}.nearest_record_evidence.ch{ch}", near.evidence, kind="text",
                     renderings=(near.evidence,), row=where, column="")
    band_label = f"{CHANNELS[0]}--{CHANNELS[-1]}"
    cells.append(_row_cells(frag, band, "", band_label))
    frag.tex = booktabs(HEADER, cells, ALIGN, midrules=(len(cells) - 1,))

    frag.add(f"{KEY}.sites", band["sites"], kind="int", column="")
    frag.add(f"{KEY}.channels", band["channels"], kind="int", column="ch")
    for state, count in band["evidence"].items():
        frag.add(f"{KEY}.{state}", count, kind="int", column="")
    for name in ("channels_without_match", "channels_nearest_matched_farther"):
        frag.add(f"{KEY}.{name}", band[name], kind="int", column="")
    frag.add(f"{KEY}.max_distance_km", band["max_distance_km"], precision=1, column="range (km)")
    frag.add(f"{KEY}.schema_version", SCHEMA_VERSION, kind="text", renderings=(SCHEMA_VERSION,), column="")
    digest = _sha256(path)
    frag.add(f"{KEY}.export_sha256", digest, kind="text", renderings=(digest,), column="")

    frag.notes.append(f"layout: one {len(HEADER)}-column tabular, {len(cells)} rows (channels {band_label} then a "
                      "band row over all of them, below a midrule); natural width 444 pt at 11pt against the "
                      "document's 470 pt text block, so it sets upright and unscaled, and the chapter supplies the "
                      "table environment, the caption and the label")
    frag.notes.append(f"the whole table is a reduction of {path.name} ({SCHEMA_VERSION}, sha256 {digest[:12]}), the "
                      "frozen dtv-census export that also feeds fig:census:map; no archive-run, product or "
                      "propagation input is read, and the run argument of build() is provenance only")
    recorded = recorded_digest(provenance)
    if recorded and recorded != digest:
        frag.notes.append(f"WARNING: PROVENANCE.md records sha256 {recorded[:12]} for the export but the file reduced "
                          f"here is {digest[:12]}: the vendored file is not the one the provenance describes")
    elif recorded:
        frag.notes.append("the export matches the sha256 PROVENANCE.md records for it")
    else:
        frag.notes.append("no PROVENANCE.md digest was found beside the export, so the file could not be checked "
                          "against its recorded one")
    frag.notes.append(f"{band['records']} envelope records at {band['sites']} distinct source range--bearing sites "
                      f"({band['evidence']['reported_on_air_unverified']} reported-on-air/unverified, "
                      f"{band['evidence']['reported_on_air_licensed']} reported-on-air/licence-matched, "
                      f"{band['evidence']['licensed_candidate']} licence-only candidates), the counts fig:census:map's "
                      "caption quotes; sites are the export's rounded range--bearing pairs because it carries no "
                      "transmitter coordinates")
    frag.notes.append(f"primary is service_class in {sorted(PRIMARY_CLASSES)} and secondary is everything else in "
                      f"{sorted(SECONDARY_CLASSES)}: {band['primary']} primary against {band['secondary']} secondary "
                      "over the band, the count on which the chapter's 'the secondary tier dominates' rests")
    matched_states = ", ".join(MATCHED_STATES)
    frag.notes.append(f"matched counts rows whose evidence_status is one of ({matched_states}); in this export the "
                      "ISED overlay is Canadian-only, so the matched column is a BC/AB column and every US row is "
                      "unmatched -- a limit of the export, not a statement about US facilities")
    if band["channels_without_match"]:
        no_match = [str(r["channel"]) for r in rows if r["matched"] == 0]
        frag.notes.append(f"no licence-matched row on channel(s) {', '.join(no_match)}: their nearest-facility and ERP "
                          f"cells print {DASH}")
    if band["channels_nearest_matched_farther"]:
        frag.notes.append(f"on {band['channels_nearest_matched_farther']} of {band['channels']} channels the nearest "
                          "licence-matched facility is farther than the nearest envelope record of any evidence state; "
                          "the nearer unverified row is recorded as ch03.census.nearest_record*.chNN but not printed, "
                          "because the stub's column is the matched one")
    if band["matched_without_erp"]:
        frag.notes.append(f"{band['matched_without_erp']} licence-matched record(s) carry no erp_kw and so cannot enter "
                          "the ERP column; a channel whose matched rows all lack one prints the dash")
    if band["unmatched_with_erp"]:
        frag.notes.append(f"{band['unmatched_with_erp']} record(s) carry an erp_kw without a licence-matched evidence "
                          "state; they are excluded from the matched count and from the ERP column")
    if out_of_band:
        channels = sorted({r.channel for r in out_of_band})
        frag.notes.append(f"{len(out_of_band)} export record(s) lie outside physical channels {band_label} "
                          f"(channel(s) {channels}) and are excluded from every count in this table")
    frag.notes.append("the band row's nearest matched facility and its strongest matched facility are in general "
                      "different facilities on different channels, not one row of the export")
    frag.notes.append("ERP is the largest licensed erp_kw over a channel's matched rows, to three significant figures; "
                      "'strongest' is by licensed power, not by predicted field strength -- the export's optional "
                      "detectability_db is an optimistic upper bound carried on a minority of rows and is not read here")
    frag.notes.append("the table carries no observed-carrier, detection or propagation quantity: the counts are "
                      "inclusive envelope records with their evidence state")
    return frag


BUILDERS = (build,)
