#!/usr/bin/env python3
"""Build an offline regulatory sidecar; never label acquisitions on or off."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from rfisher_results.validation.regulatory import (
    dbf_rows,
    fcc_history,
    ised_dates,
    lms_rows,
    table_source,
)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fcc", type=Path, required=True)
    parser.add_argument("--fcc-candidates", type=Path, required=True)
    parser.add_argument("--census", type=Path, required=True)
    parser.add_argument("--ised", type=Path, required=True)
    parser.add_argument("--fcc-snapshot-date", required=True)
    parser.add_argument("--ised-snapshot-date", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists() and any(args.out.iterdir()):
        parser.error("output directory must be absent or empty; preserve frozen evidence")
    with args.fcc_candidates.open(newline="") as stream:
        candidates = list(csv.DictReader(stream))
    with args.census.open(newline="") as stream:
        census = list(csv.DictReader(stream))
    wanted_calls = {c for row in census for c in row["callsign"].split("+")
                    if c.startswith(("K", "W"))}
    matches = [r for r in lms_rows(args.fcc, "facility", {"facility_id", "callsign"})
               if r["callsign"] in wanted_calls]
    facilities = {r["facility_id"] for r in candidates} | {r["facility_id"] for r in matches}
    fcc_inputs = [table_source(args.fcc, table, "dat")
                  for table in ["facility", "license_filing_version"]]
    fcc_inputs += [args.fcc_candidates, args.census]
    fcc = fcc_history(args.fcc, facilities, snapshot_date=args.fcc_snapshot_date,
                      source_hashes={str(p.resolve()): digest(p) for p in fcc_inputs})
    fcc["selection"] = {
        "current_candidate_facility_ids": sorted({r["facility_id"] for r in candidates}),
        "exact_census_callsign_matches": [{"callsign": r["callsign"], "facility_id": r["facility_id"]} for r in matches],
        "unmatched_census_callsigns": sorted(wanted_calls - {r["callsign"] for r in matches}),
        "limit": "current 500-mile candidate IDs plus exact existing census callsigns; excludes unresolved historical callsigns/newly discovered deleted sites; not a complete historical candidate scope",
    }
    # Keep both allotment and operational rows; a deleted transmitter can be
    # absent from the current census yet matter to a historical channel era.
    wanted_ised = {r["CALL_SIGN"] for r in dbf_rows(args.ised, "tvstatio")
                   if r["PROVINCE"] in {"BC", "AB"} and r["CHANNEL"].isdigit()
                   and 14 <= int(r["CHANNEL"]) <= 36}
    ised = ised_dates(args.ised, wanted_ised, snapshot_date=args.ised_snapshot_date,
                      source_hashes={str(args.ised.resolve()): digest(args.ised)})
    ised["selection"] = "all callsigns with a BC/AB physical-channel 14-36 record in this technical snapshot; not restricted to 500 miles; all their status/site/channel rows retained"
    case_names = ["CHBC-DT", "CHKL-DT", "CHBC-DT-1", "CHKL-DT-1", "CHBC-DT-2", "CHKL-DT-2"]
    hypotheses = {
        "schema": "rfisher_regulatory_era_hypotheses_v1",
        "decision": {"date": "2020-12-04", "date_type": "authorization_issued",
                     "url": "https://crtc.gc.ca/eng/archive/2020/2020-391.htm",
                     "application": "2019-1119-9", "reviewed_sections": [8, 32, 33]},
        "ised_sha256": digest(args.ised),
        "channel_mapping_source": "https://ised-isde.canada.ca/site/spectrum-management-telecommunications/en/devices-and-equipment/digital-television-dtv-transition-schedule",
        "candidate_pairs": [
            {"community": "Kelowna", "old_callsign": "CHBC-DT", "old_physical_channel": 27,
             "multiplex_host": "CHKL-DT", "host_physical_channel": 24},
            {"community": "Penticton", "old_callsign": "CHBC-DT-1", "old_physical_channel": 32,
             "multiplex_host": "CHKL-DT-1", "host_physical_channel": 30},
            {"community": "Vernon", "old_callsign": "CHBC-DT-2", "old_physical_channel": 20,
             "multiplex_host": "CHKL-DT-2", "host_physical_channel": 22},
        ],
        "source_records": [r for r in ised["records"] if r["station"]["CALL_SIGN"] in case_names],
        "operational_cutover_interval": None,
        "eligible_use": "external authorization/certificate dates can define explicitly administrative exploratory era comparisons; do not assert actual RF cutover or transmitter-off intervals",
        "confirmation_needed": "dated operator/engineering completion or suspension/resumption records; account for other cochannel transmitters and host carrier sharing",
    }
    summary = {"fcc_facilities": len(fcc["facilities"]),
               "fcc_licence_versions": len(fcc["licence_versions"]),
               "fcc_unmatched_census_callsigns": len(fcc["selection"]["unmatched_census_callsigns"]),
               "ised_station_rows": len(ised["records"]),
               "ised_rows_with_dates": sum(r["date_row_present"] for r in ised["records"]),
               "ised_rows_with_on_air_date": sum("ON_AIR" in r["dates"] for r in ised["records"]),
               "verified_rf_intervals": 0}
    args.out.mkdir(parents=True, exist_ok=True)
    for name, value in [("fcc-history.json", fcc), ("ised-dates.json", ised),
                        ("era-hypotheses.json", hypotheses), ("summary.json", summary)]:
        (args.out / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
