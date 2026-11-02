"""rfisher table    -- forecast every channel and write the table
rfisher figures  -- draw the per-channel plates and the summary from a table
rfisher overview -- reproduce the CHIME Overview forecast, then run it in 6 MHz channels
"""
import argparse
from pathlib import Path


def main(argv=None):
    ap = argparse.ArgumentParser(prog="rfisher", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    t = sub.add_parser("table", help="forecast every channel and write the table")
    t.add_argument("--out", type=Path, required=True)
    t.add_argument("--channels", help="comma-separated channel numbers (default: all)")
    t.add_argument("--workers", type=int)
    f = sub.add_parser("figures", help="draw the per-channel plates and the summary")
    f.add_argument("--table", type=Path, help="table JSON (default: the shipped table)")
    f.add_argument("--out", type=Path, required=True)
    f.add_argument("--channels", help="comma-separated channel numbers (default: all)")
    o = sub.add_parser("overview", help="reproduce the CHIME Overview forecast and run it in 6 MHz channels")
    o.add_argument("--out", type=Path, required=True)
    o.add_argument("--workers", type=int)
    args = ap.parse_args(argv)
    pick = None if not getattr(args, "channels", None) else {int(c) for c in args.channels.split(",")}
    if pick is not None:
        from .bands import channels
        unknown = pick - {b.channel for b in channels()}
        if unknown:
            ap.error(f"unknown channels: {', '.join(map(str, sorted(unknown)))}")
    if getattr(args, "workers", None) is not None and args.workers < 1:
        ap.error("workers must be positive")

    if args.command == "table":
        from .bands import channels
        from .table import build_table, write_table
        bands = [b for b in channels() if pick is None or b.channel in pick]
        for path in write_table(build_table(bands, args.workers), args.out):
            print(path)
    elif args.command == "overview":
        import json

        from .figures import overview_figure
        from .overview import reference
        args.out.mkdir(parents=True, exist_ok=True)
        result = reference(args.workers)
        path = args.out / "overview_planck2018.json"
        path.write_text(json.dumps(result, indent=1) + "\n")
        print(path)
        print(overview_figure(result, args.out))

    else:
        from .figures import draw_all
        from .table import read_table
        for path in draw_all(read_table(args.table), args.out, pick):
            print(path)


if __name__ == "__main__":  # pragma: no cover
    main()
