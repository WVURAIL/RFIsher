"""``calibration_anchors`` and ``calibration_containment``: the measured anchors
against the fine spans (ch08 ``tab:calibration:anchors``) and the compact
K = 64/128/256 containment companion of ``fig:calibration:containment``, both
read from the ledger alone.

Each table has one row per channel (14--36). Numeric cells are set in math
mode (:func:`core.fmt`: ASCII hyphen as the minus sign, ``{,}`` thousands);
an absent or undefined value prints as ``--`` (:data:`core.DASH`), no number
is emitted for it, and the fragment's notes say why. Text cells are emitted
as ``kind='text'`` numbers whose rendering is the printed cell. No channel of
the v5 run has a selected operating point: the ``selector bin`` column is the
bin the *diagnostic* selection centred its window on, and the notes say so.

``calibration_anchors`` (:func:`build`; keys ``ch08.anchors.<column>.chNN``)
=========================================================================

The anchor of record is the current era's (section ``anchor``: eq
calibration:anchor over the whole current era, with its block bootstrap). On
the channels whose current era is off it is the previous (on) era's
(``anchor.source == 'previous_era'``), and the ``era`` cell says so.

===============  ==========================================================
column           ledger keys and rendering
===============  ==========================================================
ch               the channel
era              ``anchor.source``: the era the anchor of record was measured
                 on -- ``current`` the current era; ``previous`` the previous
                 (on) era, on the channels whose current era is off;
                 ``cal.\\ block`` the calibration block (not a v5 case)
estimator        ``anchor.method``: ``on-quiet`` (eq calibration:anchor, used
                 only where ``anchor.quiet_cohort_is_null``) or ``median (on)``
                 -- the plain median of the cohort ``anchor.fallback_cohort``
                 names (the text number carries the whole string)
bin              ``anchor.anchor_bin`` (padded fine bin, 0..255), marked
                 ``s`` when ``containment.anchor_suspect``: the anchor
                 disagrees with the in-span lobe, folds onto an out-of-span
                 feature, or its bootstrap mode mass
                 (``anchor.boot_mode_mass``) is below 0.5
f_a (Hz)         ``anchor.anchor_rf_offset_hz``: the RF offset of the anchor
                 from the nominal pilot (positive towards higher RF)
[q16, q84] (Hz)  ``anchor.boot_rf_hz_q16``, ``boot_rf_hz_q84``: the 16--84 %
                 block-bootstrap interval; dashed unless
                 ``anchor.boot_status == 'ok'``
selector bin     ``selection.anchor_bin`` tagged by ``selection.anchor_source``:
                 the bin the diagnostic selection centred its designated
                 window on -- ``cal`` the calibration block's anchor
                 (``anchor_calibration.anchor_bin``, held out from the
                 evaluation block); ``lobe`` the spectrum's in-span lobe
                 (``containment.lobe_fine_bin``), taken because the fine
                 anchor is suspect, with the calibration block's anchor in
                 parentheses; ``nominal`` the nominal fine bin (no anchor
                 measured); ``era`` / ``prev`` the anchor of record (the
                 calibration block's not measured). When the selection did
                 not run the calibration block's bin is printed untagged.
dom. (Hz / dB)   ``containment.dominant_refined_offset_hz``, ``dominant_db``:
                 the dominant lobe of the era-mean spectrum within +-15 kHz
                 (outside the centre line), dB over the window median; the
                 Hz cell is marked ``a`` when ``containment.window_aliased_hz``
                 is positive (the pilot lies within the window of a
                 coarse-channel edge, ``containment.edge_distance_hz`` away,
                 and the far side of the window is read as aliased content)
in-span (Hz)     ``containment.in_span_refined_offset_hz``: the strongest
                 feature inside the K = 128 span (dashed when
                 ``containment.in_span_recovered`` is false)
Delta (bins)     ``containment.anchor_lobe_offset_bins``: anchor minus
                 in-span lobe in fine bins, marked ``*`` when
                 ``containment.anchor_lobe_disagree`` (beyond the designated
                 half-width) and ``f`` when
                 ``containment.anchor_folds_out_of_span`` (the anchor folds
                 onto the out-of-span feature by one coarse bin)
|df| 50/90/99    ``containment.peak_abs_median_hz``, ``peak_abs_p90_hz``,
                 ``peak_abs_p99_hz``: percentiles of the per-frame peak
                 offset magnitude over coarse-detected frames, integer Hz
disposition      ``containment.disposition`` as ``supported`` / ``sentinel``
                 (= supported with sentinel) / ``unsupported`` with
                 ``containment.reasons`` abbreviated: ``oos`` a stronger
                 out-of-span feature, ``E`` E_128 below E_min, ``ref``
                 K = 128 reference contamination at or above the bound,
                 ``alias`` the fine anchor folds onto an out-of-span feature,
                 ``lobe`` the fine anchor disagrees with the in-span lobe
prev. (Hz)       ``anchor_previous.anchor_rf_offset_hz``: the previous era's
                 anchor (dashed on one-era channels; on an off-era channel
                 it repeats the anchor of record)
shift (bins)     ``anchor_previous.shift_from_previous_bins``: the current
                 era's own anchor (``anchor_era``: on an off-era channel the
                 off era's argmax) minus the previous era's, unwrapped fine
                 bins
===============  ==========================================================

``calibration_containment`` (:func:`build_containment`; keys
``ch08.containment.<column>.chNN`` and ``ch04.kstar.<column>.emin<E_min>``)
=========================================================================

One row per channel, then one ``K*`` row per ``E_min`` of ``tables/kstar.csv``.

===============  ==========================================================
column           ledger keys and rendering
===============  ==========================================================
ch               the channel
disp.            ``containment.disposition`` (short word, as above), marked
                 ``a`` when ``containment.window_aliased_hz`` is positive
F_K              ``containment.frames_in_span_K``: fraction of the
                 coarse-detected frames whose spectrum peak lies inside
                 the span +-f_s/2K
E_K              ``containment.e_K``: fraction of the pilot-associated
                 energy inside the span (eq:param:kstar)
L_K (dB)         ``containment.straddle_loss_db_K``: the Dirichlet straddle
                 loss at the in-span lobe
M_K (Hz)         ``containment.margin_hz_K``: margin from the in-span lobe
                 to the span edge (negative outside the span)
C_K              ``containment.ref_contamination_K``: excess in the two
                 reference passbands over the in-span excess, marked ``a``
                 when ``containment.ref_aliased_K`` (a passband crossing
                 the coarse-channel edge is read at its aliased position)
K* rows          ``tables/kstar.csv``: ``k_star`` is marked in the E_K
                 column of that K, ``failing_k`` carries the binding
                 channel and its ``binding_e``; the ``disp.`` cell counts
                 the eligible channels and names the sentinels (channels
                 below E_min at every K, which do not drag the choice)
===============  ==========================================================
"""
from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Mapping, Sequence

