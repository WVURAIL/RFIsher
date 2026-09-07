"""``tab:calibration:eras`` (chapter 8) and its companion evidence ledger
``tab:archive:calibration_eras`` (Appendix~C): the current era of every channel
and its transition evidence, one row per channel in each.

The chapter table prints exactly the columns the chapter's ``\\stubtab`` names
(the current era's start, end and boundary uncertainty; the transition evidence
and its agreement with a station record; the stale-latest flag; the earlier eras;
the valid-frame count; the calendar coverage) beside the channel. It is one
``tabular`` -- no panel split was needed -- and its natural width fits a sideways
page with room to spare (700~pt against the 650.4~pt of ``\\textheight``, a scale
of 0.93). The per-channel *evidence* the builder carries beyond the stub -- the
spectral state, the located-month count, the peak drift and range, and the
unconfirmed-instrument flag -- goes to the companion ``calibration_eras_ledger``
fragment (411~pt: it fits a portrait page), beside the channel's plate in
Appendix~\\ref{app:archive-diagnostics}, rather than widening the chapter table
to 1022~pt.

Both fragments read the channel record's ``era`` section and the run's
``tables/eras.csv`` (with ``channels/chNN/eras.json`` as the fallback), and both
are joined on the channel number.

Chapter columns (the ledger key each cell reads; ``era.*`` is the channel
record's ``era`` section):

``Ch.``
    the channel number.
``Start``, ``End``
    ``era.current_first_month`` and ``era.current_last_month`` (UTC months).
``$\\pm$ mo``
    ``era.current_boundary_uncertainty_months``: calendar months strictly
    between the last month of the previous era and the first of the current
    one. Undefined for an ``archive start`` era (no transition defines the
    start): the dash.
``Evidence``
    ``era.current_evidence``, the kinds of boundary that opened the era
    (``archive start``, ``transmitter sign-on`` / ``sign-off``, ``station
    change``, ``instrument change``, ``spectral-state transition``; ``+``
    joined when kinds coincide).
``Record``
    the current era's ``record_agreement`` from ``eras.csv`` (``confirmed
    YYYY-MM`` when a station record dates the transition and agrees with its
    direction; ``disagrees YYYY-MM (kind)`` when the record's direction
    differs), followed by ``unmatched YYYY-MM`` for every
    ``era.unmatched_station_records`` month no boundary absorbed. The dash
    means no station record exists for the boundary; instrument records enter
    the evidence column directly.
``Stale (lag)``
    ``era.stale_latest`` with ``era.stale_lag_months``: ``yes (n)`` when the
    era ends more than the grace before the campaign's last populated month,
    ``no`` otherwise (``no (n)`` when the lag is nonzero but within grace).
``Earlier eras``
    the eras before the current one from ``eras.csv``, oldest first, as
    ``first..last state`` separated by semicolons; the dash when the current
    era is the only one.
``Frames``
    ``era.current_frames``, the valid frames whose UTC month lies in the era.
``Coverage``
    ``populated_months/months_spanned`` of the current era's ``eras.csv`` row
    (its ``coverage`` is the ratio).

Companion ledger columns (``calibration_eras_ledger``, one row per channel):

``Ch.``
    the channel number, the join back to the chapter table.
``State``
    ``era.current_state`` as ``high`` / ``low`` / ``ambiguous`` (``proxy-high``,
    ``proxy-low``, ``ambiguous-only``); ``(no off)`` follows when ``era.fallback``
    carries ``no_off_state`` -- the channel has no proxy-low month and its era
    is bounded only by station and instrument changes.
``Peak mo.``
    ``peak_months`` of the current era's ``eras.csv`` row: the era's months
    whose fine peak was located, the sample the drift and range are read from.
``Drift (bins/mo)``
    ``era.current_peak_drift_bins_per_month``: the least-squares slope of the
    located monthly peak position (the era's proxy-high months whose peak was
    located) in fine bins per month, signed. Undefined with fewer than three
    located months -- on this run every proxy-low era, and a proxy-high era with one or
    two located months -- and printed as the dash.
``Range (bins)``
    ``era.current_peak_range_bins``: max minus min of the located monthly
    peak position; the dash without a located month (a range beside a dashed
    drift is an era with one or two located months). Marked ``$^\\dagger$``
    where the range exceeds the designated half-width
    (``anchors.DESIGNATED_HALF_WIDTH``, 2 bins): the peak wandered beyond the
    designated set inside an era the station-change rule (``station_shift_bins``
    against the running median) did not split.
``Instr.\\ (last mo.)``
    ``era.unconfirmed_instrument_change_last_month``: ``unconfirmed`` when an
    instrument map entered in the channel's last populated month (the
    campaign's, on a channel that is not stale), where the
    persistence rule (``persistence_months``) cannot confirm it and the era is
    left open; ``none`` otherwise.

Numbers (unchanged keys; only the fragment that carries them moved with their
columns): per channel ``ch08.eras.<column>.chNN`` for ``n_eras``,
``current_first_month``, ``current_last_month``,
``current_boundary_uncertainty_months``, ``current_evidence``,
``record_agreement``, ``unmatched_station_records``, ``stale_latest``,
``stale_lag_months``, ``earlier_eras``, ``current_frames``, ``coverage``
(the ratio, rendered ``m/n``), ``coverage_populated_months`` and
``coverage_months_spanned`` from the chapter table, and ``current_state``,
``peak_months``, ``current_peak_drift_bins_per_month``,
``current_peak_range_bins``, ``peak_range_exceeds_half_width`` (``yes`` /
``no``, the mark) and ``unconfirmed_instrument_change_last_month`` (``yes`` /
``no``) from the ledger; band-level ``ch08.eras.n_channels``,
``n_eras_total``, ``n_channels_multi_era``, ``n_channels_record_confirmed``,
``n_channels_stale`` and ``campaign_last_month`` from the chapter table, and
``n_channels_no_off_state``, ``n_channels_drift_measured``,
``n_channels_peak_range_exceeds_half_width``,
``n_channels_unconfirmed_instrument_change`` and ``designated_half_width``
from the ledger. Every key each fragment emits is emitted once, across the two
documents. Text cells that print the dash emit no number.
"""
from __future__ import annotations

