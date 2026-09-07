r"""Chapter 11 synthesis and appendix C denominators: three fragments from the ledger.

No channel of the v5 run has a selected operating point (``selection.status``
is ``no feasible point`` or ``refused``, ``claim_status`` ``diagnostic``
where a surface exists), so wherever a stub asks for "the selected
``(rho*, eta*)``" these fragments print the *diagnostic point*: the
least-residual point of the evaluated calibration surface
(``selection.diagnostic_*``), replayed on the evaluation block, and say so in
the header, the cell (a dagger) or a note. A selected point is used when a
channel carries one (``selection.rho`` not null), so the same code renders a
run with feasible selections.

``build`` -> ``conclusions_matrix`` (tab:conclusions:matrix), counts only.
Columns ``disposition`` / ``channels`` / ``value``; rows in four groups:

* *Screening class*: one row per class of ``screening.screening_class``
  (recovery candidate, measurement-bound on floor, measurement-bound on
  tau_c, occupancy-wall excision candidate, off-era; an ``unclassified`` row
  appears only when a channel carries no class), counting the channels.
* *Handover policy*, derived from the class by the two chapter 9 rules:
  ``kept-and-masked`` (every class but the excision candidates; the allocation
  keeps its channels at the operating point), with the off-era channels of
  that count on their own row (``of which evaluated on an off era``: their
  point is a false-alarm basis, not a verdict); ``excised interior`` and
  ``monitoring tap`` (the occupancy-wall excision candidates: the interior is
  discarded and the pilot-bin channel, which is the product channel, is kept
  as a tap); ``no policy`` only for a channel without a class.
* *Selection status*: ``selection.status`` counts (``feasible``, ``no
  feasible point``, ``refused``; ``no selection record`` when a channel has
  no selection section) and the channels whose ``claim_status`` is
  ``diagnostic``.
* *Band level at the operating points* (the header names the basis): the
  kept channels (both kept-and-masked rows) whose point has a masked fraction
  ``f``; the current-era frames on them (``era.current_frames``); the
  frame-weighted masked fraction ``sum(w f) / sum(w)`` with ``w =
  era.current_frames``; and the integration-time cost factor ``1 / (1 - f)``
  of that band-level fraction (total era frames over kept frames on the kept
  channels). ``f`` is ``selection.masked_fraction_calibration`` at the
  selected point where one exists and otherwise
  ``selection.diagnostic_masked_fraction``.

``build_atlas_counts`` -> ``archive_atlas_counts`` (tab:archive:atlas-counts),
one row per channel and one column per name in the appendix C stub, and no
others: ``ch``; ``freq_id``; ``valid`` (``product.n_valid``, the valid frames
in the archive); ``excluded (reason)`` (``product.health_excluded``, the frames
the input-health gate removed, with the gate's reason counts
``product.health_reasons`` abbreviated by :data:`REASON_LABELS`; a list of more
than one reason is set one reason to a line, so the longest list and not the
column sets the width); ``current era``
(``era.current_first_month``--``era.current_last_month``); ``era frames``
(``era.current_frames``); ``kept at point`` (the frames the point keeps,
``round((1 - f) x selection.calibration_frames)`` on the calibration block plus
``selection.kept_evaluation`` on the evaluation replay: their sum is the
plate's denominator); and ``plate digest`` (the dash until the plates are
rendered). A dagger on the kept cell marks the diagnostic point and a double
dagger a cell that is the calibration block alone (the point was never
replayed); the cell is the dash on a channel without a point
(``selection.status`` ``refused``, or no selection record).

Three columns of the first draft are no longer printed, because the stub does
not name them: ``frames`` (``product.n_frames``, the archive count before the
health gate; the stub's denominator is the valid count) and the two blocks of
the kept count, now one summed column. Every number they carried is still
emitted under its own key (``appC.atlas_counts.n_frames``,
``kept_calibration``, ``kept_evaluation``, ``kept_total``) with the column
:data:`NOT_PRINTED`, and the notes say where each went. The trim takes the
fragment from 715.4pt to 435.4pt, the width of the boxed ``tabular`` at 11pt
on the run of 2026-09-07, inside the 469.8pt text block: the appendix sets it
upright and needs neither a sideways page nor a ``\resizebox``. The three
columns are per-channel evidence, but the appendix already prints the plate
beside the row, so they go to the numbers rather than to a companion
``archive_atlas_counts_ledger`` fragment; no companion and no stacked panels
are needed, and :data:`BUILDERS` keeps its three builders.

``build_headline`` -> ``headline``: numbers only (the ``.tex`` is a comment),
every value emitted under both ``ch11.headline.<name>`` and
``front.headline.<name>``: the channel count, the counts by class with the
channel lists, the measurement-bound total, the off-era list; the selection
statuses (``selection.status``, ``claim_status``); floors by
``null.floor_evidence`` (measured / stated / refused, with the channel lists,
and the stated floors split by ``null.floor_basis``); correlation times by
``chain.tau_quality`` (measured / bounded_above / refused / unmeasured, with
the measured and bounded lists); ``K*`` at the run's ``provisional.e_min``
from ``tables/kstar.csv`` (``k_star``, ``failing_k``, ``binding_channel``,
``binding_e``, ``sentinels``); the channels whose least residual is within
ten times tolerance (``selection.min_R <= 10``); the smallest
``selection.min_R`` and its channel; the smallest coarse-rule frontier
``selection.coarse_min_R`` and its channel (with its masked fraction
``selection.coarse_min_R_masked_fraction``) and the number of channels with a
frontier; the null bulk (channels whose ``null.coarse_centre_db`` is within
0.1 dB of mu_0, and the ranges of ``null.coarse_core_width_factor`` and
``null.fine_core_width_factor``); and the band level of the matrix (kept
channels, frames, masked fraction, time cost, basis).

Every printed number is added to the fragment (``ch11.matrix.<name>``,
``appC.atlas_counts.<column>.chNN``, ``ch11.headline.<name>`` /
``front.headline.<name>``); an absent or undefined value prints as the dash
and the fragment's notes say why.
"""
from __future__ import annotations

