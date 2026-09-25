"""Least-residual points on a surface, with ties broken by the selector's own rule.

:func:`rfisher.thresholds.optimize_threshold` chooses among its near-minimum-cost
points by the key (systematic residual, masked fraction, rho, exact multiplier):
the lower residual, then less masking, then the lower rank, then the lower
multiplier. The summaries of this package pick a least-residual point from a
surface of kept-frame means. Two candidates that keep the same frames (one kept
set reached at several ranks, or a plateau on which every kept frame sits at the
channel floor) have residuals that differ only by summation-order rounding,
about 1e-15 relative, so an exact comparison chooses among them by the last
digit.

The rule here: residuals within ``TIE_REL_TOL`` (relative) of the least are
tied, and the tie is broken by the rest of the selector's key, the smallest
masked fraction first, then the lowest rho, then the lowest multiplier (on the
coarse rule, which has no rank, the lowest ``eta_c``). ``TIE_REL_TOL = 1e-9``
is well above the rounding of a mean over a million frames (about 1e-10 at
worst) and well below any real difference between two kept sets.
"""
from __future__ import annotations

import math
from typing import Callable, Iterable, TypeVar

T = TypeVar("T")

TIE_REL_TOL = 1e-9


def tied(a: float, b: float, *, rel_tol: float = TIE_REL_TOL) -> bool:
    """Whether two residuals are equal to within ``rel_tol`` of the larger magnitude."""
    return math.isclose(float(a), float(b), rel_tol=rel_tol, abs_tol=0.0)


def least(rows: Iterable[T], residual: Callable[[T], float], tie_key: Callable[[T], object], *,
          rel_tol: float = TIE_REL_TOL) -> T | None:
    """The row of least ``residual``; rows tied with it (:func:`tied`) go to the smallest ``tie_key``.

    ``None`` for no rows. Every residual must be finite; the callers filter first.
    """
    rows = list(rows)
    if not rows:
        return None
    low = min(float(residual(r)) for r in rows)
    return min((r for r in rows if tied(residual(r), low, rel_tol=rel_tol)), key=tie_key)
