"""Two frozen reference tolerances, written as band tolerance rows.

The per-bin grid table (:mod:`rfisher.tolerance.table`) is one tolerance
basis. Two earlier results price bands on bases of their own, and are kept as
data beside the grid table, byte for byte and pinned by sha256:

- ``exact_time_reference_2026-09-09``: the qualified exact-time reference at
  one on-sky year, integrated directly at the target time rather than read
  from a year grid. Its per-band tolerance is ``conditional_reference_amplitude``
  (the least over the band's bins of the binding required component), in the
  scenario without a delay filter (``none``, the rule scenario).
- ``coarse_world_sensitivity_2026-09-09``: the tolerance of the deployed delay
  filter (``deployed``, a sensitivity scenario) with the suppression S it
  assumes, per band, from the primary dilation basis at zeta 1. Its per-bin
  tolerances are those of the bands that overlap a single bin.

:func:`reference_rows` writes both as rows of ``tolerances.csv`` and
``tolerance_components.csv`` with the basis named in ``tolerance_basis``.
Every value is the frozen file's own number: a float read from its decimal
string and written back with ``repr`` returns the same string.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import math
from importlib.resources import files
from pathlib import Path
from typing import Sequence

EXACT_TIME = "exact_time_reference_2026-09-09"
COARSE_WORLD = "coarse_world_sensitivity_2026-09-09"
BASES = (EXACT_TIME, COARSE_WORLD)
DATA = "rfisher.data"
DIRECTORY = "tolerances"
# The vendored files and the sha256 of their bytes (the coarse-world file is
# stored gzip-compressed; the pin is of the decoded bytes, the frozen file's).
EXACT_TIME_FILES = {
    "channels.csv":
        "6b8634f0f88a861a10c07b9a1ad1c807512bd4e61204a89a6fb3a3bde0fe86de",
    "reference.json":
        "d4b0f30240368f5b0e93cbbc2be5d33429661a5af53e771aeb7d3a798b670611",
    "manifest.json":
        "37ff02d1654a952a8f8cbedf6e59dd6559aae470b78d098f1b8e6981e117cdd8",
}
COARSE_WORLD_FILE = "coarse_world_sensitivity_2026-09-09.csv.gz"
COARSE_WORLD_SHA256 = (
    "cdc5bba4056d511cece0b4b29f9971c4631c6f666a81f085ace0a128f5ad9bf0")
SCENARIOS = {EXACT_TIME: ("none", "rule"),
             COARSE_WORLD: ("deployed", "sensitivity")}
# The rows of the coarse-world table that carry the deployed tolerance.
COARSE_WORLD_SELECTION = {"world": "deployed", "science_group": "dilation",
                          "zeta": "1.0", "tolerance_basis": "primary"}
REFUSED_ABSENT = "the reference prices no band with this id"
REFUSED_EDGES = "the band edges differ from the reference's"


def _read(name: str) -> bytes:
    return files(DATA).joinpath(DIRECTORY, name).read_bytes()


def _checked(name: str, data: bytes, expected: str) -> bytes:
    found = hashlib.sha256(data).hexdigest()
    if found != expected:
        raise ValueError(f"{name}: sha256 {found}, the vendored file is "
                         f"{expected}")
    return data


def exact_time_files() -> dict[str, bytes]:
    """The exact-time reference's three files, each checked against its pin."""
    return {name: _checked(name, _read(f"{EXACT_TIME}/{name}"), sha)
            for name, sha in EXACT_TIME_FILES.items()}


def coarse_world_bytes() -> bytes:
    """The decoded coarse-world table, checked against its pin."""
    return _checked(COARSE_WORLD_FILE,
                    gzip.decompress(_read(COARSE_WORLD_FILE)),
                    COARSE_WORLD_SHA256)


def _csv(data: bytes) -> list[dict]:
    return list(csv.DictReader(io.StringIO(data.decode("utf-8"))))


def _bins(text: str) -> tuple[int, ...]:
    return tuple(int(b) for b in text.split(";") if b)


def exact_time_bands() -> dict[str, dict]:
    """``{band id: the reference's row}``, its bins as integers."""
    rows = _csv(exact_time_files()["channels.csv"])
    return {r["channel"]: {**r, "bins": _bins(r["bins"])}
            for r in rows if r["channel"].isdigit()}


def exact_time_bins() -> dict[int, dict]:
    """``{bin: {value, parameter, label}}``: each bin's binding component."""
    doc = json.loads(exact_time_files()["reference.json"])
    return {int(b["bin_index"]): {
        "value": float(b["conditional_reference_amplitude"]),
        "parameter": b["binding_parameter"],
        "label": f"z {b['z_low']!r}-{b['z_high']!r}"} for b in doc["bins"]}


def exact_time_conditions() -> dict:
    """The target time (years) and zeta the reference was computed at."""
    doc = json.loads(exact_time_files()["reference.json"])
    return {"target_time_years": float(doc["retained_on_sky_hours"]) / 8760.0,
            "zeta": float(doc["zeta"])}