import csv
import math
import re
from typing import Mapping, Sequence

from .. import screening as sc
from .core import DASH, Channel, Fragment, Run, booktabs, fmt, fmt_int, fmt_month, tex

CLASS_SLUGS: Mapping[str, str] = {
    sc.RECOVERY: "recovery_candidate", sc.BOUND_FLOOR: "measurement_bound_floor", sc.BOUND_TAU: "measurement_bound_tau_c",
    sc.WALL: "occupancy_wall_excision_candidate", sc.OFF_ERA: "off_era",
}
CLASS_TEX: Mapping[str, str] = {
    sc.RECOVERY: "recovery candidate", sc.BOUND_FLOOR: "measurement-bound on floor", sc.BOUND_TAU: r"measurement-bound on $\tau_c$",
    sc.WALL: "occupancy-wall excision candidate", sc.OFF_ERA: "off-era",
}
UNCLASSIFIED = "unclassified"

POLICY_KEPT = "kept-and-masked"
POLICY_EXCISED = "excised interior"
POLICY_NONE = "no policy (unscreened)"
POLICY_SLUGS: Mapping[str, str] = {POLICY_KEPT: "kept_and_masked", POLICY_EXCISED: "excised_interior", POLICY_NONE: "none"}
KEPT_OFF_ERA_SLUG = "kept_and_masked_off_era"        # the off-era share of the kept-and-masked count
MONITORING_TAP_SLUG = "monitoring_tap"                # one pilot-bin channel per excised allocation

SELECTION_SLUGS: Mapping[str, str] = {"feasible": "feasible", "no feasible point": "no_feasible_point", "refused": "refused"}
SELECTION_NONE = "no selection record"

BASIS_SELECTED = "selected points"
BASIS_DIAGNOSTIC = "diagnostic points: least residual on the calibration surface, no selection"
BASIS_MIXED = "selected points where feasible, else diagnostic points"

REASON_LABELS: Mapping[str, str] = {
    "baseband_power_at_negative_full_scale_ceiling": "rail",
    "detector_invalid": "invalid",
    "detector_powers_all_zero": "all-zero",
}

MARK_DIAGNOSTIC = r"\dagger"    # the point is the diagnostic least-residual point of the surface, not a selection
MARK_NO_REPLAY = r"\ddagger"    # the kept count is the calibration block alone: the point was never replayed
DAGGER = f"^{{{MARK_DIAGNOSTIC}}}"    # inside math mode: the diagnostic point, not a selection
NOT_PRINTED = "(numbers only)"        # the number is emitted; the stub names no column for it
STACK_OPEN = r"\begin{tabular}[t]{@{}l@{}}"     # a cell on more than one line, its first line on the row's baseline
STACK_CLOSE = r"\end{tabular}"
WITHIN_FACTOR = 10.0          # 'least residual within 10x of tolerance': min_R <= WITHIN_FACTOR
CENTRE_TOLERANCE_DB = 0.1     # 'coarse centre at mu_0': |null.coarse_centre_db| <= CENTRE_TOLERANCE_DB
DEFAULT_E_MIN = 0.9
FLOOR_EVIDENCE = ("measured", "stated", "refused")
TAU_QUALITIES = ("measured", "bounded_above", "refused", "unmeasured")


# ------------------------------------------------------------------ helpers
def _num(value) -> float | None:
    """A finite float, or None for absent, NaN, infinite or non-numeric values."""
    if value is None or isinstance(value, bool):
        return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _math(text: str) -> str:
    return text if text == DASH else f"${text}$"


def _sig(value, digits: int = 3) -> tuple[str, int | None]:
    """``fmt(value, digits, sig=True)`` and the number of decimals it printed."""
    x = _num(value)
    if x is None:
        return DASH, None
    decimals = 0 if x == 0.0 else max(digits - 1 - int(math.floor(math.log10(abs(x)))), 0)
    return fmt(x, digits, sig=True), decimals


def _channel_list(channels: Sequence[int]) -> str:
    return ", ".join(str(c) for c in channels)