from .core import DASH, Channel, Fragment, Run, booktabs, fmt, fmt_int, tex

SPANS = (64, 128, 256)
CHAPTER = "ch08"

_SOURCE = {"calibration": "cal.\\ block", "current_era": "current", "previous_era": "previous"}
_SELECTOR_SOURCE = {"calibration": "cal", "psd in-span lobe (fine anchor suspect)": "lobe", "nominal bin": "nominal",
                    "current_era": "era", "previous_era": "prev"}
_METHOD = {"on_minus_quiet": "on-quiet", "median_fallback": "median"}
_DISPOSITION = {"supported": "supported", "supported with sentinel": "sentinel", "unsupported": "unsupported"}
_REASON_CODES = (
    ("stronger out-of-span feature", "oos"),
    ("E_128 =", "E"),
    ("reference contamination", "ref"),
    ("fine anchor aliases", "alias"),
    ("from the PSD in-span lobe", "lobe"),
)
SUSPECT_MARK = "\\mathrm{s}"
ALIAS_MARK = "\\mathrm{a}"
DISAGREE_MARK = "*"
FOLD_MARK = "\\mathrm{f}"
MODE_MASS_LIMIT = 0.5                       # run.py: a bootstrap mode mass below this makes the anchor suspect
REASON_LEGEND = ("disposition reasons: oos = stronger out-of-span feature; E = E_128 below E_min; "
                 "ref = K = 128 reference contamination at or above the bound; alias = fine anchor folds onto an "
                 "out-of-span feature by one coarse bin; lobe = fine anchor disagrees with the in-span lobe by more "
                 "than the designated half-width")


