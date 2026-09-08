"""The delay filter booked on both sides: what each cut world does to each channel.

Chapter 9's world table asks what happens when a delay cut is carried
self-consistently rather than claimed on one side. Each world is one published
cut: the Fisher bank loses the modes below it, so the parameter tolerances are
re-derived from that world's own bank; and the residual chain gains the
matching shelf suppression from the same tau-to-k_parallel mapping. Nothing is
invented -- the cuts are the deployed 200 ns and the two BAO-preserving design
points, and the suppressions are the chain's own ``DELAY_SUPPRESSION_DB``.

The tolerances. For each world's bank, each redshift bin and each parameter,
the tolerance is the smallest per-unit-residual bias over the integration
times that pass the registered response-stability gate. Computing them reads
four banks and takes minutes, so they are cached beside the banks and rebuilt
only when a bank is newer than the cache.

The residuals. Each channel's residual at its operating point
(:mod:`.operating`) is this analysis's own, on the current era, with no delay
credit: that is the convention every other number in chapter 9 uses. A world
divides it by its suppression. The ratio ``R = r / r_tol`` is reported per
parameter, and ``R <= 1`` passes, the one direction used throughout.

What this is not. A world is a bookkeeping exercise in what a cut would buy,
not a claim that the filter has been applied: it models the mode-cut geometry
only, never the filter's foreground-removal performance.
"""
from __future__ import annotations

import csv
import importlib.util
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
CACHE_COLUMNS = ("world", "bin_index", "z_lo", "z_hi", "parameter", "tolerance",
                 "years_accepted", "years_refused")


def _cell(value):
    """Floats round-trip exactly; ``numpy`` scalars are written as plain floats."""
    return repr(float(value)) if isinstance(value, float) else value


def suppression_db(world: str) -> float:
    """The shelf suppression this world's cut removes, from the chain's own table."""
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
    for world, filename, kfg, _ in WORLDS:
        bank = bt.load_bias_bank(Path(bank_dir) / filename, build_command="see scripts/three_worlds.py",
                                 expected_kfg_fac=kfg, expected_epsilon_fg=0.0)
        names = list(bank.paramnames)
        zs = bank.zs
        for ib in range(len(zs) - 1):
            accepted = {p: [] for p in PARAMETERS}
            refused = {p: 0 for p in PARAMETERS}
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
                        accepted[p].append(sig[p] / abs(dth[p]))
                    else:
                        refused[p] += 1
            for p in PARAMETERS:
                rows.append({"world": world, "bin_index": ib, "z_lo": round(float(zs[ib]), 4),
                             "z_hi": round(float(zs[ib + 1]), 4), "parameter": p,
                             "tolerance": float(min(accepted[p])) if accepted[p] else math.nan,
                             "years_accepted": len(accepted[p]), "years_refused": refused[p]})
    return rows


def _cache_is_current(cache: Path, bank_dir: Path) -> bool:
    """The cache stands unless a bank is newer than it.

    On a machine with no banks -- CI, or a reader of the shipped tree --
    nothing can invalidate the cache, so it stands and no bank is opened.
    """
    if not cache.is_file():
        return False
    mtimes = [(bank_dir / f).stat().st_mtime for _, f, _, _ in WORLDS if (bank_dir / f).is_file()]
    return not mtimes or cache.stat().st_mtime >= max(mtimes)


