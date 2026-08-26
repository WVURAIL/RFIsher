"""Select a threshold from prepared frame arrays."""
import numpy as np

from rfisher.thresholds import (build_residual_score_histogram,
                                optimize_threshold)


systematic = np.full(100, 0.02)
histograms = {
    4: build_residual_score_histogram(
        np.linspace(0.8, 2.2, 100), systematic, (1.0, 1.5, 2.0),
        bulk_size=32),
    8: build_residual_score_histogram(
        np.linspace(0.9, 2.3, 100), systematic, (1.0, 1.5, 2.0),
        bulk_size=32),
}

result = optimize_threshold(histograms, 0.025)
print(result.selected)