import csv
import json
import math
import re
from pathlib import Path
from typing import Mapping

from ..anchors import DESIGNATED_HALF_WIDTH
from .core import DASH, Channel, Fragment, Run, booktabs, fmt, fmt_int, fmt_month, tex

NAME = "calibration_eras"
LABEL = "tab:calibration:eras"
LEDGER_NAME = "calibration_eras_ledger"          # the companion evidence ledger, Appendix C
LEDGER_LABEL = "tab:archive:calibration_eras"
KEY = "ch08.eras"
EARLIER_WIDTH = "4.4cm"          # the wrapped earlier-eras column (two eras per line at \\footnotesize)
RANGE_MARK = r"^{\dagger}"       # inside the range cell's math mode: the range exceeds the designated half-width

_STATES = {"proxy-high": "high", "proxy-low": "low", "ambiguous-only": "ambiguous"}
_CONFIRMED = re.compile(r"^confirmed by record (\d{4}-\d{2})$")
_DISAGREES = re.compile(r"^record (\d{4}-\d{2}) says ([\w-]+); direction disagrees$")


# ------------------------------------------------------------------ eras.csv
def _as_int(value, default=None):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _as_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _as_bool(value) -> bool:
    return value is True or str(value).strip().lower() == "true"


def _normalize(row: Mapping, *, current_index: int | None = None) -> dict:
    era = _as_int(row.get("era"))
    return {"era": era, "first_month": str(row.get("first_month") or ""), "last_month": str(row.get("last_month") or ""),
            "state": str(row.get("state") or ""), "evidence": str(row.get("evidence") or ""),
            "record_agreement": str(row.get("record_agreement") or ""),
            "populated_months": _as_int(row.get("populated_months")), "months_spanned": _as_int(row.get("months_spanned")),
            "coverage": _as_float(row.get("coverage")), "peak_months": _as_int(row.get("peak_months")),
            "is_current": _as_bool(row.get("is_current")) if current_index is None else era == current_index}


