#!/usr/bin/env python3
"""Per-channel working threshold, priced against BAO residual tolerance.

``mu`` says where the null is; it does not say how far above the null the
threshold belongs.  That is a science question, and it is answered exactly
the way ``RFIsher/scripts/optimal_thresholds.py`` answers it:
minimise the survey-time cost

    T / T_clean = (1 + r) / (1 - f)

over the threshold family ``F > eta * mu``, subject to the bias tolerance
``r <= r_tol``, with the rounded fine-stage screening credit applied to
the bound.  ``r`` grows with ``eta`` and ``f`` shrinks with it, so the
minimum is interior wherever the residual is large enough to matter -- and
where it is not, no masking pays and the tolerance alone sets the ceiling.

Two things make the answer per-channel rather than global:

* each channel's own occupancy and residual, which differ by orders of
  magnitude across the band;
* each channel's own tolerance, from the redshift bins its 6 MHz allocation
  overlaps (``tolerances.py``).  Both tiers are carried: the acoustic
  dilation tolerance the released selector constrains on, and the stricter
  growth-rate tolerance the dissertation's verdicts quote.

Everything is evaluated on the latest era only, through a single-era product
view (``ppcal.era_view``).

**Adopted floor basis: the quiet era, which is the bounded choice.**  Three
bases are available and they do not agree:

* the product's own kept-frame floor (the ``mu0`` sliver, 1 < F <= mu0).
  ``rfisher.residual.FloorProvenance`` shows this one is fixed by the weight
  bank rather than by the sky -- it lands on 10log10(mu0 - 1) plus a constant
  offset -- and it is the *lowest* of the three, so it is the least
  conservative.
* the sigma-implied level, the excess a threshold sitting at the null centre
  can actually resolve.  Defensible everywhere, including the channels where
  mu0 < 1 leaves the sliver empty for any dataset.
* the registered upper shelf percentile of the channel's own quietest era:
  a measurement taken on
  frames the transmitter was demonstrably off for, and the *highest* of the
  three, so the most conservative.

This run takes the quiet era wherever the channel has one and falls back to
the sigma-implied substitute where it does not, which on this archive is
exactly the five always-on carriers (ch17, 22, 24, 30, 31 -- ch35 has a
pre-sign-on quiet era).  Both choices push the residual up rather than down,
so the floor is bounded in the same one-sided sense as the coherence cap
below, and ``note`` records per channel which basis a row used.

**Adopted basis: measured value, resolved upper bound, or cap.**  The residual
depends on how long contamination stays coherent.  A measured value is used
when the estimator resolves one, and a shortest-lag crossing is carried as an
upper bound.  A refusal is evaluated at the sidereal-day cap, which is the
physical ceiling: anything longer-lived has already been removed as m = 0.
Since tau_cap >= tau_true, and the coherent amplification n_coh grows with
tau, the residual reported at the cap is an **upper bound** on the true
residual, not an estimate of it.

Two consequences follow, and both matter for how the columns are read:

* ``r > r_tol`` at an adopted upper bound does **not** demonstrate that a
  channel violates its tolerance.  It demonstrates that the tolerance is
  *not certified* on present evidence.  A tighter coherence result can only
  lower the residual, so it can only enlarge the feasible set.
* Nothing in the keep/excise disposition rests on this.  Every excised
  channel fails on carrier dominance -- the densest population in its latest
  era is the carrier, so no null exists to threshold against -- which is a
  tau-free measurement.  The bound governs what the kept channels cost, not
  which channels are kept.

The thermal end (one frame, n_coh = 1) is carried alongside as the
optimistic limit, so the width of the bracket is visible; it is not the
operating basis.  ``residual_basis`` names, per channel, which of the two a
row's adopted-coherence numbers actually rest on.

**What an exact residual still needs**, in descending order of how much it
would move the answer:

1. a usable coherence result per channel.  Refused channels sit at the
   sidereal-day cap, and the bracket between that and the thermal limit spans
   four to six orders of magnitude -- far more than any other term here.  The
   acquisition is specified but not scheduled.
2. a directly measured sensitivity floor, from a control-frequency or null
   trawl, rather than one bounded from whichever era happened to be quietest.
   This matters most on the five always-on carriers, which have no quiet era
   at all and therefore no floor measurement of any kind.
3. the pilot-to-shelf transfer, which is assumed exact here through the ATSC
   constants and is the one step in the chain with no error bar attached.

Until those land, every residual this script reports is an upper limit, and
every verdict that depends on one is "not certified" rather than "failed".

    python3 scripts/calibrated_thresholds.py [--products DIR] [--out DIR]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import inspect
import os
import sys
import tempfile

# This is the tolerance-layer half of the calibration suite and belongs in
# RFIsher; the calibration package it reads products through
# lives in pilot-proxy, which owns the products. Point PP_ANALYSIS at that
# repo's analysis/ directory (and PP_SRC at its src/) to relocate either.
sys.path.insert(0, os.environ.get(
    "PP_SRC", os.path.expanduser("~/rail/pilot-proxy/src")))
sys.path.insert(0, os.environ.get(
    "PP_ANALYSIS", os.path.expanduser("~/rail/pilot-proxy/analysis")))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

try:
    from ppcal import era_view  # noqa: F401
except ImportError as exc:                # pragma: no cover - setup guidance
    raise SystemExit(
        "this script reads per-pilot products through the calibration package "
        "`ppcal`, which lives in pilot-proxy (the repository that owns the "
        "products). Point PP_ANALYSIS at that repo's analysis/ directory and "
        "PP_SRC at its src/, e.g.\n"
        "  export PP_ANALYSIS=~/rail/pilot-proxy/analysis\n"
        "  export PP_SRC=~/rail/pilot-proxy/src\n"
        f"underlying import error: {exc}") from exc

from rfisher import residual  # noqa: E402
from rfisher import selection_policy  # noqa: E402
from rfisher import thresholds  # noqa: E402
from rfisher import tolerances  # noqa: E402
from rfisher.constants import CHIME_FRAME_SECONDS  # noqa: E402

from ppcal import eras  # noqa: E402
from ppcal.calib import calibrate  # noqa: E402
from ppcal.products import Channel, load_all, product_paths  # noqa: E402
from channel_tolerances import channel_tolerances  # noqa: E402

_ETA_POINT, _ETA_START, _ETA_STOP, _ETA_COUNT = selection_policy.value(
    "archive_reference.calibrated_eta_geometric_segment")
ETA_GRID = np.concatenate([
    [_ETA_POINT], np.geomspace(_ETA_START, _ETA_STOP, int(_ETA_COUNT))])
FINE_DB = float(selection_policy.value("transfer.fine_stage_credit_db"))
PLATEAU = thresholds.COST_PLATEAU
ERA_POINT_FIELDS = (
    "channel", "era", "eta_basis", "masked_fraction", "r_over_rtol",
    "best_cost_masked_fraction", "best_cost_r_over_rtol", "tau_seconds",
    "tau_quality", "floor_basis", "floor_era", "floor_frames", "floor_db",
    "r_tol_dilation", "r_eta1_adopted", "r_cost_adopted", "product_file",
    "product_sha256", "product_schema", "detector_version",
    "generator_sha256", "analysis_source_sha256",
)
def load_channels(directory, only=None):
    """Load all channels, or only the requested physical channels."""
    if only is None:
        return load_all(directory)
    selected = []
    for path in product_paths(directory):
        with np.load(path, allow_pickle=False) as data:
            ch = int(np.asarray(data["physical_channel"]).flat[0])
        if ch in only:
            selected.append(Channel(path))
    found = {c.ch for c in selected}
    missing = sorted(only - found)
    if missing:
        raise SystemExit("requested channel products not found: %s" %
                         ", ".join(str(ch) for ch in missing))
    return selected


def residual_basis(tau_quality):
    """Describe the coherence value used by the residual budget."""
    if tau_quality == "measured":
        return "measured tau"
    if tau_quality == "bounded_above":
        return "upper bound on tau"
    if tau_quality == "refused":
        return "upper bound (tau at sidereal cap)"
    return "unavailable"


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def analysis_source_sha256():
    """Hash the source files used by this export."""
    sources = {
        "generator": __file__,
        "rfisher.residual": residual.__file__,
        "rfisher.selection_policy": selection_policy.__file__,
        "rfisher.thresholds": thresholds.__file__,
        "rfisher.tolerances": tolerances.__file__,
        "ppcal.era_view": era_view.__file__,
        "ppcal.eras": eras.__file__,
        "ppcal.calib": inspect.getsourcefile(calibrate),
        "ppcal.products": inspect.getsourcefile(Channel),
        "channel_tolerances": inspect.getsourcefile(channel_tolerances),
    }
    digest = hashlib.sha256(b"calibrated-era-source-v2\0")
    for label, path in sorted(sources.items()):
        if not path:
            raise ValueError(f"source path unavailable for {label}")
        digest.update(label.encode("utf-8") + b"\0")
        digest.update(bytes.fromhex(file_sha256(path)))
    return digest.hexdigest()


def product_identity(path):
    with np.load(path, allow_pickle=False) as data:
        return {
            "product_file": os.path.basename(path),
            "product_sha256": file_sha256(path),
            "product_schema": str(np.asarray(data["schema_version"]).item()),
            "detector_version": str(
                np.asarray(data["detector_version"]).item()),
        }


def eta1_row(rows):
    matches = [row for row in rows
               if row["eta_mu"] == float(_ETA_POINT)]
    if len(matches) != 1:
        raise ValueError("the calibrated eta_mu=1 row is unavailable")
    return matches[0]


def era_point_record(rec):
    """Build the compact current-era figure row."""
    if rec.get("eta1_status_adopted") != "evaluated":
        raise ValueError(
            f"channel {rec['ch']} has no calibrated eta_mu=1 row")
    values = {
        "channel": str(rec["ch"]),
        "era": rec["era"],
        "eta_basis": "eta_mu_1",
        "masked_fraction": rec["mask_eta1_adopted"],
        "r_over_rtol": rec["r_eta1_adopted"] / rec["r_tol_dilation"],
        "best_cost_masked_fraction": rec["mask_cost_adopted"],
        "best_cost_r_over_rtol": (
            rec["r_cost_adopted"] / rec["r_tol_dilation"]),
        "tau_seconds": rec["tau_seconds"],
        "tau_quality": rec["tau_quality"],
        "floor_basis": rec["floor_basis"],
        "floor_era": rec["floor_era"],
        "floor_frames": rec["floor_frames"],
        "floor_db": rec["floor_db"],
        "r_tol_dilation": rec["r_tol_dilation"],
        "r_eta1_adopted": rec["r_eta1_adopted"],
        "r_cost_adopted": rec["r_cost_adopted"],
        "product_file": rec["product_file"],
        "product_sha256": rec["product_sha256"],
        "product_schema": rec["product_schema"],
        "detector_version": rec["detector_version"],
        "generator_sha256": rec["generator_sha256"],
        "analysis_source_sha256": rec["analysis_source_sha256"],
    }
    return {
        key: (f"{value:.10g}" if isinstance(value, float) else value)
        for key, value in values.items()
    }


def write_csv_atomic(path, fieldnames, rows):
    """Replace a CSV only after a complete write."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{os.path.basename(path)}.", dir=directory, text=True)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=fieldnames, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def write_era_points(path, rows):
    """Write compact rows used by the dissertation figures."""
    records = [era_point_record(row) for row in rows]
    write_csv_atomic(path, ERA_POINT_FIELDS, records)


