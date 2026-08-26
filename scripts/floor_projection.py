#!/usr/bin/env python3
"""What would have to be true for the mask to clear the bias tolerance.

The measured verdict is negative. On every channel with a measured kept-frame
floor, the pilot-proxy mask leaves a residual above the tolerance, because
the mask cannot remove contamination the detector cannot see, so the residual
is floored by detection sensitivity, and after coherence amplification that
floor is still too high.

That is a statement about the *bootstrap coarse rule*, which is what produced
the survey products: it decides on the coarse axis, roughly 10 dB less
sensitive than the fine coherent stage the detector is designed around. This
script asks what the remaining gap is in terms anyone can check, by walking
each channel through the improvements that are actually on the table and
marking where it crosses.

Every step here is a *conditional* rather than a measurement, and the output labels
them as such. The point is not to rescue the verdict; it is to say precisely
how far away it is and which of the open items would close it.

    python3 scripts/floor_projection.py
"""
from __future__ import annotations

import argparse


import numpy as np


from rfisher import products as _products
from rfisher import residual as R
from rfisher import selection_policy
from rfisher.tolerances import TOL_APERP, TOL_FS8

# The rounded screening credit and its lower development sensitivity check.
_FINE_CREDIT = selection_policy.decision("transfer.fine_stage_credit_db")
FINE_GAIN_DB = float(_FINE_CREDIT.value)
FINE_SENSITIVITY_DB = tuple(
    float(value) for value in _FINE_CREDIT.sensitivity_values
    if float(value) != FINE_GAIN_DB)
DEFAULT_CHANNELS = tuple(int(value) for value in selection_policy.value(
    "archive_reference.floor_projection_channels"))
TOLERANCE_TARGET = str(selection_policy.value(
    "archive_reference.floor_projection_tolerance_target"))
_TOLERANCE_TABLES = {"aperp": TOL_APERP, "fs8": TOL_FS8}
if TOLERANCE_TARGET not in _TOLERANCE_TABLES:
    raise RuntimeError("floor-projection tolerance target is not defined")
TOLERANCES = _TOLERANCE_TABLES[TOLERANCE_TARGET]
PRIMARY_ZETA = float(selection_policy.value(
    "science.systematic_budget.primary_zeta"))
PROJECTION_SCENARIOS = tuple(selection_policy.value(
    "archive_reference.floor_projection_scenarios"))
PERSISTENCE_REFERENCE_CHANNEL = int(selection_policy.value(
    "archive_reference.floor_projection_persistence_reference_channel"))
_PROJECTION_LABELS = {
    "coarse": "coarse (now)",
    "fine": "+fine stage",
    "fine_plus_bao_peak1": "+fine +1st peak",
    "fine_plus_bao_peak2": "+fine +2nd peak",
}
_PROJECTION_CREDITS = {
    "coarse": 0.0,
    "fine": FINE_GAIN_DB,
    "fine_plus_bao_peak1": (
        FINE_GAIN_DB + R.DELAY_SUPPRESSION_DB["bao_peak1"]),
    "fine_plus_bao_peak2": (
        FINE_GAIN_DB + R.DELAY_SUPPRESSION_DB["bao_peak2"]),
}
if any(key not in _PROJECTION_CREDITS for key in PROJECTION_SCENARIOS):
    raise RuntimeError("floor-projection scenario is not defined")


def channel_state(npz):
    st = R.shelf_statistics(npz)
    corr = R.correlation_time(npz)
    # One booking for the whole package: a refused tau_c takes no
    # ground-filter credit (see residual.surviving_components).
    gain = sum(f * n for f, n in R.surviving_components(st, corr))
    return st, corr, gain


