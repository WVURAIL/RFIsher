"""Named sensitivities, and the three gates on them.

(a) Mutation: with no sensitivity named, the screen, the deployable sets, R
    and the selections are byte-identical whatever suppression the
    sensitivity scenarios assume.
(b) Property: a sensitivity can only remove an excision, never add one.
(c) Lint: no residual is multiplied by a sensitivity factor outside
    ``rfisher/verdict/sensitivity.py`` (and the named records).
"""
from __future__ import annotations

import ast
import random
from pathlib import Path

import pytest

from rfisher.verdict import sensitivity
from rfisher.verdict.archive import verdict_archive

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "projects" / "chime_bao"
FACTOR_NAMES = ("suppression_db", "gamma", "split_share", "variance_split")


def _run(handoff_copy, tolerances, out, suppression):
    tol = tolerances({"29": [("none", "rule", 1000.0, 0.0),
                             ("deployed", "sensitivity", 900.0, suppression),
                             ("peak1", "sensitivity", 800.0, suppression / 3)],
                      "34": [("none", "rule", 100.0, 0.0),
                             ("deployed", "sensitivity", 90.0, suppression)]},
                     name=f"tolerances_{out.name}.csv")
    verdict_archive(handoff_copy.path, tol, PROJECT, out)
    return {name: (out / name).read_bytes() for name in (
        "screen.csv", "verdict.csv", "verdict_points.csv", "sensitivity.csv")}


def test_a_changed_suppression_changes_nothing_but_the_sensitivities(
        handoff_copy, tolerances, tmp_path):
    handoff_copy.edit(refusal="", stability_status="passed",
                      claim_status="screening")
    base = _run(handoff_copy, tolerances, tmp_path / "a", 11.4)
    rng = random.Random(20260930)
    for index in range(3):
        other = _run(handoff_copy, tolerances, tmp_path / f"m{index}",
                     rng.uniform(0.0, 60.0))
        for name in ("screen.csv", "verdict.csv", "verdict_points.csv"):
            assert other[name] == base[name], name
        assert other["sensitivity.csv"] != base["sensitivity.csv"]


def test_a_sensitivity_only_removes_an_excision():
    scenarios = [{"scenario": "deployed", "role": "sensitivity",
                  "tolerance_basis": "b", "r_tol": 1.0, "suppression_db": s}
                 for s in (0.0, 11.4, 40.0)]
    points = [(2.0, "rho=1"), (3.0, "rho=2")]
    rows = sensitivity.sensitivities("7", "excise", scenarios, points)
    assert [r["excision_holds"] for r in rows] == [True, False, False]
    assert {r["label"] for r in rows} == {sensitivity.IDEALIZED}
    assert sensitivity.outcome_with_sensitivities("excise", rows) == \
        "undetermined"
    robust = sensitivity.sensitivities("7", "excise", scenarios[:1], points)
    assert {r["label"] for r in robust} == {sensitivity.ROBUST}
    for outcome in ("undetermined", "keep"):
        rows = sensitivity.sensitivities("7", outcome, scenarios,
                                         [(1e9, "rho=1")])
        assert {r["label"] for r in rows} == {sensitivity.NO_EXCISION}
        assert sensitivity.outcome_with_sensitivities(outcome, rows) == outcome


def test_the_factor_multiplies_in_the_declared_order():
    assert sensitivity.priced(2.0, 11.4, 0.5) == 2.0 * 10.0 ** (-11.4 / 10.0) / 0.5
    assert sensitivity.factor(0.0) == 1.0


def _factor_products(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(
                node.op, (ast.Mult, ast.Div, ast.Pow)):
            names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
            names |= {n.attr for n in ast.walk(node)
                      if isinstance(n, ast.Attribute)}
            names |= {n.value for n in ast.walk(node)
                      if isinstance(n, ast.Constant) and isinstance(n.value,
                                                                     str)}
            hit = [n for n in names if any(f in str(n) for f in FACTOR_NAMES)]
            if hit:
                yield node.lineno, sorted(hit)


def test_no_sensitivity_factor_is_multiplied_in_elsewhere():
    package = ROOT / "src" / "rfisher"
    exempt = {package / "verdict" / "sensitivity.py"}
    # The forecast defines S and its own physics; the records of the 2026
    # capture ruling carry their frozen credit readings by name.
    exempt_dirs = (package / "forecast", package / "records")
    found = {}
    for path in sorted(package.rglob("*.py")):
        if path in exempt or any(d in path.parents for d in exempt_dirs):
            continue
        hits = list(_factor_products(ast.parse(path.read_text(
            encoding="utf-8"))))
        if hits:
            found[path.relative_to(ROOT).as_posix()] = hits
    assert found == {}


@pytest.mark.parametrize("suppression", [0.0, 3.6, 8.2, 11.4])
def test_the_rule_rows_carry_no_suppression(handoff_copy, tolerances, tmp_path,
                                            suppression):
    out = _run(handoff_copy, tolerances, tmp_path / f"s{suppression}",
               suppression)
    header = out["verdict.csv"].decode().splitlines()[0]
    assert "suppression" not in header


def test_an_excision_with_nothing_priced_is_not_called_robust():
    scenarios = [{"scenario": "deployed", "role": "sensitivity",
                  "tolerance_basis": "b", "r_tol": float("nan"),
                  "suppression_db": 11.4}]
    rows = sensitivity.sensitivities("7", "excise", scenarios,
                                     [(2.0, "rho=1")])
    assert {r["label"] for r in rows} == {sensitivity.UNPRICED}
    assert sensitivity.sensitivities("7", "excise", [], [(2.0, "rho=1")]) == []
