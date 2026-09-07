"""The screening-class rule."""
from __future__ import annotations

import math

from rfisher_results.archive import screening as sc


def _inputs(**kw):
    base = dict(off_era=False, selection_status="feasible", tolerance_fraction=0.5, masked_fraction=0.3,
                survey_flag_rate=0.6, floor_evidence="measured", correlation_quality="measured")
    base.update(kw)
    return sc.ScreeningInputs(**base)


def test_recovery_candidate_needs_feasibility_floor_and_correlation():
    s = sc.screen(_inputs())
    assert s.screening_class == sc.RECOVERY and "transfer gate" in s.closing_condition
    assert sc.screen(_inputs(correlation_quality="bounded_above")).screening_class == sc.RECOVERY


def test_measurement_bound_classes():
    assert sc.screen(_inputs(floor_evidence="stated")).screening_class == sc.BOUND_FLOOR
    assert sc.screen(_inputs(correlation_quality="refused")).screening_class == sc.BOUND_TAU
    # infeasible but not at the wall: bound on the weaker evidence
    assert sc.screen(_inputs(selection_status="no feasible point", tolerance_fraction=math.nan, masked_fraction=math.nan,
                             floor_evidence="stated")).screening_class == sc.BOUND_FLOOR
    assert sc.screen(_inputs(selection_status="refused", tolerance_fraction=math.nan, masked_fraction=math.nan,
                             correlation_quality="refused", refusal="stability refused")).screening_class == sc.BOUND_TAU


def test_occupancy_wall_by_flag_rate_or_vacuous_feasibility():
    s = sc.screen(_inputs(survey_flag_rate=0.99, selection_status="no feasible point", tolerance_fraction=math.nan, masked_fraction=math.nan))
    assert s.screening_class == sc.WALL and "monitoring tap" in s.closing_condition
    s = sc.screen(_inputs(masked_fraction=0.99, survey_flag_rate=0.99))
    assert s.screening_class == sc.WALL and any("vacuous" in r for r in s.reasons)
    # a feasible point that masks little on an occupied channel is not the wall
    assert sc.screen(_inputs(masked_fraction=0.2, survey_flag_rate=0.95)).screening_class == sc.RECOVERY
    # infeasible with everything measured and no wall: no admissible point
    s = sc.screen(_inputs(selection_status="no feasible point", tolerance_fraction=math.nan, masked_fraction=math.nan))
    assert s.screening_class == sc.WALL and "no admissible" in s.closing_condition


def test_off_era_takes_precedence_and_thresholds_are_recorded():
    s = sc.screen(_inputs(off_era=True, survey_flag_rate=0.99))
    assert s.screening_class == sc.OFF_ERA and s.thresholds["occupancy_wall_flag_rate"] == 0.9
    row = s.as_row()
    assert row["screening_class"] == sc.OFF_ERA and "sign-on" in row["closing_condition"]
    assert set(sc.CLASSES) == {sc.RECOVERY, sc.BOUND_FLOOR, sc.BOUND_TAU, sc.WALL, sc.OFF_ERA}
