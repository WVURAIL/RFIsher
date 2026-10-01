"""The capture handoff: the detector's measurements the capture ruling of record reads.

The release producer (r5.2) read its measured inputs from the frame-analysis
tree, the validated Stokes I inputs, the kernel runs, the archive per-pilot
products, channel 33's rescan, the channel 24 lane, the reduced dumps and the
archive ledger. The records here read one directory instead, in the layout
``capture_handoff_measurements`` version 0 (``manifest.json``):

- ``frame_analysis/``, ``stokes_i/``, ``cohort2020/``, ``phasor/phasor14.csv.gz``: byte copies of the detector's
  measurement tables;
- ``board_detector.csv``: the archive's gain bound per channel (the channel ruling's tau quality, booked tau and
  ``G_nocredit``, the columns the detector reads from it);
- ``ladder_eta.csv``: each rung's archive threshold per channel (the
  ``higher`` quantile of Q over the band's valid frames), on the nominal bank
  and on channel 33's measured-marker bank;
- ``dump_q.csv``: each dump's median Q per channel, on both banks;
- ``tau_bounds.csv``: the within-dump 95 % lower bounds on tau per channel and
  class, for each setting of the lane the releases read;
- ``cohort24.json``: the channel 24 lane's per-event tables (2020 cohort);
- ``phasor/raw_epochs.json``: the reference-free class means of the reduced
  dumps the phase limit reads;
- ``archive_shares.json``: the archive ledger's booked shares per channel.

The record's own tables (the table of record and its v7 input), the BAO-basis coherence times (``gain_bao.csv``) and
the channel ruling's board are not measurements of the capture: the records take them as explicit inputs
(``--record-table``, ``--input-table``, ``--gain-bao``), and a handoff that holds one of them is refused
(:data:`RECORD_FILES`); a measurement handoff of the earlier layout is read only to build the handoff from.

Every float the derivation computed is a ``repr`` string or a JSON number, so
it reads back bit for bit. :class:`CaptureHandoff` checks the schema, the
sha256 of every file against the manifest, the header of every table, and the
detector constants against :mod:`capture_units`; it refuses a file the
manifest does not list and, unless asked for the borrowed basis, any file the
release marks as borrowed. Each function below returns the objects the
release's own reading lines built, from the same lines with the file reads
replaced.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import re
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from rfisher.records.chime_atsc_2026 import capture_units as U

SCHEMA = "capture_handoff_measurements"
SCHEMA_VERSION = 0
# the files the measured basis of channel 24 must never open (a19_inputs.BORROWED)
BORROWED = ("pilot_to_inband.csv", "pilot_vs_inband_D1.json", "cohort_exc_long.json")
SCIENCE = ("20260916162300", "20260917040230", "20260917090230", "20260917140230")
PILOT = {14: 844, 15: 829, 16: 813, 17: 798, 18: 783, 19: 767, 20: 752, 21: 736, 22: 721, 23: 706, 24: 690, 25: 675,
         26: 660, 27: 644, 28: 629, 29: 614, 30: 598, 31: 583, 32: 568, 33: 552, 34: 537, 35: 521, 36: 506, 37: 491}
QS = {"cal_q0.1": 0.1, "cal_q0.5": 0.5, "cal_q0.9": 0.9}
TAU_FILES = {(0, 1): "cadence_tau.csv", (0, 32): "cadence_tau_ns32.csv", (0, 64): "cadence_tau_ns64.csv",
             (0, 128): "cadence_tau_ns128.csv", (0, 255): "cadence_tau_ns255.csv", (1, 0): "cadence_tau_ew1.csv",
             (2, 0): "cadence_tau_ew2.csv", (3, 0): "cadence_tau_ew3.csv"}
CLS_NAME = {(0, 1): "ns1", (0, 8): "ns8", (0, 32): "ns32", (0, 64): "ns64", (0, 128): "ns128", (0, 255): "ns255",
            (1, 0): "ew1", (1, 32): "ew1ns32", (2, 0): "ew2", (3, 0): "ew3"}
# files of the earlier layout that are not measurements of the capture: the records take them as explicit inputs
RECORD_FILES = ("frame_analysis/table_of_record.csv", "frame_analysis/table_of_record_before_amendment8.csv",
                "frame_analysis/gain_bao.csv", "board_final.csv")
# the lane settings the releases read (a19_inputs.tau_lower_bounds(censor, source, calibrate))
BOUND_SETTINGS = {(False, "summary", False): "r5", (True, "fits", True): "r5_1"}

_TOR_V7 = ("freq_id,channel,role,disposition,policy_or_reason,A_keep_all_ns1_bound,A_keep_all_ns1_pol0,"
           "A_keep_all_ns1_pol1,A_keep_all_class_median,G_dump,lambda_none,lambda_deployed,suppression_db,R_none_G1,"
           "R_deployed_G1,R_none_Gdump,R_deployed_Gdump,G_archive,R_deployed_Garchive,tau_c_s,tau_c_status,G_measured,"
           "R_none_Gmeasured,R_deployed_Gmeasured,A_lowest_epoch,lowest_epoch,R_deployed_lowest_Gmeasured,A_bao_keep_all,"
           "tau_bao_s,tau_bao_status,G_bao,R_none_Gbao,R_deployed_Gbao,R_deployed_bao_G1,A_bao_lowest_epoch,"
           "kept_dumps_cal_q0.5,kept_dumps_cal_q0.9,n_dumps").split(",")
_RANGE_COLUMNS = ("A_net", "measured", "floor_level", "tau_s", "tau_status", "tau_least_s", "probe_db", "rescue_rho",
                  "gate_db", "G", "rho", "ground_credit_db", "R_deployed", "R_none", "verdict")
# the header of every table, by file name (a family of names shares one)
HEADERS = {
    "class_excess_epochs.csv": "channel,epoch,ew,ns,pol,excess,n_bins",
    "class_floor_bins.csv": "epoch,ew,ns,pol,freq_id,excess",
    "cadence_tau": "channel,bins,pol,status,tau_c_s,tau_c_high_s,G,plateau,plateau_se,n_pairs,n_classes,n_epochs,probes",
    "frame_residual": ("channel,ew,ns,pol,frames,n_frames,excess_pilot_bin,excess_inband_median,excess_inband_max,"
                       "lambda_q,phi_fast_pilot,G_dump_pilot,lag_zero_pilot,kernel_excess_db_median"),
    "gain_bao.csv": "channel,bins,status,tau_c_s,tau_c_high_s,G,basis,ew1,ew2,ew3",
    "lag_coherence_tenclasses_D.csv": "channel,cls,bins,a,b,lag_s,lag_class,rho,rho_noise,n_bins",
    "pilot_to_inband.csv": "channel,pilot_A_long,inband_A_long,correction_db,usable,strong",
    "board_detector.csv": "channel,tau_quality,tau_booked_s,G_nocredit",
    "board_final.csv": ("channel,era,first_blocker_record,archived_refusal,tau_quality,tau_booked_s,G_nocredit,G_table,"
                        "table_credit_dB,floor_evidence,floor_db,lambda_q,best_policy,tie_note,retention,exposure_cost,"
                        "kept,A,R_q_nocredit,gap_dB_nocredit,gap_dB_nocredit_15bin,R_q_table,gap_dB_table,G1_R_q,"
                        "G1_gap_dB,G1_headroom_dB,tau_needed_s,dominant_term,ruling"),
    "table_of_record_before_amendment8.csv": ",".join(_TOR_V7),
    "table_of_record.csv": ",".join(_TOR_V7 + [f"{r}_{c}" for r in ("shortest", "bao_short", "bao_long")
                                                for c in _RANGE_COLUMNS]),
    "ladder_eta.csv": "channel,bank,policy,eta",
    "dump_q.csv": "channel,event,bank,q_median",
    "tau_bounds.csv": ("setting,channel,ew,ns,lane,check,range,variants,lb,least_variant,span,lb_priced,capped,b4,"
                       "calibration"),
    "phasor14.csv.gz": "channel,cls,pol,a,b,lag_s,lag_class,rho",
}


class HandoffError(ValueError):
    """The directory is not a capture handoff this reader accepts."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _header_key(rel: str) -> str:
    name = rel.rsplit("/", 1)[-1]
    for family in ("cadence_tau", "frame_residual"):
        if name.startswith(family):
            return family
    return name


