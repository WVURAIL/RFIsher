#!/usr/bin/env python3
"""The delay filter booked on both sides: three worlds, one verdict table.

Each world is one published delay-cut choice carried self-consistently:
the Fisher bank loses the cut modes (kfg_fac = tau_cut * bandwidth) and the
residual chain claims the matching DTV suppression derived from the same
k_par <-> delay mapping. Nothing is invented: the cut values are CHIME's
(200 ns deployed; 55/110 ns are the first- and second-peak-preserving
design points any BAO analysis faces), and the suppression numbers are the
chapter's DELAY_SUPPRESSION_DB.

Verdicts are quoted at the minimum-residual operating point (eta = 1,
product-basis floors, fine-stage credit) for the threshold-feasible
channels and the tau_c-hostage ch29. Tolerances are the per-parameter
minima over the entries that survive the registered response-stability gate.
Sign-off channels use their transmitter-on eras.

The four bias-response banks are not shipped. Build matched strict-v2,
unit-response banks first:

    python scripts/build_bank.py --config chime2022 --cosmology planck2018 \\
        --epsilon-fg 0 --p-res 1.0 --dense-knee \\
        --out data/fisher_bank_chime2022_pres_dense.npz
    python scripts/build_bank.py --config chime2022 --cosmology planck2018 \\
        --epsilon-fg 0 --p-res 1.0 --kfg-fac 22 --dense-knee \\
        --out data/fisher_bank_chime2022_pres_kfg22_dense.npz
    python scripts/build_bank.py --config chime2022 --cosmology planck2018 \\
        --epsilon-fg 0 --p-res 1.0 --kfg-fac 44 --dense-knee \\
        --out data/fisher_bank_chime2022_pres_kfg44_dense.npz
    python scripts/build_bank.py --config chime2022 --cosmology planck2018 \\
        --epsilon-fg 0 --p-res 1.0 --kfg-fac 80 --dense-knee \\
        --out data/fisher_bank_chime2022_pres_kfg80_dense.npz
    python scripts/three_worlds.py
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import importlib.util
import os
from pathlib import Path
import tempfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]

from rfisher import residual as R
from rfisher import selection_policy
from rfisher import survey
from rfisher.channels import channel_z_range
from rfisher.npzio import load_npz

spec = importlib.util.spec_from_file_location(
    "bt", str(ROOT / "scripts" / "bias_tolerance.py"))
bt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bt)

_WORLD_SPECS = {
    "none": ("no filter (Fig. 31 baseline)",
             "fisher_bank_chime2022_pres_dense.npz", "none", None),
    "peak1": ("55 ns, preserves 1st peak",
              "fisher_bank_chime2022_pres_kfg22_dense.npz",
              "bao_peak1", 22.0),
    "peak2": ("110 ns, preserves 2nd peak",
              "fisher_bank_chime2022_pres_kfg44_dense.npz",
              "bao_peak2", 44.0),
    "deployed": ("200 ns, CHIME's cut",
                 "fisher_bank_chime2022_pres_kfg80_dense.npz",
                 "aggressive_200ns", 80.0),
}
WORLD_KEYS = tuple(selection_policy.value(
    "archive_reference.three_worlds_scenarios"))
if any(key not in _WORLD_SPECS for key in WORLD_KEYS):
    raise RuntimeError("three-worlds response scenario is not defined")
WORLDS = [
    (key, _WORLD_SPECS[key][0], _WORLD_SPECS[key][1],
     R.DELAY_SUPPRESSION_DB[_WORLD_SPECS[key][2]])
    for key in WORLD_KEYS
]
WORLD_KFG = {key: _WORLD_SPECS[key][3] for key in WORLD_KEYS}
FINE_DB = float(selection_policy.value("transfer.fine_stage_credit_db"))
STABILITY_FRACTION = float(selection_policy.value(
    "science.response_stability.time_fraction"))
MAXIMUM_TOLERANCE_RATIO = float(selection_policy.value(
    "science.response_stability.maximum_tolerance_ratio"))
PARAMS = tuple(selection_policy.value(
    "archive_reference.three_worlds_parameters"))
(_GRID1_START, _GRID1_STOP, _GRID1_COUNT,
 _GRID2_START, _GRID2_STOP, _GRID2_COUNT) = selection_policy.value(
    "archive_reference.three_worlds_response_grid")
EXPECTED_DENSE_GRID = np.unique(np.concatenate([
    np.logspace(_GRID1_START, _GRID1_STOP, int(_GRID1_COUNT)),
    10.0 ** np.linspace(_GRID2_START, _GRID2_STOP, int(_GRID2_COUNT)),
]))
from rfisher import products as P
CHANNELS = tuple(int(value) for value in selection_policy.value(
    "archive_reference.three_worlds_channels"))
Z_BIN = {
    ch: float(np.floor(channel_z_range(ch)[0] * 10.0) / 10.0)
    for ch in CHANNELS
}
POSITIVE_EXCESS_ETA = float(selection_policy.value(
    "archive_reference.positive_excess_eta"))
YEARS = tuple(float(value) for value in selection_policy.value(
    "archive_reference.forecast_year_grid"))
PRODUCT_FIELDS = (
    "product_file", "product_sha256", "floor_epoch", "floor_frames",
    "floor_db", "floor_evidence", "tau_quality", "tau_reason",
)


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_rows(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def floor_details(path, ch):
    off_through = R.SIGN_ON_OFF_THROUGH.get(ch)
    off_from = R.SIGN_OFF_FROM.get(ch)
    stats = R.shelf_statistics(
        path, off_through=off_through, off_from=off_from)
    if off_through is not None:
        epoch = f"through {off_through}"
    elif off_from is not None:
        epoch = f"from {off_from}"
    else:
        epoch = "kept frames"
    return epoch, stats.n_off_frames


def bank_identity(path, bank):
    provenance = bank.meta["provenance"]
    settings = provenance["experiment"]["settings"]
    foreground = bank.meta["foreground_settings"]
    return {
        "generator_sha256": file_sha256(__file__),
        "bias_source_sha256": file_sha256(ROOT / "scripts" /
                                           "bias_tolerance.py"),
        "residual_source_sha256": file_sha256(R.__file__),
        "selection_policy_sha256": selection_policy.sha256(),
        "bank_file": Path(path).name,
        "bank_sha256": file_sha256(path),
        "bank_schema": bank.meta["schema_version"],
        "bank_source_commit": provenance["baonoise"]["git_commit"],
        "bank_source_sha256": provenance["baonoise"]["working_tree_sha256"],
        "bank_backend_commit": provenance["radiofisher"]["git_commit"],
        "bank_backend_sha256": provenance["radiofisher"][
            "working_tree_sha256"],
        "bank_kfg_fac": "" if foreground.get("kfg_fac") is None
        else foreground["kfg_fac"],
        "bank_epsilon_fg": foreground["epsilon_fg"],
        "bank_p_res": settings["P_res"],
        "bank_grid_points": len(bank.t_grid),
    }


def stable_minima(bank):
    """Per-(bin, parameter) minimum tolerance over stability-gated entries."""
    names = list(bank.paramnames)
    zs = bank.zs
    out = {}
    for zlo in (1.3, 1.4, 1.5):
        ib = [i for i in range(len(zs) - 1) if abs(zs[i] - zlo) < 1e-9][0]
        vals = {p: [] for p in PARAMS}
        refused = 0
        for yr in YEARS:
            t = yr * survey.OVERVIEW_ONSKY_YEAR_HOURS
            dth, sig = bt.bias_per_unit_r(bank.F(ib, t), names)
            for p in PARAMS:
                drift, nsign = bt.stability(
                    bank, ib, t, names, p, frac=STABILITY_FRACTION)
                if drift <= MAXIMUM_TOLERANCE_RATIO and nsign == 1:
                    vals[p].append(sig[p] / abs(dth[p]))
                else:
                    refused += 1
        out[zlo] = ({p: (min(v) if v else float("nan"))
                     for p, v in vals.items()}, refused)
    return out


def eta1_population(p, ch):
    d = load_npz(p)
    valid = d["valid"][:, 0].astype(bool)
    on = valid.copy()
    off_from = R.SIGN_OFF_FROM.get(ch)
    if off_from is not None:
        unit_month = np.array([
            dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m")
            for t in d["unit_time0_ctime"]
        ])[d["frame_unit_index"]]
        on &= unit_month < off_from
    keep = on & (
        d["fstat_raw"][:, 0] <= POSITIVE_EXCESS_ETA * float(d["mu0"][0]))
    return int(keep.sum()), int(on.sum())


def channel_r_eta1(p, ch):
    """Fine-stage residual at eta = 1, product-basis floor (as in the
    optimizer): the minimum-residual point of the threshold family."""
    off_from = R.SIGN_OFF_FROM.get(ch)
    n_kept, n_valid = eta1_population(p, ch)
    floor_db, floor_evidence = R.kept_frame_floor(p)
    floor_epoch, floor_frames = floor_details(p, ch)
    sweep = R.threshold_sweep(
        p, etas=np.array([POSITIVE_EXCESS_ETA]), floor_db=floor_db,
        off_from=off_from)
    corr = R.correlation_time(p, off_from=off_from)
    return {
        "r_fine": (sweep[0]["r_masked"] / 10 ** (FINE_DB / 10)
                   if sweep else None),
        "residual_status": (
            "evaluated" if sweep else "insufficient_kept_frames"),
        "n_eta1_kept": n_kept,
        "n_eta1_valid": n_valid,
        "product_file": Path(p).name,
        "product_sha256": file_sha256(p),
        "floor_epoch": floor_epoch,
        "floor_frames": floor_frames,
        "floor_db": floor_db,
        "floor_evidence": floor_evidence,
        "tau_quality": corr.quality,
        "tau_reason": getattr(corr, "reason", "") or "",
    }


def unavailable_row(world, suppression_db, ch, tau_capped, status,
                    result, tolerances, bank_info):
    return dict(
        world=world, suppression_db=suppression_db, ch=ch,
        tau_capped=tau_capped, residual_status=status,
        n_eta1_kept=result["n_eta1_kept"],
        n_eta1_valid=result["n_eta1_valid"],
        min_eta1_kept=R.MIN_THRESHOLD_SWEEP_KEPT_FRAMES, r_fine=None,
        **bank_info,
        **{field: result[field] for field in PRODUCT_FIELDS},
        **{f"tol_{p}": tolerances[p] for p in PARAMS},
        **{f"pass_{p}": None for p in PARAMS})


def validate_world_bank(bank):
    """Check the scalar response and exact dense grid."""
    overrides = bank.meta.get("expt_overrides", {})
    recorded = bank.meta.get("provenance", {}).get(
        "experiment", {}).get("settings", {})

    def is_scalar_unit(value):
        return (
            isinstance(value, (int, float, np.integer, np.floating))
            and not isinstance(value, (bool, np.bool_))
            and float(value) == 1.0
        )

    if not (is_scalar_unit(overrides.get("P_res"))
            and is_scalar_unit(recorded.get("P_res"))):
        raise ValueError(
            "three-worlds banks require the scalar P_res=1.0 response")
    if not np.array_equal(np.asarray(bank.t_grid), EXPECTED_DENSE_GRID):
        raise ValueError(
            "three-worlds banks require the exact 27-point --dense-knee "
            "time grid")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--bank-dir", type=Path, default=ROOT / "data",
        help="directory containing all four locally built strict-v2 "
             "unit-response banks listed in this command's description")
    args = ap.parse_args(argv)

    banks = {}
    for key, _, filename, _ in WORLDS:
        expected_kfg = WORLD_KFG[key]
        kfg = "" if expected_kfg is None else f" --kfg-fac {expected_kfg:g}"
        command = (
            "python scripts/build_bank.py --config chime2022 "
            "--cosmology planck2018 --epsilon-fg 0 --p-res 1.0"
            f"{kfg} --dense-knee --out data/{filename}"
        )
        try:
            bank = bt.load_bias_bank(
                args.bank_dir / filename, build_command=command,
                expected_kfg_fac=expected_kfg, expected_epsilon_fg=0.0)
            validate_world_bank(bank)
            banks[key] = bank
        except ValueError as exc:
            ap.error(f"{exc}\nBuild the exact prerequisite with:\n  {command}")

    rows = []
    paths = P.paths(channels=sorted(Z_BIN))
    missing_products = sorted(set(Z_BIN) - set(paths))
    if missing_products:
        ap.error(
            "survey products are missing for channels "
            + ", ".join(map(str, missing_products))
            + "; configure products.json or its local override")
    r1 = {ch: channel_r_eta1(paths[ch], ch) for ch in sorted(Z_BIN)}
    channel_summary = []
    for ch, result in r1.items():
        residual = result["r_fine"]
        capped = result["tau_quality"] == "refused"
        status = result["residual_status"]
        value = status if residual is None else f"{residual:.4g}"
        channel_summary.append(f"ch{ch}={value}{'*' if capped else ''}")
    print("channels at eta=1, fine stage: " + "  ".join(channel_summary)
          + "   (* = tau_c capped)\n")

    for key, label, filename, sup_db in WORLDS:
        tol = stable_minima(banks[key])
        bank_info = bank_identity(args.bank_dir / filename, banks[key])
        sup = 10 ** (sup_db / 10)
        print(f"--- world '{key}': {label}  (suppression {sup_db} dB, "
              f"refusals per bin: " +
              ", ".join(f"{z}:{tol[z][1]}" for z in (1.3, 1.4, 1.5)) + ")")
        for ch, zlo in Z_BIN.items():
            t = tol[zlo][0]
            result = r1[ch]
            capped = result["tau_quality"] == "refused"
            if result["r_fine"] is None:
                print(f"    ch{ch}   {result['residual_status']}")
                rows.append(unavailable_row(
                    key, sup_db, ch, capped, result["residual_status"],
                    result, t, bank_info))
                continue
            r = result["r_fine"] / sup
            verdicts = {}
            cells = []
            for p in PARAMS:
                ok = r <= t[p]
                verdicts[p] = ok
                cells.append(f"{p} {'PASS x%.1f' % (t[p]/r) if ok else 'x%.2g over' % (r/t[p])}")
            print(f"    ch{ch}{'*' if capped else ' '}  r={r:9.4g}   " +
                  "   ".join(f"{c:>16}" for c in cells))
            rows.append(dict(world=key, suppression_db=sup_db, ch=ch,
                             tau_capped=capped,
                             residual_status=result["residual_status"],
                             n_eta1_kept=result["n_eta1_kept"],
                             n_eta1_valid=result["n_eta1_valid"],
                             min_eta1_kept=R.MIN_THRESHOLD_SWEEP_KEPT_FRAMES,
                             r_fine=r,
                             **bank_info,
                             **{field: result[field]
                                for field in PRODUCT_FIELDS},
                             **{f"tol_{p}": t[p] for p in PARAMS},
                             **{f"pass_{p}": verdicts[p] for p in PARAMS}))
        print()

    out = ROOT / "out" / "three_worlds.csv"
    write_rows(out, rows)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
