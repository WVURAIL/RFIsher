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


@pytest.fixture
def recorded_rank_policy(pol):
    class RecordedRankPolicy:
        def value(self, ident):
            return "all" if ident == "selector.fine_rank" else pol.value(ident)

        def __getattr__(self, name):
            return getattr(pol, name)

    return RecordedRankPolicy()


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
    if summary.get("eta_pfa_status") == "available":
        summary = {"pfa_target": 1e-3, "pfa_upper_95": 9e-4,
                   "null_frames": 200000, "pfa_effective_samples": 200000.0,
                   "null_source": "transmitter-off epoch fixture", **summary}
    rows, summaries = [], []
    for index, values in enumerate(r_values):
        rho = str(index + 63)
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


def test_an_excision_needs_every_recorded_family_empty(recorded_rank_policy):
    pol = recorded_rank_policy
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


def test_an_empty_floor_flag_does_not_verify_the_floor(recorded_rank_policy):
    pol = recorded_rank_policy
    rows, summaries = _band([[5.0, 6.0]], floor_share=0.99, floor_verified=None)
    out = _screen(pol, rows, summaries)
    assert out.outcome == "undetermined" and "sensitivity-limited" in out.reason
    rows, summaries = _band([[5.0, 6.0], [7.0, 8.0]], floor_share=0.99)
    summaries[0]["floor_verified"] = True       # one family verified is not every family
    assert _screen(pol, rows, summaries).outcome == "undetermined"
    for s in summaries:
        s["floor_verified"] = True
    assert _screen(pol, rows, summaries).outcome == "excise"


def test_an_exclusion_without_a_finite_r_does_not_excise(pol):
    rows, summaries = _band([[5.0, 6.0]], floor_verified=True)
    for r in rows:
        r["r_sys"] = math.inf
    out = _screen(pol, rows, summaries)
    assert (out.outcome, out.reason) == ("undetermined",
                                         "no finite R in the exclusion reading")


def test_a_refused_family_carries_no_keep_and_no_excision(recorded_rank_policy):
    pol = recorded_rank_policy
    # One recorded family keeps but is refused; the other is empty.
    rows, summaries = _band([[0.5, 6.0], [7.0, 8.0]], eta_pfa=0.5,
                            eta_pfa_status="available")
    summaries[0]["stability_status"] = "refused_drift"
    out = _screen(pol, rows, summaries)
    assert (out.outcome, out.step) == ("excise", 4)
    assert out.families_checked == 2
    # the unrefused family keeps: the refused empty one does not block it
    rows, summaries = _band([[5.0, 6.0], [0.5, 8.0]], eta_pfa=0.5,
                            eta_pfa_status="available")
    summaries[0]["refusal"] = "bundle: too few frames"
    assert _screen(pol, rows, summaries).outcome == "keep"


def test_a_limit_on_the_bulk_or_at_another_alpha_is_not_certified(pol):
    rows, summaries = _band([[0.5, 6.0]], eta_pfa=0.5,
                            eta_pfa_status="available", pfa_target=1e-3,
                            null_source="transmitter-off epoch from 2023-02")
    families = screening.family_readings(rows, summaries, 1.0, pol)
    tol = {"r_tol": 1.0, "refusal": ""}
    assert screening.screen("99", tol, summaries, families, pol,
                            alpha=1e-3).outcome == "keep"
    assert screening.screen("99", tol, summaries, families, pol,
                            alpha=1e-2).outcome == "undetermined"
    for s in summaries:
        s["null_source"] = "bulk of the mixture (declared)"
    families = screening.family_readings(rows, summaries, 1.0, pol)
    out = screening.screen("99", tol, summaries, families, pol, alpha=1e-3)
    assert out.reason == "keep-eligible; P_fa unverified"


