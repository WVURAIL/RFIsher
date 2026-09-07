"""The ch05 blocked-evaluation table (``tab:estimator:blocked``, the
sec:estimator:archive stub): does the null frozen on the calibration block
transfer to the untouched evaluation block?

One row per channel 14--36. Cells read the ledger sections ``blocks``,
``null`` (the calibration block's null), ``null_evaluation`` (the same
description read on the evaluation block with nothing re-fitted) and
``selection`` (the diagnostic replay). A value the ledger does not carry or
that is undefined prints as the dash and the fragment's notes say why. No
channel of the 2026-09-07 run has a selected operating point: the replay
columns print the least-residual point of the calibration surface replayed
on the evaluation block (``selection.diagnostic_*``, claim status
``diagnostic``) and the column head says so.

Columns (ledger keys in ``section.key`` form; numeric cells are in math mode):

``ch``
    Physical channel. ``ch^{\\ddagger}`` when the block split is not
    supported (``blocks.status`` other than ``supported``; ``blocks.detail``
    goes to the notes).
``calibration block: months, frames``
    ``blocks.calibration_first_month``--``blocks.calibration_last_month``
    (the populated months of the block, first and last) and
    ``blocks.calibration_frames``.
``evaluation block: months, frames``
    ``blocks.evaluation_first_month``--``blocks.evaluation_last_month`` and
    ``blocks.evaluation_frames``.
``excluded: untimed``
    ``blocks.frames_without_time_excluded``: frames of the era without a
    recorded time, excluded from both blocks (one block definition for
    blocks, anchors, nulls and selection).
``calibration null F/mu_0: centre, width``
    ``null.coarse_centre`` (the coarse null centre of ``F/mu_0``; 1 is the
    packed-weight prediction) and ``null.coarse_core_width_factor`` (robust
    core width over the i.i.d. width), read on the calibration block. The
    centre carries a mark for the null's population (``null.null_source``,
    ``null.off_null_like``, ``null.floor_basis``): ``off`` when it is the
    verified transmitter-off population, ``off*`` when that population fails
    the null-like check (a carrier persists after the recorded sign-off),
    ``*`` when it is the bulk of the block's mixture but the ledger records no
    null population for the block (``floor_basis`` ``none``: the bulk's
    centre is the carrier's, not the receiver's null); unmarked when it is the
    bulk of the block's mixture read as a null.
``evaluation null: centre, width``
    ``null_evaluation.coarse_centre`` and
    ``null_evaluation.coarse_core_width_factor`` with the same marks.
``drift: centre [dB], width ratio``
    ``10 log10(null_evaluation.coarse_centre / null.coarse_centre)`` and
    ``null_evaluation.coarse_core_width_factor / null.coarse_core_width_factor``
    (derived). Defined only when each block's null is read from that block's
    own frames (``null.coarse_frames`` equals ``blocks.calibration_frames``
    and ``null_evaluation.coarse_frames`` equals
    ``blocks.evaluation_frames``); where the calibration null is an off
    population outside the block (channel 35: the archive's verified off era,
    off through 2021-10) no between-block drift exists and the cells are
    dashed.
``finite-estimate rate: cal., eval.``
    ``blocks.calibration_finite_estimate_rate`` and
    ``blocks.evaluation_finite_estimate_rate``: the fraction of the block's
    frames with a finite pilot-inferred shelf estimate.
``flag rate: cal., eval.``
    ``blocks.calibration_flag_rate`` and ``blocks.evaluation_flag_rate``: the
    fraction of the block's frames the survey flag rejects (``F > mu_0``).
    The product's shelf estimate is finite exactly where the survey flag is
    set, so the two rates coincide by construction; the notes say when they
    do.
``diagnostic replay (eval.): f q16--q84, kept``
    ``selection.masked_fraction_evaluation_q16``--``q84``, the acquisition
    block-bootstrap 16--84% interval of the masked fraction when the
    diagnostic point is replayed on the evaluation block, and
    ``selection.kept_evaluation``, the frames that replay keeps. When the
    replay exists (``selection.masked_fraction_evaluation`` finite) but no
    interval was formed (``selection.bootstrap_blocks_evaluation`` below the
    minimum) the cell prints the point value followed by ``[--]``. The two
    bounds are separate math cells joined by a text-mode en dash (``--`` inside
    math mode would print as two minus signs). Both cells
    are the dash when no replay exists (``selection.status`` ``refused``: the
    floor is refused and nothing was replayed). A replay that kept no frame
    prints its masked fraction of 1 and ``kept`` 0.

Numbers: ``ch05.blocked_evaluation.<column>.chNN`` for every printed cell
(``calibration_first_month``, ``calibration_last_month``,
``calibration_frames``, the evaluation counterparts,
``frames_without_time_excluded``, ``split_status`` (text, when marked),
``calibration_centre``, ``calibration_width_factor``,
``calibration_null_source`` (text, with the mark as a rendering), the
evaluation counterparts, ``centre_drift_db`` and ``width_factor_ratio``
(status ``derived``), ``calibration_finite_estimate_rate``,
``calibration_flag_rate`` and the evaluation counterparts,
``masked_fraction_evaluation``, ``masked_fraction_evaluation_q16``/``_q84``,
``kept_evaluation``), and the band-level counts
``ch05.blocked_evaluation.n_channels``, ``n_split_supported``,
``n_channels_off_population``, ``n_channels_no_null_population``,
``n_channels_drift_defined``, ``n_channels_replayed``,
``n_channels_no_replay``, ``frames_without_time_excluded_total``.
"""
from __future__ import annotations

