"""``fig:tolerance:twowalls`` and ``fig:tolerance:case`` from the ledger and the per-channel
calibration surfaces, with the points the figures mark as a table fragment.

Sources per channel (``channels/chNN/``)
    ``operating_points.csv``  the selector's evaluated calibration surface, written by the producer
        thinned to about 200 rows per rank (``channel, rho, rank_fraction, eta_q16, eta, frames,
        kept, masked_fraction, r_sys, tolerance_fraction, cost, feasible, selected``). The rows at
        one rank, the rank of the channel's least-residual point (``selection.min_r_sys_rho``),
        ordered by ``eta_q16``, trace ``(f, r_sys)`` as ``eta`` rises (raising ``eta`` walks the
        curve from ``f -> 1`` to ``f = 0``). A denser surface is thinned to about
        :data:`CURVE_POINTS` rows, evenly in ``f`` and in ``log10(1 - f)`` so the occupancy end
        stays resolved, always keeping both ends, the marked points and the ``f = 0`` row; the
        producer's thinned surface passes untouched. A header-only file (a channel whose selection
        is ``refused``) gives no curve.
    ``coarse_frontier.csv``  the coarse rule's frontier (``channel, eta_c, frames, kept,
        masked_fraction, r_sys, R, evaluable``), ordered by ``eta_c``; absent where the floor is
        refused or no surface was evaluated. The residual is a functional of the coarse statistic
        alone, so the frontier is the lower envelope of the plane by construction; rows that are
        not ``evaluable`` (or carry no ``R``) are not drawn.

The two walls (``fig_bao_two_walls.pdf``, one panel)
    x: masked fraction ``f`` (``masked_fraction``); y: ``R = r_proxy / r_tol`` (``tolerance_fraction``,
    log axis; ``r_tol`` is ``selection.r_tol``, the tolerance on the dilation tier of the channel's
    bin, ``tolerance.r_tol_dilation`` when the selection carries none). One fine curve per channel
    at its least-residual rank, coloured by ``screening.screening_class``, with the coarse frontier
    (``R`` against ``masked_fraction``) as a dotted curve beside it in the same colour. A curve is
    dashed when the floor is not measured (``selection.floor_evidence`` ``stated`` or ``refused``)
    or ``tau_c`` is not measured (``chain.tau_quality`` ``bounded_above`` or ``refused``: no
    ground-filter credit, so the curve is an upper bound). Marked per channel: the diagnostic
    point (``selection.diagnostic_rho, diagnostic_eta_q16, diagnostic_eta,
    diagnostic_masked_fraction, diagnostic_r_sys, diagnostic_R, diagnostic_cost``: the least-residual
    point of the calibration surface, ``diagnostic_basis``; read back from ``min_r_sys_rho,
    min_r_sys_eta, min_r_sys_masked_fraction, min_r_sys, min_R`` on a ledger without the diagnostic
    keys), its replay on the evaluation block as an open triangle (``masked_fraction_evaluation``,
    ``R_evaluation``, drawn only when ``kept_evaluation`` is positive), the selected point
    ``(rho*, eta*)`` when the selector selected one (``selection.rho, eta_q16, eta,
    masked_fraction_calibration, r_sys_calibration, R_calibration``; none in a run where every
    selection is ``diagnostic``), the keep-everything point at ``f = 0`` with ``R =
    keep_everything_r_sys_calibration / r_tol`` (``r_sys_unmasked_calibration`` when the key is
    absent), and the survey flag rate (``screening.survey_flag_rate_era``) as a tick on the ``f``
    axis only: the ledger carries no residual at the survey flag. Walls: the bias wall ``R = 1``;
    the occupancy wall at ``run.provisional.occupancy_wall_masked_fraction`` (shaded beyond); the
    ``f sigma_8`` band spanning ``tolerance.r_tol_fs8 / r_tol`` over the channels whose growth-rate
    tolerance is priced (``tolerance.fs8_status``).

The case (``fig_bao_the_case.pdf``, one panel per channel in :data:`CASE_CHANNELS`)
    ``r_sys`` against ``f`` along the same fine curve and coarse frontier, with the keep-everything
    point, the diagnostic point (kept frames from the surface row), its evaluation replay
    (``r_sys_evaluation``), the dilation tolerance ``r_tol`` (the bias wall), the ``f sigma_8``
    tolerance ``r_tol_fs8``, the occupancy wall and the survey flag rate as the occupancy
    reference. Channel 33 is the stub's channel; its floor is stated (``null.floor_basis`` ``bulk
    left side (not H0)``) and its era chain refuses ``tau_c`` where the archive-wide chain bounds
    it, so channel 29 (stated kept-half floor, ``tau_c`` bounded above) is the second panel. Only
    the policies the ledger carries are drawn: keep everything, the pilot proxy along ``eta``, the
    coarse rule, and excision (``f = 1``: no residual and no measurement). Alternative flaggers are
    not in the archive ledger and are not invented.

The table fragment (``tables/figures_two_walls.tex``, one row per channel) prints the marked
points, columns (ledger ``section.key``):

    ch          channel number
    curve       ``solid`` or ``dashed`` (selection.floor_evidence, chain.tau_quality); the dash when
                no curve is drawn (no surface rows at the least-residual rank)
    point       which point the ``rho .. R`` cells print: ``selected`` when the selector selected
                one, ``diagnostic`` otherwise (selection.diagnostic_*; no channel of the 2026-09-07
                run has a selected point), ``least residual`` on a ledger without diagnostic keys
    rho         the point's rank (selection.rho or diagnostic_rho)
    eta_q16     its exact multiplier (selection.eta_q16 or diagnostic_eta_q16)
    eta         its display multiplier (selection.eta or diagnostic_eta)
    f           its masked fraction (selection.masked_fraction_calibration or diagnostic_masked_fraction)
    r_proxy     its residual (selection.r_sys_calibration or diagnostic_r_sys)
    R           its ratio to the dilation tolerance (selection.R_calibration or diagnostic_R)
    R_eval      the point replayed on the evaluation block (selection.R_evaluation); the dash when
                the replay kept no frame (selection.kept_evaluation 0)
    R_keep      keep_everything_r_sys_calibration / r_tol (derived)
    R_coarse    the coarse frontier's least ratio (selection.coarse_min_R); its multiplier
                coarse_min_R_eta and coarse_R_at_flag go to the numbers
    f_coarse    the masked fraction at that frontier point (selection.coarse_min_R_masked_fraction)
    flag rate   screening.survey_flag_rate_era
    R_fs8 wall  tolerance.r_tol_fs8 / r_tol, the ratio at which the growth-rate wall falls
                (derived; the dash where tolerance.fs8_status is not ``published``)
    floor       selection.floor_evidence with null.floor_basis in brackets when stated
                (``stated (kept half)``, ``stated (bulk left)``); ``measured``; ``refused``
    tau_c       chain.tau_quality as ``measured`` / ``bound`` / ``refused``, with the archive-wide
                chain's word in brackets when it is better than the era chain's (chain_archive
                .tau_quality; channel 33: ``refused (archive: bound)``)

An absent or undefined value prints as the dash and the fragment's notes say why. Every printed
number is keyed ``ch09.twowalls.<column>.chNN`` (with ``kept``, ``cost``, ``r_tol``, ``r_keep``,
``keep_over_proxy``, ``f_eval``, ``kept_eval``, ``eta_coarse``, ``R_coarse_at_flag``, ``floor_basis``,
``floor_db``, ``tau_c_minutes``, ``class``, ``status``, ``gain_basis``, ``curve_points`` and
``coarse_points`` beside the columns); band-level values ``ch09.twowalls.<name>``; the case
figure's annotations ``ch09.case.<name>.chNN`` for each panel's channel.

``operating_curves.csv`` (written beside the figures) carries the drawn curves: ``channel, source
(fine | coarse), rho, eta_q16, eta (eta_c for the coarse rule), kept, masked_fraction, r_sys, R,
marker (diagnostic | selected | keep_everything | coarse_min)`` so the dissertation can vendor the
data behind the figures.
"""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from .core import DASH, Channel, Fragment, Run, booktabs, fmt, fmt_int, tex, write_report

NAME = "figures_two_walls"
LABEL = "fig:tolerance:twowalls"
CASE_LABEL = "fig:tolerance:case"
LABELS = (LABEL, CASE_LABEL)
CASE_CHANNELS = (33, 29)
CURVE_POINTS = 256
FIGURE_TWO_WALLS = "fig_bao_two_walls"
FIGURE_CASE = "fig_bao_the_case"
CURVES_CSV = "operating_curves.csv"
SURFACE_CSV = "operating_points.csv"
FRONTIER_CSV = "coarse_frontier.csv"

_FIELDS = (("rho", "i8"), ("eta_q16", "i8"), ("eta", "f8"), ("frames", "i8"), ("kept", "i8"),
           ("masked_fraction", "f8"), ("r_sys", "f8"), ("tolerance_fraction", "f8"), ("cost", "f8"),
           ("feasible", "?"), ("selected", "?"))