def load_era_rows(run: Run) -> tuple[dict[int, list[dict]], list[Path]]:
    """Every channel's era rows (``tables/eras.csv``, else ``channels/chNN/eras.json``) and the files read."""
    rows: dict[int, list[dict]] = {}
    inputs: list[Path] = []
    flat = run.results_dir / "tables" / "eras.csv"
    if flat.is_file():
        inputs.append(flat)
        with flat.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                ch = _as_int(row.get("channel"))
                if ch is not None:
                    rows.setdefault(ch, []).append(_normalize(row))
    for c in run.channels:
        if c.channel in rows:
            continue
        per_channel = run.results_dir / "channels" / f"ch{c.channel:02d}" / "eras.json"
        if not per_channel.is_file():
            continue
        inputs.append(per_channel)
        d = json.loads(per_channel.read_text(encoding="utf-8"))
        current = _as_int(d.get("current_era"))
        rows[c.channel] = [_normalize(e, current_index=current) for e in d.get("eras", ())]
    for ch in rows:
        rows[ch].sort(key=lambda r: (r["era"] is None, r["era"]))
    return rows, inputs


# ------------------------------------------------------------------ cells
def _state(era: Mapping) -> tuple[str, str]:
    """(printed state, the number's text) or two dashes."""
    raw = str(era.get("current_state") or "")
    if not raw:
        return DASH, ""
    short = _STATES.get(raw, raw)
    if "no_off_state" in str(era.get("fallback") or "").split(";"):
        return f"{short} (no off)", short
    return short, short


def _record(agreement: str, unmatched: str) -> tuple[str, list[str]]:
    """The record cell and its renderings; ('--', []) without any record."""
    parts, renderings = [], []
    if agreement:
        m = _CONFIRMED.match(agreement)
        d = _DISAGREES.match(agreement)
        if m:
            parts.append(f"confirmed {m.group(1)}")
        elif d:
            parts.append(f"disagrees {d.group(1)} ({d.group(2)})")
        else:
            parts.append(agreement)
        renderings += [agreement, parts[-1]]
    months = [u for u in unmatched.split(";") if u]
    if months:
        parts.append("unmatched " + ", ".join(months))
        renderings.append(parts[-1])
    if not parts:
        return DASH, []
    return "; ".join(parts), renderings


def _stale(era: Mapping) -> tuple[str, str, int | None]:
    """(cell, 'yes'/'no', lag) from era.stale_latest and era.stale_lag_months."""
    if "stale_latest" not in era:
        return DASH, "", None
    stale = _as_bool(era.get("stale_latest"))
    lag = _as_int(era.get("stale_lag_months"))
    flag = "yes" if stale else "no"
    if lag is not None and (stale or lag > 0):
        return f"{flag} ({lag})", flag, lag
    return flag, flag, lag


def _earlier(rows: list[dict], current: int | None) -> tuple[str, str]:
    """(cell, plain text) listing the eras before the current one."""
    if current is None:
        return DASH, ""
    parts = []
    for r in rows:
        if r["era"] is None or r["era"] >= current:
            continue
        state = _STATES.get(r["state"], r["state"] or "?")
        parts.append(f"{fmt_month(r['first_month'])}..{fmt_month(r['last_month'])} {state}")
    if not parts:
        return DASH, ""
    text = "; ".join(parts)
    return f"\\parbox[t]{{{EARLIER_WIDTH}}}{{\\raggedright {tex(text)}}}", text


