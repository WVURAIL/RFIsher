"""The capture ruling of record: the table of record per baseline range, and its amendment 18 and 19 readings.

The release r5.2 producer ``ruling_a18.py`` (a copy of the record's ``ruling_baseline.py`` with the author's
decisions as named switches), with its logic unchanged. Its inputs are injected: the measured inputs come from the
capture handoff (:mod:`capture_handoff`, which returns the objects the release's own reading lines built), the units
from :mod:`capture_units`, and the switch sets from the rule files ``projects/chime_bao/capture_rules/`` (``record``
is the identity, ``a18``, ``r5``, ``r5_1`` and ``r5_2`` the releases', ``sensitivities/`` the named readings). With
the ``record`` rule and the record's input table it writes the table of record byte for byte (9867551a); with
``r5_2`` it writes the release's ``run/`` files.

Switches (identity value first; --a18 sets every switch to its amendment 18 value, the last listed but g1):
  UNITS           booked | power          item 1: R from A_net (booked) or the per-frame covariance ratio A_net^2 N n_b,
                                          in R_dep, R_none and the detection gate; "measured" stays the amplitude test
  POL             larger | stokes_i       item 2: the larger per-pol product, or Stokes I (A, tau and the channel 37
                                          floor all read on the complex mean of the XX and YY class stacks)
  UNMEASURED_TAU  current | gmin | g1     item 3: unpriced ranges and refused classes (dropped), or priced at the
                                          admissible minimum G per range and per refused class; g1 is the G = 1
                                          sensitivity
  GAIN            zero | bao              item 4: the zero-frequency block count, or the BAO-band shell average with bin fill
  KEEP            coded | stated          item 5: the coded keep (credits, lambda_dep, measured G, a short range at the
                                          floor accepted), or the stated rule (no credits, lambda_none, G at the cap,
                                          no at-floor range accepted)
  EVERY_POLICY    coded | thesis          item 6: at-floor policies skipped, or every policy that keeps a dump must be
                                          over the allowance (an at-floor policy blocks); no-dump policies listed
  ALLOWANCE       db | ratio              item 7: the test db(R) > 3, or R > 10^0.3 stated as such
  THRESHOLDS      off | on                item 8: thresholds from unrounded R with the code's own test
  WORLD           200ns | none            item 15: the exclusion side in the deployed 200 ns world (lambda_deployed and
                                          the delay-filter credit S, the record's), or in the no-filter world
                                          (lambda_none, no S; under GAIN=bao the bin fill is read on the no-filter
                                          per-bin tolerances); the ground-filter credit (1 - gamma^2) stays in both
                                          (item 16), and the keep side is unchanged (it already reads lambda_none)
  GROUND_CREDIT   on | off                item 17: the exclusion side with the ground-filter credit (1 - gamma^2), or with
                                          no credit; under off the rescue coherence is the coherence a ground filter would
                                          need with no credit taken, printed beside the measured one
  TAU_LOWER_BOUNDS off | on               item 35: unmeasured and refused classes at the admissible minimum G, or, where the
                                          within-dump lane bounds the class's tau (a19_inputs.tau_lower_bounds), at the
                                          bound (never below the admissible minimum); exclusion side only

r3 (2026-09-24, DECISIONS.md items 15 and 16): the WORLD switch. The model is idealized (system temperature and DTV RFI
only), so the exclusion side reads the no-filter tolerance lambda_none, as the keep side already does, and the delay-filter
credit S is removed; the ground-filter credit (1 - gamma^2) stays. --a18 now includes WORLD=none; --a18 --set WORLD=200ns
is revision 2 (results/capture_ruling_a18_2026-09-24_r2), reproduced byte for byte (tests/test_a18.py test_reproduces_r2).

r4 (2026-09-24, DECISIONS.md items 17 and 18): the GROUND_CREDIT switch. No post-processing credit of any kind: the
exclusion side compares the measured residual with the idealized survey's tolerance (lambda_none) without the ground-filter
credit (1 - gamma^2). The bin fill stays: it is part of the BAO-band gain model, not a credit. --a18 now includes
GROUND_CREDIT=off; --a18 --set GROUND_CREDIT=on is revision 3 and --a18 --set WORLD=200ns --set GROUND_CREDIT=on is
revision 2, both reproduced byte for byte (tests/test_a18.py test_reproduces_r3 and test_reproduces_r2).

r5 (2026-09-25, DECISIONS.md item 35, amendment 19): the TAU_LOWER_BOUNDS switch. A measured lower bound on tau counts as
measured when excising: where the within-dump autocorrelation lane (with its independent check) bounds a class's tau, an
unmeasured or refused class is priced at that bound (the least over every variant of both, capped at the longest lag the
lane observes, 1.34 s, beyond which a bound is a model extrapolation) instead of the admissible minimum G; the bound never
prices below the admissible minimum, which is the least G any tau allows. The keep side is
unchanged (it reads G at the cap). --a18 now includes TAU_LOWER_BOUNDS=on; --a18 --set TAU_LOWER_BOUNDS=off is revision 4,
reproduced byte for byte (tests/test_a18.py test_reproduces_r4). Channel 24 has no capture products and is ruled on its
2020 in-band measurement by ch24_2020_basis_a18.py (CH24_BASIS), not here.

B-4 (2026-09-25, red-team triage row 4, a sensitivity for r5.1): the TAU_CENSOR switch. The cadence estimator sets tau to the
first populated lag class (15 s) when the structure function already reaches its target there (cadence_tau.py, k == 0), so a
"measured" 15.0 s says only tau <= 15 s. Under TAU_CENSOR=on such a class is unmeasured on the exclusion side (item 3): it is
priced at its within-dump lower bound where one exists (item 35; a19_inputs.tau_lower_bounds(censor=True) adds the bounds
this lane measured for the censored classes), else at the admissible minimum, and enters the range's median as a refused
class does. Off (the default, also under --a18) reproduces r5 byte for byte.

r5.1 (2026-09-25, red-team triage rows 4, 22 and 35, work items B-3 and B-4): four more switches, each at its r5 value under
--a18, so --a18 still reproduces r5 byte for byte (tests/test_a18.py test_reproduces_r5); --r51 sets --a18 and the r5.1 values.
  TAU_CENSOR all      B-4 as above, and also a censored trim probe (a probe of a resolved class at the 15 s lag minimum) is
                      priced as a censored class is (its within-dump bound, else the admissible minimum) in the least-probe
                      reading (amendment 10 item 7), as B-4/tier_c.py prices it
  BOUND_SOURCE        summary | fits: the check's lags-1-and-2 bound from check_ac/summary.json (rounded, r5) or from
                      check_ac/fits_check.csv (0.918 s and 0.439 s, triage row 35)
  BOUND_CALIBRATION   off | on: on, a bound prices a class only when it beats the channel 37 null of B-3 (at most 5 % of the
                      91 null cells certify at or above it, B-3/PLAN.md section 3)
  G1_NAMES            r5 | literal: the verdict and threshold texts name R with every class at G = 1 "literal G = 1"
                      (triage row 22); the G = 1 sensitivity run is "unmeasured classes at G = 1" in the release tables
  SWITCH_RECORD       omit | all: the json's switches omit the identity values that reproduce the frozen releases (r5), or
                      record every switch (triage row 35)

r5.2 (2026-09-25, DECISIONS.md item 41, work item B-1): two more switches for the ground-credit sensitivity reading, each at its
r5.1 value under --a18 and --r51, so both still reproduce r5 and r5.1 byte for byte (tests/test_a18.py test_reproduces_r5 and
test_reproduces_r51); --r52 sets --r51 and the r5.2 values. They act only where a ground credit is taken (GROUND_CREDIT=on, the
credit readings) and in the printed coherence columns and rescue texts; the no-credit ruling's R, bars and dispositions do not use them.
  CREDIT_FORM         one_minus_gamma_sq | one_minus_gamma: the credit (1 - gamma^2) of revisions 2 to 5.1, or the form B-1 settles
                      from the ground filter's definition, (1 - gamma): a per-day filter leaves f = 1 - |E V|^2 / E|V|^2, and for the
                      pair statistic gamma = E cos(phi_a - phi_b) the least f any amplitude fluctuation allows is 1 - gamma (the
                      most generous credit the measured gamma allows); the rescue coherence is read in the same form
  CREDIT_GAMMA        released | reconciled: the range's gamma as the median over all its classes (revisions 2 to 5.1), or B-1's
                      reconciled definition, the median over its measured (gain) classes, the classes whose residual G prices, with
                      the all-class median where none is measured; clamped to [0, 0.95] either way

usage: rfisher records capture-ruling --rule NAME [--sensitivity NAME] [--set NAME=VALUE ...] --input TABLE
                                      --handoff DIR --out CSV [--json OUT.json] [--thresholds OUT.csv] [--ch33-rescan]
"""
import csv, json, re
from pathlib import Path

