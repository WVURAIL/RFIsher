"""Conditional delay-filter scenarios with target-time Fisher tolerances.

The filter banks price the loss of cosmological modes. The separate scalar
suppression constants are historical hypothetical assumptions, not a transfer
measurement and not a consequence of the delay-to-wavenumber coordinate map.
Every physical interpretation also requires signal/noise/RFI propagation
through the actual mask-dependent visibility operator. Floor assignment is
a screening allowance, not a physical lower bound or a confidence interval.

All parameters are evaluated at TARGET_YEARS. Refused target-time cells stay
unpriced; another year cannot supply the answer. Cached tables require their
content identity, current policy/source identity, and authenticated banks.
"""
from __future__ import annotations

import csv
import importlib.util
import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from rfisher import residual, selection_policy, survey

ROOT = Path(__file__).resolve().parents[3]
BANK_DIR = ROOT / "data"
CACHE = BANK_DIR / "world_tolerances.csv"
WORLDS = (("none", "fisher_bank_chime2022_pres_dense.npz", None, "none"),
          ("peak1", "fisher_bank_chime2022_pres_kfg22_dense.npz", 22.0, "bao_peak1"),
          ("peak2", "fisher_bank_chime2022_pres_kfg44_dense.npz", 44.0, "bao_peak2"),
          ("deployed", "fisher_bank_chime2022_pres_kfg80_dense.npz", 80.0, "aggressive_200ns"))
WORLD_LABEL = {"none": "no filter", "peak1": r"$55$~ns", "peak2": r"$110$~ns", "deployed": r"$200$~ns"}
PARAMETERS = tuple(selection_policy.value("archive_reference.three_worlds_parameters"))
CACHE_COLUMNS = ("world", "bin_index", "z_lo", "z_hi", "parameter", "tolerance", "at_target",
                 "years_used", "years_accepted", "years_refused")
TARGET_YEARS = 1.0     # T*, the declared target integration; chapter 9 quotes r_tol there


def _cell(value):
    """Floats round-trip exactly; ``numpy`` scalars are written as plain floats."""
    return repr(float(value)) if isinstance(value, float) else value


def suppression_db(world: str) -> float:
    """Hypothetical suppression assigned to this scenario, not measured transfer."""
    key = dict((w, k) for w, _, _, k in WORLDS)[world]
    return 0.0 if key == "none" else float(residual.DELAY_SUPPRESSION_DB[key])