def _coverage(current: Mapping | None) -> tuple[str, int | None, int | None, float]:
    if current is None:
        return DASH, None, None, float("nan")
    m, n = current.get("populated_months"), current.get("months_spanned")
    if m is None or n is None:
        return DASH, None, None, float("nan")
    return f"{m}/{n}", m, n, current.get("coverage", float("nan"))


def _drift(era: Mapping) -> tuple[str, float | None, str]:
    """(cell, value, printed text) from era.current_peak_drift_bins_per_month; the dash when undefined."""
    x = _as_float(era.get("current_peak_drift_bins_per_month"))
    if not math.isfinite(x):
        return DASH, None, ""
    text = fmt(x, 2)
    if float(text) == 0.0:
        text = "0.00"                      # a slope that rounds to zero carries no sign
    elif x > 0:
        text = "+" + text
    return f"${text}$", x, text


def _range(era: Mapping) -> tuple[str, float | None, str, bool]:
    """(cell, value, printed text, exceeds) from era.current_peak_range_bins; marked when beyond the half-width."""
    x = _as_float(era.get("current_peak_range_bins"))
    if not math.isfinite(x):
        return DASH, None, "", False
    text = fmt_int(x, thousands=False) if float(x).is_integer() else fmt(x, 1)
    exceeds = x > DESIGNATED_HALF_WIDTH
    return f"${text}{RANGE_MARK if exceeds else ''}$", x, text, exceeds


def _instrument(era: Mapping) -> tuple[str, str]:
    """(cell, 'yes'/'no') from era.unconfirmed_instrument_change_last_month; the dash when unrecorded."""
    if "unconfirmed_instrument_change_last_month" not in era:
        return DASH, ""
    if _as_bool(era.get("unconfirmed_instrument_change_last_month")):
        return "unconfirmed", "yes"
    return "none", "no"


def _current_row(c: Channel, rows: list[dict], frag: Fragment, dashed: str) -> dict | None:
    """The eras.csv row of the current era, cross-checked against the ledger; None when absent or inconsistent."""
    era = c.era
    current = [r for r in rows if r["is_current"]]
    index = _as_int(era.get("current_era"))
    if not current and index is not None:
        current = [r for r in rows if r["era"] == index]
    if not current:
        return None
    row = current[0]
    if era.get("current_first_month") and row["first_month"] != era["current_first_month"]:
        frag.notes.append(f"ch{c.channel:02d}: the eras table's current era ({row['first_month']}..{row['last_month']}) "
                          f"disagrees with the ledger ({era['current_first_month']}..{era.get('current_last_month', '')}); "
                          f"{dashed} are dashed")
        return None
    return row


def _context(run: Run, frag: Fragment, dashed: str) -> tuple[list[tuple[Channel, list[dict], dict | None]], list[int]]:
    """Per channel: (record, its era rows, the current era's row); and the channels with no era rows at all.

    Sets ``frag.inputs``; ``dashed`` names the cells a disagreeing eras table costs this fragment.
    """
    era_rows, extra_inputs = load_era_rows(run)
    frag.inputs = run.inputs() + extra_inputs
    context, without_table = [], []
    for c in run.channels:
        table_rows = era_rows.get(c.channel, [])
        current = _current_row(c, table_rows, frag, dashed) if c.era else None
        if not table_rows and c.era:
            without_table.append(c.channel)
        context.append((c, table_rows, current))
    return context, without_table


def _channels(numbers: list[int]) -> str:
    return ", ".join(str(ch) for ch in numbers)


def _missing_note(run: Run, frag: Fragment) -> None:
    missing = [c.channel for c in run.channels if not c.era]
    if missing:
        frag.notes.append("no era section for channels " + _channels(missing) + ": every era cell is dashed")


