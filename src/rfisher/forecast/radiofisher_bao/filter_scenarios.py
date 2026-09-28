"""Delay-filter options of the forecast.

The delay-cut hooks are forecast options and are off by default: a bank or a
forecast uses them only when a caller passes the hook into the experiment.
The digitised filter response of the CHIME 2025 detection (Fig. 10) stays in
package data.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .bank._validation import nonnegative_scalar, positive_scalar

FILTER_RESIDUAL_TABLE = "chime2025_fig10_filter_residual.csv"


def filter_residual_table(path: str | Path | None = None):
    """The digitised Fig. 10 filter response: (tau / tau_cut, RMS residual).

    Rows are the vertices of the paper's median curve; the file header
    records the extraction and the high-delay plateau."""
    from .bank.resources import data_file

    source = Path(path) if path is not None else data_file(
        FILTER_RESIDUAL_TABLE)
    with source.open("r") as stream:
        rows = [line for line in stream
                if line.strip() and not line.lstrip().startswith("#")]
    # The first non-comment line is the column header.
    try:
        table = np.loadtxt(rows[1:], delimiter=",", ndmin=2)
    except ValueError as exc:
        raise ValueError(f"{source} is not a two-column response table") \
            from exc
    if table.shape[1] != 2 or table.shape[0] < 2:
        raise ValueError(f"{source} is not a two-column response table")
    ratio, response = table[:, 0], table[:, 1]
    if np.any(np.diff(ratio) <= 0.0) or ratio[0] < 0.0:
        raise ValueError(f"{source}: tau / tau_cut must increase from >= 0")
    if np.any(response < 0.0):
        raise ValueError(f"{source}: RMS residual must be non-negative")
    return ratio, response


def delay_transfer(rf, expt: dict, cosmo_fns, tau_cut_seconds: float,
                   table=None):
    """Return the ``expt['kpar_transfer_fn']`` hook for the soft delay cut.

    The measured filter response (Fig. 10, at 200 ns) is scaled in
    tau / tau_cut to ``tau_cut_seconds``, normalised to its plateau and
    squared, and multiplies the signal power. Signal only: the same
    filter attenuates the noise too, so this brackets the hard cut from
    the conservative side rather than replacing it."""
    from .bank.backend import require_backend_capabilities

    require_backend_capabilities(rf, {"kpar_transfer_fn"})
    ratio, response = filter_residual_table() if table is None else table
    return rf.delay_transfer_fn(
        positive_scalar(tau_cut_seconds, "tau_cut_seconds"),
        cosmo_fns[0], expt["nu_line"], ratio, response)


def delay_cut(rf, expt: dict, cosmo_fns, tau_cut_seconds: float,
              transition: float | None = None):
    """Return the ``expt['kpar_min_fn']`` hook for a hard delay-domain cut.

    ``tau_cut_seconds`` is the high-pass filter delay; the backend applies
    the transition-zone factor (1.4 by default, CHIME's 200 ns cut against
    its 280 ns mask) before converting delay to k_par. A zero cut is a
    valid no-op, so a no-cut reference runs through exactly the same
    code path as every masked point."""
    from .bank.backend import require_backend_capabilities

    require_backend_capabilities(rf, {"kpar_min_fn"})
    if transition is None:
        transition = rf.DELAY_TRANSITION_FACTOR
    return rf.delay_cut_kpar_min(
        nonnegative_scalar(tau_cut_seconds, "tau_cut_seconds"),
        cosmo_fns[0], expt["nu_line"], transition=transition)