def _channel_phrase(channels: Sequence[int]) -> str:
    """``channel 17`` / ``channels 19, 21``: a channel list with the noun a note reads with."""
    return f"channel{'' if len(channels) == 1 else 's'} {_channel_list(channels)}"


def _slug(text: str) -> str:
    """A key segment from free text: lower case, runs of non-alphanumerics folded to one underscore."""
    return re.sub(r"[^a-z0-9]+", "_", str(text).strip().lower()).strip("_") or "none"


def class_of(ch: Channel) -> str:
    """The channel's screening class, or ``unclassified`` when the ledger carries none."""
    cls = ch.screening.get("screening_class")
    return cls if cls in sc.CLASSES else UNCLASSIFIED


def policy_of(cls: str) -> str:
    """The handover policy the chapter 9 rules derive from a screening class."""
    if cls == sc.WALL:
        return POLICY_EXCISED
    if cls in sc.CLASSES:
        return POLICY_KEPT
    return POLICY_NONE


def selection_status(ch: Channel) -> str:
    """``selection.status`` as recorded, or ``no selection record``."""
    status = ch.selection.get("status") if ch.has("selection") else None
    return str(status) if status else SELECTION_NONE


def operating_point_fraction(ch: Channel) -> tuple[float | None, str]:
    """The masked fraction at the channel's operating point and its basis.

    The selected point's ``masked_fraction_calibration`` when the selection
    carries a point (``rho`` not None); otherwise the diagnostic point's
    ``diagnostic_masked_fraction``; ``(None, '')`` when neither is defined.
    """
    sel = ch.selection
    if sel.get("rho") is not None and _num(sel.get("masked_fraction_calibration")) is not None:
        return _num(sel["masked_fraction_calibration"]), "selected"
    f = _num(sel.get("diagnostic_masked_fraction"))
    return (f, "diagnostic") if f is not None else (None, "")


def kept_at_point(ch: Channel) -> dict:
    """Frames the operating point keeps: ``{'basis', 'calibration', 'evaluation'}`` (None where undefined).

    ``calibration = round((1 - f) x selection.calibration_frames)``;
    ``evaluation = selection.kept_evaluation`` when the point was replayed on
    the evaluation block (``masked_fraction_evaluation`` finite).
    """
    sel = ch.selection
    f, basis = operating_point_fraction(ch)
    frames = _num(sel.get("calibration_frames"))
    calibration = int(round((1.0 - f) * frames)) if f is not None and frames is not None else None
    evaluation = None
    if basis and _num(sel.get("masked_fraction_evaluation")) is not None and _num(sel.get("kept_evaluation")) is not None:
        evaluation = int(round(_num(sel["kept_evaluation"])))
    return {"basis": basis, "calibration": calibration, "evaluation": evaluation}


def reason_parts(reasons) -> list[str]:
    """``name:count;name:count`` -> ``['rail 7', 'invalid 4']`` (plain text, escaped)."""
    parts = []
    for item in str(reasons or "").split(";"):
        item = item.strip()
        if not item:
            continue
        name, _, count = item.rpartition(":")
        if not name:
            name, count = count, ""
        label = REASON_LABELS.get(name, name)
        parts.append(f"{tex(label)} {tex(count)}".strip())
    return parts


def render_reasons(reasons) -> str:
    """``name:count;name:count`` -> ``rail 7, invalid 4``: the one-line rendering the prose may use."""
    return ", ".join(reason_parts(reasons))


def _head(top: str, bottom: str) -> str:
    """A column head on two lines, so a wordy head does not set the column's width."""
    return r"\shortstack{%s\\%s}" % (top, bottom)


def _stacked(lines: Sequence[str]) -> str:
    """One cell on several lines, the first on the row's baseline and the rest hanging below it."""
    return lines[0] if len(lines) == 1 else STACK_OPEN + r"\\".join(lines) + STACK_CLOSE


def excluded_cell(excluded, reasons) -> str:
    """``7 (rail 7)``; a list of more than one reason is set one reason to a line, the dash for no count."""
    count = _num(excluded)
    if count is None:
        return DASH
    text = _math(fmt_int(count))
    parts = reason_parts(reasons)
    if not parts:
        return text
    if len(parts) == 1:
        return f"{text} ({parts[0]})"
    return _stacked([f"{text} ({parts[0]},"] + [f"{p}," for p in parts[1:-1]] + [f"{parts[-1]})"])


def kept_cell(value, marks: Sequence[str]) -> str:
    """A kept count with its marks in one superscript, or the dash where the count is undefined."""
    if value is None:
        return DASH
    return f"${fmt_int(value)}" + ("^{" + "".join(marks) + "}$" if marks else "$")


