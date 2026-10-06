"""The tolerance rule on a stub science model."""
from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from rfisher.science_model import Bin, Parameters, Scenario
from rfisher.tolerance import rule

HOURS = 10.0
TARGET = 1.0 * HOURS


def _model(response=None, accept=None, *, years=(1.0, 2.0), zeta=1.0):
    def default_response(scenario, bin_index, hours):
        b = {"a": 2.0, "b": -4.0, "c": 8.0}
        sigma = {"a": 0.5, "b": 0.25, "c": 0.125}
        return b, sigma

    def default_accept(scenario, bin_index, hours, parameter):
        return 1.0, 1

    return SimpleNamespace(
        parameters=Parameters(("a", "b"), ("c",)), zeta=zeta,
        target_years=1.0, year_grid=years, maximum_tolerance_ratio=1.2,
        scenarios=(Scenario("s", "rule", "x"), Scenario("t", "rule", "y")),
        load=lambda name: None,
        bins=lambda: (Bin(0, "z 1.0-1.1", 1.0, 1.1), Bin(1, "z 1.1-1.2", 1.1, 1.2)),
        hours=lambda years: years * HOURS,
        response=response or default_response,
        accept=accept or default_accept)


def test_rows_are_the_hand_computed_ones_in_the_models_orders():
    rows = rule.tolerance_rows(_model())
    assert [(r["world"], r["bin_index"], r["parameter"]) for r in rows] == [
        (s, b, p) for s in ("s", "t") for b in (0, 1) for p in ("a", "b", "c")]
    by = {(r["world"], r["bin_index"], r["parameter"]): r for r in rows}
    assert by[("s", 0, "a")]["tolerance"] == 0.5 / 2.0
    assert by[("s", 0, "b")]["tolerance"] == 0.25 / 4.0
    assert by[("t", 1, "c")]["tolerance"] == 0.125 / 8.0
    assert all(r["at_target"] and r["years_used"] == 1.0
               and r["years_accepted"] == 2 and r["years_refused"] == 0
               for r in rows)
    assert (by[("s", 1, "a")]["z_lo"], by[("s", 1, "a")]["z_hi"]) == (1.1, 1.2)


def test_zeta_scales_the_tolerance_and_one_is_exact():
    rows = rule.tolerance_rows(_model(zeta=0.5))
    assert rows[0]["tolerance"] == 0.5 * 0.5 / 2.0
    assert rule.tolerance_rows(_model(zeta=1.0))[0]["tolerance"] \
        == 0.5 / abs(2.0)


def test_a_refused_response_refuses_every_parameter_at_that_time():
    def response(scenario, bin_index, hours):
        if hours == TARGET:
            raise ValueError("solver refused")
        return {"a": 2.0, "b": 2.0, "c": 2.0}, {"a": 1.0, "b": 1.0, "c": 1.0}

    rows = rule.tolerance_rows(_model(response=response))
    for r in rows:
        assert not r["at_target"] and math.isnan(r["tolerance"])
        assert math.isnan(r["years_used"])
        assert (r["years_accepted"], r["years_refused"]) == (1, 1)


def test_a_refused_acceptance_refuses_only_its_parameter():
    def accept(scenario, bin_index, hours, parameter):
        if parameter == "b":
            raise ValueError("no stable response")
        return 1.0, 1

    rows = rule.tolerance_rows(_model(accept=accept))
    for r in rows:
        refused = r["parameter"] == "b"
        assert r["at_target"] is not refused
        assert r["years_refused"] == (2 if refused else 0)


@pytest.mark.parametrize("drift,signs", [(1.3, 1), (1.0, 2)])
def test_an_unstable_or_sign_flipping_response_is_refused(drift, signs):
    rows = rule.tolerance_rows(_model(
        accept=lambda *a: (drift, signs)))
    assert all(not r["at_target"] and r["years_refused"] == 2 for r in rows)


def test_only_the_target_time_sets_a_price():
    def accept(scenario, bin_index, hours, parameter):
        return (2.0 if hours == TARGET else 1.0), 1

    rows = rule.tolerance_rows(_model(accept=accept, years=(2.0, 3.0)))
    for r in rows:
        # the target is added to the grid, refused there, accepted elsewhere
        assert not r["at_target"] and math.isnan(r["tolerance"])
        assert (r["years_accepted"], r["years_refused"]) == (2, 1)


def test_an_unavailable_response_stops_the_table():
    def load(name):
        raise ValueError("bank missing")

    stub = _model()
    stub.load = load
    with pytest.raises(ValueError, match="bank missing"):
        rule.tolerance_rows(stub)