import math
from collections import Counter

from .core import DASH, Channel, Fragment, Run, booktabs, fmt, fmt_int, fmt_month, fmt_range, tex

NAME = "blocked_evaluation"
LABEL = "tab:estimator:blocked"
KEY = "ch05.blocked_evaluation"

OFF_SOURCE_PREFIX = "verified transmitter-off era"
BULK = "bulk"                               # the bulk of the block's mixture, read as a null
BULK_NO_NULL = "bulk (no null population)"  # the bulk of the mixture where the ledger records no null population
OFF = "off"                                 # the verified transmitter-off population, null-like
OFF_NOT_NULL_LIKE = "off (not null-like)"   # the verified off population that fails the null-like check
MARKS = {BULK: "", BULK_NO_NULL: r"^{\ast}", OFF: r"^{\mathrm{off}}", OFF_NOT_NULL_LIKE: r"^{\mathrm{off}\ast}"}
SPLIT_MARK = r"^{\ddagger}"
_STATUS_TEXT = {"supported": "supported", "insufficient_support": "insufficient", "empty": "empty"}

HEADER = ["ch", "months", "frames", "months", "frames", "untimed", "centre", "width", "centre", "width",
          "centre [dB]", "width ratio", "cal.", "eval.", "cal.", "eval.", r"$f$ q16--q84", "kept"]
GROUPS = [("", 1), ("calibration block", 2), ("evaluation block", 2), ("excluded", 1),
          (r"calibration null $F/\mu_0$", 2), ("evaluation null", 2), ("drift", 2), ("finite-estimate rate", 2),
          ("flag rate", 2), ("diagnostic replay (eval.)", 2)]
ALIGN = "lrrrrrrrrrrrrrrrcr"
BLOCKS = ("calibration", "evaluation")
NULL_SECTIONS = {"calibration": "null", "evaluation": "null_evaluation"}
SHORT = {"calibration": "cal", "evaluation": "eval"}


# ------------------------------------------------------------------ helpers
def _finite(value) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _decimals(text: str) -> int:
    return len(text.split(".")[1]) if "." in text else 0


def _math(text: str) -> str:
    return text if text == DASH else f"${text}$"


def drift_db(calibration_centre, evaluation_centre) -> float:
    """``10 log10`` of the evaluation-over-calibration centre ratio; NaN when either is absent or non-positive."""
    if not (_finite(calibration_centre) and _finite(evaluation_centre)):
        return math.nan
    a, b = float(calibration_centre), float(evaluation_centre)
    if a <= 0 or b <= 0:
        return math.nan
    return 10.0 * math.log10(b / a)


def width_ratio(calibration_width, evaluation_width) -> float:
    if not (_finite(calibration_width) and _finite(evaluation_width)) or float(calibration_width) <= 0:
        return math.nan
    return float(evaluation_width) / float(calibration_width)


def null_population(section) -> str:
    """Which population a block's coarse null describes: ``off``, ``off (not null-like)``, ``bulk`` or
    ``bulk (no null population)`` (``null_source``, ``off_null_like``, ``floor_basis``); empty when the section is absent."""
    if not section:
        return ""
    source = str(section.get("null_source") or "")
    if source.startswith(OFF_SOURCE_PREFIX):
        if section.get("off_null_like") is False or "not null-like" in source:
            return OFF_NOT_NULL_LIKE
        return OFF
    if str(section.get("floor_basis") or "") == "none":
        return BULK_NO_NULL
    return BULK


