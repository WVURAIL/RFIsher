"""The capture handoff of the records, with the detector's readings from pilot-proxy's capture output.

pilot-proxy writes its readings of the capture in the layout ``capture_operating_characteristic`` version 1
(``pilot-proxy capture oc-table``: ``capture_oc_table.csv``, ``capture_oc_summary.csv``, ``capture_tau_bounds.csv``
and ``manifest.json``). The capture records read one directory in the layout ``capture_handoff_measurements``
version 0 (:mod:`capture_handoff`). This command writes the second with its three detector readings taken from the
first:

- ``ladder_eta.csv``: each rung's archive threshold per band and bank (the summary's ``eta_<rung>_<bank>``);
- ``dump_q.csv``: each science dump's median Q per band and bank (the table's ``q_median``, which pilot-proxy fills
  on the science dumps, the only dumps the records read);
- ``tau_bounds.csv``: the within-dump lower bounds per lane setting, band and class. The detector does not group its
  classes into ranges; each class takes its range from the ruling's range rule (:data:`capture_ruling.RANGES`).

- ``board_detector.csv``: the archive's gain bound per band (the summary's ``board_*`` columns).

Every other file is copied from a measurement handoff (``--measurements``): the frame-analysis and Stokes I tables,
the 2020 cohort, the phasor tables, the channel 24 lane and the archive shares, which come from lanes pilot-proxy does
not run. The record's own tables (the table of record and its v7 input), the BAO-basis coherence times and the
channel ruling's board are not copied: the capture records take them as explicit inputs. Both inputs are checked
against their manifests first, and the detector's integration constants and science dumps must be the record's.

usage: rfisher records capture-handoff --oc DIR --measurements DIR --out DIR
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
from pathlib import Path

from rfisher.records.chime_atsc_2026 import capture_handoff as ch
from rfisher.records.chime_atsc_2026 import capture_units as U
from rfisher.records.chime_atsc_2026.capture_ruling import RANGES

OC_SCHEMA = "capture_operating_characteristic"
OC_SCHEMA_VERSION = 1
OC_FILES = ("capture_oc_table.csv", "capture_oc_summary.csv", "capture_tau_bounds.csv")
BANKS = ("nominal", "measured_marker")
READINGS = ("ladder_eta.csv", "dump_q.csv", "tau_bounds.csv", "board_detector.csv")
TAU_COLUMNS = ("censor", "source", "calibrate", "channel", "ew", "ns", "lane", "check", "variants", "lb", "least_variant",
               "span", "lb_priced", "capped", "b4", "calibration_fcr", "calibration_n_at_or_above", "calibration_n_cells",
               "calibration_fcr_same_class", "calibration_null_max_s", "calibration_null_max_same_class_s",
               "calibration_passes")
RANGE_OF = {c: name for name, classes in RANGES.items() for c in classes}


class OCError(ValueError):
    """The directory is not a capture operating characteristic this reader accepts."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _rows(data: bytes) -> tuple[list[str], list[dict]]:
    reader = csv.DictReader(io.StringIO(data.decode("utf-8"), newline=""))
    return list(reader.fieldnames or ()), list(reader)


def _float(text: str) -> str:
    return repr(float(text))


