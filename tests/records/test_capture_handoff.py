"""The capture handoff reader: the release's objects, and what it refuses.

``reader_objects.json.gz`` holds the objects the release producer's own input block (ruling_a18.py, executed from its
text on the frozen inputs) built, under both products and with and without channel 33's rescan. The reader must
return the same objects from the golden handoff, every float equal as its repr.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from rfisher.records.chime_atsc_2026 import capture_handoff as ch
from rfisher.records.chime_atsc_2026 import capture_units as U

ROOT = Path(__file__).resolve().parents[2]
OBJECTS = ("ex", "floor", "POL_OF_CLASS", "tau", "tau_least", "tau_probe_meas", "tau_pol", "rho", "eta", "Qmed")


def _key(k):
    return "|".join(f"{x[0]},{x[1]}" if isinstance(x, tuple) else str(x) for x in (k if isinstance(k, tuple) else (k,)))


def _value(v):
    if isinstance(v, (float, np.floating)): return repr(float(v))
    if isinstance(v, (tuple, list)): return [_value(x) for x in v]
    if isinstance(v, dict): return {_key(k): _value(x) for k, x in v.items()}
    return v


@pytest.mark.parametrize("pol", ["larger", "stokes_i"])
@pytest.mark.parametrize("rescan", [False, True])
def test_the_reader_returns_the_release_readers_objects(capture_handoff_dir, frozen_reader_objects, pol, rescan):
    got = ch.ruling_inputs(ch.open_handoff(capture_handoff_dir), pol, rescan)
    frozen = frozen_reader_objects["objects"][f"{pol}|{'rescan' if rescan else 'nominal'}"]
    for name in OBJECTS:
        assert {_key(k): _value(v) for k, v in getattr(got, name).items()} == frozen[name], name


def test_the_detector_constants_are_the_records(capture_handoff_dir):
    h = ch.open_handoff(capture_handoff_dir)
    assert h.manifest["constants"] == U.constants()
    assert [f"{U.admissible_min_G(n):.2f}" for n in (11, 33, 4)] == ["8.41", "21.06", "4.06"]


def test_the_within_dump_bounds_keep_the_lanes_invariants(capture_handoff_dir):
    h = ch.open_handoff(capture_handoff_dir)
    for setting in ((False, "summary", False), (True, "fits", True)):
        LB = ch.tau_lower_bounds(h, *setting)
        span = next(iter(LB.values()))["span"]
        assert abs(span - 32 * U.TF) < 1e-12
        for k, v in LB.items():
            assert v["lb"] == min(v["variants"].values()) and v["lb_priced"] == min(v["lb"], span)
            assert v["least_variant"] == min(v["variants"], key=v["variants"].get)
        assert ("calibration" in next(iter(LB.values()))) == setting[2]
    assert set(k for k, v in ch.tau_lower_bounds(h).items() if "check" in v) == {
        (14, (0, 32)), (14, (0, 64)), (26, (0, 32)), (27, (0, 32))}
    with pytest.raises(ch.HandoffError, match="no within-dump bounds"):
        ch.tau_lower_bounds(h, censor=True, source="summary", calibrate=False)


def _copy(src, tmp_path):
    dst = tmp_path / "handoff"
    shutil.copytree(src, dst)
    return dst


def _rewrite(root, rel, text):
    (root / rel).write_text(text)
    m = json.loads((root / "manifest.json").read_text())
    m["files"][rel]["sha256"] = hashlib.sha256((root / rel).read_bytes()).hexdigest()
    (root / "manifest.json").write_text(json.dumps(m))


def test_a_changed_file_is_refused(capture_handoff_dir, tmp_path):
    root = _copy(capture_handoff_dir, tmp_path)
    with open(root / "ladder_eta.csv", "a") as fh:
        fh.write("14,nominal,cal_q0.1,1.0\n")
    with pytest.raises(ch.HandoffError, match="sha256"):
        ch.ladder_eta(ch.open_handoff(root))


def test_a_missing_or_extra_column_is_refused(capture_handoff_dir, tmp_path):
    root = _copy(capture_handoff_dir, tmp_path)
    rows = (root / "dump_q.csv").read_text().splitlines()
    _rewrite(root, "dump_q.csv", "\n".join([rows[0] + ",extra"] + [r + ",0" for r in rows[1:]]) + "\n")
    with pytest.raises(ch.HandoffError, match="extra"):
        ch.dump_q(ch.open_handoff(root))
    _rewrite(root, "dump_q.csv", "\n".join(",".join(r.split(",")[:3]) for r in rows) + "\n")
    with pytest.raises(ch.HandoffError, match="missing"):
        ch.dump_q(ch.open_handoff(root))


def test_a_borrowed_file_and_an_unlisted_one_are_refused(capture_handoff_dir):
    h = ch.open_handoff(capture_handoff_dir)
    for rel in ("frame_analysis/pilot_to_inband.csv", "cohort2020/cohort_exc_long.json", "cohort2020/pilot_vs_inband_D1.json"):
        with pytest.raises(ch.HandoffError, match="borrowed"):
            h.data(rel)
    with pytest.raises(ch.HandoffError, match="not in the handoff manifest"):
        h.data("frame_analysis/ruling_baseline.py")
    assert ch.open_handoff(capture_handoff_dir, borrowed=True).rows("frame_analysis/pilot_to_inband.csv")


def test_a_wrong_schema_or_constant_is_refused(capture_handoff_dir, tmp_path):
    root = _copy(capture_handoff_dir, tmp_path)
    m = json.loads((root / "manifest.json").read_text())
    (root / "manifest.json").write_text(json.dumps(dict(m, schema_version=1)))
    with pytest.raises(ch.HandoffError, match="schema"):
        ch.open_handoff(root)
    m["constants"]["NB"]["0,255"] = 5
    (root / "manifest.json").write_text(json.dumps(m))
    with pytest.raises(ch.HandoffError, match="constants"):
        ch.open_handoff(root)


AUDIT = r"""
import runpy, sys
opened = []
def hook(event, args):
    if event == "open" and isinstance(args[0], str):
        opened.append(args[0])