POINT_DTYPE = np.dtype(list(_FIELDS))
_COARSE_FIELDS = (("eta_c", "f8"), ("frames", "i8"), ("kept", "i8"), ("masked_fraction", "f8"), ("r_sys", "f8"),
                  ("R", "f8"), ("evaluable", "?"))
COARSE_DTYPE = np.dtype(list(_COARSE_FIELDS))
CURVE_COLUMNS = ("channel", "source", "rho", "eta_q16", "eta", "kept", "masked_fraction", "r_sys", "R", "marker")

COLUMNS = ("channel", "curve", "point", "rho", "eta_q16", "eta", "masked_fraction", "r_sys", "R", "R_eval", "R_keep",
           "R_coarse", "f_coarse", "flag_rate", "fs8_wall", "floor", "tau_quality")
HEADER = ("ch", "curve", "point", r"$\rho$", r"$\eta_{q16}$", r"$\eta$", "$f$", r"$r_{\rm proxy}$", "$R$",
          r"$R_{\rm eval}$", r"$R_{\rm keep}$", r"$R_{\rm coarse}$", r"$f_{\rm coarse}$", "flag rate",
          r"$R_{f\sigma_8}$ wall", "floor", r"$\tau_c$")
ALIGN = "lll" + "r" * 12 + "ll"
TAU_WORD = {"measured": "measured", "bounded_above": "bound", "refused": "refused"}
FLOOR_BASIS_WORD = {"off era p90": "off era", "kept half about mu_0": "kept half", "bulk left side (not H0)": "bulk left",
                    "none": ""}


# ------------------------------------------------------------------ the surfaces
def _finite(value) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _f(value) -> float:
    return float(value) if _finite(value) else math.nan


def _i(value) -> int | None:
    return int(round(float(value))) if _finite(value) else None


def read_operating_points(path: Path | str, channel: int, rho: int) -> np.ndarray:
    """The rows of one channel's ``operating_points.csv`` at rank ``rho``, ordered by ``eta_q16``.

    Only the lines starting ``channel,rho,`` are parsed (an unthinned surface holds millions of
    rows), and the columns are found by name from the header.
    """
    path = Path(path)
    prefix = f"{int(channel)},{int(rho)},"
    with path.open("r", encoding="utf-8", newline="") as fh:
        header = next(csv.reader([next(fh)]))
        lines = [line for line in fh if line.startswith(prefix)]
    missing = [name for name in ("channel", *(n for n, _ in _FIELDS)) if name not in header]
    if missing:
        raise ValueError(f"{path}: operating points lack columns {missing}")
    if header.index("channel") != 0 or header.index("rho") != 1:
        raise ValueError(f"{path}: expected 'channel,rho' as the first two columns, got {header[:2]}")
    out = np.empty(len(lines), dtype=POINT_DTYPE)
    if lines:
        columns = list(zip(*csv.reader(lines)))
        for name, kind in _FIELDS:
            col = columns[header.index(name)]
            out[name] = (np.array(col) == "True") if kind == "?" else np.array(col, dtype=POINT_DTYPE[name])
    return out[np.argsort(out["eta_q16"], kind="stable")]


def read_coarse_frontier(path: Path | str, channel: int) -> np.ndarray:
    """One channel's rows of ``coarse_frontier.csv``, ordered by ``eta_c``; blank ``r_sys`` / ``R``
    read as NaN (a row the coarse rule could not evaluate)."""
    path = Path(path)
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        names = list(reader.fieldnames or ())
        missing = [n for n in ("channel", *(n for n, _ in _COARSE_FIELDS)) if n not in names]
        if missing:
            raise ValueError(f"{path}: coarse frontier lacks columns {missing}")
        rows = [r for r in reader if (r.get("channel") or "").strip() == str(int(channel))]
    out = np.empty(len(rows), dtype=COARSE_DTYPE)
    for name, kind in _COARSE_FIELDS:
        vals = [(r.get(name) or "").strip() for r in rows]
        if kind == "?":
            out[name] = [v == "True" for v in vals]
        elif kind == "f8":
            out[name] = [float(v) if v and v.lower() not in ("none", "nan") else math.nan for v in vals]
        else:
            out[name] = [int(float(v)) if v and v.lower() not in ("none", "nan") else 0 for v in vals]
    return out[np.argsort(out["eta_c"], kind="stable")]


_SURFACES: dict[tuple, np.ndarray] = {}


def surface_at_rank(path: Path | str, channel: int, rho: int) -> np.ndarray:
    """:func:`read_operating_points`, cached on the file's size and mtime (the report reads each
    surface once for the table and once for the figures)."""
    path = Path(path)
    st = path.stat()
    key = (str(path.resolve()), int(channel), int(rho), st.st_size, st.st_mtime_ns)
    if key not in _SURFACES:
        if len(_SURFACES) >= 64:
            _SURFACES.clear()
        _SURFACES[key] = read_operating_points(path, channel, rho)
    return _SURFACES[key]


