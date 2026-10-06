"""The handoff files a verdict reads, checked before any value is used.

A characterization directory holds ``oc_table.csv``, ``oc_summary.csv`` and
``manifest.json`` (the operating-characteristic handoff, schema version 1).
:func:`read_characterization` refuses the directory unless

- the manifest names the schema and the version this package vendors, and
  carries every required key;
- every file the manifest lists has the sha256 it records;
- the two tables have exactly the schema's columns, in its order;
- the residual reference and the residual shape are the science model's (a
  tolerance is a tolerance on one residual, in one reference);
- every row's band edges are the manifest's for that band.

:func:`read_tolerances` reads one ``tolerances.csv`` and checks its band
edges against the handoff's. The schema is checked by its columns and keys
directly, so no schema library is needed at run time.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import dataclass
from fractions import Fraction
from importlib.resources import files
from pathlib import Path
from typing import Mapping, Sequence

SCHEMA = "operating_characteristic"
SCHEMA_VERSION = 1
SCHEMA_FILE = "operating_characteristic_v1.schema.json"
SCHEMA_SHA256 = "8267e9e0990ad531675ba5f9ab01aede92cfe4787ada938c7978f7d400143cd2"
TABLE = "oc_table.csv"
SUMMARY = "oc_summary.csv"
MANIFEST = "manifest.json"
COMPLETE_SCOPE = "supported_calibration_candidates"
TOLERANCE_COLUMNS = ("band_id", "band_low_mhz", "band_high_mhz", "scenario",
                     "role", "r_tol", "binding_parameter", "binding_bin",
                     "zeta", "target_time_years", "tolerance_basis",
                     "refusal")


class HandoffError(ValueError):
    """A handoff file is not what its manifest and schema declare."""


def schema() -> dict:
    """The vendored schema, checked against its pin."""
    data = files("rfisher.data").joinpath("schemas", SCHEMA_FILE).read_bytes()
    if hashlib.sha256(data).hexdigest() != SCHEMA_SHA256:
        raise HandoffError(f"{SCHEMA_FILE}: not the pinned schema")
    return json.loads(data)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _cast(kind: str, text: str):
    """A cell as its schema type: an empty float is NaN, an empty integer or
    boolean None, and a string stays as written."""
    if kind == "str":
        return text
    if kind == "float":
        return float(text) if text != "" else math.nan
    if text == "":
        return None
    if kind == "int":
        return int(text)
    if kind == "bool":
        if text not in ("True", "False"):
            raise HandoffError(f"not a boolean: {text!r}")
        return text == "True"
    raise HandoffError(f"unknown column type {kind!r}")


def _read_table(path: Path, columns: Sequence[dict]) -> list[dict]:
    names = [c["name"] for c in columns]
    kinds = {c["name"]: c["type"] for c in columns}
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        header = next(reader, None)
        if header != names:
            raise HandoffError(f"{path.name}: the columns are not the schema's")
        rows = []
        for record in reader:
            if len(record) != len(names):
                raise HandoffError(f"{path.name}: a row has {len(record)} "
                                   f"cells, the header {len(names)}")
            rows.append({n: _cast(kinds[n], v) for n, v in zip(names, record)})
    return rows


@dataclass(frozen=True)
class Characterization:
    """A checked handoff: its manifest, tables and the digests of its files."""

    root: Path
    manifest: Mapping
    table: list
    summary: list
    sha256: Mapping[str, str]
    complete_calibration_grid: bool = False

    @property
    def bands(self) -> dict[str, dict]:
        return {str(b["band_id"]): dict(b) for b in self.manifest["bands"]}

    @property
    def thinned(self) -> bool:
        """Whether the fine surface may be written thinned (not every
        candidate). A manifest that does not say it is complete is read as
        thinned, so a missing statement never completes a set."""
        return not self.complete_calibration_grid


def _integer(value, name: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise HandoffError(f"{name}: expected an integer >= {minimum}")
    return value


def _close(actual, expected, name: str) -> None:
    if not math.isfinite(actual) or not math.isclose(
            actual, expected, rel_tol=1e-12, abs_tol=1e-14):
        raise HandoffError(f"{name}: {actual!r} disagrees with {expected!r}")


def _complete_grid(manifest: Mapping, table: list, summary: list) -> bool:
    """Validate the producer's complete supported calibration candidate set."""
    if manifest.get("fine_surface_rows") != "complete":
        return False
    if manifest.get("fine_surface_scope") != COMPLETE_SCOPE:
        raise HandoffError("complete fine surface requires supported calibration scope")
    if manifest.get("mask_rule") != "statistic > eta":
        raise HandoffError("complete fine surface requires mask_rule 'statistic > eta'")
    bands = {str(b["band_id"]): b for b in manifest["bands"]}
    counts = manifest.get("fine_surface_counts")
    if not isinstance(counts, dict) or set(counts) != set(bands):
        raise HandoffError("fine_surface_counts must include every manifest band")
    summaries = {}
    for row in summary:
        if row["candidate_set"] != "fine_surface":
            continue
        key = (row["band_id"], row["threshold_family"])
        if key in summaries:
            raise HandoffError(f"duplicate fine summary: {key}")
        if row["population"] != "current_era_calibration_block":
            raise HandoffError(f"fine summary population: {key}")
        summaries[key] = row
    for band, families in counts.items():
        if not isinstance(families, dict):
            raise HandoffError(f"fine_surface_counts[{band}]: expected families")
        expected = {f for b, f in summaries if b == band}
        if set(families) != expected:
            raise HandoffError(f"fine_surface_counts[{band}]: summary families differ")
        for family, count in families.items():
            _integer(count, f"fine_surface_counts[{band}][{family}]")
            row = summaries[band, family]
            total = _integer(row["candidates_total"], "candidates_total")
            evaluable = _integer(row["candidates_evaluable"], "candidates_evaluable")
            if count != evaluable or count > total:
                raise HandoffError(f"fine surface summary count differs: {band}/{family}")
    found, previous, denominators, orders = {}, {}, {}, set()
    for row in table:
        if row["candidate_set"] != "fine_surface":
            continue
        band, family, block = row["band_id"], row["threshold_family"], row["block"]
        if block not in ("calibration", "evaluation") or row["population"] != (
                f"current_era_{block}_block"):
            raise HandoffError(f"fine row population/block differ: {band}/{family}")
        rho = _integer(row["rho"], "rho", 1)
        bulk = _integer(row["bulk_size"], "bulk_size", 1)
        if rho > bulk or family != f"rho={rho}" or row["statistic"] != "Z_rho":
            raise HandoffError(f"fine family/rank/statistic differ: {band}/{family}")
        _close(row["rank_fraction"], rho / (bulk + 1), "rank_fraction")
        eta_q16 = _integer(row["eta_q16"], "eta_q16", 1)
        if eta_q16 > 2**64 - 1:
            raise HandoffError("eta_q16 exceeds the unsigned 64-bit deployment range")
        exact = Fraction(eta_q16, 65536)
        try:
            if Fraction(row["eta_exact"]) != exact or row["eta"] != float(exact):
                raise ValueError
        except (ValueError, ZeroDivisionError):
            raise HandoffError(f"eta_q16, eta_exact and eta differ: {band}/{family}") from None
        frames = _integer(row["frames"], "frames", 1)
        kept = _integer(row["kept"], "kept")
        masked = _integer(row["masked"], "masked")
        if kept + masked != frames:
            raise HandoffError(f"kept + masked differs from frames: {band}/{family}")
        _close(row["masked_fraction"], masked / frames, "masked_fraction")
        if kept:
            _close(row["exposure_cost_uniform_loss"], frames / kept,
                   "exposure_cost_uniform_loss")
        if kept:
            for name in ("r_var", "r_sys", "r_sys_incoherent", "r_unmasked"):
                if not math.isfinite(row[name]) or row[name] < 0:
                    raise HandoffError(f"{name}: expected a finite nonnegative residual")
            if not 0 <= row["floor_share"] <= 1:
                raise HandoffError("floor_share must be in [0, 1]")
        cohort = (band, block)
        identity = (frames, row["era_label"], row["era_start"], row["era_end"],
                    row["era_state"], bulk, row["r_unmasked"])
        if denominators.setdefault(cohort, identity) != identity:
            raise HandoffError(f"fine cohort denominator or geometry changes: {band}/{block}")
        if block != "calibration":
            continue
        key = (band, family)
        if key not in summaries:
            raise HandoffError(f"fine calibration row has no summary: {key}")
        if kept < 30:
            raise HandoffError(f"fine calibration support is below 30 frames: {key}")
        order = _integer(row["candidate_order"], "candidate_order")
        if (band, order) in orders:
            raise HandoffError(f"duplicate fine candidate_order: {band}/{order}")
        orders.add((band, order))
        if key in previous:
            old_order, old_eta, old_kept = previous[key]
            if order <= old_order or eta_q16 <= old_eta or kept < old_kept:
                raise HandoffError(f"fine candidate order/threshold/keep is not monotone: {key}")
        previous[key] = (order, eta_q16, kept)
        found[key] = found.get(key, 0) + 1
    for band, families in counts.items():
        for family, count in families.items():
            if found.get((band, family), 0) != count:
                raise HandoffError(f"fine surface row count differs: {band}/{family}")
    return True


