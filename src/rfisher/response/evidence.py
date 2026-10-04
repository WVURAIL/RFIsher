"""Evidence boundary between detector diagnostics and science selection.

This checks an explicit qualification declaration, not the underlying science
calibration. A caller still has to authenticate its source and use the declared
same-mask response, tolerance and observing-time estimator. In particular, an
unqualified diagnostic cannot become evidence of all-threshold infeasibility.
"""
from __future__ import annotations

from collections.abc import Mapping

CONDITIONAL_SCREENING_EVIDENCE = {
    "evidence_kind": "conditional_screening_allowance",
    "physical_response_qualified": False,
    "science_selection_eligible": False,
    "residual_contains_sensitivity_floor": True,
}
HISTORICAL_SCREENING_EVIDENCE = {
    **CONDITIONAL_SCREENING_EVIDENCE,
    "decision_scope": "historical_conditional_screen",
    "physical_operating_recommendation": "not_established",
}


class UnqualifiedResponseError(ValueError):
    """A diagnostic or undeclared response cannot select a science policy."""


def require_science_selection_evidence(evidence: Mapping) -> None:
    """Refuse implicit conversion of a floor or detector contrast into RFI.

    Missing legacy metadata is ineligible. A matched-null detector contrast is
    useful evidence but needs a qualified physical transfer before it can enter
    science-tolerance admission. Contradictory flags cannot promote either that
    contrast or an archival screening allowance to a physical response.

    Passing this boundary does not itself admit any candidate: tolerance and
    time remain the responsibility of the physical response's selector.
    """
    if not isinstance(evidence, Mapping):
        raise TypeError("response evidence must be a mapping")
    if (evidence.get("evidence_kind") != "physical_same_mask_response"
            or evidence.get("physical_response_qualified") is not True
            or evidence.get("science_selection_eligible") is not True
            or evidence.get("residual_contains_sensitivity_floor") is not False):
        raise UnqualifiedResponseError(
            "science selection requires a qualified physical same-mask response "
            "with sensitivity floors separate from residual interference; "
            "diagnostic or missing evidence is not proof of infeasibility and "
            "does not justify reject-all")
