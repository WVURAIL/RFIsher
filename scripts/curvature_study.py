#!/usr/bin/env python3
"""Measure the local background polynomial around each pilot, and price the
declined +/-2,+/-4 Richardson reference design against measurement.

The symmetric pair cancels odd orders exactly; what survives is curvature:
the pair's background estimate is biased by  eps = a2*Delta^2  (fraction of
the local level) at reference distance Delta = 6.104 kHz. The Richardson
design (weights 4/3, -1/3 at +/-2, +/-4 bins) would null a2 and leave
-4*a4*Delta^4. This script fits the archive-averaged within-channel
spectrum (products' integrated_spectrum_before_mask) on the flanks
5-12 kHz either side of the pilot (excluding the pilot cluster and any
secondary forest) and reports each term as a fraction of the background,
to be compared against the eta - 1 = 1% decision knee and the measured
null widths.

    python3 scripts/curvature_study.py
"""
from __future__ import annotations
import numpy as np
DF = 390.625e3 / 16384            # 23.84 Hz per spectrum bin
DELTA = 2 * 390.625e3 / 128       # 6.104 kHz reference distance
WIN = 390.625e3 / 128             # 3.05 kHz window integration width
FIT_IN, FIT_OUT = 5e3, 12e3       # fit annulus: past the cluster, local

from rfisher import products
PRODUCTS = products.paths()
NBINS = 16384
DC_GUARD = 100                    # bins around the FFT DC artifact to distrust
CLUSTER = 209                     # 5 kHz: the pilot cluster the anchor lives in


def spectrum_fields(path):
    """The four fields this study reads, loaded without pickle.

    ``rfisher.npzio.load_npz`` materialises every field, which was free for the
    32 MB products of the superseded cohort but costs a 768 MB read and roughly
    4 GB of resident frame spectra per channel in the current v5 rebuild
    (``du -sh`` on 844.npz: 32M then, 768M now). This study only needs the
    archive-averaged spectrum and the three pieces of geometry that locate the
    pilot in it, so it takes those and leaves the per-frame cube on disk. The
    pickle refusal and the closed handle are kept for the same reason npzio
    keeps them: survey products are external inputs.
    """
    with np.load(path, allow_pickle=False) as archive:
        return {name: np.array(archive[name], copy=True)
                for name in ("integrated_spectrum_before_mask",
                             "pilot_frequency_hz", "chime_frequency_hz",
                             "sense")}


def main():
    from scipy.ndimage import median_filter
    print(f"reference distance Delta = {DELTA/1e3:.3f} kHz; fit annulus "
          f"{FIT_IN/1e3:.0f}-{FIT_OUT/1e3:.0f} kHz both sides\n")
    print(f"{'ch':>3} {'slope a1*D':>11} {'curv a2*D^2':>12} "
          f"{'rich 4a4*D^4':>13} {'direct pair':>12} {'clip%':>6}"
          "   (fractions of local background)")
    res = []
    for ch, p in sorted(PRODUCTS.items()):
        d = spectrum_fields(p)
        s = d["integrated_spectrum_before_mask"].astype(float)
        dfhz = (float(d["pilot_frequency_hz"][0])
                - float(d["chime_frequency_hz"][0]))
        nom = int(round(int(d["sense"]) * dfhz / DF)) % NBINS
        idx = np.arange(NBINS)
        # The spectral axis is cyclic, so bin distance is measured the short way
        # round; a channel whose pilot sits near bin 0 (ch14's is at bin 128)
        # otherwise loses its lower reference off the end of the array and gets
        # a one-sided fit. The same wrap keeps the DC artifact outside both the
        # anchor search and the fit: it is a frame artifact, it can exceed the
        # archive-averaged pilot (ch14, 5.6e14 at bin 0 against 2.7e14 at bin
        # 128), and a plain argmax over a clipped window locks onto it.
        clear = (idx > DC_GUARD) & (idx < NBINS - DC_GUARD)

        def cyclic(center):
            return ((idx - center + NBINS // 2) % NBINS - NBINS // 2) * DF

        win = (np.abs(cyclic(nom)) <= CLUSTER * DF) & clear
        pk = int(idx[win][np.argmax(s[win])])   # metadata-anchored
        off = cyclic(pk)
        sm = median_filter(s, 21)            # suppress narrow lines
        m = ((np.abs(off) >= FIT_IN) & (np.abs(off) <= FIT_OUT)
             & clear)                        # keep clear of the DC artifact
        x, y = off[m] / DELTA, sm[m]
        b0 = np.median(y)
        yn = y / b0
        keep = np.ones(len(x), bool)
        for _ in range(4):                   # sigma-clip residual structure
            c = np.polynomial.polynomial.polyfit(x[keep], yn[keep], 4)
            r = yn - np.polynomial.polynomial.polyval(x, c)
            keep = np.abs(r) < 3 * np.std(r[keep])
        a1, a2, a4 = c[1], c[2], c[4]

        def wavg(f0):
            w = (np.abs(off - f0) <= WIN / 2) & clear
            return s[w].mean() if w.any() else np.nan

        center = np.polynomial.polynomial.polyval(0.0, c) * b0
        direct = (0.5 * (wavg(DELTA) + wavg(-DELTA)) - center) / center
        res.append((ch, a1, a2, -4 * a4, direct))
        print(f"{ch:>3} {a1:>11.2e} {a2:>12.2e} {-4*a4:>13.2e} "
              f"{direct:>12.2e} {1-keep.mean():>6.1%}")
    a2s = [abs(r[2]) for r in res]
    ds = [abs(r[4]) for r in res]
    print(f"\nsmooth curvature |a2*D^2|: median {np.median(a2s):.1e}, worst "
          f"{max(a2s):.1e} (ch{res[int(np.argmax(a2s))][0]});  knee = 1e-2")
    print(f"direct pair bias:          median {np.median(ds):.1e}, worst "
          f"{max(ds):.1e} (ch{res[int(np.argmax(ds))][0]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
