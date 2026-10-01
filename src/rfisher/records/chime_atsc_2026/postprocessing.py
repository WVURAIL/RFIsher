"""The post-processing sensitivity of the idealized ruling (DECISIONS.md items 17 and 18): every r4 excision (no credit of
any kind) evaluated again with the credits applied. Revision 3 is r4 with the ground-filter credit (1 - gamma^2); revision 2
is the 200 ns delay filter plus its credit S (with the ground credit too). Channel by channel.

All three rulings take the same readings (A, tau, G, policies, epochs, blockers). The ground credit lowers each range's bar
by its own -10 log10(1 - gamma^2), gamma the range's measured coherence (r4 minus r3, checked on every range with a bar in
both); the filter moves every bar of a channel by one shift (r3 minus r2, filter_sensitivity.csv of revision 3). A credit
can only remove an excision, never add one (asserted).

Labels (item 18), on the r4 disposition:
  robust to post-processing   excised in r4, r3 and r2
  idealized-only              excised in r4 but not with a credit; removed_by names the credit (the ground filter
                              (1 - gamma^2), revision 3, or the 200 ns filter plus S, revision 2)
  not excised                 not excised in r4
The item 18 promotion also needs robustness under the rule variants, which this table records beside the label: the r4
G = 1 sensitivity (run/a18_g1.json) and, from robustness_a18.csv, the cleaner polarization and the archive shares.
The cleaner polarization excises only where the booking range is measured above the control floor on that polarization
(the amplitude test of the ruling, any class, three floor scatters over the floor mean, on the frozen per-pol files):
robustness_a18.csv floors each class at 3e-5 in amplitude before conversion, so its margin exists for a range that is at the
floor, and a range at the floor cannot excise.

r5 (amendment 19): the same table for revision 5. Its credit readings are the r5 rule (the within-dump lower bounds of item 35
and channel 24's measured 2020 basis of item 34) with the ground credit ("r3") and with the 200 ns filter plus S and the ground
credit ("r2"), built by build_release.py --credit-reading into the release's credit_readings/, and passed here in place of the
frozen revisions 3 and 2 (the column names keep r4, r3 and r2 for the no-credit, ground-credit and filter readings). With --ch24
C4.json C3.json C2.json (ch24_2020_basis_a18.py --json of each reading) and channel 24 on its measured basis, channel 24's row
is read from those: its bars, its G = 1 disposition, and the cleaner polarization and archive shares of robustness_a18.csv. Its
ground credit is the ceiling (1 - 0.95^2), since channel 24 has no measured coherence.

r5.1 (triage rows 22, 26 and 35): with --r51 the rulings record every switch (the credit readings' GROUND_CREDIT and WORLD
included), the G = 1 sensitivity is named for what it is, "unmeasured classes at G = 1" (r4_unmeasured_G1_disposition), and a
literal G = 1 column (every class at G = 1: r4_literal_G1_disposition and r4_literal_G1_bar_db, from dispositions_a18.csv) stands
beside it; the literal reading is reported, not a rule variant of item 18 (a measured cross-frame amplitude cannot be priced
below the admissible minimum, B-2 D3). A variant that does not apply is printed as such ("n/a" archive shares, "at floor"
cleaner polarization, robustness_a18.csv --variant-labels); an "n/a" variant is not a failure, an "at floor" one is (as in r5).
Without --r51 the output is r5's.

r5.2 (item 41, B-1): with --credit-form one_minus_gamma the credit readings take the ground credit in the settled form (1 - gamma) at
B-1's reconciled range gamma (ruling_a18.py --r52), channel 24 at (1 - 0.95), and removed_by names that form; the labels follow
from the readings as before. Without it the output is r5.1's.

The release's ``postprocessing_sensitivity_a18.py``, with its logic unchanged; the frame-analysis tables come from the
capture handoff.
usage: rfisher records postprocessing --handoff DIR <r4 a18.json> <r4 a18_g1.json> <r4 dispositions_a18.csv>
                                      <r4 robustness_a18.csv> <r3 release dir> <r2 release dir> <out csv>
                                      [--ch24 C4.json C3.json C2.json] [--r51] [--credit-form one_minus_gamma_sq|one_minus_gamma]
"""
import csv, math, os

import numpy as np

from rfisher.records.chime_atsc_2026 import capture_handoff
from rfisher.records.chime_atsc_2026 import capture_units as U
from rfisher.records.chime_atsc_2026._files import load_json, read_rows


