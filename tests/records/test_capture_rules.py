"""The capture ruling's rules on the golden handoff (the release producer's tests of the RFIsher side).

Ported from the r5.2 producer's tests/test_a18.py: each test reads the rulings the rule files give on the golden
capture handoff, in place of the frozen trees the producer's tests read. The frozen releases themselves are pinned by
sha in test_capture_identity.py.
"""
from __future__ import annotations

import csv
import json
import re

import numpy as np
import pytest

from capture_golden import quiet
from rfisher.records.chime_atsc_2026 import capture_ruling
from rfisher.records.chime_atsc_2026 import capture_units as U

ANY = "excised at any τ"


@pytest.fixture(scope="module")
def rulings(capture_handoff_dir, tmp_path_factory):
    """{name: (a18.json, thresholds rows, full rows)} for the rulings the tests read."""
    out = tmp_path_factory.mktemp("rulings")
    table = capture_handoff_dir / "frame_analysis" / "table_of_record_before_amendment8.csv"
    runs = {"r5_2": ["--rule", "r5_2"], "r5_1": ["--rule", "r5_1"], "r5": ["--rule", "r5"],
            "coded_policy": ["--rule", "r5_2", "--set", "EVERY_POLICY=coded"],
            "r4": ["--rule", "a18", "--set", "TAU_LOWER_BOUNDS=off"],
            "r3": ["--rule", "a18", "--set", "TAU_LOWER_BOUNDS=off", "--sensitivity", "r3"],
            "r2": ["--rule", "a18", "--set", "TAU_LOWER_BOUNDS=off", "--sensitivity", "r2"],
            "r5_2_r3": ["--rule", "r5_2", "--sensitivity", "r3"]}
    got = {}
    for name, args in runs.items():
        quiet(capture_ruling.main, [*args, "--json", str(out / f"{name}.json"), "--thresholds", str(out / f"{name}.csv"),
                                    "--input", str(table), "--handoff", str(capture_handoff_dir),
                                    "--out", str(out / f"{name}_full.csv"), "--ch33-rescan"])
        with open(out / f"{name}.csv", newline="") as fh:
            thr = list(csv.DictReader(fh))
        with open(out / f"{name}_full.csv", newline="") as fh:
            full = list(csv.DictReader(fh))
        got[name] = (json.loads((out / f"{name}.json").read_text()), thr, full)
    return got


def test_the_rule_files_resolve_to_the_releases_switch_sets():
    identity, a18, r51, r52 = capture_ruling.switch_sets()
    assert set(identity) == set(capture_ruling.CHOICES) and identity["UNITS"] == "booked"
    assert capture_ruling.resolve("r5") == capture_ruling.resolve("a18") == {**identity, **a18}
    assert capture_ruling.resolve("r5_2") == {**identity, **a18, **r51, **r52}
    assert r52 == {"CREDIT_FORM": "one_minus_gamma", "CREDIT_GAMMA": "reconciled"}
    for name in ("g1", "r3", "r2"):
        assert capture_ruling.rule_file(name, sensitivity=True)["switches"]
    with pytest.raises(capture_ruling.RuleError):
        capture_ruling.rule_file("r6")


def test_every_policy_rule():
    """An at-floor policy that keeps a dump blocks; a policy absent from pols (no dump) never blocks."""
    order = ["cal_q0.1", "cal_q0.5", "cal_q0.9", "keep_all"]
    assert U.every_policy_blockers({"cal_q0.9": dict(measured=False), "keep_all": dict(measured=True)}, order) == ["cal_q0.9"]
    assert U.every_policy_blockers({"cal_q0.5": dict(measured=True), "keep_all": dict(measured=True)}, order) == []
    assert U.every_policy_blockers({}, order) == []


