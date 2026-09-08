"""``tab:archive:drift``: what the within-era drift screen measured, and where
its message comes from.

Appendix~C says the screen refused every channel it reached and quotes the
behaviour as prose. This is the table behind that sentence. One row per
channel per kept-fraction probe: the rule that produced the stated reason, the
candidate the per-half retained-frame floor fires on, the frames each calendar
half carries, the calendar support against the register's minimums, and the
worst early/late cost and systematic-residual ratios the run's own diagnostic
(:func:`..selection.drift_diagnostic`) measured over the candidates that keep
at least the stated fraction of *each* half.

Two rules, one message. :func:`rfisher.preparation.assess_histogram_stability`
returns ``refused_insufficient_support`` from two different places. It first
tests calendar support --- at least ``era.minimum_observed_months`` observed
months and ``era.minimum_span_days`` elapsed days in each half --- and returns
immediately if either half falls short, before it has looked at a single
candidate. Only if both halves pass does it sweep the candidate surface, where
it refuses at the first pair whose *pooled* kept count reaches
``MIN_RETAINED_FRAMES`` while one half is below the per-half floor. The status
string is the same either way, so the status alone cannot say which happened;
the reason string can, and this table splits the channels on it.

Why that matters. Where the retention rule fires, the reason is an artefact of
where the sweep crosses the pooled floor rather than a statement about drift:
the sweep meets that band at a candidate keeping a few tenths of a percent of
the block, and refuses there whatever the rest of the surface does. The
verdict is still the right one, but it has to be defended on the ratios, not
on the message --- which is what the probe rows are for. Where the calendar
rule fires the reason is a measurement (a half with three observed months is a
half with three observed months) and nothing about it is an artefact. The
fragment's notes report which channels of the run at hand fall in each group
rather than asserting one story for all of them.

The probes. Every candidate the diagnostic scores already keeps at least the
per-half floor in each half, so ``kept >= 0`` is not "all candidates" but "all
supported candidates"; the larger fractions ask for the drift a point holding
a real share of each half would see. The limits the ratios are measured
against (``stability.maximum_cost_ratio`` 1.05 and
``stability.maximum_systematic_residual_ratio`` 1.10) are the provisional
values of :mod:`..selection`; the ledger does not carry them, so the fragment
quotes the module and says so. The retained-frame floor and both calendar
minimums are quoted from the run's own reason strings, which name them.

Numbers: ``appC.drift.<column>.chNN`` per channel, ``appC.drift.<column>.
<probe>.chNN`` per probe row, and ``appC.drift.<name>`` for the run-level
counts and limits.

What this table does not carry. The screen is a deterministic comparison of
point estimates, not an equivalence test, and the block-resampled uncertainty
that an operational claim would also need
(:class:`rfisher.preparation.BlockStabilityAssessment`) is not recorded in the
ledger. A channel whose selector refused before a threshold family existed
never reached the screen at all, and prints dashes.
"""
from __future__ import annotations

import math
import re

from ..selection import PROVISIONAL_MAX_COST_RATIO, PROVISIONAL_MAX_SYSTEMATIC_RATIO
from . import core
from .core import DASH, Channel, Fragment, Run

NAME = "drift_screen"
LABEL = "tab:archive:drift"
KEY = "appC.drift"
SECTION = "selection"

HEADER = ("ch", "rule", r"refused at $\eta$ (e/l)", "frames e/l", "calendar", r"kept $\ge$", "$C$",
          r"$r_{\rm sys}$")