def band_level(run: Run) -> dict:
    """The band-level masked fraction and time-cost factor over the kept channels.

    ``masked_fraction = sum(w f) / sum(w)`` and ``time_cost = sum(w) / sum(w (1 - f))``
    with ``w = era.current_frames``; ``time_cost`` is inf when the points keep no frame.
    """
    used, skipped, bases = [], [], set()
    sum_wf = sum_w = 0.0
    for ch in run.channels:
        if policy_of(class_of(ch)) != POLICY_KEPT:
            continue
        f, basis = operating_point_fraction(ch)
        w = _num(ch.era.get("current_frames"))
        if f is None or w is None or w <= 0:
            skipped.append((ch.channel, "no masked fraction at an operating point" if f is None else "no current-era frame count"))
            continue
        used.append(ch.channel)
        bases.add(basis)
        sum_wf += w * f
        sum_w += w
    if bases == {"selected"}:
        basis = BASIS_SELECTED
    elif bases == {"diagnostic"}:
        basis = BASIS_DIAGNOSTIC
    elif bases:
        basis = BASIS_MIXED
    else:
        basis = ""
    masked = sum_wf / sum_w if sum_w > 0 else math.nan
    kept = sum_w - sum_wf
    return {"channels": used, "skipped": skipped, "frames": int(round(sum_w)), "basis": basis, "masked_fraction": masked,
            "time_cost": math.nan if sum_w <= 0 else (sum_w / kept if kept > 0 else math.inf)}


def class_counts(run: Run) -> dict[str, list[int]]:
    counts: dict[str, list[int]] = {cls: [] for cls in sc.CLASSES}
    for ch in run.channels:
        counts.setdefault(class_of(ch), []).append(ch.channel)
    return counts


def selection_counts(run: Run) -> dict[str, list[int]]:
    counts: dict[str, list[int]] = {status: [] for status in SELECTION_SLUGS}
    for ch in run.channels:
        counts.setdefault(selection_status(ch), []).append(ch.channel)
    return counts


def read_kstar(run: Run) -> tuple[dict | None, str]:
    """The ``tables/kstar.csv`` row at the run's ``e_min``; ``(None, why)`` when absent."""
    path = run.results_dir / "tables" / "kstar.csv"
    provisional = run.run.get("provisional")
    e_min = _num(provisional.get("e_min")) if isinstance(provisional, Mapping) else None
    e_min = DEFAULT_E_MIN if e_min is None else e_min
    if not path.is_file():
        return None, f"tables/kstar.csv absent: no K* at E_min {e_min:g}"
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if _num(row.get("e_min")) is not None and abs(_num(row["e_min"]) - e_min) < 1e-9:
                return {"e_min": e_min, "k_star": _num(row.get("k_star")), "failing_k": _num(row.get("failing_k")),
                        "binding_channel": _num(row.get("binding_channel")), "binding_e": _num(row.get("binding_e")),
                        "sentinels": str(row.get("sentinels", "") or "")}, ""
    return None, f"tables/kstar.csv has no row at E_min {e_min:g}"


def _band_notes(band: dict) -> list[str]:
    notes = []
    if band["channels"]:
        notes.append(f"band level over kept channels {_channel_list(band['channels'])} at the {band['basis']}")
        if not math.isfinite(band["time_cost"]):
            notes.append("integration-time cost undefined: the operating points keep no frame on the kept channels (f = 1)")
        if band["basis"] == BASIS_DIAGNOSTIC:
            notes.append("no channel has a feasible selected point: the band level uses the diagnostic point of each evaluated "
                         "calibration surface (selection.diagnostic_masked_fraction, the least-residual point, claim_status diagnostic)")
        elif band["basis"] == BASIS_MIXED:
            notes.append("mixed basis: selected points where feasible, diagnostic points elsewhere")
    else:
        notes.append("band level undefined: no kept channel has a masked fraction at an operating point")
    for channel, why in band["skipped"]:
        notes.append(f"ch{channel} left out of the band level: {why}")
    return notes