# ------------------------------------------------------------------ the chapter table
def build(run: Run) -> Fragment:
    """``tab:calibration:eras``: the stub's columns beside the channel, one row per channel."""
    frag = Fragment(NAME, LABEL, "")
    context, without_table = _context(run, frag, "record, earlier eras and coverage")
    header = ["Ch.", "Start", "End", r"$\pm$ mo", "Evidence", "Record", "Stale (lag)", "Earlier eras", "Frames", "Coverage"]
    rows = []
    n_multi = n_confirmed = n_stale = n_eras_total = 0
    campaign_month = str(run.run.get("campaign_last_month") or "")
    for c, table_rows, current in context:
        ch = c.channel
        era = c.era
        row = {"channel": ch}
        n_eras = _as_int(era.get("n_eras"))
        index = _as_int(era.get("current_era"))
        if n_eras is not None:
            n_eras_total += n_eras
            frag.add(f"{KEY}.n_eras.ch{ch}", n_eras, kind="int", row=row, column="n_eras")
            n_multi += n_eras > 1
        if not campaign_month:
            campaign_month = str(era.get("campaign_last_month") or "")

        first, last = era.get("current_first_month") or "", era.get("current_last_month") or ""
        if first:
            frag.add(f"{KEY}.current_first_month.ch{ch}", first, kind="text", renderings=(first,), row=row, column="Start")
        if last:
            frag.add(f"{KEY}.current_last_month.ch{ch}", last, kind="text", renderings=(last,), row=row, column="End")

        evidence = str(era.get("current_evidence") or "")
        uncertainty = _as_int(era.get("current_boundary_uncertainty_months"))
        if evidence == "archive start" or uncertainty is None:
            unc_cell = DASH
        else:
            unc_cell = str(uncertainty)
            frag.add(f"{KEY}.current_boundary_uncertainty_months.ch{ch}", uncertainty, kind="int", row=row, column="pm mo")
        if evidence:
            short = evidence.replace("transmitter ", "")
            frag.add(f"{KEY}.current_evidence.ch{ch}", evidence, kind="text", renderings=tuple(dict.fromkeys((evidence, short))),
                     row=row, column="Evidence")
        evidence_cell = tex(evidence.replace("+", " + ")) if evidence else DASH

        agreement = current["record_agreement"] if current else ""
        unmatched_records = str(era.get("unmatched_station_records") or "")
        record_cell, renderings = _record(agreement, unmatched_records)
        if agreement:
            frag.add(f"{KEY}.record_agreement.ch{ch}", agreement, kind="text", renderings=tuple(renderings[:2]), row=row, column="Record")
            n_confirmed += bool(_CONFIRMED.match(agreement))
        if unmatched_records:
            frag.add(f"{KEY}.unmatched_station_records.ch{ch}", unmatched_records, kind="text",
                     renderings=(renderings[-1], unmatched_records), row=row, column="Record")

        stale_cell, stale_text, lag = _stale(era)
        if stale_text:
            frag.add(f"{KEY}.stale_latest.ch{ch}", stale_text, kind="text", renderings=(stale_text, stale_cell), row=row, column="Stale (lag)")
            n_stale += stale_text == "yes"
        if lag is not None:
            frag.add(f"{KEY}.stale_lag_months.ch{ch}", lag, kind="int", row=row, column="Stale (lag)")

        earlier_cell, earlier_text = _earlier(table_rows, index) if current else (DASH, "")
        if earlier_text:
            frag.add(f"{KEY}.earlier_eras.ch{ch}", earlier_text, kind="text", renderings=(earlier_text,), row=row, column="Earlier eras")

        frames = _as_int(era.get("current_frames"))
        if frames is not None:
            frag.add(f"{KEY}.current_frames.ch{ch}", frames, kind="int", row=row, column="Frames")
        frames_cell = f"${fmt_int(frames)}$" if frames is not None else DASH

        cov_cell, m, n, ratio = _coverage(current)
        if m is not None:
            frag.add(f"{KEY}.coverage.ch{ch}", ratio, precision=3, renderings=(cov_cell,), row=row, column="Coverage")
            frag.add(f"{KEY}.coverage_populated_months.ch{ch}", m, kind="int", row=row, column="Coverage")
            frag.add(f"{KEY}.coverage_months_spanned.ch{ch}", n, kind="int", row=row, column="Coverage")

        rows.append([str(ch), fmt_month(first), fmt_month(last), unc_cell, evidence_cell, tex(record_cell), tex(stale_cell),
                     earlier_cell, frames_cell, cov_cell])

    frag.tex = booktabs(header, rows, "rllrllllrr")
    frag.add(f"{KEY}.n_channels", len(run.channels), kind="int", column="rows")
    frag.add(f"{KEY}.n_eras_total", n_eras_total, kind="int", column="n_eras")
    frag.add(f"{KEY}.n_channels_multi_era", n_multi, kind="int", column="n_eras")
    frag.add(f"{KEY}.n_channels_record_confirmed", n_confirmed, kind="int", column="Record")
    frag.add(f"{KEY}.n_channels_stale", n_stale, kind="int", column="Stale (lag)")
    if campaign_month:
        frag.add(f"{KEY}.campaign_last_month", campaign_month, kind="text", renderings=(campaign_month,), column="Stale (lag)")

    frag.notes.append("the +- column is dashed for 'archive start' eras: no transition defines the start, so the boundary "
                      "uncertainty is undefined (the ledger records 0)")
    frag.notes.append("the record column is dashed where no station record exists for the boundary; instrument records enter "
                      "the evidence column as 'instrument change'")
    frag.notes.append("earlier eras carry span and state only; their evidence and record agreement stay in tables/eras.csv")
    frag.notes.append(f"the columns beyond the stub -- the era's spectral state, its located-month count, the peak drift and "
                      f"range and the unconfirmed-instrument flag -- print in the companion evidence ledger "
                      f"{LEDGER_NAME}.tex ({LEDGER_LABEL}, appendix C), one row per channel joined on the channel number; "
                      "printing them here would take the table to 1022 pt")
    frag.notes.append("one tabular, no panel split: 700 pt natural width fits a sideways page (650.4 pt) at a scale of 0.93; "
                      "the companion ledger is 411 pt and fits a portrait page")
    if without_table:
        frag.notes.append("no eras table (tables/eras.csv or channels/chNN/eras.json) for channels "
                          + _channels(without_table) + ": record, earlier eras and coverage are dashed")
    _missing_note(run, frag)
    return frag


