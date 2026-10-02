"""Robustness of the baseline-resolved excisions (amendment 8): per excised channel the bar on the range that excises
it with both credits (the ruling), the same bar without the ground-filter credit, the bar if the archive's booked shares
were granted instead of the measured coherence, and the bar on the cleaner polarisation of the range's classes.
Writes robustness_credit.csv in the column layout the dissertation generator reads.

Amendment 18 copy (2026-09-24): robustness_v8.py, which writes the robustness_credit.csv of record (FA's older
robustness_credit.py writes a different, pre-amendment-8 layout that the record no longer uses). Paths are arguments;
the frame-analysis inputs and the archive ledger's shares are read from the capture handoff. Without --a18 it is the frozen computation (tests/test_a18.py
reproduces the vendored csv). With --a18 A18.json (ruling_a18.py --a18 --json) each excised channel is read on the
amendment 18 ruling: its booking range (long if it excises, else short), the unrounded bar, the G of the bar, the
delay cut with the bin fill, and every margin in the per-frame covariance ratio A_net^2 N n_b (item 1). The cleaner
polarization (the smaller single product of the record's per-pol files, net of its own floor) is converted per class,
with the 3e-5 amplitude floor applied per class before conversion, since the power form needs the class's n_b.
r3 (item 15): on a no-filter ruling (A18.json with world "none") the exclusion side has no delay filter, so S is the bin
fill alone and the tolerance is lambda_none (the json's S and lam_exclusion); the bar carries the ground-filter credit only,
and the basis says so. On a 200 ns ruling the output is revision 2's byte for byte.
r4 (item 17): on a ruling with GROUND_CREDIT=off the bar takes no credit at all, so the no-ground-credit margin equals the
bar and the cleaner polarization is read without (1 - gamma^2) too; the basis says so. On a ruling with the ground credit
the output is revision 3's (or revision 2's) byte for byte.
r5 (amendment 19, item 34): with --ch24 CH24.json (ch24_2020_basis_a18.py --set CH24_BASIS=measured2020 --json) and channel 24
excised on its own 2020 in-band measurement, channel 24's row is added from that reading: its booking range, bar and G, the
archive shares from its own ledger and the cleaner polarization on its own products (a19_inputs). Without --ch24, or with the
borrowed basis, the output is revision 4's byte for byte.
r5.1 (triage row 26): with --variant-labels a variant that does not apply prints its reason in place of a bar: "n/a" for the
archive shares of a channel with none in the ledger (26 and 27), and "at floor" for a cleaner polarization with no class of the
booking range above the control floor (its reading would be priced at the 3e-5 amplitude floor). Without it the output is r5's.

The release's ``robustness_credit_a18.py``, with its logic unchanged; the frame-analysis tables and the archive shares
come from the capture handoff.
The table of record is read from --record-table TABLE. Different bytes require --in-run-record-table;
the input digest and mode are logged to stderr.
usage: rfisher records robustness --handoff DIR --record-table TABLE <output csv> [--a18 A18.json] [--ch24 CH24.json]
                                  [--variant-labels]"""
import csv, re

import numpy as np

from rfisher.records.chime_atsc_2026 import capture_handoff
from rfisher.records.chime_atsc_2026 import capture_units as U
from rfisher.records.chime_atsc_2026._files import load_json