# ------------------------------------------------------------------ helpers
def _finite(value) -> bool:
    try:
        return value is not None and not isinstance(value, bool) and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _chlist(channels: Sequence[int]) -> str:
    return ", ".join(str(c) for c in channels)


def _sup(*marks: str) -> str:
    """The superscript carrying the given marks, empty when there is none."""
    marks = tuple(m for m in marks if m)
    return f"^{{{''.join(marks)}}}" if marks else ""


def reason_codes(reasons) -> list[str]:
    """``containment.reasons`` (``;``-joined sentences) as the short codes of the module docstring."""
    out: list[str] = []
    for part in str(reasons or "").split(";"):
        part = part.strip()
        if not part:
            continue
        code = next((code for needle, code in _REASON_CODES if needle in part), "other")
        if code not in out:
            out.append(code)
    return out


def disposition_text(disposition, reasons="") -> str:
    """``supported`` / ``sentinel: oos, E`` / ``unsupported``; an unknown disposition passes through."""
    word = _DISPOSITION.get(str(disposition), str(disposition))
    codes = reason_codes(reasons)
    return f"{word}: {', '.join(codes)}" if codes else word


def method_text(method, fallback_cohort="") -> str:
    """``on-quiet`` / ``median (on)``: the cohort word of ``anchor.fallback_cohort`` without its parenthesis."""
    rendering = _METHOD.get(str(method), str(method))
    cohort = str(fallback_cohort or "").split("(")[0].strip()
    if method == "median_fallback" and cohort:
        rendering = f"{rendering} ({cohort})"
    return rendering


def window_aliased(cont: Mapping) -> bool:
    """Whether the containment window's far side is aliased content (``window_aliased_hz > 0``)."""
    value = cont.get("window_aliased_hz")
    return _finite(value) and float(value) > 0.0


class _Row:
    """Cells of one channel's row; every printed value goes to the fragment as a number."""

    def __init__(self, frag: Fragment, prefix: str, ch: int):
        self.frag, self.prefix, self.ch = frag, prefix, ch
        self.row = {"channel": ch}

    def num(self, column: str, value, *, digits: int | None = None, integer: bool = False, plus: bool = False,
            mark: str = "") -> str:
        """A math-mode number cell, or the dash when the value is absent or not finite."""
        if not _finite(value):
            return DASH
        if integer:
            text = fmt(value, 0, plus=True) if plus else fmt_int(value)
            self.frag.add(f"{self.prefix}.{column}.ch{self.ch}", int(round(float(value))), precision=0, kind="int",
                          row=self.row, column=column)
        else:
            text = fmt(value, digits, plus=plus)
            self.frag.add(f"{self.prefix}.{column}.ch{self.ch}", float(value), precision=digits, row=self.row, column=column)
        if text[:1] in "+-" and float(text[1:].replace("{,}", "")) == 0.0:
            text = text[1:]                      # a value that rounds to zero prints unsigned, not as -0.0 or +0.0
        return f"${text}{mark}$"

    def text(self, column: str, value, rendering: str) -> str:
        self.frag.add(f"{self.prefix}.{column}.ch{self.ch}", str(value), kind="text", renderings=(rendering,),
                      row=self.row, column=column)
        return tex(rendering)

    def flag(self, column: str, rendering: str) -> None:
        """A boolean ledger flag that is printed as a mark."""
        self.text(column, "true", rendering)


def _disposition_cell(row: _Row, cont: Mapping, *, with_reasons: bool) -> str:
    disposition = cont.get("disposition")
    if not disposition:
        return DASH
    reasons = cont.get("reasons", "") if with_reasons else ""
    cell = row.text("disposition", disposition, disposition_text(disposition, reasons))
    if with_reasons and reasons:
        row.frag.add(f"{row.prefix}.reasons.ch{row.ch}", str(reasons), kind="text",
                     renderings=(", ".join(reason_codes(reasons)),), row=row.row, column="disposition")
    return cell


