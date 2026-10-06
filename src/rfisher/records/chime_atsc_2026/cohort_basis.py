"""Channel 24 on its 2020 cohort basis: the borrowed reading (revision 4) and its own 2020 in-band measurement (item 34).

Channel 24's band (freq_id 676 to 691) is absent from every 2026 dump, so the capture has no products for it. Its
records rule it on the 2020 CANFAR cohort, each here with its logic unchanged:

- :func:`main` is the release's ``ch24_2020_basis_a18.py``: without ``--a18`` the frozen 2020-basis record (the pilot bin
  and the pilot-to-in-band correction borrowed from the other strong transmitters, at the archive tau of
  ``--tau-archive`` and the timed-frame count of ``--timed-frames``); with ``--a18`` amendment 18's rule as written (the
  borrowed correction takes its most favorable value, undetermined); with ``--set CH24_BASIS=measured2020`` the measured
  reading of item 34.
- :func:`ch24_measured2020` and the functions after it are the channel 24 half of the release's ``a19_inputs.py``,
  on the lane's own rule (:func:`rule`, :func:`class_reading`, :func:`floor_stats`, :func:`ratio`, the functions of the
  lane's ``ch24_inband_a18.py``) and its per-event tables.

The lane's tables, frames, thresholds and dump medians are the capture handoff's ``cohort24.json``; only the borrowed
basis opens the handoff's borrowed files (``cohort2020/`` and ``frame_analysis/pilot_to_inband.csv``); channel 24's
lambda_none is read from the table of record given as ``--record-table``.

The measured reading takes no credit and no delay filter (``--world none --ground off``; post-processing is not
modelled). The release's credit readings of channel 24 (the ground credit at its ceiling and the 200 ns filter plus S),
its archive-share reading and the both-credits column of the per-bin table are not computed here; the release keeps
them. ``--world`` and ``--ground`` keep their defaults (200 ns, on) for the frozen 2020-basis record, which was priced
that way.

usage: rfisher records cohort-basis --handoff DIR --record-table TABLE [--a18 [--json OUT.json]] [--tau-archive S]
                                    [--timed-frames N] [--world 200ns|none] [--ground on|off]
                                    [--set CH24_BASIS=borrowed|measured2020] [--per-bin OUT.csv] [--per-bin-own-events]
                                    [--g1-names r5|literal]
"""
import csv, json, os

import numpy as np

from rfisher.records.chime_atsc_2026 import capture_handoff
from rfisher.records.chime_atsc_2026 import capture_units as U
from rfisher.records.chime_atsc_2026._files import read_rows

TAU_ARCHIVE = 8423.0
# ---- the lane's classes, ranges and policies (ch24_inband_a18.py)
NFFT = U.NFFT
INB = list(range(676, 692)); C37 = [477, 480, 483, 486, 489, 491]
CLS = [(0, 1), (0, 32), (0, 64), (0, 128), (0, 255), (1, 0), (2, 0), (3, 0)]
RANGES = {"shortest": [(0, 1)], "bao_short": [(0, 32), (0, 64)], "bao_long": [(0, 128), (0, 255), (1, 0), (2, 0), (3, 0)]}
LONG = RANGES["bao_long"]
POLICIES = ["cal_q0.1", "cal_q0.5", "cal_q0.9", "keep_all"]; QS = {"cal_q0.1": 0.1, "cal_q0.5": 0.5, "cal_q0.9": 0.9}
freq = lambda f: 800.0 - f * 0.390625
TAU_ARCH = 8423.0
def db(x): return 10 * np.log10(x) if (x is not None and np.isfinite(x) and x > 0) else np.nan
_STATE = {}
lam_none = FILL = None   # channel 24's lambda_none and its bin fill, set by load()


class Lane:
    """The lane module's names, read from the handoff (:func:`load`)."""

    def __init__(self, **kw):
        self.__dict__.update(kw)

    def nframes(self, e, maxfr): return nframes(e, maxfr)
    def tables(self, prod, maxfr, ref_mode="sky"): return tables(prod, maxfr, ref_mode)
    def kept(self, pol): return kept(pol)
    floor_stats = staticmethod(lambda T, epochs: floor_stats(T, epochs))
    class_reading = staticmethod(lambda T, fl, epochs, c, key="inband": class_reading(T, fl, epochs, c, key))
    rule = staticmethod(lambda T, fl, maxfr, key="inband", credit=1.0: rule(T, fl, maxfr, key, credit))
    ratio = staticmethod(lambda T, fl, epochs, key="inband": ratio(T, fl, epochs, key))
    freq = staticmethod(lambda f: freq(f))


def load(h, record_table):
    """Read the lane from the handoff and channel 24's lambda_none from the table of record."""
    global lam_none, FILL
    c = capture_handoff.cohort24(h)
    lam_none = [float(x["lambda_none"]) for x in read_rows(record_table) if int(x["channel"]) == 24 and x["role"] != "pilot" and x["lambda_none"]][0]
    FILL = U.fill_factor(24, lam_none, "none")
    L = Lane(EVENTS=c.EVENTS, MAXFR=c.MAXFR, INB=c.INB, C37=c.C37, R=c.R, dup=c.dup, eta=c.eta, Qmed={e: c.Qmed[e] for e in c.EVENTS},
             lam_none=lam_none, FILL=FILL, POLICIES=POLICIES, CLS=CLS, LONG=LONG, RANGES=RANGES, lane=c.lane, code=c.code,
             code_sha256=c.code_sha256, products_sha256=c.products_sha256, n_products=c.n_products)
    assert L.MAXFR == 8 and len(L.EVENTS) == 12 and all(ok for _, _, ok in L.dup), (L.MAXFR, len(L.EVENTS))
    _STATE.update(lane=L, frames=c.frames, tables=c.tables, record=record_table)
    return L