ALIGN = "lllllrrr"
CAPTION = (
    "The within-era drift screen, channel by channel, behind the prose of this appendix. Throughout, "
    "\\emph{e} and \\emph{l} are the early and late halves of the calibration block, split at its "
    "calendar midpoint. \\emph{rule} is which of the screen's two refusal rules produced the stated "
    "reason: \\emph{calendar}, the observed-month and elapsed-day minimums each half must meet, tested "
    "before any candidate is examined; \\emph{retention}, the per-half retained-frame floor, tested "
    "along the candidate sweep. \\emph{refused at} is the candidate the retention rule fires on, with "
    "the frames it keeps in each half. The rule fires on the earlier half alone, not on the sum, "
    "is why the two are always below the per-half floor there. \\emph{calendar} is the half that fell "
    "short and its support against the minimum it needed, or \\emph{passed} where both halves met both "
    "minimums. The last three columns give one row per probe: over the candidates keeping at least "
    "that fraction of each half, the worst early/late cost ratio $C$ and systematic-residual ratio "
    "$r_{\\rm sys}$ the run's diagnostic measured. The row labelled \\emph{all} is every candidate the "
    "screen's own per-half floor admits, not every candidate. The limits those ratios are judged "
    f"against are {PROVISIONAL_MAX_COST_RATIO:.2f} and {PROVISIONAL_MAX_SYSTEMATIC_RATIO:.2f}, so a "
    "channel is outside on the numbers wherever a printed ratio exceeds them.")

# the ledger names each probe by its fraction with the point spelled 'p': drift_max_cost_ratio_at_0p05
PROBE_KEY = re.compile(r"^drift_max_cost_ratio_at_(?P<tag>[0-9p]+)$")
# the two rules' reason strings, verbatim from rfisher.preparation.assess_histogram_stability
RETENTION_REASON = re.compile(
    r"candidate rho=(?P<rho>\d+), eta=(?P<eta>[\d.eE+-]+) retains fewer than (?P<floor>\d+) frames in one era half")
CALENDAR_MONTHS = re.compile(r"(?P<half>early|late) half has (?P<value>\d+) observed months?; need (?P<need>\d+)")
CALENDAR_DAYS = re.compile(r"(?P<half>early|late) half spans (?P<value>[\d.]+) days; need (?P<need>[\d.]+)")

RETENTION, CALENDAR, PASSED, NOT_RUN, OTHER = "retention", "calendar", "passed", "not run", "other"


def probe_label(fraction: float) -> str:
    """The probe column's row label: the zero probe is every *supported* candidate, so it says so."""
    return "all" if fraction <= 0.0 else f"${core.fmt(fraction, 2)}$"


def _finite(value) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _num(value):
    return float(value) if _finite(value) else None


def _int(value):
    return int(value) if _finite(value) else None


def _math(text: str) -> str:
    return DASH if text == DASH else f"${text}$"


def probes(channels) -> tuple[tuple[str, float], ...]:
    """``(tag, fraction)`` for every kept-fraction probe the run recorded, ascending.

    The probe set is read from the ledger rather than from
    ``..selection.DRIFT_KEPT_FRACTIONS`` so the table describes the run in
    front of it: a run made before a fraction was added carries fewer probes,
    and printing a column the run never measured would be a blank claim.
    """
    tags: dict[str, float] = {}
    for c in channels:
        for key in c.section(SECTION):
            m = PROBE_KEY.match(key)
            if m:
                tags[m["tag"]] = float(m["tag"].replace("p", "."))
    return tuple(sorted(tags.items(), key=lambda item: item[1]))


def stated_rule(section) -> str:
    """Which rule produced the screen's stated reason on this channel.

    The status is the same string for both refusal rules, so the reason is the
    only record of which one fired; ``not run`` is the case where the selector
    refused before a threshold family existed and the screen never ran.
    """
    status = str(section.get("stability_status") or "")
    reason = str(section.get("stability_reason") or "")
    if not status:
        return NOT_RUN
    if status == "passed":
        return PASSED
    if RETENTION_REASON.search(reason):
        return RETENTION
    if CALENDAR_MONTHS.search(reason) or CALENDAR_DAYS.search(reason):
        return CALENDAR
    return OTHER