def _aliased_window(row: _Row, cont: Mapping, tally: dict) -> bool:
    """Record an aliased containment window (the far side of +-W beyond the coarse-channel edge)."""
    if not window_aliased(cont):
        return False
    row.num("window_aliased_hz", cont.get("window_aliased_hz"), digits=0)
    row.num("edge_distance_hz", cont.get("edge_distance_hz"), digits=0)
    tally["aliased_window"].append((row.ch, cont.get("edge_distance_hz"), cont.get("window_aliased_hz")))
    return True


# ------------------------------------------------------------------ anchors
ANCHOR_HEADER = ("ch", "era", "estimator", "bin", r"$\widehat f_a$ (Hz)", r"$[q_{16}, q_{84}]$ (Hz)", "selector bin",
                 "dom.\\ (Hz)", "dom.\\ (dB)", "in-span (Hz)", r"$\Delta$ (bins)", r"$|\delta f|_{50}$ (Hz)",
                 r"$|\delta f|_{90}$ (Hz)", r"$|\delta f|_{99}$ (Hz)", "disposition", "prev.\\ (Hz)", "shift (bins)")
ANCHOR_ALIGN = "lllrrrlrrrrrrrlrr"


def _suspect_reasons(anchor: Mapping, cont: Mapping) -> list[str]:
    """Why ``containment.anchor_suspect`` is set, in the run's three terms."""
    why = []
    if cont.get("anchor_lobe_disagree"):
        why.append(f"{fmt(cont.get('anchor_lobe_offset_bins'), 1, plus=True)} bins from the in-span lobe")
    if cont.get("anchor_folds_out_of_span"):
        why.append("folds onto the out-of-span feature")
    mass = anchor.get("boot_mode_mass")
    if _finite(mass) and float(mass) < MODE_MASS_LIMIT:
        why.append(f"bootstrap mode mass {fmt(mass, 2)}")
    return why or ["flagged by the run without a recorded term"]


def _anchor_cells(row: _Row, c: Channel, tally: dict) -> list[str]:
    """era, estimator, bin, f_a, [q16, q84]."""
    anchor, cont = c.anchor, c.containment
    if not c.has("anchor"):
        tally["no_anchor"].append(c.channel)
        return [DASH] * 5
    cells = []
    source = str(anchor.get("source", ""))
    cells.append(row.text("source", source, _SOURCE.get(source, source)) if source else DASH)
    if source == "previous_era":
        tally["previous_source"].append(c.channel)
    method = str(anchor.get("method", ""))
    if method:
        cells.append(row.text("method", f"{method} {anchor.get('fallback_cohort', '') or ''}".strip(),
                              method_text(method, anchor.get("fallback_cohort", ""))))
        if method == "median_fallback":
            tally["median_fallback"].append(c.channel)
    else:
        cells.append(DASH)
    if anchor.get("status") != "ok":
        tally["anchor_not_ok"].append((c.channel, str(anchor.get("status", ""))))
        return cells + [DASH] * 3
    suspect = bool(c.has("containment") and cont.get("anchor_suspect", False))
    cells.append(row.num("anchor_bin", anchor.get("anchor_bin"), integer=True, mark=_sup(SUSPECT_MARK if suspect else "")))
    if suspect:
        row.flag("anchor_suspect", "s")
        tally["suspect"].append((c.channel, "; ".join(_suspect_reasons(anchor, cont))))
    cells.append(row.num("anchor_rf_offset_hz", anchor.get("anchor_rf_offset_hz"), digits=1))
    q16, q84 = anchor.get("boot_rf_hz_q16"), anchor.get("boot_rf_hz_q84")
    if anchor.get("boot_status") == "ok" and _finite(q16) and _finite(q84):
        row.num("boot_rf_hz_q16", q16, digits=1)
        row.num("boot_rf_hz_q84", q84, digits=1)
        cells.append(f"$[{fmt(q16, 1)},\\,{fmt(q84, 1)}]$")
    else:
        tally["no_boot"].append((c.channel, str(anchor.get("boot_status", ""))))
        cells.append(DASH)
    return cells


