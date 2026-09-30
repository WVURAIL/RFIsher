"""The ``rfisher`` command.

    rfisher forecast     evaluate one uniform masking scenario from a Fisher bank
    rfisher build-bank   build a Fisher bank (slow; needs RadioFisher)
    rfisher tolerance    build, show and reduce the residual tolerance table,
                         and write the two frozen reference tolerances
    rfisher verdict      the screen of each band from a detector handoff
    rfisher response     the known-moment check of the visibility response
    rfisher records      the code of record of the 2026 campaign
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
# These import no science profile reader (PyYAML): a command of record runs
# where the forecast's own dependencies are not installed (tests/test_cli.py).
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


def _table_path(out: Path) -> Path:
    from .forecast.radiofisher_bao.model import TABLE_NAME

    return out / TABLE_NAME if out.is_dir() or not out.suffix else out


def _unscreened_bands(path: Path) -> list[str]:
    """Band ids whose ``role`` column, when the CSV has one, is not screened.

    A handoff manifest lists every band with its role; only its screened
    bands are read, so it has none to refuse.
    """
    import csv

    if path.suffix == ".json":
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return [row["band_id"] for row in csv.DictReader(fh)
                if row.get("role", "screened") != "screened"]


def reference_main(argv=None, prog: str = "rfisher tolerance reference") -> int:
    """Write the frozen reference tolerances as band tolerance rows."""
    from .tolerance import bands, reference, table

    parser = argparse.ArgumentParser(
        prog=prog, description="Write tolerances.csv and "
        "tolerance_components.csv for the bands on one or more frozen "
        "reference bases (the vendored exact-time reference and the "
        "coarse-world sensitivity).")
    parser.add_argument("--basis", action="append", required=True,
                        choices=reference.BASES,
                        help="a reference basis; repeat for several, whose "
                             "rows are written in the order given")
    parser.add_argument("--bands", type=Path, required=True,
                        help="CSV with band_id,low_mhz,high_mhz (an optional "
                             "role column must read screened), or a handoff "
                             "manifest.json, whose screened bands are read")
    parser.add_argument("--out", type=Path, required=True,
                        help="output directory")
    args = parser.parse_args(argv)
    unscreened = _unscreened_bands(args.bands)
    if unscreened:
        parser.error(f"{args.bands}: only screened bands are priced; "
                     f"role is not screened for {', '.join(unscreened)}")
    band_list = bands.read_bands(args.bands)
    tolerances, components = [], []
    for basis in args.basis:
        rows, parts = reference.reference_rows(basis, band_list)
        tolerances += rows
        components += parts
    for path in table.write_bands(tolerances, components, args.out,
                                  reference.provenance(args.basis,
                                                       args.bands)):
        print(f"wrote {path}")
    return 0


def tolerance_main(argv=None, prog: str = "rfisher tolerance") -> int:
    """``rfisher tolerance {build, bands, reference, show, bias}``."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["reference"]:
        return reference_main(argv[1:], prog=f"{prog} reference")
    from .forecast.radiofisher_bao import response
    from .forecast.radiofisher_bao.model import RadioFisherBAO, packaged_table
    from .tolerance import bands, table

    if argv[:1] == ["bias"]:
        return response.bias_main(argv[1:], prog=f"{prog} bias")
    parser = argparse.ArgumentParser(
        prog=prog, description="The residual tolerance table: "
        "'build' prices every scenario, bin and parameter of the science "
        "model; 'bands' reduces the table to one tolerance per band and "
        "scenario; 'reference' writes the frozen reference tolerances in the "
        "same layout; 'show' prints it; 'bias' reports the full response of "
        "one bank (see 'rfisher tolerance bias --help').")
    actions = parser.add_subparsers(dest="action", required=True,
                                    metavar="{build,bands,reference,show,bias}")
    built = actions.add_parser(
        "build", help="recompute the per-bin table and its provenance")
    built.add_argument("--project", type=Path, required=True,
                       help="the science profile directory")
    built.add_argument("--banks", type=Path,
                       help="response bank directory (default: packaged)")
    built.add_argument("--out", type=Path, required=True,
                       help="the table file, or a directory for it")
    built.add_argument("--radiofisher-dir", type=Path)
    built.add_argument("--accept-new", action="store_true",
                       help="replace an existing table whose bytes change")
    reduced = actions.add_parser(
        "bands", help="write tolerances.csv and tolerance_components.csv")
    reduced.add_argument("--project", type=Path, required=True)
    reduced.add_argument("--bands", type=Path, required=True,
                         help="CSV with band_id,low_mhz,high_mhz (an "
                              "optional role column must read screened), or "
                              "a handoff manifest.json, whose screened bands "
                              "are read")
    reduced.add_argument("--out", type=Path, required=True,
                         help="output directory")
    reduced.add_argument("--table", type=Path,
                         help="the per-bin table (default: packaged)")
    reduced.add_argument("--banks", type=Path,
                         help="response bank directory the table was built "
                              "from (default: packaged)")
    shown = actions.add_parser("show", help="print the per-bin table")
    shown.add_argument("--table", type=Path,
                       help="the per-bin table (default: packaged)")
    shown.add_argument("--project", type=Path,
                       help="also verify the table's recorded inputs against "
                            "this science profile and the current code")
    shown.add_argument("--banks", type=Path,
                       help="response bank directory the table was built "
                            "from (default: packaged)")
    actions.add_parser("reference", help="the frozen reference tolerances "
                       "(see 'rfisher tolerance reference --help')")
    actions.add_parser("bias", help="the full response report of one bank")
    args = parser.parse_args(argv)

    if args.action == "build":
        model = RadioFisherBAO(args.project, response_banks_dir=args.banks,
                               rf_dir=args.radiofisher_dir)
        out = _table_path(args.out)
        try:
            rows = table.build(model, out, accept_new=args.accept_new)
        except ValueError as exc:
            parser.error(str(exc))
        print(f"wrote {out} ({len(rows)} rows) and {table.sidecar(out).name}")
        return 0
    source = args.table or packaged_table()
    model = (RadioFisherBAO(args.project, response_banks_dir=args.banks)
             if args.project is not None else None)
    try:
        if model is not None:
            table.verify(model, source)
        rows = table.load(source)
    except ValueError as exc:
        parser.error(str(exc))
    if args.action == "show":
        checked = ("inputs verified" if model is not None
                   else "inputs not verified; pass --project")
        print(f"{source} (csv_sha256 authenticated; {checked})")
        for row in rows:
            value = (f"{row['tolerance']:.6g}" if row["at_target"]
                     else "refused")
            print(f"  {row['world']:<9} bin {row['bin_index']:>2} "
                  f"z {row['z_lo']:.4g}-{row['z_hi']:.4g} "
                  f"{row['parameter']:<6} {value}")
        return 0
    unscreened = _unscreened_bands(args.bands)
    if unscreened:
        parser.error(f"{args.bands}: only screened bands are priced; "
                     f"role is not screened for {', '.join(unscreened)}")
    band_list = bands.read_bands(args.bands)
    tolerances, components = bands.band_tolerances(model, rows, band_list)
    written = table.write_bands(tolerances, components, args.out, {
        "schema": table.IDENTITY_SCHEMA,
        "table": source.name,
        "table_csv_sha256": table.sha256_file(source),
        "bands_sha256": table.sha256_file(args.bands),
        "profile_sha256": table.sha256_file(model.profile_path),
    })
    for path in written:
        print(f"wrote {path}")
    return 0


