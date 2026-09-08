"""The systematic-budget sensitivity table: the linearity it rests on, and every count it prints.

The table's whole content is arithmetic on published ratios, so the first
tests check the arithmetic is licensed --- that ``r_tol`` really is linear in
``zeta`` in the solver the tolerances come from, and that the response
stability gate does not move with the budget --- and the rest check the
counting on a synthetic ledger and on the run of record.
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
from pathlib import Path

import numpy as np
import pytest

from rfisher import selection_policy
from rfisher_results.archive.report import core
from rfisher_results.archive.report import zeta_sensitivity as zs
from rfisher_results.archive.worlds import WORLDS

ROOT = Path(__file__).resolve().parents[1]
REAL_RUN = Path(os.environ.get("RFISHER_ARCHIVE_RESULTS", "/home/djg/rail/results/archive_v5_2026-09-07b"))
RUN_OF_RECORD = "archive_v5_2026-09-07b"
WORLD_NAMES = tuple(w[0] for w in WORLDS)
PARAMETERS = (zs.GROWTH,) + zs.DILATIONS


def _bias_tolerance():
    """The tolerance solver, loaded the way the archive loads it (a script, not a module)."""
    spec = importlib.util.spec_from_file_location("zeta_test_bias_tolerance",
                                                  ROOT / "scripts" / "bias_tolerance.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Bank:
    """The smallest bias bank the solver accepts, with a mild time dependence.

    The response has to move a little with integration time or the stability
    gate has nothing to measure, and it must move slowly enough to pass it:
    ``sqrt(t)`` puts the tolerance drift at ``(1.1/0.9)^(1/4) = 1.05``, inside
    the registered limit of 1.2, so the gate accepts and the test can show
    that it accepts identically at every budget.
    """

    names = ("aperp", "apar", "fs8", "_Pres")

    def __init__(self):
        matrix = np.diag(np.array([4.0, 6.0, 9.0, 12.0]))
        ip = self.names.index("_Pres")
        for name, response in (("aperp", 0.8), ("apar", -0.4), ("fs8", 0.5)):
            i = self.names.index(name)
            matrix[i, ip] = matrix[ip, i] = response
        self.matrix = matrix
        self.paramnames = list(self.names)
        self.nbins = 1
        self.zs = np.array([0.8, 0.9])
        self.zc = np.array([0.85])
        self.t_grid = np.array([1e-3, 1e9])

    def F(self, ibin, t_hours):
        return self.matrix * (ibin + 1.0) * math.sqrt(float(t_hours))


# --------------------------------------------------------- the licence for the arithmetic
def test_the_budgets_come_from_the_decision_register():
    budgets = zs.zetas()
    assert budgets[0] == pytest.approx(float(selection_policy.value(zs.PRIMARY_ID)))
    declared = set(selection_policy.decision(zs.PRIMARY_ID).sensitivity_values)
    declared |= set(selection_policy.value(zs.SENSITIVITY_ID))
    assert set(budgets) == declared | {budgets[0]}
    assert list(budgets[1:]) == sorted(budgets[1:], reverse=True)      # strictest budget last, so counts fall
    assert all(z > 0.0 for z in budgets)


@pytest.mark.parametrize("parameter", ["aperp", "apar", "fs8"])
def test_the_tolerance_is_exactly_linear_in_the_budget(parameter):
    """r_tol(zeta) = zeta * r_tol(1) in the solver the world tolerances come from."""
    bt = _bias_tolerance()
    estimator = bt.PerBinAppendixAEstimator(_Bank())
    reference = bt.evaluate_fisher_point(estimator, 0, 3.0, parameter, zeta=1.0)
    for zeta in zs.zetas():
        point = bt.evaluate_fisher_point(estimator, 0, 3.0, parameter, zeta=zeta)
        assert point["central"]["r_tolerance"] == pytest.approx(
            zeta * reference["central"]["r_tolerance"], rel=1e-12)
        assert point["central"]["r_tolerance_current_noise_ratio"] == pytest.approx(
            zeta * reference["central"]["r_tolerance_current_noise_ratio"], rel=1e-12)


def test_the_stability_gate_does_not_move_with_the_budget():
    """The gate compares a ratio of tolerances, so the accepted times are the same at every budget."""
    bt = _bias_tolerance()
    estimator = bt.PerBinAppendixAEstimator(_Bank())
    reference = bt.evaluate_fisher_point(estimator, 0, 3.0, "aperp", zeta=1.0)
    assert reference["accepted"] is True                     # the fixture is inside the registered drift limit
    for zeta in zs.zetas():
        point = bt.evaluate_fisher_point(estimator, 0, 3.0, "aperp", zeta=zeta)
        assert point["accepted"] == reference["accepted"]
        assert point["rejection_reasons"] == reference["rejection_reasons"]
        assert point["stability"]["observed_tolerance_ratio"] == pytest.approx(
            reference["stability"]["observed_tolerance_ratio"])
        assert point["stability"]["bias_response_sign_count"] \
            == reference["stability"]["bias_response_sign_count"]


def test_the_world_banks_take_the_budget_free_form_of_the_same_tolerance():
    """archive.worlds builds sig/|dth|, which is the solver's tolerance at zeta = 1."""
    bt = _bias_tolerance()
    bank = _Bank()
    derivative, sigma = bt.bias_per_unit_r(bank.F(0, 3.0), bank.paramnames)
    solved = bt.evaluate_fisher_point(bt.PerBinAppendixAEstimator(bank), 0, 3.0, "aperp", zeta=1.0)
    assert sigma["aperp"] / abs(derivative["aperp"]) == pytest.approx(solved["central"]["r_tolerance"])
    # the gate the world path uses takes no budget at all: it cannot depend on one
    assert "zeta" not in bt.stability.__code__.co_varnames