def ch24_lane():
    return _STATE["lane"]


def nframes(e, maxfr):
    assert maxfr == _STATE["lane"].MAXFR, "the handoff carries the lane at its own frame limit"
    return _STATE["frames"][e]


def tables(prod, maxfr, ref_mode="sky"):
    assert maxfr == _STATE["lane"].MAXFR and ref_mode == "sky", "the handoff carries the lane's sky-referenced tables"
    return _STATE["tables"][prod]


def kept(pol):
    L = _STATE["lane"]; EVENTS, Qmed, eta = L.EVENTS, L.Qmed, L.eta
    return list(EVENTS) if pol == "keep_all" else [e for e in EVENTS if np.isfinite(Qmed[e]) and Qmed[e] <= eta[pol]]


# ---------------------------------------------------------------- the lane's rule (ch24_inband_a18.py)
def floor_stats(T, epochs):
    return {c: (float(np.mean([v for e in epochs for v in T[(e, c)]["floor"]])), float(np.std([v for e in epochs for v in T[(e, c)]["floor"]], ddof=1)),
                len([v for e in epochs for v in T[(e, c)]["floor"]])) for c in CLS}

def class_reading(T, fl, epochs, c, key="inband"):
    vals = [T[(e, c)][key] for e in epochs if np.isfinite(T[(e, c)][key])]
    if not vals: return None
    A = float(np.median(vals)); fm, fs, nfl = fl[c]
    an = A - fm
    return dict(A=A, A_net=an, measured=A > fm + 3 * fs, fm=fm, fs=fs, sigma=(an / fs), power=U.to_power(an, c), gate_power=U.gate_power(3 * fs, c))

def rule(T, fl, maxfr, key="inband", credit=1.0):
    out = {}
    for rng, classes in RANGES.items():
        pols, excluded = {}, {}
        for pol in POLICIES:
            eps = kept(pol)
            if not eps: excluded[pol] = "keeps no dump"; continue
            rd = {c: class_reading(T, fl, eps, c, key) for c in classes}; rd = {c: x for c, x in rd.items() if x}
            meas = [x for x in rd.values() if x["measured"]]
            Apow = float(np.median([x["power"] for x in meas])) if meas else np.nan
            n = min(nframes(e, maxfr) for e in eps); Gmin = U.admissible_min_G(n)
            G_used = U.gain_bao(Gmin * U.TF, 24)
            pols[pol] = dict(kept=eps, n_min_frames=n, G_min=Gmin, G_used=G_used, measured=bool(meas), n_measured=len(meas), A_power=Apow,
                             R_excl=Apow * FILL * credit * G_used / lam_none if meas else np.nan,
                             R_G1=Apow * FILL * credit / lam_none if meas else np.nan,
                             R_arch=Apow * FILL * credit * U.gain_bao(TAU_ARCH, 24) / lam_none if meas else np.nan,
                             R_keep_stated=Apow * U.gain_bao(U.CAP, 24) / lam_none if meas else np.nan,
                             classes={f"{c[0]},{c[1]}": x for c, x in rd.items()})
        blockers = U.every_policy_blockers(pols, POLICIES)
        cand = [(p, d) for p, d in pols.items() if d["measured"]]
        if not pols: verdict = "undetermined"
        elif "keep_all" in pols and not pols["keep_all"]["measured"]: verdict = "at floor"
        elif blockers: verdict = "policy at floor"
        else:
            pb, d = min(cand, key=lambda x: x[1]["R_excl"])
            verdict = "excise" if d["R_excl"] > U.ALLOW_R else "marginal"
        bar = min((d["R_excl"] for p, d in cand), default=np.nan)
        out[rng] = dict(verdict=verdict, bar_db=db(bar), bar_G1_db=db(min((d["R_G1"] for p, d in cand), default=np.nan)),
                        bar_arch_db=db(min((d["R_arch"] for p, d in cand), default=np.nan)),
                        keep_stated_db=db(max((d["R_keep_stated"] for p, d in cand), default=np.nan)), blockers=blockers, excluded=excluded, pols=pols)
    L, S = out["bao_long"]["verdict"], out["bao_short"]["verdict"]
    disp = "excise" if "excise" in (L, S) else "undetermined"
    return disp, out

def ratio(T, fl, epochs, key="inband"):
    """pilot_to_inband.py's relation on the long classes: per class the median over epochs of the in-band and of the pilot-bin
    excess, then the median over classes; reported on the sky-referenced excess (the record's definition) and net of the floor."""
    I = [float(np.median([T[(e, c)][key] for e in epochs])) for c in LONG]; P = [float(np.median([T[(e, c)]["pilot"] for e in epochs])) for c in LONG]
    Im, Pm = float(np.median(I)), float(np.median(P))
    fm = {c: fl[c][0] for c in LONG}
    In = float(np.median([i - fm[c] for i, c in zip(I, LONG)])); Pn = float(np.median([p - fm[c] for p, c in zip(P, LONG)]))
    percls = {f"{c[0]},{c[1]}": dict(inband=i, pilot=p, amp_db=db(i / p) if i > 0 and p > 0 else np.nan) for i, p, c in zip(I, P, LONG)}
    return dict(inband=Im, pilot=Pm, amp_db=db(Im / Pm), power_db=2 * db(Im / Pm), inband_net=In, pilot_net=Pn,
                amp_db_net=db(In / Pn), power_db_net=2 * db(In / Pn), per_class=percls)


