"""The coherence gain of a persistent residual in the BAO band, and the bin fill.

The science half of the capture ruling's units (release r5.2,
``a18_units.py``; DECISIONS.md items 4, 8 and 15), with the function bodies
unchanged:

- :func:`gain_bao`: the shell average over mu in [0, 1] of
  ``(tau / T_f) sinc^2(omega tau / 2)``, ``omega = Omega k chi cos(dec) mu``,
  at k = 0.3 h/Mpc and cos dec 0.7, the gain a residual coherent for tau
  carries into the BAO band; :func:`gain_zero` is the zero-frequency block
  count the table of record books;
- :func:`bin_overlaps` and :func:`fill_factor`: how a 6 MHz band's residual,
  diluted over the redshift bins it overlaps, compares with the binding bin;
- :func:`invert_gain`: the least tau at which a non-decreasing gain reaches a
  given value (the thresholds of item 8).

The bin fill takes the per-bin tolerances as an argument (the capture
records pass the vendored references of :mod:`rfisher.tolerance.reference`).
Imports only numpy, scipy and the standard library.
"""
import functools

import numpy as np
from scipy.special import sici

TF = 16384 * 2.56e-6              # the frame the gain counts in, s (r_reference's frame seconds)
CAP = 86164.0905                  # sidereal day, s: the cap on tau
OMEGA = 2 * np.pi / CAP
K_BAO, COSD_BAO = 0.3, 0.7        # item 4: k = 0.3 h/Mpc, cos dec 0.7
NU21 = 1420.405751
ZS = np.array([0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.04, 2.20, 2.355, 2.51])   # Overview z bins


def chi_mpch(z, om=0.3158):
    zz = np.linspace(0, z, 4001); E = np.sqrt(om * (1 + zz) ** 3 + 1 - om)
    return 2997.92458 * np.trapezoid(1 / E, zz)


def z_center(ch):
    return NU21 / (473.0 + 6.0 * (ch - 14)) - 1.0


def gain_zero(tau):
    """The zero-frequency block count, as the record books it."""
    return min(tau, CAP) / TF


@functools.lru_cache(maxsize=None)
def _chi_ch(ch):
    return chi_mpch(z_center(ch))


def gain_bao(tau, ch, k=K_BAO, cosd=COSD_BAO):
    """Shell average over mu in [0, 1] of (tau / T_f) sinc^2(omega tau / 2), omega = Omega k chi cos(dec) mu."""
    tau = min(tau, CAP)
    m = k * _chi_ch(ch) * cosd; X = OMEGA * m * tau / 2.0
    if X < 1e-6: return tau / TF
    return (tau / TF) * (sici(2 * X)[0] - np.sin(X) ** 2 / X) / X


def bin_overlaps(ch):
    lo, hi = 470.0 + 6.0 * (ch - 14), 476.0 + 6.0 * (ch - 14); out = {}
    for b in range(len(ZS) - 1):
        f_lo, f_hi = NU21 / (1 + ZS[b + 1]), NU21 / (1 + ZS[b])
        ov = min(hi, f_hi) - max(lo, f_lo)
        if ov > 1e-9: out[b] = (ov, f_hi - f_lo)
    return out


def fill_factor(ch, lam_dep, lb):
    """lambda / min_b (lambda_b / f_b): the factor a footprint-diluted residual carries against the binding bin, for
    the per-bin tolerances lb ({bin: lambda_b}) of the world the band's lambda is read in."""
    return lam_dep / min(lb[b] / (o / w) for b, (o, w) in bin_overlaps(ch).items())


def invert_gain(G_needed, gain):
    """Least tau in (0, CAP] with gain(tau) >= G_needed for a non-decreasing gain, or None if gain(CAP) < G_needed."""
    if gain(CAP) < G_needed: return None
    lo, hi = 0.0, CAP
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if gain(mid) >= G_needed: hi = mid
        else: lo = mid
    return hi
