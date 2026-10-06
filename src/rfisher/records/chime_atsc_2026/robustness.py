"""The cleaner-polarization margin of each excision of the amendment 18 ruling.

Per excised channel: its booking range (long if it excises, else short), the unrounded bar, and the bar read on the
cleaner polarization of the range's classes, in the per-frame covariance ratio A_net^2 N n_b (item 1). The cleaner
polarization (the smaller single product of the record's per-pol files, net of its own floor) is converted per class,
with the 3e-5 amplitude floor applied per class before conversion, since the power form needs the class's n_b. The
ruling must take no credit and no delay filter (GROUND_CREDIT=off, world "none"): the exclusion side's constant is the
bin fill alone and the tolerance lambda_none (the json's S and lam_exclusion).

With --ch24 CH24.json (cohort-basis --set CH24_BASIS=measured2020 --json) and channel 24 excised on its own 2020 in-band
measurement, channel 24's row is added from that reading: its booking range, bar and the cleaner polarization on its own
products. A cleaner polarization with no class of the booking range above the control floor prints "at floor" in place
of a bar (its reading would be priced at the 3e-5 amplitude floor).

The bar and cleaner-polarization columns and the basis are those of the release's robustness_a18.csv (release r5.2,
robustness_credit_a18.py with --variant-labels). The release's post-processing columns (the ground-filter credit and
the archive's booked shares) and the amendment 8 record without --a18 (robustness_credit.csv, with both credits) are
not computed here: post-processing is not modelled. The release and the dissertation keep those files.

The table of record is read from --record-table TABLE. Different bytes require --in-run-record-table;
the input digest and mode are logged to stderr.
usage: rfisher records robustness --handoff DIR --record-table TABLE <output csv> --a18 A18.json [--ch24 CH24.json]"""
import csv

import numpy as np

from rfisher.records.chime_atsc_2026 import capture_handoff
from rfisher.records.chime_atsc_2026 import capture_units as U
from rfisher.records.chime_atsc_2026._files import load_json

COLUMNS = ("channel", "bar_db", "margin_otherpol_db", "basis")