class CaptureHandoff:
    """One handoff directory, checked on open; :attr:`opened` lists what was read."""

    def __init__(self, directory, *, borrowed: bool = False, measurements: bool = False):
        self.root = Path(directory)
        path = self.root / "manifest.json"
        if not path.is_file():
            raise HandoffError(f"{self.root}: no manifest.json")
        self.manifest = json.loads(path.read_text())
        if (self.manifest.get("schema"), self.manifest.get("schema_version")) != (SCHEMA, SCHEMA_VERSION):
            raise HandoffError(f"{self.root}: schema {self.manifest.get('schema')!r} version "
                               f"{self.manifest.get('schema_version')!r}, expected {SCHEMA!r} {SCHEMA_VERSION}")
        self.files = self.manifest["files"]
        held = [r for r in RECORD_FILES if r in self.files]
        if held and not measurements:
            raise HandoffError(f"{self.root}: holds {held}, which the records take as explicit inputs, not as "
                               "measurements of the capture")
        self.borrowed = borrowed
        self.opened: list[str] = []
        self.check_constants()
        if tuple(self.manifest.get("science_events", ())) != SCIENCE:
            raise HandoffError(f"{self.root}: the science dumps differ from the record's")

    # ---- files
    def check_constants(self) -> None:
        if self.manifest.get("constants") != U.constants():
            raise HandoffError(f"{self.root}: the detector constants differ from the record's (capture_units)")

    def data(self, rel: str) -> bytes:
        """The bytes of a listed file, after its sha256 is checked."""
        if rel not in self.files:
            raise HandoffError(f"{rel}: not in the handoff manifest")
        if rel.rsplit("/", 1)[-1] in BORROWED and not self.borrowed:
            raise HandoffError(f"{rel}: a borrowed quantity, refused on the measured basis")
        data = (self.root / rel).read_bytes()
        if _sha256(data) != self.files[rel]["sha256"]:
            raise HandoffError(f"{rel}: sha256 differs from the manifest")
        self.opened.append(rel)
        return data

    def has(self, rel: str) -> bool:
        return rel in self.files

    def names(self, prefix: str) -> list[str]:
        return sorted(r[len(prefix):] for r in self.files if r.startswith(prefix) and "/" not in r[len(prefix):])

    def text(self, rel: str) -> str:
        data = self.data(rel)
        return (gzip.decompress(data) if rel.endswith(".gz") else data).decode("utf-8")

    def rows(self, rel: str) -> list[dict]:
        """A table's rows, after its header is checked (no missing or extra column)."""
        reader = csv.DictReader(io.StringIO(self.text(rel), newline=""))
        expected = HEADERS.get(_header_key(rel))
        if expected is None:
            raise HandoffError(f"{rel}: no header is declared for this table")
        if reader.fieldnames != expected.split(","):
            got, want = set(reader.fieldnames or ()), set(expected.split(","))
            raise HandoffError(f"{rel}: columns differ (missing {sorted(want - got)}, extra {sorted(got - want)})")
        return list(reader)

    def json(self, rel: str):
        return json.loads(self.text(rel))