def test_the_module_reprices_by_dividing_by_the_budget():
    section = {"deployed_aperp_evaluation_R": 2.0}
    assert zs.ratio(section, "deployed", "aperp", 1.0) == pytest.approx(2.0)
    assert zs.ratio(section, "deployed", "aperp", 0.5) == pytest.approx(4.0)     # stricter budget, larger R
    assert zs.ratio(section, "deployed", "aperp", 0.1) == pytest.approx(20.0)
    assert zs.ratio({}, "deployed", "aperp", 1.0) is None
    assert zs.ratio({"deployed_aperp_evaluation_R": float("nan")}, "deployed", "aperp", 1.0) is None


# ------------------------------------------------------------------ the synthetic ledger
def _section(channel, ratios, *, r_evaluation=1.0, floor_bound=False):
    """A worlds section carrying held-out ratios at zeta = 1.

    ``ratios`` maps ``(world, parameter)`` to the published ratio; anything
    unnamed is NaN, which is how the ledger records a parameter whose
    stability gate accepted no integration time.
    """
    out = {"channel": channel, "r_point": 1.0, "r_evaluation": r_evaluation, "floor_bound": floor_bound,
           "masked_fraction": 0.5, "status": "measured", "notes": ""}
    for world in WORLD_NAMES:
        out[f"{world}_r"] = 1.0
        out[f"{world}_evaluation_r"] = r_evaluation
        for p in PARAMETERS:
            out[f"{world}_{p}_evaluation_R"] = float(ratios.get((world, p), float("nan")))
    return out


def _run(tmp_path, records):
    ledger = tmp_path / "ledger"
    (ledger / "channels").mkdir(parents=True, exist_ok=True)
    (ledger / "run.json").write_text(json.dumps(
        {"schema": {"name": "rfisher-archive-ledger", "version": 1}, "generated": "2026-09-07T00:00:00+00:00",
         "producer": {"commit": "a" * 40}, "products": {}, "era_config_digest": "c" * 64,
         "channels": [f"channels/ch{ch}_fid{900 - ch}.json" for ch in sorted(records)]}))
    for ch, section in records.items():
        (ledger / "channels" / f"ch{ch}_fid{900 - ch}.json").write_text(json.dumps(
            {"channel": ch, "freq_id": 900 - ch, "product": f"{900 - ch}.npz", "product_sha256": "b" * 64,
             "notes": [], "sections": {} if section is None else {"worlds": section}}))
    return core.load_run(tmp_path)


def _all(value):
    return {(w, p): value for w in WORLD_NAMES for p in PARAMETERS}


def _ledger(tmp_path):
    """A band with one channel inside at every budget, one that drops out, and two absences."""
    inside = _all(30.0)
    inside.update({("deployed", "aperp"): 0.05, ("deployed", "apar"): 0.08,
                   ("peak2", "aperp"): 0.05, ("peak2", "apar"): 0.08})
    marginal = _all(30.0)
    marginal.update({("deployed", "aperp"): 0.4, ("deployed", "apar"): 0.9,
                     ("peak2", "aperp"): 0.4, ("peak2", "apar"): 2.0})
    half = _all(30.0)
    half.update({("deployed", "aperp"): 0.2})           # one dilation only: no pair verdict
    gated = _all(30.0)
    for p in PARAMETERS:                                # the gate refused this channel's 110 ns bins
        gated[("peak2", p)] = float("nan")
    gated[("deployed", "fs8")] = 0.5
    records = {
        21: _section(21, inside),
        29: _section(29, marginal),
        26: _section(26, half, floor_bound=True),
        18: _section(18, gated),
        15: _section(15, _all(float("nan")), r_evaluation=float("nan")),      # no replay at all
        14: None,                                                            # predates the section
    }
    return _run(tmp_path, records)