def main(argv=None):
    import sys
    argv = ["robustness"] + list(sys.argv[1:] if argv is None else argv)
    in_run = "--in-run-record-table" in argv
    if in_run: argv.remove("--in-run-record-table")
    _h = [argv[i + 1] for i, x in enumerate(argv) if x == "--handoff"]
    if not _h: raise SystemExit("robustness: --handoff is required")
    if "--a18" not in argv: raise SystemExit("robustness: --a18 A18.json is required (the amendment 8 record with credits is not computed)")
    H = capture_handoff.open_handoff(_h[0])
    _pos = [x for i, x in enumerate(argv) if i > 0 and x not in ("--handoff", "--a18", "--ch24", "--record-table") and argv[i - 1] not in ("--handoff", "--a18", "--ch24", "--record-table")]
    if len(_pos) != 1: raise SystemExit("robustness: one output csv is required")
    OUT = _pos[0]
    RT = argv[argv.index("--record-table") + 1] if "--record-table" in argv else None
    capture_handoff.table_rows(H, "frame_analysis/table_of_record.csv", RT, in_run=in_run)   # the record the ruling read, checked
    A18 = load_json(argv[argv.index("--a18") + 1])
    C24 = load_json(argv[argv.index("--ch24") + 1]) if "--ch24" in argv else None
    if not (A18["switches"].get("GROUND_CREDIT") == "off" and A18.get("world") == "none"):
        raise SystemExit("robustness: the ruling takes a credit or a delay filter; post-processing is not modelled")
    if C24 is not None and not (C24.get("basis") == "measured2020" and C24["disposition"] == "excise"): C24 = None
    RANGES = {"bao_short": [(0, 32), (0, 64)], "bao_long": [(0, 128), (0, 255), (1, 0), (2, 0), (3, 0)]}
    SCIENCE = ["20260916162300", "20260917040230", "20260917090230", "20260917140230"]
    ex = {}
    for r in H.rows("frame_analysis/class_excess_epochs.csv"):
        if r["excess"] and r["epoch"] in SCIENCE: ex.setdefault((int(r["channel"]), (int(r["ew"]), int(r["ns"])), int(r["pol"])), []).append(float(r["excess"]))
    fl = {}
    for r in H.rows("frame_analysis/class_floor_bins.csv"):
        if r["epoch"] in SCIENCE: fl.setdefault(((int(r["ew"]), int(r["ns"])), int(r["pol"])), []).append(float(r["excess"]))
    floor = {k: (float(np.mean(v)), float(np.std(v, ddof=1))) for k, v in fl.items()}
    rows = []
    print("ch  range      bar(ruling)  cleaner-pol")
    for ch in sorted([int(c) for c, s_ in A18["summary"].items() if s_[0] == "excise"] + ([24] if C24 else [])):
        if ch == 24 and C24 is not None:   # r5: channel 24 on its own 2020 in-band measurement (a19_inputs), no credit
            assert C24["world"] == "none" and C24["ground"] == "off"
            rng = C24["booking_range"]; B = C24["reading"]["ranges"][rng]; cp = C24["cleaner_pol"]
            rows.append(dict(channel=24, bar_db=f"{B['bar_db']:.1f}", margin_otherpol_db=("at floor" if not cp["measured"] else f"{cp['bar_db']:.1f}"),
                             basis=f"{rng}: {'long' if rng == 'bao_long' else 'short'} BAO baselines, no credit, no delay filter, amendment 19 (2020 in-band measurement, policy {B['bar_policy']}, G {B['G_bar']:.1f})"))
            print(f"{ch:2d}  {rng:9s}  {B['bar_db']:6.1f}       {cp['bar_db']:6.1f}   (2020 in-band measurement)")
            continue
        per = A18["results"][str(ch)]; rng = "bao_long" if per["bao_long"]["verdict"][0] == "excise" else "bao_short"; pr = per[rng]
        bar_db = pr["bar"]; G = pr["G_bar"]
        S = A18["S"][str(ch)]; lam = A18.get("lam_exclusion", A18["lam_dep"])[str(ch)]
        # cleaner polarisation: per class the smaller-polarisation excess net of its floor, median over the range's measured classes
        cl = []; cmeas = 0
        for c in RANGES[rng]:
            vals = []
            for p in (0, 1):
                v = ex.get((ch, c, p)); f = floor.get((c, p))
                if v and f: vals.append((float(np.median(v)) - f[0], float(np.median(v)) > f[0] + 3.0 * f[1]))
            if vals:
                best = min(vals, key=lambda x: x[0]); cmeas += best[1]   # r5.1: the class is measured on its cleaner polarization
                cl.append(U.to_power(max(min(x[0] for x in vals), 3e-5), c))
        A_c = float(np.median(cl)) if cl else np.nan
        R_other = A_c * S * G / lam if np.isfinite(A_c) else np.nan
        cp_txt = ("at floor" if not cmeas else f"{10*np.log10(R_other):.1f}") if np.isfinite(R_other) and R_other > 0 else ""
        rows.append(dict(channel=ch, bar_db=f"{bar_db:.1f}", margin_otherpol_db=cp_txt,
                         basis=f"{rng}: {'long' if rng == 'bao_long' else 'short'} BAO baselines, no credit, no delay filter, amendment 18 ({pr['basis']}, G {G:.1f})"))
        print(f"{ch:2d}  {rng:9s}  {bar_db:6.1f}       {10*np.log10(R_other) if np.isfinite(R_other) and R_other > 0 else float('nan'):6.1f}")
    with open(OUT, "w") as fh:
        w = csv.DictWriter(fh, fieldnames=list(COLUMNS)); w.writeheader(); w.writerows(rows)
    print("wrote the cleaner-polarization margins (amendment 18)")
    return 0
