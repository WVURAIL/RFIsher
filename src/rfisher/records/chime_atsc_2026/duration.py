"""Two readings of the amendment 18 ruling that change no disposition (r2 of the release).

1. keep_gap_a18.csv: how far each floor channel's detection gate sits above the stated keep rule (item 5: no credits,
   lambda_none, the BAO-band G at the cap, R <= 1). A residual at the gate would read gate x G_cap / lambda_none; the
   capture floor would have to fall by that power ratio for the gate itself to pass. R goes as A^2 (item 1), so the
   amplitude sensitivity needed is half the dB, written as 10 log10 of the amplitude ratio (the convention of the booked
   units, where R was A); amplitude_factor is the ratio itself, the square root of the power ratio.
2. duration_a18.csv: every bar repriced at 2 and 3 on-sky years (T* stays 1 on-sky year) with the residual averaging
   down like noise, so A and G are fixed and only the tolerance moves: bar(t) = bar(1) + 10 log10(e(1) / e(t)), e the
   binding bin-filled deployed tolerance min_b lambda_b / f_b of item 4. lambda(t) is the survey-duration compute run's
   (output/survey-duration-2026-09-24/compute/ruling_factors.csv, dA_bao); the crossing time of any exclusion lost by
   3 on-sky years is found on the same banks with the same gate (compute_duration.py: cell, chan_eff), whose values at
   1, 2 and 3 years are checked equal to the compute run's first.

r3 (DECISIONS.md item 15): on a no-filter ruling (a18.json with world "none") the duration reading is redone in the
no-filter world and written to duration_nofilter.csv in place of duration_a18.csv:
3. duration_nofilter.csv: every bar at 1, 2, 3, 5, 8 and 10 on-sky years, the residual averaging down like noise (A and G
   fixed, T* one on-sky year), so bar(t) = bar(1) + 10 log10(e(1) / e(t)), e the binding bin-filled no-filter tolerance
   min_b lambda_b / f_b (item 4's fill, both dilations, every overlapping bin). The one-year bar is the ruling's, on the
   qualified exact-time reference; there is no qualified reference at other durations, so e(t) / e(1) is read on the
   no-filter bias bank (RFIsher data/fisher_bank_chime2022_pres_dense.npz) without the stability gate, as the
   survey-duration check reads lambda_none(t) (compute_duration.py, dK_a, gated=False), and each duration says whether the
   gate would accept every cell the channel reads (gate_<t>yr; at one year the bar is on the qualified reference). The
   bank values at the six durations are checked equal to the compute run's (bin_sigma_lambda.csv). Each excision's
   least bar over 1 to 10 on-sky years on a 0.01-year grid is also given,
   so an excision lost between the tabulated durations cannot be missed. The keep side moves with the channel's
   lambda_none(t) (no fill, compute run dK_a).
The keep gap (1) does not depend on the world: the keep side already reads lambda_none and no credits.

r5 (amendment 19, item 34): with --ch24 CH24.json and channel 24 excised on its own 2020 in-band measurement, channel 24's BAO
ranges enter the duration reading on that measurement's bars (A and G fixed, only the tolerance moves, as for every other
channel; there are no trim probes, so the probe reading is the bar). Without it the output is revision 4's byte for byte.

The release's ``sensitivity_a18.py``, with its logic unchanged: the banks are the packaged response banks and the
stability gate's values the science register's, through the forecast adapter in place of the scripts the release read.
usage: rfisher records duration <a18.json> <out dir> --duration-reference DIR [--ch24 CH24.json]
"""
import csv, math, os

import numpy as np

from rfisher.records.chime_atsc_2026 import capture_units as U
from rfisher.records.chime_atsc_2026._files import load_json, read_rows


