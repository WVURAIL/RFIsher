"""The exclusion-side phase limit on the coherence gain: G = min(tau_level, tau_phase) / T_frame.

tau_phase is the phase coherence time of the in-band residual on a baseline class, read on the polarisation
that sets A there (amendment 11). Its estimator mirrors the level estimator of cadence_tau.py:
  gamma_ab   the between-dump phasor coherence of the pair of epochs (a, b): the median over the channel's
             in-band bins of cos(phase difference) of the reference-subtracted class mean (phasor14.py, the
             definition of cadence_lags_tenclasses.py), for every pair of the fourteen epochs closer than a
             sidereal day;
  classes    each pair goes to the nearest of cadence_tau.py's LAG_CLASSES in log lag, and a class value is
             the mean over its pairs, as the level's class-mean D is;
  crossing   the decoherence 1 - gamma is a structure function whose incoherent plateau is known, one, since
             gamma of an unrelated phase is zero; tau_phase is the lag at which the class-mean decoherence
             first reaches CROSS = 1 - 1/e of that plateau, that is gamma first falls to 1/e, linearly
             interpolated between class centres, with at least three populated classes below 7200 s. For an
             exponential decay both this and the level's crossing return the e-folding time;
  bound      gamma above 1/e through the longest populated class below 7200 s: tau_phase is bounded below
             at that class, 3600 s, and the lower end is entered, as for a level bound.
Noise lowers gamma, so the crossing it reads is the earlier one: the side the exclusion rule grants.
Each class of a range then enters the record's aggregation (ruling_baseline.py range_gain: the gain classes
measured above the control floor, geometric median over the measured and bound classes, amendments 7, 11, 12,
16; the borrowed 19.5 m class for a long range with no measured class, amendment 9) with tau_level replaced by
min(tau_level, tau_phase), for the class value and for the least trim probe. R is linear in G, so every
policy's R scales by G_amended / G_record and the verdict rule is the record's (excise when the bar and the bar
at the least trim probe both exceed the 3 dB allowance).
The limit is applied only where it can weaken an exclusion: on a range the record excises. On a range it does not
excise, a lower G moves toward a keep, which the rule does not credit.
It is evaluated on every range the record excises: every priced range of the six excised channels (15, 17, 30,
31, 33, 35), and the 0.3 m range on each channel whose label is undetermined and whose 0.3 m range the record
excises (14, 16, 18, 19, 21, 22, 23, 25, 26, 27, 32), read from the table of record, not listed by hand.
Reads the ruling's own products read-only and phasor14.csv; computes the 0.3 m class (0, 1), which phasor14.py
does not carry, with the same definition from the reduced products, on every channel above. Writes phase_limit_classes.csv and
phase_limit_ranges.csv beside this file; changes nothing in the ruling of record.

Amendment 18 copy (2026-09-24, DECISIONS.md item 10): the same computation with the bars in the new units. The phase
limit scales G, and a ratio of gains has no units, so every G, tau and gain change is the record's; what changes is
the bar it scales. Under --units power the bar of record on each evaluated range is the ruling's bar with only the
units switch of item 1 set (ruling_a18.py --set UNITS=power, read unrounded from its --json output), and R_deployed,
R_none and the detection gate are that run's keep-all values; the evaluated ranges are the record's, as amendment 17
defines them; in the CSV those columns are named *_units_only (bar_units_only_db, R_deployed_units_only, R_none_units_only,
gate_units_only_db) and the log states the units. --units booked (the default) reproduces the vendored outputs byte for byte (tests/test_a18.py). With
--a18-json the channel 15 reading on the amendment 18 ruling is appended.
r3 (item 15): a units-only json run with --set WORLD=none (the no-filter world: lambda_none, no delay-filter credit S) is
accepted; its exclusion-side ratio columns are then named R_exclusion_* in place of R_deployed_*, and the log says so. A
200 ns units-only json gives revision 2's output byte for byte.
r4 (item 17): a units-only json run with --set GROUND_CREDIT=off (no ground-filter credit) is accepted; its rescue
coherence is then the coherence a ground filter would need with no credit taken, and the log says so. A units-only json
with the ground credit gives revision 3's (or revision 2's) output byte for byte.
The table of record is read from --record-table TABLE (the frozen table, or the table written in the same run).
usage: rfisher records phase-limit --handoff DIR --record-table TABLE <out dir> [--units booked|power --units-json RUN.json]
                                   [--a18-json A18.json]

The release's ``phase_limit_a18.py``, with its logic unchanged; the record, the frame-analysis tables, the vendored
phasor14.csv and the class means of the reduced dumps come from the capture handoff.
"""
import collections, csv, os, re