def own_frames(ch: Channel, block: str) -> bool:
    """Whether the block's coarse null is read from the block's own frames (``coarse_frames`` equals the block's frames)."""
    frames, null_frames = ch.blocks.get(f"{block}_frames"), ch.section(NULL_SECTIONS[block]).get("coarse_frames")
    return _finite(frames) and _finite(null_frames) and int(frames) == int(null_frames)


def drift_defined(ch: Channel) -> bool:
    """A between-block drift exists when each block's null is that block's own frames."""
    return all(own_frames(ch, block) for block in BLOCKS)


def replay_exists(ch: Channel) -> bool:
    """Whether a point was replayed on the evaluation block (``selection.masked_fraction_evaluation`` finite)."""
    return _finite(ch.selection.get("masked_fraction_evaluation"))


def group_header(groups) -> str:
    """The first header row (``\\multicolumn`` group titles) and its ``\\cmidrule`` line."""
    cells, rules, start = [], [], 1
    for title, span in groups:
        cells.append(f"\\multicolumn{{{span}}}{{c}}{{{title}}}" if title else ("" if span == 1 else f"\\multicolumn{{{span}}}{{c}}{{}}"))
        if title:
            rules.append(f"\\cmidrule(lr){{{start}-{start + span - 1}}}")
        start += span
    return " & ".join(cells) + " \\\\\n" + " ".join(rules) + "\n"


# ------------------------------------------------------------------ one row
def _row(ch: Channel, frag: Fragment) -> list[str]:
    n = ch.channel
    row = {"channel": n}
    b, sel = ch.blocks, ch.selection
    cells = []

    def add(column, value, *, precision=None, kind="float", status="measured", renderings=()):
        frag.add(f"{KEY}.{column}.ch{n:02d}", value, precision=precision, kind=kind, status=status,
                 renderings=renderings, row=row, column=column)

    # the channel, marked when the split is not supported
    status = b.get("status")
    if status and str(status) != "supported":
        printed = _STATUS_TEXT.get(str(status), str(status))
        cells.append(f"{n}${SPLIT_MARK}$")
        add("split_status", str(status), kind="text", renderings=(printed, str(status)))
    else:
        cells.append(str(n))

    # the two blocks: month span and frames
    for block in BLOCKS:
        first, last = b.get(f"{block}_first_month"), b.get(f"{block}_last_month")
        if first and last:
            cells.append(f"{tex(fmt_month(first))}--{tex(fmt_month(last))}")
            add(f"{block}_first_month", str(first), kind="text", renderings=(str(first),))
            add(f"{block}_last_month", str(last), kind="text", renderings=(str(last),))
        else:
            cells.append(DASH)
        frames = b.get(f"{block}_frames")
        if _finite(frames) and int(frames) > 0:
            cells.append(_math(fmt_int(frames)))
            add(f"{block}_frames", int(frames), kind="int", precision=0)
        else:
            cells.append(DASH)

    # frames without a recorded time, excluded from both blocks
    untimed = b.get("frames_without_time_excluded")
    if ch.has("blocks") and _finite(untimed):
        cells.append(_math(fmt_int(untimed)))
        add("frames_without_time_excluded", int(untimed), kind="int", precision=0)
    else:
        cells.append(DASH)

    # the null on each block, its centre marked for the population it describes
    for block in BLOCKS:
        sec = ch.section(NULL_SECTIONS[block])
        population = null_population(sec)
        centre, width = sec.get("coarse_centre"), sec.get("coarse_core_width_factor")
        if _finite(centre):
            text = fmt(centre, 4, sig=True)
            cells.append(_math(text + MARKS[population]))
            add(f"{block}_centre", float(centre), precision=_decimals(text))
            add(f"{block}_null_source", str(sec.get("null_source") or ""), kind="text",
                renderings=(population, MARKS[population]) if MARKS[population] else (population,))
        else:
            cells.append(DASH)
        if _finite(width):
            text = fmt_int(width) if float(width) >= 1000 else fmt(width, 3, sig=True)
            cells.append(_math(text))
            add(f"{block}_width_factor", float(width), precision=_decimals(text))
        else:
            cells.append(DASH)

    # the drift between blocks (undefined unless each null is the block's own frames)
    null, null_eval = ch.null, ch.section("null_evaluation")
    defined = drift_defined(ch)
    d_db = drift_db(null.get("coarse_centre"), null_eval.get("coarse_centre")) if defined else math.nan
    ratio = width_ratio(null.get("coarse_core_width_factor"), null_eval.get("coarse_core_width_factor")) if defined else math.nan
    if _finite(d_db):
        cells.append(_math(fmt(d_db, 3, plus=True)))
        add("centre_drift_db", d_db, precision=3, status="derived")
    else:
        cells.append(DASH)
    if _finite(ratio):
        cells.append(_math(fmt(ratio, 2)))
        add("width_factor_ratio", ratio, precision=2, status="derived")
    else:
        cells.append(DASH)

    # finite-estimate rate and survey flag rate on each block
    for rate_key in ("finite_estimate_rate", "flag_rate"):
        for block in BLOCKS:
            rate = b.get(f"{block}_{rate_key}")
            if _finite(rate):
                cells.append(_math(fmt(rate, 3)))
                add(f"{block}_{rate_key}", float(rate), precision=3)
            else:
                cells.append(DASH)

    # the diagnostic replay on the evaluation block: masked-fraction interval and kept frames
    if replay_exists(ch):
        value = float(sel.get("masked_fraction_evaluation"))
        q16, q84 = sel.get("masked_fraction_evaluation_q16"), sel.get("masked_fraction_evaluation_q84")
        add("masked_fraction_evaluation", value, precision=4)
        if _finite(q16) and _finite(q84):
            cells.append(f"${fmt(q16, 4)}$--${fmt(q84, 4)}$")      # the en dash in text mode, the bounds in math
            add("masked_fraction_evaluation_q16", float(q16), precision=4, renderings=(fmt_range(q16, q84, 4),))
            add("masked_fraction_evaluation_q84", float(q84), precision=4, renderings=(fmt_range(q16, q84, 4),))
        else:
            cells.append(f"${fmt(value, 4)}$ [{DASH}]")
        kept = sel.get("kept_evaluation")
        if _finite(kept):
            cells.append(_math(fmt_int(kept)))
            add("kept_evaluation", int(kept), kind="int", precision=0)
        else:
            cells.append(DASH)
    else:
        cells += [DASH, DASH]
    return cells