def r_at(floor_db, gain, extra_db=0.0):
    return 10.0 ** ((floor_db - extra_db) / 10.0) * gain


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--products", nargs="+",
                    default=[p for _c, p in sorted(_products.paths(
                        channels=DEFAULT_CHANNELS,
                        announce=False).items())])
    args = ap.parse_args(argv)

    checks = ", ".join(f"{value:g}" for value in FINE_SENSITIVITY_DB)
    print(f"bias tolerance: channel-specific {TOLERANCE_TARGET}, "
          f"zeta = {PRIMARY_ZETA:g}")
    print(f"fine-stage credit: {FINE_GAIN_DB:g} dB rounded screening scenario; "
          f"development checks: {checks} dB\n")

    measured, unmeasured = [], []
    for path in args.products:
        st, corr, gain = channel_state(path)
        (measured if np.isfinite(st.floor_db) else unmeasured).append(
            (st, corr, gain))

    print("MEASURED FLOORS: these carry verdicts")
    scenario_header = " ".join(
        f"{_PROJECTION_LABELS[key]:>17}" for key in PROJECTION_SCENARIOS)
    print(f"  {'ch':>3} {'tau_c':>14} {'gain':>10} {scenario_header}")
    for st, corr, gain in measured:
        tolerance = TOLERANCES[st.channel]
        row = [f"  {st.channel:3d}"]
        tau = (f"{corr.tau_for_budget/60:.0f} min" if corr.tau_for_budget < 3600
               else f"{corr.tau_for_budget/3600:.1f} h")
        row.append(f"{tau + ('' if corr.quality == 'measured' else '*'):>14}")
        row.append(f"{gain:10.4g}")
        for scenario in PROJECTION_SCENARIOS:
            extra = _PROJECTION_CREDITS[scenario]
            r = r_at(st.floor_db, gain, extra)
            mark = "PASS" if r <= tolerance else f"x{r/tolerance:,.0f}"
            row.append(f"{r:8.3g} {mark:>7s}")
        print(" ".join(row))
    print("  * tau_c is a bound (refused or bounded-above), so the row is a "
          "bound on r rather than a measurement")

    print("\nUNMEASURED FLOORS: no verdict is available")
    for st, corr, gain in unmeasured:
        tolerance = TOLERANCES[st.channel]
        need = 10.0 * np.log10(tolerance / gain)
        print(f"  ch{st.channel}: no null population ({st.n_off_frames} frames). "
              f"Would need a floor below {need:.1f} dB to clear the tolerance "
              f"at the present gain of {gain:.4g}.")

    # ---- the other lever: tau_c ----------------------------------------
    reference = next(
        (row for row in measured
         if row[0].channel == PERSISTENCE_REFERENCE_CHANNEL), None)
    if reference is None:
        print(f"\nChannel {PERSISTENCE_REFERENCE_CHANNEL} is unavailable; "
              "the data-derived persistence bound cannot be shown.")
        return 0
    tau_reference = reference[1].tau_for_budget
    tau_minutes = tau_reference / 60.0
    print("\nTHE OTHER LEVER. Two channels sit at the sidereal cap because "
          "tau_c was refused.\nSubstituting the measured upper bound from "
          f"channel {PERSISTENCE_REFERENCE_CHANNEL} "
          f"(tau_c <= {tau_minutes:g} min) in place of the cap:")
    for st, corr, gain in measured:
        if (corr.quality == "measured"
                or corr.tau_for_budget <= tau_reference):
            continue
        # The what-if books through the shared discipline: on a refused
        # channel the assumed timescale narrows the cap but the invalidated
        # split stays uncredited at the reference timescale.
        g2 = sum(f * n for f, n in
                 R.surviving_components(
                     st, corr, tau_intraday=tau_reference))
        tolerance = TOLERANCES[st.channel]
        for label, extra in (("as-is", 0.0), ("+fine", FINE_GAIN_DB)):
            r = r_at(st.floor_db, g2, extra)
            mark = "PASS" if r <= tolerance else f"x{r/tolerance:,.0f} over"
            print(f"  ch{st.channel} with tau_c <= {tau_minutes:g} min, "
                  f"{label:6s}: "
                  f"gain {g2:9.4g}  r = {r:9.3g}  {mark}")
    print("\nThat substitution is a what-if rather than a measurement. It is listed "
          "because it identifies\nwhich open item moves the verdict most: on "
          "these channels tau_c does rather than the floor.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