def main(argv=None):
    import sys
    argv = ["postprocessing"] + list(sys.argv[1:] if argv is None else argv)
    SCIENCE = ["20260916162300", "20260917040230", "20260917090230", "20260917140230"]
    RANGES = {"bao_short": [(0, 32), (0, 64)], "bao_long": [(0, 128), (0, 255), (1, 0), (2, 0), (3, 0)]}
    if "--handoff" not in argv: raise SystemExit("postprocessing: --handoff DIR is required")
    H = capture_handoff.open_handoff(argv[argv.index("--handoff") + 1])
    i_ = argv.index("--handoff"); argv = argv[:i_] + argv[i_ + 2:]
    _ex, _fl = {}, {}
    for r in H.rows("frame_analysis/class_excess_epochs.csv"):
        if r["excess"] and r["epoch"] in SCIENCE: _ex.setdefault((int(r["channel"]), (int(r["ew"]), int(r["ns"])), int(r["pol"])), []).append(float(r["excess"]))
    for r in H.rows("frame_analysis/class_floor_bins.csv"):
        if r["epoch"] in SCIENCE: _fl.setdefault(((int(r["ew"]), int(r["ns"])), int(r["pol"])), []).append(float(r["excess"]))
    _floor = {k: (float(np.mean(v)), float(np.std(v, ddof=1))) for k, v in _fl.items()}
    def cleaner_measured(ch, rng):
        """Classes of the range measured above the control floor on the cleaner (smaller net) polarization, and how many were read."""
        n = m = 0
        for c in RANGES[rng]:
            best = None
            for p in (0, 1):
                v = _ex.get((ch, c, p)); f = _floor.get((c, p))
                if v and f:
                    A = float(np.median(v)); cand = (A - f[0], A > f[0] + 3.0 * f[1])
                    if best is None or cand[0] < best[0]: best = cand
            if best is not None: n += 1; m += best[1]
        return m, n
    A4, G14, D4, RB4, R3, R2, OUT = argv[1:8]
    R51 = "--r51" in argv
    CF = argv[argv.index("--credit-form") + 1] if "--credit-form" in argv else "one_minus_gamma_sq"   # r5.2, item 41
    assert CF in ("one_minus_gamma_sq", "one_minus_gamma") and (CF == "one_minus_gamma_sq" or R51)
    GFORM = "(1 - gamma^2)" if CF == "one_minus_gamma_sq" else "(1 - gamma)"
    C24 = None
    if "--ch24" in argv:
        i = argv.index("--ch24"); C24 = [load_json(x) for x in argv[i + 1:i + 4]]
        if C24[0].get("basis") != "measured2020": C24 = None
        else: assert [(c["world"], c["ground"]) for c in C24] == [("none", "off"), ("none", "on"), ("200ns", "on")], [(c["world"], c["ground"]) for c in C24]
        if C24 is not None: assert all(c.get("ground_credit_form", "one_minus_gamma_sq") == CF for c in C24[1:]), "r5.2: channel 24's credit readings in the same form"
    a4 = load_json(A4); g4 = load_json(G14)
    a3 = load_json(os.path.join(R3, "run", "a18.json")); a2 = load_json(os.path.join(R2, "run", "a18.json"))
    assert a4["switches"]["GROUND_CREDIT"] == "off" and a4["world"] == "none" and g4["switches"]["GROUND_CREDIT"] == "off"
    if R51:   # r5.1: every switch recorded
        assert a3["switches"]["GROUND_CREDIT"] == "on" and a3["world"] == "none" and "world" not in a2 and a2["switches"]["WORLD"] == "200ns" and a2["switches"]["GROUND_CREDIT"] == "on"
        assert {k: v for k, v in a4["switches"].items() if k != "GROUND_CREDIT"} == {k: v for k, v in a3["switches"].items() if k != "GROUND_CREDIT"}
        assert {k: v for k, v in a4["switches"].items() if k not in ("GROUND_CREDIT", "WORLD")} == {k: v for k, v in a2["switches"].items() if k not in ("GROUND_CREDIT", "WORLD")}
        assert a3["switches"].get("CREDIT_FORM", "one_minus_gamma_sq") == CF and a2["switches"].get("CREDIT_FORM", "one_minus_gamma_sq") == CF   # r5.2
    else:
        assert "GROUND_CREDIT" not in a3["switches"] and a3["world"] == "none" and "world" not in a2
        assert {k: v for k, v in a4["switches"].items() if k != "GROUND_CREDIT"} == a3["switches"]
    d4 = {r["channel"]: r for r in read_rows(D4)}
    d3 = {r["channel"]: r for r in read_rows(os.path.join(R3, "dispositions_a18.csv"))}
    d2 = {r["channel"]: r for r in read_rows(os.path.join(R2, "dispositions_a18.csv"))}
    rb4 = {r["channel"]: r for r in read_rows(RB4)}
    BAO = ("bao_short", "bao_long")
    def db(x): return 10 * math.log10(x)
    def over(b): return 10 ** (b / 10) > U.ALLOW_R          # item 7, the code's test
    def bar(a, c, rng):
        p = a["results"][c][rng]
        return p["bar"] if p["verdict"][0] in ("excise", "marginal", "policy at floor") else None
    def f2(x): return "" if x is None else f"{x:.2f}"
    rows = []
    for ch in range(14, 38):
        c = str(ch); r4, r3, r2 = d4[c], d3[c], d2[c]
        o = dict(channel=ch)
        for w, r in (("r4", r4), ("r3", r3), ("r2", r2)):
            o[f"{w}_disposition"] = r["a18_disposition"]; o[f"{w}_deciding_range"] = r["deciding_range"]; o[f"{w}_deciding_bar_db"] = ""
        if ch == 24 and C24 is not None:   # r5: channel 24 on its own 2020 in-band measurement, in each reading
            cr = -10 * math.log10(1 - 0.95 ** 2) if CF == "one_minus_gamma_sq" else -10 * math.log10(1 - 0.95)   # r5.2: the settled form
            for rng in BAO:
                b4, b3, b2 = (C["reading"]["ranges"][rng]["bar_db"] if C["reading"]["ranges"][rng]["verdict"] in ("excise", "marginal", "policy at floor") else None for C in C24)
                assert b4 is not None and b3 is not None and abs(b4 - b3 - cr) < 1e-9, (rng, b4, b3)
                o[f"ground_credit_{rng}_db"] = f"{cr:.2f}"
                for w, b, C in (("r4", b4, C24[0]), ("r3", b3, C24[1]), ("r2", b2, C24[2])):
                    o[f"{w}_{rng}_state"] = C["reading"]["ranges"][rng]["verdict"]; o[f"{w}_{rng}_bar_db"] = f2(b)
            for w, r, C in (("r4", r4, C24[0]), ("r3", r3, C24[1]), ("r2", r2, C24[2])):
                if r["deciding_range"] in BAO: o[f"{w}_deciding_bar_db"] = f2(C["reading"]["ranges"][r["deciding_range"]]["bar_db"])
        elif c in a4["results"] and c != "37":
            for rng in BAO:
                b4, b3, b2 = bar(a4, c, rng), bar(a3, c, rng), bar(a2, c, rng)
                p3 = a3["results"][c][rng]; cr = p3["credit_db"]
                assert a4["results"][c][rng]["credit_db"] == 0.0 and a4["results"][c][rng]["rho"] == p3["rho"]
                assert (b4 is None) == (b3 is None) and (b4 is None or abs(b4 - b3 - cr) < 1e-9), (ch, rng, b4, b3, cr)
                v4, v3 = a4["results"][c][rng]["verdict"][0], p3["verdict"][0]
                assert v4 == v3 or {v4, v3} == {"excise", "marginal"}, (ch, rng, v4, v3)
                o[f"ground_credit_{rng}_db"] = f"{cr + 0.0:.2f}" if cr is not None else ""   # + 0.0: a range with no coherence prints 0.00, not -0.00
                for w, b, a in (("r4", b4, a4), ("r3", b3, a3), ("r2", b2, a2)):
                    o[f"{w}_{rng}_state"] = a["results"][c][rng]["verdict"][0]; o[f"{w}_{rng}_bar_db"] = f2(b)
            for w, r, a in (("r4", r4, a4), ("r3", r3, a3), ("r2", r2, a2)):
                if r["deciding_range"] in BAO: o[f"{w}_deciding_bar_db"] = f2(bar(a, c, r["deciding_range"]))
        ex4, ex3, ex2 = (r["a18_disposition"] == "excise" for r in (r4, r3, r2))
        assert not (ex3 and not ex4) and not (ex2 and not ex3), ch      # a credit can only remove an excision
        removed = [t for t, e in ((f"the ground filter {GFORM}, r3", ex3), ("the 200 ns filter plus S, r2", ex2)) if not e]
        if not ex4: o["label"] = "not excised"; removed = []
        elif not removed: o["label"] = "robust to post-processing"
        else: o["label"] = "idealized-only"
        # the credit that first removes it: the ground credit alone (r3) before the filter (r2, which also carries the ground credit)
        o["removed_by"] = removed[0].rsplit(",", 1)[0] if removed else ""
        # the rule variants on r4 (item 18 needs both): G = 1, the cleaner polarization and the archive shares
        if ex4:
            rb = rb4[c]
            cp = float(rb["margin_otherpol_db"]) if rb["margin_otherpol_db"] not in ("", "at floor") else None
            ar = float(rb["margin_credit_db"]) if rb["margin_credit_db"] != "n/a" else None   # r5.1: n/a where the ledger has no shares
            if ch == 24 and C24 is not None:
                g1 = C24[0]["disposition_G1"]; brng = C24[0]["booking_range"]; cm, cn = C24[0]["cleaner_pol"]["measured"], C24[0]["cleaner_pol"]["n"]
            else:
                g1 = g4["summary"][c][0]
                brng = "bao_long" if a4["results"][c]["bao_long"]["verdict"][0] == "excise" else "bao_short"
                cm, cn = cleaner_measured(ch, brng)
            assert rb["basis"].startswith(brng)
            o["r4_unmeasured_G1_disposition" if R51 else "r4_G1_disposition"] = g1
            if R51: o["r4_literal_G1_disposition"] = r4["sensitivity_literal_G1_disposition"]; o["r4_literal_G1_bar_db"] = r4["literal_G1_bar_db"]
            o["r4_cleaner_pol_bar_db"] = rb["margin_otherpol_db"]; o["r4_cleaner_pol_measured_classes"] = f"{cm} of {cn} ({brng})"
            o["r4_archive_shares_bar_db"] = rb["margin_credit_db"]
            failed = [n for n, ok in (("unmeasured classes at G = 1" if R51 else "G = 1", g1 == "excise"),
                                      ("cleaner polarization at the floor" if not cm else "cleaner polarization", cm > 0 and cp is not None and over(cp)),
                                      ("archive shares", ar is None or over(ar))) if not ok]
            o["robust_in_rule_variants"] = "yes" if not failed else "no (" + ", ".join(failed) + ")"
            o["item18_promotion"] = str(not failed and o["label"] == "robust to post-processing")
        else:
            o["item18_promotion"] = "False"
        if o["label"] == "idealized-only":
            wr = "r3" if not ex3 else "r2"; dr = r4["deciding_range"]
            o["note"] = (f"excised with no credit ({dr} {o['r4_deciding_bar_db']} dB); with {o['removed_by']} the same reading is"
                         f" {o[wr + '_' + dr + '_bar_db']} dB, {(r3 if wr == 'r3' else r2)['a18_disposition']}")
        elif o["label"] == "robust to post-processing":
            dr = r4["deciding_range"]
            o["note"] = (f"excised in all three; the ground credit lowers the {dr} bar by {o['ground_credit_' + dr + '_db']} dB (r3), and the 200 ns"
                         f" filter plus S reads {o['r2_deciding_bar_db']} dB (r2, {r2['deciding_range']})")
            if ch == 24 and C24 is not None: o["note"] += "; channel 24 on its own 2020 in-band measurement, the ground credit at its ceiling (no measured coherence)"
        elif ch == 24 and C24 is None: o["note"] = "no 2026 capture products; undetermined on the 2020 basis in all three (item 9)"
        elif ch == 37: o["note"] = "reference channel"
        elif r4["deciding_range"]: o["note"] = f"undetermined in all three ({r4['bao_long'] if r4['deciding_range'] == 'bao_long' else r4['bao_short']})"
        else: o["note"] = "undetermined in all three: both BAO ranges at the control floor"
        rows.append(o)
    fields = ["channel", "label", "removed_by"] + [f"{w}_{k}" for w in ("r4", "r3", "r2") for k in ("disposition", "deciding_range", "deciding_bar_db")]
    fields += [f"ground_credit_{rng}_db" for rng in BAO] + [f"{w}_{rng}_{k}" for rng in BAO for w in ("r4", "r3", "r2") for k in ("state", "bar_db")]
    fields += (["r4_unmeasured_G1_disposition", "r4_literal_G1_disposition", "r4_literal_G1_bar_db"] if R51 else ["r4_G1_disposition"]) + ["r4_cleaner_pol_bar_db", "r4_cleaner_pol_measured_classes", "r4_archive_shares_bar_db", "robust_in_rule_variants", "item18_promotion", "note"]
    with open(OUT, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n", restval=""); w.writeheader(); w.writerows(rows)
    lab = lambda s: [r["channel"] for r in rows if r["label"] == s]
    RV = (("r5.2" if CF != "one_minus_gamma_sq" else "r5.1") if R51 else "r5") if C24 is not None else "r4"   # r5: the no-credit ruling is revision 5's (its columns keep the r4_ prefix)
    print(f"{RV} excisions (no credit): {[r['channel'] for r in rows if r['r4_disposition'] == 'excise']}; robust to post-processing: {lab('robust to post-processing')};"
          f" idealized-only: {[(r['channel'], r['removed_by']) for r in rows if r['label'] == 'idealized-only']}")
    print(f"robust in the {RV} rule variants ({'unmeasured classes at G = 1' if R51 else 'G = 1'}, cleaner polarization, archive shares): {[r['channel'] for r in rows if r.get('robust_in_rule_variants') == 'yes']};"
          f" item 18 promotion (both): {[r['channel'] for r in rows if r['item18_promotion'] == 'True']}")
    return 0