def test_every_policy_on_the_ruling(rulings):
    """Channel 22's long range has cal_q0.9 at the floor, which blocks it; with item 6 at its identity value only 22
    moves (to excise). No-dump policies are listed and excluded and do not block."""
    d = rulings["r5_2"][0]; e = rulings["coded_policy"][0]; L = d["results"]["22"]["bao_long"]
    assert L["verdict"][0] == "policy at floor" and L["blockers"] == ["cal_q0.9"] and d["summary"]["22"][0] == "undetermined"
    assert e["summary"]["22"][0] == "excise" and e["results"]["22"]["bao_long"]["verdict"][0] == "excise"
    assert sorted(int(c) for c in d["summary"] if d["summary"][c][0] != e["summary"][c][0]) == [22]
    pilot = [int(c) for c, h in d["has_pilot"].items() if h and c in d["results"]]
    for c in pilot:
        for rng in ("bao_short", "bao_long"):
            ex_ = d["results"][str(c)][rng]["excluded"]
            assert ex_.get("cal_q0.1") == "keeps no dump" and "cal_q0.1" not in d["results"][str(c)][rng]["pols"]
    q5 = sorted(c for c in pilot if d["results"][str(c)]["bao_long"]["excluded"].get("cal_q0.5") == "keeps no dump")
    assert q5 == [23, 25, 33, 35]
    assert d["summary"]["33"][0] == d["summary"]["35"][0] == "excise"


def test_thresholds(rulings):
    d, thr, _ = rulings["r5_2"]
    ch = {r["channel"]: r for r in thr if r["range"] == "channel"}
    for c in ("19", "28"):
        assert ch[c]["threshold_text"] == "not excisable at any τ"
    anyr = [r for r in thr if r["range"] != "channel" and r["threshold_text"].startswith(ANY)]
    exc = [c for c, s in d["summary"].items() if s[0] == "excise"]
    assert all(ch[c]["tau_threshold_s"] or ch[c]["threshold_text"].startswith(ANY) for c in exc)
    for r in anyr:
        assert d["results"][r["channel"]][r["range"]]["R1"] > U.ALLOW_R and not r["tau_threshold_s"]
    rows = [r for r in thr if r["range"] != "channel" and r["tau_threshold_s"]]
    assert rows and all(r["threshold_brackets"] == "True" for r in rows)
    assert all(float(r["G_threshold"]) > 1 and float(r["tau_threshold_s"]) > U.TF for r in rows)
    assert all(r["verdict_reproduced"] == "True" for r in thr if r["verdict_reproduced"])
    for r in rows:   # from the unrounded R, with the code's own strict test
        t = float(r["tau_threshold_s"]); c = int(r["channel"]); R1 = d["results"][r["channel"]][r["range"]]["R1"]
        assert R1 * U.gain_bao(t * (1 + 1e-5), c) > U.ALLOW_R and not (R1 * U.gain_bao(t * (1 - 1e-5), c) > U.ALLOW_R)


def test_lowest_epoch(rulings):
    """Where G depends on the epoch's frame count, the lowest-epoch bound is the least R over the epochs."""
    d = rulings["r5_2"][0]; n = 0
    for c, per in d["results"].items():
        for rng in ("bao_short", "bao_long"):
            p = per[rng]
            if not p["basis"].startswith("lowest epoch"): continue
            L = p["low"]; E = L["epochs"]; b = min(E, key=lambda x: x["R_dep"])
            assert L["epoch"] == b["epoch"] and abs(p["bar"] - 10 * np.log10(b["R_dep"])) < 1e-9
            assert abs(p["bar"] + p["probe_bar"] - 10 * np.log10(min(x["R_least"] for x in E))) < 1e-9
            assert abs(p["R1"] / p["R1_bar"] - min(x["A"] for x in E) / b["A"]) < 1e-12
            n += 1
    assert n


def test_rescue_unrounded(rulings):
    """Every printed rescue coherence is the rule applied to the unrounded bar, in the settled form (1 - rho)."""
    d, _, full = rulings["r5_2"]; n = 0
    assert d["switches"]["GROUND_CREDIT"] == "off" and d["switches"]["CREDIT_FORM"] == "one_minus_gamma"

    def rr(b):
        if b is None or not np.isfinite(b) or b <= 3.0: return None
        rem = (1 - 0.0) * 10 ** ((3.0 - b) / 10)
        return float(1 - rem) if 0 < rem < 1 else None
    for r in full:
        c = r["channel"]
        if r["role"] != "data" or c not in d["results"] or r["policy_or_reason"] != d["summary"][c][1]: continue
        for rng in ("shortest", "bao_short", "bao_long"):
            x = rr(d["results"][c][rng].get("vbar"))
            assert r[f"{rng}_rescue_rho"] == (f"{x:.4f}" if x is not None else ""), (c, rng)
            n += x is not None
    assert n


