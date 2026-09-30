"""r5.1: the least-corner statement (triage row 14, work item B-2) and the grounds each excision carries (row 15), written into the
release as promotion_least_corners.csv and PROMOTION_EVIDENCE.md by build_release.py --r51 (here by capture_release). The
evidence directory and revision 5's release are arguments.

The least corners are B-2's declared grid (b_list/B-2/PLAN.md), rerun on the r5.1 readings (b_list/B-2/r51, its PLAN.md declared
before the rerun). This module does not decide the promotion set: it reports which excisions satisfy item 18 as the release codes it
(postprocessing_sensitivity.csv, item18_promotion) and which satisfy it under B-2's admissible grid (every admissible cell excises),
and the evidence beside each. Every number is read from a file named in the text; the checks below tie the grid rerun to this
release's own bars. Read-only on every input.

r5.2 (DECISIONS.md items 39 and 41): write(..., rev="r5.2", r51_rel=<the r5.1 release>) titles the file r5.2, reads the labels from
the settled ground credit ((1 - gamma) at B-1's reconciled gamma), names channel 24's promotion as the author's ruling (item 39), and
moves B-7's both-credit margins by the change of the r2 bar from r5.1 (the credit multiplies R as the bar does). Without them the
output is r5.1's byte for byte."""
import csv, json, math, os

from rfisher.records.chime_atsc_2026 import capture_units as U


def inputs(evid):
    """The evidence files the text reads, under the decision-evidence directory ``evid``."""
    return (os.path.join(evid, "research", "static_mask_by_channel.csv"), os.path.join(evid, "b_list", "B-6", "out", "b6_table.csv"),
            os.path.join(evid, "b_list", "B-7", "out", "variance_reading.csv"), os.path.join(evid, "b_list", "B-8", "ch24_grounds.json"))
PROMOTED_R5 = (17, 24, 30, 31, 33, 35)
EXCISED = (17, 24, 30, 31, 33, 35, 14, 15, 26, 27)
CROSS = ("1,32", "2,32", "3,32", "1,64", "2,64", "3,64")         # between cylinders (B-6's primary classes)
MSG = {17: True, 30: True, 31: True, 35: True, 33: False}          # DECISIONS.md, corrections to item 12 (median-threshold mask)
ALLOW_DB = 10 * math.log10(U.ALLOW_R)
RT = {"bao_short": "short", "bao_long": "long"}


def _f(x):
    return None if x in ("", None, "None") else float(x)


