"""The per-bin tolerance table and the band tables, with their provenance.

The per-bin table has one row per scenario, bin and parameter. Its layout is
frozen: the scenario column is named ``world``, floats are written as their
``repr`` (so they read back exactly), and lines end in ``\\n``. Beside it, a
``.provenance.json`` sidecar (identity schema 3) records content digests only:
the CSV, the tolerance code, and whatever the science model says its
responses depend on. It holds no commit and no dirty flag, so it does not
change with every commit.

:func:`build` recomputes the table and refuses to change the bytes of an
existing one unless asked to. :func:`load` checks the CSV against its sidecar,
and :func:`verify` checks the sidecar against the current inputs; neither
opens a bank.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from pathlib import Path
from typing import Sequence

from rfisher.science_model import ScienceModel

from . import rule

COLUMNS = ("world", "bin_index", "z_lo", "z_hi", "parameter", "tolerance",
           "at_target", "years_used", "years_accepted", "years_refused")
IDENTITY_SCHEMA = 3
BASIS = "grid_T1yr_stability_gated"
BAND_COLUMNS = ("band_id", "band_low_mhz", "band_high_mhz", "scenario", "role",
                "r_tol", "binding_parameter", "binding_bin", "zeta",
                "target_time_years", "suppression_db", "tolerance_basis",
                "refusal")
COMPONENT_COLUMNS = ("band_id", "scenario", "tolerance_basis", "parameter",
                     "required", "bin", "bin_label", "r_tol_component",
                     "status")
SOURCES = ("rule.py", "bands.py", "table.py")


def _cell(value):
    """Floats round-trip exactly; ``numpy`` scalars are written as plain floats."""
    return repr(float(value)) if isinstance(value, float) else value


def sidecar(path: str | Path) -> Path:
    """The provenance file beside a table."""
    return Path(path).with_suffix(".provenance.json")


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def render(rows: Sequence[dict], columns: Sequence[str]) -> bytes:
    """The CSV bytes of ``rows`` in the given column order."""
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(columns),
                            lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: _cell(v) for k, v in row.items()})
    return stream.getvalue().encode("utf-8")


def identity(model: ScienceModel, path: str | Path, *,
             responses: bool = True) -> dict:
    """Identity schema 3 of the table at ``path``: content digests only.

    With ``responses`` False, the digests the model can give only by loading
    a response are left out.
    """
    here = Path(__file__).resolve().parent
    sources = {f"rfisher/tolerance/{name}": sha256_file(here / name)
               for name in SOURCES}
    described = model.identity(responses=responses)
    sources.update(described["sources"])
    out = {key: value for key, value in described.items() if key != "sources"}
    out.update(schema=IDENTITY_SCHEMA, target_years=float(model.target_years),
               sources=dict(sorted(sources.items())),
               csv_sha256=sha256_file(path))
    return out


def build(model: ScienceModel, out: str | Path, *,
          accept_new: bool = False) -> list[dict]:
    """Compute the table, write it and its sidecar, and return its rows.

    An existing table is rewritten only with identical bytes, unless
    ``accept_new`` is given: a tolerance table never changes silently.
    """
    out = Path(out)
    rows = rule.tolerance_rows(model)
    data = render(rows, COLUMNS)
    if out.exists() and out.read_bytes() != data and not accept_new:
        raise ValueError(
            f"{out}: the rebuilt tolerance table differs from the existing "
            f"one ({hashlib.sha256(data).hexdigest()} against "
            f"{sha256_file(out)}); pass accept_new to replace it")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    sidecar(out).write_text(
        json.dumps(identity(model, out), indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    return rows


def _number(value: str) -> float:
    return float(value) if value not in ("", "nan", None) else math.nan


def _recorded(path: Path) -> dict:
    record = sidecar(path)
    if not record.is_file():
        raise ValueError(f"{path}: no provenance sidecar {record.name}")
    return json.loads(record.read_text(encoding="utf-8"))


def _leaves(value, prefix=()):
    """``(key path, value)`` for every leaf of a nested mapping."""
    if isinstance(value, dict) and value:
        for key, item in value.items():
            yield from _leaves(item, prefix + (str(key),))
    else:
        yield prefix, value


def verify(model: ScienceModel, path: str | Path) -> None:
    """Refuse a table whose sidecar no longer describes its inputs.

    Every digest of the sidecar that needs no response loaded is recomputed
    from the current inputs: the CSV, the tolerance code, and whatever the
    model gives without loading a response (for the RadioFisher model, its
    sources, the profile, the science register, the bank source and the
    bytes of each response bank). A digest that needs a response loaded, a
    field of a ``banks`` entry that the model leaves out without its
    response, is recomputed only by :func:`build`. Never opens a bank.
    """
    path = Path(path)
    then = dict(_leaves(_recorded(path)))
    current = identity(model, path, responses=False)
    now = dict(_leaves(current))
    listed = set(current.get("banks") or {})
    stale = []
    for key in sorted(set(then) | set(now)):
        if key not in now and key[:1] == ("banks",) and len(key) > 2 \
                and key[1] in listed:
            continue                  # needs the response; build checks it
        if then.get(key) != now.get(key):
            stale.append(f"{'/'.join(key)}: recorded {then.get(key)!r}, "
                         f"now {now.get(key)!r}")
    if stale:
        raise ValueError(
            f"{path}: the table's provenance no longer matches its inputs; "
            "rebuild it with 'rfisher tolerance build'\n  "
            + "\n  ".join(stale))


def load(path: str | Path) -> list[dict]:
    """The rows of an authenticated table; never opens a bank.

    The CSV must match the ``csv_sha256`` its sidecar records.
    """
    path = Path(path)
    recorded = _recorded(path).get("csv_sha256")
    if recorded != sha256_file(path):
        raise ValueError(f"{path}: the table does not match the csv_sha256 "
                         f"its sidecar records")
    with path.open(newline="", encoding="utf-8") as fh:
        return [{**r, "bin_index": int(r["bin_index"]),
                 "z_lo": float(r["z_lo"]), "z_hi": float(r["z_hi"]),
                 "at_target": str(r.get("at_target", "")).lower() == "true",
                 "years_used": _number(r.get("years_used")),
                 "tolerance": _number(r["tolerance"]),
                 "years_accepted": int(r["years_accepted"]),
                 "years_refused": int(r["years_refused"])}
                for r in csv.DictReader(fh)]


def write_bands(tolerances: Sequence[dict], components: Sequence[dict],
                out: str | Path, provenance: dict) -> tuple[Path, Path]:
    """Write ``tolerances.csv`` and ``tolerance_components.csv`` into ``out``.

    A refused value is written as an empty cell; every other float as its
    ``repr``. ``provenance`` goes beside them.
    """
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    paths = (out / "tolerances.csv", out / "tolerance_components.csv")
    for path, rows, columns in zip(paths, (tolerances, components),
                                   (BAND_COLUMNS, COMPONENT_COLUMNS)):
        path.write_bytes(render(
            [{k: ("" if isinstance(v, float) and not math.isfinite(v) else v)
              for k, v in row.items()} for row in rows], columns))
    record = dict(provenance, tolerances_sha256=sha256_file(paths[0]),
                  components_sha256=sha256_file(paths[1]))
    (out / "tolerances.provenance.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return paths