@pytest.mark.parametrize("field,value", [
    ("pfa_upper_95", None), ("pfa_upper_95", math.nan),
    ("pfa_upper_95", math.inf), ("pfa_upper_95", 0.0),
    ("pfa_upper_95", 0.5), ("pfa_target", None),
    ("pfa_target", math.nan), ("pfa_target", 1.0),
    ("null_frames", 0), ("null_frames", -1),
    ("null_frames", 2.5), ("null_frames", True),
    ("pfa_effective_samples", None), ("pfa_effective_samples", 12.5),
    ("pfa_effective_samples", 199999.0), ("pfa_effective_samples", math.inf),
    ("null_source", ""), ("null_source", None),
    ("null_source", "transmitter-off epoch "),
    ("null_source", "verified signal-free transmitter-off epoch fixture"),
    ("null_source", "bulk of the mixture (declared)"),
])
def test_malformed_null_certificate_cannot_keep(pol, field, value):
    rows, summaries = _band([[0.5, 6.0]], eta_pfa=0.5,
                            eta_pfa_status="available", **{field: value})
    families = screening.family_readings(rows, summaries, 1.0, pol)
    out = screening.screen("99", {"r_tol": 1.0, "refusal": ""},
                           summaries, families, pol, alpha=1e-3)
    assert (out.outcome, out.step, out.reason) == (
        "undetermined", 5, "keep-eligible; P_fa unverified")


def test_certificate_needs_its_summary_and_accepts_bound_equality(pol):
    rows, summaries = _band([[0.5, 6.0]], eta_pfa=0.5,
                            eta_pfa_status="available", pfa_upper_95=1e-3)
    reading = screening.family_readings(rows, summaries, 1.0, pol)[0].keep
    assert not screening.certified(reading)
    assert screening.certified(reading, summaries[0], alpha=1e-3)
    assert not screening.certified(reading, summaries[0], alpha=math.nan)
    for field in ("pfa_target", "pfa_upper_95", "pfa_effective_samples",
                  "null_frames", "null_source"):
        missing = {key: value for key, value in summaries[0].items() if key != field}
        assert not screening.certified(reading, missing, alpha=1e-3)



def test_coarse_certificate_uses_its_own_source_description(pol):
    rows, summaries = _band([[0.5, 6.0]], eta_pfa=0.5, eta_pfa_status="available")
    reading = screening.family_readings(rows, summaries, 1.0, pol)[0].keep
    summary = dict(summaries[0], candidate_set="coarse_frontier",
                   null_source="verified signal-free transmitter-off epoch fixture")
    assert screening.certified(reading, summary, alpha=1e-3)
    summary["pfa_effective_samples"] = 199999.5
    assert not screening.certified(reading, summary, alpha=1e-3)



@pytest.mark.parametrize("eta", [0.0, -1.0])
def test_fine_certificate_requires_a_positive_threshold(pol, eta):
    rows, summaries = _band([[0.5, 6.0]], eta_pfa=eta, eta_pfa_status="available")
    reading = screening.family_readings(rows, summaries, 1.0, pol)[0].keep
    assert not screening.certified(reading, summaries[0], alpha=1e-3)


def test_certificate_bound_cannot_beat_zero_exceedances(pol):
    from scipy.stats import beta

    rows, summaries = _band([[0.5, 6.0]], eta_pfa=0.5, eta_pfa_status="available",
                            null_frames=1, pfa_effective_samples=1.0)
    reading = screening.family_readings(rows, summaries, 1.0, pol)[0].keep
    assert not screening.certified(reading, summaries[0], alpha=1e-3)
    for n in (10000, 200000):
        upper = float(beta.ppf(0.95, 1, n))
        summaries[0].update(null_frames=n, pfa_effective_samples=float(n), pfa_upper_95=upper)
        assert screening.certified(reading, summaries[0], alpha=1e-3)
        summaries[0]["pfa_upper_95"] = 0.99 * upper
        assert not screening.certified(reading, summaries[0], alpha=1e-3)
