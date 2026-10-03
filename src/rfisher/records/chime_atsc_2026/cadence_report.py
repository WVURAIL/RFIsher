"""The cadence report of record: the detector's report with the table of record's section appended.

pilot-proxy's ``capture cadence-report`` writes the report through its phase-coherence section; the report of
record goes on with one line per channel of the table of record (its disposition, policy or reason, coherence time
and R values) and the count of rows by disposition, copied from the table as the frame analysis's
``cadence_report.py`` wrote them. This command computes nothing: it copies the detector report's bytes and appends
that section.

usage: rfisher records cadence-report --detector-report MD --table-of-record CSV --out MD
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict

HEADING = "\n## Table of record at the measured gain (one line per channel; the CSV has one row per freq_id)\n"


def table_section(rows) -> str:
    """The table of record's section, the text the frame analysis's report appended (from its blank line on)."""
    L = [HEADING]
    L.append("| ch | disposition | policy or reason | tau_c (s) | status | G measured | R none G_meas | R deployed G_meas | R deployed G=1 |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    seen = set()
    for r in rows:
        ch = int(r["channel"])
        if ch in seen or r["role"] == "pilot": continue
        seen.add(ch)
        L.append(f"| {ch} | {r['disposition']} | {r['policy_or_reason']} | {r['tau_c_s']} | {r['tau_c_status']} | {r['G_measured']} | {r['R_none_Gmeasured']} | {r['R_deployed_Gmeasured']} | {r['R_deployed_G1']} |")
    cnt = defaultdict(int)
    for r in rows: cnt[r["disposition"]] += 1
    L.append("\nRows by disposition: " + ", ".join(f"{k} {v}" for k, v in sorted(cnt.items())) + f" (of {len(rows)}).")
    return "\n".join(L) + "\n"


def compose(detector_report: bytes, rows) -> bytes:
    """The report of record: the detector report's bytes, then the table of record's section."""
    if b"## Table of record" in detector_report:
        raise ValueError("the detector report already holds a table of record section")
    if not detector_report.endswith(b"\n"):
        raise ValueError("the detector report does not end with a newline")
    return detector_report + table_section(rows).encode("utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="rfisher records cadence-report", description=__doc__.split("\n\n")[0])
    ap.add_argument("--detector-report", required=True, help="pilot-proxy's capture cadence-report output")
    ap.add_argument("--table-of-record", required=True, help="the table of record (one row per freq_id)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    with open(args.detector_report, "rb") as fh:
        detector = fh.read()
    with open(args.table_of_record, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    data = compose(detector, rows)
    with open(args.out, "wb") as fh:
        fh.write(data)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
