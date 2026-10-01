"""The capture handoff written from pilot-proxy's capture output (rfisher.records.chime_atsc_2026.capture_oc).

An operating-characteristic directory in pilot-proxy's layout is written here from the golden handoff's own readings
(the summary's eta columns, the table's q_median, the bounds' columns); the handoff built from it must read back the
golden's ladder and bounds byte for byte, its dump medians value for value, every other file unchanged, and the
release reader's objects.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path

import pytest

from test_capture_handoff import OBJECTS, _key, _value

from rfisher.records.chime_atsc_2026 import capture_handoff as ch
from rfisher.records.chime_atsc_2026 import capture_oc as oc
from rfisher.records.chime_atsc_2026 import capture_units as U

SETTING = {v: k for k, v in ch.BOUND_SETTINGS.items()}


def _write(path: Path, header, rows):
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(header), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def _read(root: Path, rel: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO((root / rel).read_text(encoding="utf-8"), newline="")))


def _manifest(root: Path, **changes):
    files = {n: hashlib.sha256((root / n).read_bytes()).hexdigest() for n in oc.OC_FILES}
    m = {"schema": oc.OC_SCHEMA, "schema_version": oc.OC_SCHEMA_VERSION, "files": files,
         "integration": {"n_frame": U.NFFT, "frame_seconds": U.TF, "coherence_cap_seconds": U.CAP},
         "measurement_allowance_db": U.ALLOW_DB, "detection_gate_sigma": 3.0,
         "events": {**{e: {"science": True, "frames": U.NFRAMES[e], "label": e} for e in ch.SCIENCE},
                    "20260917160208": {"science": False, "frames": 33, "label": "rescan"}},
         "classes": {f"c{c[0]}_{c[1]}": {"ew": c[0], "ns": c[1], "n_b": n} for c, n in U.NB.items()},
         "producer": {"module": "pilot_proxy.capture.oc_table"}}
    m.update(changes)
    (root / "manifest.json").write_text(json.dumps(m), encoding="utf-8")


def _operating_characteristic(handoff: Path, root: Path) -> Path:
    """pilot-proxy's layout, holding the golden handoff's readings."""
    root.mkdir()
    eta = _read(handoff, "ladder_eta.csv")
    bands = sorted({int(r["channel"]) for r in eta})
    cols = [f"eta_{q}_{b}" for b in oc.BANKS for q in ch.QS]
    summary = []
    for band in bands:
        row = {"band_id": band, **{c: "" for c in cols}}
        for r in eta:
            if int(r["channel"]) == band:
                row[f"eta_{r['policy']}_{r['bank']}"] = r["eta"]
        summary.append(row)
    _write(root / "capture_oc_summary.csv", ["band_id"] + cols, summary)
    table = []
    for r in _read(handoff, "dump_q.csv"):
        science = r["event"] in ch.SCIENCE
        for product in ("xx", "yy"):   # a band's rows of a dump repeat its median
            table.append({"band_id": r["channel"], "product": product, "bank": r["bank"], "event": r["event"],
                          "science": str(science), "q_median": r["q_median"] if science else ""})
    _write(root / "capture_oc_table.csv", ["band_id", "product", "bank", "event", "science", "q_median"], table)
    bounds = []
    for r in _read(handoff, "tau_bounds.csv"):
        censor, source, calibrate = SETTING[r["setting"]]
        cal = json.loads(r["calibration"]) if r["calibration"] else {}

        def cell(k):
            v = cal.get(k)
            return "" if v is None else str(v) if not isinstance(v, bool) else str(v)
        bounds.append({"censor": str(censor), "source": source, "calibrate": str(calibrate), "channel": r["channel"],
                       "ew": r["ew"], "ns": r["ns"], "lane": r["lane"], "check": r["check"],
                       "variants": json.dumps({k: float(v) for k, v in json.loads(r["variants"]).items()}),
                       "lb": r["lb"], "least_variant": r["least_variant"], "span": r["span"], "lb_priced": r["lb_priced"],
                       "capped": r["capped"], "b4": "True" if r["b4"] == "True" else "False",
                       **{f"calibration_{k}": cell(k) for k in ("fcr", "n_at_or_above", "n_cells", "fcr_same_class",
                                                               "null_max_s", "null_max_same_class_s", "passes")}})
    _write(root / "capture_tau_bounds.csv", oc.TAU_COLUMNS, bounds)
    _manifest(root)
    return root


@pytest.fixture
def built(capture_handoff_dir, tmp_path):
    source = _operating_characteristic(capture_handoff_dir, tmp_path / "oc")
    out = tmp_path / "handoff"
    oc.build(source, capture_handoff_dir, out)
    return source, out


def test_the_built_handoff_reads_back_the_golden(capture_handoff_dir, built):
    _, out = built
    for name in ("ladder_eta.csv", "tau_bounds.csv"):
        assert (out / name).read_bytes() == (capture_handoff_dir / name).read_bytes(), name
    science = {(r["channel"], r["event"], r["bank"]): r["q_median"] for r in _read(capture_handoff_dir, "dump_q.csv")
               if r["event"] in ch.SCIENCE}
    assert {(r["channel"], r["event"], r["bank"]): r["q_median"] for r in _read(out, "dump_q.csv")} == science
    golden = json.loads((capture_handoff_dir / "manifest.json").read_text())["files"]
    made = json.loads((out / "manifest.json").read_text())["files"]
    assert set(made) == set(golden)
    for rel in set(golden) - set(oc.READINGS):
        assert (out / rel).read_bytes() == (capture_handoff_dir / rel).read_bytes(), rel
        assert made[rel] == golden[rel], rel
    for rel in oc.READINGS:
        assert made[rel]["source"].startswith(f"{oc.OC_SCHEMA} v{oc.OC_SCHEMA_VERSION}: ")


@pytest.mark.parametrize("pol", ["larger", "stokes_i"])
@pytest.mark.parametrize("rescan", [False, True])
def test_the_built_handoff_gives_the_release_readers_objects(built, frozen_reader_objects, pol, rescan):
    _, out = built
    got = ch.ruling_inputs(ch.open_handoff(out), pol, rescan)
    frozen = frozen_reader_objects["objects"][f"{pol}|{'rescan' if rescan else 'nominal'}"]
    for name in OBJECTS:
        assert {_key(k): _value(v) for k, v in getattr(got, name).items()} == frozen[name], name


def test_the_bounds_of_every_setting_are_the_golden(capture_handoff_dir, built):
    _, out = built
    a, b = ch.open_handoff(capture_handoff_dir), ch.open_handoff(out)
    for setting in ch.BOUND_SETTINGS:
        assert ch.tau_lower_bounds(a, *setting) == ch.tau_lower_bounds(b, *setting)


def _rewrite(root: Path, name: str, edit):
    rows = _read(root, name)
    header = list(rows[0])
    rows = edit(rows)
    _write(root / name, header, rows)
    m = json.loads((root / "manifest.json").read_text())
    m["files"][name] = hashlib.sha256((root / name).read_bytes()).hexdigest()
    (root / "manifest.json").write_text(json.dumps(m))


def test_what_the_reader_refuses(capture_handoff_dir, tmp_path):
    source = _operating_characteristic(capture_handoff_dir, tmp_path / "oc")
    n = iter(range(100))

    def refused(match):
        with pytest.raises(oc.OCError, match=match):
            oc.build(source, capture_handoff_dir, tmp_path / f"out{next(n)}")
    _manifest(source, schema_version=2)
    refused("schema")
    _manifest(source, measurement_allowance_db=2.0)
    refused("integration constants")
    _manifest(source, events={e: {"science": True, "frames": 1} for e in ch.SCIENCE})
    refused("science dumps")
    _manifest(source)
    (source / "capture_oc_summary.csv").write_text("band_id\n14\n")
    refused("sha256 differs")
    source = _operating_characteristic(capture_handoff_dir, tmp_path / "oc2")

    def disagree(rows):
        for r in rows:
            if r["product"] == "yy" and r["q_median"]:
                r["q_median"] = repr(float(r["q_median"]) * 2)
                break
        return rows
    _rewrite(source, "capture_oc_table.csv", disagree)
    refused("two median Q readings")
    source = _operating_characteristic(capture_handoff_dir, tmp_path / "oc3")
    _rewrite(source, "capture_tau_bounds.csv", lambda rows: [dict(rows[0], source="mean")] + rows[1:])
    refused("no lane setting")
    out = tmp_path / "exists"
    out.mkdir()
    with pytest.raises(oc.OCError, match="exists"):
        oc.build(_operating_characteristic(capture_handoff_dir, tmp_path / "oc4"), capture_handoff_dir, out)


def test_the_record_tables_can_be_given_explicitly(capture_handoff_dir, tmp_path):
    h = ch.open_handoff(capture_handoff_dir)
    rel = "frame_analysis/table_of_record.csv"
    copy = tmp_path / "table_of_record.csv"
    copy.write_bytes((capture_handoff_dir / rel).read_bytes())
    assert ch.table_rows(h, rel, copy) == ch.table_rows(h, rel)
    copy.write_text("channel,role\n14,data\n")
    with pytest.raises(ch.HandoffError, match="columns differ"):
        ch.table_rows(h, rel, copy)
