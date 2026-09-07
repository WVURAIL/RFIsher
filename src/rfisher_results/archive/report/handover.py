"""The per-channel handover disposition (chapter 9, ``sec:tolerance:verdicts``,
the closing stub): every CHIME coarse channel of the declared inclusive
edge-bin range ``freq_id = 492..845`` (the ATSC 1.0 allocation, 470-608 MHz),
dispositioned by the screening class of the allocation it belongs to.

Coarse channel ``k`` is centred on ``800 MHz - k f_s`` with ``f_s =
390.625 kHz`` and covers ``+-f_s/2``; it belongs to every allocation whose
6 MHz band it overlaps (an edge channel straddles two allocations). The rules
the text adopts for the handover:

- an allocation that is not an occupancy-wall excision candidate keeps every
  one of its channels, ``kept-and-masked`` at the channel's operating point
  (this run: the diagnostic point; the survey flag is the reference);
- an excised allocation discards its interior but keeps a boundary channel
  it shares with a kept allocation, and keeps its pilot-bin channel as a
  ``monitoring tap``;
- an edge shared by two excised allocations is discarded.

Columns of ``handover_disposition.tex`` (one row per allocation): channel,
allocation (MHz), ``freq_id`` range, coarse channels, screening class, policy,
kept / discarded channel counts, pilot-bin ``freq_id``, the survey-flag masked
fraction and the diagnostic point's masked fraction with their integration-time
cost factors ``1/(1-f)`` (the inclusive keep priced at the coherence cap the
chain books). Band-level numbers: kept and discarded channel counts over the
354 and the mean cost factor over the kept allocations.

Ledger keys: geometry.allocation_low_mhz/high_mhz, geometry.freq_id (from the
channel record), screening.screening_class, screening.survey_flag_rate_era,
selection.diagnostic_masked_fraction.
"""
from __future__ import annotations

import math

from .core import Fragment, Run, booktabs, fmt, tex

SAMPLE_RATE_MHZ = 0.390625
TOP_MHZ = 800.0
FREQ_ID_RANGE = (492, 845)
EXCISION = "occupancy-wall excision candidate"
KEPT = "kept-and-masked"
EXCISED = "excised interior"
TAP = "monitoring tap"


def _num(value) -> float:
    """A ledger value as a float; JSON null (a NaN in the ledger) is NaN."""
    try:
        return float(value) if value is not None else math.nan
    except (TypeError, ValueError):
        return math.nan


def coarse_channels(low_mhz: float, high_mhz: float) -> list[int]:
    """Every ``freq_id`` whose coarse channel overlaps ``[low, high]`` MHz, ascending."""
    out = []
    for k in range(FREQ_ID_RANGE[0], FREQ_ID_RANGE[1] + 1):
        centre = TOP_MHZ - k * SAMPLE_RATE_MHZ
        if centre + SAMPLE_RATE_MHZ / 2 > low_mhz and centre - SAMPLE_RATE_MHZ / 2 < high_mhz:
            out.append(k)
    return out


def disposition(run: Run) -> tuple[list[dict], dict]:
    """Per-allocation rows and the band-level counts."""
    channels = run.by_channel()
    alloc = {}
    for ch, c in channels.items():
        g = c.section("geometry")
        lo, hi = _num(g.get("allocation_low_mhz")), _num(g.get("allocation_high_mhz"))
        if not (math.isfinite(lo) and math.isfinite(hi)):
            continue
        alloc[ch] = {"low": lo, "high": hi, "bins": coarse_channels(lo, hi), "class": c.screening.get("screening_class", ""),
                     "pilot_bin": int(c.freq_id), "flag": _num(c.screening.get("survey_flag_rate_era")),
                     "f_diag": _num(c.selection.get("diagnostic_masked_fraction")) if c.has("selection") else math.nan}
    excised = {ch for ch, a in alloc.items() if a["class"] == EXCISION}
    owners: dict[int, set] = {}
    for ch, a in alloc.items():
        for k in a["bins"]:
            owners.setdefault(k, set()).add(ch)
    status: dict[int, str] = {}
    for k in range(FREQ_ID_RANGE[0], FREQ_ID_RANGE[1] + 1):
        own = owners.get(k, set())
        kept_owner = any(ch not in excised for ch in own)
        if kept_owner:
            status[k] = KEPT
        elif any(alloc[ch]["pilot_bin"] == k for ch in own):
            status[k] = TAP
        else:
            status[k] = EXCISED
    rows = []
    for ch in sorted(alloc):
        a = alloc[ch]
        bins = a["bins"]
        kept = [k for k in bins if status[k] in (KEPT, TAP)]
        rows.append({"channel": ch, "low": a["low"], "high": a["high"], "freq_lo": bins[0], "freq_hi": bins[-1], "n_bins": len(bins),
                     "class": a["class"], "policy": (KEPT if ch not in excised else EXCISED + " + " + TAP),
                     "kept": len(kept), "discarded": len(bins) - len(kept), "pilot_bin": a["pilot_bin"],
                     "flag": a["flag"], "cost_flag": (1.0 / (1.0 - a["flag"]) if a["flag"] < 1.0 else math.inf) if math.isfinite(a["flag"]) else math.nan,
                     "f_diag": a["f_diag"], "cost_diag": 1.0 / (1.0 - a["f_diag"]) if (math.isfinite(a["f_diag"]) and a["f_diag"] < 1.0) else math.nan})
    total = FREQ_ID_RANGE[1] - FREQ_ID_RANGE[0] + 1
    n_kept = sum(1 for k in status if status[k] == KEPT)
    n_tap = sum(1 for k in status if status[k] == TAP)
    kept_rows = [r for r in rows if r["class"] != EXCISION]
    costs = [r["cost_flag"] for r in kept_rows if math.isfinite(r["cost_flag"])]
    band = {"coarse_channels": total, "kept": n_kept, "monitoring_taps": n_tap, "discarded": total - n_kept - n_tap,
            "allocations_kept": len(kept_rows), "allocations_excised": len(excised),
            "mean_cost_factor_at_flag_kept": sum(costs) / len(costs) if costs else math.nan}
    return rows, band


