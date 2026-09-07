"""The chapter's world table and its Appendix~C companion: every cell of both on a synthetic ledger."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

import pytest

from rfisher_results.archive.report import core
from rfisher_results.archive.report import worlds as rw
from rfisher_results.archive.worlds import PARAMETERS, WORLDS, suppression_db

REAL_RUN = Path(os.environ.get("RFISHER_ARCHIVE_RESULTS", "/home/djg/rail/results/archive_v5_2026-09-07"))
WORLD_NAMES = tuple(w[0] for w in WORLDS)


def _section(r_point, *, bins="7", z=(1.7, 1.8), f=0.4, status="measured", scale=1.0, refuse=(), notes=()):
    """A worlds section: the residual carried through each cut, priced on a tolerance that tightens with it."""
    out = {"channel": 0, "bins": bins, "z_lo": z[0], "z_hi": z[1], "r_point": r_point,
           "masked_fraction": f, "status": status, "notes": "; ".join(notes)}
    for world in WORLD_NAMES:
        db = suppression_db(world)
        r = r_point / 10 ** (db / 10) if r_point is not None and math.isfinite(r_point) else math.nan
        out[f"{world}_r"] = r
        out[f"{world}_suppression_db"] = db
        for p in PARAMETERS:
            tol = math.nan if (world, p) in refuse else scale * 1e-2 / (PARAMETERS.index(p) + 1)
            out[f"{world}_{p}_r_tol"] = tol
            out[f"{world}_{p}_R"] = r / tol if math.isfinite(tol) and math.isfinite(r) else math.nan
    return out


def _ledger(tmp_path):
    records = {
        # far outside every world: the ratios stay astronomically large
        18: {"worlds": _section(3.2e4, bins="10", z=(1.8, 1.9), f=0.527)},
        # the closest channel: passes under the deployed cut only
        29: {"worlds": _section(6.0e-3, bins="7", z=(1.7, 1.8), f=0.473, scale=1.0)},
        # a channel one parameter's gate refused in the hardest world
        21: {"worlds": _section(0.5, bins="8", z=(1.8, 1.9), f=0.584,
                                refuse=(("deployed", "fs8"),),
                                notes=("the stability gate accepted no integration time for deployed/fs8",))},
        # no operating point to carry through
        15: {"worlds": {"channel": 15, "bins": "9", "z_lo": 1.9, "z_hi": 2.0, "r_point": None,
                        "masked_fraction": None, "status": "no operating point",
                        "notes": "the channel has no operating point to carry through the worlds"}},
        # no overlapping forecast bin at all
        36: {"worlds": {"channel": 36, "bins": "", "z_lo": None, "z_hi": None, "r_point": 12.0,
                        "masked_fraction": 0.2, "status": "no overlapping bin",
                        "notes": "the channel overlaps no forecast bin, so no world applies"}},
        # a channel that predates the section entirely
        14: {"selection": {"status": "refused"}},
    }
    ledger = tmp_path / "ledger"
    (ledger / "channels").mkdir(parents=True)
    run = {"schema": {"name": "rfisher-archive-ledger", "version": 1}, "generated": "2026-09-07T00:00:00+00:00",
           "producer": {"commit": "a" * 40}, "products": {}, "era_config_digest": "c" * 64,
           "channels": [f"channels/ch{ch}_fid{900 - ch}.json" for ch in sorted(records)]}
    (ledger / "run.json").write_text(json.dumps(run))
    for ch, sections in records.items():
        sections = {k: (dict(v, channel=ch) if k == "worlds" else v) for k, v in sections.items()}
        rec = {"channel": ch, "freq_id": 900 - ch, "product": f"{900 - ch}.npz", "product_sha256": "b" * 64,
               "notes": [], "sections": sections}
        (ledger / "channels" / f"ch{ch}_fid{900 - ch}.json").write_text(json.dumps(rec))
    return tmp_path


def _both(tmp_path):
    run = core.load_run(_ledger(tmp_path))
    return rw.build(run), rw.build_ledger(run)


def _rows(frag):
    lines = frag.tex.splitlines()
    body = lines[lines.index(r"\midrule") + 1:lines.index(r"\bottomrule")]
    return [[c.strip() for c in line.rstrip(" \\").split(" & ")] for line in body if line != r"\midrule"]


def test_builders_are_registered():
    assert rw.BUILDERS == (rw.build, rw.build_ledger)
    from rfisher_results.archive.report import build as b
    assert "worlds" in b.TABLE_MODULES


def test_the_chapter_table_lists_only_channels_carrying_the_section(tmp_path):
    chapter, _ = _both(tmp_path)
    assert [row[0] for row in _rows(chapter)] == ["15", "18", "21", "29", "36"]      # ch14 has no section


def test_every_world_gets_a_column(tmp_path):
    chapter, _ = _both(tmp_path)
    assert len(rw.HEADER) == 3 + len(WORLD_NAMES)
    assert all(len(row) == len(rw.HEADER) for row in _rows(chapter))


def test_a_cell_prints_the_residual_over_its_binding_ratio(tmp_path):
    chapter, _ = _both(tmp_path)
    row = {r[0]: r for r in _rows(chapter)}["29"]
    r_none = 6.0e-3
    assert row[3].startswith(f"${rw.sci(r_none)}$ / ")                        # no filter: the residual is untouched
    r_dep = r_none / 10 ** (suppression_db("deployed") / 10)
    assert row[-1].startswith(f"${rw.sci(r_dep)}$ / ")


def test_the_binding_ratio_is_the_largest_of_the_parameters(tmp_path):
    run = core.load_run(_ledger(tmp_path))
    ch29 = run.by_channel()[29]
    name, R = rw.binding(ch29.section("worlds"), "none")
    assert name == "fs8"                                      # the tightest tolerance makes the largest ratio
    assert R == pytest.approx(6.0e-3 / (1e-2 / 3))
    assert R == max(ch29.section("worlds")[f"none_{p}_R"] for p in PARAMETERS)


def test_a_refused_parameter_does_not_hide_the_others(tmp_path):
    run = core.load_run(_ledger(tmp_path))
    section = run.by_channel()[21].section("worlds")
    name, R = rw.binding(section, "deployed")
    assert math.isnan(section["deployed_fs8_R"])
    assert name in ("aperp", "apar") and math.isfinite(R)


def test_a_channel_without_a_point_dashes_every_world(tmp_path):
    chapter, _ = _both(tmp_path)
    row = {r[0]: r for r in _rows(chapter)}["15"]
    assert row[2] == core.DASH and set(row[3:]) == {core.DASH}


def test_a_channel_with_no_bin_dashes_its_redshift_span(tmp_path):
    chapter, _ = _both(tmp_path)
    assert {r[0]: r for r in _rows(chapter)}["36"][1] == core.DASH


def test_the_verdict_counts_what_passes(tmp_path):
    run = core.load_run(_ledger(tmp_path))
    channels = [c for c in run.channels if c.has("worlds")]
    none = rw.verdict(channels, "none")
    deployed = rw.verdict(channels, "deployed")
    assert none.channels == deployed.channels == 3            # ch15 and ch36 score in no world
    assert none.passing == ()                                 # nothing passes without the cut
    assert deployed.passing == (29,)                          # the cut carries one channel under R = 1
    assert deployed.best_channel == none.best_channel == 29
    assert deployed.best_ratio < 1.0 <= none.best_ratio


def test_the_notes_book_both_sides_of_the_cut(tmp_path):
    chapter, _ = _both(tmp_path)
    joined = " ".join(chapter.notes)
    assert "re-derived from the Fisher bank" in joined
    assert "no world claims the credit without the cost" in joined
    assert "mode geometry only" in joined


def test_the_ledger_opens_out_every_parameter(tmp_path):
    _, led = _both(tmp_path)
    rows = _rows(led)
    scored = [c for c in (18, 21, 29, 15, 36)]
    assert len(rows) == len(scored) * len(WORLD_NAMES)
    assert len(rw.LEDGER_HEADER) == 4 + len(PARAMETERS)
    assert all(len(row) == len(rw.LEDGER_HEADER) for row in rows)


def test_the_ledger_carries_the_tolerance_behind_each_ratio(tmp_path):
    _, led = _both(tmp_path)
    keys = {n.key for n in led.numbers}
    for world in WORLD_NAMES:
        for p in PARAMETERS:
            assert f"appC.worlds.R.{world}.{p}.ch29" in keys
            assert f"appC.worlds.r_tol.{world}.{p}.ch29" in keys


def test_every_number_renders_as_it_prints(tmp_path):
    chapter, led = _both(tmp_path)
    for frag in (chapter, led):
        for n in frag.numbers:
            # a number prints either from its precision or from an explicit rendering, never from neither
            assert n.precision is not None or n.renderings or n.kind == "int", f"{n.key} has no printed form"
            assert all("\\times" not in r for r in n.renderings), n.key


def test_an_empty_run_says_why(tmp_path):
    ledger = tmp_path / "ledger"
    (ledger / "channels").mkdir(parents=True)
    (ledger / "run.json").write_text(json.dumps(
        {"schema": {"name": "rfisher-archive-ledger", "version": 1}, "generated": "x", "producer": {},
         "channels": ["channels/ch14_fid886.json"]}))
    (ledger / "channels" / "ch14_fid886.json").write_text(json.dumps(
        {"channel": 14, "freq_id": 886, "product": "x.npz", "product_sha256": "b" * 64, "notes": [], "sections": {}}))
    run = core.load_run(tmp_path)
    frag = rw.build(run)
    assert frag.tex == "" and "no channel carries a worlds section" in frag.notes[0]


@pytest.mark.skipif(not (REAL_RUN / "ledger" / "run.json").is_file(), reason="the archive run is not on this machine")
def test_the_real_run_builds_when_it_carries_the_section():
    run = core.load_run(REAL_RUN)
    if not any(c.has("worlds") for c in run.channels):
        pytest.skip("the run predates the world table")
    chapter, led = rw.build(run), rw.build_ledger(run)
    assert chapter.tex.count(r"\\") >= 5 and led.tex
    assert any(n.key.startswith("ch09.worlds.n_passing.") for n in chapter.numbers)