def _selector_cell(row: _Row, c: Channel, tally: dict) -> str:
    """The bin the diagnostic selection used, tagged by its source, with the calibration block's anchor beside it."""
    cal = c.section("anchor_calibration")
    cal_bin = cal.get("anchor_bin") if c.has("anchor_calibration") and cal.get("status") == "ok" else None
    cal_text = row.num("calibration_anchor_bin", cal_bin, integer=True) if _finite(cal_bin) else ""
    if not c.has("selection"):
        tally["no_selection"].append(c.channel)
        return cal_text or DASH
    sel = c.selection
    sel_bin = sel.get("anchor_bin")
    if not _finite(sel_bin):
        tally["no_selector_bin"].append(c.channel)
        return cal_text or DASH
    sel_text = row.num("selector_anchor_bin", sel_bin, integer=True)
    source = str(sel.get("anchor_source", "") or "")
    tag = row.text("selector_anchor_source", source, _SELECTOR_SOURCE.get(source, source)) if source else ""
    if source.startswith("psd in-span lobe"):
        tally["lobe_selector"].append(c.channel)
    elif source == "nominal bin":
        tally["nominal_selector"].append(c.channel)
    cell = f"{tag} {sel_text}".strip()
    if cal_text and int(round(float(cal_bin))) != int(round(float(sel_bin))):
        cell += f" (cal {cal_text})"
    return cell


def _spectrum_cells(row: _Row, c: Channel, tally: dict) -> list[str]:
    """dom. (Hz), dom. (dB), in-span, Delta, |df| 50/90/99, disposition."""
    cont = c.containment
    if not c.has("containment"):
        tally["no_containment"].append(c.channel)
        return [DASH] * 8
    cells = []
    aliased = _aliased_window(row, cont, tally)
    cells.append(row.num("dominant_refined_offset_hz", cont.get("dominant_refined_offset_hz"), digits=1,
                         mark=_sup(ALIAS_MARK if aliased else "")))
    cells.append(row.num("dominant_db", cont.get("dominant_db"), digits=1))
    in_span = cont.get("in_span_refined_offset_hz") if cont.get("in_span_recovered", True) else None
    if not _finite(in_span):
        tally["no_in_span"].append(c.channel)
    cells.append(row.num("in_span_refined_offset_hz", in_span, digits=1))
    disagree, folds = bool(cont.get("anchor_lobe_disagree", False)), bool(cont.get("anchor_folds_out_of_span", False))
    cells.append(row.num("anchor_lobe_offset_bins", cont.get("anchor_lobe_offset_bins"), digits=1, plus=True,
                         mark=_sup(DISAGREE_MARK if disagree else "", FOLD_MARK if folds else "")))
    if disagree:
        row.flag("anchor_lobe_disagree", "*")
    if folds:
        row.flag("anchor_folds_out_of_span", "f")
        tally["folds"].append(c.channel)
    for column in ("peak_abs_median_hz", "peak_abs_p90_hz", "peak_abs_p99_hz"):
        cells.append(row.num(column, cont.get(column), integer=True))
    cells.append(_disposition_cell(row, cont, with_reasons=True))
    return cells


def _previous_cells(row: _Row, c: Channel, tally: dict) -> list[str]:
    """prev. (Hz), shift (bins)."""
    previous = c.section("anchor_previous")
    if not c.has("anchor_previous"):
        tally["one_era"].append(c.channel)
        return [DASH, DASH]
    if previous.get("status") != "ok":
        tally["previous_not_ok"].append((c.channel, str(previous.get("status", ""))))
        return [DASH, DASH]
    return [row.num("previous_anchor_rf_offset_hz", previous.get("anchor_rf_offset_hz"), digits=1),
            row.num("shift_from_previous_bins", previous.get("shift_from_previous_bins"), integer=True, plus=True)]


def _anchor_row(frag: Fragment, c: Channel, tally: dict) -> list[str]:
    row = _Row(frag, f"{CHAPTER}.anchors", c.channel)
    return ([str(c.channel)] + _anchor_cells(row, c, tally) + [_selector_cell(row, c, tally)]
            + _spectrum_cells(row, c, tally) + _previous_cells(row, c, tally))


