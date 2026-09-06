"""``rfisher-results``: render dissertation results figures from releases.

    rfisher-results estimator-transfer --release DIR --out FILE.pdf
        [--calibration pilot_below_db,bin_enbw_hz,dtv_bandwidth_hz[,efficiency]]
        [--title TEXT] [--y-min DB] [--no-tex]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import style
from .estimator_transfer import Calibration, figure_estimator_transfer, load_release


def _calibration(text: str | None) -> Calibration | None:
    if not text:
        return None
    parts = [float(p) for p in text.split(",")]
    if len(parts) not in (3, 4):
        raise SystemExit("--calibration takes pilot_below_db,bin_enbw_hz,dtv_bandwidth_hz[,efficiency]")
    return Calibration(*parts)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="rfisher-results", description=__doc__.split("\n", 1)[0])
    sub = ap.add_subparsers(dest="command", required=True)
    et = sub.add_parser("estimator-transfer", help="digital or over-the-air estimator-transfer figure")
    et.add_argument("--release", type=Path, required=True, help="release directory (data/plot_points.csv inside)")
    et.add_argument("--out", type=Path, required=True, help="PDF to write")
    et.add_argument("--calibration", default=None, help="pilot calibration when the release has no run/run_state.json")
    et.add_argument("--title", default=None)
    et.add_argument("--y-min", type=float, default=None, dest="y_min")
    et.add_argument("--no-tex", action="store_true", help="preview without LaTeX text rendering")
    args = ap.parse_args(argv)

    style.configure(require_tex=not args.no_tex)
    if args.command == "estimator-transfer":
        release = load_release(args.release, calibration=_calibration(args.calibration))
        out = figure_estimator_transfer(release, out=args.out, title=args.title, y_min_db=args.y_min)
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