def calendar_support(section) -> dict:
    """The calendar support the reason string records, as ``{half, unit, value, need}``.

    Only the half that failed leaves its months or days in the record: the
    gate returns on the first shortfall and the run serialises no per-half
    month or day count of its own, so a channel that passed the gate is known
    to have met both minimums in both halves without the counts being
    recoverable from the ledger.
    """
    reason = str(section.get("stability_reason") or "")
    for pattern, unit in ((CALENDAR_MONTHS, "months"), (CALENDAR_DAYS, "days")):
        m = pattern.search(reason)
        if m:
            return {"half": m["half"], "unit": unit, "value": float(m["value"]), "need": float(m["need"])}
    return {}


def refusing_candidate(section) -> dict:
    """The candidate the per-half retention rule fires on, from the run's drift diagnostic.

    ``..selection.drift_diagnostic`` re-walks the same sweep in the same order
    and records the first candidate that trips the rule, so on a channel the
    screen refused there this is the candidate it refused on. On a channel the
    calendar gate stopped first the screen never reached the sweep, and the
    entry is where the retention rule *would* have fired; the row marks it.
    """
    eta, early, late = (_num(section.get("drift_refused_eta")), _int(section.get("drift_refused_early_kept")),
                        _int(section.get("drift_refused_late_kept")))
    if eta is None or early is None or late is None:
        return {}
    return {"rho": _int(section.get("drift_refused_rho")), "eta": eta, "early_kept": early, "late_kept": late,
            "kept_fraction": _num(section.get("drift_refused_kept_fraction"))}


def _calendar_cell(rule: str, support: dict) -> str:
    """``passed``, or the half that fell short with its support against the minimum it needed."""
    if rule == NOT_RUN:
        return DASH
    if not support:
        return "passed"
    unit = "mo" if support["unit"] == "months" else "d"
    return f"{support['half'][0]}: ${core.fmt(support['value'], 0)}<{core.fmt(support['need'], 0)}$~{unit}"


def _channel_rows(c: Channel, frag: Fragment, tags) -> list[list[str]]:
    """One channel: its rule and support once, then a row for each kept-fraction probe."""
    s = c.section(SECTION)
    ch = c.channel
    rule = stated_rule(s)
    support = calendar_support(s)
    candidate = refusing_candidate(s)

    def add(column: str, value, **kw):
        frag.add(f"{KEY}.{column}.ch{ch:02d}", value, row={"channel": ch}, column=column, **kw)

    add("status", str(s.get("stability_status") or "") or "not run", kind="text",
        renderings=(str(s.get("stability_status") or "") or "not run",))
    add("rule", rule, kind="text", renderings=(rule,))
    # the reason verbatim, so the appendix can quote the screen rather than paraphrase it
    reason = str(s.get("stability_reason") or "") or str(s.get("refusal") or "")
    add("reason", reason, kind="text", renderings=(reason,) if reason else ())
    early, late = _int(s.get("drift_early_frames")), _int(s.get("drift_late_frames"))
    for column, value in (("early_frames", early), ("late_frames", late)):
        if value is None:
            add(column, None, kind="text", status="pending", renderings=(DASH,))
        else:
            add(column, value, kind="int")
    if candidate:
        add("refused_eta", candidate["eta"], precision=3)
        add("refused_rho", candidate["rho"], kind="int")
        add("refused_early_kept", candidate["early_kept"], kind="int")
        add("refused_late_kept", candidate["late_kept"], kind="int")
        add("refused_kept_fraction", candidate["kept_fraction"], precision=4)
    if support:
        add("calendar_half", support["half"], kind="text", renderings=(support["half"],))
        add("calendar_" + support["unit"], support["value"], precision=0)
        add("calendar_" + support["unit"] + "_required", support["need"], precision=0)

    candidate_cell = DASH
    if candidate:
        mark = "" if rule == RETENTION else r"$^{\dagger}$"     # the screen stopped before the sweep
        candidate_cell = (f"${core.fmt(candidate['eta'], 3)}$ (${candidate['early_kept']}/"
                          f"{candidate['late_kept']}$){mark}")
    frames_cell = (f"${core.fmt_int(early)}/{core.fmt_int(late)}$" if early is not None and late is not None
                   else DASH)
    head = [str(ch), rule, candidate_cell, frames_cell, _calendar_cell(rule, support)]

    rows = []
    for tag, fraction in tags:
        cost, systematic = (_num(s.get(f"drift_max_cost_ratio_at_{tag}")),
                            _num(s.get(f"drift_max_systematic_ratio_at_{tag}")))
        count = _int(s.get(f"drift_candidates_at_{tag}"))
        row = {"channel": ch, "kept_fraction": fraction}
        for column, value, kw in (("candidates", count, {"kind": "int"}),
                                  ("cost_ratio", cost, {"precision": 3}),
                                  ("systematic_ratio", systematic, {"precision": 3})):
            key = f"{KEY}.{column}.{tag}.ch{ch:02d}"
            if value is None:
                frag.add(key, None, kind="text", status="pending", renderings=(DASH,), row=row, column=column)
            else:
                frag.add(key, value, row=row, column=column, **kw)
        rows.append([probe_label(fraction), _math(core.fmt(cost, 3)), _math(core.fmt(systematic, 3))])
    if not any(row[1] != DASH for row in rows):
        # the channel carries no measured probe at all: one dashed row says so once rather than four times
        rows = [[DASH, DASH, DASH]]
    return [head + rows[0]] + [[""] * len(head) + r for r in rows[1:]]