def main(argv=None):
    import sys
    argv = ["robustness"] + list(sys.argv[1:] if argv is None else argv)
    in_run = "--in-run-record-table" in argv
    if in_run: argv.remove("--in-run-record-table")
    _h = [argv[i + 1] for i, x in enumerate(argv) if x == "--handoff"]
    if not _h: raise SystemExit("robustness: --handoff is required")
    H = capture_handoff.open_handoff(_h[0])
    _pos = [x for i, x in enumerate(argv) if i > 0 and x not in ("--handoff", "--a18", "--ch24", "--variant-labels", "--record-table") and argv[i - 1] not in ("--handoff", "--a18", "--ch24", "--record-table")]
    if len(_pos) != 1: raise SystemExit("robustness: one output csv is required")
    OUT = _pos[0]
    A18 = load_json(argv[argv.index("--a18") + 1]) if "--a18" in argv else None
    C24 = load_json(argv[argv.index("--ch24") + 1]) if "--ch24" in argv else None
    VLAB = "--variant-labels" in argv   # r5.1, triage row 26
    if C24 is not None and not (C24.get("basis") == "measured2020" and C24["disposition"] == "excise"): C24 = None
    RANGES = {"bao_short": [(0, 32), (0, 64)], "bao_long": [(0, 128), (0, 255), (1, 0), (2, 0), (3, 0)]}
    SCIENCE = ["20260916162300", "20260917040230", "20260917090230", "20260917140230"]
    tor = {}
    RT = argv[argv.index("--record-table") + 1] if "--record-table" in argv else None
    for r in capture_handoff.table_rows(H, "frame_analysis/table_of_record.csv", RT, in_run=in_run):
        ch = int(r["channel"])
        if r["role"] != "pilot" and ch not in tor: tor[ch] = r
    shares = {}
    for name, isd_, fsd_, gdb_ in capture_handoff.archive_shares(H):   # the ledger's chain sections, in its file order
        shares[int(name[2:4])] = (isd_, fsd_, gdb_)
    ex = {}
    for r in H.rows("frame_analysis/class_excess_epochs.csv"):
        if r["excess"] and r["epoch"] in SCIENCE: ex.setdefault((int(r["channel"]), (int(r["ew"]), int(r["ns"])), int(r["pol"])), []).append(float(r["excess"]))
    fl = {}
    for r in H.rows("frame_analysis/class_floor_bins.csv"):
        if r["epoch"] in SCIENCE: fl.setdefault(((int(r["ew"]), int(r["ns"])), int(r["pol"])), []).append(float(r["excess"]))
    floor = {k: (float(np.mean(v)), float(np.std(v, ddof=1))) for k, v in fl.items()}
    GOFF = A18 is not None and A18["switches"].get("GROUND_CREDIT") == "off"   # r4, item 17
    rows = []
    print("ch  range      bar(ruling)  no-ground-credit  archive-shares  cleaner-pol")
    for ch in sorted(tor) if A18 is None else sorted([int(c) for c, s_ in A18["summary"].items() if s_[0] == "excise"] + ([24] if C24 else [])):
        if ch == 24 and C24 is not None:   # r5: channel 24 on its own 2020 in-band measurement (a19_inputs), no credit
            assert GOFF and A18.get("world") == "none" and C24["world"] == "none" and C24["ground"] == "off"
            rng = C24["booking_range"]; B = C24["reading"]["ranges"][rng]; cp, ar = C24["cleaner_pol"], C24["archive_shares"]
            rows.append(dict(channel=24, bar_db=f"{B['bar_db']:.1f}", ground_filter_db_archive=f"{ar['ground_filter_db_archive']:.1f}", margin_credit_db=f"{ar['bar_db']:.1f}",
                             rho_ew="", ground_filter_db_ew="0.0", margin_credit_ew_db=f"{B['bar_db']:.1f}",
                             margin_otherpol_db=("at floor" if VLAB and not cp["measured"] else f"{cp['bar_db']:.1f}"), margin_both_ew_db=f"{B['bar_db']:.1f}",
                             basis=f"{rng}: {'long' if rng == 'bao_long' else 'short'} BAO baselines, no credit, no delay filter, amendment 19 (2020 in-band measurement, policy {B['bar_policy']}, G {B['G_bar']:.1f})"))
            print(f"{ch:2d}  {rng:9s}  {B['bar_db']:6.1f}       {B['bar_db']:6.1f}          {ar['bar_db']:6.1f}       {cp['bar_db']:6.1f}   (2020 in-band measurement)")
            continue
        if A18 is None:
            r = tor[ch]
            if r["disposition"] != "excise": continue
            rng = "bao_long" if r["bao_long_verdict"] == "excise" else "bao_short"
            bar = float(r[f"{rng}_R_deployed"]) if r[f"{rng}_R_deployed"] else np.nan
            m = re.search(r"subtraction bar ([-\d.]+) dB", r["policy_or_reason"]); bar_db = float(m.group(1)) if m else 10 * np.log10(bar)
            credit = float(r[f"{rng}_ground_credit_db"] or 0.0); G = float(r[f"{rng}_G"]); rho = float(r[f"{rng}_rho"])
            S = 10 ** (-float(r["suppression_db"]) / 10); lam = float(r["lambda_deployed"])
        else:   # the amendment 18 ruling: booking range, unrounded bar, the G of the bar, S with the bin fill
            per = A18["results"][str(ch)]; rng = "bao_long" if per["bao_long"]["verdict"][0] == "excise" else "bao_short"; pr = per[rng]
            bar_db = pr["bar"]; credit = pr["credit_db"] or 0.0; G = pr["G_bar"]; rho = pr["rho"]
            S = A18["S"][str(ch)]; lam = A18.get("lam_exclusion", A18["lam_dep"])[str(ch)]
        isd, fsd, gdb = shares.get(ch, (None, None, None))
        R_ruling = 10 ** (bar_db / 10); R_noground = R_ruling * 10 ** (credit / 10)
        R_archive = (R_noground / G) * (isd * G + fsd) if isd is not None else R_noground
        # cleaner polarisation: per class the smaller-polarisation excess net of its floor, median over the range's measured classes
        cl = []; cmeas = 0
        for c in RANGES[rng]:
            vals = []
            for p in (0, 1):
                v = ex.get((ch, c, p)); f = floor.get((c, p))
                if v and f: vals.append((float(np.median(v)) - f[0], float(np.median(v)) > f[0] + 3.0 * f[1]))
            if vals:
                best = min(vals, key=lambda x: x[0]); cmeas += best[1]   # r5.1: the class is measured on its cleaner polarization
                vals = [x[0] for x in vals]
                cl.append(min(vals) if A18 is None else U.to_power(max(min(vals), 3e-5), c))
        A_c = (max(float(np.median(cl)), 3e-5) if A18 is None else float(np.median(cl))) if cl else np.nan
        R_other = A_c * S * (1 - rho ** 2 if not GOFF else 1.0) * G / lam if np.isfinite(A_c) else np.nan
        ar_txt = "n/a" if (VLAB and isd is None) else f"{10*np.log10(R_archive):.1f}"
        cp_txt = ("at floor" if (VLAB and not cmeas) else f"{10*np.log10(R_other):.1f}") if np.isfinite(R_other) and R_other > 0 else ""
        rows.append(dict(channel=ch, bar_db=f"{bar_db:.1f}", ground_filter_db_archive=("" if gdb is None else f"{gdb:.1f}"), margin_credit_db=ar_txt,
                         rho_ew=f"{rho:.2f}", ground_filter_db_ew=f"{credit:.1f}", margin_credit_ew_db=f"{10*np.log10(R_noground):.1f}",
                         margin_otherpol_db=cp_txt, margin_both_ew_db=f"{bar_db:.1f}", basis=f"{rng}: {'long' if rng == 'bao_long' else 'short'} BAO baselines, both credits (amendment 8)" if A18 is None else f"{rng}: {'long' if rng == 'bao_long' else 'short'} BAO baselines, {('both credits' if 'world' not in A18 else 'the ground-filter credit, no delay filter') if not GOFF else ('the delay-filter credit alone' if 'world' not in A18 else 'no credit, no delay filter')}, amendment 18 ({per[rng]['basis']}, G {G:.1f})"))
        print(f"{ch:2d}  {rng:9s}  {bar_db:6.1f}       {10*np.log10(R_noground):6.1f}          {10*np.log10(R_archive):6.1f}       {10*np.log10(R_other) if np.isfinite(R_other) and R_other > 0 else float('nan'):6.1f}")
    with open(OUT, "w") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print("wrote robustness_credit.csv (amendment 8 basis)")
    return 0