import numpy as np

from rfisher.records.chime_atsc_2026 import capture_handoff
from rfisher.records.chime_atsc_2026._files import load_json


def main(argv=None):
    import sys
    argv = ["phase-limit"] + list(sys.argv[1:] if argv is None else argv)
    _args = argv[1:]; OUT = None; UNITS = "booked"; UJSON = A18JSON = None; H = None; RT = None
    while _args:
        k = _args.pop(0)
        if not k.startswith("--") and OUT is None: OUT = k; continue
        v = _args.pop(0)
        if k == "--handoff": H = capture_handoff.open_handoff(v)
        elif k == "--units": UNITS = v
        elif k == "--units-json": UJSON = load_json(v)
        elif k == "--a18-json": A18JSON = load_json(v)
        elif k == "--record-table": RT = v
    if H is None or OUT is None: raise SystemExit("phase-limit: --handoff and an output directory are required")
    assert UNITS in ("booked", "power") and (UNITS == "booked" or UJSON is not None)
    if UJSON is not None: assert UJSON["switches"]["UNITS"] == "power" and all(v == dict(POL="larger", UNMEASURED_TAU="current", GAIN="zero", KEEP="coded", EVERY_POLICY="coded", ALLOWANCE="db", THRESHOLDS="off")[k] for k, v in UJSON["switches"].items() if k not in ("UNITS", "WORLD", "GROUND_CREDIT"))
    WORLD = UJSON["switches"].get("WORLD", "200ns") if UJSON is not None else "200ns"   # r3, item 15
    GROUND = UJSON["switches"].get("GROUND_CREDIT", "on") if UJSON is not None else "on"   # r4, item 17
    NFFT = 16384; TF = NFFT * 2.56e-6; SIDEREAL = 86164.0905; CAP = SIDEREAL
    PLATEAU_START = 7200.0; CROSS = 1.0 - 1.0 / np.e; MIN_CLASSES = 3; ALLOW_DB = 3.0; NSIG = 3.0
    LAG_CLASSES = [15, 30, 45, 60, 90, 120, 180, 240, 360, 480, 600, 720, 960, 1200, 3600, 18000, 36000, 86400]
    SCIENCE = ["20260916162300", "20260917040230", "20260917090230", "20260917140230"]
    RANGES = {"shortest": [(0, 1)], "bao_short": [(0, 32), (0, 64)], "bao_long": [(0, 128), (0, 255), (1, 0), (2, 0), (3, 0)]}
    NAME = {(0, 1): "ns1", (0, 32): "ns32", (0, 64): "ns64", (0, 128): "ns128", (0, 255): "ns255", (1, 0): "ew1", (2, 0): "ew2", (3, 0): "ew3"}
    TAU_FILE = {c: ("cadence_tau.csv" if c == (0, 1) else f"cadence_tau_{n}.csv") for c, n in NAME.items()}
    EXCISED = (15, 17, 30, 31, 33, 35)
    BOOKING = {15: "bao_short", 17: "bao_long", 30: "bao_long", 31: "bao_long", 33: "bao_long", 35: "bao_long"}

    record = {int(r["channel"]): r for r in capture_handoff.table_rows(H, "frame_analysis/table_of_record.csv", RT) if r["role"] == "data"}
    # every range the record excises, and the channels, not excised, that carry one: the limit is evaluated on all of them
    EXCISED_RANGES = {(ch, rng) for ch, r in record.items() for rng in RANGES if r[f"{rng}_verdict"] == "excise"}
    assert {ch for ch, r in record.items() if r["disposition"] == "excise"} == set(EXCISED)
    UNDETERMINED = tuple(sorted({ch for ch, _ in EXCISED_RANGES} - set(EXCISED)))
    assert all(record[ch]["disposition"] == "undetermined" for ch in UNDETERMINED)
    assert all(rng == "shortest" for ch, rng in EXCISED_RANGES if ch in UNDETERMINED)
    EVALUATED = EXCISED + UNDETERMINED
    ex = {}
    for r in H.rows("frame_analysis/class_excess_epochs.csv"):
        if r["excess"]:
            ex[(int(r["channel"]), r["epoch"], (int(r["ew"]), int(r["ns"])), int(r["pol"]))] = float(r["excess"])
    fl = collections.defaultdict(list)
    for r in H.rows("frame_analysis/class_floor_bins.csv"):
        if r["epoch"] in SCIENCE:
            fl[((int(r["ew"]), int(r["ns"])), int(r["pol"]))].append(float(r["excess"]))
    floor = {k: (float(np.mean(v)), float(np.std(v, ddof=1))) for k, v in fl.items()}

    def reading(ch, c):
        """(A_net, measured, pol) on the polarisation with the larger A_net over the science dumps (amendment 11)."""
        best = None
        for p in (0, 1):
            v = [ex[(ch, e, c, p)] for e in SCIENCE if (ch, e, c, p) in ex]
            if not v or (c, p) not in floor: continue
            A = float(np.median(v)); fm, fs = floor[(c, p)]
            if best is None or A - fm > best[0]: best = (A - fm, A > fm + NSIG * fs, p)
        return best

    def level_tau(ch, c, p):
        """(status, tau, least trim probe) of the level on class c, polarisation p, as ruling_baseline.py reads it."""
        fp = f"frame_analysis/{TAU_FILE[c][:-4]}_pol{p}.csv"
        row = next(r for r in H.rows(fp) if r["bins"] == "inband" and int(r["channel"]) == ch)
        t = float(row["tau_c_s"]) if row["tau_c_s"] else np.nan
        probes = [float(m) for m in re.findall(r"(?:measured|bound|constant)\s+([\d.]+)", row.get("probes", "") or "")]
        tl = min(min(probes), t) if (probes and np.isfinite(t)) else (min(probes) if probes else np.nan)
        return row["status"], t, tl

    def gmed(v):
        v = sorted(v); n = len(v)
        return v[n // 2] if n % 2 else float(np.sqrt(v[n // 2 - 1] * v[n // 2]))

    def lag_class(dt):
        return min(LAG_CLASSES, key=lambda L: abs(np.log(max(dt, 1) / L)))

    # between-dump phasor coherence per pair: phasor14.csv for the seven BAO classes
    pairs = collections.defaultdict(list)          # (ch, class name, pol) -> [(lag, lag class, gamma)]
    for r in H.rows("phasor/phasor14.csv.gz"):
        if r["pol"] in ("0", "1") and int(r["channel"]) in EVALUATED:
            pairs[(int(r["channel"]), r["cls"], int(r["pol"]))].append((float(r["lag_s"]), int(r["lag_class"]), float(r["rho"])))
    # and the 0.3 m class (0, 1) from the reduced products, with phasor14.py's definition; the same loader serves
    # the channel 37 control check at the end, so each epoch is read once
    CHS = set(EVALUATED) | {34, 37}
    labels, RAW = capture_handoff.raw_epochs(H)   # the class means load_raw read from the reduced dumps (the handoff's)
    t = {l: float(np.median([v["t0"] for v in RAW[l].values()])) for l in labels}
    def referenced(c, refch):
        """Class means less one complex mean over the bins of the reference channels (phasor14.py uses 34 and 37)."""
        res = {}
        for l in labels:
            res[l] = {f: dict(ch=v["ch"], m=list(v["raw"][c])) for f, v in RAW[l].items()}
            for p in (0, 1):
                ref = [v["raw"][c][p] for v in RAW[l].values() if v["ch"] in refch]
                r0 = np.mean(ref) if ref else 0
                for v in res[l].values(): v["m"][p] = v["m"][p] - r0
        return res
    def pair_rows(res, ch, p):
        rows = []
        for i in range(len(labels)):
            for j in range(i + 1, len(labels)):
                a, b = labels[i], labels[j]; dt = abs(t[b] - t[a])
                rh = [(res[a][f]["m"][p] * np.conj(res[b][f]["m"][p])).real / (abs(res[a][f]["m"][p]) * abs(res[b][f]["m"][p]))
                      for f in res[a] if res[a][f]["ch"] == ch and f in res[b] and abs(res[a][f]["m"][p]) > 0 and abs(res[b][f]["m"][p]) > 0]
                if rh: rows.append((dt, lag_class(dt), float(np.median(rh)), a, b))
        return rows
    REF = (34, 37)
    CHECKED = [ch for ch in EVALUATED if pairs[(ch, "ns32", 0)]]   # the evaluated channels phasor14.csv carries
    for c in ((0, 1), (0, 32)):                    # (0, 32) is recomputed only to check the loader against phasor14.csv
        res = referenced(c, REF)
        for ch in (EVALUATED if c == (0, 1) else CHECKED):
            for p in (0, 1):
                rows = [r[:3] for r in pair_rows(res, ch, p)]
                if c == (0, 1): pairs[(ch, "ns1", p)] = rows
                else:
                    ref = sorted(pairs[(ch, "ns32", p)]); mine = sorted(rows)
                    assert len(ref) == len(mine) and max(abs(x[2] - y[2]) for x, y in zip(ref, mine)) < 1e-5, (ch, p)
    print("loader check: the (0, 32) class recomputed from the reduced products reproduces phasor14.csv to better than 1e-5 on"
          f" channels {', '.join(map(str, CHECKED))} (every evaluated channel phasor14.csv carries), both polarisations")

    def phase_tau(ch, name, p, stat="mean"):
        """(status, tau_phase, {lag class: class gamma}) by the crossing above."""
        use = [(L, g) for dt, L, g in pairs[(ch, name, p)] if dt < SIDEREAL and L < PLATEAU_START]
        by = collections.defaultdict(list)
        for L, g in use: by[L].append(g)
        centers = sorted(by); vals = {L: (float(np.mean(by[L])) if stat == "mean" else float(np.median(by[L]))) for L in centers}
        if len(centers) < MIN_CLASSES: return "no cadence lags", np.nan, vals
        d = [1.0 - vals[L] for L in centers]
        if max(d) < CROSS: return "bound", float(max(centers)), vals
        k = next(i for i, x in enumerate(d) if x >= CROSS)
        if k == 0: return "measured", float(centers[0]), vals
        x0, x1, y0, y1 = centers[k - 1], centers[k], d[k - 1], d[k]
        return "measured", float(x1 if y1 == y0 else x0 + (CROSS - y0) * (x1 - x0) / (y1 - y0)), vals

    def db(x): return 10 * np.log10(x) if (x is not None and np.isfinite(x) and x > 0) else np.nan

    class_rows, range_rows = [], []
    for ch in EVALUATED:
        rec = record[ch]
        for rng, classes in RANGES.items():
            if ch in UNDETERMINED and (ch, rng) not in EXCISED_RANGES: continue   # only the excised range of these
            rd = {c: reading(ch, c) for c in classes}
            gcls = [c for c in classes if rd[c] and rd[c][1]] or classes
            info = {}
            for c in gcls:
                p = rd[c][2]
                ls, lt, ll = level_tau(ch, c, p)
                ps, pt, vals = phase_tau(ch, NAME[c], p)
                ps_md, pt_md, _ = phase_tau(ch, NAME[c], p, "median")
                binds = ls in ("measured", "bound") and ps == "measured" and np.isfinite(lt) and pt < lt
                eff_status = "measured" if binds else ls
                info[c] = dict(p=p, ls=ls, lt=lt, ll=ll, ps=ps, pt=pt, pt_md=pt_md, eff_status=eff_status,
                               et=min(lt, pt) if binds else lt, el=min(ll, pt) if (binds or (ps == "measured" and np.isfinite(ll) and pt < ll)) else ll, binds=binds)
                class_rows.append(dict(channel=ch, range=rng, booking=("yes" if BOOKING.get(ch) == rng else "no"), cls=NAME[c], pol=p,
                                       tau_level_s=f"{lt:.1f}", level_status=ls, tau_level_least_s=f"{ll:.1f}",
                                       tau_phase_s=f"{pt:.1f}" if np.isfinite(pt) else "", phase_status=ps,
                                       tau_phase_median_s=f"{pt_md:.1f}" if np.isfinite(pt_md) else "",
                                       phase_binds="yes" if binds else "no",
                                       gamma_by_lag=" ".join(f"{L}:{g:+.2f}" for L, g in vals.items())))
            def agg(key, skey):
                meas = [info[c][key] for c in gcls if info[c][skey] == "measured" and np.isfinite(info[c][key])]
                bnd = [info[c][key] for c in gcls if info[c][skey] == "bound" and np.isfinite(info[c][key])]
                if meas: return gmed(meas + bnd)
                if bnd: return bnd[0]
                return np.nan
            t0 = agg("lt", "ls"); t0l = agg("ll", "ls"); t1 = agg("et", "eff_status"); t1l = agg("el", "eff_status")
            for c in gcls: info[c]["gap"] = min(info[c]["et"], 1200.0)
            tgap = agg("gap", "eff_status")
            borrowed = False
            if not np.isfinite(t0) and rng == "bao_long":
                p64 = reading(ch, (0, 64))
                if p64:
                    ls, lt, ll = level_tau(ch, (0, 64), p64[2])
                    if ls == "measured":
                        ps, pt, vals = phase_tau(ch, "ns64", p64[2]); ps_md, pt_md, _ = phase_tau(ch, "ns64", p64[2], "median")
                        binds = ps == "measured" and pt < lt
                        t0, t0l = lt, ll; t1 = min(lt, pt) if binds else lt; t1l = min(ll, pt) if (ps == "measured" and pt < ll) else ll
                        tgap = min(t1, 1200.0)
                        borrowed = True
                        class_rows.append(dict(channel=ch, range=rng, booking=("yes" if BOOKING.get(ch) == rng else "no"), cls="ns64 (borrowed)", pol=p64[2],
                                               tau_level_s=f"{lt:.1f}", level_status=ls, tau_level_least_s=f"{ll:.1f}",
                                               tau_phase_s=f"{pt:.1f}" if np.isfinite(pt) else "", phase_status=ps,
                                               tau_phase_median_s=f"{pt_md:.1f}" if np.isfinite(pt_md) else "",
                                               phase_binds="yes" if binds else "no",
                                               gamma_by_lag=" ".join(f"{L}:{g:+.2f}" for L, g in vals.items())))
            # check against the record
            rt = rec[f"{rng}_tau_s"]; rG = rec[f"{rng}_G"]
            if rt:
                assert abs(round(t0) - float(rt)) <= 1, (ch, rng, t0, rt)
            if not np.isfinite(t0): continue
            G0 = min(t0, CAP) / TF; G1 = min(t1, CAP) / TF; G0l = min(t0l, CAP) / TF; G1l = min(t1l, CAP) / TF
            if rG: assert abs(G0 - float(rG)) <= 1, (ch, rng, G0, rG)
            Rd = float(rec[f"{rng}_R_deployed"]) if rec[f"{rng}_R_deployed"] else np.nan
            Rn = float(rec[f"{rng}_R_none"]) if rec[f"{rng}_R_none"] else np.nan
            if UNITS == "power":   # item 1: the keep-all ratios of the units-only run
                ka = UJSON["results"][str(ch)][rng]["pols"].get("keep_all", {})
                Rd = ka.get("R_dep") if ka.get("R_dep") is not None else np.nan
                Rn = ka.get("R_none") if ka.get("R_none") is not None else np.nan
            verdict = rec[f"{rng}_verdict"]
            # the bar of record is the least over the policies (or the lowest epoch); R is linear in G so it scales with it
            bar0 = None
            txt = rec["policy_or_reason"]
            seg = {"bao_long": r"long BAO baselines", "bao_short": r"short BAO baselines", "shortest": r"0\.3 m baseline"}[rng]
            mm = re.search(seg + r"[^:]*: (?:excise \()?([-\d.]+) dB over tolerance", txt)
            if mm: bar0 = float(mm.group(1))
            if UNITS == "power":   # item 1: the unrounded bar of the units-only run on the same range
                u = UJSON["results"][str(ch)][rng]
                assert u["verdict"][0] == verdict or verdict != "excise", (ch, rng, u["verdict"][0], verdict)
                bar0 = u["bar"] if (u["bar"] is not None and u["verdict"][0] in ("excise", "marginal")) else None
            if verdict == "excise" and bar0 is None: raise SystemExit(f"no bar parsed for {ch} {rng}")
            scale = db(G1 / G0)
            bar1 = bar0 + scale if bar0 is not None else np.nan
            probe1 = db(G1l / G1) if G1 > 0 else 0.0
            bar1l = bar1 + probe1 if np.isfinite(bar1) else np.nan
            v1 = verdict
            if verdict == "excise":
                v1 = "excise" if (bar1 > ALLOW_DB and bar1l > ALLOW_DB) else ("marginal" if bar1 > ALLOW_DB else "inside allowance")
            rho = float(rec[f"{rng}_rho"]); rr = np.nan
            if np.isfinite(bar1) and bar1 > ALLOW_DB:
                rem = (1 - rho ** 2 if GROUND == "on" else 1.0) * 10 ** ((ALLOW_DB - bar1) / 10)   # r4: no credit taken under off
                rr = float(np.sqrt(1 - rem)) if 0 < rem < 1 else np.nan
            g0 = float(rec[f"{rng}_gate_db"]) if rec[f"{rng}_gate_db"] else np.nan
            if UNITS == "power":
                ka = UJSON["results"][str(ch)][rng]["pols"].get("keep_all", {})
                g0 = 10 * np.log10(ka["R_floor"]) if (ka.get("R_floor") is not None and ka["R_floor"] > 0) else np.nan
            range_rows.append(dict(channel=ch, range=rng, booking=("yes" if BOOKING.get(ch) == rng else "no"), verdict_record=verdict,
                                   tau_record_s=f"{t0:.1f}", G_record=f"{G0:.0f}", tau_amended_s=f"{t1:.1f}", G_amended=f"{G1:.0f}",
                                   tau_least_amended_s=f"{t1l:.1f}", phase_binds=("yes" if t1 < t0 - 1e-9 else "no"),
                                   gain_change_db=f"{scale:+.2f}", bar_record_db=(f"{bar0:.1f}" if bar0 is not None else ""),
                                   bar_amended_db=(f"{bar1:.1f}" if np.isfinite(bar1) else ""),
                                   bar_amended_least_probe_db=(f"{bar1l:.1f}" if np.isfinite(bar1l) else ""),
                                   R_deployed_record=(f"{Rd:.4g}" if np.isfinite(Rd) else ""), R_deployed_amended=(f"{Rd * G1 / G0:.4g}" if np.isfinite(Rd) else ""),
                                   R_none_record=(f"{Rn:.4g}" if np.isfinite(Rn) else ""), R_none_amended=(f"{Rn * G1 / G0:.4g}" if np.isfinite(Rn) else ""),
                                   tau_inside_allowance_s=(format(t1 * 10 ** ((ALLOW_DB - bar1) / 10), ".1f" if UNITS == "booked" else ".4g") if np.isfinite(bar1) else ""),
                                   rescue_rho_amended=(format(rr, ".4f" if UNITS == "booked" else ".6f") if np.isfinite(rr) else ""),
                                   gate_record_db=(f"{g0:.1f}" if np.isfinite(g0) else ""), gate_amended_db=(f"{g0 + scale:.1f}" if np.isfinite(g0) else ""),
                                   verdict_amended=v1,
                                   bar_at_gap_floor_db=(f"{bar1 + db(tgap / t1):.1f}" if np.isfinite(bar1) else ""),
                                   applied=("yes" if (t1 < t0 - 1e-9 and verdict == "excise") else
                                            ("no: the range is not excised, so G sets only its detection gate, and lowering the gate is the keep direction, which the rule does not credit"
                                             if t1 < t0 - 1e-9 else ""))))

    # under --units power the bar, R and gate columns the record carries in the booked form are the units-only run's power-form
    # values, so they are named for what they hold; tau, G and verdict_record are the record's own
    UNIT_NAMES = dict(bar_record_db="bar_units_only_db", R_deployed_record="R_deployed_units_only", R_none_record="R_none_units_only",
                      gate_record_db="gate_units_only_db") if UNITS == "power" else {}
    if WORLD == "none": UNIT_NAMES.update(R_deployed_record="R_exclusion_units_only", R_deployed_amended="R_exclusion_amended")   # item 15
    for name, rows in (("phase_limit_classes.csv", class_rows), ("phase_limit_ranges.csv", range_rows)):
        with open(os.path.join(OUT, name), "w", newline="") as fh:
            rows_w = [{UNIT_NAMES.get(k, k): v for k, v in r.items()} for r in rows]
            w = csv.DictWriter(fh, fieldnames=list(rows_w[0])); w.writeheader(); w.writerows(rows_w)
    if UNITS == "power":
        print("units: every bar, R and gate below and in phase_limit_ranges.csv is in the amendment 18 power form (item 1, the per-frame")
        print("covariance ratio A_net^2 N n_b), read on the record's evaluated ranges with the units switch alone (ruling_a18.py --set")
        print("UNITS=power); the columns the record names *_record are named *_units_only. tau, G and verdict_record are the record's.")
        if WORLD == "none":
            print("world: the units-only run is in the no-filter world (--set WORLD=none, item 15): lambda_none and no delay-filter credit S on")
            if GROUND == "on": print("the exclusion side, the ground-filter credit kept; its exclusion-side ratio is in the R_exclusion_* columns.")
            else: print("the exclusion side and no ground-filter credit (--set GROUND_CREDIT=off, item 17); its exclusion-side ratio is in the\nR_exclusion_* columns, and rescue_rho_amended is the coherence a ground filter would need with no credit taken.")

    print("per class, on the polarisation that sets A: tau_level (status) and tau_phase (status; class-median check)")
    for r in class_rows:
        print(f"ch{r['channel']} {r['range']:9s} {'book' if r['booking'] == 'yes' else '    '} {r['cls']:15s} pol{r['pol']}: level {r['tau_level_s']:>7s} s ({r['level_status']:8s})"
              f"  phase {r['tau_phase_s'] or 'n/a':>7s} s ({r['phase_status']}; median {r['tau_phase_median_s'] or 'n/a'})  binds {r['phase_binds']}")
        print(f"      gamma: {r['gamma_by_lag']}")
    print()
    print("per range: record and amended tau, G and bar (dB over tolerance, least policy; at the least trim probe)")
    for r in range_rows:
        print(f"ch{r['channel']} {r['range']:9s} {'book' if r['booking'] == 'yes' else '    '} {r['verdict_record']:15s} tau {r['tau_record_s']:>7s} -> {r['tau_amended_s']:>7s} s"
              f"  G {r['G_record']:>6s} -> {r['G_amended']:>6s}  bar {r['bar_record_db'] or 'n/a':>5s} -> {r['bar_amended_db'] or 'n/a':>5s} dB"
              f" (least probe {r['bar_amended_least_probe_db'] or 'n/a'})  binds {r['phase_binds']}  -> {r['verdict_amended']}")
    print()
    print("gate (dB over tolerance at the floor reading) where the limit binds:")
    for r in range_rows:
        if r["phase_binds"] == "yes" and r["gate_record_db"]:
            print(f"ch{r['channel']} {r['range']}: {r['gate_record_db']} -> {r['gate_amended_db']} dB; verdict {r['verdict_record']} -> {r['verdict_amended']}")
    print()
    print("least class gamma on the classes that enter a range gain (level measured or bound), excised channels other than 15:")
    low = min((float(g.split(":")[1]), r["channel"], r["cls"], g.split(":")[0]) for r in class_rows
              if r["channel"] in EXCISED and r["channel"] != 15 and r["level_status"] in ("measured", "bound") for g in r["gamma_by_lag"].split())
    print(f"  {low[0]:+.3f} (channel {low[1]}, {low[2]}, lag class {low[3]} s) against the crossing at 1/e = {1 / np.e:.3f}")
    print()
    print("sensitivity of the binding booking class to the crossing level (not the estimator of record):")
    for r in class_rows:
        if r["phase_binds"] == "yes" and r["booking"] == "yes":
            ch, c, p = r["channel"], r["cls"], int(r["pol"])
            by = collections.defaultdict(list)
            for dt, L, g in pairs[(ch, c, p)]:
                if dt < SIDEREAL and L < PLATEAU_START: by[L].append(g)
            cs = sorted(by); v = [float(np.mean(by[L])) for L in cs]
            for lvl, what in ((1 / np.e, "gamma = 1/e (estimator of record)"), (1 - 1 / np.e, "gamma = 1 - 1/e")):
                k = next(i for i, x in enumerate(v) if x <= lvl)
                tx = cs[k - 1] + (v[k - 1] - lvl) * (cs[k] - cs[k - 1]) / (v[k - 1] - v[k])
                rr = next(x for x in range_rows if x["channel"] == ch and x["range"] == r["range"])
                print(f"  ch{ch} {c} pol{p}, {what}: tau_phase {tx:.1f} s, bar {float(rr['bar_record_db']) + db(tx / float(r['tau_level_s'])):.1f} dB")
    print()
    print("the lag gap: every class value capped at 1200 s, the low end of the unsampled gap between the 1200 s and 3600 s classes")
    for r in range_rows:
        if r["verdict_amended"] == "excise" and r["bar_amended_db"]:
            print(f"  ch{r['channel']} {r['range']:9s} {'book' if r['booking'] == 'yes' else '    '} bar {r['bar_amended_db']:>5s} -> {r['bar_at_gap_floor_db']:>5s} dB"
                  f" ({float(r['bar_at_gap_floor_db']) - float(r['bar_amended_db']):+.1f})")
    print()
    print("channel 37 control: per-lag-class median over the cadence pairs (15 to 1200 s), then median (least to greatest) over")
    print("the lag classes, as phasor_summary.py reports it, under three references: the record's one complex mean over the bins")
    print("of channels 34 and 37 (reproduces phasor_summary.log), none, and channel 34 alone; 'pooled' is the median (least to")
    print("greatest) over the cadence pairs themselves")
    for refname, refch in (("34+37", (34, 37)), ("none", ()), ("34 only", (34,))):
        for c in NAME:
            res = referenced(c, refch); cells = []
            for p in (0, 1):
                by = collections.defaultdict(list)
                for dt, L, g, a, b in pair_rows(res, 37, p):
                    if a.startswith("C") and b.startswith("C"): by[L].append(g)
                v = [float(np.median(by[L])) for L in sorted(by)]; allp = [g for L in by for g in by[L]]
                cells.append(f"pol{p} {np.median(v):+.2f} ({min(v):+.2f} to {max(v):+.2f}); pooled {np.median(allp):+.2f} ({min(allp):+.2f} to {max(allp):+.2f}, {len(allp)} pairs)")
            print(f"  reference {refname:7s} {NAME[c]:5s}: " + " | ".join(cells))
    print()
    print("the uniform evaluation: the 0.3 m range on every channel whose label is undetermined and whose 0.3 m range the")
    print("record excises; tau_level and tau_phase on the polarisation that sets A, whether the limit binds, and the bar")
    print("(dB over tolerance, least policy) before and after, with the bar at the least trim probe and the amended verdict")
    for r in range_rows:
        if r["channel"] in UNDETERMINED:
            c = next(x for x in class_rows if x["channel"] == r["channel"] and x["range"] == r["range"])
            print(f"  ch{r['channel']} 0.3 m pol{c['pol']}: level {c['tau_level_s']:>6s} s ({c['level_status']}), phase {c['tau_phase_s'] or 'n/a':>6s} s"
                  f" ({c['phase_status']}), least class gamma {min(float(g.split(':')[1]) for g in c['gamma_by_lag'].split()):+.2f};"
                  f" binds {r['phase_binds']}; bar {r['bar_record_db']} -> {r['bar_amended_db']} dB (least probe {r['bar_amended_least_probe_db']}) -> {r['verdict_amended']}")
    ev = [r for r in range_rows if (r["channel"], r["range"]) in EXCISED_RANGES]
    assert len(ev) == len(EXCISED_RANGES)
    bound = [(r["channel"], r["range"]) for r in range_rows if r["phase_binds"] == "yes"]
    print()
    print(f"evaluated on every range the record excises: {len(ev)} ranges on {len({r['channel'] for r in ev})} channels"
          f" ({len([r for r in ev if r['channel'] in EXCISED])} on the six excised channels, {len([r for r in ev if r['channel'] in UNDETERMINED])} 0.3 m ranges on undetermined channels)")
    print("the phase limit binds on:", ", ".join(f"channel {c} {g}" for c, g in bound) if bound else "none")
    print("applied on the exclusion side to:", ", ".join(f"channel {r['channel']} {r['range']}" for r in range_rows if r["applied"] == "yes") or "none")
    print("excised ranges the limit would bring inside the allowance:",
          ", ".join(f"channel {r['channel']} {r['range']} ({r['bar_record_db']} -> {r['bar_amended_db']} dB, {r['verdict_amended']})"
                    for r in ev if r["verdict_amended"] != "excise") or "none")

    if A18JSON is not None:
        # amendment 18 books channel 15 on Stokes I in the BAO band; the phase limit replaces each class's tau with
        # min(tau_level, tau_phase), and tau_phase is read on the lag classes, the shortest of which is LAG_CLASSES[0]
        r15 = A18JSON["results"]["15"]; summ = A18JSON["summary"]["15"][0]
        print()
        print(f"amendment 18: channel 15 is {summ}d; per BAO range, the tau, its status and the bar on the amendment 18 ruling:")
        for rng in ("bao_short", "bao_long"):
            p = r15[rng]; f = lambda x, fmt: "n/a" if x is None else format(x, fmt)
            print(f"  {rng:9s} {p['verdict'][0]:15s} tau {f(p['tau'], '.1f')} s ({p['tstat']}), least probe {f(p['tau_least'], '.1f')} s,"
                  f" G {f(p['G_bar'], '.1f')}, bar {f(p['bar'], '+.2f')} dB")
        L = r15["bao_long"]
        floor_lag = float(LAG_CLASSES[0])
        binds = min(L["tau"], L["tau_least"]) > floor_lag
        print(f"  the deciding range is the long one, read at tau {L['tau']:.1f} s with least probe {L['tau_least']:.1f} s; tau_phase cannot be"
              f" shorter than the shortest lag class, {floor_lag:.0f} s, so min(tau_level, tau_phase) {'can' if binds else 'cannot'} lower its G:"
              f" the phase limit {'may bind' if binds else 'does not bind'} on channel 15's amendment 18 booking, whose bar stays {L['bar']:+.1f} dB")
        print("  the short range is at the control floor under amendment 18, so the limit is not applied there (it is applied only to a range that excises)")
    return 0