# ------------------------------------------------------------------ (a) the matrix
def build(run: Run) -> Fragment:
    """tab:conclusions:matrix: channels by screening class, handover policy and selection status, and the band-level cost."""
    frag = Fragment("conclusions_matrix", "tab:conclusions:matrix", "")
    counts = class_counts(run)
    frag.add("ch11.matrix.channels", len(run.channels), kind="int", row={"group": "screening class"}, column="channels")

    def count_row(label: str, key: str, channels: Sequence[int], group: str, tag: str) -> None:
        rows.append([r"\quad " + label, str(len(channels)), ""])
        frag.add(key, len(channels), kind="int", row={"group": group, "label": tag}, column="channels")

    rows: list[list[str]] = [[r"\emph{Screening class}", "", ""]]
    for cls in sc.CLASSES:
        count_row(CLASS_TEX[cls], f"ch11.matrix.class.{CLASS_SLUGS[cls]}", counts[cls], "screening class", cls)
    if counts.get(UNCLASSIFIED):
        count_row("unclassified (no screening record)", "ch11.matrix.class.unclassified", counts[UNCLASSIFIED], "screening class", UNCLASSIFIED)
        frag.notes.append(f"channels without a screening class: {_channel_list(counts[UNCLASSIFIED])}")

    policies: dict[str, list[int]] = {p: [] for p in POLICY_SLUGS}
    for cls, chans in counts.items():
        policies[policy_of(cls)].extend(chans)
    rows.append([r"\emph{Handover policy}", "", ""])
    count_row("kept-and-masked, at the operating point", f"ch11.matrix.policy.{POLICY_SLUGS[POLICY_KEPT]}",
              policies[POLICY_KEPT], "handover policy", POLICY_KEPT)
    count_row("of which evaluated on an off era", f"ch11.matrix.policy.{KEPT_OFF_ERA_SLUG}", counts[sc.OFF_ERA],
              "handover policy", "kept-and-masked, off era")
    count_row("excised interior", f"ch11.matrix.policy.{POLICY_SLUGS[POLICY_EXCISED]}", policies[POLICY_EXCISED],
              "handover policy", POLICY_EXCISED)
    count_row("monitoring tap (pilot-bin channel of an excised allocation)", f"ch11.matrix.policy.{MONITORING_TAP_SLUG}",
              policies[POLICY_EXCISED], "handover policy", "monitoring tap")
    if policies[POLICY_NONE]:
        count_row(POLICY_NONE, f"ch11.matrix.policy.{POLICY_SLUGS[POLICY_NONE]}", policies[POLICY_NONE], "handover policy", POLICY_NONE)

    statuses = selection_counts(run)
    rows.append([r"\emph{Selection status}", "", ""])
    for status, slug in SELECTION_SLUGS.items():
        label = {"feasible": "feasible (selected point)", "no feasible point": "no feasible point (diagnostic point replayed)",
                 "refused": "refused (no evaluated surface)"}[status]
        count_row(label, f"ch11.matrix.selection.{slug}", statuses[status], "selection status", status)
    for status in statuses:
        if status not in SELECTION_SLUGS:
            count_row(tex(status), f"ch11.matrix.selection.{_slug(status)}", statuses[status], "selection status", status)
    diagnostic = [c.channel for c in run.channels if c.selection.get("claim_status") == "diagnostic"]
    count_row("claim status diagnostic", "ch11.matrix.selection.diagnostic", diagnostic, "selection status", "diagnostic")

    band = band_level(run)
    basis = band["basis"]
    header = r"\emph{Band level at the operating points}" + (f" ({tex(basis)})" if basis else "")
    rows.append([header, "", ""])
    rows.append([r"\quad kept channels entering the average", str(len(band["channels"])), ""])
    frag.add("ch11.matrix.kept_channels", len(band["channels"]), kind="int", row={"group": "band level"}, column="channels")
    rows.append([r"\quad current-era frames on those channels", "", _math(fmt_int(band["frames"])) if band["channels"] else DASH])
    rows.append([r"\quad masked fraction $f$, frame-weighted", "", _math(fmt(band["masked_fraction"], 3))])
    cost_text, cost_decimals = _sig(band["time_cost"])
    rows.append([r"\quad integration-time cost $1/(1-f)$", "", _math(cost_text)])
    if band["channels"]:
        frag.add("ch11.matrix.kept_frames", band["frames"], kind="int", row={"group": "band level"}, column="value")
        frag.add("ch11.matrix.masked_fraction", band["masked_fraction"], precision=3, status="derived", row={"group": "band level"}, column="value")
        if cost_text != DASH:
            frag.add("ch11.matrix.time_cost", band["time_cost"], precision=cost_decimals, status="derived", renderings=(cost_text,),
                     row={"group": "band level"}, column="value")
        frag.add("ch11.matrix.operating_point_basis", basis, kind="text", renderings=(basis,), row={"group": "band level"}, column="disposition")
    frag.notes.extend(_band_notes(band))
    frag.notes.append("handover policy derived from the class by the chapter 9 rules: occupancy-wall excision candidates -> excised "
                      "interior with the pilot-bin channel (the product channel) kept as a monitoring tap; every other class -> "
                      "kept-and-masked at the operating point (off-era channels kept on an off era, their point a false-alarm basis)")
    frag.notes.append("integration-time cost = total current-era frames over frames kept at the points on the kept channels, "
                      "1/(1 - f) of the frame-weighted f")

    frag.tex = booktabs(["", "channels", "value"], rows, "lrr",
                        midrules=[i for i, r in enumerate(rows) if r[0].startswith(r"\emph") and i > 0])
    frag.inputs = run.inputs()
    return frag


