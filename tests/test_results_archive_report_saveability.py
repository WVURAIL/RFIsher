"""The saveability tiers: which channels a delay cut or a cadence campaign could reach, and which nothing does."""
from __future__ import annotations

import json
import math

import pytest

from rfisher import residual
from rfisher_results.archive.report import core
from rfisher_results.archive.report import saveability as sv
from rfisher_results.archive.worlds import PARAMETERS, WORLDS, suppression_db

WORLD_NAMES = tuple(w[0] for w in WORLDS)


def _worlds(growth, dilation):
    """A worlds section whose ratios fall with the cut: ``growth``/``dilation`` are the no-filter values."""
    out = {"bins": "7", "z_lo": 1.7, "z_hi": 1.8, "r_point": 1.0, "masked_fraction": 0.4, "status": "measured",
           "notes": ""}
    for world in WORLD_NAMES:
        drop = 10 ** (suppression_db(world) / 10)
        out[f"{world}_r"] = 1.0 / drop
        for p in PARAMETERS:
            base = growth if p == "fs8" else dilation
            out[f"{world}_{p}_R"] = math.nan if base is None else base / drop
    return out


def _ledger(tmp_path, records):
    ledger = tmp_path / "ledger"
    (ledger / "channels").mkdir(parents=True)
    (ledger / "run.json").write_text(json.dumps(
        {"schema": {"name": "rfisher-archive-ledger", "version": 1}, "generated": "2026-09-07T00:00:00+00:00",
         "producer": {"commit": "a" * 40},
         "channels": [f"channels/ch{ch}_fid{900 - ch}.json" for ch in sorted(records)]}))
    for ch, sections in records.items():
        (ledger / "channels" / f"ch{ch}_fid{900 - ch}.json").write_text(json.dumps(
            {"channel": ch, "freq_id": 900 - ch, "product": "x.npz", "product_sha256": "b" * 64,
             "notes": [], "sections": sections}))
    return tmp_path


def _chain(quality, minutes=None, high=None):
    return {"tau_quality": quality, "tau_c_minutes": minutes, "tau_c_high_minutes": high}


def _run(tmp_path):
    """A band with one channel of every tier, plus the era marks."""
    records = {
        # inside on the growth rate with no filter at all
        33: {"worlds": _worlds(0.5, 0.05), "chain": _chain("measured", 4.0), "era": {}, "screening": {}},
        # the growth rate needs the deployed cut; the dilations are in from the start
        29: {"worlds": _worlds(10.0, 0.8), "chain": _chain("measured", 2.0), "era": {}, "screening": {}},
        # the dilations come in under a cut, the growth rate never does
        26: {"worlds": _worlds(500.0, 5.0), "chain": _chain("bounded_above", None, 5.0), "era": {}, "screening": {}},
        # booked at the cap: nothing as booked, but the what-if reaches the dilations
        23: {"worlds": _worlds(4e5, 4e3), "chain": _chain("refused"), "era": {}, "screening": {}},
        # booked at the cap and the what-if reaches nothing either
        30: {"worlds": _worlds(4e12, 4e11), "chain": _chain("refused"), "era": {}, "screening": {}},
        # a measured timescale and no world reaches anything: the cap is not the excuse
        18: {"worlds": _worlds(1e6, 1e5), "chain": _chain("measured", 3.0), "era": {}, "screening": {}},
        # priced on a dead carrier
        20: {"worlds": _worlds(2.0, 0.2), "chain": _chain("measured", 1.0), "era": {"off_era_current": True},
             "screening": {"off_era_current": True}},
        # an unconfirmed instrument change in the last month
        35: {"worlds": _worlds(3e3, 3e2), "chain": _chain("refused"),
             "era": {"unconfirmed_instrument_change_last_month": True}, "screening": {}},
        # no operating point to carry through
        15: {"worlds": {"bins": "9", "z_lo": None, "z_hi": None, "r_point": None, "masked_fraction": None,
                        "status": "no operating point", "notes": ""},
             "chain": _chain("refused"), "era": {}, "screening": {}},
        # no worlds section at all
        14: {"chain": _chain("refused"), "era": {}, "screening": {}},
    }
    return core.load_run(_ledger(tmp_path, records))


def _tiers(run):
    tau, _ = sv.reference_tau_seconds(run)
    head = sv.cadence_headroom(tau)
    return {c.channel: sv.classify(c, headroom=head) for c in run.channels}


def test_builder_is_registered():
    from rfisher_results.archive.report import build as b
    assert sv.BUILDERS == (sv.build,) and "saveability" in b.TABLE_MODULES


