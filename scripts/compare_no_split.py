"""Reconcile the no-split archive release against the author-eras release, rewriting neither.

Adapted from compare_reanalysis_redated.py (which reconciles a re-dated release against
2026-09-09). Here the eras, products, banks and tolerances are the same in both releases and
the only change is the chain booking (RFIsher 4466028: all surviving power at one coherence
time, no variance-split credit). Expected: every changed table cell is on one of the nine
bands whose era tau_c is usable; every changed ledger field is on those nine bands, except
chain_archive.chain_gain (the archive-wide chain recorded beside the era chain, in no table)
on any channel whose archive-wide tau_c is usable, which the same rule rebooks; the three split
fields (intraday_share, fast_share, ground_filter_db) are removed from both chain sections on
every channel; nothing else is added or removed; no primary assessment changes.

Table columns are read from each CSV's header on both sides, so a header-only table (no data
rows) compares its columns like any other. The verdict ``passed`` also requires that no table
column was added and that the removed table columns are exactly the split columns (in
``chain.csv`` and, prefixed by section, in ``ledger.csv``).

    python scripts/compare_no_split.py --old <author-eras release> --new <no-split release> --out DIR
"""
from pathlib import Path
import argparse, csv, hashlib, json, math
from collections import Counter

USABLE = [16, 17, 18, 24, 29, 30, 31, 33, 35]
SPLIT = ("intraday_share", "fast_share", "ground_filter_db")
REMOVED = {f"{s}.{f}" for s in ("chain", "chain_archive") for f in SPLIT}
REMOVED_COLUMNS = ({("archive/tables/chain.csv", f) for f in SPLIT}
                   | {("archive/ledger/ledger.csv", f"{s}_{f}") for s in ("chain", "chain_archive") for f in SPLIT})
TABLES = ["archive/tables", "coarse"]


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load(root):
    run = json.loads((root / "ledger/run.json").read_text())
    docs = {}
    for path in sorted((root / "ledger/channels").glob("*.json")):
        doc = json.loads(path.read_text())
        docs[int(doc["channel"])] = doc
    assert set(docs) == set(range(14, 37))
    return run, docs


def flatten(x, prefix=""):
    if isinstance(x, dict):
        return {k: v for name, value in x.items() for k, v in flatten(value, prefix + "." + name if prefix else name).items()}
    return {prefix: x}