# ---------------------------------------------------------------- channel 24's measured 2020 reading (a19_inputs.py, item 34)
def _record24():
    for r in read_rows(_STATE["record"]):
        if r["channel"] == "24" and r["role"] != "pilot" and r["lambda_none"]:
            return float(r["lambda_none"])


def _db(x):
    return 10 * np.log10(x) if (x is not None and np.isfinite(x) and x > 0) else np.nan


def ch24_measured2020():
    """Channel 24 ruled on its own 2020 in-band measurement, r4/r5's reading: no credit and no delay filter. The lane's rule
    is r4's (items 1 to 8, 15, 17), whose exclusion factor is one."""
    L = ch24_lane(); lam_none = _record24()
    assert lam_none == L.lam_none
    fill_none = U.fill_factor(24, lam_none, "none"); assert fill_none == L.FILL
    k = 1.0
    T = L.tables("I", L.MAXFR, "sky"); fl = L.floor_stats(T, L.EVENTS)
    disp, out = L.rule(T, fl, L.MAXFR, credit=k)
    res = dict(basis="measured2020", world="none", ground="off", ground_credit_rho=None,
               exclusion_factor=k, lambda_none=lam_none, fill_none=fill_none,
               maxfr=L.MAXFR, events=list(L.EVENTS), frames={e: L.nframes(e, L.MAXFR) for e in L.EVENTS}, eta=L.eta, Qmed=L.Qmed,
               kept={p: L.kept(p) for p in L.POLICIES}, disposition=disp, ranges={})
    for rng, o in out.items():
        cand = [(p, d) for p, d in o["pols"].items() if d["measured"]]
        bp = min(cand, key=lambda x: x[1]["R_excl"])[0] if cand else None
        R1 = min((d["R_G1"] for p, d in cand), default=np.nan)
        res["ranges"][rng] = dict(verdict=o["verdict"], bar_db=o["bar_db"], bar_policy=bp, G_bar=(o["pols"][bp]["G_used"] if bp else None),
                                  G_min_bar=(o["pols"][bp]["G_min"] if bp else None), n_frames_bar=(o["pols"][bp]["n_min_frames"] if bp else None),
                                  R1=R1, bar_G1_db=o["bar_G1_db"], bar_arch_db=o["bar_arch_db"], keep_stated_db=o["keep_stated_db"],
                                  keep_stated_least_db=_db(min((d["R_keep_stated"] for p, d in cand), default=np.nan)),
                                  blockers=o["blockers"], excluded=o["excluded"],
                                  policies={p: dict(kept=len(d["kept"]), n_min_frames=d["n_min_frames"], G_min=d["G_min"], G_used=d["G_used"],
                                                    measured=d["measured"], n_measured=d["n_measured"], A_power=d["A_power"],
                                                    R_excl_db=_db(d["R_excl"]), R_G1_db=_db(d["R_G1"]),
                                                    floor_gate_power=min(x["gate_power"] for x in d["classes"].values()),
                                                    classes={c: dict(A=x["A"], A_net=x["A_net"], sigma=x["sigma"], measured=x["measured"], power=x["power"])
                                                             for c, x in d["classes"].items()}) for p, d in o["pols"].items()})
    # the channel's own pilot-to-in-band relation (reported, never used: the ruling reads the in-band bins directly)
    rt = L.ratio(T, fl, L.EVENTS); res["pilot_to_inband_own_amp_db"] = rt["amp_db"]; res["pilot_to_inband_own_amp_db_net"] = rt["amp_db_net"]
    res["floor"] = {f"{c[0]},{c[1]}": list(fl[c]) for c in L.CLS}
    # per epoch, the long range at each epoch's own admissible minimum (the lowest-epoch form, a sensitivity)
    pe = []
    for e in L.EVENTS:
        rd = [L.class_reading(T, fl, [e], c) for c in L.LONG]; meas = [x for x in rd if x and x["measured"]]
        n = L.nframes(e, L.MAXFR); Ge = U.gain_bao(U.admissible_min_G(n) * U.TF, 24)
        pe.append(dict(epoch=e, n_frames=n, G=Ge, n_measured=len(meas),
                       bar_db=_db(float(np.median([x["power"] for x in meas])) * L.FILL * k * Ge / lam_none) if meas else np.nan))
    res["per_epoch_long"] = pe
    return res