def r_tolerances():
    """{ch: (r_tol_dilation, r_tol_growth)}.

    Every channel's dilation tolerance comes from the one stable table
    (rfisher.tolerances.TOL_APERP): the stable zeta = 1 minima of the dense
    bias-response bank, the same convention for upper and lower band. The
    retired practice of extending ch14-26 from the completed-forecast
    ledger's single 1-on-sky-year point screened the lower band against
    tolerances up to ~1.8x looser than the published channels'. The ledger
    still supplies the growth tolerance and the bin edges.
    """
    derived = channel_tolerances()
    out = {}
    for ch, rec in derived.items():
        dil = tolerances.TOL_APERP.get(ch, rec["aperp"])
        out[ch] = (dil, rec["fs8"], rec["z_low"], rec["z_high"],
                   ch in tolerances.TOL_APERP)
    return out


def sweep(c, segs, fmask, mu, tau):
    """Threshold sweep over the latest era on the calibrated ``mu`` scale."""
    scale = mu / c.mu0
    floor_policy = selection_policy.quiet_floor_kwargs()
    floor_percentile = float(floor_policy["percentile"])
    floor_label = f"p{floor_percentile:g}"
    floor_db, floor_era, n_floor = era_view.quiet_era_floor_db(
        c, segs, **floor_policy)
    if np.isfinite(floor_db):
        note = "floor from era %s (%d frames, %s %.2f dB)" % (
            floor_era, n_floor, floor_label, floor_db)
        floor_info = {
            "floor_basis": "quiet_era_" + floor_label,
            "floor_era": floor_era,
            "floor_frames": int(n_floor),
            "floor_db": float(floor_db),
        }
    else:
        try:
            fp = residual.floor_provenance(c.path)
            floor_db = fp.sigma_implied_db
            note = ("floor substituted: sigma-implied %.2f dB (no quiet era)"
                    % floor_db)
            floor_info = {
                "floor_basis": "sigma_implied",
                "floor_era": "",
                "floor_frames": "",
                "floor_db": float(floor_db),
            }
        except Exception as exc:                   # noqa: BLE001
            return [], "no floor available: %s" % exc, {
                "floor_basis": "unavailable", "floor_era": "",
                "floor_frames": "", "floor_db": "",
            }
    try:
        with era_view.era_product_view(c, fmask) as view:
            rows = residual.threshold_sweep(
                view, etas=ETA_GRID * scale,
                tau_intraday=tau, floor_db=floor_db)
    except Exception as exc:                       # noqa: BLE001
        return [], "sweep failed: %s" % exc, floor_info
    credit = 10.0 ** (FINE_DB / 10.0)
    for r in rows:
        r["eta_mu"] = r["eta"] / scale
        r["r_fine"] = r["r_masked"] / credit
        r["penalty"] = ((1.0 + r["r_fine"]) / (1.0 - r["f"])
                        if r["f"] < 1.0 else float("inf"))
    return rows, note, floor_info