def test_keep_stated(rulings):
    """The stated keep reads G at the cap in the BAO-band gain; no channel is kept."""
    d = rulings["r5_2"][0]; least = None
    for c, per in d["results"].items():
        for rng, p in per.items():
            for pol, q in p["pols"].items():
                if q["R_keep_stated"] is None: continue
                assert abs(q["R_keep_stated"] / (q["A_net"] * U.gain_bao(U.CAP, int(c)) / d["lam_none"][c]) - 1) < 1e-12
                least = q["R_keep_stated"] if least is None else min(least, q["R_keep_stated"])
    assert least > 1 and not [c for c, s in d["summary"].items() if s[0] == "keep"]


def test_bar_labels(rulings):
    """A bar's G and the tau status printed beside it come from one reading."""
    d, thr, _ = rulings["r5_2"]; thr = {(r["channel"], r["range"]): r for r in thr}; n = 0
    for c, per in d["results"].items():
        for rng in ("bao_short", "bao_long"):
            p = per[rng]
            if p.get("bar") is None or p["verdict"][0] not in ("excise", "marginal", "policy at floor"): continue
            m = re.search(r"refused class(?:es)? at G ([\d.]+)", p["tstat_bar"])
            if p["basis"].startswith("lowest epoch"):
                b = next(x for x in p["low"]["epochs"] if x["epoch"] == p["low"]["epoch"])
                assert p["tstat_bar"] == b["tstat"] and p["G_bar"] == b["G"] and p["tau_bar"] == b["tau"]
                if m: assert m.group(1) == f"{U.admissible_min_G(b['n_frames']):.2f}"
            else:
                assert p["tstat_bar"] == p["tstat"] and p["G_bar"] == p["G"]
            assert f"({p['tstat_bar']})" in p["verdict"][1] or p["verdict"][0] == "policy at floor"
            if (c, rng) in thr: assert thr[(c, rng)]["tau_status"] == p["tstat_bar"]
            n += 1
    assert n


def test_world_switch(rulings):
    """The no-filter exclusion side: lambda_none, no S, the bin fill on the no-filter per-bin tolerances; against the
    200 ns world every R_dep moves by one per-channel factor and the range's own ground credit."""
    d = rulings["r4"][0]; r2 = rulings["r2"][0]
    assert d["world"] == "none" and "WORLD" not in r2["switches"]
    for c, per in d["results"].items():
        ch = int(c); lam = d["lam_exclusion"][c]; f = d["fill"][c]
        assert lam == d["lam_none"][c] and abs(d["S"][c] - f) < 1e-15 and abs(f - U.fill_factor(ch, lam, "none")) < 1e-15
        assert repr(min(U.lam_bin_none()[b] for b in U.bin_overlaps(ch))) == repr(lam)
        k = (d["S"][c] / d["lam_exclusion"][c]) / (r2["S"][c] / r2["lam_dep"][c])
        for rng, p in per.items():
            for pol, q in p["pols"].items():
                if q["R_dep"] is not None:
                    assert abs(q["R_dep"] / (q["A_net"] * f * p["G"] / lam) - 1) < 1e-12
                    assert abs(q["R_dep"] / r2["results"][c][rng]["pols"][pol]["R_dep"] / (k / (1 - p["rho"] ** 2)) - 1) < 1e-12
                if q["R_keep_stated"] is not None:
                    assert q["R_keep_stated"] == r2["results"][c][rng]["pols"][pol]["R_keep_stated"]