def main(argv=None):
    import sys
    argv = ["duration"] + list(sys.argv[1:] if argv is None else argv)
    A18, OUT = argv[1], argv[2]
    C24 = load_json(argv[argv.index("--ch24") + 1]) if "--ch24" in argv else None
    if "--duration-reference" not in argv: raise SystemExit("duration: --duration-reference DIR (the survey-duration compute run) is required")
    if C24 is not None and not (C24.get("basis") == "measured2020" and C24["disposition"] == "excise"): C24 = None
    DUR = argv[argv.index("--duration-reference") + 1]   # the survey-duration compute run, whose values the banks are checked against
    d = load_json(A18); res = d["results"]; lam_none = d["lam_none"]; lam_dep = d["lam_dep"]
    def db(x): return 10 * math.log10(x) if (x is not None and math.isfinite(x) and x > 0) else math.nan
    def over(b): return 10 ** (b / 10) > U.ALLOW_R                    # item 7, the code's test
    log = []

    # ---------------------------------------------------------------- 1. keep gap of the floor channels
    BAO = ("bao_short", "bao_long")
    floor_ch = sorted(int(c) for c, per in res.items() if c != "37" and all(per[r]["verdict"][0] == "at floor" for r in BAO))
    rows = []
    for ch in floor_ch:
        per = res[str(ch)]; gcap = U.gain_bao(U.CAP, ch); ln = lam_none[str(ch)]; o = dict(channel=ch, G_cap=f"{gcap:.6g}", lambda_none=f"{ln:.6g}")
        worst = -math.inf
        for rng in BAO:
            pols = per[rng]["pols"]
            g = {p: q["floor_level"] * gcap / ln for p, q in pols.items() if q.get("floor_level") is not None}
            assert not any(q["measured"] for q in pols.values())
            best = min(g, key=g.get); ka = g.get("keep_all", math.nan)
            o[f"{rng}_gate_keep_all_db"] = f"{db(ka):.2f}"; o[f"{rng}_gate_least_db"] = f"{db(g[best]):.2f}"; o[f"{rng}_least_policy"] = ";".join(q for q in g if abs(db(g[q]) - db(g[best])) < 1e-9)   # the gate is often the same on every policy
            worst = max(worst, db(g[best]))
        # a keep needs both BAO ranges measured and passing (item 5, no at-floor range accepted): the gap is the larger range's
        # amplitude dB is 10 log10 of the amplitude ratio (the booked units' convention), half the power dB; the factor is the ratio itself
        o.update(keep_gap_power_db=f"{worst:.2f}", keep_gap_amplitude_db=f"{worst / 2:.2f}", amplitude_factor=f"{10 ** (worst / 20):.4g}",
                 deciding_range=max(BAO, key=lambda r: float(o[f"{r}_gate_least_db"])))
        rows.append(o)
    with open(os.path.join(OUT, "keep_gap_a18.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n"); w.writeheader(); w.writerows(rows)
    log.append("keep gap (power dB / amplitude dB, larger BAO range, least policy): " + ", ".join(f"{r['channel']} {r['keep_gap_power_db']} / {r['keep_gap_amplitude_db']}" for r in rows))

    # ---------------------------------------------------------------- 3. r3: the duration sensitivity in the no-filter world
    def nofilter_duration():
        YN = (1.0, 2.0, 3.0, 5.0, 8.0, 10.0)
        os.environ.setdefault("OMP_NUM_THREADS", "1")
        from rfisher import policy
        from rfisher.forecast.radiofisher_bao import filter_scenarios
        from rfisher.forecast.radiofisher_bao import response as bt   # the response-bank library (scripts/bias_tolerance.py when r5.2 was built)
        from rfisher.forecast.radiofisher_bao.bank.experiments import OVERVIEW_ONSKY_YEAR_HOURS as HPY
        FRAC = float(policy.value("science.response_stability.time_fraction"))
        LIMIT = float(policy.value("science.response_stability.maximum_tolerance_ratio"))
        WORLDS = tuple((s.name, s.bank, s.kfg_fac, s.suppression_key) for s in filter_scenarios.SCENARIOS)
        f_, k_ = next((f, k) for w, f, k, _ in WORLDS if w == "none")
        bank = bt.load_response_bank(bt.packaged_response_banks() / f_, build_command="see scripts/three_worlds.py", expected_kfg_fac=k_, expected_epsilon_fg=0.0)
        names = list(bank.paramnames); ZS = np.asarray(bank.zs); assert np.allclose(ZS, U.ZS)
        cache = {}
        def cell(ib, y, p):
            if (ib, y, p) not in cache:
                t = y * HPY; dth, sig = bt.bias_per_unit_residual(bank.F(ib, t), names); drift, nsign = bt.response_stability(bank, ib, t, names, p, frac=FRAC)
                cache[(ib, y, p)] = (float(sig[p] / abs(dth[p])), bool(drift <= LIMIT and nsign == 1))
            return cache[(ib, y, p)]
        # the bank reproduces the compute run at the six durations, value and gate
        ref = {(int(r["bin"]), r["param"], float(r["years"])): r for r in read_rows(os.path.join(DUR, "bin_sigma_lambda.csv")) if r["world"] == "none"}
        nchk = 0
        for (ib, p, y), r in ref.items():
            if y in YN and ib in {b for ch in range(14, 37) for b in U.bin_overlaps(ch)}:
                lam, acc = cell(ib, y, p); assert repr(lam) == r["lam_raw"] and acc == (r["accepted"] == "True"), (ib, p, y); nchk += 1
        def eff(ch, y):
            """min_b lambda_b / f_b over the channel's bins (both dilations), and whether the gate accepts every one of those cells."""
            v, acc = [], True
            for b, (o, w_) in U.bin_overlaps(ch).items():
                c2 = [cell(b, y, p) for p in ("aperp", "apar")]; v.append(min(x[0] for x in c2) / (o / w_)); acc &= all(x[1] for x in c2)
            return min(v), acc
        def chan_lam(ch, y):   # the channel's lambda_none(t): min over bins and both dilations, no fill (the keep side)
            return min(cell(b, y, p)[0] for b in U.bin_overlaps(ch) for p in ("aperp", "apar"))
        cl = {int(r["channel"]): r for r in read_rows(os.path.join(DUR, "channel_lambda.csv")) if r["world"] == "none"}
        assert all(repr(chan_lam(ch, y)) == cl[ch][f"lamraw_{y:g}yr"] for ch in cl for y in YN)
        out = []; soft = []
        items = sorted(res.items(), key=lambda x: int(x[0]))
        if C24 is not None:   # r5: channel 24's BAO ranges on its own 2020 in-band measurement (no trim probes)
            assert C24["world"] == "none" and C24["ground"] == "off"
            items = [(c, (dict((rng, dict(verdict=[o["verdict"]], bar=o["bar_db"], probe_bar=0.0, R1=o["R1"])) for rng, o in C24["reading"]["ranges"].items()) if c == "24" else per)) for c, per in items]
        for c, per in items:
            ch = int(c)
            if ch == 37 or (ch == 24 and C24 is None): continue
            e1 = eff(ch, 1.0)[0]
            for rng in BAO:
                p = per[rng]; v = p["verdict"][0]
                if v not in ("excise", "marginal", "policy at floor"): continue
                bar, prb, R1 = p["bar"], p["bar"] + p["probe_bar"], p["R1"]
                o = dict(channel=ch, range=rng, verdict_1yr=v, bar_1yr_db=f"{bar:.4f}", probe_1yr_db=f"{prb:.4f}")
                for y in YN:
                    e, acc = eff(ch, y); dA = db(e1 / e)
                    st = "blocked (item 6)" if v == "policy at floor" else ("excise" if (over(bar + dA) and over(prb + dA)) else "marginal")
                    R1t = R1 * 10 ** (dA / 10) if R1 is not None else math.nan
                    if not math.isfinite(R1t) or v == "policy at floor": th = ""
                    elif R1t > U.ALLOW_R: th = "excised at any tau"
                    else:
                        t = U.invert_gain(U.ALLOW_R / R1t, lambda x: U.gain_bao(x, ch)); th = f"tau > {t:.4g} s" if t is not None else "not excisable at any tau"
                    o.update({f"dA_{y:g}yr_db": f"{dA:+.4f}", f"bar_{y:g}yr_db": f"{bar + dA:.4f}", f"probe_{y:g}yr_db": f"{prb + dA:.4f}", f"state_{y:g}yr": st,
                              f"gate_{y:g}yr": "qualified reference" if y == 1.0 else ("accepted" if acc else "refused"), f"threshold_{y:g}yr": th})
                if v == "excise":   # the least bar over 1 to 10 on-sky years on a 0.01-year grid
                    grid = [float(x) for x in np.round(np.arange(1.0, 10.001, 0.01), 2)]
                    dmin, ymin = min((db(e1 / eff(ch, y)[0]), y) for y in grid)
                    lost_at = next((y for y in grid if not (over(bar + db(e1 / eff(ch, y)[0])) and over(prb + db(e1 / eff(ch, y)[0])))), None)
                    o.update(least_bar_1to10yr_db=f"{bar + dmin:.4f}", least_bar_at_yr=f"{ymin:g}", lost_between_1_and_10yr=("no" if lost_at is None else f"yes, at {lost_at:g} on-sky years"))
                    soft.append((ch, rng, bar, [(y, float(o[f"dA_{y:g}yr_db"]), o[f"gate_{y:g}yr"]) for y in YN[1:]], dmin, ymin, lost_at))
                out.append(o)
        chan = []
        for ch in sorted({o["channel"] for o in out}):
            rr = [o for o in out if o["channel"] == ch]
            chan.append(dict(channel=ch, range="channel", verdict_1yr=(C24["disposition"] if (ch == 24 and C24 is not None) else d["summary"][str(ch)][0]),
                             **{f"state_{y:g}yr": ("excise" if any(o[f"state_{y:g}yr"] == "excise" for o in rr) else "undetermined") for y in YN}))
        fields = list(out[0]) + [k for k in ("least_bar_1to10yr_db", "least_bar_at_yr", "lost_between_1_and_10yr") if k not in out[0]]
        with open(os.path.join(OUT, "duration_nofilter.csv"), "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n", restval=""); w.writeheader(); w.writerows(out); w.writerows(chan)
        log.append(f"no-filter duration: the bank reproduces the compute run's lambda and gate on {nchk} cells (six durations) and every channel's lambda_none(t)")
        for y in YN: log.append(f"excised at {y:g} on-sky year{'s' if y != 1 else ''}: {[c['channel'] for c in chan if c[f'state_{y:g}yr'] == 'excise']}")
        log.append("no range becomes an excision: " + str(not [o for o in out if o["verdict_1yr"] != "excise" and "excise" in [o[f"state_{y:g}yr"] for y in YN]]))
        for ch, rng, bar, dd, dmin, ymin, lost_at in soft:
            s_ = [f"{y:g} yr {x:+.2f}{'' if g == 'accepted' else '*'}" for y, x, g in dd]
            log.append(f"{ch} {rng}: bar {bar:+.2f} dB at 1 on-sky year; change {', '.join(s_)} dB; least {bar + dmin:+.2f} dB at {ymin:g} on-sky years"
                       f" ({ymin / 0.152:.0f} calendar years at the 2019 duty 0.152); " + ("never lost from 1 to 10 on-sky years" if lost_at is None else f"lost at {lost_at:g} on-sky years"))
        log.append("(* the bank's stability gate refuses a cell the channel reads at that duration; no qualified reference exists away from one on-sky year)")
        least = {y: min(db(q["R_keep_stated"]) + db(chan_lam(int(c), 1.0) / chan_lam(int(c), y))
                        for c, per in res.items() if c != "37" for r in per.values() for q in r["pols"].values() if q.get("R_keep_stated") is not None)
                 for y in YN}
        log.append("least stated keep reading, dB over R = 1: " + ", ".join(f"{y:g} yr {v:+.1f}" for y, v in least.items()) + " (no keep)")

    if d.get("world", "200ns") == "none":
        nofilter_duration()
        with open(os.path.join(OUT, "sensitivity_a18.log"), "w") as fh: fh.write("\n".join(log) + "\n")
        print("\n".join(log)); return 0

    # ---------------------------------------------------------------- 2. duration sensitivity (the 200 ns world, revision 2)
    YEARS = (2.0, 3.0)
    fac = {(int(r["channel"]), float(r["years"])): r for r in read_rows(os.path.join(DUR, "ruling_factors.csv"))}
    out = []; lost = []
    for c, per in sorted(res.items(), key=lambda x: int(x[0])):
        ch = int(c)
        if ch in (24, 37): continue
        for rng in BAO:
            p = per[rng]; v = p["verdict"][0]
            if v not in ("excise", "marginal", "policy at floor"): continue
            bar, prb = p["bar"], p["bar"] + p["probe_bar"]
            o = dict(channel=ch, range=rng, verdict_1yr=v, bar_1yr_db=f"{bar:.4f}", probe_1yr_db=f"{prb:.4f}")
            for y in YEARS:
                dA = float(fac[(ch, y)]["dA_bao"])
                if v == "policy at floor": st = "blocked (item 6)"
                elif not math.isfinite(dA): st = "unpriced (200 ns lambda refused at t)"
                else: st = "excise" if (over(bar + dA) and over(prb + dA)) else "marginal"
                o.update({f"dA_{y:g}yr_db": f"{dA:+.4f}", f"bar_{y:g}yr_db": f"{bar + dA:.4f}", f"probe_{y:g}yr_db": f"{prb + dA:.4f}", f"state_{y:g}yr": st})
                if v == "excise" and st != "excise" and (ch, rng) not in lost: lost.append((ch, rng))
            R1 = p["R1"]                           # the threshold at t: R(G = 1) scales as the bar does
            for y in (1.0,) + YEARS:
                dA = 0.0 if y == 1.0 else float(fac[(ch, y)]["dA_bao"]); R1t = R1 * 10 ** (dA / 10) if R1 is not None else math.nan
                if not math.isfinite(R1t) or v == "policy at floor": th = ""
                elif R1t > U.ALLOW_R: th = "excised at any tau"
                else:
                    t = U.invert_gain(U.ALLOW_R / R1t, lambda x: U.gain_bao(x, ch)); th = f"tau > {t:.4g} s" if t is not None else "not excisable at any tau"
                o[f"threshold_{y:g}yr"] = th
            out.append(o)
    # channel dispositions at t: excised when either BAO range excises (the summary rule); nothing becomes a keep (below)
    chan = []
    for ch in sorted({o["channel"] for o in out}):
        rr = [o for o in out if o["channel"] == ch]
        chan.append(dict(channel=ch, range="channel", verdict_1yr=d["summary"][str(ch)][0],
                         **{f"state_{y:g}yr": ("excise" if any(o[f"state_{y:g}yr"] == "excise" for o in rr) else "undetermined") for y in YEARS}))
    fields = list(out[0])
    with open(os.path.join(OUT, "duration_a18.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n", restval=""); w.writeheader(); w.writerows(out); w.writerows(chan)
    exc1 = [c["channel"] for c in chan if c["verdict_1yr"] == "excise"]
    log.append(f"excised at 1 on-sky year: {exc1}; at 2: {[c['channel'] for c in chan if c['state_2yr'] == 'excise']}; at 3: {[c['channel'] for c in chan if c['state_3yr'] == 'excise']}")
    log.append("no range becomes an excision: " + str(not [o for o in out if o["verdict_1yr"] != "excise" and "excise" in (o["state_2yr"], o["state_3yr"])]))
    # the keep side at t: the least stated keep reading moves with lambda_none(t) (compute run dK_a)
    least = {y: min(db(q["R_keep_stated"]) + (float(fac[(int(c), y)]["dK_a"]) if y != 1.0 else 0.0)
                    for c, per in res.items() if c != "37" for r in per.values() for q in r["pols"].values() if q.get("R_keep_stated") is not None)
             for y in (1.0,) + YEARS}
    log.append("least stated keep reading, dB over R = 1: " + ", ".join(f"{y:g} yr {v:+.1f}" for y, v in least.items()) + " (no keep)")

    # crossing time of each exclusion lost by 3 on-sky years, on the banks (compute_duration.py cell and chan_eff, gate honoured)
    if lost:
        os.environ.setdefault("OMP_NUM_THREADS", "1")
        from rfisher import policy
        from rfisher.forecast.radiofisher_bao import filter_scenarios
        from rfisher.forecast.radiofisher_bao import response as bt   # the response-bank library (scripts/bias_tolerance.py when r5.2 was built)
        from rfisher.forecast.radiofisher_bao.bank.experiments import OVERVIEW_ONSKY_YEAR_HOURS as HPY
        FRAC = float(policy.value("science.response_stability.time_fraction"))
        LIMIT = float(policy.value("science.response_stability.maximum_tolerance_ratio"))
        WORLDS = tuple((s.name, s.bank, s.kfg_fac, s.suppression_key) for s in filter_scenarios.SCENARIOS)
        f_, k_ = next((f, k) for w, f, k, _ in WORLDS if w == "deployed")
        bank = bt.load_response_bank(bt.packaged_response_banks() / f_, build_command="see scripts/three_worlds.py", expected_kfg_fac=k_, expected_epsilon_fg=0.0)
        ZS = np.asarray(bank.zs); names = list(bank.paramnames)
        def lam_cell(ib, y, p):
            t = y * HPY; dth, sig = bt.bias_per_unit_residual(bank.F(ib, t), names); drift, nsign = bt.response_stability(bank, ib, t, names, p, frac=FRAC)
            return float(sig[p] / abs(dth[p])) if (drift <= LIMIT and nsign == 1) else math.nan
        def overlaps(ch):
            lo, hi = 470.0 + 6.0 * (ch - 14), 476.0 + 6.0 * (ch - 14); o = {}
            for b in range(len(ZS) - 1):
                f_lo, f_hi = 1420.405751 / (1 + ZS[b + 1]), 1420.405751 / (1 + ZS[b]); ov = min(hi, f_hi) - max(lo, f_lo)
                if ov > 1e-9: o[b] = ov / (f_hi - f_lo)
            return o
        def eff(ch, y):
            v = [(lambda l: min(l) if all(math.isfinite(x) and x > 0 for x in l) else math.nan)([lam_cell(b, y, p) for p in ("aperp", "apar")]) / f for b, f in overlaps(ch).items()]
            return min(v) if all(math.isfinite(x) for x in v) else math.nan
        for ch, rng in lost:
            p = res[str(ch)][rng]; bar, prb = p["bar"], p["bar"] + p["probe_bar"]; e1 = eff(ch, 1.0)
            chk = [repr(db(e1 / eff(ch, y))) == repr(float(fac[(ch, y)]["dA_bao"])) or abs(db(e1 / eff(ch, y)) - float(fac[(ch, y)]["dA_bao"])) < 1e-12 for y in YEARS]
            assert all(chk), (ch, chk)
            holds = lambda y: (lambda e: math.isfinite(e) and over(bar + db(e1 / e)) and over(prb + db(e1 / e)))(eff(ch, y))
            grid = np.round(np.arange(1.0, 3.001, 0.01), 2); y1 = next(float(y) for y in grid if not holds(float(y))); lo, hi = y1 - 0.01, y1
            for _ in range(12):
                mid = 0.5 * (lo + hi)
                if holds(mid): lo = mid
                else: hi = mid
            e = eff(ch, hi)
            log.append(f"{ch} {rng}: bar {bar:.4f} dB at 1 on-sky year (probe {prb:.4f}); the excision holds to {lo:.3f} on-sky years and is lost at"
                       f" {hi:.3f} ({hi / 0.152:.1f} calendar years at the 2019 duty 0.152), bar there {bar + db(e1 / e):.4f} dB against the"
                       f" {db(U.ALLOW_R):.4f} dB allowance; banks reproduce the compute run's dA at 2 and 3 years")
    with open(os.path.join(OUT, "sensitivity_a18.log"), "w") as fh: fh.write("\n".join(log) + "\n")
    print("\n".join(log))
    return 0
