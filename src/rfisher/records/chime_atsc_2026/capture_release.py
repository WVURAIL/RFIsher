"""The capture ruling release r5.2, written from the capture handoff.

The release producer's ``build_release.py --r52``, with its tables' logic unchanged and every run in process: the
ruling (:mod:`capture_ruling`) at identity, under r5.2, under the G = 1 sensitivity and with the units switch alone;
channel 24 on its own 2020 in-band measurement (:mod:`cohort_basis`); the phase limit (:mod:`phase_limit`); the
robustness copy (:mod:`robustness`); the duration and keep-gap readings (:mod:`duration`); the two credit readings
(``credit_readings/r3``, the ground credit, and ``credit_readings/r2``, the 200 ns filter plus S with it, each this
command with ``--credit-reading``); the post-processing sensitivity (:mod:`postprocessing`); the within-dump bounds
table; and the promotion evidence (:mod:`promotion_evidence`). Then ``table_of_record_a18.csv``,
``dispositions_a18.csv``, ``thresholds_a18.csv``, ``run/``, ``CHANGES.md`` and ``MANIFEST.json``, whose prose and fixed
fields are the release's (``projects/chime_bao/capture_rules/release_r5_2.json``) and whose ``producer`` names this
repository's commit and modules in place of a source snapshot.

Read-only on every input: the capture handoff, the frozen table of record (``--record-table``, 9867551a; the
robustness copy and the phase limit read it too), the ruling's v7 input (``--input-table``, fd718463), the
decision-evidence directory (``--evidence``: the B-list, the static mask and B-2's rerun), the directory of the frozen
releases (``--releases``: revisions 5 and 5.1, which the bounds table and the promotion evidence compare with) and the
survey-duration compute run (``--duration-reference``).

usage: rfisher records capture-release --rule r5_2 --handoff DIR --record-table TABLE --input-table TABLE --evidence DIR
                                       --releases DIR --duration-reference DIR --rel DIR --run DIR
                                       [--credit-reading r3|r2] [--tables-only]
"""
import contextlib, csv, datetime, glob, hashlib, io, json, math, os, shutil, sys
from importlib.resources import files as _files

import numpy as np

from rfisher import provenance
from rfisher.records.chime_atsc_2026 import (capture_handoff, capture_ruling, cohort_basis, duration, phase_limit,
                                             postprocessing, promotion_evidence, robustness)
from rfisher.records.chime_atsc_2026 import capture_units as U
from rfisher.records.chime_atsc_2026._files import load_json, read_rows

RULE = "r5_2"
RECORD_SHA = "9867551ad591757ed8b8864940376c68666483833478b4711292e0517a27b195"
RANGES = ("shortest", "bao_short", "bao_long")
RTXT = {"bao_short": "short BAO range", "bao_long": "long BAO range", "shortest": "0.3 m range"}
MODULES = (capture_ruling, U, capture_handoff, cohort_basis, phase_limit, robustness, duration, postprocessing, promotion_evidence)