def read_characterization(directory: str | Path, *,
                          r_reference: Mapping | None = None,
                          residual_shapes: Sequence[str] | None = None
                          ) -> Characterization:
    """Read and check a characterization directory (see the module docstring)."""
    root = Path(directory)
    spec = schema()
    manifest_path = root / MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != SCHEMA or \
            manifest.get("schema_version") != SCHEMA_VERSION:
        raise HandoffError(f"{manifest_path}: schema {manifest.get('schema')!r}"
                           f" version {manifest.get('schema_version')!r}, not "
                           f"{SCHEMA!r} version {SCHEMA_VERSION}")
    missing = [k for k in spec["required"] if k not in manifest]
    if missing:
        raise HandoffError(f"{manifest_path}: missing {missing}")
    listed = manifest["files"]
    if not {TABLE, SUMMARY} <= set(listed):
        raise HandoffError(f"{manifest_path}: files must list {TABLE} and "
                           f"{SUMMARY}")
    digests = {}
    for name, expected in listed.items():
        relative = Path(name)
        if (relative.is_absolute() or ".." in relative.parts or "\\" in name
                or (root / relative).resolve().is_relative_to(root.resolve()) is False):
            raise HandoffError(f"unsafe handoff file path: {name!r}")
        found = sha256_file(root / name)
        if found != expected:
            raise HandoffError(f"{root / name}: sha256 {found}, the manifest "
                               f"records {expected}")
        digests[name] = found
    digests[MANIFEST] = sha256_file(manifest_path)
    if r_reference is not None and dict(manifest["r_reference"]) \
            != dict(r_reference):
        raise HandoffError(f"{manifest_path}: r_reference "
                           f"{manifest['r_reference']} is not the science "
                           f"model's {dict(r_reference)}")
    if residual_shapes is not None and \
            manifest["residual_shape"] not in tuple(residual_shapes):
        raise HandoffError(f"{manifest_path}: residual shape "
                           f"{manifest['residual_shape']!r} is not one the "
                           f"science model describes {tuple(residual_shapes)}")
    table = _read_table(root / TABLE, spec["x-oc-table-columns"])
    summary = _read_table(root / SUMMARY, spec["x-oc-summary-columns"])
    band_ids = [str(b["band_id"]) for b in manifest["bands"]]
    if len(set(band_ids)) != len(band_ids):
        raise HandoffError("duplicate manifest bands")
    out = Characterization(root, manifest, table, summary, digests)
    edges = {k: (float(b["low_mhz"]), float(b["high_mhz"]))
             for k, b in out.bands.items()}
    for name, rows in ((TABLE, table), (SUMMARY, summary)):
        for row in rows:
            band = str(row["band_id"])
            if edges.get(band) != (row["band_low_mhz"], row["band_high_mhz"]):
                raise HandoffError(f"{name}: band {band} edges "
                                   f"{(row['band_low_mhz'], row['band_high_mhz'])}"
                                   f" are not the manifest's {edges.get(band)}")
    complete = _complete_grid(manifest, table, summary)
    return Characterization(root, manifest, table, summary, digests, complete)


def read_tolerances(path: str | Path, bands: Mapping[str, Mapping] | None = None
                    ) -> list[dict]:
    """The rows of one ``tolerances.csv``; band edges checked against ``bands``."""
    path = Path(path)
    kinds = {"band_low_mhz": "float", "band_high_mhz": "float",
             "r_tol": "float", "zeta": "float", "target_time_years": "float",
             "binding_bin": "int"}
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if tuple(reader.fieldnames or ()) != TOLERANCE_COLUMNS:
            raise HandoffError(f"{path}: the columns are not a tolerance "
                               "table's")
        rows = [{k: _cast(kinds.get(k, "str"), v) for k, v in r.items()}
                for r in reader]
    for row in rows:
        if bands is None or row["band_id"] not in bands:
            continue
        band = bands[row["band_id"]]
        if (float(band["low_mhz"]), float(band["high_mhz"])) != (
                row["band_low_mhz"], row["band_high_mhz"]):
            raise HandoffError(f"{path}: band {row['band_id']} edges differ "
                               "from the handoff's")
    return rows
