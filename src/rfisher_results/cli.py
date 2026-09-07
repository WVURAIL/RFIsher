"""Render dissertation results figures from releases.

Run as a module; there is deliberately no console-script entry, because the
shipped Fisher banks pin a digest of pyproject.toml and a rendering command
is no reason to re-stamp them.

    python -m rfisher_results.cli estimator-transfer --release DIR --out FILE.pdf
        [--calibration pilot_below_db,bin_enbw_hz,dtv_bandwidth_hz[,efficiency]]
        [--title TEXT] [--y-min DB] [--no-tex]
    python -m rfisher_results.cli transfer-points --sweep ROOT --out plot_points.csv
        [--conditioning conditioning.json] [--bootstrap-samples N]
    python -m rfisher_results.cli archive --products DIR --out DIR
        [--workers 6] [--replicates 1000] [--seed 20260907] [--channels 35,29]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import style
from .census_psd import figure_census_psd
from .estimator_transfer import Calibration, figure_estimator_transfer, load_release
from .evaluations import Conditioning, digital_sweep_layout, load_evaluations, transfer_points, write_points


def _calibration(text: str | None) -> Calibration | None:
    if not text:
        return None
    parts = [float(p) for p in text.split(",")]
    if len(parts) not in (3, 4):
        raise SystemExit("--calibration takes pilot_below_db,bin_enbw_hz,dtv_bandwidth_hz[,efficiency]")
    return Calibration(*parts)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m rfisher_results.cli", description=__doc__.split("\n", 1)[0])
    sub = ap.add_subparsers(dest="command", required=True)
    et = sub.add_parser("estimator-transfer", help="digital or over-the-air estimator-transfer figure")
    et.add_argument("--release", type=Path, required=True, help="release directory (data/plot_points.csv inside)")
    et.add_argument("--out", type=Path, required=True, help="PDF to write")
    et.add_argument("--calibration", default=None, help="pilot calibration when the release has no run/run_state.json")
    et.add_argument("--title", default=None)
    et.add_argument("--y-min", type=float, default=None, dest="y_min")
    et.add_argument("--no-tex", action="store_true", help="preview without LaTeX text rendering")
    cp = sub.add_parser("census-psd", help="all 23 channels' time-averaged spectra around the pilot, one canvas")
    cp.add_argument("--csv", type=Path, required=True, help="census_psd.csv from a pilot-proxy export")
    cp.add_argument("--out", type=Path, required=True)
    cp.add_argument("--provenance", required=True, help="one line for the panel key: what was averaged, from which products")
    cp.add_argument("--no-tex", action="store_true")
    tp = sub.add_parser("transfer-points", help="pool a raw evaluate-snr sweep into the release's plot_points.csv")
    tp.add_argument("--sweep", type=Path, required=True, help="root of the 40 digital shard directories")
    tp.add_argument("--out", type=Path, required=True, help="CSV to write")
    tp.add_argument("--conditioning", type=Path, default=None, help="conditioning.json with the waveform coefficients")
    tp.add_argument("--bootstrap-samples", type=int, default=10_000, dest="bootstrap_samples")
    ar = sub.add_parser("archive", help="the archive pipeline over the campaign products: eras, anchors, containment, nulls, selection, ledger")
    ar.add_argument("--products", type=Path, required=True, help="directory of the 23 v5 per-pilot products")
    ar.add_argument("--out", type=Path, required=True, help="results tree to write (a new dated directory)")
    ar.add_argument("--workers", type=int, default=6)
    ar.add_argument("--replicates", type=int, default=1000)
    ar.add_argument("--seed", type=int, default=20260907)
    ar.add_argument("--channels", default=None, help="comma-separated physical channels to run (default all)")
    args = ap.parse_args(argv)

    if args.command == "archive":
        from .archive.run import run_archive
        chans = [int(c) for c in args.channels.split(",")] if args.channels else None
        summary = run_archive(args.products, args.out, workers=args.workers, replicates=args.replicates, seed=args.seed,
                              channels=chans)
        print(json.dumps({k: v for k, v in summary.items() if k != "errors"}), flush=True)
        return 1 if summary["errors"] else 0

    if args.command == "transfer-points":
        shards = load_evaluations(digital_sweep_layout(args.sweep))
        conditioning = Conditioning.from_json(args.conditioning) if args.conditioning else None
        print(write_points(transfer_points(shards, conditioning=conditioning,
                                           bootstrap_samples=args.bootstrap_samples), args.out))
        return 0

    style.configure(require_tex=not args.no_tex)
    if args.command == "census-psd":
        print(figure_census_psd(args.csv, out=args.out, provenance=args.provenance))
    elif args.command == "estimator-transfer":
        release = load_release(args.release, calibration=_calibration(args.calibration))
        out = figure_estimator_transfer(release, out=args.out, title=args.title, y_min_db=args.y_min)
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
