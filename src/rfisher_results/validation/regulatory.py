"""Preserve regulatory records without converting authorizations to RF states.

Administrative dates, reported commissioning dates and actual transmitter
switching intervals are different evidence. These readers deliberately emit no
``StateRecord`` and cannot establish a receiver-off population.
"""
from __future__ import annotations

import csv
import io
import re
import struct
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from zipfile import ZipFile


def table_source(source, table, suffix):
    """Resolve the exact file read for a table, also used for provenance hashes.

    An extracted table takes precedence over its ZIP when both are present.
    Callers must hash this returned file rather than assuming the ZIP is read.
    """
    source = Path(source)
    if source.is_dir():
        direct = source / f"{table}.{suffix}"
        return direct if direct.is_file() else source / f"{table}.zip"
    return source


@contextmanager
def _member(source, table, suffix):
    selected = table_source(source, table, suffix)
    if selected.suffix.lower() == f".{suffix}".lower():
        with selected.open("rb") as stream:
            yield stream
    else:
        with ZipFile(selected) as zipped:
            names = [n for n in zipped.namelist()
                     if Path(n).name.lower() == f"{table}.{suffix}".lower()]
            if len(names) != 1:
                raise ValueError(f"expected exactly one {table}.{suffix} in {selected}")
            with zipped.open(names[0]) as stream:
                yield stream


def lms_rows(source, table, required):
    """Stream LMS .dat or ZIP records, rejecting malformed column layouts."""
    with _member(source, table, "dat") as binary:
        stream = io.TextIOWrapper(binary, encoding="utf-8-sig", newline="")
        reader = csv.reader(stream, delimiter="|", quoting=csv.QUOTE_NONE)

        def strip(row):
            return row[:-2] if row[-2:] == ["^", ""] else row

        header = [s.strip().lower() for s in strip(next(reader, []))]
        if len(set(header)) != len(header) or not set(required) <= set(header):
            raise ValueError(f"invalid {table} header")
        for row in reader:
            if not row:
                continue
            row = strip(row)
            if len(row) != len(header):
                raise ValueError(f"{table}:{reader.line_num}: malformed row width")
            yield dict(zip(header, [s.strip() for s in row]))


def dbf_rows(source, table):
    """Read the ISED dBASE III text fields without guessing date/time zones.

    Preserve deleted flags and raw numeric/date text. ISED's TV table has an
    extra LF after its field terminator; the published header length controls
    the first record. Unsupported binary/memo fields are rejected.
    """
    with _member(source, table, "dbf") as stream:
        base = stream.read(32)
        if len(base) != 32 or base[0] != 3:
            raise ValueError("expected dBASE III header")
        count, header_len, record_len = struct.unpack("<IHH", base[4:12])
        if header_len < 33 or record_len < 1:
            raise ValueError("invalid DBF lengths")
        descriptors = stream.read(header_len - 32)
        if len(descriptors) != header_len - 32:
            raise ValueError("truncated DBF header")
        fields, pos = [], 0
        while pos < len(descriptors) and descriptors[pos] != 13:
            field = descriptors[pos:pos + 32]
            if len(field) != 32 or chr(field[11]) not in {"C", "D", "N", "F", "L"}:
                raise ValueError("unsupported or truncated DBF field")
            fields.append((field[:11].split(b"\0")[0].decode("ascii"), field[16]))
            pos += 32
        if (pos >= len(descriptors) or sum(n for _, n in fields) + 1 != record_len
                or len({key for key, _ in fields}) != len(fields)):
            raise ValueError("invalid DBF field layout")
        for _ in range(count):
            raw = stream.read(record_len)
            if len(raw) != record_len or raw[:1] not in {b" ", b"*"}:
                raise ValueError("truncated or invalid DBF record")
            row, offset = {"_deleted": raw[:1] == b"*"}, 1
            for key, length in fields:
                row[key] = raw[offset:offset + length].decode("cp1252").strip()
                offset += length
            yield row


def _provenance(snapshot_date, source_hashes):
    date.fromisoformat(snapshot_date)
    if not source_hashes or any(not isinstance(v, str) or not re.fullmatch(r"[0-9a-f]{64}", v)
                                for v in source_hashes.values()):
        raise ValueError("source hashes must be nonempty SHA256 identities")
    return {"snapshot_date": snapshot_date, "source_sha256": dict(source_hashes),
            "physical_state": "unknown", "verified_rf_intervals": []}


