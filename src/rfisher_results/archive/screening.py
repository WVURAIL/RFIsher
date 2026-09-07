"""The screening class of a channel: one rule, its inputs named.

Vocabulary (chapter 9 §624-627, chapter 11 §27 and §76-77):

- ``recovery candidate``: the tolerance-selected operating point enters the
  dilation-tolerance region on the channel's current era (``R <= 1``) with
  the validations the closing condition names in place: a measured floor and
  a measured or bounded correlation time.
- ``measurement-bound on floor``: the verdict hangs on a floor that is only
  stated (no verified off era), whether the point is formally feasible or not.
- ``measurement-bound on tau_c``: the floor is measured but the correlation
  time was refused, so the chain is booked at the sidereal-day cap and the
  residual is an upper bound.
- ``occupancy-wall excision candidate``: the transmitter is present in nearly
  every frame; a formally feasible point there masks nearly everything (a
  time cost of hundreds) and is vacuous, and an infeasible one leaves no
  admissible point (chapter 9 §578).
- ``off-era``: the current era carries no transmitter (a proxy-low era after
  a sign-off); the channel is evaluated on an off era and its numbers are
  floors, not verdicts.

Precedence, top first: off-era; occupancy wall; then feasibility with the
floor and correlation evidence deciding between recovery candidate and the
two measurement-bound classes; an infeasible point on a channel that is not
at the occupancy wall is measurement-bound on whichever evidence is weaker.

Two thresholds the text leaves to judgement are parameters here, recorded on
every result: a masked fraction at or above 0.95 at the selected point, or a
survey-flag (occupancy) rate at or above 0.90, marks the occupancy wall.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

OCCUPANCY_WALL_MASKED_FRACTION = 0.95
OCCUPANCY_WALL_FLAG_RATE = 0.90

RECOVERY = "recovery candidate"
BOUND_FLOOR = "measurement-bound on floor"
BOUND_TAU = "measurement-bound on tau_c"
WALL = "occupancy-wall excision candidate"
OFF_ERA = "off-era"
CLASSES = (RECOVERY, BOUND_FLOOR, BOUND_TAU, WALL, OFF_ERA)


@dataclass(frozen=True)
class ScreeningInputs:
    off_era: bool                     # the current era is a transmitter-off (proxy-low) era
    selection_status: str             # 'feasible' | 'no feasible point' | 'no evaluable point' | 'refused'
    tolerance_fraction: float         # R = r_sys / r_tol at the selected point (NaN when none)
    masked_fraction: float            # at the selected point (NaN when none)
    survey_flag_rate: float           # occupancy indicator: fraction of era frames with F > mu_0
    floor_evidence: str               # 'measured' | 'stated' | 'refused'
    correlation_quality: str          # 'measured' | 'bounded_above' | 'refused' | 'unmeasured'
    refusal: str = ""
    claim_status: str = "screening"   # 'operational' | 'screening' | 'diagnostic' (drift screen refused)
    era_state: str = ""               # the current era's state (proxy-high / proxy-low / ambiguous-only)
    era_level_db: float = float("nan")  # its median level 10 log10(F/mu_0)
    anchor_sentinel: str = ""         # containment sentinel reasons when the fine anchor is suspect
    stability_status: str = ""        # the within-era drift screen's status


@dataclass(frozen=True)
class Screening:
    screening_class: str
    closing_condition: str            # the measurement that controls the verdict
    reasons: tuple[str, ...]
    thresholds: dict

    def as_row(self) -> dict:
        return {"screening_class": self.screening_class, "closing_condition": self.closing_condition,
                "screening_reasons": "; ".join(self.reasons)}


def screen(inputs: ScreeningInputs, *, wall_masked_fraction: float = OCCUPANCY_WALL_MASKED_FRACTION,
           wall_flag_rate: float = OCCUPANCY_WALL_FLAG_RATE) -> Screening:
    thresholds = {"occupancy_wall_masked_fraction": wall_masked_fraction, "occupancy_wall_flag_rate": wall_flag_rate}
    reasons: list[str] = []
    feasible = inputs.selection_status == "feasible" and inputs.tolerance_fraction <= 1.0
    floor_ok = inputs.floor_evidence == "measured"
    tau_ok = inputs.correlation_quality in ("measured", "bounded_above")

    def selection_clauses() -> list[str]:
        out = [f"selection: {inputs.selection_status}" + (" on the calibration surface" if inputs.selection_status != "feasible" else "")]
        if inputs.stability_status or inputs.refusal:
            out.append(f"drift screen: {inputs.stability_status or 'refused'}" + (f" ({inputs.refusal})" if inputs.refusal else ""))
        if inputs.claim_status:
            out.append(f"claim status {inputs.claim_status}")
        if inputs.anchor_sentinel:
            out.append(f"anchor sentinel: {inputs.anchor_sentinel}")
        return out

    if inputs.off_era:
        reasons.append("current era is a transmitter-off era; values are floors, not verdicts")
        reasons.extend(selection_clauses())
        return Screening(OFF_ERA, "era transition: the next sign-on", tuple(reasons), thresholds)

    at_wall = (inputs.survey_flag_rate >= wall_flag_rate) or (feasible and inputs.masked_fraction >= wall_masked_fraction)
    if at_wall and not (feasible and inputs.masked_fraction < wall_masked_fraction):
        if inputs.survey_flag_rate >= wall_flag_rate:
            reasons.append(f"survey flag rate {inputs.survey_flag_rate:.3f} >= {wall_flag_rate}: transmitter present in nearly every frame")
            if inputs.era_state and inputs.era_state != "proxy-high":
                level = f" (median level {inputs.era_level_db:.2f} dB)" if math.isfinite(inputs.era_level_db) else ""
                reasons.append(f"era state {inputs.era_state}{level}: a weak carrier present in nearly every frame")
        if feasible and inputs.masked_fraction >= wall_masked_fraction:
            reasons.append(f"selected point masks {inputs.masked_fraction:.3f} of frames: formally feasible, vacuous")
        reasons.extend(selection_clauses())
        return Screening(WALL, "none: excision, with the pilot bin kept as a monitoring tap", tuple(reasons), thresholds)

    if feasible:
        reasons.append(f"selected point inside tolerance on the dilation tier (R = {inputs.tolerance_fraction:.3g})")
        reasons.extend(selection_clauses()[1:])
        if floor_ok and tau_ok:
            reasons.append(f"floor measured; correlation time {inputs.correlation_quality}")
            return Screening(RECOVERY, "transfer gate: the online exact-replay agreement", tuple(reasons), thresholds)
        if not floor_ok:
            reasons.append(f"floor is {inputs.floor_evidence}: no verified off era")
            return Screening(BOUND_FLOOR, "measured floor from a verified off state", tuple(reasons), thresholds)
        reasons.append(f"correlation time {inputs.correlation_quality}: chain booked at the sidereal-day cap")
        return Screening(BOUND_TAU, "measured correlation time", tuple(reasons), thresholds)

    reasons.extend(selection_clauses())
    if not floor_ok:
        reasons.append(f"floor is {inputs.floor_evidence}")
        return Screening(BOUND_FLOOR, "measured floor from a verified off state", tuple(reasons), thresholds)
    if not tau_ok:
        reasons.append(f"correlation time {inputs.correlation_quality}")
        return Screening(BOUND_TAU, "measured correlation time", tuple(reasons), thresholds)
    reasons.append("floor and correlation time measured; no admissible point at this tolerance")
    return Screening(WALL, "none: no admissible operating point", tuple(reasons), thresholds)