sys.addaudithook(hook)
from rfisher.cli import main
code = main(sys.argv[2:])
open(sys.argv[1], "w").write("\n".join(opened))
sys.exit(code)
"""


def test_the_ruling_reads_only_the_handoff_and_its_input_table(capture_handoff_dir, tmp_path):
    """A file-open audit of a ruling run: nothing is read outside the handoff, the input table, the package and the
    interpreter."""
    log, out = tmp_path / "opened.txt", tmp_path / "a18_full.csv"
    table = capture_handoff_dir / "frame_analysis" / "table_of_record_before_amendment8.csv"
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), PYTHONDONTWRITEBYTECODE="1")
    subprocess.run([sys.executable, "-c", AUDIT, str(log), "records", "capture-ruling", "--rule", "r5_2",
                    "--json", str(tmp_path / "a18.json"), "--input", str(table), "--handoff", str(capture_handoff_dir),
                    "--out", str(out), "--ch33-rescan"], check=True, capture_output=True, env=env)
    allowed = (str(capture_handoff_dir), str(tmp_path), str(ROOT / "src"), str(ROOT / "projects"), sys.prefix,
               sys.base_prefix, "/dev/", "/proc/", "/etc/localtime", "/usr/share/zoneinfo")
    opened = [p for p in log.read_text().split("\n") if p]
    outside = sorted({p for p in opened if not os.path.abspath(p).startswith(allowed)})
    assert not outside, outside
    read = {os.path.relpath(p, capture_handoff_dir) for p in opened if p.startswith(str(capture_handoff_dir))}
    assert "frame_analysis/pilot_to_inband.csv" not in read and "cohort2020/cohort_exc_long.json" not in read
    assert {"stokes_i/class_excess_epochs.csv", "tau_bounds.csv", "ladder_eta.csv", "dump_q.csv"} <= read
    with open(out, newline="") as fh:
        assert len(list(csv.DictReader(fh))) == 368


BLOCKED = r"""
import sys
class Block:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in ("yaml", "h5py", "jsonschema", "pytest"):
            raise ImportError(f"{name} is blocked")
        return None
sys.meta_path.insert(0, Block())
from rfisher.cli import main
for command in ("table-of-record", "capture-ruling"):
    assert main(["records", command, "--help"]) == 0
import rfisher.records.chime_atsc_2026.capture_ruling, rfisher.records.chime_atsc_2026.table_of_record
"""


def test_the_capture_records_run_without_the_forecast_dependencies():
    """The records run under the release's interpreter, which has no PyYAML, h5py, jsonschema or pytest."""
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), PYTHONDONTWRITEBYTECODE="1")
    out = subprocess.run([sys.executable, "-c", BLOCKED], check=True, capture_output=True, text=True, env=env).stdout
    assert "usage: rfisher records capture-ruling" in out and "usage: rfisher records table-of-record" in out