def _bias_tolerance():
    spec = importlib.util.spec_from_file_location("bias_tolerance", ROOT / "scripts" / "bias_tolerance.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def compute_tolerances(bank_dir: Path | str = BANK_DIR) -> list[dict]:
    """Every world's stable tolerance per bin and parameter, read from the four banks."""
    bt = _bias_tolerance()
    frac = float(selection_policy.value("science.response_stability.time_fraction"))
    limit = float(selection_policy.value("science.response_stability.maximum_tolerance_ratio"))
    years = tuple(float(v) for v in selection_policy.value("archive_reference.forecast_year_grid"))
    rows = []
    if TARGET_YEARS not in years:                 # the declared target must be on the grid
        years = tuple(sorted(set(years) | {TARGET_YEARS}))
    for world, filename, kfg, _ in WORLDS:
        bank = bt.load_bias_bank(Path(bank_dir) / filename, build_command="see scripts/three_worlds.py",
                                 expected_kfg_fac=kfg, expected_epsilon_fg=0.0)
        names = list(bank.paramnames)
        zs = bank.zs
        for ib in range(len(zs) - 1):
            accepted = {p: [] for p in PARAMETERS}
            refused = {p: 0 for p in PARAMETERS}
            at_target = {p: math.nan for p in PARAMETERS}
            for year in years:
                t = year * survey.OVERVIEW_ONSKY_YEAR_HOURS
                try:
                    dth, sig = bt.bias_per_unit_r(bank.F(ib, t), names)
                except Exception:
                    for p in PARAMETERS:
                        refused[p] += 1
                    continue
                for p in PARAMETERS:
                    try:
                        drift, nsign = bt.stability(bank, ib, t, names, p, frac=frac)
                    except Exception:
                        refused[p] += 1
                        continue
                    if drift <= limit and nsign == 1:
                        value = sig[p] / abs(dth[p])
                        accepted[p].append((year, value))
                        if year == TARGET_YEARS:
                            at_target[p] = value
                    else:
                        refused[p] += 1
            for p in PARAMETERS:
                # Only the declared target time may supply an operational tolerance.
                if math.isfinite(at_target[p]):
                    value, used, on_target = at_target[p], TARGET_YEARS, True
                else:
                    value, used, on_target = math.nan, math.nan, False
                rows.append({"world": world, "bin_index": ib, "z_lo": round(float(zs[ib]), 4),
                             "z_hi": round(float(zs[ib + 1]), 4), "parameter": p,
                             "tolerance": float(value) if math.isfinite(value) else math.nan,
                             "at_target": on_target, "years_used": used,
                             "years_accepted": len(accepted[p]), "years_refused": refused[p]})
    return rows


def _cache_is_current(cache: Path, bank_dir: Path) -> bool:
    """Require a content identity and authenticated banks, not modification times."""
    sidecar = cache.with_suffix(".provenance.json")
    if not cache.is_file() or not sidecar.is_file():
        return False
    try:
        return json.loads(sidecar.read_text()) == _cache_identity(cache, bank_dir)
    except (OSError, ValueError, KeyError):
        return False


def _cache_identity(cache: Path, bank_dir: Path) -> dict:
    bt = _bias_tolerance()
    identity = {"schema": 2, "target_years": TARGET_YEARS,
                "policy": selection_policy.sha256(), "sources": {}, "banks": {},
                "csv_sha256": hashlib.sha256(cache.read_bytes()).hexdigest()}
    for path in (Path(__file__), ROOT / "scripts/bias_tolerance.py", ROOT / "src/rfisher/fisherbank.py"):
        identity["sources"][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    for _, filename, kfg, _ in WORLDS:
        path = bank_dir / filename
        # Also authenticates the configured backend's current scientific identity.
        bank = bt.load_bias_bank(path, expected_kfg_fac=kfg, expected_epsilon_fg=0.0)
        identity["banks"][filename] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                       "evaluation": bank.evaluation_identity}
    return identity


def tolerances(bank_dir: Path | str = BANK_DIR, cache: Path | str = CACHE, *, rebuild: bool = False) -> list[dict]:
    """Tolerances authenticated against their CSV, policy, sources and banks."""
    cache, bank_dir = Path(cache), Path(bank_dir)
    if not rebuild and _cache_is_current(cache, bank_dir):
        with cache.open(newline="", encoding="utf-8") as fh:
            return [{**r, "bin_index": int(r["bin_index"]), "z_lo": float(r["z_lo"]), "z_hi": float(r["z_hi"]),
                     "at_target": str(r.get("at_target", "")).lower() == "true",
                     "years_used": float(r["years_used"]) if r.get("years_used") not in ("", "nan", None) else math.nan,
                     "tolerance": float(r["tolerance"]) if r["tolerance"] not in ("", "nan") else math.nan,
                     "years_accepted": int(r["years_accepted"]), "years_refused": int(r["years_refused"])}
                    for r in csv.DictReader(fh)]
    rows = compute_tolerances(bank_dir)
    cache.parent.mkdir(parents=True, exist_ok=True)
    with cache.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(CACHE_COLUMNS), lineterminator="\n")
        writer.writeheader()
        for r in rows:
            writer.writerow({k: _cell(v) for k, v in r.items()})
    cache.with_suffix(".provenance.json").write_text(json.dumps(_cache_identity(cache, bank_dir), sort_keys=True))
    return rows


def tolerance_of(rows: Sequence[dict], world: str, bins: Sequence[int], parameter: str) -> float:
    """Minimum over every requested bin; any missing or refused target cell refuses."""
    by_bin = {int(r["bin_index"]): r for r in rows if r["world"] == world and r["parameter"] == parameter}
    values = []
    for b in bins:
        row = by_bin.get(int(b))
        if row is None or not row.get("at_target", False):
            return math.nan
        value = float(row["tolerance"])
        if not math.isfinite(value) or value <= 0:
            return math.nan
        values.append(value)
    return min(values) if values else math.nan


