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


def _section(r_point, *, bins="7", z=(1.7, 1.8), f=0.4, status="measured", scale=1.0, refuse=(), notes=(),
             floor_share=0.5):
    """A worlds section: the residual carried through each cut, priced on a tolerance that tightens with it.

    ``floor_share`` sets the frontier floor as a fraction of the operating
    point's residual, so the class-bound columns have something to price.
    """
    r_floor = r_point * floor_share if r_point is not None and math.isfinite(r_point) else math.nan
    out = {"channel": 0, "bins": bins, "z_lo": z[0], "z_hi": z[1], "r_point": r_point, "r_floor": r_floor,
           "masked_fraction": f, "status": status, "notes": "; ".join(notes)}
    for world in WORLD_NAMES:
        db = suppression_db(world)
        drop = 10 ** (db / 10)
        r = r_point / drop if r_point is not None and math.isfinite(r_point) else math.nan
        out[f"{world}_r"] = r
        out[f"{world}_floor_r"] = r_floor / drop if math.isfinite(r_floor) else math.nan
        out[f"{world}_suppression_db"] = db
        for p in PARAMETERS:
            tol = math.nan if (world, p) in refuse else scale * 1e-2 / (PARAMETERS.index(p) + 1)
            usable = math.isfinite(tol) and math.isfinite(r)
            out[f"{world}_{p}_r_tol"] = tol
            out[f"{world}_{p}_R"] = r / tol if usable else math.nan
            out[f"{world}_{p}_floor_R"] = out[f"{world}_floor_r"] / tol if usable else math.nan
    return out


_LEDGERS = set()


def _ledger(tmp_path):
    if tmp_path in _LEDGERS:
        return tmp_path
    _LEDGERS.add(tmp_path)
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


_STRUCTURE = (r"\midrule", r"\toprule", r"\bottomrule", r"\endfirsthead", r"\endhead",
              r"\endfoot", r"\endlastfoot")


def _rows(frag):
    """The body rows of a tabular or a longtable, with the structural lines dropped."""
    lines = frag.tex.splitlines()
    start = lines.index(r"\endlastfoot") + 1 if r"\endlastfoot" in lines else lines.index(r"\midrule") + 1
    stop = lines.index(r"\end{longtable}") if r"\end{longtable}" in lines else lines.index(r"\bottomrule")
    body = [ln for ln in lines[start:stop] if ln not in _STRUCTURE and not ln.startswith(r"\multicolumn")]
    return [[c.strip() for c in line.rstrip(" \\").split(" & ")] for line in body]


def test_builders_are_registered():
    assert rw.BUILDERS == (rw.build, rw.build_ledger, rw.build_class_floor)
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


def test_the_ledger_is_a_longtable_carrying_its_own_caption(tmp_path):
    _, led = _both(tmp_path)
    assert r"\begin{longtable}" in led.tex and r"\endhead" in led.tex
    assert rw.LEDGER_LABEL in led.tex          # the label rides with the environment, not a float
    assert r"\begin{tabular}" not in led.tex


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


# ---------------------------------------------------------------- the class floor
def _floor(tmp_path):
    return rw.build_class_floor(core.load_run(_ledger(tmp_path)))


def test_the_class_floor_builder_is_registered():
    assert rw.BUILDERS == (rw.build, rw.build_ledger, rw.build_class_floor)


def test_only_channels_carrying_a_floor_appear(tmp_path):
    frag = _floor(tmp_path)
    # the fixture gives every measured channel a floor; the two without a point carry none
    assert [row[0] for row in _rows(frag)] == ["18", "21", "29"]


def test_the_floor_ratio_is_the_point_ratio_scaled_by_the_floor(tmp_path):
    run = core.load_run(_ledger(tmp_path))

    s = run.by_channel()[29].section("worlds")
    for world in WORLD_NAMES:
        for p in PARAMETERS:
            point, floor = s[f"{world}_{p}_R"], s[f"{world}_{p}_floor_R"]
            assert floor == pytest.approx(point * s["r_floor"] / s["r_point"])


def test_the_floor_is_never_worse_than_the_point(tmp_path):
    run = core.load_run(_ledger(tmp_path))
    for c in run.channels:
        if not c.has("worlds"):
            continue
        s = c.section("worlds")
        if s.get("r_floor") is None:
            continue
        assert s["r_floor"] <= s["r_point"]
        _, at_floor, _ = rw._best_over(c, PARAMETERS, floor=True)
        _, at_point, _ = rw._best_over(c, PARAMETERS, floor=False)
        assert at_floor <= at_point


def test_the_counts_are_taken_at_the_floor_not_the_point(tmp_path):
    run = core.load_run(_ledger(tmp_path))
    frag = rw.build_class_floor(run)
    counts = {n.key.rsplit(".", 1)[-1]: n.value for n in frag.numbers
              if n.key.startswith("ch09.classfloor.n_")}
    inside = [c.channel for c in run.channels
              if c.has("worlds") and c.section("worlds").get("r_floor") is not None
              and rw._best_over(c, ("fs8",), floor=True)[1] <= 1.0]
    assert counts["n_growth_inside"] == len(inside)


def test_the_notes_state_the_bound_and_its_scope(tmp_path):
    joined = " ".join(_floor(tmp_path).notes)
    assert "lower envelope of the (f, r_sys) plane by construction" in joined
    assert "not a setting anyone would operate at" in joined
    assert "bounds masking, not subtraction" in joined
    assert "frame resolution" in joined


def test_a_run_without_floors_says_so(tmp_path):
    ledger = tmp_path / "ledger"
    (ledger / "channels").mkdir(parents=True)
    (ledger / "run.json").write_text(json.dumps(
        {"schema": {"name": "rfisher-archive-ledger", "version": 1}, "generated": "x", "producer": {},
         "channels": ["channels/ch29_fid871.json"]}))
    section = _section(1.0)
    section.pop("r_floor", None)
    (ledger / "channels" / "ch29_fid871.json").write_text(json.dumps(
        {"channel": 29, "freq_id": 871, "product": "x.npz", "product_sha256": "b" * 64, "notes": [],
         "sections": {"worlds": section}}))
    frag = rw.build_class_floor(core.load_run(tmp_path))
    assert frag.tex == "" and "no channel carries a frontier floor" in frag.notes[0]