def thin_indices(f, n: int = CURVE_POINTS, keep: Sequence[int] = ()) -> np.ndarray:
    """About ``n`` row indices along a curve: half evenly in ``f``, half evenly in ``log10(1 - f)``
    (so ``f -> 1`` stays resolved), plus both ends and every index in ``keep``; sorted, so the
    curve keeps its row order. A curve of at most ``n`` rows is returned whole."""
    f = np.asarray(f, dtype=float)
    m = f.size
    extra = [int(k) for k in keep if k is not None and 0 <= int(k) < m]
    if m == 0:
        return np.empty(0, dtype=int)
    if m <= n:
        return np.arange(m)
    order = np.argsort(f, kind="stable")
    fs = f[order]
    half = max(n // 2, 2)
    g = -np.log10(np.clip(1.0 - fs, 1e-12, 1.0))
    picks = np.concatenate([np.searchsorted(fs, np.linspace(fs[0], fs[-1], half)),
                            np.searchsorted(g, np.linspace(g[0], g[-1], half))])
    picks = order[np.clip(picks, 0, m - 1)]
    return np.unique(np.concatenate([picks, [0, m - 1], extra]).astype(int))


# ------------------------------------------------------------------ one channel
@dataclass(frozen=True)
class ChannelCurve:
    """One channel's curves and marked points, with the ledger values the figures print."""

    channel: int
    rho: int | None                      # selection.min_r_sys_rho: the rank of the drawn fine curve
    curve: np.ndarray                    # surface rows at that rank (POINT_DTYPE; empty when absent)
    n_full: int                          # rows at that rank before thinning
    marker: int | None                   # index into ``curve`` of the least-residual (diagnostic) point
    keep_index: int | None               # index into ``curve`` of the f = 0 row
    selected_index: int | None           # index into ``curve`` of the selected point when it lies on this rank
    coarse: np.ndarray                   # coarse frontier rows (COARSE_DTYPE; empty when absent)
    coarse_index: int | None             # index into ``coarse`` of the frontier's least-R row
    least: Mapping                       # diagnostic point: rho, eta_q16, eta, masked_fraction, r_sys, R, cost, kept
    least_kind: str                      # 'diagnostic' | 'least residual' | ''
    least_basis: str                     # selection.diagnostic_basis
    selected: Mapping | None             # the selector's point when it selected one (same keys), else None
    replay: Mapping                      # the point on the evaluation block: kept, masked_fraction, r_sys, R
    coarse_min: Mapping                  # selection.coarse_min_R, coarse_min_R_eta, coarse_min_R_masked_fraction, coarse_R_at_flag, r_sys
    r_tol: float
    r_keep: float                        # selection.keep_everything_r_sys_calibration
    keep_ratio: float                    # r_keep / r_tol
    flag_rate: float                     # screening.survey_flag_rate_era
    r_tol_fs8: float                     # tolerance.r_tol_fs8
    fs8_wall: float                      # r_tol_fs8 / r_tol
    fs8_status: str
    floor_evidence: str
    floor_basis: str                     # null.floor_basis
    floor_db: float
    tau_quality: str                     # chain.tau_quality (the era chain)
    tau_c_minutes: float
    tau_c_high_minutes: float
    archive_tau_quality: str             # chain_archive.tau_quality
    archive_tau_c_high_minutes: float
    gain_basis: str                      # selection.gain_basis
    dashed: bool
    dashed_reason: str
    screening_class: str
    era: str
    status: str
    claim_status: str
    refusal: str
    surface: Path | None                 # the operating_points.csv read, when it exists
    frontier: Path | None                # the coarse_frontier.csv read, when it exists
    notes: tuple[str, ...]

    @property
    def point(self) -> Mapping:
        """The point the table prints: the selected point when there is one, else the diagnostic point."""
        return self.selected if self.selected is not None else self.least

    @property
    def point_kind(self) -> str:
        return "selected" if self.selected is not None else self.least_kind

    @property
    def replay_drawn(self) -> bool:
        return _finite(self.replay.get("R")) and _finite(self.replay.get("masked_fraction")) and (self.replay.get("kept") or 0) > 0


def _least_point(sel: Mapping) -> tuple[dict, str, str]:
    if _finite(sel.get("diagnostic_rho")):
        p = {"rho": _i(sel["diagnostic_rho"]), "eta_q16": _i(sel.get("diagnostic_eta_q16")), "eta": _f(sel.get("diagnostic_eta")),
             "masked_fraction": _f(sel.get("diagnostic_masked_fraction")), "r_sys": _f(sel.get("diagnostic_r_sys")),
             "R": _f(sel.get("diagnostic_R")), "cost": _f(sel.get("diagnostic_cost")), "kept": None}
        return p, "diagnostic", str(sel.get("diagnostic_basis") or "least residual on the calibration surface")
    if _finite(sel.get("min_r_sys_rho")):
        p = {"rho": _i(sel["min_r_sys_rho"]), "eta_q16": None, "eta": _f(sel.get("min_r_sys_eta")),
             "masked_fraction": _f(sel.get("min_r_sys_masked_fraction")), "r_sys": _f(sel.get("min_r_sys")),
             "R": _f(sel.get("min_R")), "cost": math.nan, "kept": None}
        return p, "least residual", "least residual on the calibration surface (min_r_sys; no diagnostic keys)"
    return {"rho": None, "eta_q16": None, "eta": math.nan, "masked_fraction": math.nan, "r_sys": math.nan, "R": math.nan,
            "cost": math.nan, "kept": None}, "", ""


def _find_row(rows: np.ndarray, point: Mapping) -> int | None:
    """The surface row of ``point`` (exact ``eta_q16`` when known, else the nearest ``eta``), verified
    against its residual and masked fraction."""
    if rows.size == 0 or not _finite(point.get("r_sys")):
        return None
    if point.get("eta_q16") is not None:
        hits = np.flatnonzero(rows["eta_q16"] == int(point["eta_q16"]))
        i = int(hits[0]) if hits.size else None
    elif _finite(point.get("eta")):
        i = int(np.argmin(np.abs(rows["eta"] - float(point["eta"]))))
    else:
        i = None
    if i is None:
        return None
    if (math.isclose(float(rows["r_sys"][i]), float(point["r_sys"]), rel_tol=1e-6, abs_tol=1e-12)
            and math.isclose(float(rows["masked_fraction"][i]), float(point["masked_fraction"]), abs_tol=1e-9)):
        return i
    return None


def floor_word(evidence: str, basis: str) -> str:
    """The floor cell: the evidence with the stated floor's population in brackets."""
    if not evidence:
        return ""
    short = FLOOR_BASIS_WORD.get(basis, basis or "")
    return f"{evidence} ({short})" if evidence == "stated" and short else evidence


def tau_word(quality: str, archive_quality: str = "") -> str:
    """The tau_c cell: the era chain's quality, with the archive-wide chain's when that is better."""
    if not quality:
        return ""
    word = TAU_WORD.get(quality, quality)
    if quality == "refused" and archive_quality in ("measured", "bounded_above"):
        word += f" (archive: {TAU_WORD[archive_quality]})"
    return word


def channel_curve(run: Run, ch: Channel, *, n_points: int = CURVE_POINTS) -> ChannelCurve:
    sel, chain, arch, tol, scr, nul = ch.selection, ch.chain, ch.section("chain_archive"), ch.tolerance, ch.screening, ch.null
    notes: list[str] = []
    rho = _i(sel.get("min_r_sys_rho"))
    r_tol = _f(sel.get("r_tol")) if _finite(sel.get("r_tol")) else _f(tol.get("r_tol_dilation"))
    least, least_kind, least_basis = _least_point(sel)
    if least_kind == "least residual":
        notes.append("diagnostic keys absent: the least-residual point is read from selection.min_r_sys_*")
    if rho is not None and least.get("rho") is not None and least["rho"] != rho:
        notes.append(f"the diagnostic point lies on rank {least['rho']}, the drawn curve on rank {rho}")
    if _finite(sel.get("keep_everything_r_sys_calibration")):
        r_keep = _f(sel["keep_everything_r_sys_calibration"])
    else:
        r_keep = _f(sel.get("r_sys_unmasked_calibration"))
        if _finite(r_keep):
            notes.append("keep_everything_r_sys_calibration absent: the keep-everything residual is r_sys_unmasked_calibration")

    base = Path(run.results_dir) / "channels" / f"ch{ch.channel:02d}"
    path = base / SURFACE_CSV
    rows = np.empty(0, dtype=POINT_DTYPE)
    surface = None
    if not ch.has("selection"):
        notes.append("selection section absent: no curve and no points")
    elif rho is None:
        notes.append(f"no evaluated point ({sel.get('status') or 'no status'}): no curve, no diagnostic, keep-everything, "
                     "replay or coarse values")
    elif not path.is_file():
        notes.append(f"{SURFACE_CSV} absent: no curve; the marked points are the ledger's")
    else:
        surface = path
        rows = surface_at_rank(path, ch.channel, rho)
        if rows.size == 0:
            notes.append(f"rank {rho} has no rows in {SURFACE_CSV}: no curve; the marked points are the ledger's")
    marker_full = keep_full = selected_full = None
    if rows.size:
        marker_full = _find_row(rows, least)
        if marker_full is not None:
            least["eta_q16"] = int(rows["eta_q16"][marker_full])
            least["kept"] = int(rows["kept"][marker_full])
            if not _finite(least.get("cost")):
                least["cost"] = float(rows["cost"][marker_full])
        elif least_kind:
            notes.append("diagnostic point not found on the surface at its rank: marked from the ledger, kept frames unknown")
        zero = np.flatnonzero(rows["masked_fraction"] == 0.0)
        keep_full = int(zero[-1]) if zero.size else None
        if keep_full is None:
            notes.append("no f = 0 row at this rank: the keep-everything point is the ledger's alone")
        elif _finite(r_keep) and not math.isclose(float(rows["r_sys"][keep_full]), r_keep, rel_tol=1e-6, abs_tol=1e-12):
            notes.append("the surface's f = 0 residual differs from keep_everything_r_sys_calibration: the ledger's is marked")

    selected = None
    if sel.get("rho") is not None and sel.get("eta_q16") is not None:
        selected = {"rho": _i(sel["rho"]), "eta_q16": _i(sel["eta_q16"]), "eta": _f(sel.get("eta")),
                    "masked_fraction": _f(sel.get("masked_fraction_calibration")), "r_sys": _f(sel.get("r_sys_calibration")),
                    "R": _f(sel.get("R_calibration")), "cost": _f(sel.get("cost")), "kept": None}
        if selected["rho"] != rho:
            notes.append(f"selected point lies on rank {selected['rho']}, the drawn curve on rank {rho}")
        elif rows.size:
            selected_full = _find_row(rows, selected)
            if selected_full is not None:
                selected["kept"] = int(rows["kept"][selected_full])
    elif ch.has("selection") and rho is not None:
        notes.append(f"no selected point ({sel.get('status') or 'no status'}; {sel.get('claim_status') or 'no claim status'}): "
                     "the diagnostic point is printed")

    idx = thin_indices(rows["masked_fraction"], n_points, keep=[k for k in (marker_full, keep_full, selected_full) if k is not None])
    curve = rows[idx]
    marker = int(np.searchsorted(idx, marker_full)) if marker_full is not None else None
    keep_index = int(np.searchsorted(idx, keep_full)) if keep_full is not None else None
    selected_index = int(np.searchsorted(idx, selected_full)) if selected_full is not None else None

    replay = {"kept": _i(sel.get("kept_evaluation")), "masked_fraction": _f(sel.get("masked_fraction_evaluation")),
              "r_sys": _f(sel.get("r_sys_evaluation")), "R": _f(sel.get("R_evaluation"))}
    if rho is not None and not _finite(replay["R"]):
        if replay["kept"] == 0:
            notes.append("the replay on the evaluation block kept no frame (kept_evaluation 0): no R_eval")
        else:
            notes.append("R_evaluation absent: no R_eval")

    coarse = np.empty(0, dtype=COARSE_DTYPE)
    frontier = None
    coarse_min = {"R": _f(sel.get("coarse_min_R")), "eta": _f(sel.get("coarse_min_R_eta")),
                  "masked_fraction": _f(sel.get("coarse_min_R_masked_fraction")), "R_at_flag": _f(sel.get("coarse_R_at_flag")),
                  "r_sys": math.nan}
    fpath = base / FRONTIER_CSV
    if rho is not None and fpath.is_file():
        frontier = fpath
        coarse = read_coarse_frontier(fpath, ch.channel)
        if coarse.size == 0:
            notes.append(f"{FRONTIER_CSV} has no rows for this channel: no coarse curve")
    elif rho is not None:
        notes.append(f"{FRONTIER_CSV} absent ({'floor ' + sel.get('floor_evidence') if sel.get('floor_evidence') else 'no floor'}): "
                     "no coarse curve, R_coarse and f_coarse are the ledger's" if _finite(coarse_min["R"]) else
                     f"{FRONTIER_CSV} absent and coarse_min_R undefined ({'floor ' + str(sel.get('floor_evidence')) if sel.get('floor_evidence') else 'no floor'}): "
                     "no coarse curve, R_coarse and f_coarse dashed")
    coarse_index = None
    if coarse.size:
        ok = np.isfinite(coarse["R"]) & coarse["evaluable"]
        if ok.any():
            cand = np.flatnonzero(ok)
            coarse_index = int(cand[np.argmin(coarse["R"][cand])])
            file_min = float(coarse["R"][coarse_index])
            if not _finite(coarse_min["R"]):
                coarse_min.update(R=file_min, eta=float(coarse["eta_c"][coarse_index]),
                                  masked_fraction=float(coarse["masked_fraction"][coarse_index]))
                notes.append("coarse_min_R absent from the ledger: R_coarse and f_coarse are read from the frontier file")
            elif not math.isclose(file_min, coarse_min["R"], rel_tol=1e-6, abs_tol=1e-12):
                notes.append("the frontier file's least R differs from selection.coarse_min_R: the ledger's is printed")
            coarse_min["r_sys"] = float(coarse["r_sys"][coarse_index])
        else:
            notes.append(f"no evaluable row with R in {FRONTIER_CSV}: no coarse curve")
    if not _finite(coarse_min["r_sys"]) and _finite(coarse_min["R"]) and _finite(r_tol):
        coarse_min["r_sys"] = coarse_min["R"] * r_tol

    floor_evidence = str(sel.get("floor_evidence") or nul.get("floor_evidence") or "")
    floor_basis = str(nul.get("floor_basis") or "")
    tau_quality = str(chain.get("tau_quality") or "") if ch.has("chain") else ""
    archive_tau = str(arch.get("tau_quality") or "") if ch.has("chain_archive") else ""
    reasons = []
    if floor_evidence != "measured":
        reasons.append(f"{floor_evidence} floor" if floor_evidence else "no floor")
    if tau_quality == "bounded_above":
        reasons.append("tau_c bound")
    elif tau_quality != "measured":
        reasons.append(f"tau_c {tau_quality}" if tau_quality else "tau_c absent")
    if tau_quality == "refused" and archive_tau in ("measured", "bounded_above"):
        notes.append(f"tau_c refused on the era chain and {TAU_WORD[archive_tau]} on the archive-wide chain "
                     f"(gain basis: {sel.get('gain_basis') or 'unstated'}); the curve is drawn on the era chain")
    r_tol_fs8 = _f(tol.get("r_tol_fs8"))
    fs8_status = str(tol.get("fs8_status") or "")
    fs8_wall = r_tol_fs8 / r_tol if _finite(r_tol_fs8) and _finite(r_tol) and r_tol > 0 else math.nan
    if not _finite(fs8_wall):
        notes.append(f"f sigma_8 wall unpriced ({fs8_status or 'no tolerance section'})")
    flag_rate = _f(scr.get("survey_flag_rate_era"))
    if not _finite(flag_rate):
        notes.append("survey flag rate absent")
    keep_ratio = r_keep / r_tol if _finite(r_keep) and _finite(r_tol) and r_tol > 0 else math.nan
    if not _finite(keep_ratio) and rho is not None:
        notes.append("keep-everything ratio undefined (keep_everything_r_sys_calibration or r_tol absent)")
    return ChannelCurve(
        channel=ch.channel, rho=rho, curve=curve, n_full=int(rows.size), marker=marker, keep_index=keep_index,
        selected_index=selected_index, coarse=coarse, coarse_index=coarse_index, least=least, least_kind=least_kind,
        least_basis=least_basis, selected=selected, replay=replay, coarse_min=coarse_min, r_tol=r_tol, r_keep=r_keep,
        keep_ratio=keep_ratio, flag_rate=flag_rate, r_tol_fs8=r_tol_fs8, fs8_wall=fs8_wall, fs8_status=fs8_status,
        floor_evidence=floor_evidence, floor_basis=floor_basis, floor_db=_f(sel.get("floor_db")),
        tau_quality=tau_quality, tau_c_minutes=_f(chain.get("tau_c_minutes")), tau_c_high_minutes=_f(chain.get("tau_c_high_minutes")),
        archive_tau_quality=archive_tau, archive_tau_c_high_minutes=_f(arch.get("tau_c_high_minutes")),
        gain_basis=str(sel.get("gain_basis") or ""), dashed=bool(reasons), dashed_reason="; ".join(reasons),
        screening_class=str(scr.get("screening_class") or ""), era=str(sel.get("era") or ""),
        status=str(sel.get("status") or ""), claim_status=str(sel.get("claim_status") or ""),
        refusal=str(sel.get("refusal") or ""), surface=surface, frontier=frontier, notes=tuple(notes))


def channel_curves(run: Run, *, n_points: int = CURVE_POINTS) -> list[ChannelCurve]:
    return [channel_curve(run, ch, n_points=n_points) for ch in run.channels]


def occupancy_wall(run: Run) -> float:
    prov = run.run.get("provisional")
    return _f(prov.get("occupancy_wall_masked_fraction")) if isinstance(prov, Mapping) else math.nan


# ------------------------------------------------------------------ the table fragment
def _ratio(value) -> tuple[str, str]:
    """A ratio cell: three significant figures, scientific from 1e4; returns (tex, plain rendering)."""
    if not _finite(value):
        return DASH, DASH
    x = float(value)
    if abs(x) >= 1e4:
        mag = int(math.floor(math.log10(abs(x))))
        mant = x / 10 ** mag
        if abs(round(mant, 1)) >= 10.0:
            mag += 1
            mant = x / 10 ** mag
        return rf"{mant:.1f}\times10^{{{mag}}}", f"{mant:.1f}e{mag}"
    text = fmt(x, 3, sig=True)
    return text, text


def _decimals(text: str) -> int | None:
    if text == DASH or "e" in text:
        return None
    return len(text.split(".")[1]) if "." in text else 0


def _math(text: str) -> str:
    return text if text == DASH else f"${text}$"


def _tau_text(c: ChannelCurve) -> str:
    """The tau_c annotation of a case panel."""
    if c.tau_quality == "measured" and _finite(c.tau_c_minutes):
        return rf"$\tau_c = {fmt(c.tau_c_minutes, 1)}$ min"
    if c.tau_quality == "bounded_above" and _finite(c.tau_c_high_minutes):
        return rf"$\tau_c \leq {fmt(c.tau_c_high_minutes, 1)}$ min (bound)"
    word = rf"$\tau_c$ {tex(c.tau_quality) or 'absent'}"
    if c.tau_quality == "refused" and c.archive_tau_quality == "bounded_above" and _finite(c.archive_tau_c_high_minutes):
        word += rf" on the era chain ($\leq {fmt(c.archive_tau_c_high_minutes, 1)}$ min archive-wide)"
    elif c.tau_quality == "refused" and c.archive_tau_quality == "measured":
        word += " on the era chain (measured archive-wide)"
    return word


def _case_note(cs: Sequence[ChannelCurve]) -> str:
    parts = []
    for ch in CASE_CHANNELS:
        c = next((c for c in cs if c.channel == ch), None)
        if c is None:
            parts.append(f"channel {ch} not in the run (empty panel)")
            continue
        floor = floor_word(c.floor_evidence, c.floor_basis) or "no floor"
        tau = tau_word(c.tau_quality, c.archive_tau_quality) or "tau_c absent"
        parts.append(f"channel {ch} ({floor} floor, tau_c {tau})")
    return f"case figure: {len(CASE_CHANNELS)} panels, " + "; ".join(parts) + \
        "; channel 33 is the stub's channel and its floor is stated, so channel 29 (the stated kept-half floor with a bounded tau_c) is drawn beside it"


def build(run: Run, *, curves: Sequence[ChannelCurve] | None = None) -> Fragment:
    """The marked-point table for ``fig:tolerance:twowalls`` and the numbers both figures print."""
    cs = list(curves) if curves is not None else channel_curves(run)
    frag = Fragment(NAME, ";".join(LABELS), "")
    rows = []
    for c in cs:
        key = f"ch09.twowalls.{{}}.ch{c.channel:02d}"
        row = {"channel": c.channel}

        def add(name, value, *, column=None, **kw):
            frag.add(key.format(name), value, row=row, column=column or (name if name in COLUMNS else "point"), **kw)

        p = c.point
        which = c.point_kind if _finite(p.get("r_sys")) else DASH
        curve_word = ("dashed" if c.dashed else "solid") if c.curve.size else DASH
        cells = [str(c.channel), curve_word, which, _math(fmt_int(p.get("rho"), thousands=False)),
                 _math(fmt_int(p.get("eta_q16"))), _math(fmt(p.get("eta"), 3)), _math(fmt(p.get("masked_fraction"), 3))]
        replay_r = c.replay["R"] if c.replay_drawn else math.nan
        for name, value, status in (("r_sys", p.get("r_sys"), "measured"), ("R", p.get("R"), "measured"),
                                    ("R_eval", replay_r, "measured"), ("R_keep", c.keep_ratio, "derived"),
                                    ("R_coarse", c.coarse_min["R"], "measured")):
            t, plain = _ratio(value)
            cells.append(_math(t))
            if t != DASH:
                add(name, float(value), precision=_decimals(plain), renderings=(plain, t), status=status)
        cells.append(_math(fmt(c.coarse_min["masked_fraction"], 3)))
        cells.append(_math(fmt(c.flag_rate, 3)))
        fs8 = fmt(c.fs8_wall, 3, sig=True)
        cells.append(_math(fs8))
        floor = floor_word(c.floor_evidence, c.floor_basis)
        tau = tau_word(c.tau_quality, c.archive_tau_quality)
        cells += [tex(floor) if floor else DASH, tex(tau) if tau else DASH]
        rows.append(cells)

        if curve_word != DASH:
            add("curve", curve_word, kind="text", renderings=(curve_word, c.dashed_reason or "measured floor and tau_c"))
            add("curve_points", int(c.curve.size), kind="int", column="curve")
        if c.coarse.size:
            add("coarse_points", int(c.coarse.size), kind="int", column="R_coarse")
        if which != DASH:
            add("point", which, kind="text", renderings=(which, c.least_basis if which != "selected" else "selected by the selector"))
        if _finite(p.get("rho")):
            add("rho", int(p["rho"]), kind="int")
        if _finite(p.get("eta_q16")):
            add("eta_q16", int(p["eta_q16"]), kind="int", renderings=(fmt_int(p["eta_q16"]), str(int(p["eta_q16"]))))
        if _finite(p.get("eta")):
            add("eta", float(p["eta"]), precision=3)
        if _finite(p.get("masked_fraction")):
            add("masked_fraction", float(p["masked_fraction"]), precision=3)
        if _finite(p.get("kept")):
            add("kept", int(p["kept"]), kind="int")
        if _finite(p.get("cost")):
            add("cost", float(p["cost"]), precision=1)
        if _finite(c.r_tol):
            add("r_tol", c.r_tol, precision=_decimals(fmt(c.r_tol, 3, sig=True)), renderings=(fmt(c.r_tol, 3, sig=True),), column="R")
        if _finite(c.r_keep):
            t, plain = _ratio(c.r_keep)
            add("r_keep", c.r_keep, precision=_decimals(plain), renderings=(plain, t), column="R_keep")
        if _finite(c.keep_ratio) and _finite(p.get("r_sys")) and p["r_sys"] > 0:
            ratio = c.r_keep / float(p["r_sys"])
            add("keep_over_proxy", ratio, precision=1, renderings=(fmt(ratio, 1),), status="derived", column="R_keep")
        if c.replay_drawn:
            add("f_eval", float(c.replay["masked_fraction"]), precision=3, column="R_eval")
            add("kept_eval", int(c.replay["kept"]), kind="int", column="R_eval")
        if _finite(c.coarse_min["masked_fraction"]):
            add("f_coarse", float(c.coarse_min["masked_fraction"]), precision=3)
        if _finite(c.coarse_min["eta"]):
            add("eta_coarse", float(c.coarse_min["eta"]), precision=3, column="R_coarse")
        if _finite(c.coarse_min["R_at_flag"]):
            t, plain = _ratio(c.coarse_min["R_at_flag"])
            add("R_coarse_at_flag", float(c.coarse_min["R_at_flag"]), precision=_decimals(plain), renderings=(plain, t), column="R_coarse")
        if _finite(c.flag_rate):
            add("flag_rate", c.flag_rate, precision=3)
        if _finite(c.fs8_wall):
            add("fs8_wall", c.fs8_wall, precision=_decimals(fs8), renderings=(fs8,), status="derived")
        if floor:
            add("floor", floor, kind="text", renderings=(floor, c.floor_evidence))
            add("floor_evidence", c.floor_evidence, kind="text", renderings=(c.floor_evidence,), column="floor")
        if c.floor_basis:
            add("floor_basis", c.floor_basis, kind="text", renderings=(c.floor_basis, FLOOR_BASIS_WORD.get(c.floor_basis, c.floor_basis)), column="floor")
        if _finite(c.floor_db):
            add("floor_db", c.floor_db, precision=1, column="floor", status="derived" if c.floor_evidence == "stated" else "measured")
        if tau:
            add("tau_quality", c.tau_quality, kind="text", renderings=(tau, c.tau_quality),
                status="bounded" if c.tau_quality == "bounded_above" else ("refused" if c.tau_quality == "refused" else "measured"))
        if c.tau_quality == "measured" and _finite(c.tau_c_minutes):
            add("tau_c_minutes", c.tau_c_minutes, precision=1, column="tau_quality")
        elif c.tau_quality == "bounded_above" and _finite(c.tau_c_high_minutes):
            add("tau_c_minutes", c.tau_c_high_minutes, precision=1, column="tau_quality", status="bounded")
        if c.archive_tau_quality:
            add("archive_tau_quality", c.archive_tau_quality, kind="text", column="tau_quality",
                renderings=(TAU_WORD.get(c.archive_tau_quality, c.archive_tau_quality),))
        for name, value in (("class", c.screening_class), ("status", c.status), ("gain_basis", c.gain_basis)):
            if value:
                add(name, value, kind="text", renderings=(value,))
        for note in c.notes:
            frag.notes.append(f"ch{c.channel:02d}: {note}")
    frag.tex = booktabs(list(HEADER), rows, ALIGN)

    # band-level values the figure draws
    wall = occupancy_wall(run)
    fs8 = sorted((c.fs8_wall, c.channel) for c in cs if _finite(c.fs8_wall))
    least = sorted((c.least["R"], c.channel) for c in cs if _finite(c.least.get("R")))
    keep_over = sorted((c.r_keep / c.least["r_sys"], c.channel) for c in cs
                       if _finite(c.r_keep) and _finite(c.least.get("r_sys")) and c.least["r_sys"] > 0)
    band = "ch09.twowalls.{}"
    frag.add(band.format("channels"), len(cs), kind="int", column="band")
    frag.add(band.format("dashed_channels"), sum(c.dashed and c.curve.size > 0 for c in cs), kind="int", column="band")
    frag.add(band.format("solid_channels"), sum((not c.dashed) and c.curve.size > 0 for c in cs), kind="int", column="band")
    frag.add(band.format("selected_channels"), sum(c.selected is not None for c in cs), kind="int", column="band")
    frag.add(band.format("diagnostic_channels"), sum(c.selected is None and _finite(c.least.get("R")) for c in cs), kind="int", column="band")
    frag.add(band.format("no_point_channels"), sum(not _finite(c.point.get("R")) for c in cs), kind="int", column="band")
    frag.add(band.format("curves_drawn"), sum(c.curve.size > 0 for c in cs), kind="int", column="band")
    frag.add(band.format("coarse_drawn"), sum(c.coarse_index is not None for c in cs), kind="int", column="band")
    frag.add(band.format("replay_channels"), sum(c.replay_drawn for c in cs), kind="int", column="band")
    if _finite(wall):
        frag.add(band.format("occupancy_wall"), wall, precision=2, column="band")
    else:
        frag.notes.append("occupancy wall not drawn: run.provisional.occupancy_wall_masked_fraction absent")
    if fs8:
        frag.add(band.format("fs8_wall_low"), fs8[0][0], precision=3, renderings=(fmt(fs8[0][0], 3), fmt(fs8[0][0], 3, sig=True)),
                 status="derived", column="band")
        frag.add(band.format("fs8_wall_high"), fs8[-1][0], precision=3, renderings=(fmt(fs8[-1][0], 3), fmt(fs8[-1][0], 3, sig=True)),
                 status="derived", column="band")
        frag.add(band.format("fs8_factor_low"), 1 / fs8[-1][0], precision=0, status="derived", column="band")
        frag.add(band.format("fs8_factor_high"), 1 / fs8[0][0], precision=0, status="derived", column="band")
        frag.add(band.format("fs8_priced_channels"), len(fs8), kind="int", column="band")
    else:
        frag.notes.append("f sigma_8 band not drawn: no channel has a priced r_tol_fs8")
    if least:
        frag.add(band.format("least_R_min"), least[0][0], precision=_decimals(_ratio(least[0][0])[1]),
                 renderings=_ratio(least[0][0])[::-1], column="band")
        frag.add(band.format("least_R_min_channel"), least[0][1], kind="int", column="band")
        frag.add(band.format("least_R_max"), least[-1][0], precision=_decimals(_ratio(least[-1][0])[1]),
                 renderings=_ratio(least[-1][0])[::-1], column="band")
        frag.add(band.format("least_R_max_channel"), least[-1][1], kind="int", column="band")
        frag.add(band.format("in_recovery_box_channels"), sum(1 for r, ch in least if r <= 1.0), kind="int", column="band")
    if keep_over:
        frag.add(band.format("keep_over_proxy_low"), keep_over[0][0], precision=1, status="derived", column="band")
        frag.add(band.format("keep_over_proxy_high"), keep_over[-1][0], precision=1, status="derived", column="band")
    coarse_below = [c.channel for c in cs if _finite(c.coarse_min["R"]) and _finite(c.least.get("R")) and c.coarse_min["R"] < c.least["R"]]
    frag.add(band.format("coarse_below_fine_channels"), len(coarse_below), kind="int", column="band")

    # the case figure's annotations
    for ch in CASE_CHANNELS:
        case = next((c for c in cs if c.channel == ch), None)
        if case is None:
            frag.notes.append(f"case figure: channel {ch} not in the run")
            continue
        ck = f"ch09.case.{{}}.ch{ch:02d}"
        crow = {"channel": ch}
        frag.add(ck.format("channel"), case.channel, kind="int", row=crow, column="case")
        if case.rho is not None:
            frag.add(ck.format("rho"), case.rho, kind="int", row=crow, column="case")
        least_r = case.least.get("r_sys")
        values = (("r_keep", case.r_keep, None, "measured"), ("r_tol", case.r_tol, None, "measured"),
                  ("r_tol_fs8", case.r_tol_fs8, None, "measured"), ("r_sys", least_r, None, "measured"),
                  ("eta", case.least.get("eta"), 3, "measured"),
                  ("masked_fraction", case.least.get("masked_fraction"), 3, "measured"), ("R", case.least.get("R"), None, "measured"),
                  ("R_keep", case.keep_ratio, None, "derived"),
                  ("R_fs8", float(least_r) / case.r_tol_fs8 if _finite(least_r) and _finite(case.r_tol_fs8) and case.r_tol_fs8 > 0 else math.nan, None, "derived"),
                  ("keep_over_proxy", case.r_keep / float(least_r) if _finite(least_r) and float(least_r) > 0 and _finite(case.r_keep) else math.nan, 1, "derived"),
                  ("r_coarse_min", case.coarse_min["r_sys"], None, "measured"), ("f_coarse_min", case.coarse_min["masked_fraction"], 3, "measured"),
                  ("r_eval", case.replay["r_sys"] if case.replay_drawn else math.nan, None, "measured"),
                  ("f_eval", case.replay["masked_fraction"] if case.replay_drawn else math.nan, 3, "measured"),
                  ("flag_rate", case.flag_rate, 3, "measured"), ("floor_db", case.floor_db, 1, "derived" if case.floor_evidence == "stated" else "measured"),
                  ("tau_c_minutes", case.tau_c_minutes if case.tau_quality == "measured" else case.tau_c_high_minutes, 1,
                   "bounded" if case.tau_quality == "bounded_above" else "measured"))
        for name, value, prec, status in values:
            if _finite(value):
                t, plain = _ratio(value) if prec is None else (fmt(value, prec), fmt(value, prec))
                frag.add(ck.format(name), float(value), precision=_decimals(plain), renderings=(plain, t), status=status, row=crow, column="case")
        if _finite(case.least.get("kept")):
            frag.add(ck.format("kept"), int(case.least["kept"]), kind="int", row=crow, column="case")
        if case.replay_drawn:
            frag.add(ck.format("kept_eval"), int(case.replay["kept"]), kind="int", row=crow, column="case")
        for name, value in (("floor_evidence", case.floor_evidence), ("floor_basis", case.floor_basis), ("tau_quality", case.tau_quality),
                            ("archive_tau_quality", case.archive_tau_quality), ("status", case.status), ("era", case.era),
                            ("class", case.screening_class), ("curve", ("dashed" if case.dashed else "solid") if case.curve.size else "")):
            if value:
                frag.add(ck.format(name), value, kind="text", renderings=(value, TAU_WORD.get(value, FLOOR_BASIS_WORD.get(value, value))),
                         row=crow, column="case")
        if case.curve.size == 0:
            frag.notes.append(f"case figure: channel {ch} has no curve")
    frag.add("ch09.case.panels", len(CASE_CHANNELS), kind="int", column="case")
    frag.add("ch09.case.channels", ";".join(str(ch) for ch in CASE_CHANNELS), kind="text",
             renderings=(", ".join(str(ch) for ch in CASE_CHANNELS),), column="case")
    frag.notes.append(_case_note(cs))
    n_sel = sum(c.selected is not None for c in cs)
    if n_sel == 0:
        frag.notes.append("no channel has a selected point: the point columns print the diagnostic point (selection.diagnostic_*, the "
                          "least-residual point of the calibration surface) and R_eval its replay on the evaluation block")
    frag.notes.append("the survey flag rate is drawn on the f axis only: the ledger carries no residual at the survey flag")
    frag.notes.append("alternative flaggers are not in the archive ledger and are not drawn on the case figure")
    frag.inputs = run.inputs() + [c.surface for c in cs if c.surface is not None] + [c.frontier for c in cs if c.frontier is not None]
    return frag


# ------------------------------------------------------------------ the figures
def write_curves_csv(curves: Sequence[ChannelCurve], path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(CURVE_COLUMNS)
        for c in curves:
            for i, row in enumerate(c.curve):
                marker = ("diagnostic" if i == c.marker else "selected" if i == c.selected_index
                          else "keep_everything" if i == c.keep_index else "")
                w.writerow([c.channel, "fine", int(row["rho"]), int(row["eta_q16"]), repr(float(row["eta"])), int(row["kept"]),
                            repr(float(row["masked_fraction"])), repr(float(row["r_sys"])), repr(float(row["tolerance_fraction"])), marker])
            for i, row in enumerate(c.coarse):
                if not (row["evaluable"] and _finite(row["R"])):
                    continue
                w.writerow([c.channel, "coarse", "", "", repr(float(row["eta_c"])), int(row["kept"]), repr(float(row["masked_fraction"])),
                            repr(float(row["r_sys"])), repr(float(row["R"])), "coarse_min" if i == c.coarse_index else ""])
    return path


def _spread(values: Sequence[float], gap: float, lo: float = 0.0, hi: float = 1.0) -> list[float]:
    """Push label positions apart by at least ``gap`` inside ``[lo, hi]``, keeping their order."""
    n = len(values)
    if n == 0:
        return []
    order = sorted(range(n), key=lambda i: values[i])
    y = [max(lo, min(hi, float(values[i]))) for i in order]
    for i in range(1, n):
        y[i] = max(y[i], y[i - 1] + gap)
    over = y[-1] - hi
    if over > 0:
        y = [v - over for v in y]
    for i in range(n - 2, -1, -1):
        y[i] = min(y[i], y[i + 1] - gap)
    y[0] = max(y[0], lo)
    for i in range(1, n):
        y[i] = max(y[i], y[i - 1] + gap)
    out = [0.0] * n
    for pos, i in enumerate(order):
        out[i] = y[pos]
    return out


def _class_colors():
    from ... import style
    return {"recovery candidate": style.CONDITIONAL, "measurement-bound on floor": style.MODEL,
            "measurement-bound on tau_c": style.GOLD, "occupancy-wall excision candidate": style.FAILURE,
            "off-era": style.PENDING}


def _class_label(name: str) -> str:
    return name.replace("tau_c", r"$\tau_c$") if name else "unclassified"


def _coarse_ok(c: ChannelCurve) -> np.ndarray:
    return np.isfinite(c.coarse["R"]) & (c.coarse["R"] > 0) & c.coarse["evaluable"] if c.coarse.size else np.zeros(0, dtype=bool)


def _panel_letter(ax, letter: str) -> None:
    ax.text(-0.075, 1.01, f"({letter})", transform=ax.transAxes, ha="left", va="bottom", fontsize=9.0, fontweight="bold")


def _render_two_walls(run: Run, cs: Sequence[ChannelCurve], stem: Path) -> list[Path]:
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    from ... import style

    colors = _class_colors()
    wall = occupancy_wall(run)
    fs8 = [c.fs8_wall for c in cs if _finite(c.fs8_wall)]
    ys = [float(v) for c in cs for v in (*c.curve["tolerance_fraction"], *c.coarse["R"][_coarse_ok(c)], c.keep_ratio, c.least.get("R"),
                                         c.replay["R"] if c.replay_drawn else math.nan) if _finite(v) and float(v) > 0]
    ylo = min(min(fs8) if fs8 else 1.0, 1.0) / 4.0
    yhi = (max(ys) if ys else 10.0) * 4.0
    fig, ax = plt.subplots(figsize=(style.TEXT_WIDTH, 4.7))
    style.clean_axes(ax, grid="y")
    ax.set_yscale("log")
    ax.set_xlim(-0.015, 1.0)
    ax.set_ylim(ylo, yhi)
    span = math.log10(yhi) - math.log10(ylo)

    def yfrac(v: float) -> float:
        return (math.log10(v) - math.log10(ylo)) / span

    def yat(frac: float) -> float:
        return 10 ** (math.log10(ylo) + frac * span)

    if _finite(wall):
        ax.fill_between([0.0, wall], ylo, 1.0, color=style.LIGHT_GREEN, lw=0, zorder=0)
        ax.axvspan(wall, 1.0, color=style.LIGHT_RED, lw=0, zorder=0)
        ax.axvline(wall, color=style.FAILURE, lw=0.9, zorder=1)
        ax.text(wall, 1.004, f"occupancy wall, $f = {wall:g}$", transform=ax.get_xaxis_transform(),
                ha="right", va="bottom", fontsize=6.8, color=style.FAILURE)
        ax.text(wall / 2, yat(yfrac(1.0) * 0.5 + (yfrac(max(fs8)) * 0.5 if fs8 else 0.0)), "recovery box",
                ha="center", va="center", fontsize=7.2, color=style.CONDITIONAL)
    ax.axhline(1.0, color=style.FAILURE, lw=0.9, zorder=1)
    ax.text(0.02, 1.0 * 10 ** (0.02 * span), "bias wall, $R = 1$", ha="left", va="bottom", fontsize=7.2, color=style.FAILURE)
    if fs8:
        ax.axhspan(min(fs8), max(fs8), color=style.LIGHT_ORANGE, lw=0, zorder=0)
        priced = [c.channel for c in cs if _finite(c.fs8_wall)]
        ax.text(0.02, math.sqrt(min(fs8) * max(fs8)), rf"$f\sigma_8$ wall, priced bins (ch {min(priced)} to {max(priced)}): "
                rf"$R = {fmt(min(fs8), 3, sig=True)}$ to ${fmt(max(fs8), 3, sig=True)}$",
                ha="left", va="center", fontsize=7.0, color=style.MODEL)

    label_y = []
    label_xy = []
    for c in cs:
        color = colors.get(c.screening_class, style.MUTED)
        ls = "--" if c.dashed else "-"
        ok = _coarse_ok(c)
        if ok.any():
            ax.plot(c.coarse["masked_fraction"][ok], c.coarse["R"][ok], ls=":", lw=0.9, color=color, alpha=0.8, zorder=2)
        if c.curve.size:
            ax.plot(c.curve["masked_fraction"], c.curve["tolerance_fraction"], ls=ls, lw=1.0, color=color, alpha=0.9, zorder=3)
        if _finite(c.least.get("masked_fraction")) and _finite(c.least.get("R")):
            ax.plot([c.least["masked_fraction"]], [c.least["R"]], marker="o", ms=4.2, mfc=color, mec=style.INK, mew=0.5, ls="none", zorder=5)
            anchor = (float(c.least["masked_fraction"]), float(c.least["R"]))
        elif _finite(c.keep_ratio):
            anchor = (0.0, float(c.keep_ratio))
        else:
            anchor = None
        if c.replay_drawn:
            ax.plot([c.replay["masked_fraction"]], [c.replay["R"]], marker="^", ms=4.6, mfc="none", mec=color, mew=0.8, ls="none", zorder=5)
        if c.selected is not None and _finite(c.selected.get("masked_fraction")) and _finite(c.selected.get("R")):
            ax.plot([c.selected["masked_fraction"]], [c.selected["R"]], marker="*", ms=8, mfc=color, mec=style.INK, mew=0.5, ls="none", zorder=6)
        if _finite(c.keep_ratio):
            ax.plot([0.0], [c.keep_ratio], marker="s", ms=3.8, mfc="white", mec=color, mew=0.9, ls="none", zorder=5)
        if _finite(c.flag_rate):
            ax.vlines(c.flag_rate, 0.0, 0.03, transform=ax.get_xaxis_transform(), color=color, lw=0.9, zorder=4)
        if anchor is not None:
            label_y.append(yfrac(anchor[1]))
            label_xy.append((c.channel, anchor))
    for (channel, anchor), yf in zip(label_xy, _spread(label_y, 0.031, 0.0, 1.0)):
        ax.annotate(str(channel), xy=anchor, xycoords="data", xytext=(1.018, yf), textcoords="axes fraction",
                    fontsize=6.8, color=style.INK, ha="left", va="center", annotation_clip=False,
                    arrowprops=dict(arrowstyle="-", lw=0.4, color=style.MUTED, shrinkA=0, shrinkB=1.5))

    ax.set_xlabel(r"masked fraction $f$ (each fine curve at the rank $\rho$ of its least-residual point)")
    ax.set_ylabel(r"$R = r_{\mathrm{proxy}} / r_{\mathrm{tol}}$ (dilation tier of the channel's bin)")
    present = [k for k in colors if any(c.screening_class == k for c in cs)]
    handles = [Line2D([0], [0], color=colors[k], lw=1.6, label=_class_label(k)) for k in present]
    handles += [Line2D([0], [0], color=style.INK, lw=1.0, ls="-", label=r"solid: measured floor and $\tau_c$"),
                Line2D([0], [0], color=style.INK, lw=1.0, ls="--", label=r"dashed: stated floor or bounded $\tau_c$"),
                Line2D([0], [0], color=style.INK, lw=0.9, ls=":", label="dotted: coarse rule"),
                Line2D([0], [0], marker="o", ms=4.2, mfc=style.PAPER, mec=style.INK, ls="none", label="diagnostic point (calibration)"),
                Line2D([0], [0], marker="^", ms=4.6, mfc="none", mec=style.INK, ls="none", label="the same point, evaluation block"),
                Line2D([0], [0], marker="s", ms=3.8, mfc="white", mec=style.INK, ls="none", label=r"keep everything ($f = 0$)"),
                Line2D([0], [0], marker="|", ms=7, color=style.INK, ls="none", label="survey flag rate")]
    if any(c.selected is not None for c in cs):
        handles.append(Line2D([0], [0], marker="*", ms=8, mfc=style.PAPER, mec=style.INK, ls="none", label=r"selected $(\rho^\star, \eta^\star)$"))
    fig.legend(handles=handles, loc="lower center", ncol=2, fontsize=6.4, bbox_to_anchor=(0.5, 0.004), handlelength=2.0,
               columnspacing=1.0, borderaxespad=0.0, frameon=False)
    fig.subplots_adjust(left=0.115, right=0.93, top=0.955, bottom=0.30)
    return _save(fig, stem, "The two walls: every channel in the (masked fraction, residual) plane")


def _case_panel(ax, run: Run, c: ChannelCurve | None, channel: int, letter: str, *, xlabel: bool) -> None:
    from ... import style

    style.clean_axes(ax, grid="y")
    ax.set_yscale("log")
    ax.set_xlim(-0.015, 1.0)
    _panel_letter(ax, letter)
    if c is None:
        ax.text(0.5, 0.5, f"channel {channel} is not in this run", transform=ax.transAxes, ha="center", va="center")
        return
    wall = occupancy_wall(run)
    color = _class_colors().get(c.screening_class, style.MEASURED)
    ok = _coarse_ok(c)
    ys = [float(v) for v in (*c.curve["r_sys"], *c.coarse["r_sys"][ok], c.r_keep, c.least.get("r_sys"), c.r_tol, c.r_tol_fs8,
                             c.replay["r_sys"] if c.replay_drawn else math.nan) if _finite(v) and float(v) > 0]
    ylo = min(ys) / 4.0 if ys else 1e-3
    yhi = max(ys) * 4.0 if ys else 10.0
    ax.set_ylim(ylo, yhi)
    span = math.log10(yhi) - math.log10(ylo)

    def yat(frac: float) -> float:
        return 10 ** (math.log10(ylo) + frac * span)

    # walls and references (vertical labels stand on the axis floor, clear of the curves)
    if _finite(wall):
        ax.axvspan(wall, 1.0, color=style.LIGHT_RED, lw=0, zorder=0)
        ax.axvline(wall, color=style.FAILURE, lw=0.9, zorder=1)
        ax.text(wall - 0.008, 0.965, f"occupancy wall, $f = {wall:g}$", transform=ax.get_xaxis_transform(),
                ha="right", va="top", fontsize=6.4, color=style.FAILURE)
    if _finite(c.r_tol):
        ax.axhline(c.r_tol, color=style.FAILURE, lw=0.9, zorder=1)
        ax.text(0.02, c.r_tol * 10 ** (0.02 * span), rf"bias wall: dilation tolerance $r_{{\mathrm{{tol}}}} = {fmt(c.r_tol, 3, sig=True)}$",
                ha="left", va="bottom", fontsize=6.8, color=style.FAILURE)
    if _finite(c.r_tol_fs8):
        ax.axhline(c.r_tol_fs8, color=style.MODEL, lw=0.9, ls=(0, (1, 2)), zorder=1)
        ax.text(0.02, c.r_tol_fs8 * 10 ** (0.02 * span), rf"$f\sigma_8$ tolerance $r_{{\mathrm{{tol}}}}(f\sigma_8) = {fmt(c.r_tol_fs8, 3, sig=True)}$",
                ha="left", va="bottom", fontsize=6.8, color=style.MODEL)
    if _finite(c.flag_rate):
        ax.axvline(c.flag_rate, color=style.PENDING, lw=0.8, ls=(0, (1, 2)), zorder=1)
        ax.text(c.flag_rate - 0.01, yat(0.06), f"survey flag rate {fmt(c.flag_rate, 3)}", rotation=90, ha="right", va="bottom",
                fontsize=6.6, color=style.PENDING)
    ax.text(0.985, yat(0.5), "excision: no residual, no measurement", rotation=90, ha="right", va="center", fontsize=6.6, color=style.INK)

    # curves and marked points
    notes: list[tuple[str, tuple[float, float] | None]] = []
    if ok.any():
        ax.plot(c.coarse["masked_fraction"][ok], c.coarse["r_sys"][ok], ls=":", lw=1.1, color=color, zorder=3)
    if c.curve.size:
        ax.plot(c.curve["masked_fraction"], c.curve["r_sys"], ls="--" if c.dashed else "-", lw=1.2, color=color, zorder=4)
    if _finite(c.r_keep):
        ax.plot([0.0], [c.r_keep], marker="s", ms=4.5, mfc="white", mec=color, mew=1.0, ls="none", zorder=5)
        over = rf"; ${_ratio(c.keep_ratio)[0]}\times$ over the dilation tolerance" if _finite(c.keep_ratio) else ""
        notes.append((rf"keep everything: $r = {fmt(c.r_keep, 3, sig=True)}${over}", (0.0, float(c.r_keep))))
    if _finite(c.least.get("masked_fraction")) and _finite(c.least.get("r_sys")):
        f0, r0 = float(c.least["masked_fraction"]), float(c.least["r_sys"])
        ax.plot([f0], [r0], marker="o", ms=5, mfc=color, mec=style.INK, mew=0.5, ls="none", zorder=6)
        kept = f", {fmt_int(c.least['kept'])} kept frames" if _finite(c.least.get("kept")) else ""
        over = rf"; ${_ratio(c.least['R'])[0]}\times$ over" if _finite(c.least.get("R")) else ""
        notes.append((rf"{c.point_kind or 'least residual'} (rank $\rho = {c.least['rho']}$): $r = {fmt(r0, 3, sig=True)}$ at $f = {fmt(f0, 3)}${over}{kept}",
                      (f0, r0)))
    if ok.any() and c.coarse_index is not None:
        f1, r1 = float(c.coarse["masked_fraction"][c.coarse_index]), float(c.coarse["r_sys"][c.coarse_index])
        ax.plot([f1], [r1], marker="D", ms=3.6, mfc="white", mec=color, mew=0.9, ls="none", zorder=5)
        notes.append((rf"coarse rule, least: $r = {fmt(r1, 3, sig=True)}$ at $f = {fmt(f1, 3)}$, $\eta_c = {fmt(c.coarse['eta_c'][c.coarse_index], 2)}$",
                      (f1, r1)))
    if c.replay_drawn and _finite(c.replay.get("r_sys")):
        fe, re_ = float(c.replay["masked_fraction"]), float(c.replay["r_sys"])
        ax.plot([fe], [re_], marker="^", ms=5.2, mfc="none", mec=color, mew=0.9, ls="none", zorder=6)
        notes.append((rf"replayed on the evaluation block: $r = {fmt(re_, 3, sig=True)}$ at $f = {fmt(fe, 3)}$, {fmt_int(c.replay['kept'])} kept frames",
                      (fe, re_)))
    elif c.replay.get("kept") == 0:
        notes.append(("replayed on the evaluation block: no frame kept, no residual", None))
    for i, (text, xy) in enumerate(notes):       # a block in the empty band between the curves and the walls
        y = 0.72 - 0.068 * i
        if xy is None:
            ax.text(0.27, y, text, transform=ax.transAxes, ha="left", va="center", fontsize=6.6, color=style.MUTED)
        else:
            ax.annotate(text, xy=xy, xycoords="data", xytext=(0.27, y), textcoords="axes fraction", fontsize=6.6, color=style.INK,
                        ha="left", va="center", arrowprops=dict(arrowstyle="-", lw=0.4, color=style.MUTED, shrinkA=0, shrinkB=2.5))

    # the header, above the axes
    basis = tex(c.floor_basis).replace(r"mu\_0", r"$\mu_0$") if c.floor_basis and c.floor_basis != "none" else ""
    floor = f"floor {tex(c.floor_evidence) or 'absent'}" + (f": {basis}" if basis else "") + \
        (f", ${fmt(c.floor_db, 1)}$ dB" if _finite(c.floor_db) else "")
    head = (f"channel {c.channel}, era {tex(c.era) or DASH}; selector: {tex(c.status) or DASH}; "
            f"{c.point_kind or 'no'} point drawn\n{floor}; {_tau_text(c)}")
    ax.text(0.0, 1.02, head, transform=ax.transAxes, ha="left", va="bottom", fontsize=6.8, color=style.INK, linespacing=1.3)
    if xlabel:
        ax.set_xlabel(r"masked fraction $f$")


def _render_case(run: Run, cs: Sequence[ChannelCurve], stem: Path) -> list[Path]:
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    from ... import style

    n = len(CASE_CHANNELS)
    fig, axes = plt.subplots(n, 1, figsize=(style.TEXT_WIDTH, 3.0 * n + 0.6), sharex=True)
    axes = np.atleast_1d(axes)
    for ax, ch, letter in zip(axes, CASE_CHANNELS, "abcdefgh"):
        c = next((c for c in cs if c.channel == ch), None)
        _case_panel(ax, run, c, ch, letter, xlabel=ax is axes[-1])
    handles = [Line2D([0], [0], color=style.INK, lw=1.2, ls="-", label=r"pilot proxy along $\eta$ (solid: measured floor and $\tau_c$)"),
               Line2D([0], [0], color=style.INK, lw=1.2, ls="--", label=r"pilot proxy along $\eta$ (dashed: upper bound)"),
               Line2D([0], [0], color=style.INK, lw=1.1, ls=":", label=r"coarse rule along $\eta_c$"),
               Line2D([0], [0], marker="s", ms=4.5, mfc="white", mec=style.INK, ls="none", label="keep everything"),
               Line2D([0], [0], marker="o", ms=5, mfc=style.PAPER, mec=style.INK, ls="none", label="diagnostic point"),
               Line2D([0], [0], marker="^", ms=5.2, mfc="none", mec=style.INK, ls="none", label="replayed on the evaluation block"),
               Line2D([0], [0], marker="D", ms=3.6, mfc="white", mec=style.INK, ls="none", label="coarse rule, least residual"),
               Line2D([0], [0], color=style.FAILURE, lw=0.9, label="bias wall (dilation tolerance)"),
               Line2D([0], [0], color=style.MODEL, lw=0.9, ls=(0, (1, 2)), label=r"$f\sigma_8$ tolerance")]
    fig.legend(handles=handles, loc="lower center", ncol=2, fontsize=6.4, bbox_to_anchor=(0.5, 0.004), handlelength=2.0,
               columnspacing=1.0, borderaxespad=0.0, frameon=False)
    fig.subplots_adjust(left=0.13, right=0.95, top=0.93, bottom=0.19, hspace=0.28)
    # one y label for the stack: the residual convention is the same on every panel
    fig.text(0.018, 0.56, r"$r_{\mathrm{proxy}}$ (floor-bounded shelf, linear, $\times$ chain gain)",
             rotation=90, ha="left", va="center", fontsize=8.0, color=style.INK)
    return _save(fig, stem, "Every policy on the residual axis, two channels")


def _save(fig, stem: Path, title: str) -> list[Path]:
    import matplotlib.pyplot as plt

    from ... import style

    stem.parent.mkdir(parents=True, exist_ok=True)
    png = stem.with_suffix(".png")
    fig.savefig(png, format="png", dpi=220)
    with style.stable_pdf_subset_tags():
        pdf = style.save(fig, stem.with_suffix(".pdf"), title=title)
    plt.close(fig)
    return [pdf, png]


def render(run: Run, out_dir: Path | str, *, require_tex: bool | None = None, curves: Sequence[ChannelCurve] | None = None) -> list[Path]:
    """Both figures (PDF and PNG each) and the drawn curves' CSV, directly under ``out_dir`` (the
    report's figures directory); returns the paths (CSV, two walls, case). The style is applied
    when ``require_tex`` is given; otherwise the caller's ``style.configure`` stands."""
    if require_tex is not None:
        from ... import style

        style.configure(require_tex=require_tex)
    out = Path(out_dir)
    cs = list(curves) if curves is not None else channel_curves(run)
    paths = [write_curves_csv(cs, out / CURVES_CSV)]
    paths += _render_two_walls(run, cs, out / FIGURE_TWO_WALLS)
    paths += _render_case(run, cs, out / FIGURE_CASE)
    return paths


def report(run: Run, out_dir: Path | str, *, commit: str, generated: str, require_tex: bool = True) -> dict:
    """Figures, curves CSV, table fragment, numbers and manifest for one run, reading each surface once."""
    out = Path(out_dir)
    cs = channel_curves(run)
    artifacts = render(run, out / "figures", require_tex=require_tex, curves=cs)
    return write_report(run, out, [lambda r: build(r, curves=cs)], commit=commit, generated=generated, extra_artifacts=artifacts)