def bin_span(rows: Sequence[dict], bins: Sequence[int]) -> tuple[float, float]:
    """The redshift span a channel's bins cover, or NaNs when it overlaps none."""
    zs = [(float(r["z_lo"]), float(r["z_hi"])) for r in rows if int(r["bin_index"]) in set(bins)]
    return (min(z[0] for z in zs), max(z[1] for z in zs)) if zs else (math.nan, math.nan)


@dataclass(frozen=True)
class ChannelWorlds:
    """Conditional scalar scenarios at an operating point and assigned floor.

    Point and evaluation policies may differ and have separate identities and
    masking fractions. The frontier minimum concerns the booked allowance,
    not a lower bound on true surviving contamination. Neither basis alone
    certifies recovery of complex visibilities.
    """

    channel: int
    bins: tuple
    z_lo: float
    z_hi: float
    r_point: float                      # the residual at the operating point, no delay credit
    masked_fraction: float
    ratios: dict = field(default_factory=dict)          # (world, parameter) -> R at the operating point
    residuals: dict = field(default_factory=dict)       # world -> r after that world's suppression
    tolerances: dict = field(default_factory=dict)      # (world, parameter) -> r_tol
    r_floor: float = math.nan                           # minimum booked frontier allowance
    floor_ratios: dict = field(default_factory=dict)    # (world, parameter) -> R at the floor
    floor_residuals: dict = field(default_factory=dict)
    r_evaluation: float = math.nan                      # the residual the point leaves on the held-out block
    evaluation_ratios: dict = field(default_factory=dict)
    evaluation_residuals: dict = field(default_factory=dict)
    floor_bound: bool = False                           # evaluation allowance matches the assigned floor
    status: str = "conditional"
    notes: tuple[str, ...] = ()
    point_policy: str = "unspecified"
    evaluation_policy: str = "unspecified"
    evaluation_masked_fraction: float = math.nan
    evaluation_kept: int = 0

    def _table(self, basis: str) -> dict:
        return {"point": self.ratios, "floor": self.floor_ratios,
                "evaluation": self.evaluation_ratios}[basis]

    def binding(self, parameters: Sequence[str], *, floor: bool = False, basis: str | None = None) -> tuple[str, float, str]:
        """``(world, R, parameter)`` of the best any world reaches over ``parameters``.

        The binding parameter is the largest ratio inside a world, because that
        is the one that has to pass; the best world is the smallest of those.
        ``('', inf, '')`` when no world prices any of the parameters.
        """
        table = self._table(basis) if basis else (self.floor_ratios if floor else self.ratios)
        best = ("", math.inf, "")
        for world, _, _, _ in WORLDS:
            inside = [(table.get((world, p), math.nan), p) for p in parameters]
            inside = [(v, p) for v, p in inside if math.isfinite(v)]
            if len(inside) != len(parameters):
                continue
            value, param = max(inside)
            if value < best[1]:
                best = (world, value, param)
        return best

    def as_row(self) -> dict:
        row = {"channel": self.channel, "bins": ";".join(str(b) for b in self.bins),
               "z_lo": self.z_lo, "z_hi": self.z_hi, "r_point": self.r_point, "r_floor": self.r_floor,
               "r_evaluation": self.r_evaluation, "floor_bound": self.floor_bound,
               "masked_fraction": self.masked_fraction, "status": self.status, "notes": "; ".join(self.notes)}
        row.update({"residual_evidence": "conditional scalar screening allowance",
                    "delay_suppression_evidence": "hypothetical; not measured on these visibilities",
                    "physical_recovery_certified": False,
                    "point_policy": self.point_policy, "evaluation_policy": self.evaluation_policy,
                    "evaluation_masked_fraction": self.evaluation_masked_fraction,
                    "evaluation_kept": self.evaluation_kept})
        for world, _, _, _ in WORLDS:
            row[f"{world}_r"] = self.residuals.get(world, math.nan)
            row[f"{world}_floor_r"] = self.floor_residuals.get(world, math.nan)
            row[f"{world}_evaluation_r"] = self.evaluation_residuals.get(world, math.nan)
            row[f"{world}_suppression_db"] = suppression_db(world)
            for p in PARAMETERS:
                row[f"{world}_{p}_R"] = self.ratios.get((world, p), math.nan)
                row[f"{world}_{p}_floor_R"] = self.floor_ratios.get((world, p), math.nan)
                row[f"{world}_{p}_evaluation_R"] = self.evaluation_ratios.get((world, p), math.nan)
                row[f"{world}_{p}_r_tol"] = self.tolerances.get((world, p), math.nan)
        return row