import numpy as np

from rfisher.records.chime_atsc_2026 import capture_handoff
from rfisher.records.chime_atsc_2026 import capture_units as U
from rfisher.records.chime_atsc_2026._files import read_rows

RULES = "capture_rules"
CHOICES = dict(UNITS=("booked", "power"), POL=("larger", "stokes_i"), UNMEASURED_TAU=("current", "gmin", "g1"), GAIN=("zero", "bao"),
               KEEP=("coded", "stated"), EVERY_POLICY=("coded", "thesis"), ALLOWANCE=("db", "ratio"), THRESHOLDS=("off", "on"), WORLD=U.WORLDS, GROUND_CREDIT=("on", "off"),
               TAU_LOWER_BOUNDS=("off", "on"), TAU_CENSOR=("off", "on", "all"),
               BOUND_SOURCE=("summary", "fits"), BOUND_CALIBRATION=("off", "on"), G1_NAMES=("r5", "literal"), SWITCH_RECORD=("omit", "all"),
               CREDIT_FORM=("one_minus_gamma_sq", "one_minus_gamma"), CREDIT_GAMMA=("released", "reconciled"))
PILOT = {14:844,15:829,16:813,17:798,18:783,19:767,20:752,21:736,22:721,23:706,24:690,25:675,26:660,27:644,28:629,29:614,30:598,31:583,32:568,33:552,34:537,35:521,36:506,37:491}
POLICIES = ["cal_q0.1", "cal_q0.5", "cal_q0.9", "keep_all"]; QS = {"cal_q0.1": 0.1, "cal_q0.5": 0.5, "cal_q0.9": 0.9}
SCIENCE = {"20260916162300": "pilot", "20260917040230": "D1", "20260917090230": "D2", "20260917140230": "D3"}
TF = 16384 * 2.56e-6; CAP = 86164.0905; ALLOW_DB = 3.0; NSIG = 3.0
RANGES = {"shortest": [(0, 1)], "bao_short": [(0, 32), (0, 64)], "bao_long": [(0, 128), (0, 255), (1, 0), (2, 0), (3, 0)]}
RANGE_TEXT = {"shortest": "the 0.3 m baseline", "bao_short": "the short BAO baselines (9.8 and 19.5 m north-south)", "bao_long": "the long BAO baselines (39 and 78 m north-south, 22 to 66 m east-west)"}
TAU_FILES = {(0, 1): "cadence_tau.csv", (0, 32): "cadence_tau_ns32.csv", (0, 64): "cadence_tau_ns64.csv", (0, 128): "cadence_tau_ns128.csv", (0, 255): "cadence_tau_ns255.csv", (1, 0): "cadence_tau_ew1.csv", (2, 0): "cadence_tau_ew2.csv", (3, 0): "cadence_tau_ew3.csv"}
CLS_NAME = {(0, 1): "ns1", (0, 8): "ns8", (0, 32): "ns32", (0, 64): "ns64", (0, 128): "ns128", (0, 255): "ns255", (1, 0): "ew1", (1, 32): "ew1ns32", (2, 0): "ew2", (3, 0): "ew3"}


class RuleError(ValueError):
    """A rule file or a switch the ruling does not accept."""


def _project(project=None):
    if project is not None:
        return Path(project)
    from rfisher.policy import default_project
    return default_project()


def rule_file(name, project=None, sensitivity=False):
    base = _project(project).joinpath(RULES, *(("sensitivities",) if sensitivity else ()))
    path = base.joinpath(f"{name}.json")
    if not path.is_file():
        raise RuleError(f"no capture {'sensitivity' if sensitivity else 'rule'} named {name!r}")
    doc = json.loads(path.read_text())
    for k, v in doc["switches"].items():
        if k not in CHOICES or v not in CHOICES[k]:
            raise RuleError(f"{path.name}: {k}={v} is not a switch value of the ruling")
    return doc


def resolve(name, project=None):
    """The rule's switches: its base's, updated with its own."""
    doc = rule_file(name, project)
    sw = dict(resolve(doc["base"], project)) if doc["base"] else {}
    sw.update(doc["switches"])
    if doc["base"] is None and set(sw) != set(CHOICES):
        raise RuleError(f"{name}: the identity rule must set every switch")
    return sw


def switch_sets(project=None):
    """IDENTITY, AMENDMENT18, R51 and R52 of the release, from the rule files."""
    return (resolve("record", project), dict(rule_file("a18", project)["switches"]),
            dict(rule_file("r5_1", project)["switches"]), dict(rule_file("r5_2", project)["switches"]))