# ------------------------------------------------------------------ the companion ledger
def build_ledger(run: Run) -> Fragment:
    """``tab:archive:calibration_eras``: the per-channel era evidence behind the chapter table (appendix C)."""
    frag = Fragment(LEDGER_NAME, LEDGER_LABEL, "")
    context, without_table = _context(run, frag, "the located-month count")
    header = ["Ch.", "State", "Peak mo.", "Drift (bins/mo)", "Range (bins)", r"Instr.\ (last mo.)"]
    rows = []
    n_no_off = n_drift = 0
    drift_dashed, range_exceeds, unconfirmed = [], [], []
    era_config = run.run.get("era_config") if isinstance(run.run.get("era_config"), Mapping) else {}
    for c, _table_rows, current in context:
        ch = c.channel
        era = c.era
        row = {"channel": ch}

        state_cell, state_text = _state(era)
        if state_text:
            frag.add(f"{KEY}.current_state.ch{ch}", state_text, kind="text", renderings=(state_text, str(era["current_state"])),
                     row=row, column="State")
            n_no_off += state_cell.endswith("(no off)")

        peak_cell = DASH
        if current and current.get("peak_months") is not None:
            peak_cell = f"${fmt_int(current['peak_months'])}$"
            frag.add(f"{KEY}.peak_months.ch{ch}", current["peak_months"], kind="int", row=row, column="Peak mo.")

        drift_cell, drift, drift_text = _drift(era)
        if drift is not None:
            frag.add(f"{KEY}.current_peak_drift_bins_per_month.ch{ch}", drift, precision=2, renderings=(drift_text,),
                     row=row, column="Drift (bins/mo)")
            n_drift += 1
        elif era:
            drift_dashed.append(ch)

        range_cell, peak_range, range_text, exceeds = _range(era)
        if peak_range is not None:
            frag.add(f"{KEY}.current_peak_range_bins.ch{ch}", peak_range, precision=0 if float(peak_range).is_integer() else 1,
                     renderings=(range_text,), row=row, column="Range (bins)")
            frag.add(f"{KEY}.peak_range_exceeds_half_width.ch{ch}", "yes" if exceeds else "no", kind="text",
                     renderings=("yes",) if exceeds else ("no",), row=row, column="Range (bins)")
            if exceeds:
                range_exceeds.append(ch)

        instr_cell, instr_text = _instrument(era)
        if instr_text:
            frag.add(f"{KEY}.unconfirmed_instrument_change_last_month.ch{ch}", instr_text, kind="text",
                     renderings=(instr_text, instr_cell), row=row, column="Instr. (last mo.)")
            if instr_text == "yes":
                unconfirmed.append(ch)

        rows.append([str(ch), tex(state_cell), peak_cell, drift_cell, range_cell, instr_cell])

    frag.tex = booktabs(header, rows, "rlrrrl")
    frag.add(f"{KEY}.n_channels_no_off_state", n_no_off, kind="int", column="State")
    frag.add(f"{KEY}.n_channels_drift_measured", n_drift, kind="int", column="Drift (bins/mo)")
    frag.add(f"{KEY}.n_channels_peak_range_exceeds_half_width", len(range_exceeds), kind="int", column="Range (bins)")
    frag.add(f"{KEY}.n_channels_unconfirmed_instrument_change", len(unconfirmed), kind="int", column="Instr. (last mo.)")
    frag.add(f"{KEY}.designated_half_width", DESIGNATED_HALF_WIDTH, kind="int", column="Range (bins)")

    shift = era_config.get("station_shift_bins", 3)
    persistence = era_config.get("persistence_months", 2)
    frag.notes.append(f"the term-by-term era evidence behind {LABEL}, one row per channel joined on the channel number: "
                      "the columns the chapter stub does not name, beside the channel's plate")
    frag.notes.append("peak mo. is the current era's located-month count from tables/eras.csv (the sample the drift and range "
                      "are read from); it is dashed where no eras-table row backs the era section")
    frag.notes.append("drift and range: the least-squares slope (bins/month) and max - min of the located monthly peak position "
                      "over the current era's proxy-high months; the drift is dashed with fewer than three located months "
                      "(on this run every proxy-low era; a range beside a dashed drift is an era with one or two located months)"
                      + (f": channels {_channels(drift_dashed)}" if drift_dashed else ""))
    frag.notes.append(f"range marked dagger where it exceeds the designated half-width {DESIGNATED_HALF_WIDTH} bins"
                      + (f" (channels {_channels(range_exceeds)})" if range_exceeds else " (no channel)")
                      + f": the peak wandered beyond the designated set inside an era the station-change rule ({shift:g} bins "
                      "against the running median) did not split")
    frag.notes.append("instr. (last mo.) reads 'unconfirmed' where an instrument map entered in the campaign's last populated "
                      f"month, where the persistence rule ({persistence} months) cannot confirm it and the era is left open"
                      + (f": channels {_channels(unconfirmed)}" if unconfirmed else " (no channel)"))
    if without_table:
        frag.notes.append("no eras table (tables/eras.csv or channels/chNN/eras.json) for channels "
                          + _channels(without_table) + ": the located-month count is dashed")
    _missing_note(run, frag)
    return frag


BUILDERS = (build, build_ledger)