def tolerances(bank_dir: Path | str = BANK_DIR, cache: Path | str = CACHE, *, rebuild: bool = False) -> list[dict]:
    """The cached tolerances, rebuilt when a bank is newer than the cache."""
    cache, bank_dir = Path(cache), Path(bank_dir)
    if not rebuild and _cache_is_current(cache, bank_dir):
        with cache.open(newline="", encoding="utf-8") as fh:
            return [{**r, "bin_index": int(r["bin_index"]), "z_lo": float(r["z_lo"]), "z_hi": float(r["z_hi"]),
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
    return rows


def tolerance_of(rows: Sequence[dict], world: str, bins: Sequence[int], parameter: str) -> float:
    """The binding tolerance over a channel's bins: the smallest one the stability
    gate accepted, matching the ledger's own footing (:mod:`.tolerances`). NaN
    when the gate accepted nothing anywhere the channel overlaps."""
    values = [float(r["tolerance"]) for r in rows
              if r["world"] == world and r["parameter"] == parameter and int(r["bin_index"]) in set(bins)
              and math.isfinite(float(r["tolerance"]))]
    return min(values) if values else math.nan


def bin_span(rows: Sequence[dict], bins: Sequence[int]) -> tuple[float, float]:
    """The redshift span a channel's bins cover, or NaNs when it overlaps none."""
    zs = [(float(r["z_lo"]), float(r["z_hi"])) for r in rows if int(r["bin_index"]) in set(bins)]
    return (min(z[0] for z in zs), max(z[1] for z in zs)) if zs else (math.nan, math.nan)


@dataclass(frozen=True)
class ChannelWorlds:
    """One channel through the four worlds, at its operating point and at its frontier floor.

    Two bases, and the difference between them is what makes the second one
    worth carrying. The operating point is a *choice* -- the knee its
    calibration block selected -- so a ratio quoted there answers "does this
    policy fail". The frontier floor is the least residual any threshold on
    the same statistic can leave behind, at any masked fraction, anywhere on
    the surface, because the residual is a functional of that statistic alone
    and the coarse rule's frontier is the plane's lower envelope by
    construction. A ratio quoted at the floor therefore answers the stronger
    question, "does every policy of this kind fail", and it is the only one of
    the two that bounds a class rather than an instance.
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
    r_floor: float = math.nan                           # the frontier's least residual, the class bound
    floor_ratios: dict = field(default_factory=dict)    # (world, parameter) -> R at the floor
    floor_residuals: dict = field(default_factory=dict)
    r_evaluation: float = math.nan                      # the residual the point leaves on the held-out block
    evaluation_ratios: dict = field(default_factory=dict)
    evaluation_residuals: dict = field(default_factory=dict)
    floor_bound: bool = False                           # every kept frame is at the sensitivity floor
    status: str = "measured"
    notes: tuple[str, ...] = ()

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
            if not inside:
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
                   r_evaluation: float = math.nan, floor_bound: bool = False) -> ChannelWorlds:
    """One channel's four worlds on three bases, each priced through the same cuts.

    ``r_point`` is the operating point's residual on the calibration block --- a
    policy verdict. ``r_floor`` is the frontier's least, which bounds the whole
    class of thresholds on the statistic. ``r_evaluation`` is what the same
    point leaves on the held-out block the calibration never saw, and it is the
    only one of the three that is not graded on its own homework.

    ``floor_bound`` marks a channel whose kept frames all sit at the sensitivity
    floor, so the residual reported is the floor itself rather than a
    measurement of what survived. Its ratios are upper limits: the true residual
    is somewhere below and the instrument cannot say where.
    """
    bins = tuple(int(b) for b in bins)
    z_lo, z_hi = bin_span(rows, bins)
    ratios, residuals, tols = {}, {}, {}
    floor_ratios, floor_residuals, ev_ratios, ev_residuals = {}, {}, {}, {}
    notes = []
    common = dict(r_floor=r_floor, r_evaluation=r_evaluation, floor_bound=floor_bound)
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
        notes.append(f"the stability gate accepted no integration time for {', '.join(sorted(missing))}")
    if not math.isfinite(r_floor):
        notes.append("the channel carries no frontier floor, so no class bound is quoted beside its point")
    if not math.isfinite(r_evaluation):
        notes.append("the point was not replayed on the held-out block, so only the calibration bases are priced")
    if floor_bound:
        notes.append("every kept frame sits at the sensitivity floor, so the residual is the floor itself and "
                     "every ratio here is an upper limit rather than a measurement")
    return ChannelWorlds(channel, bins, z_lo, z_hi, r_point, masked_fraction, ratios, residuals, tols,
                         floor_ratios=floor_ratios, floor_residuals=floor_residuals,
                         evaluation_ratios=ev_ratios, evaluation_residuals=ev_residuals,
                         status="measured", notes=tuple(notes), **common)


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
