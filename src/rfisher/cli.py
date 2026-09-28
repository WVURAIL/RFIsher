"""The ``rfisher`` command.

    rfisher forecast     evaluate one uniform masking scenario from a Fisher bank
    rfisher build-bank   build a Fisher bank (slow; needs RadioFisher)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .forecast.radiofisher_bao import api, scenarios
from .forecast.radiofisher_bao.bank import build, experiments, resources


def forecast_main(argv=None, prog: str = "rfisher forecast") -> int:
    """Evaluate one uniform masking scenario and print machine-readable JSON."""
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Evaluate a uniform RFI-masking scenario from a Fisher bank.")
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {__version__}")
    bank_group = parser.add_mutually_exclusive_group()
    bank_group.add_argument(
        "--bank", type=Path,
        help="explicit bank path (must be strict schema v2)")
    bank_group.add_argument(
        "--cosmology", choices=tuple(resources.BANK_NAMES),
        help="packaged CHIME bank (default: cmbspa2026)")
    parser.add_argument("--uniform", type=float, required=True,
                        help="uniform masked fraction in [0,1]")
    parser.add_argument("--band", choices=("dtv", "chime"), default="dtv")
    parser.add_argument("--target", type=float, default=5.0)
    parser.add_argument("--duty", type=float, default=1.0)
    parser.add_argument(
        "--hours-per-year", type=float,
        default=experiments.OVERVIEW_ONSKY_YEAR_HOURS,
        help="8760 for Overview on-sky years (default, the convention every "
             "quoted time in this repository uses); 8766 for mean calendar "
             "years")
    args = parser.parse_args(argv)
    bank = (args.bank if args.bank is not None
            else resources.bank_file(args.cosmology or resources.DEFAULT_COSMOLOGY))
    forecast = api.load(bank)
    band = {"dtv": scenarios.DTV_BAND, "chime": scenarios.CHIME_BAND}[
        args.band]
    result = api.required_time(
        forecast, uniform=args.uniform, band=band, target=args.target,
        duty=args.duty, hours_per_year=args.hours_per_year)
    print(json.dumps(result, sort_keys=True))
    return 0


def build_bank_main(argv=None, prog: str = "rfisher build-bank") -> int:
    """Build a provenance-complete Fisher bank (see ``bank.build``)."""
    return build.main(argv, prog=prog)


COMMANDS = {
    "forecast": (forecast_main,
                 "evaluate one uniform masking scenario from a Fisher bank"),
    "build-bank": (build_bank_main,
                   "build a Fisher bank (slow; needs RadioFisher)"),
}


def main(argv=None) -> int:
    """Dispatch ``rfisher <command> ...`` to the command's own parser."""
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="rfisher",
        description="RFIsher: science tolerances of RFI residuals.",
        epilog="commands:\n" + "\n".join(
            f"  {name:<12} {text}" for name, (_, text) in COMMANDS.items()),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version",
                        version=f"rfisher {__version__}")
    parser.add_argument("command", choices=tuple(COMMANDS),
                        metavar="command")
    parser.add_argument("arguments", nargs=argparse.REMAINDER,
                        help="the command's own arguments (see "
                             "'rfisher <command> --help')")
    args = parser.parse_args(argv)
    command, _ = COMMANDS[args.command]
    return command(args.arguments, prog=f"rfisher {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