def open_handoff(directory, *, borrowed: bool = False, measurements: bool = False) -> CaptureHandoff:
    """The capture handoff at ``directory``; ``measurements`` also reads one of the earlier layout, which held the
    record's own tables (only to build a handoff from it)."""
    return CaptureHandoff(directory, borrowed=borrowed, measurements=measurements)


def table_rows(h: CaptureHandoff, rel: str, path) -> list[dict]:
    """The rows of one of the record's own tables (the table of record, its v7 input, the BAO-basis coherence times)
    from the file at ``path``, its header checked as the record's (:data:`HEADERS`). ``rel`` names the table."""
    if path is None:
        raise HandoffError(f"{rel}: the records take this table as an explicit input, not from the handoff")
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
    expected = HEADERS[_header_key(rel)].split(",")
    if reader.fieldnames != expected:
        got, want = set(reader.fieldnames or ()), set(expected)
        raise HandoffError(f"{path}: columns differ from {rel} (missing {sorted(want - got)}, extra {sorted(got - want)})")
    return rows


def polkey(s):
    return 0 if s == "I" else int(s)           # Stokes I is the single product, read as product 0


# ---------------------------------------------------------------- the ruling's inputs (ruling_a18.py, lines 180 to 266)
def ruling_inputs(h: CaptureHandoff, pol: str = "larger", rescan: bool = False) -> SimpleNamespace:
    """ex, floor, POL_OF_CLASS, tau, tau_least, tau_probe_meas, tau_pol, rho, eta and Qmed, as the release read them
    on the larger per-pol product (``larger``) or on Stokes I (``stokes_i``), with channel 33's ladder thresholds and
    dump medians from its measured-marker rescan when ``rescan``."""
    EXDIR = "stokes_i/" if pol == "stokes_i" else "frame_analysis/"
    FA = "frame_analysis/"
    if pol == "stokes_i": assert not [f for f in h.names(EXDIR) if re.search(r"_pol[01]\.csv$", f)]
    # excess per channel, epoch, class, pol
    ex = {}
    for r in h.rows(EXDIR + "class_excess_epochs.csv"):
        if r["excess"]: ex[(int(r["channel"]), r["epoch"], (int(r["ew"]), int(r["ns"])), polkey(r["pol"]))] = float(r["excess"])
    # floor per class, pol over the four science dumps (channel 37 bins)
    fl = {}
    for r in h.rows(EXDIR + "class_floor_bins.csv"):
        if r["epoch"] in SCIENCE: fl.setdefault(((int(r["ew"]), int(r["ns"])), polkey(r["pol"])), []).append(float(r["excess"]))
    floor = {k: (float(np.mean(v)), float(np.std(v, ddof=1))) for k, v in fl.items()}
    # amendment 11: the polarisation that sets A on each class over the four science dumps
    POL_OF_CLASS = {}
    for ch in PILOT:
        for c in CLS_NAME:
            best = None
            for p in (0, 1):
                vals = [ex[(ch, e, c, p)] for e in SCIENCE if (ch, e, c, p) in ex]
                if not vals or (c, p) not in floor: continue
                an = float(np.median(vals)) - floor[(c, p)][0]
                if best is None or an > best[1]: best = (p, an)
            if best is not None: POL_OF_CLASS[(ch, c)] = best[0]
    # coherence times per class, read on the polarisation that sets A there (amendment 11)
    tau = {}
    tau_least = {}
    tau_probe_meas = {}
    tau_pol = {}
    for c, f in TAU_FILES.items():
        byp = {}
        for p in (0, 1):
            fp = EXDIR + f[:-4] + f"_pol{p}.csv"
            if not h.has(fp): continue
            for r in h.rows(fp):
                if r["bins"] == "inband": byp[(int(r["channel"]), p)] = r
        for r in h.rows(EXDIR + f):
            if r["bins"] != "inband": continue
            ch = int(r["channel"])
            p = POL_OF_CLASS.get((ch, c))
            row = byp.get((ch, p), r) if p is not None else r
            tau[(ch, c)] = (row["status"], float(row["tau_c_s"]) if row["tau_c_s"] else np.nan)
            # amendment 10 item 7: the least of the channel's own trim probes on this class
            vals = [float(m) for m in re.findall(r"(?:measured|bound|constant)\s+([\d.]+)", row.get("probes", "") or "")]
            tl = min(vals) if vals else np.nan
            tr = float(row["tau_c_s"]) if row["tau_c_s"] else np.nan
            tau_least[(ch, c)] = min(tl, tr) if (np.isfinite(tl) and np.isfinite(tr)) else tl
            # amendment 15: the measured and bound probe values, excluding "constant"
            tau_probe_meas[(ch, c)] = [float(m) for m in re.findall(r"(?:measured|bound)\s+([\d.]+)", row.get("probes", "") or "")]
            tau_pol[(ch, c)] = row["pol"]
    # phasor coherence per class (median over the six pairs, in-band)
    rho_v = {}
    for r in h.rows(FA + "lag_coherence_tenclasses_D.csv"):
        if r["bins"] == "inband" and r["cls"].endswith("_x"): rho_v.setdefault((int(r["channel"]), r["cls"][:-2]), []).append(float(r["rho"]))
    rho = {k: float(np.median(v)) for k, v in rho_v.items()}
    # policies: eta from the archive, kept dumps from the kernel runs
    eta = ladder_eta(h, "nominal")
    Qmed = {(c, ev): q for (c, ev), q in dump_q(h, "nominal").items() if ev in SCIENCE}
    if rescan:
        eta[33] = ladder_eta(h, "measured_marker")[33]
        for (c, ev), q in dump_q(h, "measured_marker").items():
            if c == 33 and ev in SCIENCE: Qmed[(33, ev)] = q
    return SimpleNamespace(ex=ex, fl=fl, floor=floor, POL_OF_CLASS=POL_OF_CLASS, tau=tau, tau_least=tau_least,
                           tau_probe_meas=tau_probe_meas, tau_pol=tau_pol, rho=rho, eta=eta, Qmed=Qmed)


