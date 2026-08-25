#!/usr/bin/env python3
"""Regenerate bao_two_walls.csv from the survey products (bridge retirement).

The two-walls figure plots every channel's coarse threshold sweep in the
occupancy-versus-residual plane: masked fraction f against the kept-frame
residual over the binding tolerance. The committed table was recovered from
the published artwork of the ten-channel era; this generator replaces it,
computed from the released products for all 23 channels under one stated
convention:

* full-archive sweep of F > eta * mu0 (``baonoise.residual.threshold_sweep``),
  under the package's one residual booking: a refused tau_c takes no
  ground-filter credit (``surviving_components``);
* the kept-frame floor follows the package's one floor discipline
  (``baonoise.residual.kept_frame_floor``): the measured null floor where at
  least MIN_MEASURED_NULLS frames support it --- the verified pre-sign-on
  era on ch35 (``SIGN_ON_OFF_THROUGH``), the archive null population
  elsewhere (evidence ``measured``) --- and the sigma-implied substitute
  below the bar (evidence ``stated``, drawn dashed by the figure);
* the ordinate is the published plane's: the fine-credited residual over the
  stable zeta = 1 dilation tolerance of the channel's own redshift bin,
  (r_masked / 10) / tol_aperp --- the same axis as the operating-point
  optimization, constants from ``baonoise.tolerances`` (one home, one
  convention for upper and lower band alike).

Row order is the figure's: order 0 is the highest threshold and the last
row is the eta = 1 floor, where the figure draws each channel's dot.

    python3 scripts/dissertation/make_two_walls.py --products DIR

STATUS --- reconciled and adopted. The earlier STATUS blocked adoption on
three moving channels and misdiagnosed the largest mover: ch35's endpoint
shift (published 0.05 -> 4.4) was never a tau booking difference --- both
paths book its measured 45-min tau_c identically --- it is the floor basis.
The published point (and Table 9.5's 6.6x margin) stood on the sigma-implied
substitute (-45.5 dB); this generator uses ch35's measured off-era floor
(-26.2 dB, 3167 pre-sign-on null frames), and the substitution the published
number relied on is now refuted by measurement: the off-era exceedance tail
is 7-300x heavier than the fitted null (q50/q90/q99 of F-1), so real
coherent-capable structure sits ~19 dB above what the sigma-implied level
assumes an undetected frame can hide. ch31 and ch28 move because their 2-
and 6-frame floors fall below the >= 30-null bar and take the stated
substitute; refused-tau channels move because the sweep no longer keeps a
ground-filter credit the refusal invalidated. The artwork recovery's ch27
and ch30 curves were swapped and are emitted here under their correct
channels.
"""
from __future__ import annotations

import argparse
import csv
import glob
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from baonoise import residual as res  # noqa: E402
from baonoise.tolerances import TOL_APERP  # noqa: E402

FINE_DB = 10.0                    # measured fine-stage credit, booked as 10


def sweep_channel(path):
    with np.load(path, allow_pickle=False) as z:
        ch = int(z["physical_channel"][0])
    floor_db, evidence = res.kept_frame_floor(path)
    # Sign-off channels sweep their transmitter-on era only: an era-blind
    # sweep classifies the sign-off step into the DC/inter-day shares the
    # ground filter removes, so the transmitter's death would masquerade as
    # filterable structure (and ch19's straddling record returns a spurious
    # tau_c). ch35's curve deliberately stays the full-archive statement the
    # published plane made -- its post-sign-on era is the figure's X marker.
    off_from = res.SIGN_OFF_FROM.get(ch)
    tau_bound = res.correlation_time(
        path, off_from=off_from).quality != "measured"
    rows = res.threshold_sweep(path, off_from=off_from, floor_db=floor_db)
    return ch, evidence, tau_bound, rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--products", type=Path, required=True)
    ap.add_argument("--out", type=Path,
                    default=Path(__file__).resolve().parent
                    / "data" / "bao_two_walls.csv")
    args = ap.parse_args()

    paths = sorted(glob.glob(os.path.join(str(args.products), "*.npz")),
                   key=lambda p: int(Path(p).stem))
    out_rows = []
    for path in paths:
        ch, evidence, tau_bound, rows = sweep_channel(path)
        tol = TOL_APERP[ch]
        # figure order: high threshold first, the eta = 1 floor last (the dot)
        rows = sorted(rows, key=lambda r: -r["eta"])
        for i, r in enumerate(rows):
            out_rows.append(dict(
                channel=ch, evidence=evidence,
                tau_bound=int(tau_bound), order=i,
                masked_fraction=f"{r['f']:.8g}",
                r_over_rtol=f"{(r['r_masked'] / FINE_DB) / tol:.6g}"))
        end = out_rows[-1]
        print(f"ch{ch}: {evidence}{', tau bound' if tau_bound else ''}, "
              f"{len(rows)} sweep points, "
              f"eta=1 end (f, r/rtol) = ({end['masked_fraction']}, "
              f"{end['r_over_rtol']})")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as handle:
        w = csv.DictWriter(handle, fieldnames=["channel", "evidence",
                                               "tau_bound", "order",
                                               "masked_fraction",
                                               "r_over_rtol"],
                           lineterminator="\n")
        w.writeheader()
        w.writerows(out_rows)
    print(f"{args.out}: {len(out_rows)} rows, "
          f"{len({r['channel'] for r in out_rows})} channels")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
