#!/usr/bin/env python3
"""The threshold the forecast selects, per channel.

This is the closing move of the framework: minimize the survey-time cost

    T / T_clean = (1 + r) / (1 - f)

over the coarse threshold family F > eta * mu0, subject to the bias-tolerance
constraint r <= r_tol on the binding acoustic dilation (alpha_perp, zeta = 1),
with the fine stage's measured sensitivity credit applied to the bound.

Selection discipline:

* The residual bound is computed on TWO floor bases and both are reported.
  ``product`` follows the package's one floor discipline
  (rfisher.residual.kept_frame_floor): the measured null floor where at
  least MIN_MEASURED_NULLS frames support it --- the transmitter-off era on
  channels that have one (ch35), the archive null population elsewhere ---
  and the sigma-implied substitute, labelled stated evidence, below the bar.
  ``sigma_null`` bounds every undetected frame at the level a threshold
  sitting at the null center can actually resolve; a detector property
  rather than a channel measurement, defensible only where no measurement
  exists. On ch35 the two now disagree by ~19 dB because the off-era
  exceedance tail is measurably heavier than the fitted null; where the two
  disagree about feasibility, that disagreement is the finding rather than
  a nuisance, and the measured basis is the one a verdict may stand on.

* Among near-optimal thresholds (within 2% of the minimum cost) the SMALLEST
  eta is selected: equal cost, more residual margin. Optima on flat plateaus
  are otherwise spuriously precise.

* Channels whose tau_c was refused carry a bound rather than a measurement, and the
  bound is conservative in one direction only: a feasible eta is truly
  feasible, but the reported optimum may be pessimistic; a measured tau_c
  can only enlarge the feasible set. The output marks these.

    python3 scripts/optimal_thresholds.py
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
from pathlib import Path

import numpy as np


from rfisher import residual as R

# Stable zeta = 1 tolerances (scripts/bias_tolerance.py --zeta 1.0), one home.
from rfisher.tolerances import TOL_APERP, TOL_FS8
FINE_DB = 10.0                       # measured fine-stage credit, 9.4-10.0 dB
DEPLOYED_DELAY_DB = 11.4             # CHIME's 200 ns cut; NOT booked in the
                                     # verdicts; shown as a labeled scenario.
PLATEAU = 1.02                       # "within 2% of optimal" tie-break window

from rfisher import products as _products
from rfisher.npzio import load_npz

DEFAULT_PRODUCTS = _products.paths()

ETAS = np.unique(np.concatenate([
    np.arange(1.00, 1.101, 0.01),          # fine grid at the knee
    np.arange(1.10, 2.01, 0.05),
    np.geomspace(2.0, 300.0, 16),
]))


def recent_f(path, eta, mu0, year_from):
    d = load_npz(path)
    v = d["valid"][:, 0].astype(bool)
    F = d["fstat_raw"][:, 0]
    t = d["unit_time0_ctime"][d["frame_unit_index"]]
    yr = np.array([dt.datetime.utcfromtimestamp(x).year for x in t])
    m = v & (yr >= year_from)
    if m.sum() < 100:
        return float("nan")
    return float((F[m] > eta * mu0).mean())


def optimize(path, ch):
    prov = R.floor_provenance(path)
    corr = R.correlation_time(path)
    tol = TOL_APERP[ch]
    d = load_npz(path)
    t = d["unit_time0_ctime"]
    yr_max = dt.datetime.utcfromtimestamp(float(t.max())).year
    era_from = max(yr_max - 2, 2018)

    floor_db, floor_evidence = R.kept_frame_floor(path)
    out = {"ch": ch, "mu0": prov.mu0, "tau_bound": corr.quality != "measured",
           "tol_aperp": tol, "era_from": era_from,
           "floor_evidence": floor_evidence, "bases": {}}

    for basis in ("product", "sigma_null"):
        kw = {"floor_db": (floor_db if basis == "product"
                           else prov.sigma_implied_db)}
        sweep = R.threshold_sweep(path, etas=ETAS, **kw)
        rows = [dict(eta=s["eta"], f=s["f"],
                     r_fine=s["r_masked"] / 10 ** (FINE_DB / 10))
                for s in sweep]
        for row in rows:
            row["penalty"] = ((1 + row["r_fine"]) / (1 - row["f"])
                              if row["f"] < 1 else float("inf"))
        feas = [r for r in rows if r["r_fine"] <= tol]
        rec = {"n_grid": len(rows), "feasible": len(feas)}
        if feas:
            pmin = min(r["penalty"] for r in feas)
            best = min((r for r in feas if r["penalty"] <= PLATEAU * pmin),
                       key=lambda r: r["eta"])
            at1 = rows[0] if rows and abs(rows[0]["eta"] - 1.0) < 1e-9 else None
            rec.update(
                eta=best["eta"], F_thresh=best["eta"] * prov.mu0,
                f=best["f"], r_fine=best["r_fine"],
                margin=tol / best["r_fine"], penalty=best["penalty"],
                penalty_pe=(at1["penalty"] if at1 else float("nan")),
                f_recent=recent_f(path, best["eta"], prov.mu0, era_from),
                # the labeled scenario: does this eta also satisfy fs8 if the
                # deployed delay filter were booked on both sides?
                fs8_with_delay=(best["r_fine"] / 10 ** (DEPLOYED_DELAY_DB / 10)
                                <= TOL_FS8[ch]),
            )
        out["bases"][basis] = rec
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--products", nargs="+", default=None,
                    metavar="CH=PATH", help="override e.g. 30=/path/598.npz")
    ap.add_argument("--out", type=Path, default=Path("out"))
    args = ap.parse_args(argv)

    products = dict(DEFAULT_PRODUCTS)
    for spec in args.products or []:
        ch, _, path = spec.partition("=")
        products[int(ch)] = path

    # The selector's scope is the first-measured block (the channels with
    # published fs8 constants); the lower band's operating points come from
    # scripts/calibrated_thresholds.py on the same stable tolerance table.
    results = [optimize(p, ch) for ch, p in sorted(products.items())
               if ch in TOL_FS8]

    print(f"objective: min (1+r)/(1-f)  s.t.  r_fine <= r_tol(alpha_perp), "
          f"zeta = 1, fine stage {FINE_DB:.0f} dB\n")
    hdr = (f"{'ch':>3} {'basis':>10} {'eta*':>6} {'F>':>10} {'f*':>7} "
           f"{'r_fine':>9} {'margin':>7} {'cost':>6} {'@eta=1':>7} "
           f"{'recent f':>9} {'fs8+delay':>9}")
    print(hdr)
    rows_csv = []
    for res in results:
        for basis, rec in res["bases"].items():
            tag = f"ch{res['ch']}" + ("*" if res["tau_bound"] else "")
            if rec.get("feasible"):
                line = (f"{tag:>3} {basis:>10} {rec['eta']:6.2f} "
                        f"{rec['F_thresh']:10.6f} {rec['f']:7.1%} "
                        f"{rec['r_fine']:9.3g} {rec['margin']:6.1f}x "
                        f"{rec['penalty']:6.2f} {rec['penalty_pe']:7.2f} "
                        f"{rec['f_recent']:9.1%} "
                        f"{'yes' if rec['fs8_with_delay'] else 'no':>9}")
            else:
                line = (f"{tag:>3} {basis:>10} {'--':>6} {'--':>10} "
                        f"{'--':>7} {'--':>9} {'--':>7} {'--':>6} {'--':>7} "
                        f"{'--':>9} {'--':>9}   no feasible eta -> excise")
            print(line)
            rec2 = {k: rec.get(k) for k in
                    ("eta", "F_thresh", "f", "r_fine", "margin", "penalty",
                     "penalty_pe", "f_recent", "feasible", "fs8_with_delay")}
            rows_csv.append({"ch": res["ch"], "basis": basis,
                             "mu0": res["mu0"], "tau_bound": res["tau_bound"],
                             "tol_aperp": res["tol_aperp"],
                             "era_from": res["era_from"],
                             "floor_evidence": res["floor_evidence"], **rec2})
        print()

    print("*  tau_c refused (capped at one sidereal day): r is a bound, so a "
          "feasible eta is truly feasible\n   but the optimum may be "
          "pessimistic; a measured tau_c only enlarges the feasible set.\n"
          "fs8+delay: whether eta* also meets the fs8 tolerance if the "
          f"deployed {DEPLOYED_DELAY_DB} dB delay filter were booked\n"
          "(a labeled scenario; the chapter's verdicts book zero).")

    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / "optimal_thresholds.csv"
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows_csv[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(rows_csv)
    print(f"\nwrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
