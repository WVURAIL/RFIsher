"""One tolerance per frequency band and scenario, from the per-bin table.

A band overlaps some of the model's bins. Its tolerance in a scenario is the
smallest per-bin tolerance over its bins and the model's required parameters.
Any overlapping bin whose required value was refused at the target time
refuses the band, and so does a set of bins that does not cover the whole
band. Reported parameters are listed in the components and set nothing.
"""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from rfisher.science_model import ScienceModel

from .table import BASIS

REFUSED_PARAMETER = "one or more target-time parameter tolerances refused"
REFUSED_COVERAGE = "forecast bins do not cover the full band"


@dataclass(frozen=True)
class Band:
    """A frequency band: its identifier and its edges in MHz."""

    band_id: str
    low_mhz: float
    high_mhz: float


def read_bands(path: str | Path) -> list[Band]:
    """Bands from a CSV with the columns ``band_id,low_mhz,high_mhz``."""
    with Path(path).open(newline="", encoding="utf-8") as fh:
        return [Band(row["band_id"], float(row["low_mhz"]),
                     float(row["high_mhz"]))
                for row in csv.DictReader(fh)]


def tolerance_of(rows: Sequence[dict], world: str, bins: Sequence[int],
                 parameter: str) -> float:
    """Minimum over every requested bin; any missing or refused target cell refuses."""
    by_bin = {int(r["bin_index"]): r for r in rows if r["world"] == world and r["parameter"] == parameter}
    values = []
    for b in bins:
        row = by_bin.get(int(b))
        if row is None or not row.get("at_target", False):
            return math.nan
        value = float(row["tolerance"])
        if not math.isfinite(value) or value <= 0:
            return math.nan
        values.append(value)
    return min(values) if values else math.nan


def _check_bins(model: ScienceModel, rows: Sequence[dict]) -> None:
    """The table's bins must be the model's, edge for edge."""
    edges = {b.index: (b.low, b.high) for b in model.bins()}
    for row in rows:
        index = int(row["bin_index"])
        if edges.get(index) != (float(row["z_lo"]), float(row["z_hi"])):
            raise ValueError(f"table bin {index} does not match the model's "
                             f"bins")


def band_tolerances(model: ScienceModel, rows: Sequence[dict],
                    bands: Sequence[Band]) -> tuple[list[dict], list[dict]]:
    """``(tolerances, components)`` rows for every band and scenario.

    ``rows`` is the per-bin table (``rfisher.tolerance.table.load``). The
    binding parameter and bin are the first minimum in required-parameter
    order, then in ascending bin order.
    """
    _check_bins(model, rows)
    labels = {b.index: b.label for b in model.bins()}
    required = model.parameters.required
    tolerances, components = [], []
    for band in bands:
        bins, covered = model.bins_for_band(band.low_mhz, band.high_mhz)
        for scenario in model.scenarios:
            values = {p: tolerance_of(rows, scenario.name, bins, p)
                      if covered else math.nan for p in required}
            priced = all(math.isfinite(v) and v > 0 for v in values.values())
            r_tol = min(values.values()) if priced else math.nan
            binding_parameter, binding_bin = "", ""
            for p in required:
                for b in bins:
                    value = tolerance_of(rows, scenario.name, (b,), p)
                    if priced and value == r_tol and binding_parameter == "":
                        binding_parameter, binding_bin = p, b
            for p in model.parameters.all:
                for b in bins:
                    value = tolerance_of(rows, scenario.name, (b,), p)
                    components.append({
                        "band_id": band.band_id, "scenario": scenario.name,
                        "tolerance_basis": BASIS, "parameter": p,
                        "required": p in required, "bin": b,
                        "bin_label": labels[b], "r_tol_component": value,
                        "status": ("accepted" if math.isfinite(value) else
                                   "refused: no stable response at the "
                                   "target time")})
            tolerances.append({
                "band_id": band.band_id, "band_low_mhz": band.low_mhz,
                "band_high_mhz": band.high_mhz, "scenario": scenario.name,
                "role": scenario.role, "r_tol": r_tol,
                "binding_parameter": binding_parameter,
                "binding_bin": binding_bin, "zeta": float(model.zeta),
                "target_time_years": float(model.target_years),
                "suppression_db": float(scenario.suppression_db),
                "tolerance_basis": BASIS,
                "refusal": ("" if priced else REFUSED_PARAMETER if covered
                            else REFUSED_COVERAGE)})
    return tolerances, components