def _channel_list(channels) -> str:
    return ", ".join(f"ch{c:02d}" for c in sorted(channels)) or "none"


def _exceeding(channels, tag: str, column: str, limit: float) -> list[int]:
    """The channels whose worst ratio at this probe is above the declared limit."""
    out = []
    for c in channels:
        value = _num(c.section(SECTION).get(f"drift_max_{column}_ratio_at_{tag}"))
        if value is not None and value > limit:
            out.append(c.channel)
    return out


def build(run: Run) -> Fragment:
    """``tab:archive:drift``: the drift screen's verdict, its stated reason and the drift it measured."""
    frag = Fragment(NAME, LABEL, "")
    channels = sorted((c for c in run.channels if c.has(SECTION)), key=lambda c: c.channel)
    if not channels:
        frag.tex = ""
        frag.notes.append("no channel carries a selection section: the run refused before selection ran, or it "
                          "predates the section")
        return frag
    tags = probes(channels)
    rows, breaks = [], []
    for c in channels:
        if rows:
            breaks.append(len(rows))
        rows.extend(_channel_rows(c, frag, tags))
    # one row per channel per probe outgrows a page, and a float would drop the tail silently,
    # so the fragment is a longtable carrying its own caption and label (as tab:archive:worlds does)
    frag.tex = core.booktabs(HEADER, rows, ALIGN, midrules=tuple(breaks), longtable=True, caption=CAPTION,
                             label=LABEL)

    by_rule: dict[str, list[int]] = {}
    for c in channels:
        by_rule.setdefault(stated_rule(c.section(SECTION)), []).append(c.channel)
    screened = [c for c in channels if stated_rule(c.section(SECTION)) != NOT_RUN]
    frag.add(f"{KEY}.channels", len(channels), kind="int", column="channels")
    frag.add(f"{KEY}.n_screened", len(screened), kind="int", column="channels")
    for rule in (RETENTION, CALENDAR, PASSED, NOT_RUN, OTHER):
        frag.add(f"{KEY}.n_{rule.replace(' ', '_')}", len(by_rule.get(rule, ())), kind="int",
                 row={"rule": rule}, column="channels")
    frag.add(f"{KEY}.cost_limit", PROVISIONAL_MAX_COST_RATIO, precision=2, column="limit")
    frag.add(f"{KEY}.systematic_limit", PROVISIONAL_MAX_SYSTEMATIC_RATIO, precision=2, column="limit")

    frag.notes.append(f"layout: a longtable of {len(HEADER)} columns, up to {len(tags)} rows per channel (one per "
                      f"kept-fraction probe, one dashed row where the run measured none) over {len(channels)} "
                      "channels; it is a longtable, so it breaks across pages and needs no scaling, "
                      "unscaled; a midrule between channels, the header repeated on every page, and its own caption "
                      "and label, so the appendix must input it directly rather than wrap it in a table float")
    frag.notes.append("the screen returns refused_insufficient_support from two different rules: the calendar "
                      "minimums, tested on both halves before any candidate is examined, and the per-half "
                      "retained-frame floor, tested along the candidate sweep; the status string is identical, so "
                      "the rule column is read from the reason string, which names the rule that fired")
    retention, calendar = by_rule.get(RETENTION, []), by_rule.get(CALENDAR, [])
    if retention:
        fractions = [_num(c.section(SECTION).get("drift_refused_kept_fraction")) for c in channels
                     if c.channel in retention]
        pooled = {(_int(c.section(SECTION).get("drift_refused_early_kept")) or 0)
                  + (_int(c.section(SECTION).get("drift_refused_late_kept")) or 0)
                  for c in channels if c.channel in retention}
        fractions = [f for f in fractions if f is not None]
        frag.add(f"{KEY}.refused_kept_fraction_min", min(fractions), precision=4, column="kept_fraction")
        frag.add(f"{KEY}.refused_kept_fraction_max", max(fractions), precision=4, column="kept_fraction")
        frag.notes.append(
            f"on {_channel_list(retention)} the rule that fired is the retained-frame floor, and it fired where the "
            f"sweep first crosses the pooled floor: the refusing candidate's two halves sum to "
            + (f"{sorted(pooled)[0]}" if len(pooled) == 1 else f"one of {sorted(pooled)}")
            + f" frames on every one of them, keeping between {core.fmt(min(fractions) * 100, 2)}% and "
              f"{core.fmt(max(fractions) * 100, 2)}% of the calibration block; the sweep meets that band on any "
              "surface, so on these channels the stated reason is an artefact of where the rule fires and not a "
              "statement about drift --- the verdict has to stand on the ratios instead")
    if calendar:
        detail, needs = [], {}
        for c in channels:
            if c.channel not in calendar:
                continue
            support = calendar_support(c.section(SECTION))
            needs.setdefault(support["unit"], set()).add(support["need"])
            detail.append(f"ch{c.channel:02d} {support['half']} half {core.fmt(support['value'], 0)} "
                          f"{support['unit']} against {core.fmt(support['need'], 0)}")
        frag.notes.append(
            f"on {_channel_list(calendar)} the screen refused on calendar support before it examined any candidate "
            f"({'; '.join(detail)}), so on these the stated reason is a measurement and nothing about it is an "
            "artefact; the refused-at column there is the run's diagnostic re-walking the sweep to show where the "
            "retention rule would have fired, marked with a dagger, and is not what the screen refused on")
        # months before days, the order the gate tests them in
        minimums = " and ".join(f"{core.fmt(sorted(needs[unit])[0], 0)} {unit}" for unit in ("months", "days")
                                if len(needs.get(unit, ())) == 1)
        for unit, values in needs.items():
            if len(values) == 1:
                frag.add(f"{KEY}.minimum_{unit}", sorted(values)[0], precision=0, column="minimum")
        frag.notes.append(
            "the calendar gate returns on the first half that falls short, so a half's observed months and elapsed "
            "days are recorded only where they failed: a channel marked passed cleared both minimums"
            + (f" ({minimums}, the values the refusing channels' own reasons name)" if minimums else "")
            + " in both halves, but the run serialises no count for it, and the frames column is then the only "
              "per-half support the ledger carries")
    if tags:
        tag, fraction = tags[-1]
        cost = _exceeding(screened, tag, "cost", PROVISIONAL_MAX_COST_RATIO)
        systematic = _exceeding(screened, tag, "systematic", PROVISIONAL_MAX_SYSTEMATIC_RATIO)
        measured = [c for c in screened if _num(c.section(SECTION).get(f"drift_max_cost_ratio_at_{tag}")) is not None]
        frag.add(f"{KEY}.n_cost_exceeded", len(cost), kind="int", row={"kept_fraction": fraction}, column="channels")
        frag.add(f"{KEY}.n_systematic_exceeded", len(systematic), kind="int", row={"kept_fraction": fraction},
                 column="channels")
        worst = [(_num(c.section(SECTION).get(f"drift_max_cost_ratio_at_{tag}")), c.channel) for c in measured]
        if worst:
            low, high = min(worst), max(worst)
            frag.add(f"{KEY}.least_cost_ratio", low[0], precision=3, row={"kept_fraction": fraction},
                     column="cost_ratio")
            frag.add(f"{KEY}.least_cost_channel", low[1], kind="int", column="channel")
            frag.add(f"{KEY}.worst_cost_ratio", high[0], precision=3, row={"kept_fraction": fraction},
                     column="cost_ratio")
            frag.add(f"{KEY}.worst_cost_channel", high[1], kind="int", column="channel")
            frag.notes.append(
                f"the verdict stands on the ratios: at the strictest probe, over candidates keeping at least "
                f"{core.fmt(fraction, 2)} of each half, the cost ratio exceeds its {core.fmt(PROVISIONAL_MAX_COST_RATIO, 2)} "
                f"limit on {len(cost)} of the {len(measured)} channels the diagnostic measured (from "
                f"{core.fmt(low[0], 3)} on ch{low[1]:02d} to {core.fmt(high[0], 3)} on "
                f"ch{high[1]:02d}) and the systematic-residual ratio exceeds its "
                f"{core.fmt(PROVISIONAL_MAX_SYSTEMATIC_RATIO, 2)} limit on {len(systematic)}"
                + (f" ({_channel_list([ch for ch in (c.channel for c in measured) if ch not in systematic])} do not)"
                   if len(systematic) < len(measured) else ""))
    frag.notes.append("every candidate behind a probe row already keeps at least the per-half retained-frame floor "
                      "in both halves, because the diagnostic scores only the candidates that clear it; the "
                      "fraction is a further support requirement on top of that, so the row labelled 'all' means "
                      "every supported candidate rather than every candidate")
    not_run = by_rule.get(NOT_RUN, [])
    if not_run:
        frag.notes.append(f"{_channel_list(not_run)} never reached the screen: the selector refused earlier, so the "
                          "stability status is empty rather than a refusal, and the run recorded no drift "
                          f"diagnostic for them either; the selector's own refusal is carried as {KEY}.reason.chNN "
                          "rather than printed, which is why those rows are dashed across")
    frag.notes.append("the two ratio limits are the provisional values of rfisher_results.archive.selection "
                      f"(cost {core.fmt(PROVISIONAL_MAX_COST_RATIO, 2)}, systematic residual "
                      f"{core.fmt(PROVISIONAL_MAX_SYSTEMATIC_RATIO, 2)}; register ids stability.*, all open): the "
                      "ledger does not record the limits the run ran with, while the retained-frame floor and both "
                      "calendar minimums are quoted from the run's own reason strings, which name them")
    frag.notes.append("scope: the screen compares point estimates across the two halves and is not an equivalence "
                      "test; the block-resampled uncertainty an operational stability claim would also need is not "
                      "carried in the ledger, so nothing in this table promotes a screening result to an "
                      "operational one")
    return frag


BUILDERS = (build,)
