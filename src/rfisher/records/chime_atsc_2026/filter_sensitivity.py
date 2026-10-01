"""The one filter sensitivity the idealized model keeps (DECISIONS.md item 15): which no-filter excisions also hold with a
200 ns delay filter and its credit S. Revision 3 (no filter) against revision 2 (200 ns plus S), channel by channel.

Both rulings take the same readings (A, tau, G, policies, epochs, blockers); the world changes only the exclusion side's
constant, S / lambda, so every bar moves by one per-channel shift, 10 log10 of (fill_none / lambda_none) / (S_200ns / lambda_dep),
S_200ns being the 11.4 dB delay-filter credit with its bin fill. The shift is checked on every range that carries a bar in
both. A disposition is excise when either BAO range excises; excisions that exist only without the filter are flagged.

The release's ``filter_sensitivity_a18.py`` (revision 3's), with its logic unchanged.
usage: rfisher records filter-sensitivity <r3 a18.json> <r3 dispositions_a18.csv> <r2 release dir> <out csv>
"""
import csv, math, os
from rfisher.records.chime_atsc_2026._files import load_json, read_rows


def main(argv=None):
    import sys
    argv = ["filter-sensitivity"] + list(sys.argv[1:] if argv is None else argv)
    A3, D3, R2, OUT = argv[1:5]
    a3 = load_json(A3); a2 = load_json(os.path.join(R2, "run", "a18.json"))
    assert a3.get("world") == "none" and "world" not in a2 and "WORLD" not in a2["switches"]
    assert {k: v for k, v in a3["switches"].items() if k != "WORLD"} == a2["switches"]
    d3 = {r["channel"]: r for r in read_rows(D3)}; d2 = {r["channel"]: r for r in read_rows(os.path.join(R2, "dispositions_a18.csv"))}
    BAO = ("bao_short", "bao_long")
    def db(x): return 10 * math.log10(x)
    def bar(a, c, rng):
        p = a["results"][c][rng]
        return p["bar"] if p["verdict"][0] in ("excise", "marginal", "policy at floor") else None
    def f2(x): return "" if x is None else f"{x:.2f}"
    rows = []
    for ch in range(14, 38):
        c = str(ch); r3, r2 = d3[c], d2[c]
        o = dict(channel=ch, r3_disposition=r3["a18_disposition"], r3_deciding_range=r3["deciding_range"], r3_deciding_bar_db="",
                 r2_disposition=r2["a18_disposition"], r2_deciding_range=r2["deciding_range"], r2_deciding_bar_db="", filter_shift_db="")
        if c in a3["results"] and c != "37":
            shift = db(a3["S"][c] / a3["lam_exclusion"][c]) - db(a2["S"][c] / a2["lam_dep"][c])
            o["filter_shift_db"] = f"{shift:+.2f}"
            for rng in BAO:
                b3, b2 = bar(a3, c, rng), bar(a2, c, rng)
                assert (b3 is None) == (b2 is None) and (b3 is None or abs(b3 - b2 - shift) < 1e-9), (ch, rng, b3, b2, shift)
                assert a3["results"][c][rng]["verdict"][0] == a2["results"][c][rng]["verdict"][0] or {a3["results"][c][rng]["verdict"][0], a2["results"][c][rng]["verdict"][0]} == {"excise", "marginal"}
                o[f"r3_{rng}_bar_db"] = f2(b3); o[f"r2_{rng}_bar_db"] = f2(b2)
                o[f"r3_{rng}_state"] = a3["results"][c][rng]["verdict"][0]; o[f"r2_{rng}_state"] = a2["results"][c][rng]["verdict"][0]
            if r3["deciding_range"] in BAO: o["r3_deciding_bar_db"] = f2(bar(a3, c, r3["deciding_range"]))
            if r2["deciding_range"] in BAO: o["r2_deciding_bar_db"] = f2(bar(a2, c, r2["deciding_range"]))
        ex3, ex2 = r3["a18_disposition"] == "excise", r2["a18_disposition"] == "excise"
        assert not (ex2 and not ex3), ch          # the filter credit can only remove an excision
        o["excision_holds_with_filter"] = ("yes" if ex2 else "no") if ex3 else ""
        o["excised_only_without_filter"] = str(ex3 and not ex2)
        if ex3 and not ex2:
            o["note"] = (f"excised without the filter ({r3['deciding_range']} {o['r3_deciding_bar_db']} dB); with the 200 ns filter and its credit the same"
                         f" reading is {o['r2_' + r3['deciding_range'] + '_bar_db']} dB, {r2['a18_disposition']}")
        elif ex3: o["note"] = f"excised in both; the 200 ns world (its credit S and its tolerance) reads every bar {float(o['filter_shift_db']):.2f} dB lower"
        elif ch == 24: o["note"] = "no 2026 capture products; undetermined on the 2020 basis in both (item 9)"
        elif ch == 37: o["note"] = "reference channel"
        elif r3["deciding_range"]: o["note"] = f"undetermined in both ({r3['bao_long'] if r3['deciding_range'] == 'bao_long' else r3['bao_short']})"
        else: o["note"] = "undetermined in both: both BAO ranges at the control floor"
        rows.append(o)
    fields = ["channel", "r3_disposition", "r3_deciding_range", "r3_deciding_bar_db", "r2_disposition", "r2_deciding_range", "r2_deciding_bar_db",
              "filter_shift_db", "excision_holds_with_filter", "excised_only_without_filter"]
    fields += [f"{w}_{rng}_{k}" for rng in BAO for w in ("r3", "r2") for k in ("state", "bar_db")] + ["note"]
    with open(OUT, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n", restval=""); w.writeheader(); w.writerows(rows)
    only = [r["channel"] for r in rows if r["excised_only_without_filter"] == "True"]
    hold = [r["channel"] for r in rows if r["excision_holds_with_filter"] == "yes"]
    print(f"no-filter excisions: {[r['channel'] for r in rows if r['r3_disposition'] == 'excise']}; also hold with the 200 ns filter and its credit: {hold};"
          f" exist only without the filter: {only}")
    return 0