def write(REL, B2R51, EVB, A, C24, rev="r5.1", r51_rel=None, *, evid, r5):
    MASK, B6, B7, B8 = inputs(evid); R5 = r5
    lc = {int(r["channel"]): r for r in csv.DictReader(open(os.path.join(B2R51, "least_corners.csv")))}
    cells = list(csv.DictReader(open(os.path.join(B2R51, "grid_cells.csv"))))
    chk = json.load(open(os.path.join(B2R51, "checks.json")))
    pp = {int(r["channel"]): r for r in csv.DictReader(open(os.path.join(REL, "postprocessing_sensitivity.csv")))}
    dp = {int(r["channel"]): r for r in csv.DictReader(open(os.path.join(REL, "dispositions_a18.csv")))}
    r5d = {int(r["channel"]): r for r in csv.DictReader(open(os.path.join(R5, "dispositions_a18.csv")))}
    mask = {int(r["uhf_channel"]): r for r in csv.DictReader(open(MASK))}
    b6 = [r for r in csv.DictReader(open(B6)) if r["cls"] in CROSS]
    b7 = [r for r in csv.DictReader(open(B7)) if r["credit"] == "both" and r["range"] != "shortest" and r["margin_fourier_db"] not in ("", "nan")]
    A5 = json.load(open(os.path.join(R5, "run", "a18.json")))
    NEW = r51_rel is not None   # r5.2: the settled ground credit
    if NEW:   # the r2 bars of this release and of r5.1, per range (channel 24 from its own credit readings)
        R2N, R2O = (json.load(open(os.path.join(x, "credit_readings", "r2", "run", "a18.json"))) for x in (REL, r51_rel))
        C2N, C2O = (json.load(open(os.path.join(x, "credit_readings", "r2", "run", "ch24_a18.json"))) for x in (REL, r51_rel))
    g24 = json.load(open(B8))
    # ---- checks: the rerun reads this release's rule (rule, I, none, none, 0.7, released is the no-credit bar of each range)
    assert chk["r5_bars_max_abs_diff_db"] < 1e-9 and chk["r2_bars_max_abs_diff_db"] < 1e-3, chk
    for ch in EXCISED:
        c = next(x for x in cells if int(x["channel"]) == ch and (x["G"], x["pol"], x["steady_share"], x["filter"], x["cosdec"], x["lambda_dep"]) == ("rule", "I", "none", "none", "0.7", "released"))
        for rng, k in (("bao_short", "short_bar_db"), ("bao_long", "long_bar_db")):
            if ch == 24: ref = C24["reading"]["ranges"][rng]["bar_db"] if C24["reading"]["ranges"][rng]["verdict"] in ("excise", "marginal") else None
            else:
                p = A["results"][str(ch)][rng]; ref = p["bar"] if p["verdict"][0] in ("excise", "marginal") else None
            got = _f(c[k]); assert (got is None) == (ref is None) and (got is None or abs(got - ref) < 6e-4), (ch, rng, got, ref)
        assert dp[ch]["a18_disposition"] == "excise", ch
    # ---- promotion_least_corners.csv
    rows = []
    for ch in EXCISED:
        L = lc[ch]; P = pp[ch]; adm_ok = int(L["admissible_cells_not_excised"]) == 0
        rows.append(dict(channel=ch, deciding_range=dp[ch]["deciding_range"], deciding_bar_db=dp[ch]["deciding_bar_db"],
                         least_admissible_corner_db=L["least_admissible_value_db"], least_admissible_over_allowance_db=L["least_admissible_over_allowance_db"],
                         least_admissible_cell=L["least_admissible_cell"], admissible_cells=L["admissible_cells"], admissible_cells_not_excised=L["admissible_cells_not_excised"],
                         admissible_not_excised_cleaner_at_floor=L["admissible_not_excised_cleaner_at_floor"], admissible_not_excised_cells=L["admissible_not_excised_cells"],
                         least_including_inadmissible_db=L["least_all_value_db"], least_including_inadmissible_excised=L["least_all_excised"],
                         least_including_inadmissible_cell=L["least_all_cell"], least_including_inadmissible_status=L["least_all_status"],
                         least_stokes_I_admissible_db=L["least_admissible_I_value_db"], least_stokes_I_admissible_cell=L["least_admissible_I_cell"],
                         item18_as_coded=P["item18_promotion"], item18_under_b2_admissible_grid=str(adm_ok and P["label"] == "robust to post-processing"),
                         label=P["label"], robust_in_rule_variants=P["robust_in_rule_variants"]))
    with open(os.path.join(REL, "promotion_least_corners.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n"); w.writeheader(); w.writerows(rows)
    R = {r["channel"]: r for r in rows}
    coded = [ch for ch in EXCISED if R[ch]["item18_as_coded"] == "True"]
    grid = [ch for ch in EXCISED if R[ch]["item18_under_b2_admissible_grid"] == "True"]

    # ---- PROMOTION_EVIDENCE.md
    def fx(x, n=2): return "" if x in ("", None) else f"{float(x):+.{n}f}"
    def cross(ch):
        rs = [r for r in b6 if int(r["channel"]) == ch]
        if not rs or rs[0]["role"].startswith("n/a"): return None
        over = [r for r in rs if r["over_gate_every_policy"] == "True"]
        least = min(rs, key=lambda r: float(r["ratio_least_policy"])); most = max(rs, key=lambda r: float(r["ratio_keep_all"]))
        return len(over), len(rs), least, most
    def var(ch):
        rs = [r for r in b7 if int(r["channel"]) == ch]
        if not rs: return None
        w_ = max(rs, key=lambda r: float(r["margin_fourier_db"]))
        return float(w_["margin_fourier_db"]), float(w_["margin_time_db"]), w_["range"]
    def dcredit(ch, rng):   # r5.2: the r2 bar's change from r5.1 on the range, which is the settled credit's alone (the no-credit bars are r5.1's)
        if ch == 24: return C2N["reading"]["ranges"][rng]["bar_db"] - C2O["reading"]["ranges"][rng]["bar_db"]
        return R2N["results"][str(ch)][rng]["bar"] - R2O["results"][str(ch)][rng]["bar"]
    def shift(ch, rng):   # the r5.1 bar against r5's on the range (B-7's margins move dB for dB with the bar), unrounded
        if ch == 24: return 0.0
        a, b = A["results"][str(ch)][rng], A5["results"][str(ch)][rng]
        return (a["bar"] - b["bar"]) if (a["bar"] is not None and b["bar"] is not None) else 0.0
    ms = g24["masked_spectrogram"]
    out = []
    P_ = out.append
    P_(f"# Promotion evidence: capture ruling {rev}\n")
    P_("Generated by the producer (`source/promotion_evidence.py`) from the release tables and the B-list evidence it names. It reports,"
       " per excised channel, the least corner of B-2's declared grid and the grounds the excision carries. It does not decide the"
       " promotion set: item 18 is applied as the release codes it, and B-2's admissible grid is reported beside it.\n")
    P_("## The item 18 rule and who satisfies it\n")
    P_("Item 18: the not-saveable promotion (item 12) applies only to an excision that holds in every rule variant and is robust to"
       " post-processing.\n")
    P_(f"- **As coded** (`postprocessing_sensitivity.csv`, `item18_promotion`): {', '.join(map(str, coded))}. The rule variants are"
       " unmeasured classes at G = 1, the cleaner polarization and the archive shares.")
    P_(f"- **Under B-2's admissible grid** (every one of the admissible cells excises, and the label is robust to post-processing):"
       f" {', '.join(map(str, grid))}. The grid is rerun on the r5.1 readings (`b_list/B-2/r51`)."
       + (" r5.2 keeps r5.1's no-credit bars, and the grid's capture cells already take the settled ground credit, (1 - gamma) at B-1's"
          " reconciled gamma." if NEW else ""))
    nots = [ch for ch in EXCISED if ch not in grid]
    P_(f"- **Not satisfied:** {', '.join(map(str, nots))}. Each is excised in the ruling, and its disposition is unchanged (item 37).")
    for ch in nots:
        r = R[ch]
        P_(f"  - {ch}: {r['admissible_cells_not_excised']} of {r['admissible_cells']} admissible cells not excised"
           f" ({r['admissible_not_excised_cleaner_at_floor']} with the cleaner polarization at the floor"
           + (f"; the others: {r['admissible_not_excised_cells']}" if r["admissible_not_excised_cells"] else "") + f"); label {r['label']}.")
    if NEW:
        P_("- **Channel 24.** It satisfies the rule both ways. It joins item 12's five by author ruling (DECISIONS.md item 39, on triage"
           " row 15). Its grounds differ from the others' (below).")
    else:
        P_("- **Channel 24.** It satisfies the rule both ways. Adding it to item 12's five is an author ruling (triage row 15), which this"
           " release does not make. Its grounds differ from the others' (below).")
    P_("- **Literal G = 1** (every class at G = 1) is reported, not used. It is inadmissible (B-2, D3): a measured cross-frame amplitude"
       " cannot be priced below the admissible minimum G.\n")
    P_("## Least corners (B-2's grid on the r5.1 readings)\n")
    P_("The grid has 2 x 2 x 3 x 2 x 2 x 2 = 96 cells per channel: G, polarization, steady share, filter, cos dec and lambda_dep"
       " (`b_list/B-2/PLAN.md`). A value is the channel's bar in that cell, in dB over tolerance. The allowance is 10^0.3"
       f" ({ALLOW_DB:.2f} dB).\n")
    P_("| Ch | Deciding bar | Least admissible corner | Over the allowance | Cell | Admissible cells not excised | Least with literal G = 1 cells |")
    P_("|---|---|---|---|---|---|---|")
    for ch in EXCISED:
        r = R[ch]; la = r["least_admissible_corner_db"]
        P_(f"| {ch} | {RT.get(r['deciding_range'], r['deciding_range'])} {fx(r['deciding_bar_db'], 1)} dB | "
           + (f"{fx(la)} dB" if la else "at the floor") + " | " + (f"{fx(r['least_admissible_over_allowance_db'])} dB" if la else "") + " | "
           + r["least_admissible_cell"].replace("G=", "").replace("pol=", "").replace("share=", "").replace("filter=", "").replace("cosdec=", "cos dec ").replace("lambda_dep=", "")
           + f" | {r['admissible_cells_not_excised']} of {r['admissible_cells']} | "
           + (f"{fx(r['least_including_inadmissible_db'])} dB" if r["least_including_inadmissible_db"] else "at the floor")
           + ("" if r["least_including_inadmissible_excised"] == "True" else " (not excised)") + " |")
    P_("")
    def celltxt(c):
        d_ = dict(x.split("=") for x in c.split(", "))
        return (f"{'Stokes I' if d_['pol'] == 'I' else 'the cleaner polarization'}, "
                + {"none": "no steady share", "capture": "the capture steady share (1 - gamma)", "archive": "the archive shares"}[d_["share"]] + ", "
                + ("the 200 ns filter plus S" if d_["filter"] == "200ns" else "no filter") + f", cos dec {d_['cosdec']}"
                + (f" and {'D4' if d_['lambda_dep'] == 'D4' else 'the released'} lambda_dep" if d_["filter"] == "200ns" else "")
                + ("" if d_["G"] == "rule" else ", literal G = 1"))
    six = sorted(PROMOTED_R5, key=lambda c: float(R[c]["least_admissible_corner_db"]))
    all200 = all("filter=200ns" in R[c]["least_admissible_cell"] for c in PROMOTED_R5)
    inad = [c for c in PROMOTED_R5 if int(lc[c]["inadmissible_cells_not_excised"])]
    P_(f"**The statement.** Over B-2's admissible grid, the least corner of the six is channel {six[0]} at {fx(R[six[0]]['least_admissible_corner_db'])} dB"
       f" ({fx(R[six[0]]['least_admissible_over_allowance_db'])} dB over the allowance), in the cell with {celltxt(R[six[0]]['least_admissible_cell'])}."
       f" The next is channel {six[1]} at {fx(R[six[1]]['least_admissible_corner_db'])} dB."
       + (" Every admissible cell excises each of the six." if all(int(R[c]["admissible_cells_not_excised"]) == 0 for c in PROMOTED_R5) else "")
       + (" Every one of the six has its least corner in a 200 ns cell, a world that fails the precision requirement (D5)." if all200 else "")
       + (" Only literal G = 1 cells, which are inadmissible, fail any of them: " + "; ".join(
           f"channel {c} in {lc[c]['inadmissible_cells_not_excised']} of {lc[c]['inadmissible_cells']} (least {fx(R[c]['least_including_inadmissible_db'])} dB)" for c in inad) + "." if inad else "")
       + "\n")
    # against B-2 on r5 (the same grid on r5's readings)
    old = list(csv.DictReader(open(os.path.join(EVB, "B-2", "grid_cells.csv"))))
    key = lambda x: tuple(x[f] for f in ("channel", "G", "pol", "steady_share", "filter", "cosdec", "lambda_dep"))
    oc = {key(x): x for x in old}; flips = {}
    for x in cells:
        y = oc[key(x)]
        if x["status"] == "admissible" and y["channel_excised"] != x["channel_excised"]: flips.setdefault(int(x["channel"]), []).append((y, x))
    moved6 = [c for c in PROMOTED_R5 if any(abs(_f(y["channel_value_db"]) - _f(x["channel_value_db"])) > 1e-9 for x in cells if int(x["channel"]) == c and x["status"] == "admissible"
                                             for y in [oc[key(x)]] if _f(x["channel_value_db"]) is not None and _f(y["channel_value_db"]) is not None)]
    old_lc = {int(r_["channel"]): r_ for r_ in csv.DictReader(open(os.path.join(EVB, "B-2", "least_corners.csv")))}
    same6 = all(old_lc[c]["least_admissible_value_db"] == R[c]["least_admissible_corner_db"] for c in PROMOTED_R5)
    txt = ["Against B-2 on r5: the six's least corners are " + ("unchanged" if same6 else "changed") + (f", and no admissible cell of theirs moves" if not moved6 else f"; admissible cells move on {moved6}") + "."]
    for c, fl in sorted(flips.items()):
        txt.append(f"On channel {c}, {len(fl)} admissible cell{'s' if len(fl) > 1 else ''} no longer excise"
                   + ("" if len(fl) > 1 else "s") + ": " + "; ".join(f"{x['G']}/{x['pol']}/{x['steady_share']}/{x['filter']}/{x['cosdec']}/{x['lambda_dep']} {fx(y['channel_value_db'], 3)} to {fx(x['channel_value_db'], 3)} dB" for y, x in fl) + ".")
    txt.append("The causes are 15's censored tau (triage row 4) and 27's bound as fitted (0.439 s, row 35). Neither channel was in the set.")
    P_(" ".join(txt) + "\n")
    P_("## Grounds, channel by channel\n")
    P_("Sources:\n- coverage and CHIME's static mask: `research/static_mask_by_channel.csv`;\n- between cylinders: `b_list/B-6/out/b6_table.csv`;\n"
       "- the variance standard: `b_list/B-7/out/variance_reading.csv`;\n- channel 24's archive grounds: `b_list/B-8/ch24_grounds.json`;\n"
       "- the masked-spectrogram ground for 17, 30, 31 and 35: DECISIONS.md, corrections to item 12.\n")
    for ch in EXCISED:
        r = R[ch]; d = dp[ch]; p = pp[ch]; m = mask[ch]
        P_(f"### Channel {ch}\n")
        base = ("its own 2020 in-band measurement (item 34; 12 cohort events, 10 of them in January 2020; the band is dark in 2026, 0 of 16 bins live)"
                if ch == 24 else "the 2026 matched capture")
        P_(f"- **Ruling:** excised on the {RT[d['deciding_range']]} BAO range at {fx(d['deciding_bar_db'], 1)} dB over tolerance, on {base}."
           f" Threshold: {d['threshold']}.")
        P_(f"- **Rule variants:**\n  - unmeasured classes at G = 1: {p['r4_unmeasured_G1_disposition']};\n  - cleaner polarization: "
           + ("at the floor" if p["r4_cleaner_pol_bar_db"] == "at floor" else f"{fx(p['r4_cleaner_pol_bar_db'], 1)} dB")
           + " (" + p["r4_cleaner_pol_measured_classes"].split(" (")[0] + f" classes measured on the {RT[p['r4_cleaner_pol_measured_classes'].split('(')[1].rstrip(')')]} range);\n"
           "  - archive shares: " + ("n/a (none in the ledger)" if p["r4_archive_shares_bar_db"] == "n/a" else f"{fx(p['r4_archive_shares_bar_db'], 1)} dB")
           + f";\n  - robust in the rule variants: {p['robust_in_rule_variants']}.")
        P_(f"  - Literal G = 1, reported only: {p['r4_literal_G1_disposition']} ({fx(p['r4_literal_G1_bar_db'], 1)} dB).")
        P_(f"- **Post-processing:** r3 (ground credit{', 1 - gamma' if NEW else ''}) {fx(p['r3_deciding_bar_db'])} dB; r2 (200 ns filter plus S and the ground credit)"
           f" {fx(p['r2_deciding_bar_db'])} dB; label {p['label']}" + (f", removed by {p['removed_by']}" if p["removed_by"] else "") + ".")
        la = r["least_admissible_corner_db"]
        P_("- **B-2 grid:** " + (f"least admissible corner {fx(la)} dB ({fx(r['least_admissible_over_allowance_db'])} dB over the allowance)" if la else "the least admissible cell is at the floor")
           + f"; {r['admissible_cells_not_excised']} of {r['admissible_cells']} admissible cells not excised; item 18 under the grid: {r['item18_under_b2_admissible_grid']}.")
        if ch == 24:
            P_(f"- **Masked spectrogram (B-8):** holds on channel 24's own archive pilot (690.npz, the cal_q0.5 median-threshold mask)."
               f" In all {ms['months_with_20_kept']} months with at least 20 kept frames, the carrier in the kept frames is at least"
               f" {ms['carrier_kept_min_db_over_months_with_20_kept']} dB above the frame median. Masking moves it by {ms['all_minus_kept_db_range'][0]:.2f} to"
               f" {ms['all_minus_kept_db_range'][1]:.2f} dB. This is new against the triage's row 15, which lists 24 without this ground.")
            P_("- **Coherence between events (B-8):** not a ground at the declared level. On all 12 events only (0,64) passes the declared"
               " test, and the channel 37 control reads 0.99 on (2,0), so phase coherence of these stacks is not specific to an emitter.")
            P_(f"- **Trigger frames (B-8):** the excess is not carried by the trigger frames: {g24['trigger']['n_over_3sigma']} of"
               f" {g24['trigger']['n_tests']} centre-frame tests exceed 3 sigma, and both of those are negative.")
        elif ch in MSG:
            P_("- **Masked spectrogram:** " + ("the carrier survives the median-threshold mask (DECISIONS.md, corrections to item 12)." if MSG[ch] else
                                                "not carried: channel 33's carrier is outside the detector's target bin (DECISIONS.md, corrections to item 12)."))
        else:
            P_("- **Masked spectrogram:** not a ground for this channel (an exploratory capture excision).")
        cr = cross(ch)
        if cr is None: P_("- **Between cylinders (B-6):** n/a, because there is no 2026 capture.")
        else:
            n, t, least, most = cr
            P_(f"- **Between cylinders (B-6):** cross-cylinder classes over the gate under every policy: {n} of {t}. The least reading is ({least['cls']}) at"
               f" {float(least['ratio_least_policy']):.2f}x of the gate under {least['least_policy']}; the largest four-dump median is ({most['cls']}) at"
               f" {float(most['ratio_keep_all']):.2f}x (per dump {most['per_dump']}).")
        v = var(ch)
        if v is None:
            P_("- **Variance standard (B-7), both credits:** no BAO range has a reading.")
        else:
            sh = shift(ch, v[2]); dc = dcredit(ch, v[2]) if NEW else 0.0; sb = sh; sh = sh + dc; a_, b_ = v[0] + sh, v[1] + sh
            if not NEW: stxt = "" if abs(sh) < 1e-9 else f" These are shifted by {sh:+.2f} dB from B-7's r5 figures, since B-7's margins move dB for dB with the bar."
            else:
                stxt = ("" if abs(sh) < 1e-9 else f" These are shifted by {sh:+.2f} dB from B-7's r5 figures, since B-7's margins move dB for dB with the r2 bar"
                        + (f": {sb:+.2f} dB with the no-credit bar and {dc:+.2f} dB with the settled ground credit." if abs(sb) >= 1e-9 else f", which the settled ground credit moves by {dc:+.2f} dB."))
            P_(f"- **Variance standard (B-7), both credits:** {a_:+.1f} dB harmonic and {b_:+.1f} dB inverse-variance, on the {RT[v[2]]} range, where a positive"
               " margin means keeping the channel costs more than excising it."
               + stxt
               + (" It fails under both estimators." if (a_ > 0 and b_ > 0) else " It passes under both estimators." if (a_ <= 0 and b_ <= 0) else " It fails under the harmonic convention only."))
        P_(f"- **Coverage and CHIME's mask:** {m['bins_live_2026-09-16']} of {m['n_bins']} bins live on 2026-09-16. The static mask covers"
           f" {m['static_masked_2026-09-24']} of {m['n_bins']} bins in 2026, {m['static_masked_2022-01-01']} in 2022 and {m['static_masked_2019-06-01']} in 2019.\n")
    with open(os.path.join(REL, "PROMOTION_EVIDENCE.md"), "w") as fh: fh.write("\n".join(out) + "\n")
    return dict(coded=coded, grid=grid)