def coarse_world_bands() -> dict[str, dict]:
    """``{band id: {r_tol, suppression_db, bins}}`` from the deployed rows.

    Every selected row of a band carries the same tolerance and suppression;
    a band whose rows disagree is refused here rather than read.
    """
    out: dict[str, dict] = {}
    for r in _csv(coarse_world_bytes()):
        if any(r[k] != v for k, v in COARSE_WORLD_SELECTION.items()):
            continue
        if not r["base_tolerance_zeta1"]:
            continue
        entry = {"r_tol": r["base_tolerance_zeta1"],
                 "suppression_db": r["suppression_db"],
                 "target_time_years": r["retained_onsky_year_target"],
                 "bins": _bins(r["bins"])}
        if out.setdefault(r["channel"], entry) != entry:
            raise ValueError(f"{COARSE_WORLD}: band {r['channel']} has rows "
                             "with different tolerances")
    return out


def coarse_world_bins() -> dict[int, float]:
    """``{bin: tolerance}`` from the bands that overlap that bin alone."""
    values: dict[int, set] = {}
    for entry in coarse_world_bands().values():
        if len(entry["bins"]) == 1:
            values.setdefault(entry["bins"][0], set()).add(entry["r_tol"])
    if any(len(v) != 1 for v in values.values()):
        raise ValueError(f"{COARSE_WORLD}: a bin has two single-bin "
                         "tolerances")
    return {b: float(v.pop()) for b, v in values.items()}


def _edges_match(band, row) -> bool:
    return (float(row["frequency_low_MHz"]) == float(band.low_mhz)
            and float(row["frequency_high_MHz"]) == float(band.high_mhz))


def _row(band, basis, r_tol, binding_parameter, binding_bin,
         suppression_db, conditions, refusal):
    scenario, role = SCENARIOS[basis]
    return {"band_id": band.band_id, "band_low_mhz": band.low_mhz,
            "band_high_mhz": band.high_mhz, "scenario": scenario,
            "role": role, "r_tol": r_tol,
            "binding_parameter": binding_parameter,
            "binding_bin": binding_bin, "zeta": conditions["zeta"],
            "target_time_years": conditions["target_time_years"],
            "suppression_db": suppression_db, "tolerance_basis": basis,
            "refusal": refusal}


def _component(band, basis, parameter, b, label, value):
    scenario, _ = SCENARIOS[basis]
    return {"band_id": band.band_id, "scenario": scenario,
            "tolerance_basis": basis, "parameter": parameter,
            "required": True, "bin": b, "bin_label": label,
            "r_tol_component": value,
            "status": "accepted" if math.isfinite(value) else
            "refused: not in the reference"}


def reference_rows(basis: str, bands: Sequence) -> tuple[list[dict],
                                                         list[dict]]:
    """``(tolerances, components)`` rows of one reference basis.

    A band is matched by its id and must have the reference's edges; a band
    the reference does not price, or prices with other edges, is written
    with an empty tolerance and the reason.
    """
    if basis not in BASES:
        raise ValueError(f"unknown reference basis {basis!r}; one of {BASES}")
    exact = exact_time_bands()
    conditions = exact_time_conditions()
    per_bin = exact_time_bins()
    labels = {b: v["label"] for b, v in per_bin.items()}
    tolerances, components = [], []
    if basis == EXACT_TIME:
        for band in bands:
            row = exact.get(band.band_id)
            refusal = ("" if row is not None and _edges_match(band, row) else
                       REFUSED_ABSENT if row is None else REFUSED_EDGES)
            if refusal:
                tolerances.append(_row(band, basis, math.nan, "", "", 0.0,
                                       conditions, refusal))
                continue
            tolerances.append(_row(
                band, basis, float(row["conditional_reference_amplitude"]),
                row["binding_parameter"], int(row["binding_bin"]), 0.0,
                conditions, ""))
            for b in row["bins"]:
                entry = per_bin.get(b, {"value": math.nan, "parameter": "",
                                        "label": ""})
                components.append(_component(band, basis, entry["parameter"],
                                             b, entry["label"],
                                             entry["value"]))
        return tolerances, components
    coarse = coarse_world_bands()
    coarse_bins = coarse_world_bins()
    for band in bands:
        entry = coarse.get(band.band_id)
        row = exact.get(band.band_id)
        refusal = ("" if entry is not None and row is not None
                   and _edges_match(band, row) else
                   REFUSED_ABSENT if entry is None or row is None
                   else REFUSED_EDGES)
        if refusal:
            tolerances.append(_row(band, basis, math.nan, "", "", math.nan,
                                   conditions, refusal))
            continue
        tolerances.append(_row(
            band, basis, float(entry["r_tol"]), "", "",
            float(entry["suppression_db"]),
            {"zeta": float(COARSE_WORLD_SELECTION["zeta"]),
             "target_time_years": float(entry["target_time_years"])}, ""))
        for b in entry["bins"]:
            components.append(_component(band, basis, "dilation", b,
                                         labels.get(b, ""),
                                         coarse_bins.get(b, math.nan)))
    return tolerances, components


def provenance(bases: Sequence[str], bands_path: str | Path) -> dict:
    """What a written reference table was built from."""
    return {
        "schema": 3,
        "bases": list(bases),
        "files": {**{f"{EXACT_TIME}/{k}": v
                     for k, v in EXACT_TIME_FILES.items()},
                  COARSE_WORLD_FILE: COARSE_WORLD_SHA256},
        "bands_sha256": hashlib.sha256(
            Path(bands_path).read_bytes()).hexdigest(),
    }