def verdict_main(argv=None, prog: str = "rfisher verdict") -> int:
    """``rfisher verdict archive``."""
    parser = argparse.ArgumentParser(
        prog=prog, description="The screen of each band: the deployable set "
        "of thresholds [eta_Pfa, eta_sci] from the detector's handoff and one "
        "tolerance table, the selector inside it, and keep, excise or "
        "undetermined under the declared precedence.")
    actions = parser.add_subparsers(dest="action", required=True,
                                    metavar="{archive}")
    archive = actions.add_parser(
        "archive", help="the verdict of a characterization directory")
    archive.add_argument("--project", type=Path, required=True,
                         help="the science profile directory (its registers "
                              "and its residual reference)")
    archive.add_argument("--characterization", type=Path, required=True,
                         help="the handoff: oc_table.csv, oc_summary.csv and "
                              "manifest.json")
    archive.add_argument("--tolerances", type=Path, required=True,
                         help="tolerances.csv, or the directory holding it")
    archive.add_argument("--out", type=Path, required=True,
                         help="output directory")
    args = parser.parse_args(argv)
    from .verdict import handoff
    from .verdict.archive import verdict_archive

    try:
        result = verdict_archive(args.characterization, args.tolerances,
                                 args.project, args.out)
    except handoff.HandoffError as exc:
        parser.error(str(exc))
    counts = {}
    for row in result["screen"]:
        counts[row["screen_outcome"]] = counts.get(row["screen_outcome"], 0) + 1
    print(f"wrote {args.out}: " + ", ".join(
        f"{n} {k}" for k, n in sorted(counts.items())))
    return 0