def _unique(rows, key):
    result = {}
    for row in rows:
        value = row[key]
        if not value or value in result:
            raise ValueError(f"missing or duplicate {key}: {value!r}")
        result[value] = row
    return result


def fcc_history(source, facility_ids, *, snapshot_date, source_hashes):
    """Retain selected facility records and all versions of their licence IDs.

    This is licence-version history available in one snapshot, not a complete
    history of applications, silent STAs, amendments or operational intervals.
    Current inactive/cancelled/silent records are retained. Missing IDs and
    unresolved predecessor links remain explicit diagnostics.
    """
    result = _provenance(snapshot_date, source_hashes)
    wanted = set(str(v) for v in facility_ids)
    if not wanted or "" in wanted:
        raise ValueError("facility IDs must be nonempty")
    required = {"facility_id", "license_filing_id", "facility_status", "status_date"}
    facilities = _unique((r for r in lms_rows(source, "facility", required)
                          if r["facility_id"] in wanted), "facility_id")
    licenses = {r["license_filing_id"] for r in facilities.values()} - {""}
    required = {"filing_version_id", "license_filing_id", "prev_filing_version_id",
                "status_date", "current_status_code", "active_ind"}
    filings = _unique((r for r in lms_rows(source, "license_filing_version", required)
                       if r["license_filing_id"] in licenses), "filing_version_id")
    result.update(
        schema="rfisher_regulatory_fcc_v1", facilities=list(facilities.values()),
        licence_versions=sorted(filings.values(), key=lambda r: (r["license_filing_id"],
                                                               r["status_date"], r["filing_version_id"])),
        missing_facility_ids=sorted(wanted - facilities.keys()),
        unresolved_predecessors=sorted({r["prev_filing_version_id"] for r in filings.values()
                                        if r["prev_filing_version_id"]
                                        and r["prev_filing_version_id"] not in filings}),
        time_semantics="status/create/update/expiry fields are administrative; timezone unspecified; not RF switching times",
        interpretation="LICSL reports silent status at this snapshot; LICEN, LICRP, LICAN and expiry dates do not establish physical on/off intervals",
    )
    return result


def ised_dates(source, callsigns, *, snapshot_date, source_hashes):
    """Join TVSTATIO to DATES by fixed-width callsign plus BANNER.

    Exact callsign matching retains all channel/status/site rows. OP and ON_AIR
    are reported operational evidence, but neither establishes continuous
    transmission or the effective date of a later multiplex/channel change.
    """
    result = _provenance(snapshot_date, source_hashes)
    wanted = {v.strip() for v in callsigns}
    if not wanted or "" in wanted:
        raise ValueError("callsigns must be nonempty")
    dates = {}
    for row in dbf_rows(source, "dates"):
        if row["_deleted"]:
            continue
        raw = row["CALLS_BANR"]
        key = (raw[:12].strip(), raw[12:].strip())
        if key[0] in wanted:
            if key in dates:
                raise ValueError(f"duplicate ISED date identity {key}")
            dates[key] = row
    records, found = [], set()
    for row in dbf_rows(source, "tvstatio"):
        if row["CALL_SIGN"] not in wanted:
            continue
        found.add(row["CALL_SIGN"])
        joined = dates.get((row["CALL_SIGN"], row["BANNER"]))
        normalized, invalid = {}, {}
        for key in ["BC_EFFCT", "BC_EXPIR", "APPLICATN", "AUTHORIZE", "ON_AIR", "CRTC_1ST", "CRTC_1STN"]:
            value = joined.get(key, "") if joined else ""
            if value:
                try:
                    if not re.fullmatch(r"[0-9]{8}", value):
                        raise ValueError("invalid date")
                    normalized[key] = datetime.strptime(value, "%Y%m%d").date().isoformat()
                except ValueError:
                    invalid[key] = value
        records.append({"station": row, "dates": normalized, "invalid_dates": invalid,
                        "date_row_present": joined is not None,
                        "date_record_raw": joined,
                        "evidence_kind": "reported_operational_snapshot" if row["BANNER"] == "OP" and not row["_deleted"] else "administrative_or_allotment_snapshot",
                        "physical_state": "unknown"})
    result.update(schema="rfisher_regulatory_ised_v1", records=records,
                  missing_callsigns=sorted(wanted - found),
                  time_semantics="date-only, timezone unspecified; BC_EFFCT certificate effective, BC_EXPIR renewal/approval expiry, ON_AIR reported commissioning",
                  interpretation="allotments, missing/deleted rows and expiry never establish RF silence; no historical cutoff is inferred")
    return result
