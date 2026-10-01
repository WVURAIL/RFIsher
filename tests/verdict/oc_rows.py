"""Operating-characteristic rows built from histogram fixtures, for the verdict tests.

The detector writes one row per evaluable candidate: for each rank in turn,
the multipliers in increasing order, the kept frames and residual sums
accumulated over the grid, a candidate skipped when it keeps fewer than 30
frames or is ineligible. The same accumulation here gives the same floats as
the enumeration the earlier selector ran, so a selection over these rows can
be compared with that selector's, value for value.
"""
from __future__ import annotations

import math

MIN_KEPT = 30
Q16 = 1 << 16


def histogram_rows(histograms: dict, *, band_id: str = "99") -> list[dict]:
    """OC rows (the columns the verdict reads) of ``{rho: histogram spec}``."""
    rows = []
    order = 0
    for rho in sorted(histograms, key=int):
        h = histograms[rho]
        frames = sum(h["counts"])
        variance = h.get("variance_residual_sums")
        eligible = h.get("candidate_eligible")
        kept = 0
        systematic = 0.0
        var = 0.0
        for index, q16 in enumerate(h["candidate_multiplier_q16"]):
            kept += h["counts"][index]
            systematic += h["systematic_residual_sums"][index]
            if variance is not None:
                var += variance[index]
            if kept < MIN_KEPT:
                continue
            if eligible is not None and not eligible[index]:
                continue
            masked = frames - kept
            f = masked / frames
            rows.append({
                "band_id": band_id, "band_low_mhz": 1.0, "band_high_mhz": 2.0,
                "era_label": "fixture", "block": "calibration",
                "candidate_set": "fine_surface",
                "population": "current_era_calibration_block",
                "threshold_family": f"rho={int(rho)}",
                "candidate_order": order, "eta": int(q16) / Q16,
                "masked_fraction": f, "r_sys": systematic / kept,
                "r_sys_incoherent": systematic / kept,
                "r_var": (var / kept) if variance is not None else None,
                "floor_share": 0.0, "rho": int(rho), "eta_q16": int(q16)})
            order += 1
    return rows


def summary_row(family: str, rows: list[dict], **fields) -> dict:
    """A minimal ``oc_summary`` row of one family."""
    etas = [r["eta"] for r in rows if r["threshold_family"] == family]
    base = {"threshold_family": family, "band_id": "99",
            "candidate_set": "fine_surface",
            "eta_eval": min(etas) if etas else math.nan,
            "eta_pfa": math.nan, "eta_pfa_status": "not computed: statistic Z_rho",
            "chain_gain_status": "measured", "stability_status": "passed",
            "refusal": "", "floor_verified": False}
    base.update(fields)
    return base