# ------------------------------------------------------------------ notes and counts
def _chlist(channels) -> str:
    return ", ".join(str(c) for c in channels)


def _summary(run: Run, frag: Fragment) -> list[str]:
    chans = run.channels
    total = len(chans)
    notes = []

    # the split and the untimed frames
    no_blocks = [c.channel for c in chans if not c.has("blocks")]
    if no_blocks:
        notes.append(f"blocks section absent on ch {_chlist(no_blocks)}: block, untimed and rate cells dashed")
    unsupported = [(c.channel, c.blocks.get("status"), c.blocks.get("detail", "")) for c in chans
                   if c.has("blocks") and str(c.blocks.get("status")) != "supported"]
    supported = total - len(no_blocks) - len(unsupported)
    if unsupported:
        notes.append("ddagger: split not supported on " + "; ".join(f"ch{n} {s}: {d}" if d else f"ch{n} {s}" for n, s, d in unsupported)
                     + " (blocks.status, blocks.detail)")
    else:
        notes.append(f"block split supported on all {supported} channels with a blocks section (blocks.status); chronological, "
                     "whole acquisitions, balanced frame counts")
    untimed = [(c.channel, int(c.blocks["frames_without_time_excluded"])) for c in chans
               if c.has("blocks") and _finite(c.blocks.get("frames_without_time_excluded"))]
    untimed_total = sum(k for _, k in untimed)
    nonzero = [(n, k) for n, k in untimed if k]
    notes.append(f"untimed: {untimed_total} frames without a recorded time excluded from both blocks on "
                 f"{len(nonzero)} of {total} channels (blocks.frames_without_time_excluded"
                 + (": " + ", ".join(f"ch{n} {k}" for n, k in nonzero) if nonzero else "") + ")")

    # the null populations
    no_eval = [c.channel for c in chans if not c.has("null_evaluation")]
    if no_eval:
        notes.append(f"null_evaluation absent on ch {_chlist(no_eval)}: evaluation null and drift dashed")
    populations = {block: Counter() for block in BLOCKS}
    by_population = {kind: set() for kind in MARKS}
    for c in chans:
        for block in BLOCKS:
            kind = null_population(c.section(NULL_SECTIONS[block]))
            if kind:
                populations[block][kind] += 1
                by_population[kind].add(c.channel)
    off_channels = sorted(by_population[OFF] | by_population[OFF_NOT_NULL_LIKE])
    if off_channels:
        both = sorted(c.channel for c in chans if all(null_population(c.section(NULL_SECTIONS[b])) in (OFF, OFF_NOT_NULL_LIKE) for b in BLOCKS))
        one = [n for n in off_channels if n not in both]
        text = (f"off: the coarse null is the verified transmitter-off population of the block's frames (null.null_source) "
                f"on ch {_chlist(both)}" if both else "off: the coarse null is the verified transmitter-off population")
        if one:
            text += "; on ch " + ", ".join(f"{n} ({', '.join(b for b in BLOCKS if null_population(run.by_channel()[n].section(NULL_SECTIONS[b])) in (OFF, OFF_NOT_NULL_LIKE))} block only)" for n in one)
        notes.append(text)
    not_null_like = sorted(by_population[OFF_NOT_NULL_LIKE])
    if not_null_like:
        notes.append(f"off*: on ch {_chlist(not_null_like)} the off population fails the null-like check (null.off_null_like false: "
                     "a carrier persists after the recorded sign-off; centre beyond 2% of mu_0 or width factor above 5)")
    bulk = sorted(by_population[BULK] | by_population[BULK_NO_NULL])
    if bulk:
        notes.append(f"{len(bulk)} of {total} channels read the null from the bulk of each block's mixture on at least one block "
                     "(null.mixture_declared): centre = median of the bulk, width = left-side core scale about it")
    no_null = sorted(by_population[BULK_NO_NULL])
    if no_null:
        blocks_text = ", ".join(f"ch{n} ({'+'.join(SHORT[b] for b in BLOCKS if null_population(run.by_channel()[n].section(NULL_SECTIONS[b])) == BULK_NO_NULL)})" for n in no_null)
        notes.append(f"*: the ledger records no null population for the block (null.floor_basis none: the bulk's centre is beyond "
                     f"0.1 of mu_0, the carrier's bulk rather than the receiver's null) on {blocks_text}; the centre and width "
                     "describe the detections' bulk and the drift compares those bulks between blocks")

    # the drift
    own = [c for c in chans if drift_defined(c)]
    defined = [c.channel for c in own if _finite(drift_db(c.null.get("coarse_centre"), c.section("null_evaluation").get("coarse_centre")))]
    not_own = [c.channel for c in chans if c.has("blocks") and c.has("null_evaluation") and not drift_defined(c)]
    if not_own:
        detail = []
        for n in not_own:
            c = run.by_channel()[n]
            for block in BLOCKS:
                if not own_frames(c, block):
                    sec = c.section(NULL_SECTIONS[block])
                    text = (f"ch{n} {block} null {fmt_int(sec.get('coarse_frames'), thousands=False)} frames against "
                            f"{fmt_int(c.blocks.get(f'{block}_frames'), thousands=False)} in the block")
                    if null_population(sec) in (OFF, OFF_NOT_NULL_LIKE) and c.era.get("off_through"):
                        text += f" (the archive's verified off population, off through {c.era['off_through']})"
                    detail.append(text)
        notes.append(f"drift dashed on ch {_chlist(not_own)}: a block's null is not that block's own frames "
                     f"(null.coarse_frames against blocks.*_frames: {'; '.join(detail)}), so no between-block drift exists")
    undefined = [c.channel for c in own if c.channel not in defined]
    if undefined:
        notes.append(f"centre drift undefined (absent or non-positive centre) on ch {_chlist(undefined)}")
    notes.append(f"drift: centre in dB is 10 log10 of the evaluation-over-calibration coarse centre, width ratio the evaluation-over-"
                 f"calibration core width factor, printed on {len(defined)} of {total} channels (each block's null its own frames)")

    # the rates
    rated = [c for c in chans if all(_finite(c.blocks.get(f"{b}_{k}")) for b in BLOCKS for k in ("finite_estimate_rate", "flag_rate"))]
    same = [c.channel for c in rated if all(math.isclose(float(c.blocks[f"{b}_finite_estimate_rate"]), float(c.blocks[f"{b}_flag_rate"]),
                                                          rel_tol=0, abs_tol=5e-4) for b in BLOCKS)]
    if rated and len(same) == len(rated):
        notes.append(f"the finite-estimate rate equals the survey flag rate on every channel ({len(rated)}): the product's shelf "
                     "estimate is finite exactly where F > mu_0, the frames the survey flag rejects")
    elif rated:
        differ = [c.channel for c in rated if c.channel not in same]
        notes.append(f"the finite-estimate rate differs from the survey flag rate on ch {_chlist(differ)}")

    # the replay
    replayed = [c.channel for c in chans if replay_exists(c)]
    no_replay = [c for c in chans if not replay_exists(c)]
    statuses = Counter(str(c.selection.get("status") or "") for c in chans if c.has("selection"))
    claims = Counter(str(c.selection.get("claim_status") or "") for c in chans if replay_exists(c))
    selected = [c.channel for c in chans if c.selection.get("rho") is not None]
    notes.append("diagnostic replay: the interval is the acquisition block-bootstrap 16--84% of the masked fraction when the "
                 "least-residual point of the calibration surface (selection.diagnostic_rho/eta, selection.diagnostic_basis) is "
                 "replayed on the evaluation block, and kept is the frames that replay keeps (selection.kept_evaluation); a "
                 "diagnostic, not a selected operating point"
                 + (f" (selected points on ch {_chlist(selected)})" if selected else
                    f": no channel has one (selection.status {', '.join(f'{k}: {v}' for k, v in sorted(statuses.items()))}"
                    + (f"; claim_status of the replayed channels {', '.join(f'{k}: {v}' for k, v in sorted(claims.items()))}" if claims else "") + ")"))
    if no_replay:
        reasons = Counter(str(c.selection.get("refusal") or ("absent" if not c.has("selection") else c.selection.get("status") or "")) for c in no_replay)
        notes.append(f"replay cells dashed on ch {_chlist(c.channel for c in no_replay)}: no evaluation replay exists "
                     f"(selection.masked_fraction_evaluation null; " + "; ".join(f"{k} ({v})" for k, v in reasons.most_common()) + ")")
    no_interval = [c.channel for c in chans if replay_exists(c) and not (_finite(c.selection.get("masked_fraction_evaluation_q16"))
                                                                          and _finite(c.selection.get("masked_fraction_evaluation_q84")))]
    if no_interval:
        notes.append(f"replay on ch {_chlist(no_interval)} has no bootstrap interval (selection.bootstrap_blocks_evaluation below the "
                     "minimum): the point value prints with [--]")
    kept_none = [c.channel for c in chans if replay_exists(c) and _finite(c.selection.get("kept_evaluation")) and int(c.selection["kept_evaluation"]) == 0]
    if kept_none:
        notes.append(f"the replay kept no frame on ch {_chlist(kept_none)} (selection.kept_evaluation 0): the masked fraction is 1 "
                     "and its interval degenerate")
    refusals = Counter(str(c.selection.get("refusal") or "").split(":")[0] for c in chans if c.selection.get("refusal"))
    if refusals:
        notes.append("selector refusals (selection.refusal): " + "; ".join(f"{k} ({v})" for k, v in refusals.most_common()))

    # band-level counts for the text
    counts = {"n_channels": total, "n_split_supported": supported,
              "n_channels_off_population": len(off_channels), "n_channels_no_null_population": len(no_null),
              "n_channels_drift_defined": len(defined), "n_channels_replayed": len(replayed),
              "n_channels_no_replay": len(no_replay), "frames_without_time_excluded_total": untimed_total}
    for key, value in counts.items():
        frag.add(f"{KEY}.{key}", int(value), kind="int", precision=0, column=key)
    return notes


def build(run: Run) -> Fragment:
    frag = Fragment(NAME, LABEL, "")
    rows = [_row(c, frag) for c in run.channels]
    table = booktabs(HEADER, rows, ALIGN)
    frag.tex = table.replace("\\toprule\n", "\\toprule\n" + group_header(GROUPS), 1)
    frag.inputs = list(run.inputs())
    frag.notes = _summary(run, frag)
    return frag


__all__ = ["NAME", "LABEL", "KEY", "HEADER", "GROUPS", "ALIGN", "MARKS", "build", "drift_db", "width_ratio",
           "null_population", "own_frames", "drift_defined", "replay_exists", "group_header"]
