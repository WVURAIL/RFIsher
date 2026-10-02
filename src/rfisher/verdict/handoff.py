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
from importlib.resources import files
from pathlib import Path
from typing import Mapping, Sequence

SCHEMA = "operating_characteristic"
SCHEMA_VERSION = 1
SCHEMA_FILE = "operating_characteristic_v1.schema.json"
SCHEMA_SHA256 = "ab41499f06267245693eb0ac16621ddadff7c67b4791f0fce73f924991a9456c"
TABLE = "oc_table.csv"
SUMMARY = "oc_summary.csv"
MANIFEST = "manifest.json"
TOLERANCE_COLUMNS = ("band_id", "band_low_mhz", "band_high_mhz", "scenario",
                     "role", "r_tol", "binding_parameter", "binding_bin",
                     "zeta", "target_time_years", "suppression_db",
                     "tolerance_basis", "refusal")


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

    @property
    def bands(self) -> dict[str, dict]:
        return {str(b["band_id"]): dict(b) for b in self.manifest["bands"]}

    @property
    def thinned(self) -> bool:
        """Whether the fine surface may be written thinned (not every
        candidate). A manifest that does not say it is complete is read as
        thinned, so a missing statement never completes a set."""
        rows = self.manifest.get("fine_surface_rows")
        return rows is None or str(rows).startswith("thinned")


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
    return out


def read_tolerances(path: str | Path, bands: Mapping[str, Mapping] | None = None
                    ) -> list[dict]:
    """The rows of one ``tolerances.csv``; band edges checked against ``bands``."""
    path = Path(path)
    kinds = {"band_low_mhz": "float", "band_high_mhz": "float",
             "r_tol": "float", "zeta": "float", "target_time_years": "float",
             "suppression_db": "float", "binding_bin": "int"}
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