def select(rows, r_tol=None):
    """Cheapest threshold, smallest eta on a 2% cost plateau.

    With ``r_tol`` the choice is restricted to thresholds that meet the
    tolerance; without it the cost optimum is returned unconstrained, which
    is the per-channel operating point the survey-time trade alone picks and
    is defined even where no threshold meets the bound.
    """
    ok = rows if r_tol is None else [r for r in rows if r["r_fine"] <= r_tol]
    if not ok:
        return None
    best = min(r["penalty"] for r in ok)
    near = [r for r in ok if r["penalty"] <= best * PLATEAU]
    return min(near, key=lambda r: r["eta_mu"])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--products", default=os.environ.get("PP_PER_PILOT"))
    ap.add_argument("--out", default=os.environ.get(
        "PP_CALIB_OUT", os.path.join(ROOT, "out")))
    ap.add_argument("--only", default=None)
    ap.add_argument("--era-points", default=None,
                    help="write compact current-era figure rows")
    args = ap.parse_args(argv)
    if not args.products:
        raise SystemExit("pass --products, or set PP_PER_PILOT, to the "
                         "directory of per-pilot survey products")

    tol = r_tolerances()
    only = ({int(x) for x in args.only.split(",")} if args.only else None)
    if args.era_points and only is None:
        ap.error("--era-points requires --only")
    rows = []
    source_digest = analysis_source_sha256()
    print("%3s %-9s %10s %10s | %8s %8s %9s %9s | %8s %8s | %s"
          % ("ch", "z range", "r_tol_dil", "r_tol_gro", "eta_cost", "mask",
             "penalty", "r/r_dil", "eta_feas", "mask", "tau"))
    for c in sorted(load_channels(args.products, only), key=lambda c: c.ch):
        segs = eras.segment(c, **selection_policy.era_kwargs())
        fmask = eras.final_era_frame_mask(c, segs)
        cal = calibrate(c, fmask, segs[-1].label, 0)
        dil, gro, z_lo, z_hi, published = tol.get(
            c.ch, (float("nan"),) * 2 + (float("nan"),) * 2 + (False,))

        rec = dict(ch=c.ch, era=segs[-1].label, mu=cal.mu, z_low=z_lo,
                   z_high=z_hi, r_tol_dilation=dil, r_tol_growth=gro,
                   dilation_tol_published=published, note="",
                   generator_sha256=file_sha256(__file__),
                   analysis_source_sha256=source_digest,
                   **product_identity(c.path))
        try:
            with era_view.era_product_view(c, fmask) as view:
                corr = residual.correlation_time(view)
            rec["tau_seconds"] = float(corr.tau_for_budget)
            rec["tau_measured"] = bool(corr.is_measured)
            rec["tau_quality"] = corr.quality
            rec["tau_reason"] = corr.reason
        except Exception as exc:                   # noqa: BLE001
            rec["tau_seconds"], rec["tau_measured"] = "", False
            rec["tau_quality"] = "unavailable"
            rec["tau_reason"] = str(exc)
        rec["residual_basis"] = residual_basis(rec["tau_quality"])

        for tag, tau in (("adopted", None), ("thermal", CHIME_FRAME_SECONDS)):
            s, note, floor_info = sweep(c, segs, fmask, cal.mu, tau)
            rec.update(floor_info)
            if note:
                rec["note"] = note
            if not s:
                rec["eta1_status_%s" % tag] = "unavailable"
                continue
            try:
                eta1 = eta1_row(s)
            except ValueError:
                rec["eta1_status_%s" % tag] = "unavailable"
            else:
                rec["eta1_status_%s" % tag] = "evaluated"
                rec["mask_eta1_%s" % tag] = eta1["f"]
                rec["r_eta1_%s" % tag] = eta1["r_fine"]
                rec["r_unmasked_%s" % tag] = eta1["r_unmasked"]
            rec["r_floor_%s" % tag] = min(r["r_fine"] for r in s)
            cost = select(s)                       # unconstrained cost optimum
            if cost is not None:
                rec["eta_cost_%s" % tag] = cost["eta_mu"]
                rec["mask_cost_%s" % tag] = cost["f"]
                rec["penalty_cost_%s" % tag] = cost["penalty"]
                rec["r_cost_%s" % tag] = cost["r_fine"]
            for tier, rt in (("dilation", dil), ("growth", gro)):
                pick = select(s, rt)
                pre = "%s_%s" % (tier, tag)
                if pick is None:
                    rec["eta_" + pre] = ""
                    rec["mask_" + pre] = ""
                    rec["penalty_" + pre] = ""
                    rec["r_" + pre] = ""
                else:
                    rec["eta_" + pre] = pick["eta_mu"]
                    rec["mask_" + pre] = pick["f"]
                    rec["penalty_" + pre] = pick["penalty"]
                    rec["r_" + pre] = pick["r_fine"]

        def num(key, fmt):
            v = rec.get(key, "")
            return (fmt % v) if isinstance(v, float) else "-"

        rr = rec.get("r_cost_adopted")
        tau = rec["tau_seconds"]
        tau_text = ("%.0f s" % tau) if isinstance(tau, float) else "-"
        print("%3d %4.2f-%4.2f %10.3g %10.3g | %8s %8s %9s %9s | %8s %8s | "
              "%8s %-13s %s"
              % (c.ch, z_lo, z_hi, dil, gro,
                 num("eta_cost_adopted", "%.3f"),
                 num("mask_cost_adopted", "%.4f"),
                 num("penalty_cost_adopted", "%.4g"),
                 ("%.3g" % (rr / dil)) if isinstance(rr, float) else "-",
                 num("eta_dilation_adopted", "%.3f"),
                 num("mask_dilation_adopted", "%.4f"),
                 tau_text, rec["tau_quality"],
                 rec["note"][:30]))
        rows.append(rec)

    cols = ["ch", "era", "mu", "z_low", "z_high", "r_tol_dilation",
            "r_tol_growth", "dilation_tol_published", "tau_seconds",
            "tau_measured", "tau_quality", "tau_reason", "residual_basis",
            "product_file", "product_sha256", "product_schema",
            "detector_version", "generator_sha256",
            "analysis_source_sha256", "floor_basis",
            "floor_era", "floor_frames", "floor_db",
            "eta_cost_adopted", "mask_cost_adopted",
            "penalty_cost_adopted", "r_cost_adopted",
            "eta_cost_thermal", "mask_cost_thermal", "penalty_cost_thermal",
            "r_cost_thermal", "r_unmasked_adopted", "r_floor_adopted",
            "eta1_status_adopted", "mask_eta1_adopted", "r_eta1_adopted",
            "eta_dilation_adopted", "mask_dilation_adopted",
            "penalty_dilation_adopted", "r_dilation_adopted",
            "eta_growth_adopted", "mask_growth_adopted",
            "penalty_growth_adopted", "r_growth_adopted",
            "r_unmasked_thermal",
            "r_floor_thermal", "eta_dilation_thermal", "mask_dilation_thermal",
            "penalty_dilation_thermal", "r_dilation_thermal",
            "eta_growth_thermal", "mask_growth_thermal",
            "penalty_growth_thermal", "r_growth_thermal",
            "eta1_status_thermal", "mask_eta1_thermal", "r_eta1_thermal",
            "note"]
    tdir = os.path.join(args.out, "tables")
    os.makedirs(tdir, exist_ok=True)
    # A --only run is a spot check, not the table every downstream consumer
    # reads; writing it to eta_bao.csv would silently drop the other channels
    # and send them back to the global fallback threshold.
    name = "eta_bao.csv" if only is None else "eta_bao_subset.csv"
    output_path = os.path.join(tdir, name)
    write_csv_atomic(
        output_path, cols,
        ({key: row.get(key, "") for key in cols} for row in rows))
    print("\nwrote", output_path)
    if args.era_points:
        try:
            write_era_points(args.era_points, rows)
        except (KeyError, TypeError, ValueError) as exc:
            ap.error(str(exc))
        print("wrote", args.era_points)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