# ------------------------------------------------------------------ (b) the atlas counts
def build_atlas_counts(run: Run) -> Fragment:
    """tab:archive:atlas-counts: the per-channel denominators of the diagnostic plates.

    The columns are the appendix C stub's own and no others; the frame count
    ``product.n_frames`` and the two blocks behind the kept count keep their
    numbers under :data:`NOT_PRINTED` without a column.
    """
    frag = Fragment("archive_atlas_counts", "tab:archive:atlas-counts", "")
    header = ["ch", r"\texttt{freq\_id}", "valid", _head("excluded", "(reason)"), "current era", _head("era", "frames"),
              _head("kept at point", r"(cal.\ + eval.)"), _head("plate", "digest")]
    rows = []
    no_point, daggered, no_replay, empty_replay, no_era, gated = [], [], [], [], [], []
    refusals: dict[str, list[int]] = {}
    for ch in run.channels:
        row_id = {"channel": ch.channel}
        prod, era = ch.section("product"), ch.era
        cells = [str(ch.channel), str(ch.freq_id)]
        frag.add(f"appC.atlas_counts.freq_id.ch{ch.channel}", ch.freq_id, kind="int", row=row_id, column="freq_id")

        counts = {}
        for key, column in (("n_frames", NOT_PRINTED), ("n_valid", "valid")):
            value = _num(prod.get(key))
            counts[key] = None if value is None else int(round(value))
            if value is not None:
                frag.add(f"appC.atlas_counts.{key}.ch{ch.channel}", counts[key], kind="int", row=row_id, column=column)
        cells.append(_math(fmt_int(counts["n_valid"])))
        if counts["n_frames"] is not None and counts["n_frames"] != counts["n_valid"]:
            gated.append(ch.channel)

        excluded = _num(prod.get("health_excluded"))
        reasons = render_reasons(prod.get("health_reasons"))
        cells.append(excluded_cell(excluded, prod.get("health_reasons")))
        if excluded is not None:
            frag.add(f"appC.atlas_counts.health_excluded.ch{ch.channel}", int(round(excluded)), kind="int", row=row_id, column="excluded")
            if reasons:
                frag.add(f"appC.atlas_counts.health_reasons.ch{ch.channel}", str(prod.get("health_reasons")), kind="text",
                         renderings=(reasons,), row=row_id, column="excluded")

        first, last = era.get("current_first_month"), era.get("current_last_month")
        if first and last:
            span = f"{fmt_month(first)}--{fmt_month(last)}"
            cells.append(span)
            frag.add(f"appC.atlas_counts.current_era.ch{ch.channel}", f"{first}..{last}", kind="text", renderings=(span,),
                     row=row_id, column="current era")
        else:
            cells.append(DASH)
            no_era.append(ch.channel)
        frames = _num(era.get("current_frames"))
        cells.append(_math(fmt_int(frames)))
        if frames is not None:
            frag.add(f"appC.atlas_counts.current_frames.ch{ch.channel}", int(round(frames)), kind="int", row=row_id, column="era frames")

        kept = kept_at_point(ch)
        marks = [MARK_DIAGNOSTIC] if kept["basis"] == "diagnostic" else []
        status = "derived" if kept["basis"] == "diagnostic" else "measured"
        if kept["basis"] == "diagnostic":
            daggered.append(ch.channel)
        for block in ("calibration", "evaluation"):       # the blocks are numbers only: the stub asks for one kept column
            value = kept[block]
            if value is not None:
                frag.add(f"appC.atlas_counts.kept_{block}.ch{ch.channel}", value, kind="int", status=status, row=row_id,
                         column=NOT_PRINTED)
        total = None
        if kept["calibration"] is not None and kept["evaluation"] is not None:
            total = kept["calibration"] + kept["evaluation"]
            frag.add(f"appC.atlas_counts.kept_total.ch{ch.channel}", total, kind="int", status="derived", row=row_id,
                     column="kept at point")
        elif kept["calibration"] is not None:             # no replay: the cell is the calibration block alone
            total = kept["calibration"]
            marks.append(MARK_NO_REPLAY)
            no_replay.append(ch.channel)
        cells.append(kept_cell(total, marks))
        if kept["calibration"] is None:
            no_point.append(ch.channel)
            refusals.setdefault(str(ch.selection.get("refusal") or selection_status(ch)), []).append(ch.channel)
        elif kept["evaluation"] == 0:
            empty_replay.append(ch.channel)

        cells.append(DASH)
        rows.append(cells)

    frag.tex = booktabs(header, rows, "rrrlcrrl")
    frag.inputs = run.inputs()
    frag.notes.append("the printed columns are the appendix C stub's own and no others: freq_id, the valid frames in the archive, the "
                      "frames excluded by reason, the current era and its frame count, the frames kept by the point, and the plate digest")
    frag.notes.append("kept at point = round((1 - f) x selection.calibration_frames), the frames the point keeps on the calibration block "
                      "with f its masked fraction there, plus selection.kept_evaluation, the frames the point's replay on the evaluation "
                      "block kept; that sum is the plate's denominator (appC.atlas_counts.kept_total)")
    frag.notes.append("the two blocks are not printed as separate columns: their counts stay in the numbers "
                      "(appC.atlas_counts.kept_calibration, appC.atlas_counts.kept_evaluation)")
    if daggered:
        frag.notes.append(f"dagger: no selected (rho*, eta*) on {_channel_phrase(daggered)}; the kept cell is at the diagnostic "
                          "point (selection.diagnostic_masked_fraction, the least-residual point of the calibration surface, "
                          "claim_status diagnostic), not at an operating point")
    if no_replay:
        frag.notes.append(f"double dagger: the kept cell on {_channel_phrase(no_replay)} is the calibration block alone; the point "
                          "was not replayed on the evaluation block (selection.masked_fraction_evaluation absent), so no plate denominator "
                          "is defined")
    if no_point:
        frag.notes.append(f"kept at point is the dash on {_channel_phrase(no_point)}: no point of any kind "
                          "(selection.status refused, no evaluated surface)")
        for why, chans in refusals.items():
            frag.notes.append(f"  {_channel_list(chans)}: {why}")
    if empty_replay:
        frag.notes.append(f"the replay kept no frame on {_channel_phrase(empty_replay)} (kept_evaluation 0: the kept cell counts "
                          "the calibration block alone, and 0 is a count, not an absent value)")
    if no_era:
        frag.notes.append(f"no current-era span in the ledger: {_channel_list(no_era)}")
    frag.notes.append("excluded (reason): frames removed by the input-health gate; the gate's reason counts "
                      f"({', '.join(f'{k} = {v}' for k, v in REASON_LABELS.items())}) cover every frame it saw, "
                      "so a reason can also cover frames already outside the valid count; a list of more than one reason is set one "
                      "reason to a line inside the cell")
    frag.notes.append("product.n_frames, the archive frame count before the input-health gate, is not printed (the stub's denominator is "
                      "the valid count); it stays in the numbers (appC.atlas_counts.n_frames) and differs from the valid count on "
                      + (_channel_phrase(gated) if gated else "no channel of this run"))
    frag.notes.append("plate digest is the dash: the plates are pending (rendered from channels/chNN/spectra_window.json by the figure step)")
    return frag


