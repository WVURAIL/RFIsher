"""rfisher table   -- forecast every channel and write the table
rfisher figures -- draw the per-channel plates and the summary from a table
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
    args = ap.parse_args(argv)
    pick = None if not args.channels else {int(c) for c in args.channels.split(",")}

    if args.command == "table":
        from .bands import channels
        from .table import build_table, write_table
        bands = [b for b in channels() if pick is None or b.channel in pick]
        for path in write_table(build_table(bands, args.workers), args.out):
            print(path)
    else:
        from .figures import draw_all
        from .table import read_table
        for path in draw_all(read_table(args.table), args.out, pick):
            print(path)


if __name__ == "__main__":  # pragma: no cover
    main()
