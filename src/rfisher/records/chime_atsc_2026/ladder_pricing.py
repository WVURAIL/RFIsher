"""The science columns of the archive releases' coarse ladder, priced from the handoff.

The releases' ``coarse/tradeoffs.csv`` (written by the release tool
``analysis_tools/coarse_retention_diagnostic_v1.py``) mixes the detector's
ladder (each rung's threshold and the frames it keeps on each block, their
half-block drift and support) with a pricing of each rung against the
band's target-time tolerances. The pricing is science and is written here,
with :func:`price` verbatim from that tool, into ``ladder_pricing.csv``:

- the allowance priced is the rung's evaluation-block residual at G = 1
  (the handoff's ``r_sys_incoherent`` of the ladder's evaluation row), and
  the chain gain the band's (``oc_summary``);
- the tolerances are the band's dilation, aperp and apar tolerances at
  zeta = 1 (``channel_tolerances``). The releases' growth (f sigma_8) columns
  are not written: the growth rate sets no tolerance (stage P, 2026-10-06).

The detector columns of ``tradeoffs.csv`` and the per-band ``coarse/chNN.json``
records are the detector's, and the handoff does not carry all of them (the
half-block fields among them); they are not written here.
"""
from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Mapping, Sequence

POLICIES = ("cal_q0.1", "cal_q0.5", "cal_q0.9", "keep_all")
BUDGET = (("dilation", "r_tol_dilation"), ("aperp", "r_tol_aperp"),
          ("apar", "r_tol_apar"))


def price(allowance, gain, tolerance):
    """The release tool's pricing of one allowance against one tolerance."""
    good = lambda x: math.isfinite(x) and x > 0  # noqa: E731
    if not good(tolerance):
        return {'status': 'unpriced target-time tolerance'}
    if not good(allowance):
        return {'status': 'residual allowance unavailable'}
    maximum = tolerance / allowance
    row = {'status': 'conditional', 'tolerance_zeta1': tolerance,
           'maximum_total_gain': maximum,
           'G1_tolerance_fraction': allowance / tolerance,
           'G1_required_suppression_db': max(0.0, 10 * math.log10(allowance / tolerance))}
    if good(gain):
        row.update(chain_tolerance_fraction=allowance * gain / tolerance,
                   chain_required_additional_suppression_db=max(0.0, 10 * math.log10(allowance * gain / tolerance)))
    else:
        row['chain_status'] = 'calibration chain gain unavailable'
    return row


def _num(value) -> float:
    return float(value) if value is not None else math.nan


def ladder_rows(band: str, ladder: Sequence[Mapping], summary: Mapping,
                tolerance: Mapping) -> list[dict]:
    """One row per rung: its threshold and the pricing of its allowance.

    ``ladder`` holds the band's ``coarse_ladder`` rows of the evaluation
    block, ``summary`` its ``coarse_ladder`` summary row and ``tolerance`` its
    ``channel_tolerances`` row.
    """
    by_policy = {r["policy"]: r for r in ladder}
    gain = _num(summary["chain_gain"])
    out = []
    for policy in POLICIES:
        rung = by_policy.get(policy)
        allowance = _num(rung["r_sys_incoherent"]) if rung else math.nan
        row = {"channel": int(band), "policy": policy,
               "eta": _num(rung["eta"]) if rung else math.nan}
        for name, column in BUDGET:
            for k, v in price(allowance, gain, _num(tolerance[column])).items():
                row[f"{name}_{k}"] = v
        out.append(row)
    return out


def write_ladder_pricing(rows: Sequence[Mapping], path: Path) -> Path:
    """``ladder_pricing.csv``: columns in first-seen order, floats as repr."""
    keys: list[str] = []
    for row in rows:
        for k in row:
            if k not in keys:
                keys.append(k)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=keys, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: ("" if v is None or (isinstance(v, float)
                                                     and not math.isfinite(v))
                                 else repr(v) if isinstance(v, float) else v)
                             for k, v in ((k, row.get(k)) for k in keys)})
    return path