def test_ground_switch(rulings):
    """No ground credit on the exclusion side: every exclusion reading is the ground-credit reading divided by the
    range's (1 - rho^2); rho and every keep reading are unchanged."""
    d = rulings["r4"][0]; r3 = rulings["r3"][0]
    assert {k: v for k, v in d["switches"].items() if k != "GROUND_CREDIT"} == r3["switches"]
    for c, per in d["results"].items():
        for rng, p in per.items():
            q3 = r3["results"][c][rng]; cr = 1 - q3["rho"] ** 2
            assert p["rho"] == q3["rho"] and p["credit_db"] == 0.0
            for pol, q in p["pols"].items():
                s = q3["pols"][pol]
                for k in ("R_dep", "R_dep_G1", "R_floor", "R_dep_Gdump"):
                    assert (q[k] is None) == (s[k] is None) and (q[k] is None or abs(q[k] * cr / s[k] - 1) < 1e-12)
                assert q["R_keep_stated"] == s["R_keep_stated"] and q["R_none"] == s["R_none"]


def test_tau_lower_bounds_switch(rulings):
    """With the within-dump bounds on, only ranges with a bound-priced class move, each by the ratio of its G, never
    down; no disposition moves; the keep side and every amplitude are unchanged."""
    d = rulings["r5"][0]; o = rulings["r4"][0]
    assert d["switches"]["TAU_LOWER_BOUNDS"] == "on" and "TAU_LOWER_BOUNDS" not in o["switches"]
    assert [c for c in d["summary"] if d["summary"][c][0] != o["summary"][c][0]] == []
    for c, per in d["results"].items():
        for rng, p in per.items():
            q = o["results"][c][rng]; uses = "within-dump lower bound" in p["tstat"]
            assert p["verdict"][0] == q["verdict"][0]
            if not uses: assert p["tstat"] == q["tstat"] and p["G"] == q["G"]
            else: assert p["G"] >= q["G"] * (1 - 1e-12)
            for pol, x in p["pols"].items():
                y = q["pols"][pol]
                assert x["A_net"] == y["A_net"] and x["R_keep_stated"] == y["R_keep_stated"] and x["R_dep_G1"] == y["R_dep_G1"]
    assert {"14|ns32", "14|ns64", "26|ns32", "27|ns32"} <= set(d["tau_lower_bounds_used"])


def test_r52_credit(rulings):
    """r5.2 changes only the credit readings: the no-credit ruling's R, bars, G, verdicts and dispositions are r5.1's;
    the reconciled range gamma differs from the released one on 15 long, 26 short and 27 short only; and in the
    ground-credit reading every range's credit is -10 log10(1 - gamma) at that gamma."""
    d = rulings["r5_2"][0]; r51 = rulings["r5_1"][0]
    assert d["switches"]["CREDIT_FORM"] == "one_minus_gamma" and d["switches"]["CREDIT_GAMMA"] == "reconciled"
    moved = sorted((c, rng) for c in d["results"] for rng in d["results"][c] if d["results"][c][rng]["rho"] != r51["results"][c][rng]["rho"])
    assert moved == [("15", "bao_long"), ("26", "bao_short"), ("27", "bao_short")], moved
    for c in d["results"]:
        assert d["summary"][c][0] == r51["summary"][c][0], c
        for rng, p in d["results"][c].items():
            q = r51["results"][c][rng]
            assert p["verdict"][0] == q["verdict"][0] and p["bar"] == q["bar"] and p["G_bar"] == q["G_bar"] and p["credit_db"] == q["credit_db"] == 0.0
            for pol, x in p["pols"].items():
                for k in ("R_dep", "R_dep_G1", "R_floor", "R_keep_stated", "R_none"): assert x[k] == q["pols"][pol][k], (c, rng, pol, k)
    a3 = rulings["r5_2_r3"][0]
    assert a3["switches"]["GROUND_CREDIT"] == "on"
    for c, per in d["results"].items():
        for rng, p in per.items():
            g = p["rho"]; cr = 1 - g
            assert a3["results"][c][rng]["rho"] == g and abs(a3["results"][c][rng]["credit_db"] + 10 * np.log10(cr)) < 1e-12, (c, rng)
            for pol, x in p["pols"].items():
                for k in ("R_dep", "R_dep_G1", "R_floor", "R_dep_Gdump"):
                    y3 = a3["results"][c][rng]["pols"][pol][k]
                    assert (x[k] is None) == (y3 is None) and (x[k] is None or abs(x[k] * cr / y3 - 1) < 1e-12), (c, rng, pol, k)