# ------------------------------------------------------------------ (c) the headline numbers
def headline_values(run: Run) -> tuple[list[dict], list[str]]:
    """The headline numbers as ``{name, value, kind, precision, renderings, status}`` records, and notes."""
    notes: list[str] = []
    out: list[dict] = []

    def put(name, value, *, kind="int", precision=None, renderings=(), status="measured"):
        out.append({"name": name, "value": value, "kind": kind, "precision": precision, "renderings": tuple(renderings), "status": status})

    def put_list(name, channels):
        text = _channel_list(channels)
        put(name, text, kind="text", renderings=(text,))

    counts = class_counts(run)
    put("channels", len(run.channels))
    for cls in sc.CLASSES:
        put(f"class.{CLASS_SLUGS[cls]}", len(counts[cls]))
        if counts[cls]:
            put_list(f"class.{CLASS_SLUGS[cls]}_channels", counts[cls])
    if counts.get(UNCLASSIFIED):
        put("class.unclassified", len(counts[UNCLASSIFIED]))
        put_list("class.unclassified_channels", counts[UNCLASSIFIED])
    put("measurement_bound", len(counts[sc.BOUND_FLOOR]) + len(counts[sc.BOUND_TAU]))
    put("kept_and_masked", len(counts[sc.RECOVERY]) + len(counts[sc.BOUND_FLOOR]) + len(counts[sc.BOUND_TAU]) + len(counts[sc.OFF_ERA]))

    statuses = selection_counts(run)
    for status, slug in SELECTION_SLUGS.items():
        put(f"selection_{slug}", len(statuses[status]))
    for status in statuses:
        if status not in SELECTION_SLUGS:
            put(f"selection_{_slug(status)}", len(statuses[status]))
            notes.append(f"selection status {status!r} on {_channel_list(statuses[status])}")
    put_list("selection_refused_channels", statuses["refused"])
    put("selection_diagnostic", sum(1 for c in run.channels if c.selection.get("claim_status") == "diagnostic"))

    floors: dict[str, list[int]] = {e: [] for e in FLOOR_EVIDENCE}
    bases: dict[str, list[int]] = {}
    for ch in run.channels:
        evidence = ch.null.get("floor_evidence") or ch.selection.get("floor_evidence")
        if evidence in floors:
            floors[evidence].append(ch.channel)
            if evidence == "stated":
                bases.setdefault(str(ch.null.get("floor_basis") or ""), []).append(ch.channel)
        else:
            notes.append(f"ch{ch.channel}: floor evidence {evidence!r} counted nowhere")
    for evidence, chans in floors.items():
        put(f"floor_{evidence}", len(chans))
        put_list(f"floor_{evidence}_channels", chans)
    for basis, chans in sorted(bases.items()):
        put(f"floor_stated_{_slug(basis)}", len(chans))
        notes.append(f"stated floors from '{basis or 'unrecorded basis'}': {_channel_list(chans)}")

    taus: dict[str, list[int]] = {q: [] for q in TAU_QUALITIES}
    for ch in run.channels:
        quality = ch.chain.get("tau_quality") if ch.has("chain") else "unmeasured"
        taus[quality if quality in taus else "unmeasured"].append(ch.channel)
    put("tau_measured", len(taus["measured"]))
    put("tau_bounded", len(taus["bounded_above"]))
    put("tau_refused", len(taus["refused"]))
    put("tau_unmeasured", len(taus["unmeasured"]))
    put_list("tau_measured_channels", taus["measured"])
    put_list("tau_bounded_channels", taus["bounded_above"])
    if taus["refused"]:
        notes.append("tau_c refused on " + _channel_list(taus["refused"]) + ": the chain is booked at the sidereal-day cap")

    kstar, why = read_kstar(run)
    if kstar is None:
        notes.append(why)
    else:
        put("kstar_e_min", kstar["e_min"], kind="float", precision=2)
        for name in ("k_star", "failing_k", "binding_channel"):
            if kstar[name] is not None:
                put(f"kstar_{name}", int(round(kstar[name])))
        if kstar["binding_e"] is not None:
            put("kstar_binding_e", kstar["binding_e"], kind="float", precision=3)
        put("kstar_sentinels", kstar["sentinels"], kind="text", renderings=(kstar["sentinels"],))

    within, best, coarse_best, coarse_channels = [], None, None, []
    for ch in run.channels:
        r = _num(ch.selection.get("min_R"))
        if r is not None:
            if r <= WITHIN_FACTOR:
                within.append(ch.channel)
            if best is None or r < best[1]:
                best = (ch.channel, r)
        c = _num(ch.selection.get("coarse_min_R"))
        if c is not None:
            coarse_channels.append(ch.channel)
            if coarse_best is None or c < coarse_best[1]:
                coarse_best = (ch.channel, c, _num(ch.selection.get("coarse_min_R_masked_fraction")))
    put("within_10x_tolerance", len(within))
    put_list("within_10x_tolerance_channels", within)
    if best is None:
        notes.append("no channel has a least residual on its evaluated surface: min_R undefined")
    else:
        text, decimals = _sig(best[1])
        put("min_R", best[1], kind="float", precision=decimals, renderings=(text,))
        put("min_R_channel", best[0])
    put("coarse_frontier_channels", len(coarse_channels))
    if coarse_best is None:
        notes.append("no channel has a coarse-rule frontier: coarse_min_R undefined")
    else:
        text, decimals = _sig(coarse_best[1])
        put("coarse_min_R", coarse_best[1], kind="float", precision=decimals, renderings=(text,))
        put("coarse_min_R_channel", coarse_best[0])
        if coarse_best[2] is not None:
            put("coarse_min_R_masked_fraction", coarse_best[2], kind="float", precision=3)

    centred, with_centre = [], []
    widths: dict[str, list[float]] = {"coarse_core_width_factor": [], "fine_core_width_factor": []}
    for ch in run.channels:
        centre_db = _num(ch.null.get("coarse_centre_db"))
        if centre_db is not None:
            with_centre.append(ch.channel)
            if abs(centre_db) <= CENTRE_TOLERANCE_DB:
                centred.append(ch.channel)
        for key, values in widths.items():
            value = _num(ch.null.get(key))
            if value is not None:
                values.append(value)
    put("coarse_centre_within_0p1_db", len(centred))
    put("coarse_centre_channels", len(with_centre))
    if with_centre:
        put("coarse_centre_within_0p1_db_fraction", len(centred) / len(with_centre), kind="float", precision=2, status="derived")
    else:
        notes.append("no channel has a coarse null centre: the centred fraction is undefined")
    for key, values in widths.items():
        if values:
            for stat, value in (("min", min(values)), ("max", max(values))):
                text, decimals = _sig(value)
                put(f"{key}_{stat}", value, kind="float", precision=decimals, renderings=(text,))
        else:
            notes.append(f"no channel has null.{key}: its range is undefined")

    band = band_level(run)
    put("kept_channels", len(band["channels"]))
    if band["channels"]:
        put("kept_frames", band["frames"])
        put("masked_fraction", band["masked_fraction"], kind="float", precision=3, status="derived")
        cost_text, cost_decimals = _sig(band["time_cost"])
        if cost_text != DASH:
            put("time_cost", band["time_cost"], kind="float", precision=cost_decimals, renderings=(cost_text,), status="derived")
        put("operating_point_basis", band["basis"], kind="text", renderings=(band["basis"],))
    notes.extend(_band_notes(band))
    return out, notes


def build_headline(run: Run) -> Fragment:
    """``headline``: the chapter 11 and front-matter numbers, no table."""
    frag = Fragment("headline", "", "")
    values, notes = headline_values(run)
    lines = ["% headline: numbers only (no table); every value is in numbers/headline.numbers.json",
             "% under ch11.headline.<name> and front.headline.<name>"]
    for rec in values:
        for prefix in ("ch11", "front"):
            frag.add(f"{prefix}.headline.{rec['name']}", rec["value"], kind=rec["kind"], precision=rec["precision"],
                     renderings=rec["renderings"], status=rec["status"], row={"prefix": prefix}, column=rec["name"])
        lines.append(f"% ch11.headline.{rec['name']} = {rec['value']!r}")
    frag.tex = "\n".join(lines) + "\n"
    frag.notes.extend(notes)
    kstar_path = run.results_dir / "tables" / "kstar.csv"
    frag.inputs = run.inputs() + ([kstar_path] if kstar_path.is_file() else [])
    return frag


BUILDERS = (build, build_atlas_counts, build_headline)