def main(argv=None, *, project=None):
    import sys
    _a = list(sys.argv[1:] if argv is None else argv)
    rule = sensitivity = inp = outp = handoff_dir = None; JSON_OUT = THR_OUT = None; CH33_RESCAN = False; sets = []
    while _a:
        x = _a.pop(0)
        if x == "--rule": rule = _a.pop(0)
        elif x == "--sensitivity": sensitivity = _a.pop(0)
        elif x == "--set": sets.append(_a.pop(0))
        elif x == "--input": inp = _a.pop(0)
        elif x == "--handoff": handoff_dir = _a.pop(0)
        elif x == "--out": outp = _a.pop(0)
        elif x == "--json": JSON_OUT = _a.pop(0)
        elif x == "--thresholds": THR_OUT = _a.pop(0)
        elif x == "--ch33-rescan": CH33_RESCAN = True
        elif x == "--project": project = _a.pop(0)
        else: raise SystemExit(f"capture-ruling: unknown argument {x!r}")
    if not (rule and inp and outp and handoff_dir):
        raise SystemExit("capture-ruling: --rule, --input, --handoff and --out are required")
    IDENTITY, AMENDMENT18, R51, R52 = switch_sets(project)
    R5_VALUES = {k: AMENDMENT18[k] for k in R51}   # the values --a18 keeps, which r5 was built with
    R51_VALUES = {k: AMENDMENT18[k] for k in R52}   # the values --a18 and --r51 keep, which r5 and r5.1 were built with; never written to the json
    SW = resolve(rule, project)
    if sensitivity: SW.update(rule_file(sensitivity, project, sensitivity=True)["switches"])
    for s in sets:
        k, v = s.split("="); assert k in CHOICES and v in CHOICES[k], (k, v); SW[k] = v
    H = capture_handoff.open_handoff(handoff_dir)
    # item 35: the within-dump 95 % lower bounds, read on Stokes I (the lane's product), used only where the admissible minimum was
    TAU_LB = {}
    if SW["TAU_LOWER_BOUNDS"] == "on":
        assert SW["POL"] == "stokes_i" and SW["UNMEASURED_TAU"] != "current", "the bounds are Stokes I and replace the admissible minimum"
        _LB = capture_handoff.tau_lower_bounds(H, censor=SW["TAU_CENSOR"] != "off", source=SW["BOUND_SOURCE"], calibrate=SW["BOUND_CALIBRATION"] == "on")
        # the bound, capped at the longest lag the lane observes (a19_inputs); r5.1: only a bound that beats the channel 37 null prices a class
        TAU_LB = {k: v["lb_priced"] for k, v in _LB.items() if v.get("calibration", {}).get("passes", True)}
    else: assert SW["BOUND_SOURCE"] == "summary" and SW["BOUND_CALIBRATION"] == "off", "the bound switches need TAU_LOWER_BOUNDS=on"
    LB_USED = {}   # (channel, class) -> the priced tau, wherever a bound replaced the admissible minimum
    # item 7: the allowance is R > 10^0.3; the "db" identity tests db(R) > 3 as the record does
    G1T = "literal G = 1" if SW["G1_NAMES"] == "literal" else "G = 1"   # r5.1 (triage row 22): R with every class at G = 1
    ATXT = f"{ALLOW_DB:.0f} dB allowance" if SW["ALLOWANCE"] == "db" else "10^0.3 (about 2) allowance"
    def exceeds(bar_db): return bar_db > ALLOW_DB if SW["ALLOWANCE"] == "db" else 10 ** (bar_db / 10) > U.ALLOW_R
    def within(bar_db): return bar_db <= ALLOW_DB if SW["ALLOWANCE"] == "db" else 10 ** (bar_db / 10) <= U.ALLOW_R
    def gain(t, ch):
        """item 4: the coherence gain of a coherence time t on channel ch."""
        return min(t, CAP) / TF if SW["GAIN"] == "zero" else U.gain_bao(min(t, CAP), ch)
    rows_in = list(read_rows(inp))
    lam_none = {int(r["channel"]): float(r["lambda_none"]) for r in rows_in if r["lambda_none"]}
    lam_dep = {int(r["channel"]): float(r["lambda_deployed"]) for r in rows_in if r["lambda_deployed"]}
    sup = {int(r["channel"]): float(r["suppression_db"]) for r in rows_in if r["suppression_db"]}
    if SW["WORLD"] == "200ns":
        lam_excl = lam_dep          # the tolerance the exclusion side reads
        if SW["GAIN"] == "bao":   # item 4: the bin fill enters the deployed R beside S
            fill = {c: U.fill_factor(c, lam_dep[c]) for c in sup if c in lam_dep}
            sup = {c: s - 10 * np.log10(fill[c]) for c, s in sup.items()}
    else:
        # item 15: no delay filter, so no S credit, and lambda_none on the exclusion side; under item 4 the bin fill is read on
        # the no-filter per-bin tolerances, whose least over a channel's bins is its lambda_none (checked here)
        lam_excl = {c: lam_none[c] for c in lam_dep}
        assert all(repr(min(U.lam_bin_none()[b] for b in U.bin_overlaps(c))) == repr(lam_none[c]) for c in lam_excl)
        fill = {c: (U.fill_factor(c, lam_none[c], "none") if SW["GAIN"] == "bao" else 1.0) for c in sup if c in lam_excl}
        sup = {c: -10 * np.log10(fill[c]) for c in sup}
    # item 15: the verdict texts name the credits the exclusion side takes
    if SW["GROUND_CREDIT"] == "on": CREDITS = "both credits" if SW["WORLD"] == "200ns" else "the ground-filter credit"
    else: CREDITS = "the delay-filter credit alone" if SW["WORLD"] == "200ns" else "no credit"   # item 17
    RCOL = "R_deployed" if SW["WORLD"] == "200ns" else "R_exclusion"   # the exclusion-side ratio's column
    # the measured inputs (ruling_a18.py lines 180 to 266), from the handoff
    _IN = capture_handoff.ruling_inputs(H, "stokes_i" if SW["POL"] == "stokes_i" else "larger", CH33_RESCAN)
    ex, fl, floor, POL_OF_CLASS = _IN.ex, _IN.fl, _IN.floor, _IN.POL_OF_CLASS
    tau, tau_least, tau_probe_meas, tau_pol = _IN.tau, _IN.tau_least, _IN.tau_probe_meas, _IN.tau_pol
    # B-4: a "measured" tau at the first populated lag class (15 s) is an upper limit (cadence_tau.py, k == 0): unmeasured on exclusion
    LAG_MIN = 15.0; TAU_CENSORED = {}
    if SW["TAU_CENSOR"] != "off":
        assert SW["UNMEASURED_TAU"] != "current", "a censored tau is priced as item 3 prices an unmeasured one"
        for k_, (st_, v_) in sorted(tau.items()):
            if st_ == "measured" and np.isfinite(v_) and v_ <= LAG_MIN:
                TAU_CENSORED[k_] = v_; tau[k_] = ("refused: censored at the 15 s lag minimum", CAP)
    rho, eta, Qmed = _IN.rho, _IN.eta, _IN.Qmed
    if CH33_RESCAN:
        print("channel 33 under the measured-pilot bank: eta", {k: round(x, 2) for k, x in eta[33].items()}, "dump Q medians", {ev: round(Qmed[(33, ev)], 2) for ev in SCIENCE})
    def kept(ch, pol):
        if pol == "keep_all": return list(SCIENCE)
        if ch not in eta: return []
        return [ev for ev in SCIENCE if (ch, ev) in Qmed and Qmed[(ch, ev)] <= eta[ch][pol]]
    def gmed(v):
        v = sorted(v); n = len(v)
        return v[n // 2] if n % 2 else float(np.sqrt(v[n // 2 - 1] * v[n // 2]))
    def db(x): return 10 * np.log10(x) if (x is not None and np.isfinite(x) and x > 0) else np.nan

    def class_reading(ch, epochs, c, fixpol=None):
        """(A_net, measured, floor_mean, floor_sd, pol) on the larger-polarisation reading over the given epochs."""
        best = None
        for p in ((fixpol,) if fixpol is not None else (0, 1)):
            vals = [ex[(ch, e, c, p)] for e in epochs if (ch, e, c, p) in ex]
            if not vals or (c, p) not in floor: continue
            A = float(np.median(vals)); fm, fs = floor[(c, p)]
            cand = dict(A_net=A - fm, measured=A > fm + NSIG * fs, fm=fm, fs=fs, pol=p, A=A, gate=NSIG * fs)
            if best is None or cand["A_net"] > best["A_net"]: best = cand
        if best is not None and SW["UNITS"] == "power":
            # item 1: the per-frame covariance ratio A_net^2 N n_b, and the gate (3 s)^2 N n_b; "measured" is unchanged
            best = dict(best, A_net=U.to_power(best["A_net"], c), gate=U.gate_power(best["gate"], c))
        return best

    def _tau_of(ch, c, least):
        """The class's coherence time, or under least= the smallest of its trim probes."""
        if least:
            v = tau_least.get((ch, c), np.nan)
            if np.isfinite(v): return v
        return tau[(ch, c)][1]

    def ground_credit(rh):
        """The ground-filter credit at range coherence rh: (1 - rh^2), revisions 2 to 5.1, or the settled (1 - rh), r5.2 (item 41, B-1)."""
        return 1 - rh ** 2 if SW["CREDIT_FORM"] == "one_minus_gamma_sq" else 1 - rh

    def rescue_rho(bar_db, rh):
        """The coherence a ground filter must reach to bring bar_db inside the allowance. Under GROUND_CREDIT=off (item 17) the
        bar takes no ground credit, so the filter would supply the whole reduction: no measured coherence is taken first.
        r5.2: in the credit's own form, (1 - rho) under CREDIT_FORM=one_minus_gamma."""
        if SW["GROUND_CREDIT"] == "off": rh = 0.0
        if not np.isfinite(bar_db) or bar_db <= ALLOW_DB: return np.nan
        if SW["CREDIT_FORM"] == "one_minus_gamma":
            rem = (1.0 - rh) * 10 ** ((ALLOW_DB - bar_db) / 10.0)
            return float(1.0 - rem) if 0.0 < rem < 1.0 else np.nan
        rem = (1.0 - rh ** 2) * 10 ** ((ALLOW_DB - bar_db) / 10.0)
        return float(np.sqrt(1.0 - rem)) if 0.0 < rem < 1.0 else np.nan

    def gain_classes(ch, rng):
        """Amendment 11 item 2: a range's gain is read only on classes whose excess is measured above the
        control floor. G prices the persistence of the residual A measures, and a class at the floor has no
        measured residual to persist."""
        out = [c for c in RANGES[rng] if (lambda r: bool(r) and r["measured"])(class_reading(ch, list(SCIENCE), c))]
        return out or RANGES[rng]

    def unmeasured_G(ch, n=None):
        """item 3: the G an unmeasured tau takes on exclusion: the admissible minimum for the shortest dump the reading can
        draw on (the pilot dump, 11 frames, on a pilot-bin channel; 4 frames otherwise, or the frame count of the epoch that
        sets a lowest-epoch bound), or 1 under the g1 sensitivity."""
        if SW["UNMEASURED_TAU"] == "g1": return 1.0
        if n is None: n = 11 if has_pilot[ch] else 4
        return U.admissible_min_G(n)

    def lb_price(ch, c, g):
        """item 35: the tau an unmeasured or refused class takes on exclusion: its within-dump 95 % lower bound where one exists,
        never below the admissible minimum g (the least G any tau allows), else g; None when the class has no bound."""
        if (ch, c) not in TAU_LB: return None
        v = max(TAU_LB[(ch, c)], g); LB_USED[(ch, c)] = TAU_LB[(ch, c)]; return v

    def _lb_text(ch, cs, g):
        return ", ".join(f"{CLS_NAME[c]} {TAU_LB[(ch, c)]:.4g} s" + ("" if TAU_LB[(ch, c)] >= g else f" (below the admissible minimum, G {g / TF:.2f} kept)") for c in cs)

    def range_gain(ch, rng, least=False, n=None):
        t, st, note = _range_gain_record(ch, rng, least)
        if SW["UNMEASURED_TAU"] == "current": return t, st, note
        # item 3: an unmeasured range is priced at the admissible minimum, and a refused class enters the range's
        # geometric median at it instead of being dropped (it also replaces a borrowed tau)
        g = unmeasured_G(ch, n) * TF; cls = gain_classes(ch, rng)
        if not np.isfinite(t):
            # item 35: each class of the range takes its within-dump lower bound where one exists, the others the admissible
            # minimum, in the range's geometric median (as a refused class enters it under item 3)
            lbc = [c for c in cls if lb_price(ch, c, g) is not None]
            if lbc:
                v = [lb_price(ch, c, g) for c in lbc] + [g] * (len(cls) - len(lbc))
                rest = len(cls) - len(lbc)
                return gmed(v), (f"unmeasured, priced at the within-dump lower bound{'s' if len(lbc) > 1 else ''} ({_lb_text(ch, lbc, g)})"
                                 + (f" and G {g / TF:.2f} on {rest} class{'es' if rest > 1 else ''}" if rest else "")), note
            return g, f"unmeasured, priced at G {g / TF:.2f}", note
        ref = [c for c in cls if (ch, c) in tau and tau[(ch, c)][0].startswith("refused")]
        if not ref: return t, st, note
        meas = [_tau_of(ch, c, least) for c in cls if (ch, c) in tau and tau[(ch, c)][0] in ("measured", "bound") and np.isfinite(tau[(ch, c)][1])]
        meas = [v for v in meas if np.isfinite(v)]
        lbc = [c for c in ref if lb_price(ch, c, g) is not None]
        if lbc:   # item 35
            rest = len(ref) - len(lbc)
            return (gmed(meas + [lb_price(ch, c, g) for c in lbc] + [g] * rest),
                    st + f"; {len(lbc)} refused class{'es' if len(lbc) > 1 else ''} at the within-dump lower bound{'s' if len(lbc) > 1 else ''} ({_lb_text(ch, lbc, g)})"
                    + (f"; {rest} refused class{'es' if rest > 1 else ''} at G {g / TF:.2f}" if rest else ""), note)
        return gmed(meas + [g] * len(ref)), st + f"; {len(ref)} refused class{'es' if len(ref) > 1 else ''} at G {g / TF:.2f}", note

    def _range_gain_record(ch, rng, least=False):
        CLASSES = gain_classes(ch, rng)
        meas = [_tau_of(ch, c, least) for c in CLASSES if (ch, c) in tau and tau[(ch, c)][0] == "measured" and np.isfinite(tau[(ch, c)][1])]
        meas = [v for v in meas if np.isfinite(v)]
        # amendment 12: amendment 7 reads a range's coherence time as the median of its classes,
        # "where a class is bound its lower end is used", so a bound class enters the aggregate beside
        # the measured ones rather than only when every class of the range is bound.
        bnd = [_tau_of(ch, c, least) for c in CLASSES if (ch, c) in tau and tau[(ch, c)][0] == "bound" and np.isfinite(tau[(ch, c)][1])]
        bnd = [v for v in bnd if np.isfinite(v)]
        rh = range_rho(ch, rng)
        if meas: return gmed(meas + bnd), ("measured" if not bnd else "measured with a bound class"), ""
        if bnd: return bnd[0], "bound", ""
        if rng == "bao_long" and (ch, (0, 64)) in tau and tau[(ch, (0, 64))][0] == "measured" and np.isfinite(tau[(ch, (0, 64))][1]):
            return _tau_of(ch, (0, 64), least), "borrowed", f"no measured class on the long range; the channel's own measured coherence time on the 19.5 m class is used (amendment 9 item 3)"
        return np.nan, "unmeasured", "no measured class on the range and no borrowed measurement (amendment 9 item 3)"
    def range_rho(ch, rng):
        v = [rho[(ch, CLS_NAME[c])] for c in RANGES[rng] if (ch, CLS_NAME[c]) in rho]
        if SW["CREDIT_GAMMA"] == "reconciled":   # r5.2 (B-1 section 3): the median over the measured (gain) classes, else as released
            # gain_classes returns every class of the range when none is measured, which is the released median
            vm = [rho[(ch, CLS_NAME[c])] for c in gain_classes(ch, rng) if (ch, CLS_NAME[c]) in rho and np.isfinite(rho[(ch, CLS_NAME[c])])]
            if vm: v = vm
        return float(min(max(np.median(v), 0.0), 0.95)) if v else 0.0

    results = {}
    has_pilot = {ch: (ch in eta and any((ch, ev) in Qmed for ev in SCIENCE)) for ch in PILOT}
    # r5.1 (TAU_CENSOR=all, B-4 tier C): a trim probe of a resolved class at the 15 s lag minimum is an upper limit too; in the
    # least-probe reading it is priced as a censored class is (the class's within-dump bound, else the admissible minimum of the
    # reading's shortest dump, or G = 1 under the g1 sensitivity; never below it), as B-4/tier_c.py prices it
    TAU_PROBE_CENSORED = {}
    if SW["TAU_CENSOR"] == "all":
        for k_ in sorted(tau):
            st_, v_ = tau[k_]
            if st_ in ("measured", "bound") and np.isfinite(v_) and v_ > LAG_MIN and any(x <= LAG_MIN for x in tau_probe_meas.get(k_, [])) and k_[0] in has_pilot:
                g_ = unmeasured_G(k_[0]) * TF; pr_ = max(TAU_LB.get(k_, g_), g_)
                TAU_PROBE_CENSORED[k_] = dict(probe=min(tau_probe_meas[k_]), least_before=tau_least[k_], priced=pr_, bound=k_ in TAU_LB)
                tau_least[k_] = pr_
    for ch in sorted({r for r in PILOT}):
        if ch not in lam_dep: continue
        S = 10 ** (-sup.get(ch, 0.0) / 10); ld = lam_excl[ch]; ln = lam_none.get(ch, np.nan)
        GCAP = gain(CAP, ch)   # item 5: the stated keep reads G at the cap, in item 4's gain (CAP / TF under GAIN=zero)
        per = {}
        for rng, classes in RANGES.items():
            t, tstat, tnote = range_gain(ch, rng); G = gain(t, ch) if np.isfinite(t) else np.nan
            tL, _, _ = range_gain(ch, rng, least=True); GL = gain(tL, ch) if np.isfinite(tL) else np.nan
            probe_db = db(GL / G) if (np.isfinite(G) and np.isfinite(GL) and G > 0) else 0.0
            rh = range_rho(ch, rng); credit = ground_credit(rh) if SW["GROUND_CREDIT"] == "on" else 1.0   # item 17: no ground credit under off; r5.2: its form
            cdb = (-db(credit) if credit > 0 else np.nan) if SW["GROUND_CREDIT"] == "on" else 0.0
            pols = {}; excluded = {}
            for pol in POLICIES:
                eps = kept(ch, pol) if has_pilot[ch] else (list(SCIENCE) if pol == "keep_all" else [])
                if not eps:
                    # item 6: a policy that keeps no dump is not a way to save the channel: listed and excluded
                    excluded[pol] = "keeps no dump" if has_pilot[ch] else "not evaluable, no pilot bin"
                    continue
                readings = [class_reading(ch, eps, c) for c in classes]; readings = [x for x in readings if x]
                measured = [x for x in readings if x["measured"]]
                if not readings: continue
                A_net = float(np.median([x["A_net"] for x in measured])) if measured else np.nan
                # amendment 14: the published gate is a threshold on A_net, which is already net of the
                # floor mean, so it is NSIG scatters and not the floor mean plus NSIG scatters; and a range
                # is detected when ANY class clears, so the binding threshold is the least class's.
                floor_level = float(min(x["gate"] for x in readings))
                pols[pol] = dict(A_net=A_net, measured=bool(measured), n_measured=len(measured), floor_level=floor_level,
                                 R_dep=(A_net * S * credit * G / ld) if (measured and np.isfinite(G)) else np.nan,
                                 R_none=(A_net * G / ln) if (measured and np.isfinite(G) and np.isfinite(ln)) else np.nan,
                                 R_dep_G1=(A_net * S * credit / ld) if measured else np.nan,
                                 R_floor=(floor_level * S * credit * G / ld) if np.isfinite(G) else np.nan,
                                 R_dep_Gdump=(A_net * S * credit / ld) if measured else np.nan, kept=eps,
                                 R_keep_stated=(A_net * GCAP / ln) if (measured and np.isfinite(ln)) else np.nan)
            # lowest-epoch bound for channels without a pilot bin (all fourteen epochs, keep-all)
            low = None
            if not has_pilot[ch]:
                eps14 = sorted({e for (c_, e, cc, p) in ex if c_ == ch})
                vals = []
                at_floor_epoch = None
                for e in eps14:
                    rd_all = [class_reading(ch, [e], c, POL_OF_CLASS.get((ch, c))) for c in classes]; rd = [x for x in rd_all if x and x["measured"]]
                    if rd: vals.append((float(np.median([x["A_net"] for x in rd])), e))
                    elif any(rd_all): at_floor_epoch = e                        # amendment 9 item 2: an epoch at the floor is the minimum
                if at_floor_epoch is not None: low = dict(A=np.nan, epoch=at_floor_epoch, R_dep=np.nan, R_dep_G1=np.nan, at_floor=True)
                elif vals and SW["UNMEASURED_TAU"] == "current":
                    a, e = min(vals); Gl = G
                    low = dict(A=a, epoch=e, R_dep=(a * S * credit * Gl / ld) if np.isfinite(G) else np.nan, R_dep_G1=a * S * credit / ld, at_floor=False, G=Gl)
                elif vals:
                    # item 3: each epoch's unmeasured tau is priced at the admissible minimum of that epoch's own frame count, so G
                    # depends on the epoch and the lowest-epoch bound is the least R over the epochs (and, for the probe, the least
                    # R at the least trim probe), not the R of the least A. At G = 1, every epoch alike, the least is the least A's.
                    per_e = []
                    for a_, e_ in vals:
                        t_, st_, _ = range_gain(ch, rng, False, U.NFRAMES[e_]); Ge = gain(t_, ch) if np.isfinite(t_) else G
                        tq_, _, _ = range_gain(ch, rng, True, U.NFRAMES[e_]); GLe = gain(tq_, ch) if np.isfinite(tq_) else Ge
                        per_e.append(dict(epoch=e_, n_frames=U.NFRAMES[e_], A=a_, tau=t_, tau_least=tq_, G=Ge, G_least=GLe, tstat=st_, R_dep=a_ * S * credit * Ge / ld, R_least=a_ * S * credit * GLe / ld))
                    b = min(per_e, key=lambda x: x["R_dep"])
                    low = dict(A=b["A"], epoch=b["epoch"], R_dep=b["R_dep"] if np.isfinite(G) else np.nan, R_dep_G1=min(vals)[0] * S * credit / ld,
                               R_bar_G1=b["A"] * S * credit / ld, at_floor=False, tau=b["tau"], tau_least=b["tau_least"], G=b["G"], tstat=b["tstat"], probe_db=db(min(x["R_least"] for x in per_e)) - db(b["R_dep"]), epochs=per_e)
            per[rng] = dict(tau=t, tstat=tstat, tnote=tnote, G=G, tau_least=tL, G_least=GL, probe_db=probe_db, rho=rh, credit_db=cdb, pols=pols, low=low, excluded=excluded, blockers=[], bar=np.nan, G_bar=np.nan, R1=np.nan, basis="")
            # verdict on the range
            cand = [(p, d) for p, d in pols.items() if d["measured"] and np.isfinite(d["R_dep"])]
            anymeas = any(d["measured"] for d in pols.values())
            if not pols: v = ("undetermined", "no reading")
            elif not anymeas:
                fr = pols["keep_all"]["R_floor"] if "keep_all" in pols else np.nan
                v = ("at floor", f"not measured above the control floor (the detection gate is {db(fr):.1f} dB over tolerance at G {G:.0f})" if np.isfinite(fr) else "not measured above the control floor (gain unmeasured)")
                if np.isfinite(fr): per[rng]["vbar"] = db(fr)
            elif tstat == "unmeasured":
                # amendment 15: where a range has no measured and no bound class, its own trim probes may
                # establish that the channel CANNOT be excised, never that it can. Price at the greatest
                # probe the estimator admits, the least favourable reading for the channel; if the bar is
                # inside the allowance even there, no coherence time the estimator admits can excise it.
                # If it is outside, nothing is concluded, because excising on a gain the estimator refused
                # to measure is what amendment 12 item 8 forbids.
                pv = [v for c_ in gain_classes(ch, rng) for v in tau_probe_meas.get((ch, c_), [])]
                if pv:
                    gmax = gain(max(pv), ch)
                    worst = min(d["R_dep_G1"] for p, d in pols.items() if d["measured"]) * gmax
                    if within(db(worst)):
                        v = ("not excisable", f"{db(worst):.1f} dB over tolerance at the greatest trim probe the estimator admits ({max(pv):.0f} s, G {gmax:.0f}), inside the {ATXT}, so no coherence time the estimator admits can excise it (amendment 15)")
                        per[rng] = dict(tau=t, tstat=tstat, tnote=tnote, G=G, tau_least=tL, G_least=GL, probe_db=probe_db, rho=rh,
                                        credit_db=cdb, pols=pols, low=low, verdict=v, excluded=excluded, blockers=[], bar=np.nan, G_bar=np.nan, R1=np.nan, basis="", vbar=db(worst))
                        continue
                best_G1 = min(d["R_dep_G1"] for p, d in pols.items() if d["measured"])
                v = ("unpriced", f"measured above the floor but the gain is unmeasured: {db(best_G1):.1f} dB at {G1T}, {db(best_G1 * 3600 / TF):.1f} dB at the persistence bound; {tnote}")
            else:
                if not has_pilot[ch] and low is not None and low.get("at_floor"):
                    v = ("at floor", f"the lowest epoch ({low['epoch']}) is not measured above the control floor on any class of the range, so the bound is at the floor and cannot excise (amendment 9)")
                elif not has_pilot[ch] and low is not None and np.isfinite(low["R_dep"]):
                    bar = db(low["R_dep"]); pbest = "lowest-epoch bound"; pdb = low.get("probe_db", probe_db); tst = low.get("tstat", tstat)
                    # r2: the bar carries its own reading (tau, least tau, status) beside G_bar, so a printed G is never paired with the
                    # status of another frame count (the range reading prices a refused class at the shortest dump, 4 frames; the
                    # lowest epoch at its own, e.g. 33 frames and G 21.06 on channel 31)
                    per[rng].update(bar=bar, G_bar=low.get("G", G), R1=low["R_dep_G1"], R1_bar=low.get("R_bar_G1", low["R_dep_G1"]), probe_bar=pdb, tstat_bar=tst,
                                    tau_bar=low.get("tau", t), tau_least_bar=low.get("tau_least", tL), basis=f"lowest epoch {low['epoch']}")
                    if exceeds(bar) and exceeds(bar + pdb): v = ("excise", f"{bar:.1f} dB over tolerance on the lowest epoch ({low['epoch']}) with {CREDITS} at G {low.get('G', G):.0f} ({tst}), {bar + pdb:.1f} dB at the least trim probe; no policy can pass; {db(low['R_dep_G1']):.1f} dB at {G1T}; rescued only by a ground filter reaching coherence {rescue_rho(bar, rh):.4f} against the measured {rh:.2f}")
                    elif exceeds(bar): v = ("marginal", f"{bar:.1f} dB over tolerance on the lowest epoch ({low['epoch']}) but {bar + pdb:.1f} dB at the least trim probe, inside the {ATXT} (amendment 10 item 7)")
                    else: v = ("undetermined", f"lowest-epoch bound {bar:.1f} dB, within the allowance; mask not evaluable")
                    if v[0] in ("excise", "marginal"): per[rng]["vbar"] = bar
                elif cand:
                    pbest, dbest = min(cand, key=lambda x: x[1]["R_dep"]); bar = db(dbest["R_dep"])
                    per[rng].update(bar=bar, G_bar=G, R1=dbest["R_dep_G1"], R1_bar=dbest["R_dep_G1"], probe_bar=probe_db, tstat_bar=tstat, tau_bar=t, tau_least_bar=tL, basis=f"policy {pbest}")
                    if SW["KEEP"] == "coded":
                        loosest = next((p for p in reversed(POLICIES) if p in pols and pols[p]["measured"] and np.isfinite(pols[p]["R_dep"]) and pols[p]["R_dep"] <= 1), None)
                    else:   # item 5: a keep needs no credits, lambda_none and G at the cap
                        loosest = next((p for p in reversed(POLICIES) if p in pols and pols[p]["measured"] and np.isfinite(pols[p]["R_keep_stated"]) and pols[p]["R_keep_stated"] <= 1), None)
                    ka_meas = "keep_all" in pols and pols["keep_all"]["measured"]
                    blockers = U.every_policy_blockers(pols, POLICIES) if SW["EVERY_POLICY"] == "thesis" else []
                    per[rng]["blockers"] = blockers
                    if loosest and SW["KEEP"] == "coded": v = ("keep", f"{loosest} passes ({db(pols[loosest]['R_dep']):.1f} dB) with {CREDITS} at G {G:.0f} ({tstat})")
                    elif loosest: v = ("keep", f"{loosest} passes ({db(pols[loosest]['R_keep_stated']):.1f} dB) with no credit, lambda_none and G at the cap (amendment 18 item 5)")
                    elif not ka_meas:
                        fr = pols["keep_all"]["R_floor"] if "keep_all" in pols else np.nan
                        v = ("at floor", f"keep-all is not measured above the control floor (the detection gate is {db(fr):.1f} dB over tolerance at G {G:.0f}); the calibrated policies read {bar:.1f} dB over on their kept dumps")
                        per[rng]["vbar"] = db(fr)
                    elif blockers:
                        # item 6: a policy at the floor on the range may pass, which is its most favorable value
                        btxt = ", ".join(f"{p} (keeps {len(pols[p]['kept'])} of 4 dumps)" for p in blockers)
                        v = ("policy at floor", f"{btxt} not measured above the control floor; at its most favorable value it passes, so it blocks the excision (amendment 18 item 6); the measured policies read {bar:.1f} dB over tolerance (least: {pbest}) at G {G:.0f} ({tstat})")
                    elif exceeds(bar) and exceeds(bar + probe_db): v = ("excise", f"{bar:.1f} dB over tolerance under every policy (least: {pbest}) with {CREDITS} at G {G:.0f} ({tstat}), {bar + probe_db:.1f} dB at the least trim probe; {db(dbest['R_dep_G1']):.1f} dB at {G1T}; rescued only by a ground filter reaching coherence {rescue_rho(bar, rh):.4f} against the measured {rh:.2f}")
                    elif exceeds(bar): v = ("marginal", f"{bar:.1f} dB over tolerance ({pbest}) at G {G:.0f} ({tstat}) but {bar + probe_db:.1f} dB at the least trim probe, inside the {ATXT} (amendment 10 item 7)")
                    else: v = ("marginal", f"{bar:.1f} dB over tolerance ({pbest}), within the {ATXT}, at G {G:.0f} ({tstat})")
                    if v[0] in ("policy at floor", "excise", "marginal"): per[rng]["vbar"] = bar
                else: v = ("undetermined", "measured on no evaluable policy")
            per[rng]["verdict"] = v
        results[ch] = per
    # summary verdict per channel
    summary = {}
    for ch, per in results.items():
        L, Sh, W = per["bao_long"]["verdict"], per["bao_short"]["verdict"], per["shortest"]["verdict"]
        def bartxt(v): m = re.search(r"([-\d.]+) dB over tolerance", v[1]); return m.group(1) if m else ""
        # the bar at G = 1 in the reason, read out of the f-strings below (Python 3.10 takes no backslash in an f-string expression)
        def g1txt(v): m = re.search(r'([-\d.]+) dB at ' + re.escape(G1T), v[1]); return m.group(1) if m else ''
        keep_short = Sh[0] in ("keep", "at floor") if SW["KEEP"] == "coded" else Sh[0] == "keep"   # item 5: no at-floor range accepted
        if L[0] == "excise":
            disp, reason = "excise", f"excised on {RANGE_TEXT['bao_long']}: {L[1]}; on the short BAO baselines: {Sh[0]} ({Sh[1]}); worst case on the 0.3 m baseline: {W[0]} ({W[1]}); subtraction bar {bartxt(L)} dB, {g1txt(L)} dB even at {G1T if SW['G1_NAMES'] == 'literal' else 'G=1'}"
        elif Sh[0] == "excise":
            disp, reason = "excise", f"excised on {RANGE_TEXT['bao_short']}: {Sh[1]}; on the long BAO baselines: {L[0]} ({L[1]}); worst case on the 0.3 m baseline: {W[0]} ({W[1]}); subtraction bar {bartxt(Sh)} dB, {g1txt(Sh)} dB even at {G1T if SW['G1_NAMES'] == 'literal' else 'G=1'}"
        elif L[0] == "keep" and keep_short:
            disp, reason = "keep", f"keeps on the BAO baselines: long, {L[1]}; short, {Sh[0]} ({Sh[1]}); worst case on the 0.3 m baseline: {W[0]} ({W[1]})"
        elif L[0] == "policy at floor" or Sh[0] == "policy at floor":
            disp, reason = "undetermined", f"a policy that keeps dumps is at the control floor, so no excision (amendment 18 item 6): long BAO baselines, {L[0]} ({L[1]}); short BAO baselines, {Sh[0]} ({Sh[1]}); worst case on the 0.3 m baseline: {W[0]} ({W[1]})"
        elif L[0] == "unpriced" or Sh[0] == "unpriced":
            disp, reason = "undetermined", f"measured above the floor but unpriced: long BAO baselines, {L[0]} ({L[1]}); short BAO baselines, {Sh[0]} ({Sh[1]}); worst case on the 0.3 m baseline: {W[0]} ({W[1]})"
        elif L[0] == "marginal" or Sh[0] == "marginal":
            disp, reason = "undetermined", f"marginal: long BAO baselines, {L[0]} ({L[1]}); short BAO baselines, {Sh[0]} ({Sh[1]}); worst case on the 0.3 m baseline: {W[0]} ({W[1]})"
        else:
            disp, reason = "undetermined", f"at the control floor on the BAO baselines: long, {L[1]}; short, {Sh[0]} ({Sh[1]}); worst case on the 0.3 m baseline: {W[0]} ({W[1]})"
        summary[ch] = (disp, reason)
    # write: keep the input columns, replace disposition and reason for data rows, append range columns
    newcols = []
    for rng in RANGES: newcols += [f"{rng}_A_net", f"{rng}_measured", f"{rng}_floor_level", f"{rng}_tau_s", f"{rng}_tau_status", f"{rng}_tau_least_s", f"{rng}_probe_db", f"{rng}_rescue_rho", f"{rng}_gate_db", f"{rng}_G", f"{rng}_rho", f"{rng}_ground_credit_db", f"{rng}_{RCOL}", f"{rng}_R_none", f"{rng}_verdict"]
    fields = list(rows_in[0].keys()) + newcols
    with open(outp, "w") as fh:
        w = csv.DictWriter(fh, fieldnames=fields); w.writeheader()
        for r in rows_in:
            ch = int(r["channel"]); o = dict(r)
            if r["role"] != "pilot" and ch in summary and r["policy_or_reason"] != "no products":
                o["disposition"], o["policy_or_reason"] = summary[ch]
                if has_pilot.get(ch):
                    o["kept_dumps_cal_q0.5"] = " ".join(SCIENCE[e] for e in kept(ch, "cal_q0.5")); o["kept_dumps_cal_q0.9"] = " ".join(SCIENCE[e] for e in kept(ch, "cal_q0.9"))
                if ch == 37: o["disposition"], o["policy_or_reason"] = "undetermined", "reference channel (no DTV allocation): the control whose reading defines the floor; no tolerance on the board"
            for rng in RANGES:
                p = results.get(ch, {}).get(rng)
                if not p: continue
                ka = p["pols"].get("keep_all", {})
                o[f"{rng}_A_net"] = f"{ka.get('A_net', np.nan):.3e}" if ka and np.isfinite(ka.get("A_net", np.nan)) else ""
                o[f"{rng}_measured"] = str(ka.get("measured", "")) if ka else ""
                o[f"{rng}_floor_level"] = f"{ka.get('floor_level', np.nan):.3e}" if ka and np.isfinite(ka.get("floor_level", np.nan)) else ""
                o[f"{rng}_tau_s"] = f"{p['tau']:.0f}" if np.isfinite(p["tau"]) else ""; o[f"{rng}_tau_status"] = p["tstat"]
                o[f"{rng}_tau_least_s"] = f"{p['tau_least']:.0f}" if np.isfinite(p["tau_least"]) else ""; o[f"{rng}_probe_db"] = f"{p['probe_db']:+.1f}"
                o[f"{rng}_G"] = f"{p['G']:.0f}" if np.isfinite(p["G"]) else ""; o[f"{rng}_rho"] = f"{p['rho']:.2f}"; o[f"{rng}_ground_credit_db"] = f"{p['credit_db']:.1f}" if np.isfinite(p["credit_db"]) else ""
                o[f"{rng}_{RCOL}"] = f"{ka.get('R_dep', np.nan):.4g}" if ka and np.isfinite(ka.get("R_dep", np.nan)) else ""
                o[f"{rng}_R_none"] = f"{ka.get('R_none', np.nan):.4g}" if ka and np.isfinite(ka.get("R_none", np.nan)) else ""
                o[f"{rng}_verdict"] = p["verdict"][0]
                gr = ka.get("R_floor", np.nan) if ka else np.nan
                o[f"{rng}_gate_db"] = f"{db(gr):.1f}" if np.isfinite(gr) else ""
                mb = re.search(r"([-\d.]+) dB over tolerance", p["verdict"][1])
                if SW["THRESHOLDS"] == "on":   # item 8: from the unrounded bar
                    vb = p.get("vbar", np.nan)
                    assert (mb is None) == (not np.isfinite(vb)) and (mb is None or f"{vb:.1f}" == mb.group(1)), (ch, rng, p["verdict"], vb)
                    rr = rescue_rho(vb, p["rho"]) if mb else np.nan
                else:
                    rr = rescue_rho(float(mb.group(1)), p["rho"]) if mb else np.nan
                o[f"{rng}_rescue_rho"] = f"{rr:.4f}" if np.isfinite(rr) else ""
            w.writerow(o)
    print("ch  summary        | shortest              | short BAO              | long BAO")
    for ch in sorted(results):
        per = results[ch]
        print(f"{ch:2d}  {summary[ch][0]:13s} | " + " | ".join(f"{per[r]['verdict'][0]:10s} {db(per[r]['pols'].get('keep_all', {}).get('R_dep', np.nan)):+6.1f}dB G{per[r]['G']:.0f} r{per[r]['rho']:.2f}" if np.isfinite(per[r]['G']) else f"{per[r]['verdict'][0]:10s}   n/a" for r in RANGES))

    # ---- item 8: thresholds from unrounded R with the code's own test
    NOT_EXCISABLE = "not excisable at any τ"; EXCISED_ANY = "excised at any τ"
    def threshold(ch, rng):
        """The least coherence time at which the range is excised, holding every other reading fixed. R is linear in G, so
        the code's test (R > 10^0.3 at the value and at the least trim probe) holds exactly when the lesser of the two
        readings, the least trim probe, exceeds the returned time. None with a reason where there is no excise path."""
        p = results[ch][rng]; v = p["verdict"][0]
        if v in ("at floor", "undetermined", "not excisable"): return None, f"{v}: {p['verdict'][1]}"
        if v == "policy at floor": return None, f"a policy at the control floor blocks the excision at any coherence time (item 6): {', '.join(p['blockers'])}"
        if v == "keep": return None, "kept under the stated rule"
        R1 = p["R1"]
        if v == "unpriced" or not np.isfinite(R1):
            R1 = min(d["R_dep_G1"] for d in p["pols"].values() if d["measured"])
        if R1 > U.ALLOW_R:   # G cannot fall below one frame (challenge/x3: G = max(tau / T_frame, 1)), so no tau can bring R inside
            return None, f"{EXCISED_ANY}: R at {G1T} is {db(R1):+.2f} dB, over the {ATXT}, and G cannot fall below one frame"
        G_need = U.ALLOW_R / R1
        t = U.invert_gain(G_need, lambda x: gain(x, ch))
        # the code's test is strict (R > 10^0.3): step to the next representable time above the crossing
        while t is not None and not (R1 * gain(t, ch) > U.ALLOW_R): t = np.nextafter(t, np.inf)
        if t is None or t > CAP: return None, f"R at the sidereal cap is {db(R1 * gain(CAP, ch)):.2f} dB, inside the {ATXT}"
        return t, ""

    if JSON_OUT or THR_OUT:
        thr = {}
        if SW["THRESHOLDS"] == "on":
            for ch in results:
                if ch == 37: continue
                for rng in ("bao_short", "bao_long"): thr[(ch, rng)] = threshold(ch, rng)
        if THR_OUT:
            assert SW["THRESHOLDS"] == "on"
            with open(THR_OUT, "w", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(["channel", "range", "verdict_a18", "tau_s", "tau_status", "tau_least_s", "G_of_bar", "R_at_G1", "tau_threshold_s", "G_threshold", "threshold_text", "verdict_reproduced", "threshold_brackets"])
                for ch in sorted(results):
                    if ch == 37: continue
                    chan_t = []; chan_any = []
                    for rng in ("bao_short", "bao_long"):
                        p = results[ch][rng]; t, why = thr[(ch, rng)]; R1 = p["R1"]
                        # checks: the code's own test on R1 reproduces the verdict, and the threshold brackets the crossing
                        rep = ""
                        if p["verdict"][0] in ("excise", "marginal") and np.isfinite(R1) and np.isfinite(p["G_bar"]):
                            bar = db(p.get("R1_bar", R1) * p["G_bar"]); rep = str((exceeds(bar) and exceeds(bar + p.get("probe_bar", p["probe_db"]))) == (p["verdict"][0] == "excise"))
                        brk = str(R1 * gain(t, ch) > U.ALLOW_R and not (R1 * gain(t * (1 - 1e-9), ch) > U.ALLOW_R)) if t is not None else ""
                        if t is not None: chan_t.append(t)
                        if why.startswith(EXCISED_ANY): chan_any.append(rng)
                        txt = (f"excised when the least coherence-time reading of the range exceeds {t:.6g} s" if t is not None else (why if why.startswith(EXCISED_ANY) else f"{NOT_EXCISABLE} ({why})"))
                        tb, tlb = p.get("tau_bar", p["tau"]), p.get("tau_least_bar", p["tau_least"])   # r2: the reading of the bar, beside G_of_bar
                        w.writerow([ch, rng, p["verdict"][0], f"{tb:.6g}" if np.isfinite(tb) else "", p.get("tstat_bar", p["tstat"]), f"{tlb:.6g}" if np.isfinite(tlb) else "",
                                    f"{p['G_bar']:.6g}" if np.isfinite(p["G_bar"]) else "", f"{R1:.6g}" if np.isfinite(R1) else "", f"{t:.6g}" if t is not None else "",
                                    f"{gain(t, ch):.6g}" if t is not None else ("1" if why.startswith(EXCISED_ANY) else ""), txt, rep, brk])
                    w.writerow([ch, "channel", summary[ch][0], "", "", "", "", "", f"{min(chan_t):.6g}" if (chan_t and not chan_any) else "", "",
                                (f"{EXCISED_ANY} (R over the allowance at {G1T} on {' and '.join(chan_any)})" if chan_any else
                                 f"excised when either BAO range's least coherence-time reading exceeds its threshold; the lesser is {min(chan_t):.6g} s" if chan_t else NOT_EXCISABLE), "", ""])
        if JSON_OUT:
            def clean(x):
                if isinstance(x, dict): return {str(k): clean(v) for k, v in x.items()}
                if isinstance(x, (list, tuple)): return [clean(v) for v in x]
                if isinstance(x, (float, np.floating)): return None if not np.isfinite(x) else float(x)
                if isinstance(x, (np.integer,)): return int(x)
                if isinstance(x, (np.bool_,)): return bool(x)
                return x
            # the 200 ns world writes the revision 2 json unchanged (no WORLD key); the no-filter world adds its world, the
            # exclusion-side tolerance and the bin fill. Under WORLD=none, S and every R_dep, R_floor and R_dep_G1 are the
            # exclusion side's: S is the bin fill alone (no delay filter), and the tolerance is lam_exclusion (lambda_none)
            # r4: likewise GROUND_CREDIT=on writes no key, so revisions 2 and 3 are reproduced unchanged
            # r5: likewise TAU_LOWER_BOUNDS=off writes no key, so revision 4 is reproduced unchanged
            sw = {k: v for k, v in SW.items() if not (k == "WORLD" and v == "200ns") and not (k == "GROUND_CREDIT" and v == "on") and not (k == "TAU_LOWER_BOUNDS" and v == "off")
                  and not (k == "TAU_CENSOR" and v == "off") and not (k in R5_VALUES and k != "TAU_CENSOR" and v == R5_VALUES[k])}
            if SW["SWITCH_RECORD"] == "all": sw = dict(SW)   # r5.1 (triage row 35): every switch, the credit readings' included
            sw = {k: v for k, v in sw.items() if not (k in R51_VALUES and v == R51_VALUES[k])}   # r5.2: the r5.1 credit values write no key, so r5 and r5.1 are reproduced
            out = dict(switches=sw, summary={ch: list(s) for ch, s in summary.items()}, has_pilot=has_pilot, results=results,
                       S={ch: 10 ** (-sup.get(ch, 0.0) / 10) for ch in results}, lam_dep=lam_dep, lam_none=lam_none,
                       thresholds={f"{ch}|{rng}": [t, why] for (ch, rng), (t, why) in thr.items()},
                       admissible_min_G={n: U.admissible_min_G(n) for n in (4, 11, 33)} if SW["UNMEASURED_TAU"] != "current" else {})
            if SW["WORLD"] != "200ns": out.update(world=SW["WORLD"], lam_exclusion=lam_excl, fill={ch: fill[ch] for ch in results if ch in fill})
            if SW["TAU_LOWER_BOUNDS"] == "on":   # item 35: every bound read, and those that priced a class
                out.update(tau_lower_bounds={f"{c}|{CLS_NAME[k]}": dict(priced=v, bound=_LB[(c, k)]["lb"], least_variant=_LB[(c, k)]["least_variant"],
                                                                         span=_LB[(c, k)]["span"]) for (c, k), v in sorted(TAU_LB.items())},
                           tau_lower_bounds_used=sorted(f"{c}|{CLS_NAME[k]}" for (c, k) in LB_USED))
            if SW["TAU_CENSOR"] != "off": out.update(tau_censored={f"{c}|{CLS_NAME[k]}": v for (c, k), v in sorted(TAU_CENSORED.items())})
            if SW["TAU_CENSOR"] == "all": out.update(tau_probe_censored={f"{c}|{CLS_NAME[k]}": v for (c, k), v in sorted(TAU_PROBE_CENSORED.items())})
            if SW["BOUND_CALIBRATION"] == "on":
                out.update(tau_lower_bounds_calibration={f"{c}|{CLS_NAME[k]}": v["calibration"] for (c, k), v in sorted(_LB.items())})
            with open(JSON_OUT, "w") as fh: json.dump(clean(out), fh, indent=1)
    return 0