def read_oc(directory) -> dict:
    """The manifest and the three tables of an operating-characteristic directory, each file checked against the
    manifest's digest, the schema and the detector constants against the record's."""
    root = Path(directory)
    path = root / "manifest.json"
    if not path.is_file():
        raise OCError(f"{root}: no manifest.json")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if (manifest.get("schema"), manifest.get("schema_version")) != (OC_SCHEMA, OC_SCHEMA_VERSION):
        raise OCError(f"{root}: schema {manifest.get('schema')!r} version {manifest.get('schema_version')!r}, "
                      f"expected {OC_SCHEMA!r} {OC_SCHEMA_VERSION}")
    out = {"manifest": manifest, "sha256": {"manifest.json": _sha256(path.read_bytes())}}
    for name in OC_FILES:
        want = manifest.get("files", {}).get(name)
        data = (root / name).read_bytes() if (root / name).is_file() else None
        if data is None or want is None:
            raise OCError(f"{root}: {name} is missing or not in the manifest")
        if _sha256(data) != want:
            raise OCError(f"{root}: {name}: sha256 differs from the manifest")
        out["sha256"][name] = want
        out[name] = _rows(data)
    header = out["capture_tau_bounds.csv"][0]
    if tuple(header) != TAU_COLUMNS:
        raise OCError(f"{root}: capture_tau_bounds.csv: columns {header}, expected {list(TAU_COLUMNS)}")
    integration = manifest.get("integration", {})
    detector = (integration.get("n_frame"), integration.get("frame_seconds"), integration.get("coherence_cap_seconds"),
                manifest.get("measurement_allowance_db"), manifest.get("detection_gate_sigma"))
    record = (U.NFFT, U.TF, U.CAP, U.ALLOW_DB, U.constants()["detection_gate_sigma"])
    if detector != record:
        raise OCError(f"{root}: the detector's integration constants {detector} are not the record's {record}")
    events = manifest.get("events", {})
    science = tuple(sorted(e for e, v in events.items() if v.get("science")))
    if science != ch.SCIENCE or any(events[e].get("frames") != U.NFRAMES[e] for e in science):
        raise OCError(f"{root}: the science dumps {science} and their frames are not the record's {ch.SCIENCE}")
    n_b = {(v.get("ew"), v.get("ns")): v.get("n_b") for v in manifest.get("classes", {}).values()}
    if any(n_b.get(c) != n for c, n in U.NB.items()):
        raise OCError(f"{root}: the baselines per class are not the record's")
    return out


def ladder_eta_rows(summary: list[dict]) -> list[dict]:
    """``channel,bank,policy,eta``: the nominal bank's rungs band by band, then the measured-marker bank's."""
    rows = []
    for bank in BANKS:
        for s in summary:
            values = [s.get(f"eta_{rung}_{bank}", "") for rung in ch.QS]
            if not any(values):
                continue
            if not all(values):
                raise OCError(f"band {s['band_id']}: a rung's threshold is missing on the {bank} bank")
            rows += [{"channel": int(s["band_id"]), "bank": bank, "policy": rung, "eta": _float(v)}
                     for rung, v in zip(ch.QS, values)]
    return rows


def dump_q_rows(table: list[dict]) -> list[dict]:
    """``channel,event,bank,q_median``: each science dump's median Q, bank by bank, dump by dump, band by band. A
    band's rows of one dump must agree on it."""
    seen: dict = {}
    for r in table:
        if r["science"] != "True" or r["q_median"] == "" or r["bank"] not in BANKS:
            continue
        key = (r["bank"], r["event"], int(r["band_id"]))
        q = _float(r["q_median"])
        if seen.setdefault(key, q) != q:
            raise OCError(f"band {key[2]}, dump {key[1]}, bank {key[0]}: two median Q readings ({seen[key]}, {q})")
    order = {b: i for i, b in enumerate(BANKS)}
    return [{"channel": c, "event": e, "bank": b, "q_median": q}
            for (b, e, c), q in sorted(seen.items(), key=lambda kv: (order[kv[0][0]], kv[0][1], kv[0][2]))]


def tau_bound_rows(bounds: list[dict]) -> list[dict]:
    """The rows of ``tau_bounds.csv`` (see :data:`capture_handoff.HEADERS`), setting by setting, band and class
    ascending; floats as repr, the variants and the calibration as JSON in the lane's order."""
    rows = []
    for r in bounds:
        setting = ch.BOUND_SETTINGS.get((r["censor"] == "True", r["source"], r["calibrate"] == "True"))
        if setting is None:
            raise OCError(f"no lane setting of the record is censor={r['censor']}, source={r['source']}, "
                          f"calibrate={r['calibrate']}")
        c = (int(r["ew"]), int(r["ns"]))
        if c not in RANGE_OF:
            raise OCError(f"band {r['channel']}: class {c} is in no range of the ruling")
        calibration = ""
        if r["calibration_passes"] != "":
            def opt(x):
                return _float(x) if x != "" else None
            calibration = json.dumps({"fcr": _float(r["calibration_fcr"]),
                                      "n_at_or_above": int(r["calibration_n_at_or_above"]),
                                      "n_cells": int(r["calibration_n_cells"]),
                                      "fcr_same_class": opt(r["calibration_fcr_same_class"]),
                                      "null_max_s": _float(r["calibration_null_max_s"]),
                                      "null_max_same_class_s": opt(r["calibration_null_max_same_class_s"]),
                                      "passes": r["calibration_passes"] == "True"})
        rows.append({"setting": setting, "channel": int(r["channel"]), "ew": c[0], "ns": c[1],
                     "lane": _float(r["lane"]) if r["lane"] != "" else "",
                     "check": _float(r["check"]) if r["check"] != "" else "", "range": RANGE_OF[c],
                     "variants": json.dumps({k: repr(float(v)) for k, v in json.loads(r["variants"]).items()}),
                     "lb": _float(r["lb"]), "least_variant": r["least_variant"], "span": _float(r["span"]),
                     "lb_priced": _float(r["lb_priced"]), "capped": r["capped"],
                     "b4": "True" if r["b4"] == "True" else "", "calibration": calibration})
    order = {s: i for i, s in enumerate(ch.BOUND_SETTINGS.values())}
    return sorted(rows, key=lambda x: (order[x["setting"]], x["channel"], x["ew"], x["ns"]))