def response_main(argv=None, prog: str = "rfisher response") -> int:
    """``rfisher response visibility``."""
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog=prog, description="The linear parameter response of masked "
        "visibilities: 'visibility' runs its known-moment synthetic check "
        "(see 'rfisher response visibility --help').")
    parser.add_argument("action", choices=("visibility",))
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    from .response import validate

    return validate.main(args.arguments, prog=f"{prog} {args.action}")


# The capture records keep the release producer's own argument handling:
# each module's main(argv) reads its arguments and prints its usage on --help.
CAPTURE_RECORDS = {
    "table-of-record": ("table_of_record", "the table of record before "
                        "amendment 8 (v7) from the capture handoff"),
    "capture-ruling": ("capture_ruling", "the capture ruling under a rule "
                       "file (the table of record at 'record')"),
    "cohort-basis": ("cohort_basis", "channel 24 on its 2020 cohort basis "
                     "(borrowed, or its own in-band measurement)"),
    "robustness": ("robustness", "the robustness margins of the excisions"),
    "phase-limit": ("phase_limit", "the exclusion-side phase limit on the "
                    "coherence gain"),
    "duration": ("duration", "the keep gap and the survey-duration reading"),
    "postprocessing": ("postprocessing", "the post-processing sensitivity "
                       "against the credit readings"),
    "filter-sensitivity": ("filter_sensitivity", "revision 3's filter "
                           "sensitivity against revision 2"),
}


def records_main(argv=None, prog: str = "rfisher records") -> int:
    """``rfisher records ...``: the code of record of the 2026 campaign."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in CAPTURE_RECORDS:
        import importlib

        module = importlib.import_module(
            f".records.chime_atsc_2026.{CAPTURE_RECORDS[argv[0]][0]}",
            __package__)
        if "-h" in argv[1:] or "--help" in argv[1:]:
            print(module.__doc__.strip())
            return 0
        return module.main(argv[1:])
    parser = argparse.ArgumentParser(
        prog=prog, description="Code of record of the 2026 CHIME DTV "
        "campaign: the frozen release layouts and the capture ruling of "
        "record, written from the handoffs.",
        epilog="capture records (each prints its usage on --help):\n"
        + "\n".join(f"  {name:<18} {text}"
                    for name, (_, text) in CAPTURE_RECORDS.items()),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    actions = parser.add_subparsers(dest="action", required=True,
                                    metavar="{archive-layout,"
                                    + ",".join(CAPTURE_RECORDS) + "}")
    layout = actions.add_parser(
        "archive-layout", help="the frozen layout of an archive release")
    layout.add_argument("--release", required=True,
                        choices=("archive_author_eras_2026_09_23",
                                 "archive_no_split_2026_09_24_r2"))
    layout.add_argument("--characterization", type=Path, required=True,
                        help="the detector's characterization directory")
    layout.add_argument("--tolerances", type=Path, required=True,
                        help="the band tolerance table (rfisher tolerance "
                             "bands), or its directory")
    layout.add_argument("--project", type=Path, required=True,
                        help="the science profile directory")
    layout.add_argument("--out", type=Path, required=True,
                        help="output directory (must not exist)")
    args = parser.parse_args(argv)
    from .records.chime_atsc_2026 import compat_tables

    if args.out.exists():
        parser.error(f"{args.out} exists; the layout is written into a new "
                     "directory")
    try:
        result = compat_tables.write_archive_layout(
            args.release, args.characterization, args.tolerances,
            args.project, args.out)
    except (compat_tables.NotReproducible, ValueError) as exc:
        parser.error(str(exc))
    print(f"wrote {args.out}: {result['bands']} bands, priced "
          f"{', '.join(result['priced'])}")
    return 0


COMMANDS = {
    "forecast": (forecast_main,
                 "evaluate one uniform masking scenario from a Fisher bank"),
    "build-bank": (build_bank_main,
                   "build a Fisher bank (slow; needs RadioFisher)"),
    "tolerance": (tolerance_main,
                  "build, show and reduce the residual tolerance table"),
    "verdict": (verdict_main,
                "the screen of each band from a detector handoff and a "
                "tolerance table"),
    "response": (response_main,
                 "the known-moment check of the visibility response"),
    "records": (records_main,
                "the code of record of the 2026 campaign (frozen layouts)"),
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
