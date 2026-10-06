"""The archive layout writer end to end, on a characterization built from the two-band golden extract.

The golden extract (bands 18 and 33 of both releases) carries each band's marked fine rows, coarse-ladder rows,
summary rows, ledger record, chain row and rule tolerance. Here they are written back into a characterization
directory, with a fine surface filled in around the marked rows and the 108-value coarse grid, and the whole layout is
written. The rows that do not depend on the filled-in surface are the frozen ones; the rest are checked for their
layout. The full layouts are compared with the releases at the gate.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
from pathlib import Path

import pytest

from rfisher.records.chime_atsc_2026 import compat_tables as ct
from rfisher.records.chime_atsc_2026 import ladder_pricing
from rfisher.verdict import handoff

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "projects" / "chime_bao"
GOLDEN = ROOT / "tests" / "golden" / "records" / "archive_layout_18_33.json.gz"


@pytest.fixture(scope="module")
def golden():
    return json.loads(gzip.decompress(GOLDEN.read_bytes()))


def _write_rows(path, columns, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _surface(rows, summary):
    """The marked fine rows of the summary's families, with 250 more candidates of each family around them (a
    residual above the family's least) and the coarse grid of 108 values."""
    families = {s["threshold_family"] for s in summary if s["candidate_set"] == "fine_surface"}
    fine = [r for r in rows if r["candidate_set"] == "fine_surface" and f"rho={r['rho']}" in families]
    out = [r for r in rows if r["candidate_set"] != "fine_surface"] + fine
    for m in fine:
        for i in range(1, 251):
            out.append({**m, "mark": "", "candidate_order": str(int(m["candidate_order"]) + i),
                        "eta_q16": str(int(m["eta_q16"]) + i), "r_sys": repr(float(m["r_sys"]) * (1.0 + 1e-3 * i))})
    ladder = next(r for r in rows if r["candidate_set"] == "coarse_ladder")
    for i in range(ct.COARSE_GRID_SIZE):
        out.append({**ladder, "candidate_set": "coarse_surface", "block": "calibration", "candidate_order": str(i),
                    "eta": repr(1.0 + 0.01 * i), "policy": "", "r_sys": repr(float(ladder["r_sys"] or 1.0) * (1 + i))})
    return out


def _characterization(golden, release, root):
    doc = golden["releases"][release]
    columns = [c["name"] for c in handoff.schema()["x-oc-table-columns"]]
    summary_columns = [c["name"] for c in handoff.schema()["x-oc-summary-columns"]]
    table, summary, chain, tolerances = [], [], [], []
    for band in golden["bands"]:
        entry = doc["bands"][band]
        table += _surface(entry["rows"], entry["summary"])
        summary += entry["summary"]
        chain += entry["chain"]
        # the band tolerance layout no longer has a suppression column (stage P); the frozen rule row's is 0
        assert all(float(t["suppression_db"]) == 0.0 for t in entry["tolerance"])
        tolerances += [{k: v for k, v in t.items() if k != "suppression_db"} for t in entry["tolerance"]]
        record = entry["record"]
        path = root / "ledger" / "channels" / f"ch{int(band):02d}_fid{record['freq_id']}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record))
    _write_rows(root / "oc_table.csv", columns, table)
    _write_rows(root / "oc_summary.csv", summary_columns, summary)
    _write_rows(root / "tables" / "chain.csv", list(chain[0]), chain)
    (root / "ledger" / "run.json").write_text(json.dumps({
        "generated": "2026-09-23T00:00:00", "producer": {"source_root": "pilot-proxy/src"}, "products_dir": "products",
        "channels": [int(b) for b in golden["bands"]], "provisional": {"stability.maximum_systematic_residual_ratio": 1.2},
        "errors": [], "seconds": 1.0}))
    manifest = dict(doc["manifest"])
    manifest["bands"] = [b for b in manifest["bands"] if b["band_id"] in golden["bands"]]
    manifest["files"] = {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                         for name in ("oc_table.csv", "oc_summary.csv")}
    (root / "manifest.json").write_text(json.dumps(manifest))
    tol = root.parent / "tolerances.csv"
    _write_rows(tol, list(handoff.TOLERANCE_COLUMNS), tolerances)
    return root, tol