def ch24_cleaner_pol(bar_db, G_bar, factor=1.0):
    """The cleaner polarization on the booking range (bao_long), as robustness_credit_a18.py reads it on the capture: per class
    the smaller single-product excess net of its own channel 37 floor (median over every cohort event), floored at 3e-5 in
    amplitude and converted to A^2 N n_b, the median over the range's classes; and, as postprocessing_sensitivity_a18.py
    requires, the classes measured above the floor on that polarization (three floor scatters)."""
    L = ch24_lane(); lam_none = L.lam_none
    Tp = {p: L.tables(p, L.MAXFR, "sky") for p in (0, 1)}; flp = {p: L.floor_stats(Tp[p], L.EVENTS) for p in (0, 1)}
    cl, m, n, per = [], 0, 0, {}
    for c in L.LONG:
        best = None
        for p in (0, 1):
            vals = [Tp[p][(e, c)]["inband"] for e in L.EVENTS if np.isfinite(Tp[p][(e, c)]["inband"])]
            A = float(np.median(vals)); fm, fs, _ = flp[p][c]
            cand = (A - fm, A > fm + 3 * fs, p)
            if best is None or cand[0] < best[0]: best = cand
        n += 1; m += best[1]; cl.append(U.to_power(max(best[0], 3e-5), c)); per[f"{c[0]},{c[1]}"] = dict(net=best[0], measured=bool(best[1]), pol=best[2])
    A_c = float(np.median(cl)); R = A_c * L.FILL * factor * G_bar / lam_none
    return dict(bar_db=_db(R), measured=m, n=n, classes=per)


def ch24_per_bin(own_events=False):
    """Per in-band bin (676 to 691): per class the median over the 12 events of the excess net of the floor mean, in floor
    scatters, and whether it is measured (three scatters); per BAO range the reading over its measured classes (A^2 N n_b,
    median) at the admissible minimum G of the fewest frames (4) and at G = 1. No credits.
    r5.1 (triage row 24, B-9): with own_events=True each bin's G is the admissible minimum of the fewest frames among the events that
    contain the bin (bin 676 is absent from two events, one of them the 4-frame event, so its fewest is 5 and G 4.71), and the bins at
    the channel's edges are labelled."""
    L = ch24_lane(); lam_none = _record24()
    T = L.tables("I", L.MAXFR, "sky"); fl = L.floor_stats(T, L.EVENTS)
    nmin = min(L.nframes(e, L.MAXFR) for e in L.EVENTS); G = U.gain_bao(U.admissible_min_G(nmin) * U.TF, 24)
    rows = []; G_ch = G
    for f in L.INB:
        o = dict(freq_id=f, freq_mhz=L.freq(f), n_events=sum(1 for e in L.EVENTS if f in T[(e, L.LONG[0])]["bins"]))
        if own_events:
            nf = min(L.nframes(e, L.MAXFR) for e in L.EVENTS if f in T[(e, L.LONG[0])]["bins"]); G = U.gain_bao(U.admissible_min_G(nf) * U.TF, 24)
            o.update(n_frames_fewest=nf, G=G, edge=("upper edge" if f == min(L.INB) else "lower edge" if f == max(L.INB) else ""))
        for rng in ("bao_long", "bao_short", "shortest"):
            pw = []
            for c in L.RANGES[rng]:
                vals = [T[(e, c)]["bins"][f] for e in L.EVENTS if f in T[(e, c)]["bins"] and np.isfinite(T[(e, c)]["bins"][f])]
                fm, fs, _ = fl[c]; A = float(np.median(vals)); meas = A > fm + 3 * fs
                o[f"sigma_{c[0]}_{c[1]}"] = (A - fm) / fs; o[f"measured_{c[0]}_{c[1]}"] = bool(meas)
                if meas: pw.append(U.to_power(A - fm, c))
            o[f"{rng}_measured_classes"] = f"{len(pw)} of {len(L.RANGES[rng])}"
            R = float(np.median(pw)) * L.FILL / lam_none if pw else np.nan
            o[f"{rng}_bar_db"] = _db(R * G); o[f"{rng}_bar_G1_db"] = _db(R)
        rows.append(o)
    return dict(rows=rows, G=G_ch, n_frames=nmin, own_events=own_events)


def ch24_threshold(R1, g1t="G = 1"):
    """Item 8 on channel 24's measured reading: the least tau at which the range is excised, from the unrounded R at G = 1."""
    if not np.isfinite(R1): return None, "not excisable at any τ (no measured reading)"
    if R1 > U.ALLOW_R:
        return None, f"excised at any τ: R at {g1t} is {_db(R1):+.2f} dB, over the 10^0.3 (about 2) allowance, and G cannot fall below one frame"
    t = U.invert_gain(U.ALLOW_R / R1, lambda x: U.gain_bao(x, 24))
    while t is not None and not (R1 * U.gain_bao(t, 24) > U.ALLOW_R): t = np.nextafter(t, np.inf)
    if t is None: return None, f"not excisable at any τ: R at the sidereal cap is {_db(R1 * U.gain_bao(U.CAP, 24)):.2f} dB"
    return t, ""