def _new_tally() -> dict:
    return {k: [] for k in ("no_anchor", "anchor_not_ok", "no_boot", "previous_source", "median_fallback", "suspect",
                           "no_selection", "no_selector_bin", "lobe_selector", "nominal_selector", "no_containment",
                           "aliased_window", "no_in_span", "folds", "one_era", "previous_not_ok")}


def _pairs(items) -> str:
    return "; ".join(f"ch{c}: {s or 'unset'}" for c, s in items)


def build(run: Run) -> Fragment:
    """``tab:calibration:anchors``: the measured anchors against the fine span, one row per channel."""
    frag = Fragment("calibration_anchors", "tab:calibration:anchors", "")
    tally = _new_tally()
    rows = [_anchor_row(frag, c, tally) for c in run.channels]
    frag.tex = booktabs(ANCHOR_HEADER, rows, ANCHOR_ALIGN)
    notes = frag.notes
    notes.append("era: the era the anchor of record was measured on -- current = the current era (eq. 8.1 with its "
                 "block bootstrap), previous = the previous on era, on the channels whose current era is off")
    if tally["previous_source"]:
        notes.append(f"channels {_chlist(tally['previous_source'])} have an off current era: the anchor of record "
                     "(era = previous) is the previous era's, the prev.\\ column repeats it, and the shift is from it "
                     "to the off current era's own argmax (anchor_era), not between two calibration anchors")
    if tally["no_anchor"]:
        notes.append(f"anchor section absent on channels {_chlist(tally['no_anchor'])}: anchor cells dashed")
    if tally["anchor_not_ok"]:
        notes.append(f"anchor not measured (status {_pairs(tally['anchor_not_ok'])}): bin, offset and interval dashed")
    if tally["median_fallback"]:
        notes.append(f"estimator median (on) on channels {_chlist(tally['median_fallback'])}: the plain median of the "
                     "on cohort, because the mask's quiet cohort is not a null (anchor.quiet_cohort_is_null false); "
                     "on-quiet is eq. 8.1")
    if tally["suspect"]:
        notes.append("fine anchor suspect (bin marked s) on channels "
                     f"{_chlist([c for c, _ in tally['suspect']])}: {_pairs(tally['suspect'])}")
    if tally["no_boot"]:
        notes.append(f"bootstrap interval dashed where boot_status is not ok: {_pairs(tally['no_boot'])}")
    notes.append("selector bin: the bin the diagnostic selection centred its designated window on (no channel has a "
                 "selected operating point) -- cal = the calibration block's anchor (anchor_calibration, held out "
                 "from the evaluation block), lobe = the spectrum's in-span lobe because the fine anchor is suspect "
                 "(the calibration block's anchor in parentheses), nominal = the nominal fine bin, era/prev = the "
                 "anchor of record")
    if tally["lobe_selector"]:
        notes.append(f"selector bin taken from the PSD in-span lobe on channels {_chlist(tally['lobe_selector'])}")
    if tally["nominal_selector"]:
        notes.append(f"selector bin is the nominal fine bin on channels {_chlist(tally['nominal_selector'])}: no anchor measured")
    if tally["no_selection"]:
        notes.append(f"selection did not run on channels {_chlist(tally['no_selection'])}: the calibration block's "
                     "anchor bin is printed untagged, or dashed when that anchor is not measured")
    if tally["no_selector_bin"]:
        notes.append(f"selection carries no anchor bin on channels {_chlist(tally['no_selector_bin'])}: the "
                     "calibration block's anchor bin is printed untagged, or dashed")
    if tally["no_containment"]:
        notes.append(f"containment section absent on channels {_chlist(tally['no_containment'])}: spectrum cells dashed")
    if tally["aliased_window"]:
        notes.append("spectrum window aliased (dom.\\ marked a): "
                     + "; ".join(f"ch{c}: pilot {fmt(edge, 0)} Hz from the coarse-channel edge, {fmt(width, 0)} Hz of the "
                                 "+-15 kHz window read as aliased content" for c, edge, width in tally["aliased_window"]))
    if tally["no_in_span"]:
        notes.append(f"no in-span lobe recovered on channels {_chlist(tally['no_in_span'])}: in-span offset dashed "
                     "(Delta follows from the ledger and is dashed when undefined)")
    notes.append("Delta = anchor minus in-span lobe in fine bins, marked * when |Delta| exceeds the designated "
                 "half-width (containment.anchor_lobe_disagree) and f when the anchor folds onto the out-of-span "
                 "feature by one coarse bin (containment.anchor_folds_out_of_span)")
    if tally["folds"]:
        notes.append(f"fine anchor folds onto the out-of-span feature on channels {_chlist(tally['folds'])}")
    notes.append(REASON_LEGEND)
    if tally["one_era"]:
        notes.append(f"one era only on channels {_chlist(tally['one_era'])}: previous-era anchor and shift dashed")
    if tally["previous_not_ok"]:
        notes.append(f"previous-era anchor not measured ({_pairs(tally['previous_not_ok'])}): previous-era anchor "
                     "and shift dashed")
    return frag