@pytest.mark.parametrize("release", ct.RELEASES)
def test_the_layout_is_written_end_to_end(golden, tmp_path, release):
    char, tol = _characterization(golden, release, tmp_path / "characterization")
    out = tmp_path / "release"
    result = ct.write_archive_layout(release, char, tol, PROJECT, out)
    assert result == {"priced": golden["bands"], "bands": 2}
    frozen = golden["releases"][release]["bands"]

    def rows(path):
        with path.open(newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    retired = ("r_tol_fs8", "fs8_status")   # stage P: the growth rate sets no tolerance
    assert rows(out / "tables" / "channel_tolerances.csv") == [
        {k: v for k, v in frozen[b]["frozen"]["channel_tolerances"][0].items() if k not in retired}
        for b in golden["bands"]]
    chain = rows(out / "tables" / "chain.csv")
    assert [r["channel"] for r in chain] == golden["bands"]
    assert all(r["delay_key"] == "none" and float(r["delay_suppression_db"]) == 0.0 for r in chain)
    listed = knees = 0
    for band in golden["bands"]:
        ch = out / "channels" / f"ch{int(band):02d}"
        points = rows(ch / "operating_points.csv")
        by_rank = {}
        for r in points:
            by_rank.setdefault(r["rho"], []).append(r)
        listed += len(points)
        assert all(len(v) <= ct.MAX_POINTS_PER_RHO + 1 for v in by_rank.values())
        assert all(r["selected"] == "False" and r["feasible"] == "False" for r in points)
        assert len(rows(ch / "coarse_frontier.csv")) == ct.COARSE_GRID_SIZE
        if points:   # the knee report is written where the band lists candidates
            assert [r["channel"] for r in rows(ch / "operating_point.csv")] == [band]
            knees += 1
        record = json.loads(next((out / "ledger" / "channels").glob(f"ch{int(band):02d}_*.json")).read_text())
        assert record["sections"]["tolerance"] == {
            k: v for k, v in frozen[band]["frozen"]["ledger"]["sections"]["tolerance"].items() if k not in retired}
        assert set(record) == set(frozen[band]["frozen"]["ledger"])
        assert "worlds" not in record["sections"]
    assert listed
    run = json.loads((out / "ledger" / "run.json").read_text())
    assert run["schema"] == ct.LEDGER_SCHEMA and len(run["channels"]) == 2
    assert run["producer"]["repository"] == ct.PRODUCER_REPOSITORY and run["producer"]["module"] == ct.PRODUCER_MODULE
    assert run["provisional"]["occupancy_wall_masked_fraction"] == ct.OCCUPANCY_WALL_MASKED_FRACTION
    assert len(rows(out / "ledger" / "ledger.csv")) == 2
    assert len(rows(out / "coarse" / "ladder_pricing.csv")) == 2 * len(ladder_pricing.POLICIES)
    for name in ("selection.csv", "screening.csv"):
        assert len(rows(out / "tables" / name)) == 2, name
    assert not (out / "tables" / "worlds.csv").exists()
    assert "worlds_contract" not in run
    assert len(rows(out / "tables" / "operating_points.csv")) == knees


def test_a_characterization_with_the_booked_split_is_refused(golden, tmp_path):
    """The golden still holds the author-eras release, whose characterization booked the variance split; its
    layout is retired with stage P, and such a characterization is refused."""
    char, tol = _characterization(golden, "archive_author_eras_2026_09_23", tmp_path / "characterization")
    with pytest.raises(ValueError, match="characterized as"):
        ct.read_inputs(ct.RELEASES[0], char, tol, PROJECT)
    for release in ("archive_author_eras_2026_09_23", "archive_2020"):
        with pytest.raises(ValueError, match="unknown release"):
            ct.read_inputs(release, char, tol, PROJECT)


def test_a_short_coarse_grid_is_not_reproducible(golden, tmp_path):
    char, tol = _characterization(golden, ct.RELEASES[0], tmp_path / "characterization")
    inp = ct.read_inputs(ct.RELEASES[0], char, tol, PROJECT)
    p = ct.price(inp, "18")
    inp.coarse["18"] = inp.coarse["18"][:10]
    with pytest.raises(ct.NotReproducible, match="coarse candidates"):
        ct.coarse_frontier_rows(inp, p)
    inp.coarse["18"] = []
    assert ct.coarse_frontier_rows(inp, p) == []


def test_the_ladder_pricing_states_what_it_cannot_price():
    assert ladder_pricing.price(1.0, 2.0, math.nan) == {"status": "unpriced target-time tolerance"}
    assert ladder_pricing.price(math.nan, 2.0, 0.5) == {"status": "residual allowance unavailable"}
    row = ladder_pricing.price(1.0, math.nan, 0.5)
    assert row["chain_status"] == "calibration chain gain unavailable" and row["G1_tolerance_fraction"] == 2.0
    row = ladder_pricing.price(0.25, 4.0, 0.5)
    assert row["chain_tolerance_fraction"] == 2.0 and row["G1_required_suppression_db"] == 0.0


def test_the_layout_reads_the_frozen_policy_not_the_projects(golden, tmp_path):
    """The declared change of the fine rank (or any later policy change) moves the verdict, never these layouts."""
    import shutil
    assert ct.frozen_policy().sha256() == "05dfa2a6f448530e2517c7406d58eb0dd5f357bb88fb7f3e2383f94d78d73203"
    project = tmp_path / "project"
    shutil.copytree(PROJECT, project)
    path = project / "selector_policy.json"
    doc = json.loads(path.read_text())
    entry = next(d for d in doc["decisions"] if d["id"] == "selector.fine_rank")
    entry["value"] = 63
    path.write_text(json.dumps(doc, indent=2) + "\n")
    release = ct.RELEASES[0]
    char, tol = _characterization(golden, release, tmp_path / "characterization")
    a, b = tmp_path / "a", tmp_path / "b"
    ct.write_archive_layout(release, char, tol, PROJECT, a)
    ct.write_archive_layout(release, char, tol, project, b)
    files = sorted(p.relative_to(a) for p in a.rglob("*") if p.is_file())
    assert files == sorted(p.relative_to(b) for p in b.rglob("*") if p.is_file())
    for rel in files:
        if rel.name != "run.json":
            assert (a / rel).read_bytes() == (b / rel).read_bytes(), rel
    run_a, run_b = (json.loads((d / "ledger" / "run.json").read_text()) for d in (a, b))
    assert run_a["producer"]["policy_sha256"] == run_b["producer"]["policy_sha256"] == ct.frozen_policy().sha256()