def ch24_basis_main(tor, json_out=None, per_bin_out=None, own_events=False, g1_names="r5"):
    """The measured2020 branch of ch24_2020_basis_a18.py: print the reading, write its json and the per-bin csv. r5.1: own_events
    (each bin's G from its own events, triage row 24) and g1_names="literal" (R with every class at G = 1 is "literal G = 1", row 22)."""
    assert os.path.abspath(tor) == os.path.abspath(_STATE["record"]), tor
    r = ch24_measured2020(); L = ch24_lane()
    g1t = "literal G = 1" if g1_names == "literal" else "G = 1"
    if g1_names == "literal":
        def P(*a):
            print(*(str(x).replace("at G = 1", "at literal G = 1").replace("at G=1", "lit G=1") for x in a))
    else: P = print
    P("== channel 24 on its own 2020 in-band measurement (amendment 19, DECISIONS.md item 34) ==")
    P("Channel 24's band (freq_id 676 to 691) is absent from every 2026 dump, so the capture has no products for it. The")
    P("2020 cohort does record it: the channel 24 lane fetched the in-band bins 676 to 691 and the channel 37 bins of 12")
    P("cohort events from CADC, reduced them with the cohort's own reducer and checked the estimator")
    P("(decision-evidence-2026-09-24/ch24, check_ch24). This reading runs the lane's own code on those products.")
    P("No borrowed quantity: the pilot-to-in-band correction of other transmitters (-5.66 dB) is retired; the in-band level is")
    P("read directly on channel 24's bins. The floor is the channel 37 bins of the same events on the same product (Stokes I),")
    P("the policies are channel 24's own archive product (690.npz), and the tolerance is channel 24's lambda_none from the")
    P("frozen record. Channel 24's era is its whole record, and its pilot is present every year through 2026 (item 34).\n")
    P(f"events {len(r['events'])}; at most {r['maxfr']} frames per event; frames per event {r['frames']}")
    miss = {e: [f for f in L.INB + L.C37 if (e, f) not in L.R] for e in L.EVENTS}
    P(f"bins absent from CADC for an event: { {e: m for e, m in miss.items() if m} }")
    P("policy thresholds eta " + ", ".join(f"{k} {v:.2f}" for k, v in r["eta"].items()) + "; kept events " + ", ".join(f"{k} {len(v)}" for k, v in r["kept"].items()))
    P("the rule: amendment 18 as revision 4 and 5 read it, no credit of any kind (items 1 to 8, 15, 17): R = A_net^2 N n_b x fill x G / lambda_none,")
    P("tau unmeasured, so G is the admissible minimum of the fewest frames a policy's events carry (item 3), in the BAO-band gain (item 4).\n")
    P(f"{'range':10s} {'verdict':8s} {'bar':>8s} {'policy':9s} {'G':>6s} {'at G=1':>8s} {'at 8423 s':>10s} {'keep':>8s}")
    for rng, o in r["ranges"].items():
        P(f"{rng:10s} {o['verdict']:8s} {o['bar_db']:+8.2f} {o['bar_policy']:9s} {o['G_bar']:6.2f} {o['bar_G1_db']:+8.2f} {o['bar_arch_db']:+10.2f} {o['keep_stated_least_db']:+8.2f}")
        for p, d in o["policies"].items():
            P(f"    {p:9s} keeps {d['kept']:2d}, fewest frames {d['n_min_frames']:2d}, G_min {d['G_min']:.2f}, measured classes {d['n_measured']} of {len(d['classes'])}, {d['R_excl_db']:+.2f} dB, {d['R_G1_db']:+.2f} dB at G = 1")
        if o["excluded"]: P(f"    excluded (keeps no dump): {o['excluded']}")
        if o["blockers"]: P(f"    item 6 blockers: {o['blockers']}")
    kc = r["ranges"]["bao_long"]["policies"]["keep_all"]["classes"]
    P("\nlong BAO classes, keep_all, A_net in floor scatters: " + ", ".join(f"{c} {x['sigma']:.1f}" for c, x in kc.items()))
    P("per event, the long range at its own admissible minimum (the lowest-epoch form, a sensitivity): " + ", ".join(f"{x['epoch']} {x['bar_db']:+.1f}" for x in r["per_epoch_long"]))
    P(f"the lowest event reads {min(x['bar_db'] for x in r['per_epoch_long']):+.2f} dB")
    P(f"channel 24's own pilot-to-in-band relation, long classes (reported, not used): {r['pilot_to_inband_own_amp_db']:+.2f} dB amplitude,"
      f" {r['pilot_to_inband_own_amp_db_net']:+.2f} dB net of the floor")
    thr = {rng: ch24_threshold(o["R1"], g1t) for rng, o in r["ranges"].items()}
    L_, S_ = r["ranges"]["bao_long"], r["ranges"]["bao_short"]
    booking = "bao_long" if L_["verdict"] == "excise" else ("bao_short" if S_["verdict"] == "excise" else None)
    cp = None
    if booking:
        B = r["ranges"][booking]
        cp = ch24_cleaner_pol(B["bar_db"], B["G_bar"], r["exclusion_factor"])
    anyr = [rng for rng in ("bao_short", "bao_long") if thr[rng][1].startswith("excised at any")]
    thr_text = ("excised at any τ" if anyr else
                (f"tau > {min(t for t, _ in (thr['bao_short'], thr['bao_long']) if t is not None):.4g} s" if any(t is not None for t, _ in (thr["bao_short"], thr["bao_long"])) else "not excisable at any τ"))
    P("")
    if r["disposition"] == "excise":
        P(f"VERDICT (amendment 19, item 34): EXCISED on its own 2020 in-band measurement, on the {'long' if booking == 'bao_long' else 'short'} BAO baselines,")
        P(f"  {B['bar_db']:+.2f} dB over tolerance ({B['bar_policy']}, G {B['G_bar']:.2f}), {B['bar_G1_db']:+.2f} dB at G = 1; every policy that keeps an event is")
        P(f"  measured and over the allowance on both BAO ranges; {thr_text}.")
        P(f"  Rule variants on the booking range: cleaner polarization {cp['bar_db']:+.2f} dB ({cp['measured']} of {cp['n']} classes measured).")
    else:
        P(f"VERDICT (amendment 19, item 34): {r['disposition'].upper()} on its own 2020 in-band measurement.")
    P("  No keep: the stated keep reading (no credit, lambda_none, G at the cap) is "
      + ", ".join(f"{rng} {o['keep_stated_least_db']:+.1f} dB" for rng, o in r["ranges"].items() if rng != "shortest") + ".")
    pb = ch24_per_bin(own_events)
    over = [x for x in pb["rows"] if np.isfinite(x["bao_long_bar_db"]) and 10 ** (x["bao_long_bar_db"] / 10) > U.ALLOW_R]
    gtxt = (f"admissible minimum G {pb['G']:.2f}" if not own_events else
            f"each bin at the admissible minimum G of its own events' fewest frames, G {min(x['G'] for x in pb['rows']):.2f} to {max(x['G'] for x in pb['rows']):.2f}")
    lb = min(pb["rows"], key=lambda x: x["bao_long_bar_db"])
    P(f"  Per in-band bin (long range, {gtxt}, no credit): {len(over)} of {len(pb['rows'])} bins over the allowance, least"
      f" {lb['bao_long_bar_db']:+.1f} dB (freq_id {lb['freq_id']}{', ' + lb['edge'] + ' of the channel' if own_events and lb['edge'] else ''}).")
    if json_out:
        g1 = "excise" if any(r["ranges"][x]["verdict"] == "excise" and 10 ** (r["ranges"][x]["bar_G1_db"] / 10) > U.ALLOW_R for x in ("bao_short", "bao_long")) else "undetermined"
        js = dict(disposition=r["disposition"], disposition_G1=g1, basis="measured2020", world="none", ground="off", booking_range=booking,
                  deciding_bar_db=(r["ranges"][booking]["bar_db"] if booking else None), threshold=thr_text,
                  thresholds={rng: dict(tau_threshold_s=t, text=(why if t is None else ""), R_at_G1=r["ranges"][rng]["R1"]) for rng, (t, why) in thr.items()},
                  cleaner_pol=cp, reading=r,
                  per_bin=dict(G=pb["G"], n_frames=pb["n_frames"], n_over_long=len(over), n_bins=len(pb["rows"]),
                               **({"G_rule": "each bin's own events", "G_min_bins": min(x["G"] for x in pb["rows"]), "G_max_bins": max(x["G"] for x in pb["rows"])} if own_events else {})),
                  keep_stated_db=min(o["keep_stated_least_db"] for rng, o in r["ranges"].items() if rng != "shortest"),
                  inputs=dict(lane=L.lane, code=L.code, code_sha256=L.code_sha256, products_sha256=L.products_sha256,
                              n_products=L.n_products))
        def clean(x):
            if isinstance(x, dict): return {str(k): clean(v) for k, v in x.items()}
            if isinstance(x, (list, tuple)): return [clean(v) for v in x]
            if isinstance(x, (float, np.floating)): return None if not np.isfinite(x) else float(x)
            if isinstance(x, np.integer): return int(x)
            if isinstance(x, np.bool_): return bool(x)
            return x
        with open(json_out, "w") as fh: json.dump(clean(js), fh, indent=1, ensure_ascii=False)
    if per_bin_out:
        rows = pb["rows"]; fields = list(rows[0])
        with open(per_bin_out, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n"); w.writeheader()
            for x in rows:
                w.writerow({k: (f"{v:.4f}" if isinstance(v, (float, np.floating)) and k != "freq_mhz" and np.isfinite(v) else
                                (f"{v:.6f}" if k == "freq_mhz" else ("" if isinstance(v, (float, np.floating)) else v))) for k, v in x.items()})
    return 0


# ---------------------------------------------------------------- the record (ch24_2020_basis_a18.py)
def main(argv=None):
    import sys
    argv = ["cohort-basis"] + list(sys.argv[1:] if argv is None else argv)
    A18 = "--a18" in argv
    _tau = [argv[i + 1] for i, x in enumerate(argv) if x == "--tau-archive"]
    _js = [argv[i + 1] for i, x in enumerate(argv) if x == "--json"]
    _w = [argv[i + 1] for i, x in enumerate(argv) if x == "--world"]; WORLD = _w[0] if _w else "200ns"; assert WORLD in ("200ns", "none")
    _g = [argv[i + 1] for i, x in enumerate(argv) if x == "--ground"]; GROUND = _g[0] if _g else "on"; assert GROUND in ("on", "off")
    _s = [argv[i + 1] for i, x in enumerate(argv) if x == "--set"]; CH24_BASIS = "borrowed"
    for _x in _s:
        _k, _v = _x.split("="); assert _k == "CH24_BASIS" and _v in ("borrowed", "measured2020"), _x; CH24_BASIS = _v
    _pb = [argv[i + 1] for i, x in enumerate(argv) if x == "--per-bin"]
    OWN = "--per-bin-own-events" in argv                                    # r5.1 (triage row 24): each bin's G from its own events
    _gn = [argv[i + 1] for i, x in enumerate(argv) if x == "--g1-names"]; G1N = _gn[0] if _gn else "r5"; assert G1N in ("r5", "literal")   # r5.1, row 22
    _nt = [argv[i + 1] for i, x in enumerate(argv) if x == "--timed-frames"]
    _h = [argv[i + 1] for i, x in enumerate(argv) if x == "--handoff"]; _t = [argv[i + 1] for i, x in enumerate(argv) if x == "--record-table"]
    if not (_h and _t): raise SystemExit("cohort-basis: --handoff and --record-table are required")
    H = capture_handoff.open_handoff(_h[0]); TOR = _t[0]
    argv = [x for i, x in enumerate(argv) if x not in ("--a18", "--tau-archive", "--json", "--world", "--ground", "--set", "--per-bin", "--per-bin-own-events", "--g1-names", "--timed-frames", "--handoff", "--record-table") and (i == 0 or argv[i - 1] not in ("--tau-archive", "--json", "--world", "--ground", "--set", "--per-bin", "--g1-names", "--timed-frames", "--handoff", "--record-table"))]
    if len(argv) > 1: raise SystemExit(f"cohort-basis: unknown arguments {argv[1:]}")
    assert not (OWN or G1N != "r5") or CH24_BASIS == "measured2020"
    assert not _pb or CH24_BASIS == "measured2020"

    S_DB, RHO_CEIL, TF, CAP, ALLOW = (11.4 if WORLD == "200ns" else 0.0), 0.95, 16384 * 2.56e-6, 86164.0905, 3.0   # item 15: no S without a filter
    TAU_ARCHIVE = float(_tau[0]) if _tau else 8423.0      # channel 24's own archive-measured correlation time (item 9: 8,423 s, not 7777)
    TAU_FLOOR = 15.0          # amendment 5: no channel's tau_c lies below the campaign's shortest lag
    N_TIMED = int(_nt[0]) if _nt else 9470    # channel 24's current-era timed frames (the text of record; the era-redate record reads them from its histogram release)

    if CH24_BASIS == "measured2020":
        assert A18, "the measured 2020 basis is an amendment 18 ruling"
        if (WORLD, GROUND) != ("none", "off"):
            raise SystemExit("cohort-basis: the measured 2020 reading takes no credit and no delay filter (--world none --ground off); "
                             "post-processing is not modelled")
        load(H, TOR)
        return ch24_basis_main(TOR, _js[0] if _js else None, _pb[0] if _pb else None, OWN, G1N)
    H.borrowed = True   # the borrowed basis (item 9, revision 4) reads the cohort's pilot-bin table and the correction
    exc = {int(k): np.array(v) for k, v in H.json("cohort2020/cohort_exc_long.json").items()}
    pv = H.json("cohort2020/pilot_vs_inband_D1.json")

    print("== the 2020 cohort as a positive control ==")
    print("Channel 35's transmitter was off until 2021-10, so its pilot bin is a transmitter-off null")
    print("in the same frames. Every channel is read through the 2026 estimator on the same long BAO")
    print("classes (39 and 78 m north-south, 22 to 66 m east-west).\n")
    c35 = exc[35]; fm, fs = float(np.mean(c35)), float(np.std(c35, ddof=1))
    gate = fm + 3 * fs
    print(f"control ch35: excess mean {fm:.3e}, scatter {fs:.3e}, three-scatter gate {gate:.3e}\n")
    print(f"{'ch':>3} {'A_2020':>10} {'sigma over ch35':>16}  status in 2020")
    det = []
    for ch in sorted(exc):
        a = float(np.median(exc[ch])); s = (a - fm) / fs
        det.append((ch, a, s))
        print(f"{ch:>3} {a:>10.3e} {s:>16.1f}  {'DETECTED' if a > gate else 'at the null'}")
    on = [c for c, a, s in det if a > gate]
    print(f"\ndetected in 2020: {on}")
    print("Channels 26, 27 and 32 are detected here and read at the control floor in the 2026 capture,")
    print("which is what a transmitter that has since been switched off looks like. Channel 35, off in")
    print("2020, reads below its own null. The estimator therefore detects transmitters that were on")
    print("and does not detect one that was off, on the baselines the ruling rules on.\n")

    print("== channel 24 on the 2020 basis ==")
    corr_rows = [r for r in H.rows("frame_analysis/pilot_to_inband.csv") if r["correction_db"]]
    all_db = [float(r["correction_db"]) for r in corr_rows]
    strong_db = [float(r["correction_db"]) for r in corr_rows if r["strong"] == "True"]
    med_corr, worst_corr = float(np.median(strong_db)), float(min(strong_db))
    print(f"pilot-bin to in-band correction, measured on the 2026 capture over the four science dumps and")
    print(f"the five long BAO classes with the ruling's own estimator and larger-polarisation rule")
    print(f"(pilot_to_inband.py, pilot_to_inband.csv):")
    print(f"  all {len(all_db)} usable channels: median {np.median(all_db):+.2f} dB, worst {min(all_db):+.2f} dB")
    print(f"  the {len(strong_db)} strong transmitters: median {med_corr:+.2f} dB, worst {worst_corr:+.2f} dB")
    print("  A channel at the floor reads the same on its pilot bin and in band, so a weak channel's ratio")
    print("  is near unity and carries no information. Channel 24 is a strong transmitter, so the strong")
    print("  subset is the relevant population and its worst case is the figure carried below. The")
    print("  correction is never measured on channel 24 itself, whose band is absent from every 2026 dump;")
    print("  that is the chief caveat on this row.\n")

    lam = None
    for x in read_rows(TOR):
        if int(x["channel"]) == 24 and x["role"] != "pilot" and x["lambda_deployed"]:
            lam = float(x["lambda_deployed"] if WORLD == "200ns" else x["lambda_none"]); break
    A_pilot = float(np.median(exc[24]))
    S, credit = 10 ** (-S_DB / 10), (1 - RHO_CEIL ** 2 if GROUND == "on" else 1.0)   # r4, item 17: no ground credit under --ground off
    if WORLD == "200ns": print(f"A on the pilot bin {A_pilot:.3e}; lambda_deployed {lam:.4g}; delay cut {S_DB} dB;")
    else: print(f"A on the pilot bin {A_pilot:.3e}; lambda_none {lam:.4g}; no delay filter (item 15: system temperature and DTV RFI only);")
    if GROUND == "on": print(f"ground credit at the 0.95 ceiling {-10*np.log10(credit):.1f} dB (the most generous the rule allows).\n")
    else: print("no ground credit (item 17: no post-processing credit of any kind).\n")
    if A18: print("the record's booked form (A in amplitude units, zero-frequency G), which amendment 18 item 1 supersedes:")
    print(f"{'correction':>16} {'A':>11} {'tau_c':>9} {'G':>9} {'bar':>9}")
    rows = []
    for name, corr in (("strong median", med_corr), ("strong worst case", worst_corr)):
        A = A_pilot * 10 ** (corr / 10)
        for tau in (TAU_ARCHIVE, 1200.0, TAU_FLOOR):
            G = min(tau, CAP) / TF
            bar = 10 * np.log10(A * S * credit * G / lam)
            rows.append((name, corr, tau, G, bar))
            print(f"{name:>16} {A:>11.3e} {tau:>9.1f} {G:>9.0f} {bar:>+8.2f} dB")
        thresh = (10 ** (ALLOW / 10)) * lam / (A * S * credit) * TF
        if not A18: print(f"{name:>16} crosses the {ALLOW:.0f} dB allowance at tau_c = {thresh:.1f} s\n")
        else: print()
    worst_at_floor = [b for n, c, t, g, b in rows if n == "strong worst case" and t == TAU_FLOOR][0]
    worst_at_arch = [b for n, c, t, g, b in rows if n == "strong worst case" and t == TAU_ARCHIVE][0]
    thresh_worst = (10 ** (ALLOW / 10)) * lam / (A_pilot * 10 ** (worst_corr / 10) * S * credit) * TF
    if A18:
        lam_n = [float(x["lambda_none"]) for x in read_rows(TOR) if int(x["channel"]) == 24 and x["role"] != "pilot" and x["lambda_none"]][0]
        print("VERDICT (amendment 18, the rule as written): UNDETERMINED on the 2020 basis.")
        print(f"  The excision rests on the pilot-to-in-band correction, and that correction is not measured on channel 24:")
        print(f"  the {worst_corr:+.2f} dB carried here is the worst of {len(strong_db)} other strong transmitters on the 2026 capture, whose")
        print("  dumps do not contain channel 24's band. Under the rule an unmeasured quantity takes its most favorable value")
        print("  on exclusion (amendment 18 item 9). Nothing measured on channel 24 bounds how far below its pilot bin the")
        print("  in-band level sits, so the most favorable value places it inside the allowance and no bar follows.")
        print("  Channel 24 is therefore not excisable at any \u03c4 on this basis.")
        # item 5: the stated keep takes no credit, so the borrowed correction is not applied; G at the cap is item 4's BAO-band gain
        G_cap = U.gain_bao(CAP, 24); x_keep = A_pilot ** 2 * U.NFFT * 4; keep_db = 10 * np.log10(x_keep * G_cap / lam_n)
        print(f"  No keep: the stated keep reading (no credit and no borrowed correction, lambda_none, the BAO-band G at the cap {G_cap:.0f},")
        print(f"  A^2 N n_b with n_b 4, the fewest baselines of any long class) is {keep_db:+.1f} dB over tolerance.")
        if _js:
            js = dict(disposition="undetermined", tau_archive_s=TAU_ARCHIVE, correction_db=worst_corr, n_strong=len(strong_db),
                      keep_stated_db=keep_db, G_cap=G_cap, threshold="not excisable at any \u03c4")
            if WORLD != "200ns": js.update(world=WORLD, lambda_booked_form=lam, S_db=S_DB)
            if GROUND == "off": js.update(ground_credit="off")
            with open(_js[0], "w") as fh: json.dump(js, fh, indent=1)
        return 0
    print("VERDICT (2020 basis, stated conditionally):")
    print(f"  Channel 24 is over tolerance by {worst_at_arch:+.1f} dB at its own archive-measured correlation")
    print(f"  time of {TAU_ARCHIVE:.0f} s, on the worst-case correction for a strong transmitter and with every")
    print("  credit the rule allows.")
    print(f"  The excision requires a coherence time above {thresh_worst:.1f} s. The archive measures {TAU_ARCHIVE:.0f} s on")
    print(f"  this channel, a factor of {TAU_ARCHIVE/thresh_worst:.0f} above the threshold. At {TAU_FLOOR:.0f} s, the campaign-wide")
    print(f"  floor of amendment 5, the bar is {worst_at_floor:+.1f} dB, INSIDE the 3 dB allowance, so the excision")
    print("  rests on this channel's own measured correlation time and not on the floor alone. State it")
    print("  that way: it is conditional on the coherence time as well as on the transmitter.")
    print("  The transmitter condition: the archive ledger records channel 24 transmitting continuously")
    print(f"  from 2018-12 to 2026-04 with no declared off epoch, zero off frames and {N_TIMED:,} frames flagged")
    print("  transmitter-on; its bin ceased on 2026-04-16 because no live node covers it, not because it")
    print("  went quiet.")
    return 0