def _rows(frag):
    lines = frag.tex.splitlines()
    body = lines[lines.index(r"\midrule") + 1:lines.index(r"\bottomrule")]
    return [[c.strip() for c in line.rstrip(" \\").split(" & ")] for line in body if line != r"\midrule"]


def test_the_builder_is_registered():
    assert zs.BUILDERS == (zs.build,)
    assert zs.NAME == "zeta_sensitivity" and zs.LABEL == "tab:tolerance:zeta"
    from rfisher_results.archive.report import build as b
    assert "zeta_sensitivity" in b.TABLE_MODULES


def test_one_row_per_budget_and_cut(tmp_path):
    frag = zs.build(_ledger(tmp_path))
    rows = _rows(frag)
    assert len(rows) == len(zs.zetas()) * len(zs.CUTS)
    assert len(zs.HEADER) == len(zs.ALIGN)
    assert all(len(row) == len(zs.HEADER) for row in rows)
    assert rows[0][0] == "$1$" and rows[1][0] == ""       # the budget is printed once per block


def test_the_counts_fall_as_the_budget_tightens(tmp_path):
    """A stricter budget can only remove channels: the table's central claim about itself."""
    run = _ledger(tmp_path)
    channels = [c for c in run.channels if c.has(zs.SECTION)
                and c.section(zs.SECTION).get("r_evaluation") == 1.0]
    for world, _ in zs.CUTS:
        previous = None
        for zeta in zs.zetas():
            t = zs.tally(channels, world, zeta)
            counts = tuple(len(t.inside[p]) for p in PARAMETERS) + (len(t.inside_dilations),)
            if previous is not None:
                assert all(now <= before for now, before in zip(counts, previous))
            previous = counts


def test_a_channel_drops_out_at_the_budget_that_excludes_it(tmp_path):
    run = _ledger(tmp_path)
    channels = [c for c in run.channels if c.has(zs.SECTION)]
    # ch29's worse dilation is 0.9 at 200 ns: inside at zeta = 1, outside at 0.5
    assert 29 in zs.tally(channels, "deployed", 1.0).inside_dilations
    assert 29 not in zs.tally(channels, "deployed", 0.5).inside_dilations
    assert 21 in zs.tally(channels, "deployed", 0.1).inside_dilations      # 0.08 survives every budget


def test_the_dilation_pair_needs_both_parameters(tmp_path):
    run = _ledger(tmp_path)
    channels = [c for c in run.channels if c.has(zs.SECTION)]
    t = zs.tally(channels, "deployed", 1.0)
    assert 26 in t.inside["aperp"]                # the one dilation it carries is well inside
    assert 26 not in t.inside_dilations           # but the pair is undefined without the other


def test_the_named_channels_are_the_ones_inside(tmp_path):
    frag = zs.build(_ledger(tmp_path))
    # the budget prints once per block, so a row is found by its cut and its order
    deployed = [row for row in _rows(frag) if row[1] == r"$200$~ns"]
    assert len(deployed) == len(zs.zetas())
    assert deployed[0][-1] == "ch21, ch29" and deployed[0][-2] == "2"     # zeta = 1
    assert deployed[-1][-1] == "ch21" and deployed[-1][-2] == "1"         # the strictest budget


def test_a_world_the_gate_refused_lowers_that_row_only(tmp_path):
    run = _ledger(tmp_path)
    frag = zs.build(run)
    scored = {n.key: n.value for n in frag.numbers if n.key.startswith(f"{zs.KEY}.n_scored.")}
    assert scored[f"{zs.KEY}.n_scored.110"] == 3        # ch18's 110 ns bins were refused entirely
    assert scored[f"{zs.KEY}.n_scored.200"] == 4
    assert any("not at the 110 ns cut (ch18)" in note for note in frag.notes)


def test_a_channel_without_a_replay_is_in_no_denominator(tmp_path):
    frag = zs.build(_ledger(tmp_path))
    assert any("outside the table entirely (ch15)" in note for note in frag.notes)
    assert not any(".ch15" in n.key for n in frag.numbers)


