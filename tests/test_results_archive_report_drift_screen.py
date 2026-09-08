"""``tab:archive:drift``: the drift screen's two refusal rules, told apart on a synthetic ledger.

The table exists because the screen's status string is the same whichever rule
fired, so the tests that matter here are the ones that check the fragment
reads the *reason* and does not tell one story about every channel: a
retention refusal is an artefact of where the sweep crosses the pooled floor,
a calendar refusal is a measurement, and a channel the selector refused before
the screen ran is neither.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from rfisher_results.archive.report import core
from rfisher_results.archive.report import drift_screen as ds

REAL_RUN = Path(os.environ.get("RFISHER_ARCHIVE_RESULTS", "/home/djg/rail/results/archive_v5_2026-09-07b"))

PROBES = ((0.0, "0"), (0.05, "0p05"), (0.2, "0p2"))


def _drift(refused=(1, 1.0713, 29, 1), frames=(9482, 8550), ratios=((6.05, 41.4), (2.84, 10.2), (1.88, 5.17))):
    """The diagnostic fields ``..selection.drift_diagnostic`` writes into the selection section."""
    out = {"drift_status": "measured", "drift_early_frames": frames[0], "drift_late_frames": frames[1]}
    if refused is not None:
        rho, eta, early, late = refused
        out.update({"drift_refused_rho": rho, "drift_refused_eta": eta, "drift_refused_early_kept": early,
                    "drift_refused_late_kept": late,
                    "drift_refused_kept_fraction": (early + late) / (frames[0] + frames[1])})
    for (fraction, tag), (cost, systematic) in zip(PROBES, ratios):
        out[f"drift_candidates_at_{tag}"] = 1000 - int(fraction * 1000)
        out[f"drift_max_cost_ratio_at_{tag}"] = cost
        out[f"drift_max_systematic_ratio_at_{tag}"] = systematic
    return out


def _selection(status, reason, **extra):
    return {"status": "no feasible point", "refusal": f"within-era stability {status}: {reason}" if status else "",
            "stability_status": status, "stability_reason": reason, "stability_points_checked": 0,
            "stability_points_skipped": 30, **extra}


_LEDGERS = set()


def _ledger(tmp_path):
    if tmp_path in _LEDGERS:
        return tmp_path
    _LEDGERS.add(tmp_path)
    records = {
        # the retention rule: the sweep's first crossing of the pooled floor, halves summing to it
        14: _selection("refused_insufficient_support",
                       "candidate rho=1, eta=1.07129 retains fewer than 30 frames in one era half",
                       **_drift()),
        # the calendar rule, on observed months: the screen never reached the sweep
        17: _selection("refused_insufficient_support", "early half has 3 observed months; need 6",
                       **_drift(refused=(1, 546.643, 16, 14), frames=(3274, 3034),
                                ratios=((2.155, 1.091), (1.712, 1.055), (1.474, 1.049)))),
        # the calendar rule, on elapsed days
        19: _selection("refused_insufficient_support", "early half spans 166.924 days; need 270",
                       **_drift(refused=(1, 1.068, 18, 12), frames=(3330, 3123),
                                ratios=((4.032, 6.083), (2.164, 1.943), (1.585, 1.257)))),
        # the selector refused before a threshold family existed: no screen, no diagnostic
        15: {"status": "refused", "refusal": "no floor for frames without a shelf estimate",
             "stability_status": "", "stability_reason": "", "drift_status": "ValueError"},
        # a screen that passed, so the fragment must not describe every channel as refused
        20: _selection("passed", "supported point estimates are within both declared drift limits",
                       **_drift(refused=None, frames=(5000, 5000),
                                ratios=((1.02, 1.05), (1.01, 1.03), (1.01, 1.02)))),
    }
    ledger = tmp_path / "ledger"
    (ledger / "channels").mkdir(parents=True)
    run = {"schema": {"name": "rfisher-archive-ledger", "version": 1}, "generated": "2026-09-07T00:00:00+00:00",
           "producer": {"commit": "a" * 40}, "products": {}, "era_config_digest": "c" * 64,
           "channels": [f"channels/ch{ch}_fid{900 - ch}.json" for ch in sorted(records)]}
    (ledger / "run.json").write_text(json.dumps(run))
    for ch, section in records.items():
        rec = {"channel": ch, "freq_id": 900 - ch, "product": f"{900 - ch}.npz", "product_sha256": "b" * 64,
               "notes": [], "sections": {"selection": section}}
        (ledger / "channels" / f"ch{ch}_fid{900 - ch}.json").write_text(json.dumps(rec))
    return tmp_path


def _fragment(tmp_path):
    return ds.build(core.load_run(_ledger(tmp_path)))


_STRUCTURE = (r"\midrule", r"\toprule", r"\bottomrule", r"\endfirsthead", r"\endhead", r"\endfoot", r"\endlastfoot")


def _rows(frag):
    """The body rows of the longtable, with the structural lines dropped."""
    lines = frag.tex.splitlines()
    start = lines.index(r"\endlastfoot") + 1
    stop = lines.index(r"\end{longtable}")
    body = [ln for ln in lines[start:stop] if ln not in _STRUCTURE and not ln.startswith(r"\multicolumn")]
    return [[c.strip() for c in line.rstrip(" \\").split(" & ")] for line in body]


def _numbers(frag):
    return {n.key: n for n in frag.numbers}


def test_the_builder_is_registered():
    assert ds.BUILDERS == (ds.build,)
    from rfisher_results.archive.report import build as b
    assert "drift_screen" in b.TABLE_MODULES


def test_the_probe_set_comes_from_the_run_not_from_the_module(tmp_path):
    run = core.load_run(_ledger(tmp_path))
    channels = [c for c in run.channels if c.has("selection")]
    # the fixture records three of the four fractions the current module sweeps: a table that
    # printed the fourth would be printing a column the run never measured
    assert ds.probes(channels) == (("0", 0.0), ("0p05", 0.05), ("0p2", 0.2))


def test_each_rule_is_read_from_the_reason_not_from_the_status(tmp_path):
    run = core.load_run(_ledger(tmp_path)).by_channel()
    rules = {ch: ds.stated_rule(run[ch].selection) for ch in (14, 15, 17, 19, 20)}
    assert rules == {14: ds.RETENTION, 15: ds.NOT_RUN, 17: ds.CALENDAR, 19: ds.CALENDAR, 20: ds.PASSED}
    # the two refusal rules are indistinguishable by status alone, which is the point of the column
    assert run[14].selection["stability_status"] == run[17].selection["stability_status"]


def test_an_unrecognised_reason_is_not_forced_into_a_rule():
    assert ds.stated_rule({"stability_status": "refused_drift", "stability_reason": "cost ratio 2 exceeds 1.05"}) \
        == ds.OTHER


def test_the_calendar_support_is_the_measurement_the_reason_records(tmp_path):
    run = core.load_run(_ledger(tmp_path)).by_channel()
    assert ds.calendar_support(run[17].selection) == {"half": "early", "unit": "months", "value": 3.0, "need": 6.0}
    assert ds.calendar_support(run[19].selection) == {"half": "early", "unit": "days", "value": 166.924,
                                                     "need": 270.0}
    # a channel that passed the gate leaves no count behind: the gate returns on the first shortfall
    assert ds.calendar_support(run[14].selection) == {}


def test_the_refusing_candidate_sums_to_the_pooled_floor(tmp_path):
    run = core.load_run(_ledger(tmp_path)).by_channel()
    candidate = ds.refusing_candidate(run[14].selection)
    assert candidate["early_kept"] + candidate["late_kept"] == 30
    assert candidate["early_kept"] < 30 and candidate["late_kept"] < 30
    assert ds.refusing_candidate(run[15].selection) == {}          # no diagnostic was recorded


def test_a_calendar_refusal_marks_its_candidate_as_the_diagnostic_re_walk(tmp_path):
    rows = {r[0]: r for r in _rows(_fragment(tmp_path)) if r[0]}
    assert r"$^{\dagger}$" in rows["17"][2] and r"$^{\dagger}$" in rows["19"][2]
    assert r"\dagger" not in rows["14"][2]     # there the screen did refuse on that candidate


def test_a_channel_that_never_reached_the_screen_takes_one_dashed_row(tmp_path):
    rows = _rows(_fragment(tmp_path))
    dashed = [r for r in rows if r[0] == "15"]
    assert len(dashed) == 1 and set(dashed[0][2:]) == {core.DASH}
    assert dashed[0][1] == ds.NOT_RUN


def test_a_screened_channel_takes_one_row_per_probe(tmp_path):
    rows = _rows(_fragment(tmp_path))
    assert [r[0] for r in rows].count("14") == 1            # only the group's first row names the channel
    head = [i for i, r in enumerate(rows) if r[0] == "14"][0]
    group = rows[head:head + len(PROBES)]
    assert [r[5] for r in group] == ["all", "$0.05$", "$0.20$"]
    assert [r[0] for r in group[1:]] == [""] * (len(PROBES) - 1)
    assert all(len(r) == len(ds.HEADER) for r in rows)


def test_the_zero_probe_is_labelled_as_the_supported_candidates(tmp_path):
    # 'kept >= 0' would read as every candidate; every candidate scored has already cleared the floor
    assert ds.probe_label(0.0) == "all"
    assert " labelled 'all' means every supported candidate" in " ".join(_fragment(tmp_path).notes)


def test_a_ratio_prints_to_three_decimals_so_a_limit_is_not_straddled(tmp_path):
    rows = {r[0]: r for r in _rows(_fragment(tmp_path)) if r[0]}
    assert rows["17"][6] == "$2.155$" and rows["17"][7] == "$1.091$"
    # at three significant figures 1.091 would print as 1.09 and 1.101 as 1.10, which reads as
    # sitting on the 1.10 limit rather than above it
    assert core.fmt(1.101, 3) == "1.101"


def test_the_notes_separate_the_artefact_from_the_measurement(tmp_path):
    notes = " ".join(_fragment(tmp_path).notes)
    assert "ch14" in notes and "the stated reason is an artefact of where the rule fires" in notes
    assert "ch17, ch19" in notes and "the stated reason is a measurement" in notes
    # the fragment must not claim the artefact for the calendar refusals
    artefact = [n for n in _fragment(tmp_path).notes if "artefact of where the rule fires" in n][0]
    assert "ch17" not in artefact and "ch19" not in artefact


def test_the_notes_price_the_verdict_on_the_ratios_at_the_strictest_probe(tmp_path):
    frag = _fragment(tmp_path)
    numbers = _numbers(frag)
    # ch14, ch17 and ch19 exceed the cost limit at kept >= 0.2; ch20's passing screen does not
    assert numbers["appC.drift.n_cost_exceeded"].value == 3
    assert numbers["appC.drift.n_systematic_exceeded"].value == 2      # ch17 sits at 1.049
    assert numbers["appC.drift.worst_cost_channel"].value == 14
    assert "the verdict stands on the ratios" in " ".join(frag.notes)


def test_the_counts_split_the_band_by_rule(tmp_path):
    numbers = _numbers(_fragment(tmp_path))
    assert numbers["appC.drift.channels"].value == 5
    assert numbers["appC.drift.n_retention"].value == 1
    assert numbers["appC.drift.n_calendar"].value == 2
    assert numbers["appC.drift.n_passed"].value == 1
    assert numbers["appC.drift.n_not_run"].value == 1
    assert numbers["appC.drift.n_screened"].value == 4


def test_the_calendar_minimums_are_quoted_from_the_run(tmp_path):
    numbers = _numbers(_fragment(tmp_path))
    assert numbers["appC.drift.minimum_months"].value == 6.0
    assert numbers["appC.drift.minimum_days"].value == 270.0
    assert "the run serialises no count for it" in " ".join(_fragment(tmp_path).notes)


def test_the_reason_is_carried_verbatim_for_every_channel(tmp_path):
    numbers = _numbers(_fragment(tmp_path))
    assert numbers["appC.drift.reason.ch17"].value == "early half has 3 observed months; need 6"
    # a channel the screen never reached carries the selector's refusal instead of an empty cell
    assert numbers["appC.drift.reason.ch15"].value == "no floor for frames without a shelf estimate"


def test_the_fragment_is_a_longtable_carrying_its_own_caption(tmp_path):
    frag = _fragment(tmp_path)
    assert r"\begin{longtable}" in frag.tex and r"\endhead" in frag.tex
    assert ds.LABEL in frag.tex and r"\begin{tabular}" not in frag.tex


def test_every_number_renders_as_it_prints(tmp_path):
    for n in _fragment(tmp_path).numbers:
        assert n.precision is not None or n.renderings or n.kind == "int", f"{n.key} has no printed form"


def test_an_empty_run_says_why(tmp_path):
    ledger = tmp_path / "ledger"
    (ledger / "channels").mkdir(parents=True)
    (ledger / "run.json").write_text(json.dumps(
        {"schema": {"name": "rfisher-archive-ledger", "version": 1}, "generated": "x", "producer": {},
         "channels": ["channels/ch14_fid886.json"]}))
    (ledger / "channels" / "ch14_fid886.json").write_text(json.dumps(
        {"channel": 14, "freq_id": 886, "product": "x.npz", "product_sha256": "b" * 64, "notes": [], "sections": {}}))
    frag = ds.build(core.load_run(tmp_path))
    assert frag.tex == "" and "no channel carries a selection section" in frag.notes[0]


@pytest.mark.skipif(not (REAL_RUN / "ledger" / "run.json").is_file(), reason="the archive run is not on this machine")
def test_the_real_run_splits_into_both_rules():
    """The run of record refuses under both rules, which is why the fragment reports them apart."""
    run = core.load_run(REAL_RUN)
    frag = ds.build(run)
    rules = {c.channel: ds.stated_rule(c.selection) for c in run.channels if c.has("selection")}
    if not rules:
        pytest.skip("the run predates the selection section")
    # every screened channel of this run refused, and both rules are represented; a run where the
    # retention rule fired everywhere would make the artefact note the whole story, and it is not
    assert ds.PASSED not in rules.values()
    assert sum(1 for r in rules.values() if r == ds.CALENDAR) > 0
    assert sum(1 for r in rules.values() if r == ds.RETENTION) > 0
    for c in run.channels:
        if ds.stated_rule(c.selection) != ds.RETENTION:
            continue
        candidate = ds.refusing_candidate(c.selection)
        # the refusal is the sweep's first crossing of the pooled floor, so the halves sum to it
        assert candidate["early_kept"] + candidate["late_kept"] == 30
    assert frag.tex.count(r"\\") > len(rules)
