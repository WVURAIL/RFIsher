"""The priced candidates and the selector (rfisher.verdict.interval).

The split-function property: on the recorded fixtures and for five
tolerances each (the fixture's, 10x, 100x, the largest finite float and half
the least residual), the points, R, feasibility, cost, the selected point,
its status and its plateau are those the earlier selector
(``thresholds.optimize_threshold`` at 7b0067b) gave, float for float.
"""
from __future__ import annotations

import ast
import json
import math
from pathlib import Path

import pytest

from oc_rows import histogram_rows
from rfisher import policy
from rfisher.verdict import interval

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "tests" / "golden" / "verdict" / "split_property.json"
PROJECT = ROOT / "projects" / "chime_bao"


@pytest.fixture(scope="module")
def pol():
    return policy.load(PROJECT)


def _cases():
    doc = json.loads(GOLDEN.read_text(encoding="utf-8"))
    for fixture in doc["fixtures"]:
        for case in fixture["cases"]:
            yield pytest.param(fixture, case,
                               id=f"{fixture['name']}-{case['label']}")


def _hex(value):
    return None if value is None else float(value).hex()


@pytest.mark.parametrize("fixture,case", list(_cases()))
def test_the_split_selector_reproduces_the_earlier_one(pol, fixture, case):
    rows = histogram_rows(fixture["histograms"])
    tolerance = float.fromhex(case["tolerance"])
    pts = interval.points(rows, tolerance, pol)
    got = [[int(p.row["rho"]), int(p.row["eta_q16"]), _hex(p.R), p.feasible,
            _hex(p.cost), _hex(p.masked_fraction), _hex(p.r_sys)]
           for p in pts]
    assert got == case["points"]
    chosen = interval.select(pts, pol)
    assert chosen.status == case["status"]
    selected = chosen.selected
    assert ([int(selected.row["rho"]), int(selected.row["eta_q16"])]
            if selected else None) == case["selected"]
    if case["plateau"] is None:
        assert chosen.plateau_members is None
    else:
        low, high = chosen.plateau_eta
        assert {"members": chosen.plateau_members, "eta_low": _hex(low),
                "eta_high": _hex(high)} == case["plateau"]


def test_the_cost_has_the_selectors_operands_in_order():
    assert interval.cost(0.0, 0.36) == (1.0 + 0.0) / (1.0 - 0.36)
    assert interval.cost(None, 0.36) == 1.0 / (1.0 - 0.36)
    assert interval.cost(0.3, 0.4) == 1.3 / 0.6


def test_equality_meets_the_tolerance(pol):
    assert interval.feasible(0.125, 0.125, True)
    assert not interval.feasible(0.125, 0.125, False)
    assert not interval.feasible(math.nextafter(0.125, 1.0), 0.125, True)


def test_the_fine_rank_is_read_in_one_place(pol, monkeypatch):
    rows = histogram_rows({"1": {"candidate_multiplier_q16": [65536],
                                 "counts": [40, 10],
                                 "systematic_residual_sums": [1.0, 1.0]},
                           "63": {"candidate_multiplier_q16": [65536],
                                  "counts": [40, 10],
                                  "systematic_residual_sums": [1.0, 1.0]}})
    assert {r["threshold_family"] for r in interval.fine_candidates(
        rows, pol)} == {"rho=63"}

    class RecordedRankStudy:
        def value(self, ident):
            return "all" if ident == "selector.fine_rank" else pol.value(ident)

    assert {r["threshold_family"] for r in interval.fine_candidates(
        rows, RecordedRankStudy())} == {"rho=1", "rho=63"}
    readers = []
    for path in sorted((ROOT / "src" / "rfisher").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value == \
                    "selector.fine_rank":
                readers.append(path.relative_to(ROOT).as_posix())
    assert readers == ["src/rfisher/verdict/interval.py"]


def test_the_tie_break_is_the_policys(pol):
    key = interval.tie_key(pol)
    rows = histogram_rows({"3": {"candidate_multiplier_q16": [65536],
                                 "counts": [40, 10],
                                 "systematic_residual_sums": [4.0, 1.0]},
                           "2": {"candidate_multiplier_q16": [65536],
                                 "counts": [40, 10],
                                 "systematic_residual_sums": [4.0, 1.0]}})
    a, b = interval.points(rows, 1.0, pol)
    assert key(a) < key(b)                     # same r and f: the lower rank

    class Other:
        def value(self, ident):
            return ["masked_fraction"] if ident == "selection.tie_break" \
                else pol.value(ident)

    with pytest.raises(ValueError, match="tie_break"):
        interval.tie_key(Other())


def test_the_frozen_tie_break_names_the_same_order(pol):
    """The archive's frozen policy copy names the tail by rho and multiplier_q16; the key is the same."""
    class Frozen:
        def value(self, ident):
            return ["systematic_residual", "masked_fraction", "rho", "multiplier_q16"] \
                if ident == "selection.tie_break" else pol.value(ident)

    assert pol.value("selection.tie_break") == ("systematic_residual", "masked_fraction", "candidate_order")
    rows = histogram_rows({"3": {"candidate_multiplier_q16": [65536, 70000],
                                 "counts": [40, 10, 5],
                                 "systematic_residual_sums": [4.0, 1.0, 0.5]},
                           "2": {"candidate_multiplier_q16": [65536],
                                 "counts": [40, 10],
                                 "systematic_residual_sums": [4.0, 1.0]}})
    pts = interval.points(rows, 1.0, pol)
    assert [interval.tie_key(pol)(p) for p in pts] == [interval.tie_key(Frozen())(p) for p in pts]


def test_a_feasible_candidate_without_a_finite_cost_is_refused(pol):
    rows = histogram_rows({"4": {
        "candidate_multiplier_q16": [65536, 131072],
        "counts": [30, 30, 40], "systematic_residual_sums": [3.0, 6.0, 40.0]}})
    rows[0]["r_var"] = math.nan                 # an empty cell of the table
    with pytest.raises(interval.SelectionRefused, match="cost is not finite"):
        interval.select(interval.points(rows, 0.2, pol), pol)
    assert interval.select(interval.points(rows[1:], 0.2, pol),
                           pol).status == "selected"