def ladder_eta(h: CaptureHandoff, bank: str = "nominal") -> dict:
    """{channel: {policy: eta}}: each rung's archive threshold, in the file's (the policies') order."""
    eta = {}
    for r in h.rows("ladder_eta.csv"):
        if r["bank"] == bank: eta.setdefault(int(r["channel"]), {})[r["policy"]] = float(r["eta"])
    return eta


def dump_q(h: CaptureHandoff, bank: str = "nominal") -> dict:
    """{(channel, event): median Q of the dump}; a channel read twice in a dump keeps its last reading, as the
    release's loop over the kernel run's channels does."""
    out = {}
    for r in h.rows("dump_q.csv"):
        if r["bank"] == bank: out[(int(r["channel"]), r["event"])] = float(r["q_median"])
    return out


def _cls(s):
    a, b = s.strip().strip("()").split(","); return (int(a), int(b))


def tau_lower_bounds(h: CaptureHandoff, censor=False, source="summary", calibrate=False) -> dict:
    """{(channel, class): dict(lane, variants, range, check, b4, lb, least_variant, span, lb_priced, capped,
    calibration)}: a19_inputs.tau_lower_bounds for the setting, with its keys in the release's order."""
    setting = BOUND_SETTINGS.get((bool(censor), source, bool(calibrate)))
    if setting is None:
        raise HandoffError(f"the handoff carries no within-dump bounds for censor={censor}, source={source}, "
                           f"calibrate={calibrate}")
    out = {}
    for r in h.rows("tau_bounds.csv"):
        if r["setting"] != setting: continue
        o = dict(lane=float(r["lane"]), variants={k: float(v) for k, v in json.loads(r["variants"]).items()}, range=r["range"])
        if r["check"] != "": o["check"] = float(r["check"])
        if r["b4"] != "": o["b4"] = r["b4"] == "True"
        o.update(lb=float(r["lb"]), least_variant=r["least_variant"], span=float(r["span"]), lb_priced=float(r["lb_priced"]),
                 capped=r["capped"] == "True")
        if r["calibration"]:
            o["calibration"] = {k: (float(v) if isinstance(v, str) else v) for k, v in json.loads(r["calibration"]).items()}
        out[(int(r["channel"]), (int(r["ew"]), int(r["ns"])))] = o
    return out