def build(run: Run) -> Fragment:
    rows, band = disposition(run)
    header = ["ch", "MHz", r"\texttt{freq\_id}", "$n$", "class", "policy", "kept", "disc.", "tap", r"$f_{\rm flag}$", r"$1/(1-f_{\rm flag})$", r"$f_{\rm diag}$"]
    cells = []
    frag = Fragment("handover_disposition", "tab:tolerance:disposition", "")
    for r in rows:
        ch = r["channel"]
        short = {EXCISION: "excision", "measurement-bound on floor": "bound (floor)", "measurement-bound on tau_c": r"bound ($\tau_c$)",
                 "off-era": "off-era", "recovery candidate": "recovery"}.get(r["class"], tex(r["class"]))
        policy = "kept, masked" if r["class"] != EXCISION else "interior excised; tap"
        cells.append([str(ch), f"{r['low']:.0f}--{r['high']:.0f}", f"{r['freq_lo']}--{r['freq_hi']}", str(r["n_bins"]), short, policy,
                      str(r["kept"]), str(r["discarded"]), str(r["pilot_bin"]), fmt(r["flag"], 3),
                      (fmt(r["cost_flag"], 1) if math.isfinite(r["cost_flag"]) else r"$\infty$"), fmt(r["f_diag"], 3)])
        frag.add(f"ch09.disposition.freq_lo.ch{ch}", r["freq_lo"], kind="int", row={"channel": ch}, column="freq_id")
        frag.add(f"ch09.disposition.freq_hi.ch{ch}", r["freq_hi"], kind="int", row={"channel": ch}, column="freq_id")
        frag.add(f"ch09.disposition.kept.ch{ch}", r["kept"], kind="int", row={"channel": ch}, column="kept")
        frag.add(f"ch09.disposition.discarded.ch{ch}", r["discarded"], kind="int", row={"channel": ch}, column="disc.")
        frag.add(f"ch09.disposition.policy.ch{ch}", policy, kind="text", renderings=(policy,), row={"channel": ch}, column="policy")
        frag.add(f"ch09.disposition.flag.ch{ch}", r["flag"], precision=3, row={"channel": ch}, column="f_flag")
        if math.isfinite(r["cost_flag"]):
            frag.add(f"ch09.disposition.cost_flag.ch{ch}", r["cost_flag"], precision=1, row={"channel": ch}, column="cost_flag")
        if math.isfinite(r["f_diag"]):
            frag.add(f"ch09.disposition.f_diag.ch{ch}", r["f_diag"], precision=3, row={"channel": ch}, column="f_diag")
    frag.tex = booktabs(header, cells, "lllrllrrrrrr")
    for k, v in band.items():
        frag.add(f"ch09.disposition.{k}", v, kind="int" if isinstance(v, int) else "float", precision=None if isinstance(v, int) else 2, column=k)
    frag.notes.append(f"{band['kept']} coarse channels kept and masked, {band['monitoring_taps']} monitoring taps, {band['discarded']} discarded of {band['coarse_channels']}; "
                      f"{band['allocations_kept']} allocations kept, {band['allocations_excised']} excised; the diagnostic point's masked fraction is the least-residual point of the surface, not a selection")
    return frag


BUILDERS = (build,)