def finite(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def num(s):
    try:
        v = float(s)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def assess(s):
    t = s.get("tolerance") or {}
    sel = s.get("selection") or {}
    if not finite(t.get("r_tol_dilation")):
        return "unpriced by primary Fisher gate"
    return {"refused": "preparation refused", "no feasible point": "no feasible point under assigned residual model",
            "feasible": "numerically feasible; inspect evidence and drift gates"}.get(sel.get("status"), "unresolved; inspect ledger")


def table_cells(old_root, new_root):
    """Every changed cell of every CSV (TABLES, archive/channels/chNN, archive/ledger), rows matched by position with the key columns checked."""
    cells, removed_columns, added_columns, files = [], [], [], {}
    paths = [p for sub in TABLES for p in sorted((old_root / sub).glob("*.csv"))]
    paths += sorted(old_root.glob("archive/channels/ch*/*.csv")) + [old_root / "archive/ledger/ledger.csv"]
    for old_path in paths:
        rel = old_path.relative_to(old_root).as_posix()
        new_path = new_root / rel
        if not new_path.exists():
            files[rel] = "missing in new"
            continue
        # columns from each side's header, so a header-only table compares like any other
        with old_path.open(newline="") as f:
            reader = csv.DictReader(f)
            old_fields = list(reader.fieldnames or [])
            old_rows = list(reader)
        with new_path.open(newline="") as f:
            reader = csv.DictReader(f)
            new_fields = list(reader.fieldnames or [])
            new_rows = list(reader)
        removed_columns += [{"table": rel, "column": c} for c in old_fields if c not in new_fields]
        added_columns += [{"table": rel, "column": c} for c in new_fields if c not in old_fields]
        assert len(old_rows) == len(new_rows), rel
        key = [k for k in ("channel", "e_min", "policy", "flagger", "era", "label", "basis") if k in old_fields]
        n = 0
        directory_channel = str(int(old_path.parent.name[2:])) if old_path.parent.name.startswith("ch") else ""
        for i, (a, b) in enumerate(zip(old_rows, new_rows)):
            assert all(a[k] == b[k] for k in key), (rel, i, key)
            a.setdefault("channel", directory_channel)
            for c in old_fields:
                if c in new_fields and a[c] != b[c]:
                    x, y = num(a[c]), num(b[c])
                    cells.append({"table": rel, "row": i, "key": ";".join(f"{k}={a[k]}" for k in key), "channel": a.get("channel", ""),
                                  "column": c, "prior": a[c], "current": b[c],
                                  "ratio": y / x if x not in (None, 0.0) and y is not None else ""})
                    n += 1
        files[rel] = "byte-identical" if digest(old_path) == digest(new_path) else f"{n} changed cells"
    return cells, removed_columns, added_columns, files


def verdict(*, outside, outside_cells, unkeyed_cells, removed_ok, added, channels, removed_columns, added_columns) -> dict:
    """The checks behind ``passed``, and ``passed`` itself: every one must hold."""
    checks = {
        "no_unexpected_ledger_changes": not outside,
        "no_unexpected_table_cell_changes": not outside_cells,
        "no_table_cell_change_without_channel_key": not unkeyed_cells,
        "removed_fields_exactly_the_split_fields": bool(removed_ok),
        "no_added_fields": not added,
        "no_added_columns": not added_columns,
        "removed_columns_exactly_the_split_columns": {(c["table"], c["column"]) for c in removed_columns} == REMOVED_COLUMNS,
        "primary_assessments_unchanged": all(c["primary_assessment"] == c["primary_assessment_prior"] for c in channels),
    }
    return {"passed": all(checks.values()), "checks": checks}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--old", type=Path, required=True, help="the author-eras release root")
    parser.add_argument("--new", type=Path, required=True, help="the no-split release root")
    parser.add_argument("--out", type=Path, required=True)
    a = parser.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    old_run, old = load(a.old / "archive")
    new_run, new = load(a.new / "archive")
    assert old_run["products"] == new_run["products"]
    assert old_run.get("era_overrides") == new_run.get("era_overrides")
    diffs, removed, added, channels = [], [], [], []
    for ch in new:
        assert old[ch]["product_sha256"] == new[ch]["product_sha256"]
        previous, current = flatten(old[ch]["sections"]), flatten(new[ch]["sections"])
        for field in sorted(set(previous) | set(current)):
            if field not in current:
                removed.append({"channel": ch, "field": field, "prior": previous[field]})
                continue
            if field not in previous:
                added.append({"channel": ch, "field": field, "current": current[field]})
                continue
            before, after = previous[field], current[field]
            if before != after:
                diffs.append({"channel": ch, "usable_tau": ch in USABLE, "field": field, "prior": before, "current": after,
                              "ratio": after / before if finite(before) and finite(after) and before != 0 else None})
        so, sn = old[ch]["sections"], new[ch]["sections"]
        channels.append({"channel": ch, "usable_tau": ch in USABLE,
                         "tau_quality": (sn.get("chain") or {}).get("tau_quality"),
                         "primary_assessment_prior": assess(so), "primary_assessment": assess(sn),
                         "selection_status_prior": (so.get("selection") or {}).get("status"),
                         "selection_status": (sn.get("selection") or {}).get("status"),
                         "screening_class_prior": (so.get("screening") or {}).get("screening_class"),
                         "screening_class": (sn.get("screening") or {}).get("screening_class"),
                         "chain_gain_prior": (so.get("chain") or {}).get("chain_gain"),
                         "chain_gain": (sn.get("chain") or {}).get("chain_gain"),
                         "physical_recovery_certified": False})
    cells, removed_columns, added_columns, files = table_cells(a.old, a.new)
    archive_usable = {ch for ch in new if ((new[ch]["sections"].get("chain_archive") or {}).get("tau_quality")) in ("measured", "bounded_above")}
    expected_outside = [d for d in diffs if not d["usable_tau"] and d["field"] == "chain_archive.chain_gain" and d["channel"] in archive_usable]
    outside = [d for d in diffs if not d["usable_tau"] and d not in expected_outside]
    expected_outside_cells = [c for c in cells if c["channel"] and int(c["channel"]) not in USABLE and c["table"] == "archive/ledger/ledger.csv"
                              and c["column"] == "chain_archive_chain_gain" and int(c["channel"]) in archive_usable]
    outside_cells = [c for c in cells if c["channel"] and int(c["channel"]) not in USABLE and c not in expected_outside_cells]
    unkeyed_cells = [c for c in cells if not c["channel"]]
    removed_ok = {(r["channel"], r["field"]) for r in removed} == {(c, f) for c in range(14, 37) for f in REMOVED}
    # the three full calibration surfaces (archive/channels/chNN/operating_points.csv, ~25k points each) are
    # summarised per column against the channel's chain-gain factor rather than listed cell by cell
    factor = {c["channel"]: float(c["ratio"]) for c in cells if c["table"] == "archive/tables/chain.csv" and c["column"] == "chain_gain"}
    surface = lambda c: c["table"].startswith("archive/channels/") and c["table"].endswith("/operating_points.csv")
    summary_rows = {}
    for c in cells:
        if not surface(c):
            continue
        k = (c["table"], c["channel"], c["column"])
        r = summary_rows.setdefault(k, {"table": c["table"], "channel": c["channel"], "column": c["column"], "changed_cells": 0,
                                        "gain_factor": factor.get(c["channel"], ""), "ratio_min": math.inf, "ratio_max": -math.inf,
                                        "all_equal_gain_factor": True})
        r["changed_cells"] += 1
        x = float(c["ratio"]) if c["ratio"] != "" else math.nan
        r["ratio_min"], r["ratio_max"] = min(r["ratio_min"], x), max(r["ratio_max"], x)
        f = factor.get(c["channel"])
        r["all_equal_gain_factor"] = bool(r["all_equal_gain_factor"] and f and math.isfinite(x) and abs(x / f - 1) < 1e-9)
    listed = [c for c in cells if not surface(c)]
    for name, rows, keys in [("channel-assessment.csv", channels, None),
                             ("changed-surface-columns.csv", list(summary_rows.values()),
                              ["table", "channel", "column", "changed_cells", "gain_factor", "ratio_min", "ratio_max", "all_equal_gain_factor"]),
                             ("changed-fields.csv", diffs, ["channel", "usable_tau", "field", "prior", "current", "ratio"]),
                             ("removed-fields.csv", removed, ["channel", "field", "prior"]),
                             ("changed-cells.csv", listed, ["table", "row", "key", "channel", "column", "prior", "current", "ratio"])]:
        with (a.out / name).open("x", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys or list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    inputs = {str(a.old / "archive/ledger/run.json"): digest(a.old / "archive/ledger/run.json"),
              str(a.new / "archive/ledger/run.json"): digest(a.new / "archive/ledger/run.json"), str(Path(__file__)): digest(Path(__file__))}
    summary = {
        "schema": "no-split-archive-reconciliation-v1",
        **verdict(outside=outside, outside_cells=outside_cells, unkeyed_cells=unkeyed_cells, removed_ok=removed_ok, added=added,
                  channels=channels, removed_columns=removed_columns, added_columns=added_columns),
        "channels": 23, "product_identities_equal": True, "era_overrides_equal": True,
        "usable_tau_channels": USABLE,
        "ledger_changes_outside_usable_channels": len(outside) + len(expected_outside),
        "ledger_changes_outside_usable_channels_expected": [{"channel": d["channel"], "field": d["field"], "prior": d["prior"], "current": d["current"],
                                                             "why": "archive-wide chain (chain_archive): its tau_c is usable on this channel although the era tau_c is refused; recorded in the ledger only"}
                                                            for d in expected_outside],
        "ledger_changes_outside_usable_channels_unexpected": len(outside),
        "archive_wide_tau_usable_channels": sorted(archive_usable),
        "table_cell_changes_outside_usable_channels": len(outside_cells) + len(expected_outside_cells),
        "table_cell_changes_outside_usable_channels_expected": [f'{c["table"]} ch{c["channel"]} {c["column"]}' for c in expected_outside_cells],
        "table_cell_changes_outside_usable_channels_unexpected": len(outside_cells),
        "table_cell_changes_without_channel_key": len(unkeyed_cells),
        "removed_fields_exactly_the_split_fields_on_every_channel": removed_ok,
        "removed_fields": len(removed), "added_fields": len(added),
        "changed_fields": len(diffs),
        "changes_by_section": dict(Counter(r["field"].split(".")[0] for r in diffs)),
        "changes_by_channel": {str(k): v for k, v in sorted(Counter(r["channel"] for r in diffs).items())},
        "changed_cells": len(cells),
        "changed_cells_listed": len(listed),
        "changed_surface_cells_summarised": len(cells) - len(listed),
        "surface_columns_all_equal_gain_factor": all(r["all_equal_gain_factor"] for r in summary_rows.values()),
        "changed_cells_by_table": dict(Counter(c["table"] for c in cells)),
        "removed_columns": removed_columns, "added_columns": added_columns, "tables": files,
        "primary_counts_prior": dict(Counter(r["primary_assessment_prior"] for r in channels)),
        "primary_counts": dict(Counter(r["primary_assessment"] for r in channels)),
        "old_producer": old_run["producer"], "new_producer": new_run["producer"], "input_sha256": inputs,
        "scope": "Comparison of retrospective conditional screens under a changed chain booking; no physical irrecoverability claim",
    }
    with (a.out / "summary.json").open("x") as f:
        json.dump(summary, f, indent=2)
        f.write("\n")
    print(json.dumps({k: v for k, v in summary.items() if k not in ["old_producer", "new_producer", "input_sha256", "tables"]}, indent=2))


if __name__ == "__main__":
    main()