def board_rows(summary: list[dict]) -> list[dict]:
    """``channel,tau_quality,tau_booked_s,G_nocredit``: the archive's gain bound of each band the summary reads it for,
    band ascending."""
    rows = [{"channel": int(s["band_id"]), "tau_quality": s["board_tau_quality"], "tau_booked_s": s["board_tau_booked_s"],
             "G_nocredit": _float(s["board_G_nocredit"])}
            for s in summary if s.get("board_G_nocredit", "") != ""]
    return sorted(rows, key=lambda r: r["channel"])


def _csv(rows: list[dict], header: str) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=header.split(","), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def build(oc_dir, measurements_dir, out) -> dict:
    """Write the capture handoff into ``out`` (which must not exist); return its manifest."""
    out = Path(out)
    if out.exists():
        raise OCError(f"{out} exists")
    oc = read_oc(oc_dir)
    H = ch.open_handoff(measurements_dir, borrowed=True, measurements=True)
    readings = {"ladder_eta.csv": (ladder_eta_rows(oc["capture_oc_summary.csv"][1]), "capture_oc_summary.csv"),
                "dump_q.csv": (dump_q_rows(oc["capture_oc_table.csv"][1]), "capture_oc_table.csv"),
                "tau_bounds.csv": (tau_bound_rows(oc["capture_tau_bounds.csv"][1]), "capture_tau_bounds.csv"),
                "board_detector.csv": (board_rows(oc["capture_oc_summary.csv"][1]), "capture_oc_summary.csv")}
    files = {}
    out.mkdir(parents=True)
    for rel, entry in sorted(H.files.items()):
        if rel in READINGS or rel in ch.RECORD_FILES:
            continue
        data = H.data(rel)
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / rel).write_bytes(data)
        files[rel] = dict(entry)
    for rel, (rows, source) in readings.items():
        if not rows:
            raise OCError(f"{oc_dir}: no rows for {rel}")
        data = _csv(rows, ch.HEADERS[rel])
        (out / rel).write_bytes(data)
        files[rel] = {"sha256": _sha256(data), "source": f"{OC_SCHEMA} v{OC_SCHEMA_VERSION}: {source}",
                      "source_sha256": oc["sha256"][source]}
    manifest = {"schema": ch.SCHEMA, "schema_version": ch.SCHEMA_VERSION, "constants": H.manifest["constants"],
                "science_events": list(ch.SCIENCE), "files": dict(sorted(files.items())),
                "inputs": {"operating_characteristic": dict(sorted(oc["sha256"].items())),
                           "measurements": {"manifest.json": _sha256((Path(measurements_dir) / "manifest.json").read_bytes()),
                                            "producer": H.manifest.get("producer")}},
                "producer": {"module": __name__, "operating_characteristic_producer": oc["manifest"].get("producer")}}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    ch.open_handoff(out, borrowed=True)
    return manifest


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    opts = {}
    while args:
        key = args.pop(0)
        if key not in ("--oc", "--measurements", "--out") or not args:
            raise SystemExit(f"capture-handoff: unknown or incomplete argument {key!r}\n{__doc__.strip().splitlines()[-1]}")
        opts[key] = args.pop(0)
    if set(opts) != {"--oc", "--measurements", "--out"}:
        raise SystemExit("capture-handoff: --oc, --measurements and --out are required")
    try:
        manifest = build(opts["--oc"], opts["--measurements"], opts["--out"])
    except (OCError, ch.HandoffError) as exc:
        raise SystemExit(f"capture-handoff: {exc}")
    print(f"wrote {opts['--out']}: {len(manifest['files'])} files, the detector's readings from {opts['--oc']}")
    return 0