def sha(p):
    with open(p, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()



def run(fn, args, out=None):
    """Run a record in process; its stdout, as the release's subprocess captured it, goes to out."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = fn(args)
    assert not rc, (fn.__module__, rc)
    data = buf.getvalue().encode("utf-8")
    if out:
        with open(out, "wb") as fh: fh.write(data)
    return data


def _release_doc(project=None):
    return json.loads(capture_ruling._project(project).joinpath(capture_ruling.RULES, "release_r5_2.json").read_text())


def main(argv=None):
    a = list(sys.argv[1:] if argv is None else argv)
    def opt(k, d=None):
        if k in a: i = a.index(k); v = a[i + 1]; del a[i:i + 2]; return v
        return d
    rule = opt("--rule", RULE); handoff_dir = opt("--handoff"); RECORD = opt("--record-table"); EVID = opt("--evidence")
    RELEASES = opt("--releases"); DUR = opt("--duration-reference"); REL = opt("--rel"); RUN = opt("--run"); project = opt("--project")
    reading = opt("--credit-reading"); INPUT = opt("--input-table")
    TABLES_ONLY = "--tables-only" in a
    if TABLES_ONLY: a.remove("--tables-only")
    if a: raise SystemExit(f"capture-release: unknown arguments {a}")
    if rule != RULE: raise SystemExit(f"capture-release: the release of record is {RULE}; its earlier revisions are frozen")
    if not all((handoff_dir, RECORD, INPUT, EVID, RELEASES, DUR, REL, RUN)):
        raise SystemExit("capture-release: --handoff, --record-table, --input-table, --evidence, --releases, --duration-reference, --rel "
                         "and --run are required")
    if reading not in (None, "r3", "r2"): raise SystemExit("capture-release: --credit-reading is r3 or r2")
    CREDIT = reading is not None   # only the rulings, channel 24 and the dispositions and thresholds (a credit reading of the release)
    if CREDIT: assert TABLES_ONLY, "a credit reading is built with --tables-only"
    WORLD = "200ns" if reading == "r2" else "none"; GROUND = "on" if CREDIT else "off"
    # the release's switches (build_release.py --r52): r5.1 on r5's, and the settled ground credit
    CH24 = "measured2020"; TLB = "on"; TC = "off"; R51 = True; CF, CG = "one_minus_gamma", "reconciled"
    SETTLED = (CF, CG) == ("one_minus_gamma", "reconciled"); OLDCREDIT = (CF, CG) == ("one_minus_gamma_sq", "released")
    REV = "r5.2" if SETTLED else "r5.1" if R51 else "r5"
    CFX = [] if CF == "one_minus_gamma_sq" else ["--credit-form", CF]   # r5.2: channel 24's ceiling and the post-processing labels in the same form
    BOFF = ["--set", "BOUND_SOURCE=summary", "--set", "BOUND_CALIBRATION=off"] if R51 else []   # r5.1: the bound switches go off with the bounds
    G1T = "literal G = 1" if R51 else "G = 1"                                                  # r5.1, triage row 22
    C24X = ["--per-bin-own-events", "--g1-names", "literal"] if R51 else []                    # r5.1, triage rows 24 and 22
    SENS = ["--sensitivity", reading] if CREDIT else []                                        # the credit reading's world and credit
    RCOL = "_R_exclusion" if WORLD == "none" else "_R_deployed"
    R5 = os.path.join(RELEASES, "capture_ruling_a19_2026-09-25_r5"); R51REL = os.path.join(RELEASES, "capture_ruling_a19_2026-09-25_r5_1")
    B2R51 = os.path.join(EVID, "b_list", "B-2", "r51"); EVB = os.path.join(EVID, "b_list")
    assert os.path.abspath(REL) not in (R5, R51REL), "the frozen releases are only read"
    H = capture_handoff.open_handoff(handoff_dir)
    IN = INPUT; capture_handoff.table_rows(H, "frame_analysis/table_of_record_before_amendment8.csv", IN)
    assert sha(RECORD) == RECORD_SHA
    os.makedirs(RUN, exist_ok=True); os.makedirs(REL, exist_ok=True)
    R = capture_ruling.main
    RARGS = ["--input", IN, "--handoff", handoff_dir, "--ch33-rescan"]
    # 1. the ruling: identity, r5.2, the G = 1 sensitivity, units alone
    if not CREDIT: run(R, ["--rule", "record", "--out", f"{RUN}/identity.csv", *RARGS], f"{RUN}/identity.log"); assert sha(f"{RUN}/identity.csv") == RECORD_SHA
    run(R, ["--rule", RULE, *SENS, "--json", f"{RUN}/a18.json", "--thresholds", f"{RUN}/thresholds.csv", "--out", f"{RUN}/a18_full.csv", *RARGS], f"{RUN}/a18.log")
    if not CREDIT:
        run(R, ["--rule", RULE, "--sensitivity", "g1", "--json", f"{RUN}/a18_g1.json", "--out", f"{RUN}/a18_g1_full.csv", *RARGS], f"{RUN}/a18_g1.log")
        run(R, ["--rule", "record", "--set", "UNITS=power", "--set", "WORLD=none", "--set", "GROUND_CREDIT=off", "--json", f"{RUN}/units_only.json",
                "--out", f"{RUN}/units_only_full.csv", *RARGS], f"{RUN}/units_only.log")
    A = load_json(f"{RUN}/a18.json"); G1 = load_json(f"{RUN}/a18_g1.json") if not CREDIT else None
    # 2. the copies
    PB24 = os.path.join(REL, "ch24_per_bin_a19.csv")
    run(cohort_basis.main, ["--handoff", handoff_dir, "--record-table", RECORD, "--a18", "--world", WORLD, *(["--ground", "off"] if GROUND == "off" else []),
                            "--set", "CH24_BASIS=measured2020", *(["--per-bin", PB24] if not CREDIT else []), *C24X, *CFX, "--json", f"{RUN}/ch24_a18.json"],
        os.path.join(REL, "ch24_basis_a18.txt"))
    C24 = load_json(f"{RUN}/ch24_a18.json")
    _CE = "its ceiling" if CF == "one_minus_gamma_sq" else "its ceiling, (1 - 0.95),"   # r5.2: the settled form
    _W = {("none", "off"): "", ("none", "on"): f" with the ground credit at {_CE} (no measured coherence)",
          ("200ns", "on"): f" with the 200 ns filter plus S and the ground credit at {_CE} (no measured coherence)"}[(WORLD, GROUND)]
    def _st24(rng):
        o = C24["reading"]["ranges"][rng]
        if o["verdict"] in ("excise", "marginal"):
            return (f"{o['verdict']} {o['bar_db']:+.1f} dB{'' if o['verdict'] == 'excise' else ', inside the allowance'} (2020 in-band measurement, policy {o['bar_policy']},"
                    f" G {o['G_bar']:.1f}, tau unmeasured, priced at G {o['G_min_bar']:.2f})")
        return {"at floor": "at the control floor (2020 in-band measurement)", "policy at floor": f"blocked: {', '.join(o['blockers'])} at the control floor (item 6)"}.get(o["verdict"], o["verdict"])
    _B = C24["booking_range"]
    REASON24 = ((f"no 2026 capture products; ruled on its own 2020 in-band measurement (item 34: 12 cohort events, in-band bins 676 to 691, no borrowed"
                 f" quantity){_W}: excised on the {'long' if _B == 'bao_long' else 'short'} BAO range, {_st24(_B)}; "
                 f"{'short' if _B == 'bao_long' else 'long'} BAO range: {_st24('bao_short' if _B == 'bao_long' else 'bao_long')};"
                 f" {C24['reading']['ranges'][_B]['bar_G1_db']:+.1f} dB at {G1T}") if C24["disposition"] == "excise" else
                (f"no 2026 capture products; on its own 2020 in-band measurement (item 34){_W}: long BAO range {_st24('bao_long')}; short BAO range {_st24('bao_short')}"))
    REASON24 += f"; no keep: the stated keep reading is {C24['keep_stated_db']:+.1f} dB (ch24_basis_a18.txt)"
    C24FLAG = ["--ch24", f"{RUN}/ch24_a18.json"]
    if not CREDIT:
        pl = os.path.join(REL, "phase_limit_a18"); os.makedirs(pl, exist_ok=True)
        run(phase_limit.main, ["--handoff", handoff_dir, pl, "--units", "power", "--units-json", f"{RUN}/units_only.json", "--a18-json", f"{RUN}/a18.json",
                               "--record-table", RECORD],
            os.path.join(pl, "phase_limit_a18.log"))
        for f in ("phase_limit_ranges.csv", "phase_limit_classes.csv"): os.replace(os.path.join(pl, f), os.path.join(pl, f.replace(".csv", "_a18.csv")))
        run(robustness.main, ["--handoff", handoff_dir, os.path.join(REL, "robustness_a18.csv"), "--a18", f"{RUN}/a18.json", *C24FLAG, *(["--variant-labels"] if R51 else []),
                              "--record-table", RECORD],
            f"{RUN}/robustness_a18.log")
        run(duration.main, [f"{RUN}/a18.json", REL, *C24FLAG, "--duration-reference", DUR], f"{RUN}/sensitivity_a18.stdout")
        shutil.move(os.path.join(REL, "sensitivity_a18.log"), os.path.join(RUN, "sensitivity_a18.log"))
    if not TABLES_ONLY:
        with open(os.path.join(REL, "CHANGES.md"), "wb") as fh: fh.write(_files("rfisher.records.chime_atsc_2026").joinpath("data", "CHANGES_r5_2.md").read_bytes())

    # 3. table_of_record_a18.csv: the frozen record, every column and value as recorded, then the amendment 18 columns
    def f1(x): return "" if x is None else f"{x:.1f}"
    def deciding(ch):
        per = A["results"][str(ch)]; disp = A["summary"][str(ch)][0]
        if disp == "excise": return "bao_long" if per["bao_long"]["verdict"][0] == "excise" else "bao_short"
        cand = [(per[r]["bar"], r) for r in ("bao_short", "bao_long") if per[r]["bar"] is not None and per[r]["verdict"][0] in ("marginal", "policy at floor", "excise")]
        return max(cand)[1] if cand else ""
    def range_bar(ch, rng):
        p = A["results"][str(ch)][rng]
        return p["bar"] if p["verdict"][0] in ("excise", "marginal", "policy at floor") else None
    rec = list(read_rows(RECORD)); full = list(read_rows(f"{RUN}/a18_full.csv"))
    def _f(x, fmt): return "" if x is None else format(x, fmt)
    def row24(o, rng):
        """r5: channel 24's per-range columns on its own 2020 in-band measurement, in the ruling's formats (the keep_all reading, as
        the ruling prints; the bar is the least policy's)."""
        q = C24["reading"]["ranges"][rng]; ka = q["policies"]["keep_all"]; lam = C24["reading"]["lambda_none"]; k = C24["reading"]["exclusion_factor"] * C24["reading"]["fill_none"]
        v = q["verdict"]; bar = q["bar_db"] if v in ("excise", "marginal", "policy at floor") else None
        Rk = ka["A_power"] * k * ka["G_used"] / lam if ka["measured"] else None
        rr = (lambda b: float((1 - 10 ** ((3.0 - b) / 10)) ** 0.5) if (b is not None and b > 3.0) else None)(bar)
        o.update({f"a18_{rng}_bar_db": f1(bar), f"a18_{rng}_A_net": _f(ka["A_power"] if ka["measured"] else None, ".3e"), f"a18_{rng}_measured": str(ka["measured"]),
                  f"a18_{rng}_floor_level": f"{ka['floor_gate_power']:.3e}", f"a18_{rng}_gate_db": f1(10 * math.log10(ka["floor_gate_power"] * k * ka["G_used"] / lam)),
                  f"a18_{rng}_tau_s": f"{ka['G_min'] * U.TF:.4g}", f"a18_{rng}_tau_status": f"unmeasured, priced at G {ka['G_min']:.2f} (2020 in-band measurement)",
                  f"a18_{rng}_tau_least_s": f"{ka['G_min'] * U.TF:.4g}", f"a18_{rng}_probe_db": "+0.0", f"a18_{rng}_G": f"{ka['G_used']:.4g}", f"a18_{rng}_rho": "",
                  f"a18_{rng}_ground_credit_db": "0.0", f"a18_{rng}{RCOL}": _f(Rk, ".4g"),
                  f"a18_{rng}_R_none": _f(ka["A_power"] * ka["G_used"] / lam if ka["measured"] else None, ".4g"), f"a18_{rng}_rescue_rho": _f(rr, ".4f"), f"a18_{rng}_verdict": v})
    assert len(rec) == len(full) and all(a["freq_id"] == b["freq_id"] for a, b in zip(rec, full))
    rc = ["_A_net", "_measured", "_floor_level", "_gate_db", "_tau_s", "_tau_status", "_tau_least_s", "_probe_db", "_G", "_rho", "_ground_credit_db", RCOL, "_R_none", "_rescue_rho", "_verdict"]
    new = ["a18_disposition", "a18_deciding_range", "a18_deciding_bar_db", "a18_reason"]
    for rng in RANGES: new += [f"a18_{rng}_bar_db"] + [f"a18_{rng}{c}" for c in rc]
    with open(os.path.join(REL, "table_of_record_a18.csv") if not CREDIT else os.devnull, "w", newline="") as fh:   # a credit reading carries no table of record
        w = csv.DictWriter(fh, fieldnames=list(rec[0]) + new); w.writeheader()
        for r, a in zip(rec, full):
            o = dict(r); ch = int(r["channel"]); o["a18_disposition"], o["a18_reason"] = a["disposition"], a["policy_or_reason"]
            if ch == 24 and r["policy_or_reason"] == "no products": o["a18_disposition"], o["a18_reason"] = C24["disposition"], REASON24   # item 9
            ruled = r["role"] == "data" and str(ch) in A["summary"] and a["disposition"] == A["summary"][str(ch)][0] and a["policy_or_reason"] == A["summary"][str(ch)][1]
            dr = deciding(ch) if ruled else ""
            o["a18_deciding_range"] = dr; o["a18_deciding_bar_db"] = f1(range_bar(ch, dr)) if dr else ""
            for rng in RANGES:
                o[f"a18_{rng}_bar_db"] = f1(range_bar(ch, rng)) if str(ch) in A["results"] else ""
                for c in rc: o[f"a18_{rng}{c}"] = a[f"{rng}{c}"]
                if str(ch) in A["results"]:   # sub-second times and small gains: four significant figures in place of the record's integer format
                    p = A["results"][str(ch)][rng]
                    for c, k in (("_tau_s", "tau"), ("_tau_least_s", "tau_least"), ("_G", "G")): o[f"a18_{rng}{c}"] = "" if p[k] is None else f"{p[k]:.4g}"
            if ch == 24 and CH24 == "measured2020":   # r5: every amendment column of channel 24's rows is its own 2020 in-band reading
                B = C24["booking_range"]; o["a18_deciding_range"] = B or ""; o["a18_deciding_bar_db"] = f1(C24["deciding_bar_db"]) if B else ""
                for rng in RANGES: row24(o, rng)
            w.writerow(o)

    # 4. dispositions_a18.csv: one row per channel
    recd = {}
    for r in rec:
        if r["role"] == "data" and r["channel"] not in recd: recd[r["channel"]] = r["disposition"]
    def state(ch, rng, res):
        p = res["results"][str(ch)][rng]; v = p["verdict"][0]; b = p["bar"]
        if v == "excise": return f"excise {b:+.1f} dB ({p['basis']}, G {p['G_bar']:.1f}, tau {p.get('tstat_bar') or p['tstat']})"
        if v == "marginal": return f"marginal {b:+.1f} dB, inside the allowance ({p['basis']}, G {p['G_bar']:.1f}, tau {p.get('tstat_bar') or p['tstat']})"
        if v == "policy at floor": return f"blocked: {', '.join(p['blockers'])} at the control floor (item 6); the measured policies read {b:+.1f} dB"
        if v == "at floor": return "at the control floor" + (" on the lowest epoch" if "lowest epoch" in p["verdict"][1] else "")
        return v
    rows = []
    for ch in range(14, 38):
        s = str(ch)
        if ch == 24 and CH24 == "measured2020":   # r5, item 34
            exc24 = sorted({f"{p}: {why}" for rng in ("bao_short", "bao_long") for p, why in C24["reading"]["ranges"][rng]["excluded"].items()})
            rows.append(dict(channel=24, record_disposition=recd.get(s, ""), a18_disposition=C24["disposition"], deciding_range=C24["booking_range"] or "",
                             deciding_bar_db=f1(C24["deciding_bar_db"]) if C24["booking_range"] else "", reason=REASON24, bao_short=_st24("bao_short"), bao_long=_st24("bao_long"),
                             policies_excluded="; ".join(exc24), sensitivity_G1_disposition=C24["disposition_G1"], threshold=C24["threshold"])); continue
        if ch == 24:
            rows.append(dict(channel=24, record_disposition=recd.get(s, ""), a18_disposition=C24["disposition"], deciding_range="bao_long (2020 cohort)", deciding_bar_db="",
                             reason=REASON24, bao_short="no capture products", bao_long="no capture products", policies_excluded="",
                             sensitivity_G1_disposition=C24["disposition"], threshold=C24["threshold"])); continue
        if ch == 37:   # the label the table of record and table_of_record_a18.csv carry; the expected outcome's "all others"
            rows.append(dict(channel=37, record_disposition=recd.get(s, ""), a18_disposition="undetermined", deciding_range="", deciding_bar_db="",
                             reason="reference channel (no DTV allocation, no tolerance on the board): the control whose Stokes I reading defines the floor",
                             bao_short="", bao_long="", policies_excluded="", sensitivity_G1_disposition="undetermined", threshold="")); continue
        per = A["results"][s]; disp = A["summary"][s][0]; dr = deciding(ch)
        exc = sorted({f"{p}: {why}" for rng in ("bao_short", "bao_long") for p, why in per[rng]["excluded"].items()})
        other = "bao_short" if dr == "bao_long" else "bao_long"
        if disp == "excise": reason = f"excised on the {RTXT[dr]}: {state(ch, dr, A)}; {RTXT[other]}: {state(ch, other, A)}"
        elif dr: reason = f"{RTXT[dr]}: {state(ch, dr, A)}; {RTXT[other]}: {state(ch, other, A)}"
        else: reason = "both BAO ranges at the control floor" + ("; no pilot bin, lowest epoch at the floor" if "lowest epoch" in per["bao_long"]["verdict"][1] + per["bao_short"]["verdict"][1] else "")
        t = next((r for r in read_rows(f"{RUN}/thresholds.csv") if r["channel"] == s and r["range"] == "channel"), None)
        rows.append(dict(channel=ch, record_disposition=recd.get(s, ""), a18_disposition=disp, deciding_range=dr, deciding_bar_db=f1(range_bar(ch, dr)) if dr else "",
                         reason=reason, bao_short=state(ch, "bao_short", A), bao_long=state(ch, "bao_long", A), policies_excluded="; ".join(exc),
                         sensitivity_G1_disposition=G1["summary"][s][0] if G1 else "",
                         threshold=(f"tau > {float(t['tau_threshold_s']):.4g} s" if t and t["tau_threshold_s"] else
                                    "excised at any τ" if t and t["threshold_text"].startswith("excised at any τ") else "not excisable at any τ")))
    if R51:
        # triage row 22: "G = 1" had two meanings. The G = 1 sensitivity run (a18_g1.json: unmeasured and refused classes at G = 1, a
        # bounded class at its bound) is "unmeasured classes at G = 1"; the literal reading puts every class at G = 1, which is R at G = 1
        # on the deciding range (the ruling's R1: the least policy, or the least epoch), excised where a BAO range that excises has
        # R1 over the allowance (the code's test), which is the thresholds' "excised at any τ"
        TH = {(r["channel"], r["range"]): r for r in read_rows(f"{RUN}/thresholds.csv")}
        for o in rows:
            ch = int(o["channel"]); s_ = str(ch); o["sensitivity_unmeasured_G1_disposition"] = o.pop("sensitivity_G1_disposition"); thr_ = o.pop("threshold")
            if ch == 24 and CH24 == "measured2020":
                B = C24["booking_range"]; lit = C24["disposition_G1"]; lb = C24["reading"]["ranges"][B]["bar_G1_db"] if B else None
            elif ch in (24, 37) or s_ not in A["results"]: lit, lb = ("undetermined" if ch == 37 else o["sensitivity_unmeasured_G1_disposition"]), None
            else:
                per = A["results"][s_]; ex_ = [rng for rng in ("bao_short", "bao_long") if per[rng]["verdict"][0] == "excise" and per[rng]["R1"] is not None and per[rng]["R1"] > U.ALLOW_R]
                lit = "excise" if ex_ else "undetermined"; dr = o["deciding_range"]
                lb = 10 * math.log10(per[dr]["R1"]) if (dr and per[dr]["R1"] is not None and per[dr]["verdict"][0] in ("excise", "marginal", "policy at floor")) else None
                assert (lit == "excise") == any(TH[(s_, rng)]["threshold_text"].startswith("excised at any") for rng in ("bao_short", "bao_long")), ch
            o["sensitivity_literal_G1_disposition"] = lit; o["literal_G1_bar_db"] = f1(lb); o["threshold"] = thr_
    with open(os.path.join(REL, "dispositions_a18.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

    # 5. thresholds_a18.csv: the producer's, with channel 24 on its 2020 basis in place of its empty capture rows
    thr = [r for r in read_rows(f"{RUN}/thresholds.csv") if r["channel"] != "24"]
    fields = list(thr[0]); i24 = next(i for i, r in enumerate(thr) if int(r["channel"]) > 24)
    if CH24 == "borrowed":
        thr.insert(i24, {**{k: "" for k in fields}, "channel": "24", "range": "channel", "verdict_a18": "undetermined",
                         "threshold_text": "not excisable at any τ (2020 basis: the borrowed pilot-to-in-band correction is unmeasured on channel 24 and takes its most favorable value, item 9; no 2026 capture products)"})
    else:   # r5, item 34: the thresholds of channel 24's own 2020 in-band reading, from its unrounded R at G = 1 with the code's test
        new24 = []; tt = []
        for rng in ("bao_short", "bao_long"):
            q = C24["reading"]["ranges"][rng]; th = C24["thresholds"][rng]; t = th["tau_threshold_s"]; R1 = th["R_at_G1"]
            any_ = th["text"].startswith("excised at any")
            if t is not None: tt.append(t)
            txt = (f"excised when the least coherence-time reading of the range exceeds {t:.6g} s" if t is not None else (th["text"] if any_ else f"not excisable at any τ ({th['text']})"))
            gb = q["G_bar"]
            rep_ = str((10 ** (q["bar_db"] / 10) > U.ALLOW_R) == (q["verdict"] == "excise")) if q["verdict"] in ("excise", "marginal") else ""
            new24.append({**{k: "" for k in fields}, "channel": "24", "range": rng, "verdict_a18": q["verdict"], "tau_s": (f"{q['G_min_bar'] * U.TF:.6g}" if gb else ""),
                          "tau_status": (f"unmeasured, priced at G {q['G_min_bar']:.2f} (2020 in-band measurement)" if gb else ""), "tau_least_s": (f"{q['G_min_bar'] * U.TF:.6g}" if gb else ""),
                          "G_of_bar": (f"{gb:.6g}" if gb else ""), "R_at_G1": (f"{R1:.6g}" if R1 is not None else ""), "tau_threshold_s": (f"{t:.6g}" if t is not None else ""),
                          "G_threshold": (f"{U.gain_bao(t, 24):.6g}" if t is not None else ("1" if any_ else "")), "threshold_text": txt, "verdict_reproduced": rep_,
                          "threshold_brackets": (str(R1 * U.gain_bao(t, 24) > U.ALLOW_R and not (R1 * U.gain_bao(t * (1 - 1e-9), 24) > U.ALLOW_R)) if t is not None else "")})
        anyr = [x["range"] for x in new24 if x["threshold_text"].startswith("excised at any")]
        new24.append({**{k: "" for k in fields}, "channel": "24", "range": "channel", "verdict_a18": C24["disposition"],
                      "tau_threshold_s": (f"{min(tt):.6g}" if (tt and not anyr) else ""),
                      "threshold_text": ((f"excised at any τ (R over the allowance at {G1T} on {' and '.join(anyr)})" if anyr else
                                          f"excised when either BAO range's least coherence-time reading exceeds its threshold; the lesser is {min(tt):.6g} s" if tt else "not excisable at any τ")
                                         + " (2020 in-band measurement, item 34)")})
        thr[i24:i24] = new24
    with open(os.path.join(REL, "thresholds_a18.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields); w.writeheader(); w.writerows(thr)
    # 5b. the run outputs the release tables are built from (unrounded results, full ruling tables, thresholds, logs)
    rr = os.path.join(REL, "run"); os.makedirs(rr, exist_ok=True)
    RUNFILES = ("a18.json", "a18.log", "thresholds.csv", "ch24_a18.json") if CREDIT else \
               ("a18.json", "a18.log", "a18_full.csv", "thresholds.csv", "a18_g1.json", "a18_g1.log", "a18_g1_full.csv", "units_only.json", "units_only.log",
                "units_only_full.csv", "identity.log", "ch24_a18.json", "robustness_a18.log", "sensitivity_a18.log")
    for f in RUNFILES:
        shutil.copy2(os.path.join(RUN, f), os.path.join(rr, f))
    if CREDIT: print("credit reading:", REL); return 0
    # r5: the credit readings are the rule itself with the ground credit ("r3") and with the 200 ns filter plus S and the ground
    # credit ("r2"), built here into credit_readings/, and the post-processing sensitivity is computed against them
    for k in ("r3", "r2"):
        d = os.path.join(REL, "credit_readings", k); shutil.rmtree(d, ignore_errors=True)
        run(main, ["--rule", RULE, "--handoff", handoff_dir, "--record-table", RECORD, "--input-table", IN, "--evidence", EVID, "--releases", RELEASES, "--duration-reference", DUR,
                   "--rel", d, "--run", os.path.join(RUN, f"credit_{k}"), "--tables-only", "--credit-reading", k, *(["--project", project] if project else [])],
            os.path.join(RUN, f"credit_{k}.log"))
    run(postprocessing.main, ["--handoff", handoff_dir, f"{RUN}/a18.json", f"{RUN}/a18_g1.json", os.path.join(REL, "dispositions_a18.csv"),
                              os.path.join(REL, "robustness_a18.csv"), os.path.join(REL, "credit_readings", "r3"), os.path.join(REL, "credit_readings", "r2"),
                              os.path.join(REL, "postprocessing_sensitivity.csv"),
                              "--ch24", f"{RUN}/ch24_a18.json", os.path.join(REL, "credit_readings", "r3", "run", "ch24_a18.json"),
                              os.path.join(REL, "credit_readings", "r2", "run", "ch24_a18.json"), *(["--r51"] if R51 else []), *CFX],
        f"{RUN}/postprocessing_sensitivity.log")
    shutil.copy2(f"{RUN}/postprocessing_sensitivity.log", os.path.join(rr, "postprocessing_sensitivity.log"))
    # r5: the bounds read and where each prices a class (item 35), with the bars it moves (r4's readings: the bounds off)
    run(R, ["--rule", RULE, "--set", "TAU_LOWER_BOUNDS=off", *BOFF, *([] if TC == "off" else ["--set", "TAU_CENSOR=on"]), "--json", f"{RUN}/a18_bounds_off.json",
            "--out", f"{RUN}/a18_bounds_off_full.csv", *RARGS], f"{RUN}/a18_bounds_off.log")
    run(R, ["--rule", RULE, "--set", "TAU_LOWER_BOUNDS=off", *BOFF, *([] if TC == "off" else ["--set", "TAU_CENSOR=on"]), "--sensitivity", "g1",
            "--json", f"{RUN}/a18_g1_bounds_off.json", "--out", f"{RUN}/a18_g1_bounds_off_full.csv", *RARGS], f"{RUN}/a18_g1_bounds_off.log")
    Aoff = load_json(f"{RUN}/a18_bounds_off.json"); G1off = load_json(f"{RUN}/a18_g1_bounds_off.json")
    LBall = capture_handoff.tau_lower_bounds(H, censor=(TC == "on" or R51), source=("fits" if R51 else "summary"), calibrate=R51); CN = {(0, 1): "ns1", (0, 32): "ns32", (0, 64): "ns64", (0, 128): "ns128", (0, 255): "ns255", (1, 0): "ew1", (2, 0): "ew2", (3, 0): "ew3"}
    used = set(A["tau_lower_bounds_used"]); brows = []
    R5A = load_json(os.path.join(R5, "run", "a18.json")) if R51 else None
    def _bar(p): return f1(p["bar"] if p["verdict"][0] in ("excise", "marginal", "policy at floor") else None)
    for (ch, c), v in sorted(LBall.items()):
        if ch == 37: continue
        key = f"{ch}|{CN[c]}"; rng = next((r for r, cl in (("bao_short", ((0, 32), (0, 64))), ("bao_long", ((0, 128), (0, 255), (1, 0), (2, 0), (3, 0)))) if c in cl), "")
        p5, p4 = A["results"][str(ch)][rng], Aoff["results"][str(ch)][rng]; g5, g4 = G1["results"][str(ch)][rng], G1off["results"][str(ch)][rng]
        if not R51:
            brows.append(dict(channel=ch, cls=CN[c], range=rng, bound_s=f"{v['lb']:.4g}", least_variant=v["least_variant"], lane_least_s=f"{v['lane']:.4g}",
                              check_least_s=(f"{v['check']:.4g}" if "check" in v else ""), span_s=f"{v['span']:.4g}", priced_s=f"{v['lb_priced']:.4g}", capped=str(v["capped"]),
                              used=str(key in used), range_tau_status_r5=(p5.get("tstat_bar") or p5["tstat"]) if key in used else "", verdict_r5=p5["verdict"][0],
                              bar_r4_db=_bar(p4), bar_r5_db=_bar(p5), G_bar_r4=_f(p4["G_bar"], ".4g"), G_bar_r5=_f(p5["G_bar"], ".4g"),
                              G1_bar_r4_db=_bar(g4), G1_bar_r5_db=_bar(g5)))
            continue
        # r5.1: the bound as fitted (row 35), the censored classes' bounds (B-4), B-3's calibration, and the bars with the bounds off (r5.1's
        # other switches kept) and on, beside r5's
        cal = v["calibration"]; p5r = R5A["results"][str(ch)][rng]
        brows.append(dict(channel=ch, cls=CN[c], range=rng, bound_s=f"{v['lb']:.4g}", least_variant=v["least_variant"], lane_least_s=f"{v['lane']:.4g}",
                          check_least_s=(f"{v['check']:.4g}" if np.isfinite(v.get("check", np.nan)) else ""), source=("B-4 lane run (censored class)" if v.get("b4") else "lane and check (fits_check.csv)"),
                          span_s=f"{v['span']:.4g}", priced_s=f"{v['lb_priced']:.4g}", capped=str(v["capped"]),
                          null_fcr=f"{cal['fcr']:.4f}", null_cells_at_or_above=f"{cal['n_at_or_above']} of {cal['n_cells']}", null_max_s=f"{cal['null_max_s']:.4g}",
                          null_fcr_same_class=("" if cal["fcr_same_class"] is None else f"{cal['fcr_same_class']:.4f}"), calibration_passes=str(cal["passes"]),
                          used=str(key in used), range_tau_status=(p5.get("tstat_bar") or p5["tstat"]) if key in used else "", verdict=p5["verdict"][0],
                          bar_bounds_off_db=_bar(p4), bar_db=_bar(p5), bar_r5_db=_bar(p5r), G_bar_bounds_off=_f(p4["G_bar"], ".4g"), G_bar=_f(p5["G_bar"], ".4g"),
                          unmeasured_G1_bar_bounds_off_db=_bar(g4), unmeasured_G1_bar_db=_bar(g5)))
    with open(os.path.join(REL, "tau_lower_bounds_a19.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(brows[0]), lineterminator="\n"); w.writeheader(); w.writerows(brows)
    for f in ("a18_bounds_off.json", "a18_bounds_off.log", "a18_g1_bounds_off.json", "a18_g1_bounds_off.log"): shutil.copy2(os.path.join(RUN, f), os.path.join(rr, f))
    # 5c. r5.1: B-2's least corners on the r5.1 readings, and the grounds each excision carries (PROMOTION_EVIDENCE.md)
    PE_INPUTS = promotion_evidence.inputs(EVID)
    PROMO = promotion_evidence.write(REL, B2R51, EVB, A, C24, rev=REV, r51_rel=(None if OLDCREDIT else R51REL), evid=EVID, r5=R5)
    print("item 18 as coded:", PROMO["coded"], "under B-2's admissible grid:", PROMO["grid"])
    if TABLES_ONLY: print("tables:", REL); return 0
    write_manifest(REL, H, handoff_dir, RECORD, EVID, RELEASES, DUR, A, PE_INPUTS, project, IN)
    print("release:", REL)
    return 0


def write_manifest(REL, H, handoff_dir, RECORD, EVID, RELEASES, DUR, A, PE_INPUTS, project=None, INPUT=None):
    """MANIFEST.json: the release's prose and fixed fields, then what this build read and wrote."""
    doc = _release_doc(project); fixed = doc["fields"]
    assert fixed["r5_1"]["ruling_switches"] == {k: A["switches"][k] for k in fixed["r5_1"]["ruling_switches"]}
    assert fixed["r5_2"]["ruling_switches"] == {k: A["switches"][k] for k in fixed["r5_2"]["ruling_switches"]}
    files = {}
    for p in sorted(glob.glob(os.path.join(REL, "**", "*"), recursive=True)):
        if os.path.isfile(p) and os.path.relpath(p, REL) != "MANIFEST.json": files[os.path.relpath(p, REL)] = sha(p)
    inputs = {f"handoff/{k}": v["sha256"] for k, v in sorted(H.files.items())}
    inputs["handoff/manifest.json"] = sha(os.path.join(handoff_dir, "manifest.json"))
    inputs[RECORD] = sha(RECORD)
    if INPUT is not None: inputs[INPUT] = sha(INPUT)
    for p in PE_INPUTS + tuple(sorted(glob.glob(os.path.join(EVID, "b_list", "B-2", "r51", "*.csv")) + glob.glob(os.path.join(EVID, "b_list", "B-2", "*.csv")))):
        if os.path.isfile(p): inputs[p] = sha(p)
    for rel in ("capture_ruling_a19_2026-09-25_r5/run/a18.json", "capture_ruling_a19_2026-09-25_r5/dispositions_a18.csv",
                "capture_ruling_a19_2026-09-25_r5_1/credit_readings/r2/run/a18.json", "capture_ruling_a19_2026-09-25_r5_1/credit_readings/r2/run/ch24_a18.json"):
        p = os.path.join(RELEASES, rel)
        if os.path.isfile(p): inputs[p] = sha(p)
    for name in ("bin_sigma_lambda.csv", "channel_lambda.csv"):
        p = os.path.join(DUR, name)
        if os.path.isfile(p): inputs[p] = sha(p)
    computed = dict(built=datetime.datetime.now().isoformat(timespec="seconds"), python=sys.version.split()[0], interpreter=sys.executable,
                    switches_a18=A["switches"],
                    producer=dict(provenance.producer_identity(), modules={m.__name__: sha(m.__file__) for m in MODULES}),
                    commands=[(f"rfisher records capture-release --rule {RULE} --handoff <handoff> --record-table <table of record> --input-table <v7 table>"
                               f" --evidence <evidence> --releases <releases> --duration-reference <duration> --rel <release> --run <run>   (this release)"),
                              ("rfisher records capture-ruling --rule r5_2 --json a18.json --thresholds thresholds.csv --input "
                               "<v7 table> --handoff <handoff> --out a18_full.csv --ch33-rescan"),
                              "rfisher records capture-release ... --tables-only --credit-reading r3   (and r2)"],
                    inputs=inputs, datasets=dict(handoff=H.manifest.get("inputs", {}), note="the reduced dumps, products and lanes the handoff was derived from"),
                    files=files,
                    tests=dict(suite="tests/records (test_capture_identity.py, test_capture_rules.py, test_capture_handoff.py)",
                               note="the producer's own test log (tests_a18.txt) is superseded by the RFIsher suite"))
    m = {}
    for k in doc["key_order"]:
        if k in fixed: m[k] = fixed[k]
        elif k in computed: m[k] = computed[k]
    with open(os.path.join(REL, "MANIFEST.json"), "w") as fh: json.dump(m, fh, indent=1, ensure_ascii=False)