# ------------------------------------------------------------- containment
def containment_header() -> list[str]:
    header = ["ch", "disp."]
    for k in SPANS:
        header += [f"$F_{{{k}}}$", f"$E_{{{k}}}$", f"$L_{{{k}}}$ (dB)", f"$M_{{{k}}}$ (Hz)", f"$C_{{{k}}}$"]
    return header


CONTAINMENT_ALIGN = "ll" + "rrrrr" * len(SPANS)


def _containment_row(frag: Fragment, c: Channel, tally: dict) -> list[str]:
    row = _Row(frag, f"{CHAPTER}.containment", c.channel)
    cont = c.containment
    cells = [str(c.channel)]
    if not c.has("containment"):
        tally["no_containment"].append(c.channel)
        return cells + [DASH] * (1 + 5 * len(SPANS))
    disposition = _disposition_cell(row, cont, with_reasons=False)
    if _aliased_window(row, cont, tally) and disposition != DASH:
        disposition += f"${_sup(ALIAS_MARK)}$"
    cells.append(disposition)
    for k in SPANS:
        cells.append(row.num(f"frames_in_span_{k}", cont.get(f"frames_in_span_{k}"), digits=3))
        cells.append(row.num(f"e_{k}", cont.get(f"e_{k}"), digits=3))
        cells.append(row.num(f"straddle_loss_db_{k}", cont.get(f"straddle_loss_db_{k}"), digits=2))
        cells.append(row.num(f"margin_hz_{k}", cont.get(f"margin_hz_{k}"), integer=True))
        aliased = bool(cont.get(f"ref_aliased_{k}", False))
        cells.append(row.num(f"ref_contamination_{k}", cont.get(f"ref_contamination_{k}"), digits=3,
                             mark=_sup(ALIAS_MARK if aliased else "")))
        if aliased:
            row.flag(f"ref_aliased_{k}", "a")
            tally["aliased"].append((c.channel, k))
    return cells


def read_kstar(path: Path) -> list[dict]:
    """``tables/kstar.csv`` rows with numbers parsed; blank cells (an undefined rule) become ``None``."""
    def _int(s):
        return int(float(s)) if s not in ("", None) else None

    def _float(s):
        return float(s) if s not in ("", None) else None

    with Path(path).open(newline="", encoding="utf-8") as fh:
        rows = []
        for r in csv.DictReader(fh):
            rows.append({"e_min": float(r["e_min"]), "k_star": _int(r.get("k_star")), "failing_k": _int(r.get("failing_k")),
                         "binding_channel": _int(r.get("binding_channel")), "binding_e": _float(r.get("binding_e")),
                         "sentinels": [int(s) for s in str(r.get("sentinels") or "").split(";") if s],
                         "eligible": [int(s) for s in str(r.get("eligible") or "").split(";") if s]})
    return rows