def channel_worlds(channel: int, bins: Sequence[int], r_point: float, masked_fraction: float,
                   rows: Sequence[dict], *, r_floor: float = math.nan,
                   r_evaluation: float = math.nan, floor_bound: bool = False,
                   point_policy: str = "unspecified", evaluation_policy: str = "unspecified",
                   evaluation_masked_fraction: float = math.nan, evaluation_kept: int = 0) -> ChannelWorlds:
    """Price three explicitly conditional scalar bases through the same cuts.

    ``r_point`` and ``r_evaluation`` must retain their respective policy
    identities; a diagnostic replay can differ from the displayed knee.
    ``r_floor`` is the minimum booked allowance, not a physical class bound.
    ``floor_bound`` is a legacy field name for a floor-only evaluation
    assignment; it does not establish a confidence limit on the actual residual.
    """
    bins = tuple(int(b) for b in bins)
    z_lo, z_hi = bin_span(rows, bins)
    ratios, residuals, tols = {}, {}, {}
    floor_ratios, floor_residuals, ev_ratios, ev_residuals = {}, {}, {}, {}
    notes = []
    common = dict(r_floor=r_floor, r_evaluation=r_evaluation, floor_bound=floor_bound,
                  point_policy=point_policy, evaluation_policy=evaluation_policy,
                  evaluation_masked_fraction=evaluation_masked_fraction, evaluation_kept=evaluation_kept)
    if not bins:
        return ChannelWorlds(channel, bins, z_lo, z_hi, r_point, masked_fraction, status="no overlapping bin",
                             notes=("the channel overlaps no forecast bin, so no world applies",), **common)
    if not math.isfinite(r_point):
        return ChannelWorlds(channel, bins, z_lo, z_hi, r_point, masked_fraction, status="no operating point",
                             notes=("the channel has no operating point to carry through the worlds",), **common)
    for world, _, _, _ in WORLDS:
        drop = 10.0 ** (suppression_db(world) / 10.0)
        r = r_point / drop
        residuals[world] = r
        floor_residuals[world] = r_floor / drop if math.isfinite(r_floor) else math.nan
        ev_residuals[world] = r_evaluation / drop if math.isfinite(r_evaluation) else math.nan
        for p in PARAMETERS:
            tol = tolerance_of(rows, world, bins, p)
            tols[(world, p)] = tol
            usable = math.isfinite(tol) and tol > 0
            ratios[(world, p)] = r / tol if usable else math.nan
            for table, source in ((floor_ratios, floor_residuals), (ev_ratios, ev_residuals)):
                table[(world, p)] = (source[world] / tol
                                     if usable and math.isfinite(source[world]) else math.nan)
    missing = [f"{w}/{p}" for (w, p), t in tols.items() if not math.isfinite(t)]
    if missing:
        notes.append(f"no accepted target-time tolerance for {', '.join(sorted(missing))}")
    if not math.isfinite(r_floor):
        notes.append("the channel carries no minimum frontier allowance")
    if not math.isfinite(r_evaluation):
        notes.append("the point was not replayed on the held-out block, so only the calibration bases are priced")
    if floor_bound:
        notes.append("the evaluation allowance is within 0.1 percent of its floor-only assignment; "
                     "it is a conditional allowance, not a measurement or confidence limit")
    return ChannelWorlds(channel, bins, z_lo, z_hi, r_point, masked_fraction, ratios, residuals, tols,
                         floor_ratios=floor_ratios, floor_residuals=floor_residuals,
                         evaluation_ratios=ev_ratios, evaluation_residuals=ev_residuals,
                         status="conditional", notes=tuple(notes), **common)


def write_world_rows(results: Sequence[ChannelWorlds], path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [r.as_row() for r in results]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]) if rows else ["channel"], lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _cell(v) for k, v in row.items()})
    return path