def test_a_floor_bound_channel_inside_is_daggered_and_glossed(tmp_path):
    run = _run(tmp_path, {26: _section(26, _all(0.05), floor_bound=True)})
    frag = zs.build(run)
    assert zs.DAGGER in _rows(frag)[0][-1]
    joined = " ".join(frag.notes)
    assert "upper limits" in joined and "lower bound on that channel's tier" in joined


def test_the_notes_carry_the_linearity_and_the_direction(tmp_path):
    joined = " ".join(zs.build(_ledger(tmp_path)).notes)
    assert "r_tol(zeta) = zeta * r_tol(1) exactly" in joined
    assert "a smaller zeta is a stricter budget" in joined
    assert "evaluation_R" in joined and "the calibration never saw" in joined
    assert "two of the four worlds" in joined


def test_the_least_ratio_is_reported_as_the_budget_it_implies(tmp_path):
    frag = zs.build(_ledger(tmp_path))
    got = {n.key: n.value for n in frag.numbers}
    # ch21's worse dilation at 200 ns is 0.08, so no budget under it admits anything
    assert got[f"{zs.KEY}.least_dilation_R.200"] == pytest.approx(0.08)
    assert got[f"{zs.KEY}.least_dilation_channel.200"] == 21
    assert got[f"{zs.KEY}.least_growth_R.200"] == pytest.approx(0.5)    # ch18's, the only one under 30
    assert got[f"{zs.KEY}.least_growth_channel.200"] == 18


def test_every_number_renders_as_it_prints(tmp_path):
    frag = zs.build(_ledger(tmp_path))
    for n in frag.numbers:
        assert n.precision is not None or n.renderings or n.kind == "int", f"{n.key} has no printed form"
        assert all("\\times" not in r for r in n.renderings), n.key


def test_an_empty_run_says_why(tmp_path):
    frag = zs.build(_run(tmp_path, {14: None}))
    assert frag.tex == "" and "no channel carries a held-out residual" in frag.notes[0]


# ------------------------------------------------------------------ the run of record
@pytest.mark.skipif(not (REAL_RUN / "ledger" / "run.json").is_file(), reason="the archive run is not on this machine")
def test_the_real_run_builds_and_its_counts_only_fall():
    run = core.load_run(REAL_RUN)
    if not any(c.has(zs.SECTION) for c in run.channels):
        pytest.skip("the run predates the world table")
    frag = zs.build(run)
    assert frag.tex.count(r"\\") >= len(zs.zetas()) * len(zs.CUTS)
    counts = {(n.key.split(".")[-2], n.key.split(".")[-1]): n.value
              for n in frag.numbers if ".n_dilations." in n.key}
    for _, tag in zs.CUTS:
        series = [counts[(zs._zeta_key(z), tag)] for z in zs.zetas()]
        assert series == sorted(series, reverse=True)


@pytest.mark.skipif(REAL_RUN.name != RUN_OF_RECORD or not (REAL_RUN / "ledger" / "run.json").is_file(),
                    reason="not the run of record")
def test_the_run_of_record_admits_two_channels_at_zeta_one_and_none_below_a_half():
    """The chapter's claim, pinned: the verdict is a budget question only at the loosest budget.

    On archive_v5_2026-09-07b the held-out basis puts ch21 and ch29 inside on
    both dilations under the deployed cut at zeta = 1, ch21 alone at 110 ns,
    and nothing anywhere once the budget reaches the declared 0.3. The growth
    rate is outside at every declared budget.
    """
    frag = zs.build(core.load_run(REAL_RUN))
    got = {n.key: n.value for n in frag.numbers}
    assert got[f"{zs.KEY}.inside_dilations.z1.200"] == "ch21, ch29"
    assert got[f"{zs.KEY}.inside_dilations.z1.110"] == "ch21"
    for tag in ("110", "200"):
        assert got[f"{zs.KEY}.n_dilations.z0p3.{tag}"] == 0
        assert got[f"{zs.KEY}.n_dilations.z0p1.{tag}"] == 0
        for zeta in zs.zetas():
            assert got[f"{zs.KEY}.n_{zs.GROWTH}.{zs._zeta_key(zeta)}.{tag}"] == 0
    assert got[f"{zs.KEY}.least_growth_R.200"] == pytest.approx(3.17881119456898)
    assert got[f"{zs.KEY}.least_dilation_R.200"] == pytest.approx(0.5577942130310626)