def _kstar_row(frag: Fragment, entry: dict) -> list[str]:
    e_min = entry["e_min"]
    tag = f"emin{e_min:g}"
    key_row = {"e_min": e_min}

    def add(column, value, **kw):
        frag.add(f"ch04.kstar.{column}.{tag}", value, row=key_row, column=column, **kw)

    add("eligible_count", len(entry["eligible"]), kind="int", precision=0)
    sentinels = _chlist(entry["sentinels"])
    sentinel_text = f"sentinel {sentinels}" if sentinels else "no sentinel"
    add("sentinels", ";".join(str(c) for c in entry["sentinels"]), kind="text", renderings=(sentinel_text,))
    cells = [f"$K^\\star$ ($E_{{\\min}} = {e_min:g}$)", tex(f"{len(entry['eligible'])} eligible; {sentinel_text}")]
    if entry["k_star"] is not None:
        add("k_star", int(entry["k_star"]), kind="int", precision=0)
    if entry["failing_k"] is not None:
        add("failing_k", int(entry["failing_k"]), kind="int", precision=0)
    if entry["binding_channel"] is not None:
        add("binding_channel", int(entry["binding_channel"]), kind="int", precision=0)
    if _finite(entry["binding_e"]):
        add("binding_e", float(entry["binding_e"]), precision=3)
    for k in SPANS:
        e_cell = ""
        if entry["k_star"] == k:
            e_cell = "$K^\\star$"
        elif entry["failing_k"] == k:
            binding = f"ch{entry['binding_channel']}" if entry["binding_channel"] is not None else DASH
            e_cell = f"fails: {binding} (${fmt(entry['binding_e'], 3)}$)"
        cells += ["", e_cell, "", "", ""]
    return cells


def build_containment(run: Run) -> Fragment:
    """``fig:calibration:containment``'s companion table: containment at K = 64, 128, 256 and the K* rule."""
    frag = Fragment("calibration_containment", "fig:calibration:containment", "")
    tally = {"no_containment": [], "aliased": [], "aliased_window": []}
    rows = [_containment_row(frag, c, tally) for c in run.channels]
    notes = frag.notes
    kstar_path = run.results_dir / "tables" / "kstar.csv"
    kstar_rows = []
    if kstar_path.is_file():
        kstar_rows = read_kstar(kstar_path)
        frag.inputs = run.inputs() + [kstar_path]
        for entry in kstar_rows:
            rows.append(_kstar_row(frag, entry))
            if entry["k_star"] is None:
                notes.append(f"K* undefined at E_min = {entry['e_min']:g} (no eligible non-sentinel channel): no K marked")
            elif entry["failing_k"] is None:
                notes.append(f"no candidate K fails at E_min = {entry['e_min']:g}: K* is the largest candidate")
    else:
        notes.append("tables/kstar.csv absent: no K* rows")
    frag.tex = booktabs(containment_header(), rows, CONTAINMENT_ALIGN, midrules=[len(run.channels)] if kstar_rows else ())
    notes.insert(0, "F_K fraction of coarse-detected frames whose spectrum peak lies inside +-f_s/2K; E_K pilot-associated "
                    "energy fraction inside the span; L_K straddle loss at the in-span lobe; M_K margin from the in-span "
                    "lobe to the span edge; C_K reference-passband contamination over the in-span excess")
    if tally["no_containment"]:
        notes.append(f"containment section absent on channels {_chlist(tally['no_containment'])}: row dashed")
    if tally["aliased_window"]:
        notes.append("disp.\\ marked a where the pilot lies within the +-15 kHz window of a coarse-channel edge and the far "
                     "side of the window is read as aliased content: "
                     + "; ".join(f"ch{c} ({fmt(width, 0)} Hz aliased, edge {fmt(edge, 0)} Hz away)"
                                 for c, edge, width in tally["aliased_window"]))
    if tally["aliased"]:
        notes.append("C_K marked a where a reference passband crosses the coarse-channel edge and is read aliased: "
                     + ", ".join(f"ch{c} K={k}" for c, k in tally["aliased"]))
    notes.append("K* rows: K* marked in the E_K column of that K; the first failing K names the binding channel and its "
                 "E_K; sentinels fail E_min at every K and do not drag the choice")
    return frag


BUILDERS = (build, build_containment)
