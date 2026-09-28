"""Band tolerances from the committed table, against the frozen archive tables."""
from __future__ import annotations

import csv
import math
from pathlib import Path

import pytest

from rfisher.forecast.radiofisher_bao import model
from rfisher.tolerance import bands, table

ROOT = Path(__file__).resolve().parents[2]
COMMITTED = ROOT / "src/rfisher/data/tolerances/filter_scenarios_T1yr.csv"
FIVE = [bands.Band(label, low, high) for label, low, high in (
    ("14", 470.0, 476.0), ("18", 494.0, 500.0), ("20", 506.0, 512.0),
    ("29", 560.0, 566.0), ("33", 584.0, 590.0))]
# r_tol as the frozen archive tables print it (channel_tolerances.csv
# r_tol_dilation for "none"; min of worlds.csv <s>_aperp_r_tol and
# <s>_apar_r_tol for the filter scenarios where a band has an operating
# point, and the per-bin table otherwise); "" is a refusal.
FROZEN_R_TOL = {
    "14": {"none": "", "peak1": "0.01021924679364289",
           "peak2": "0.009635835358288176", "deployed": "0.00750119928573071"},
    "18": {"none": "0.011958214197006222", "peak1": "0.02454212548996021",
           "peak2": "0.013699067424083207",
           "deployed": "0.015235843461215755"},
    "20": {"none": "0.00850842842622088", "peak1": "0.019149672216084164",
           "peak2": "", "deployed": "0.015235843461215755"},
    "29": {"none": "", "peak1": "", "peak2": "0.012472319337120617",
           "deployed": "0.0512661994655337"},
    "33": {"none": "0.01582870388553073", "peak1": "0.015394238461340167",
           "peak2": "", "deployed": "0.008835289661451726"},
}
SUPPRESSION = {"none": "0.0", "peak1": "3.6", "peak2": "8.2",
               "deployed": "11.4"}


@pytest.fixture(scope="module")
def written(tmp_path_factory):
    out = tmp_path_factory.mktemp("bands")
    science = model.RadioFisherBAO(ROOT / "projects" / "chime_bao")
    tolerances, components = bands.band_tolerances(
        science, table.load(COMMITTED), FIVE)
    table.write_bands(tolerances, components, out, {"schema": 3})
    with (out / "tolerances.csv").open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    with (out / "tolerance_components.csv").open(newline="") as fh:
        parts = list(csv.DictReader(fh))
    return rows, parts, out


def test_every_band_and_scenario_has_one_row_in_order(written):
    rows, _, _ = written
    assert [(r["band_id"], r["scenario"]) for r in rows] == [
        (b.band_id, s) for b in FIVE
        for s in ("none", "peak1", "peak2", "deployed")]
    assert list(rows[0]) == list(table.BAND_COLUMNS)


def test_r_tol_is_the_frozen_value_and_refusals_are_blank(written):
    rows, _, _ = written
    for r in rows:
        assert r["r_tol"] == FROZEN_R_TOL[r["band_id"]][r["scenario"]]
        assert r["refusal"] == ("" if r["r_tol"] else
                                bands.REFUSED_PARAMETER)
        assert (r["binding_parameter"] == "") == (r["r_tol"] == "")


def test_roles_suppression_and_the_declared_constants(written):
    rows, _, _ = written
    for r in rows:
        assert r["role"] == ("rule" if r["scenario"] == "none"
                             else "sensitivity")
        assert r["suppression_db"] == SUPPRESSION[r["scenario"]]
        assert (r["zeta"], r["target_time_years"]) == ("1.0", "1.0")
        assert r["tolerance_basis"] == "grid_T1yr_stability_gated"
    first = rows[0]
    assert (first["band_low_mhz"], first["band_high_mhz"]) == ("470.0", "476.0")


def test_the_binding_parameter_and_bin_reach_the_minimum(written):
    rows, parts, _ = written
    for r in rows:
        if not r["r_tol"]:
            continue
        match = [p for p in parts if p["band_id"] == r["band_id"]
                 and p["scenario"] == r["scenario"]
                 and p["parameter"] == r["binding_parameter"]
                 and p["bin"] == r["binding_bin"]]
        assert [p["r_tol_component"] for p in match] == [r["r_tol"]]
        assert r["binding_parameter"] in ("aperp", "apar")


def test_the_components_are_the_per_bin_table(written):
    _, parts, _ = written
    per_bin = {(r["world"], r["bin_index"], r["parameter"]): r
               for r in table.load(COMMITTED)}
    assert {(p["band_id"], p["bin"]) for p in parts} == {
        ("14", "11"), ("18", "10"), ("20", "9"), ("20", "10"), ("29", "7"),
        ("33", "6")}
    for p in parts:
        row = per_bin[(p["scenario"], int(p["bin"]), p["parameter"])]
        value = row["tolerance"] if row["at_target"] else math.nan
        assert p["r_tol_component"] == ("" if math.isnan(value)
                                        else repr(value))
        assert p["required"] == str(p["parameter"] != "fs8")
        assert p["status"] == ("accepted" if p["r_tol_component"] else
                               "refused: no stable response at the target time")
        assert p["bin_label"].startswith("z ")


def test_a_band_the_bins_do_not_cover_is_refused_as_such():
    science = model.RadioFisherBAO(ROOT / "projects" / "chime_bao")
    tolerances, _ = bands.band_tolerances(
        science, table.load(COMMITTED), [bands.Band("edge", 395.0, 410.0)])
    assert {r["refusal"] for r in tolerances} == {bands.REFUSED_COVERAGE}
    assert all(math.isnan(r["r_tol"]) for r in tolerances)


def test_bands_are_read_from_a_csv(tmp_path):
    path = tmp_path / "bands.csv"
    path.write_text("band_id,low_mhz,high_mhz\n14,470,476\n")
    assert bands.read_bands(path) == [bands.Band("14", 470.0, 476.0)]


def test_the_provenance_names_the_table_and_the_outputs(written):
    import json
    _, _, out = written
    record = json.loads((out / "tolerances.provenance.json").read_text())
    assert set(record) == {"schema", "tolerances_sha256", "components_sha256"}
