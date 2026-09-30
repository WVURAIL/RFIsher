"""The screen of a band and its precedence (rfisher.verdict.screening)."""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from oc_rows import histogram_rows, summary_row
from rfisher import policy
from rfisher.verdict import handoff, interval, screening

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "projects" / "chime_bao"
GOLDEN = ROOT / "tests" / "golden" / "handoff" / "archive_screen"
# The C.6 mapping: the rule-scenario tolerance is refused on 15 bands (step 1)
# and the detector refused the surface of the other eight (step 2).
STEP_1 = {"14", "15", "16", "17", "23", "24", "25", "26", "27", "28", "29",
          "30", "34", "35", "36"}
STEP_2 = {"18", "19", "20", "21", "22", "31", "32", "33"}


@pytest.fixture(scope="module")
def pol():
    return policy.load(PROJECT)


def test_the_golden_handoff_screens_23_bands_undetermined(pol):
    spec = handoff.schema()
    summary = handoff._read_table(GOLDEN / "oc_summary_extract.csv",
                                  spec["x-oc-summary-columns"])
    tolerances = handoff.read_tolerances(GOLDEN / "tolerances_rule.csv")
    source = json.loads((GOLDEN / "SOURCE.json").read_text())
    assert source["summary_rows"] == len(summary)
    outcomes = {}
    for tol in tolerances:
        band = tol["band_id"]
        rows = [s for s in summary if str(s["band_id"]) == band]
        families = screening.family_readings([], rows, float(tol["r_tol"])
                                             if math.isfinite(tol["r_tol"])
                                             else 1.0, pol)
        outcomes[band] = screening.screen(band, tol, rows, families, pol)
    assert {o.outcome for o in outcomes.values()} == {"undetermined"}
    assert {b for b, o in outcomes.items() if o.step == 1} == STEP_1
    assert {b for b, o in outcomes.items() if o.step == 2} == STEP_2
    assert outcomes["20"].reason == (
        "detector refused: no floor for frames without a shelf estimate")
    assert outcomes["18"].reason.startswith(
        "detector refused: within-era stability refused_insufficient_support")
    assert outcomes["14"].reason == ("tolerance refused: one or more "
                                     "target-time parameter tolerances refused")


def _band(r_values, *, statuses=("measured",), floor_share=0.0, **summary):
    """One band with one family per residual list: rows and summaries."""
    rows, summaries = [], []
    for index, values in enumerate(r_values):
        rho = str(index + 1)
        spec = {"candidate_multiplier_q16": [65536 * (k + 1)
                                             for k in range(len(values))],
                "counts": [30] + [10] * (len(values) - 1) + [5],
                "systematic_residual_sums": [0.0] * (len(values) + 1)}
        family_rows = histogram_rows({rho: spec})
        for row, value in zip(family_rows, values):
            row["r_sys"] = value
            row["r_sys_incoherent"] = value / 1000.0
            row["floor_share"] = floor_share
        rows += family_rows
        summaries.append(summary_row(
            f"rho={rho}", family_rows,
            chain_gain_status=statuses[index % len(statuses)], **summary))
    return rows, summaries


def _screen(pol, rows, summaries, r_tol=1.0):
    families = screening.family_readings(rows, summaries, r_tol, pol)
    return screening.screen("99", {"r_tol": r_tol, "refusal": ""}, summaries,
                            families, pol)


def test_an_excision_needs_every_family_empty(pol):
    rows, summaries = _band([[5.0, 6.0], [7.0, 8.0]])
    out = _screen(pol, rows, summaries)
    assert (out.outcome, out.step) == ("excise", 4)
    rows, summaries = _band([[5.0, 6.0], [0.5, 8.0]])
    out = _screen(pol, rows, summaries)
    assert out.outcome == "undetermined" and "P_fa unverified" in out.reason


def test_a_keep_needs_a_certified_false_alarm_limit(pol):
    rows, summaries = _band([[0.5, 6.0]])
    assert _screen(pol, rows, summaries).reason == \
        "keep-eligible; P_fa unverified"
    rows, summaries = _band([[0.5, 6.0]], eta_pfa=0.5,
                            eta_pfa_status="available")
    out = _screen(pol, rows, summaries)
    assert (out.outcome, out.step) == ("keep", 3)


def test_an_unmeasured_gain_excises_only_at_g_one(pol):
    # at the cap the exclusion reads r_sys at G = 1 (here r / 1000)
    rows, summaries = _band([[5.0, 6.0]], statuses=("cap",))
    out = _screen(pol, rows, summaries)
    assert out.outcome == "undetermined"
    rows, summaries = _band([[5000.0, 6000.0]], statuses=("bounded",))
    assert _screen(pol, rows, summaries).outcome == "excise"


def test_an_r_that_only_measures_the_floor_cannot_excise(pol):
    rows, summaries = _band([[5.0, 6.0]], floor_share=0.95)
    out = _screen(pol, rows, summaries)
    assert out.outcome == "undetermined" and "sensitivity-limited" in out.reason
    rows, summaries = _band([[5.0, 6.0]], floor_share=0.95,
                            floor_verified=True)
    assert _screen(pol, rows, summaries).outcome == "excise"


def test_the_precedence_is_first_match(pol):
    rows, summaries = _band([[5.0, 6.0]], refusal="bundle: too few frames",
                            stability_status="refused_drift")
    out = _screen(pol, rows, summaries)
    assert (out.outcome, out.step) == ("undetermined", 2)
    out = screening.screen("99", {"r_tol": math.nan, "refusal": "refused"},
                           summaries, [], pol)
    assert (out.outcome, out.step) == ("undetermined", 1)


def test_the_policy_must_declare_the_implemented_precedence(pol):
    class Other:
        def value(self, ident):
            return ["keep"] if ident == "selector.precedence" \
                else pol.value(ident)

    with pytest.raises(ValueError, match="precedence"):
        screening.check_precedence(Other())
    assert screening.exclusion_residual("measured", pol) == "r_sys"
    assert screening.exclusion_residual("bounded", pol) == "r_sys_incoherent"
    assert screening.exclusion_residual("cap", pol) == "r_sys_incoherent"
    with pytest.raises(ValueError, match="no exclusion gain"):
        screening.exclusion_residual("guessed", pol)
    assert interval.STATUS_THINNED in screening.NONEMPTY
