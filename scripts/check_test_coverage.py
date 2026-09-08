"""Enforce package-wide and per-component branch-inclusive test coverage."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ("rfisher", "rfisher_results")
MIN_TOTAL = 85.0
MIN_COMPONENT = 70.0
# These boundaries must retain their stronger coverage even if reports grow.
CRITICAL = {
    "src/rfisher/_validation.py": 100.0,
    "src/rfisher/npzio.py": 95.0,
    "src/rfisher/thresholds.py": 95.0,
    "src/rfisher/forecast.py": 90.0,
    "src/rfisher/archive_acceptance.py": 85.0,
    "src/rfisher_results/archive/blocks.py": 90.0,
}


def check(report: dict, root: Path = ROOT) -> list[str]:
    """Return failures, including source files entirely absent from the report."""
    failures = []
    if report.get("meta", {}).get("branch_coverage") is not True:
        return ["branch coverage is required; run pytest --cov --cov-branch"]
    files = report["files"]
    expected = {path.relative_to(root).as_posix()
                for package in PACKAGES for path in (root / "src" / package).rglob("*.py")}
    if not expected:
        return ["no package source files found"]
    missing = expected - files.keys()
    failures.extend(f"{name}: absent from coverage report" for name in sorted(missing))
    covered = possible = 0
    for name in sorted(expected & files.keys()):
        summary = files[name]["summary"]
        numerator = summary["covered_lines"] + summary["covered_branches"]
        denominator = summary["num_statements"] + summary["num_branches"]
        covered += numerator
        possible += denominator
        percentage = 100 * numerator / denominator if denominator else 100.0
        minimum = CRITICAL.get(name, MIN_COMPONENT)
        if percentage + 1e-9 < minimum:
            failures.append(f"{name}: {percentage:.2f}% < {minimum:g}%")
    total = 100 * covered / possible if possible else 0.0
    if total + 1e-9 < MIN_TOTAL:
        failures.append(f"total: {total:.2f}% < {MIN_TOTAL:g}%")
    return failures


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", nargs="?", type=Path, default=ROOT / "coverage.json")
    args = parser.parse_args(argv)
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
        failures = check(report)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Cannot read a complete coverage report: {exc}")
        return 1
    for failure in failures:
        print(f"FAIL {failure}")
    if failures:
        return 1
    print(f"Coverage gates passed: total >= {MIN_TOTAL:g}%; every component >= {MIN_COMPONENT:g}% "
          "with stronger gates on critical boundaries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