def test_the_reference_timescale_is_the_bands_worst_measured_evidence(tmp_path):
    run = _run(tmp_path)
    tau, basis = sv.reference_tau_seconds(run)
    assert tau == pytest.approx(4.0 * 60.0)             # ch33's 4 min is the largest measured
    assert "largest measured" in basis


def test_a_bound_stands_in_when_nothing_is_measured(tmp_path):
    run = core.load_run(_ledger(tmp_path, {26: {"worlds": _worlds(1.0, 1.0),
                                                "chain": _chain("bounded_above", None, 5.0)}}))
    tau, basis = sv.reference_tau_seconds(run)
    assert tau == pytest.approx(300.0) and "upper bound" in basis


def test_a_run_with_no_timescale_at_all_states_its_fallback(tmp_path):
    run = core.load_run(_ledger(tmp_path, {30: {"worlds": _worlds(1.0, 1.0), "chain": _chain("refused")}}))
    tau, basis = sv.reference_tau_seconds(run)
    assert tau == pytest.approx(sv.FALLBACK_TAU_MINUTES * 60.0) and "stated" in basis


def test_the_headroom_is_the_ratio_of_the_two_coherence_counts():
    head = sv.cadence_headroom(300.0)
    assert head == pytest.approx(residual.n_coh_from_correlation_time(300.0)
                                 / residual.n_coh_from_correlation_time(sv.CAP_SECONDS))
    assert 0.0 < head < 1.0                              # the what-if can only lower a capped residual


def test_the_growth_tier_takes_the_weakest_cut_that_reaches_it(tmp_path):
    tiers = _tiers(_run(tmp_path))
    assert tiers[33].tier == "growth" and tiers[33].reached_by == "none"     # in with no filter
    assert tiers[29].tier == "growth" and tiers[29].reached_by == "deployed"  # 10 / 13.8 < 1


def test_a_channel_inside_on_the_dilations_only_is_its_own_tier(tmp_path):
    tiers = _tiers(_run(tmp_path))
    assert tiers[26].tier == "dilation"
    assert tiers[26].growth_ratio > 1.0 and tiers[26].dilation_ratio <= 1.0


def test_the_cadence_tier_needs_both_a_refused_timescale_and_a_reachable_what_if(tmp_path):
    tiers = _tiers(_run(tmp_path))
    assert tiers[23].tier == "cadence" and tiers[23].headroom < 1.0
    assert tiers[30].tier == "none" and "the cap is not the reason" in tiers[30].note
    # a measured timescale never takes the cadence tier, however far out it is
    assert tiers[18].tier == "none" and tiers[18].headroom == 1.0


def test_a_channel_without_a_point_or_a_section_has_no_verdict(tmp_path):
    tiers = _tiers(_run(tmp_path))
    assert tiers[15].tier == "no verdict" and "no operating point" in tiers[15].note
    assert tiers[14].tier == "no verdict" and "no worlds section" in tiers[14].note


def test_the_era_marks_do_not_change_a_tier(tmp_path):
    tiers = _tiers(_run(tmp_path))
    assert tiers[20].off_era and tiers[20].tier == "growth"
    assert tiers[35].unsettled and tiers[35].tier in ("cadence", "none")


def test_the_table_has_one_row_per_channel_and_counts_every_tier(tmp_path):
    frag = sv.build(_run(tmp_path))
    lines = frag.tex.splitlines()
    body = [ln for ln in lines[lines.index(r"\midrule") + 1:lines.index(r"\bottomrule")] if ln != r"\midrule"]
    assert len(body) == 10
    counts = {n.key.rsplit(".", 1)[-1]: n.value for n in frag.numbers if n.key.startswith("ch09.saveability.n_")}
    assert counts["n_growth"] + counts["n_dilation"] + counts["n_cadence"] + counts["n_none"] \
           + counts["n_no_verdict"] == 10


def test_the_notes_state_the_what_if_and_the_era_caveat(tmp_path):
    joined = " ".join(sv.build(_run(tmp_path)).notes)
    assert "restores no ground-filter credit" in joined
    assert "not that the channel passes" in joined
    assert "what the channel will keep doing" in joined
    assert "R <= 1 is already the loose test" in joined


def test_every_number_carries_a_printed_form(tmp_path):
    frag = sv.build(_run(tmp_path))
    for n in frag.numbers:
        assert n.precision is not None or n.renderings or n.kind == "int", n.key
        assert all("\\times" not in r for r in n.renderings), n.key


def test_an_empty_run_says_so(tmp_path):
    run = core.load_run(_ledger(tmp_path, {}))
    frag = sv.build(run)
    assert frag.tex == "" and "no channel" in frag.notes[0]
