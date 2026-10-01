"""A writable copy of the detector's golden handoff, and tolerance tables for it."""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
from pathlib import Path

import pytest

GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "handoff" / "archive"
TOLERANCE_HEADER = ("band_id,band_low_mhz,band_high_mhz,scenario,role,r_tol,"
                    "binding_parameter,binding_bin,zeta,target_time_years,"
                    "suppression_db,tolerance_basis,refusal\n")
EDGES = {"29": (560.0, 566.0), "34": (590.0, 596.0)}


def _rehash(root: Path) -> None:
    manifest = json.loads((root / "manifest.json").read_text())
    for name in manifest["files"]:
        manifest["files"][name] = hashlib.sha256(
            (root / name).read_bytes()).hexdigest()
    (root / "manifest.json").write_text(json.dumps(manifest, indent=1,
                                                   sort_keys=True))


def _edit_summary(root: Path, **changes) -> None:
    path = root / "oc_summary.csv"
    with path.open(newline="") as fh:
        reader = csv.DictReader(fh)
        header, rows = reader.fieldnames, list(reader)
    for row in rows:
        row.update(changes)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    _rehash(root)


@pytest.fixture
def handoff_copy(tmp_path):
    """The golden handoff, copied; ``edit(**changes)`` rewrites every summary
    row and re-records the manifest's digests."""
    root = tmp_path / "characterization"
    shutil.copytree(GOLDEN, root)

    class Copy:
        path = root

        @staticmethod
        def edit(**changes):
            _edit_summary(root, **changes)

    return Copy


@pytest.fixture
def tolerances(tmp_path):
    """Write a tolerances.csv: ``{band: [(scenario, role, r_tol, S), ...]}``."""
    def write(spec, name="tolerances.csv"):
        path = tmp_path / name
        lines = [TOLERANCE_HEADER]
        for band, entries in spec.items():
            low, high = EDGES[band]
            for scenario, role, r_tol, sdb in entries:
                lines.append(f"{band},{low!r},{high!r},{scenario},{role},"
                             f"{'' if r_tol is None else repr(r_tol)},,,1.0,"
                             f"1.0,{sdb!r},grid_T1yr_stability_gated,"
                             f"{'refused' if r_tol is None else ''}\n")
        path.write_text("".join(lines), encoding="utf-8")
        return path

    return write
