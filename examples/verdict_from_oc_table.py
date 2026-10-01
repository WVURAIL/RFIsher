"""The verdict of a detector handoff: its bands priced against the shipped tolerance table.

pilot-proxy hands the science side one directory per characterization (oc_table.csv, oc_summary.csv and
manifest.json, schema operating_characteristic_v1). This example reads the small golden handoff of this repository's
tests (two bands of a synthetic archive), reduces the shipped per-bin tolerance table to its bands
(``rfisher tolerance bands``), runs the archive verdict (``rfisher verdict archive``) and prints, per band and
scenario, the tolerance, eta_sci, the deployable interval [max(eta_Pfa, eta_eval), eta_sci] and the least R.
Run it from a source checkout: ``python examples/verdict_from_oc_table.py``.
"""
import csv
import tempfile
from pathlib import Path

from rfisher.cli import main
from rfisher.verdict.archive import verdict_archive

ROOT = Path(__file__).resolve().parents[1]
HANDOFF = ROOT / "tests" / "golden" / "handoff" / "archive"
PROJECT = ROOT / "projects" / "chime_bao"


def cell(row, key, fmt="{:.3g}"):
    return fmt.format(float(row[key])) if row.get(key) else "-"


with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    main(["tolerance", "bands", "--project", str(PROJECT), "--bands", str(HANDOFF / "manifest.json"),
          "--out", str(tmp / "tolerances")])
    result = verdict_archive(HANDOFF, tmp / "tolerances", PROJECT, tmp / "verdict")
    with open(tmp / "verdict" / "verdict.csv", newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if r["threshold_family"] == "union"]
    print("band scenario   r_tol      eta_sci  interval             least R  status")
    for r in rows:
        interval = f"[{cell(r, 'interval_low')}, {cell(r, 'interval_high')}]"
        print(f"{r['band_id']:>4} {r['scenario']:<10} {cell(r, 'r_tol'):<10} {cell(r, 'eta_sci'):<8} {interval:<20} "
              f"{cell(r, 'min_R'):<8} {r['interval_status']}")
    for s in result["screen"]:
        print(f"band {s['band_id']}: {s['screen_outcome']} ({s['screen_reason']})")