# ---------------------------------------------------------------- the channel 24 lane (2020 cohort, item 34)
def cohort24(h: CaptureHandoff) -> SimpleNamespace:
    """The channel 24 lane's measured tables: its events, frames, policy thresholds and dump medians, and the per-event
    tables of every class on Stokes I and on each polarization (sky reference), with the lane's identity."""
    d = h.json("cohort24.json")

    def table(raw):
        out = {}
        for key, x in raw.items():
            e, c = key.split("|"); c = tuple(int(v) for v in c.split(","))
            out[(e, c)] = dict(inband=float(x["inband"]), inband_nopilot=float(x["inband_nopilot"]), n_inband=x["n_inband"],
                               pilot=float(x["pilot"]), floor=[float(v) for v in x["floor"]], ch35_pilot=float(x["ch35_pilot"]),
                               bins={int(f): float(v) for f, v in x["bins"].items()})
        return out
    tables = {("I" if p == "I" else int(p)): table(t) for p, t in d["tables"].items()}
    return SimpleNamespace(EVENTS=list(d["events"]), MAXFR=d["maxfr"], INB=list(d["inb"]), C37=list(d["c37"]),
                           R={tuple([e, int(f)]) for e, f in (k.split("|") for k in d["present"])},
                           dup=[tuple(x) for x in d["dup"]], frames=dict(d["nframes"]),
                           eta={k: float(v) for k, v in d["eta"].items()}, Qmed={e: float(v) for e, v in d["qmed"].items()},
                           tables=tables, lane=d["lane"], code=d["code"], code_sha256=d["code_sha256"],
                           products_sha256=d["products_sha256"], n_products=d["n_products"])


# ---------------------------------------------------------------- the phase limit's class means (phase_limit_a18.py load_raw)
def raw_epochs(h: CaptureHandoff) -> tuple[list, dict]:
    """(labels, {label: {freq_id: dict(ch, raw={class: [pol 0 mean, pol 1 mean]}, t0)}}), in the loader's bin order,
    each mean the numpy scalar the loader computed."""
    d = h.json("phasor/raw_epochs.json")
    names = {f"{c[0]},{c[1]}": c for c in U.NB}

    def scalar(x):
        kind, re_, im_ = x
        return np.dtype(kind).type(complex(float(re_), float(im_)))
    raw = {}
    for label in d["epochs"]:
        raw[label] = {int(f): dict(ch=v["ch"], raw={names[k]: [scalar(x) for x in m] for k, m in v["raw"].items()}, t0=float(v["t0"]))
                      for f, v in d["raw"][label]}
    return list(d["epochs"]), raw


def archive_shares(h: CaptureHandoff) -> list[tuple]:
    """[(ledger file name, intraday share, fast share, ground-filter dB)] in the ledger's file order."""
    return [tuple(x) for x in h.json("archive_shares.json")["records"]]
