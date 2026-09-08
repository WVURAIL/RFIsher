"""The incumbent flaggers across the band, as chapter 9's flagger table.

The stub asks for a compact survey summary rather than a 23-row expansion:
the median and range of each flagger's suppression and masked fraction over
the current eras, with the pilot proxy as the row that matters, and the
per-channel values in the appendix ledger. Both fragments are here:
``build`` is the chapter's summary, ``build_ledger`` the per-channel table.

Rows, in the order the chapter argues them: keep everything (the reference
every suppression is measured against, so its own row is zero by
construction); the two incumbents; the pilot proxy at the survey flag, which
is the rule the kernel actually runs; and the pilot proxy at the point the
selection reports --- on this run a declared diagnostic, since no channel has
a selected point, and the column head says so.

Columns. Masked fraction and suppression, each as a median over the channels
the flagger is defined on with the range beside it, and the count of channels
that contributed. A flagger that keeps nothing on a channel has no surviving
shelf, so that channel is excluded from its median and the count says how
many did contribute.

Ledger keys: ``flaggers.{keep,mad,sk,flag,point}_{masked_fraction,suppression_db,
retained_shelf_db,kept,status}``, ``flaggers.scored_frames``,
``flaggers.duty_cycle``, ``flaggers.blocks``. Numbers: ``ch09.flaggers.*``.
"""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np

from .core import DASH, Fragment, Run, booktabs, fmt, fmt_int

NAME = "flagger_survey"
LABEL = "tab:tolerance:flaggers"
LEDGER_NAME = "flagger_survey_ledger"
LEDGER_LABEL = "tab:archive:flaggers"
ROWS = (("keep", "keep everything"), ("mad", r"MAD $1.8\times$ within acquisition"),
        ("sk", r"SK $3\sigma$ within acquisition"), ("flag", "pilot proxy, survey flag"),
        ("point", "pilot proxy, reported point"))


def _num(value) -> float:
    try:
        return float(value) if value is not None else math.nan
    except (TypeError, ValueError):
        return math.nan


def _summary(values: Sequence[float]) -> tuple[float, float, float, int]:
    finite = np.array([v for v in values if math.isfinite(v)], dtype=float)
    if finite.size == 0:
        return math.nan, math.nan, math.nan, 0
    return float(np.median(finite)), float(finite.min()), float(finite.max()), int(finite.size)


def build(run: Run) -> Fragment:
    frag = Fragment(NAME, LABEL, "")
    present = [c for c in run.channels if c.has("flaggers")]
    header = ["flagger", "channels", "masked fraction $f$", "suppression [dB]"]
    rows = []
    for tag, label in ROWS:
        fractions = [_num(c.section("flaggers").get(f"{tag}_masked_fraction")) for c in present]
        suppressions = [_num(c.section("flaggers").get(f"{tag}_suppression_db")) for c in present
                        if str(c.section("flaggers").get(f"{tag}_status") or "") == "measured"]
        f_med, f_lo, f_hi, f_n = _summary(fractions)
        s_med, s_lo, s_hi, s_n = _summary(suppressions)
        rows.append([label, str(f_n),
                     f"{fmt(f_med, 3)} ({fmt(f_lo, 3)}--{fmt(f_hi, 3)})" if f_n else DASH,
                     f"{fmt(s_med, 2)} ({fmt(s_lo, 2)}--{fmt(s_hi, 2)})" if s_n else DASH])
        for name, (med, lo, hi, n), precision in (("masked_fraction", (f_med, f_lo, f_hi, f_n), 3),
                                                  ("suppression_db", (s_med, s_lo, s_hi, s_n), 2)):
            frag.add(f"ch09.flaggers.{tag}.{name}.median", med, precision=precision, row={"flagger": label}, column=name)
            frag.add(f"ch09.flaggers.{tag}.{name}.min", lo, precision=precision, row={"flagger": label}, column=name)
            frag.add(f"ch09.flaggers.{tag}.{name}.max", hi, precision=precision, row={"flagger": label}, column=name)
            frag.add(f"ch09.flaggers.{tag}.{name}.channels", n, kind="int", row={"flagger": label}, column="channels")
    frag.tex = booktabs(header, rows, "lrll")
    frag.add("ch09.flaggers.channels", len(present), kind="int", column="channels")
    scored_counts = [_num(c.section("flaggers").get("scored_frames")) for c in present]
    scored = sum(int(value) for value in scored_counts if math.isfinite(value))
    frag.add("ch09.flaggers.scored_frames", scored, kind="int", column="frames")
    missing_counts = sum(not math.isfinite(value) for value in scored_counts)
    if missing_counts:
        frag.notes.append(f"{missing_counts} channels have no recorded scored-frame count; "
                          "the frame total includes only the recorded counts")
    frag.notes.append(
        f"summarised over the {len(present)} channels with a flagger comparison, on {fmt_int(scored)} frames of their "
        "current eras: the era's frames restricted to acquisitions long enough for a block statistic, so every flagger "
        "sees the same frames")
    frag.notes.append("suppression is the keep-everything mean over the row's, in dB, so the keep-everything row is zero "
                      "by construction; a channel where a flagger keeps nothing contributes no suppression and the "
                      "channel count says how many did")
    if any(str(c.section("flaggers").get("point_status") or "") for c in present):
        frag.notes.append("the reported point is the least-residual point of the calibration surface, declared a "
                          "diagnostic: no channel has a selected point on this run")
    return frag


def build_ledger(run: Run) -> Fragment:
    frag = Fragment(LEDGER_NAME, LEDGER_LABEL, "")
    header = ["ch", "scored", "blocks", "duty", *[f"$f$ {t}" for t, _ in ROWS], *[f"dB {t}" for t, _ in ROWS]]
    rows = []
    for c in run.channels:
        s = c.section("flaggers")
        if not s:
            rows.append([str(c.channel), *([DASH] * (len(header) - 1))])
            continue
        cells = [str(c.channel), fmt_int(_num(s.get("scored_frames"))), fmt_int(_num(s.get("blocks"))),
                 fmt(_num(s.get("duty_cycle")), 3)]
        cells += [fmt(_num(s.get(f"{t}_masked_fraction")), 3) for t, _ in ROWS]
        cells += [fmt(_num(s.get(f"{t}_suppression_db")), 2) for t, _ in ROWS]
        rows.append(cells)
        for t, _ in ROWS:
            frag.add(f"appC.flaggers.{t}.masked_fraction.ch{c.channel:02d}", _num(s.get(f"{t}_masked_fraction")),
                     precision=3, row={"channel": c.channel}, column=f"f {t}")
            frag.add(f"appC.flaggers.{t}.suppression_db.ch{c.channel:02d}", _num(s.get(f"{t}_suppression_db")),
                     precision=2, row={"channel": c.channel}, column=f"dB {t}")
        scored = _num(s.get("scored_frames"))
        frag.add(f"appC.flaggers.scored_frames.ch{c.channel:02d}", int(scored) if math.isfinite(scored) else math.nan, kind="int",
                 row={"channel": c.channel}, column="scored")
        frag.add(f"appC.flaggers.duty_cycle.ch{c.channel:02d}", _num(s.get("duty_cycle")), precision=3,
                 row={"channel": c.channel}, column="duty")
        note = str(s.get("notes") or "")
        if note:
            frag.notes.append(f"channel {c.channel}: {note}")
    frag.tex = booktabs(header, rows, "l" + "r" * (len(header) - 1))
    frag.notes.append("the per-channel values behind the chapter's summary; duty is the fraction of the scored frames "
                      "the survey flag rejects")
    return frag


BUILDERS = (build, build_ledger)
