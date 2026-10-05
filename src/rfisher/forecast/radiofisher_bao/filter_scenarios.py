"""The delay-filter scenarios of the forecast and their assumed suppression.

A scenario names a delay-filter cut and the response bank that prices the
cosmological modes the cut removes (``kfg_fac = tau_cut * bandwidth``). Its
suppression S is a separate, hypothetical assumption about how much of the
residual the filter would remove; it is not measured and not a consequence of
the delay-to-wavenumber map. S is listed beside every tolerance and is never
folded into one. Which scenario a verdict rests on is the science profile's
choice (its ``role``); no rule reads a sensitivity scenario.

The delay filter enters the forecast only through the ``kfg_fac`` response
banks and S; the backend has no delay-cut hook. The digitised filter response
of the CHIME 2025 detection (Fig. 10) stays in package data.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from rfisher import policy

# Delay-filter suppression of the residual, dB, as a function of which BAO
# feature the filter must preserve. Derived from the k_par <-> delay relation
# k_par = 2 pi nu_21 H0 E(z) tau / [c (1 + z)^2] (Amiri et al. 2023, Eq. 64)
# evaluated at the profile's report band. Preserving a *larger* scale (lower k_par, the
# first acoustic peak) forces a shorter delay cutoff and buys less suppression.
DELAY_SUPPRESSION_DB = {
    "none": 0.0,                # claim no foreground-removal help (default)
    "aggressive_200ns": 11.4,   # CHIME's deployed tau_cut = 200 ns
    "bao_peak2": 8.2,           # second acoustic peak, tau ~ 104 ns
    "bao_peak1": 3.6,           # first acoustic peak, tau ~ 56 ns
}
# Default to claiming nothing. The delay filter is a foreground-removal stage,
# and the forecast this feeds follows the Overview paper's Figure 31
# convention: thermal noise from Tsys and nothing else: no foreground
# residual, no wedge, BAO-shift only. Crediting the chain with a filter the
# forecast does not model would take suppression from a stage that is not in
# the budget. The non-zero entries stay available as an explicit opt-in and
# bound the help that *could* be claimed if the filter were modelled on both
# sides. Note the direction: claiming nothing makes every residual larger,
# which is the conservative direction for a contamination budget.
DEFAULT_DELAY_KEY = str(policy.value("transfer.delay_suppression.default_key"))
if DEFAULT_DELAY_KEY not in DELAY_SUPPRESSION_DB:
    raise RuntimeError("default delay scenario is not defined")


@dataclass(frozen=True)
class FilterScenario:
    """A delay-filter cut, the response bank that prices it, and its S key."""

    name: str
    bank: str
    kfg_fac: float | None
    suppression_key: str


# The four scenarios, in the order every table lists them. ``none`` is the
# no-filter bank; the others cut the modes a delay filter removes when it
# preserves the first acoustic peak (55 ns), the second (110 ns), or runs at
# CHIME's deployed 200 ns.
SCENARIOS = (
    FilterScenario("none", "fisher_bank_chime2022_pres_dense.npz", None,
                   "none"),
    FilterScenario("peak1", "fisher_bank_chime2022_pres_kfg22_dense.npz",
                   22.0, "bao_peak1"),
    FilterScenario("peak2", "fisher_bank_chime2022_pres_kfg44_dense.npz",
                   44.0, "bao_peak2"),
    FilterScenario("deployed", "fisher_bank_chime2022_pres_kfg80_dense.npz",
                   80.0, "aggressive_200ns"),
)


def scenario(name: str) -> FilterScenario:
    """The scenario of this name."""
    for item in SCENARIOS:
        if item.name == name:
            return item
    raise KeyError(f"unknown filter scenario {name!r}; choose from "
                   f"{[item.name for item in SCENARIOS]}")


def suppression_db(name: str) -> float:
    """Hypothetical suppression assigned to a scenario, not a measured transfer."""
    key = scenario(name).suppression_key
    return 0.0 if key == "none" else float(DELAY_SUPPRESSION_DB[key])


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
