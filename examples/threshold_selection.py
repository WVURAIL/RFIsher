"""Select a screening threshold from exact prepared frame rows."""
import datetime as dt
import hashlib

import numpy as np

from rfisher.preparation import (CalibrationEvidence,
                                 prepare_threshold_family,
                                 select_prepared_threshold)
from rfisher.thresholds import ALWAYS_MASKED_Q16, Q16_SCALE


def artifact_digest(label):
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def measured_evidence(label):
    return CalibrationEvidence(
        state="measured",
        method=f"example {label}",
        source="embedded threshold-selection example",
        artifact_sha256=artifact_digest(label),
    )


stamps = []
for year in (2024, 2025):
    for month in range(1, 13):
        stamp = dt.datetime(
            year, month, 1, tzinfo=dt.timezone.utc).timestamp()
        stamps.extend([stamp] * 5)

frame_count = len(stamps)
pattern = [1, Q16_SCALE, 2 * Q16_SCALE,
           ALWAYS_MASKED_Q16, Q16_SCALE]
requirements = pattern * (frame_count // len(pattern))

# These drift values demonstrate the interface; they are not adopted limits.
family = prepare_threshold_family(
    {1: requirements, 2: requirements},
    np.full(frame_count, 0.02),
    frame_times=stamps,
    acquisition_ids=range(frame_count),
    exposure_seconds=np.full(frame_count, 41.0),
    source_id=f"sha256:{artifact_digest('latest-era rows')}",
    era_label="2024-01..2025-12 example",
    latest_era=True,
    additive_residuals=True,
    score=measured_evidence("Q16 score boundaries"),
    correlation=measured_evidence("block correlation summary"),
    transfer=CalibrationEvidence(
        state="conditional",
        method="unit screening transfer",
        source="embedded threshold-selection example",
    ),
    max_cost_ratio=1.0,
    max_systematic_residual_ratio=1.0,
    minimum_half_retained_frames=10,
)

result = select_prepared_threshold(
    family, science_tolerance=0.025, allow_screening=True)
print(result.claim_status, result.source_id, result.policy_sha256,
      result.selected)
