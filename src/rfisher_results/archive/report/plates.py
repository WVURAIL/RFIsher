"""Appendix C's per-channel diagnostic plates, regenerated from the v5 products.

``render(run, out_dir)`` draws one plate per ledger channel
(``fig_archive_plate_chNN.pdf`` and a companion ``.png``) in the dissertation
style (:mod:`rfisher_results.style`; the caller applies ``style.configure()``
first, ``configure(require_tex=False)`` only for a preview).  ``build(run)`` is
the report builder: a :class:`core.Fragment` whose ``tex`` is a one-row-per-
channel booktabs table of what each plate draws and whose numbers carry every
value a plate prints.  Both go through :func:`plates`, which computes each
channel's layers exactly once per process (opening a product costs one pass
over its per-frame spectra), so a report that renders and then builds reads
each product once.

**fig:archive:atlas:NN** (Appendix~C).  Five layers, in the appendix's own
order.  Every layer is drawn on the *current era* of the channel's ledger ---
``era.current_first_month .. era.current_last_month`` intersected with the
frames the health gate admits and with the frames that carry a recorded time,
which is the run's own era mask (frames without a time are in no block, and
the count excluded is printed).  The one exception is the offset-containment
panel, which follows the run and reads the *previous on era* on the five
channels whose current era is a transmitter-off era, because the peak offsets
of an off era measure nothing; the panel says which era it drew.  The gate
is pilot-proxy's ``pilotproxy_archive_frame_health_gate_v1``; where
``pilot_proxy`` cannot be imported the mask falls back to valid frames alone,
which admits the frames the gate would have removed, and the plate's head and
the fragment's notes say so rather than letting the counts pass for the run's.

  (a) coarse ``F/mu_0``   histogram of ``products.Product.statistic`` over the
                          current-era frames, logarithmic counts, with the
                          survival count ``N(> x)`` --- the tail complementary
                          distribution on the same count axis --- and the null
                          bulk the threshold was priced against overlaid:
                          ``null.coarse_centre`` (the bulk median) plus and
                          minus ``null.coarse_core_sigma`` (its left-side core
                          scale), read on the calibration block of the same
                          era.  ``F/mu_0 = 1`` is drawn as the survey flag's
                          boundary; ``mu_0`` is the ratio-of-expected-powers
                          scale of the declared white/isotropic model, not a
                          claim about any finite-sample null mean
  (b) normalized level    the same statistic in decibels,
                          ``products.Product.level_db = 10 log10(F/mu_0)``,
                          with 0 dB and the era's median level
                          (``era.current_level_median_db``) marked
  (c) input power         ``baseband_power_linear``: the decoded native
                          complex-``int4`` mean input power per frame, on a
                          logarithmic axis, with the negative-full-scale
                          ceiling (128 native units) drawn.  The frames at that
                          rail are what the frame-health gate removes, so an
                          admitted frame never sits on it
  (d) fine ``Z(rho)``     the designated-window statistic at the rank of the
                          channel's diagnostic point: ``Z_i(rho) = max_{f in D}
                          T_i[f] / T_i,(rho)``, with ``D`` the designated set of
                          the selection's anchor bin (``+-2`` bins), ``T`` the
                          fine power ratio ``2 S_0 / (S_1 + S_2)`` of
                          ``products.fine_power_ratio``, and ``T_(rho)`` the
                          ``rho``-th smallest bulk-bin value among the bulk bins
                          with a positive reference denominator --- the exact
                          keep boundary of ``rfisher.residual_scores`` evaluated
                          in float64 rather than in exact integers, which
                          reproduces the run's kept counts.  Logarithmic axis,
                          the survival count beside it, the bulk of this
                          histogram fitted by the run's own recipe (median plus
                          left-side scale, :func:`nulls.core_scale`) overlaid,
                          and the diagnostic ``eta`` marked: a frame is kept
                          when ``Z <= eta``.  Dashed and empty on the four
                          channels the selector refused before evaluating a
                          surface

  middle                  the masked-versus-unmasked spectrum: the all-frame
                          mean ``P_all = sum_all P_i / N`` and the retained
                          conditional mean ``P_keep|keep = sum_keep P_i /
                          N_keep`` of the current era, each in decibels over the
                          median positive bin of ``P_all``, against RF offset
                          from the nominal pilot on the receiver's circular
                          axis.  The removed contribution ``P_all -
                          P_keep,contrib``, with ``P_keep,contrib = sum_keep P_i
                          / N`` --- the common denominator, so it is *not* the
                          difference of the two drawn curves --- is formed in
                          linear power and tabulated in the panel, as
                          Section 6.4 requires.  It is neither a calibrated
                          power spectral density nor a quantity in W/Hz.  A
                          channel whose mask keeps no current-era frame reports
                          an unavailable after-mask spectrum, not zero power
  lower                   the era record: the arithmetic mean of the fine
                          statistic ``T`` in each UTC calendar month, over every
                          health-admitted frame of the channel (not only the
                          era), as ``10 log10 T`` against fine-envelope
                          frequency.  Calendar gaps stay blank.  The
                          geometry-predicted anchor (``geometry.grid_residual_hz``
                          wrapped onto the fine axis) is the dashed white line;
                          the measured current-era anchor
                          (``anchor_era.anchor_fine_hz``) is drawn across the
                          era it was measured on; era boundaries are dotted and
                          the current era's opening boundary is solid.  It is a
                          detector-statistic heatmap: the products keep one
                          feed-summed spectrum per frame and nothing within a
                          frame, so no sub-frame spectrogram exists
  containment             the per-frame raw-peak offset distribution of the
                          detected frames (the stored survey flag), taken from
                          the per-frame spectra inside the ``+-15`` kHz census
                          window with the instrumental centre line excluded,
                          against the ``K = 64``, ``128`` and ``256`` capture
                          spans: the evidence behind the disposition column of
                          ``tab:calibration:anchors``
  operating point         the ``eta`` trade curves of
                          ``channels/chNN/operating_points.csv``: surviving
                          residual ``r_sys`` against masked fraction, one thin
                          curve per candidate rank with the diagnostic rank
                          drawn over them, the tolerance ``r_tol`` as a
                          horizontal line, the diagnostic calibration-block
                          point and its evaluation-block replay with
                          block-bootstrap 16--84% intervals.  Empty on the four
                          refused channels, whose file carries no point

No point drawn on any plate is a selection: the selector returned no operating
point on any channel of this run, so every marked point is the least-residual
point of the evaluated calibration surface, declared a diagnostic.

Inputs: the ledger (``ledger/run.json``, ``ledger/channels/chNN_fidXXX.json``),
``channels/chNN/eras.json``, ``channels/chNN/operating_points.csv``, and the
per-channel v5 product named by ``run.json``'s ``products_dir`` and each
channel's ``product``.  A product that cannot be opened costs the plate its
four data layers; the panel says so, the row is dashed, and the fragment's
notes name the channel.

**The table** (``tables/plates.tex``, one row per channel): ``ch``; ``era``
(the current era's months and state); ``frames`` (its timed frames);
``$\\rho$`` and ``$\\eta$`` (the diagnostic point); ``kept`` (the frames that
point keeps on the era); ``removed [\\%]`` (the share of the band-integrated
all-frame power the mask removes); ``months`` (populated months on the
heatmap); ``anchor [Hz]`` (the measured current-era anchor on the fine
envelope); ``marks``.

Numbers are keyed ``appC.plates.<name>.chNN``; band-level values drop the
channel suffix (``appC.plates.channels``, ``appC.plates.count.<name>``).
"""
from __future__ import annotations

import csv
import json
import math
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import matplotlib
matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter

from ... import style
from .. import anchors as anchor_mod
from .. import blocks as block_mod
from .. import eras as era_mod
from .. import nulls as null_mod
from ..products import (FINE_BIN_HZ, FINE_BINS, HEALTH_GATE_SCHEMA, NFFT, PSD_BIN_HZ,
                        SAMPLE_RATE_HZ, Product, fine_hz_of_bin, fine_power_ratio)
from . import core
from .core import DASH, Fragment, Run, booktabs, fmt, fmt_int, tex

NAME = "plates"
LABEL = "fig:archive:atlas"
PLATE_LABEL = "fig:archive:atlas:{channel:d}"
FIGURE = "fig_archive_plate_ch{channel:02d}"
ERAS_JSON = "eras.json"
POINTS_CSV = "operating_points.csv"

DESIGNATED_HALF_WIDTH = 2                  # D = {(f_a + k) mod 256 : |k| <= 2}, selection.DESIGNATED_HALF_WIDTH
WINDOW_HZ = 15_000.0                       # psd.WINDOW_HZ: the census window the peaks are read in
CENTRE_LINE_HALF_WIDTH_HZ = 60.0           # psd.CENTRE_LINE_HALF_WIDTH_HZ: the instrumental line, excluded from peaks
SPANS = (64, 128, 256)                     # psd.SPANS: the candidate capture spans
FULL_SCALE_NATIVE = 128.0                  # complex-int4 negative-full-scale power, 2 * 8^2
PSD_CHUNK = 2048                           # frames per decoded spectrum chunk (psd.DEFAULT_CHUNK)
HIST_BINS = 72
MAX_NOTE_SHARE = 0.32                      # most of a panel belongs to its data, whatever the note asks for
MAX_RANK_CURVES = 24                       # trade curves drawn behind the diagnostic rank


# ------------------------------------------------------------------ small helpers
def _finite(value) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _f(value) -> float:
    return float(value) if _finite(value) else math.nan


def _i(value, default: int = -1) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def month_index_of(label) -> int:
    """``'2024-10'`` -> ``year * 12 + month - 1`` (``blocks.month_index``'s coordinate); -1 when unparsable."""
    text = str(label or "")
    if len(text) != 7 or text[4] != "-":
        return -1
    try:
        return int(text[:4]) * 12 + int(text[5:]) - 1
    except ValueError:
        return -1


def span_half_width_hz(k: int) -> float:
    """``f_s / 2K``: the unambiguous half-span of a K-tap window."""
    return SAMPLE_RATE_HZ / (2.0 * k)


def wrap_fine_hz(offset_hz: float) -> float:
    """A fine-axis offset in Hz onto the centred envelope ``[-L/2, L/2)`` bins."""
    if not _finite(offset_hz):
        return math.nan
    span = FINE_BINS * FINE_BIN_HZ
    return (float(offset_hz) + span / 2.0) % span - span / 2.0


def _list(values) -> str:
    return ", ".join(str(v) for v in values)


def _db(values, reference: float) -> np.ndarray:
    """``10 log10(x / reference)``; NaN where either is not a positive number."""
    x = np.asarray(values, dtype=float)
    out = np.full(x.shape, np.nan)
    if _finite(reference) and reference > 0:
        ok = np.isfinite(x) & (x > 0)
        out[ok] = 10.0 * np.log10(x[ok] / reference)
    return out


# ------------------------------------------------------------------ the run's own records
@dataclass(frozen=True)
class EraRecord:
    """One era of ``channels/chNN/eras.json``: the months it spans and its state."""

    index: int                   # the file's one-based 'era'
    first_month: int
    last_month: int
    state: str

    @property
    def label(self) -> str:
        return f"{block_mod.month_label(self.first_month)}..{block_mod.month_label(self.last_month)}"


def eras_path(run: Run, channel: int) -> Path:
    return Path(run.results_dir) / "channels" / f"ch{channel:02d}" / ERAS_JSON


def points_path(run: Run, channel: int) -> Path:
    return Path(run.results_dir) / "channels" / f"ch{channel:02d}" / POINTS_CSV


def read_eras(path: Path) -> tuple[tuple[EraRecord, ...], int]:
    """``(eras, current_index)`` from an ``eras.json``; ``((), -1)`` when it is absent or unreadable."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return (), -1
    records = []
    for entry in payload.get("eras", ()):
        if not isinstance(entry, dict):
            continue
        first, last = month_index_of(entry.get("first_month")), month_index_of(entry.get("last_month"))
        if first < 0 or last < 0:
            continue
        records.append(EraRecord(_i(entry.get("era")), first, last, str(entry.get("state", "") or "")))
    current = _i(payload.get("current_era"), 0) - 1
    if not 0 <= current < len(records):
        current = len(records) - 1
    return tuple(records), current


@dataclass(frozen=True)
class TradeCurves:
    """The candidate surface of ``operating_points.csv``: one entry per rank."""

    by_rho: dict[int, np.ndarray]        # rho -> (n, 3): masked fraction, r_sys, eta
    rows: int                            # rows the file carried, drawable or not

    @property
    def present(self) -> bool:
        """Whether any rank carries a drawable point (a header-only file carries none)."""
        return bool(self.by_rho)


def read_points(path: Path) -> TradeCurves:
    """The trade curves of one channel; an empty object when the file is absent or carries no point."""
    try:
        with Path(path).open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
    except OSError:
        return TradeCurves({}, 0)
    by_rho: dict[int, list[tuple[float, float, float]]] = {}
    for row in rows:
        rho = _i(row.get("rho"))
        f, r, eta = _f(row.get("masked_fraction")), _f(row.get("r_sys")), _f(row.get("eta"))
        if rho < 0 or not (math.isfinite(f) and math.isfinite(r)):
            continue
        by_rho.setdefault(rho, []).append((f, r, eta))
    ordered = {}
    for rho, values in by_rho.items():
        arr = np.asarray(sorted(values), dtype=float)
        ordered[rho] = arr
    return TradeCurves(ordered, len(rows))


# ------------------------------------------------------------------ the layers
@dataclass
class Plate:
    """Everything one channel's plate draws, and the reason for whatever it cannot."""

    channel: int
    freq_id: int
    product_name: str
    product_path: Path
    present: bool = False
    missing_reason: str = ""
    inputs: list = field(default_factory=list)
    health_schema: str = ""              # the frame-health gate the era mask was taken through
    ledger_health_schema: str = ""       # the gate the run itself applied

    # era
    era_first_month: int = -1
    era_last_month: int = -1
    era_state: str = ""
    era_off: bool = False
    era_label: str = ""
    reference_label: str = ""            # the era the containment panel drew
    reference_is_current: bool = True
    era_frames: float = math.nan         # timed current-era frames (the run's era mask)
    era_frames_untimed: float = math.nan
    ledger_era_frames: float = math.nan
    boundaries: tuple[int, ...] = ()     # first month of every era after the first

    # (a)-(c)
    coarse: np.ndarray = field(default_factory=lambda: np.empty(0))
    level_db: np.ndarray = field(default_factory=lambda: np.empty(0))
    input_power: np.ndarray = field(default_factory=lambda: np.empty(0))
    flag_rate: float = math.nan
    bulk_centre: float = math.nan
    bulk_scale: float = math.nan
    level_median_db: float = math.nan
    input_median: float = math.nan
    rail_frames: float = math.nan

    # (d)
    z: np.ndarray = field(default_factory=lambda: np.empty(0))
    rho: float = math.nan
    eta: float = math.nan
    anchor_bin: float = math.nan
    bulk_size: float = math.nan
    z_bulk_centre: float = math.nan
    z_bulk_scale: float = math.nan
    kept_frames: float = math.nan
    masked_fraction_era: float = math.nan
    ledger_masked_fraction: float = math.nan
    ledger_kept_evaluation: float = math.nan
    no_point_reason: str = ""

    # middle
    rf_offset_hz: np.ndarray = field(default_factory=lambda: np.empty(0))
    all_db: np.ndarray = field(default_factory=lambda: np.empty(0))
    keep_db: np.ndarray = field(default_factory=lambda: np.empty(0))
    spectrum_reference: float = math.nan
    removed_fraction: float = math.nan
    removed_pilot_db: float = math.nan
    keep_pilot_db: float = math.nan
    all_pilot_db: float = math.nan
    after_mask_reason: str = ""

    # lower
    heat_months: np.ndarray = field(default_factory=lambda: np.empty(0, dtype=int))
    heat_db: np.ndarray = field(default_factory=lambda: np.empty((0, 0)))
    fine_hz: np.ndarray = field(default_factory=lambda: np.empty(0))
    predicted_anchor_hz: float = math.nan
    measured_anchor_hz: float = math.nan
    populated_months: float = math.nan
    blank_months: float = math.nan

    # containment
    peak_offsets_hz: np.ndarray = field(default_factory=lambda: np.empty(0))
    in_span: dict = field(default_factory=dict)          # K -> fraction, computed here
    ledger_in_span: dict = field(default_factory=dict)   # K -> fraction, from the ledger
    peak_abs_median_hz: float = math.nan
    disposition: str = ""

    # operating point
    curves: TradeCurves = field(default_factory=lambda: TradeCurves({}, 0))
    r_tol: float = math.nan
    diagnostic_masked_fraction: float = math.nan
    diagnostic_r_sys: float = math.nan
    evaluation_masked_fraction: float = math.nan
    evaluation_masked_q16: float = math.nan
    evaluation_masked_q84: float = math.nan
    evaluation_r_sys: float = math.nan
    evaluation_r_sys_q16: float = math.nan
    evaluation_r_sys_q84: float = math.nan
    claim_status: str = ""
    selection_status: str = ""
    screening_class: str = ""

    @property
    def has_point(self) -> bool:
        return _finite(self.rho) and _finite(self.eta)

    @property
    def health_gate_agrees(self) -> bool:
        """Whether this process applied the same frame-health gate the run did."""
        return bool(self.health_schema) and self.health_schema == (self.ledger_health_schema or HEALTH_GATE_SCHEMA)

    @property
    def has_keep(self) -> bool:
        return self.keep_db.size > 0 and np.isfinite(self.keep_db).any()

    @property
    def era_months(self) -> str:
        if self.era_first_month < 0:
            return ""
        return f"{block_mod.month_label(self.era_first_month)}..{block_mod.month_label(self.era_last_month)}"

    @property
    def era_word(self) -> str:
        state = self.era_state or "state unstated"
        return f"{state} (transmitter off)" if self.era_off else state


def _era_mask(product: Product, months: np.ndarray, first: int, last: int) -> np.ndarray:
    """The run's own era mask: health-admitted frames of the era that carry a recorded time."""
    return product.selected & np.isfinite(product.frame_time) & (months >= first) & (months <= last)


def fine_statistic(product: Product) -> np.ndarray:
    """``T[i, f] = 2 S_0 / (S_1 + S_2)`` for every frame, and the positive-denominator mask."""
    return fine_power_ratio(product.fine_terms_all())


def z_statistic(ratio: np.ndarray, positive: np.ndarray, *, anchor_bin: int, bulk: np.ndarray,
                rho: int) -> np.ndarray:
    """``Z_i(rho) = max_D T / T_(rho)``: the exact keep boundary of the run, in float64.

    ``T_(rho)`` is the ``rho``-th smallest bulk value among the bulk bins whose
    reference denominator is positive (the run ranks those bins alone); a frame
    with no such bin, or with a zero at that rank, is always masked and scores
    ``inf``.  A frame whose designated bins are all zero scores ``0`` and is
    always kept, which is the run's ``boundary = 1`` case.
    """
    designated = list(anchor_mod.designated_set(int(anchor_bin), DESIGNATED_HALF_WIDTH, ratio.shape[1]))
    peak = ratio[:, designated].max(axis=1)
    ranked = np.where(positive[:, bulk], ratio[:, bulk], np.inf)
    ranked.sort(axis=1)
    index = int(rho) - 1
    if not 0 <= index < ranked.shape[1]:
        raise ValueError(f"rank {rho} is outside the bulk of {ranked.shape[1]} bins")
    reference = ranked[:, index]
    usable = np.isfinite(reference) & (reference > 0.0)
    return np.where(usable, peak / np.where(usable, reference, 1.0), np.inf)


def monthly_fine_means(ratio: np.ndarray, months: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """``(months, mean T per bin)`` over the masked frames of each populated month, in calendar order."""
    present = np.unique(months[mask & (months >= 0)])
    if present.size == 0:
        return np.empty(0, dtype=int), np.empty((0, ratio.shape[1]))
    out = np.empty((present.size, ratio.shape[1]))
    for i, month in enumerate(present):
        out[i] = ratio[mask & (months == month)].mean(axis=0)
    return present.astype(int), out


@dataclass(frozen=True)
class SpectrumPass:
    """One pass over the per-frame spectra: two era means and the detected frames' peaks."""

    rf_offset_hz: np.ndarray        # ascending, the receiver's circular axis about the nominal pilot
    all_mean: np.ndarray            # linear, sum over the era divided by the per-bin finite count
    keep_mean: np.ndarray           # linear, sum over the kept frames divided by their own per-bin count
    removed: np.ndarray             # linear, P_all - P_keep,contrib on the common per-bin denominator
    all_frames: int
    keep_frames: int
    peak_offsets_hz: np.ndarray


def spectrum_pass(product: Product, era: np.ndarray, keep: np.ndarray, peaks_on: np.ndarray, *,
                  chunk: int = PSD_CHUNK) -> SpectrumPass:
    """Accumulate ``P_all``, ``P_keep`` and the raw peak offsets in one sweep of ``psd_frame_db_i16``.

    Bin denominators are per-bin finite-code counts, and the removed
    contribution divides both sums by the all-frame count of the same bin, so
    it is ``sum_masked P_i / N`` rather than a difference of means.
    """
    geometry = product.geometry
    rf = (geometry.psd_rf_offset_hz(np.arange(NFFT)) + SAMPLE_RATE_HZ / 2.0) % SAMPLE_RATE_HZ - SAMPLE_RATE_HZ / 2.0
    order = np.argsort(rf, kind="stable")
    in_window = np.abs(rf) <= WINDOW_HZ
    peak_cols = np.flatnonzero(in_window & (np.abs(rf - geometry.centre_line_rf_offset_hz) > CENTRE_LINE_HALF_WIDTH_HZ))
    acc_all, acc_keep = np.zeros(NFFT), np.zeros(NFFT)
    count_all, count_keep = np.zeros(NFFT, dtype=np.int64), np.zeros(NFFT, dtype=np.int64)
    peaks = np.full(int(peaks_on.sum()), np.nan)
    filled = 0
    for rows, power in product.psd_rows(chunk):
        block = era[rows]
        wanted = block | peaks_on[rows]
        if not wanted.any():
            continue
        finite = np.isfinite(power)
        if block.any():
            count_all += finite[block].sum(axis=0)
            kept = keep[rows] & block
            if kept.any():
                count_keep += finite[kept].sum(axis=0)
        np.nan_to_num(power, copy=False, nan=0.0)     # our own decoded copy; zeros drop out of the sums
        if block.any():
            acc_all += power[block].sum(axis=0)
            kept = keep[rows] & block
            if kept.any():
                acc_keep += power[kept].sum(axis=0)
        want_peaks = peaks_on[rows]
        if want_peaks.any() and peak_cols.size:
            sub = power[want_peaks][:, peak_cols]
            any_finite = finite[want_peaks][:, peak_cols].any(axis=1)
            offsets = rf[peak_cols[np.argmax(sub, axis=1)]]
            offsets[~any_finite] = np.nan
            peaks[filled:filled + offsets.size] = offsets
            filled += offsets.size
    all_mean = np.full(NFFT, np.nan)
    keep_mean = np.full(NFFT, np.nan)
    removed = np.full(NFFT, np.nan)
    has_all = count_all > 0
    all_mean[has_all] = acc_all[has_all] / count_all[has_all]
    has_keep = count_keep > 0
    keep_mean[has_keep] = acc_keep[has_keep] / count_keep[has_keep]
    removed[has_all] = (acc_all[has_all] - acc_keep[has_all]) / count_all[has_all]
    return SpectrumPass(rf[order], all_mean[order], keep_mean[order], removed[order],
                        int(era.sum()), int((keep & era).sum()), peaks[:filled])


def _reference_era(records: Sequence[EraRecord], current: int, off: bool) -> tuple[int, bool]:
    """The era the containment panel reads: the previous on era when the current era is off."""
    if off and current - 1 >= 0:
        return current - 1, False
    return current, True


def compute_plate(run: Run, ledger: core.Channel, *, products_dir: Path | str | None = None) -> Plate:
    """One channel's layers: the ledger, its era file and trade curves, and one pass over its product."""
    channel = ledger.channel
    directory = Path(products_dir) if products_dir is not None else Path(str(run.run.get("products_dir", "")))
    plate = Plate(channel=channel, freq_id=ledger.freq_id, product_name=ledger.product,
                  product_path=directory / ledger.product)
    era, null, selection, anchor_era = ledger.era, ledger.null, ledger.selection, ledger.section("anchor_era")
    geometry, containment, screening = ledger.section("geometry"), ledger.containment, ledger.screening

    plate.era_first_month = month_index_of(era.get("current_first_month"))
    plate.era_last_month = month_index_of(era.get("current_last_month"))
    plate.era_state = str(era.get("current_state", "") or "")
    plate.era_off = bool(era.get("off_era_current"))
    plate.era_label = plate.era_months
    plate.ledger_era_frames = _f(era.get("current_frames"))
    plate.level_median_db = _f(era.get("current_level_median_db"))
    plate.flag_rate = _f(screening.get("survey_flag_rate_era"))
    plate.screening_class = str(screening.get("screening_class", "") or "")
    plate.bulk_centre = _f(null.get("coarse_centre"))
    plate.bulk_scale = _f(null.get("coarse_core_sigma"))
    plate.bulk_size = _f(null.get("bulk_size"))
    plate.anchor_bin = _f(selection.get("anchor_bin", null.get("anchor_bin")))
    plate.rho = _f(selection.get("diagnostic_rho"))
    plate.eta = _f(selection.get("diagnostic_eta"))
    plate.ledger_masked_fraction = _f(selection.get("diagnostic_masked_fraction"))
    plate.ledger_kept_evaluation = _f(selection.get("kept_evaluation"))
    plate.claim_status = str(selection.get("claim_status", "") or "")
    plate.selection_status = str(selection.get("status", "") or "")
    plate.r_tol = _f(selection.get("r_tol", ledger.tolerance.get("r_tol_dilation")))
    plate.diagnostic_masked_fraction = _f(selection.get("diagnostic_masked_fraction"))
    plate.diagnostic_r_sys = _f(selection.get("diagnostic_r_sys"))
    plate.evaluation_masked_fraction = _f(selection.get("masked_fraction_evaluation"))
    plate.evaluation_masked_q16 = _f(selection.get("masked_fraction_evaluation_q16"))
    plate.evaluation_masked_q84 = _f(selection.get("masked_fraction_evaluation_q84"))
    plate.evaluation_r_sys = _f(selection.get("r_sys_evaluation"))
    plate.evaluation_r_sys_q16 = _f(selection.get("r_sys_evaluation_q16"))
    plate.evaluation_r_sys_q84 = _f(selection.get("r_sys_evaluation_q84"))
    plate.predicted_anchor_hz = wrap_fine_hz(_f(geometry.get("grid_residual_hz")))
    plate.measured_anchor_hz = wrap_fine_hz(_f(anchor_era.get("anchor_fine_hz")))
    plate.ledger_health_schema = str(ledger.section("product").get("health_schema", "") or "")
    plate.disposition = str(containment.get("disposition", "") or "")
    plate.peak_abs_median_hz = _f(containment.get("peak_abs_median_hz"))
    plate.ledger_in_span = {k: _f(containment.get(f"frames_in_span_{k}")) for k in SPANS}
    if not plate.has_point:
        plate.no_point_reason = str(selection.get("refusal", "") or plate.selection_status or "no diagnostic point")

    plate.curves = read_points(points_path(run, channel))
    if plate.curves.present:
        plate.inputs.append(points_path(run, channel))
    records, current = read_eras(eras_path(run, channel))
    if records:
        plate.inputs.append(eras_path(run, channel))
        plate.boundaries = tuple(r.first_month for r in records[1:])
        reference, is_current = _reference_era(records, current, plate.era_off)
        plate.reference_is_current = is_current
        plate.reference_label = records[reference].label if 0 <= reference < len(records) else ""
    else:
        plate.reference_is_current = not plate.era_off
        plate.reference_label = plate.era_months if plate.reference_is_current else ""

    if not plate.product_path.is_file():
        plate.missing_reason = f"product {ledger.product} not found under {directory}"
        return plate
    try:
        product = Product(plate.product_path)
    except (OSError, ValueError) as exc:
        plate.missing_reason = f"product {ledger.product} unreadable ({type(exc).__name__}: {exc})"
        return plate
    with product:
        _fill_from_product(plate, product, records, current)
    plate.present = True
    plate.inputs.append(plate.product_path)
    return plate


def _fill_from_product(plate: Plate, product: Product, records: Sequence[EraRecord], current: int) -> None:
    """The four measured layers of one plate, from one open product."""
    months = era_mod.frame_months(product)
    plate.health_schema = product.health.schema
    selected = product.selected
    era = _era_mask(product, months, plate.era_first_month, plate.era_last_month)
    plate.era_frames = float(era.sum())
    plate.era_frames_untimed = float((selected & (months >= plate.era_first_month)
                                      & (months <= plate.era_last_month) & ~np.isfinite(product.frame_time)).sum())
    reference_index, _ = _reference_era(records, current, plate.era_off)
    if records and 0 <= reference_index < len(records):
        record = records[reference_index]
        reference = _era_mask(product, months, record.first_month, record.last_month)
    else:
        reference = era

    plate.coarse = product.statistic[era]
    plate.coarse = plate.coarse[np.isfinite(plate.coarse)]
    plate.level_db = product.level_db[era]
    plate.level_db = plate.level_db[np.isfinite(plate.level_db)]
    power = product.frame_column("baseband_power_linear").astype(float)[era]
    plate.input_power = power[np.isfinite(power)]
    plate.input_median = float(np.median(plate.input_power)) if plate.input_power.size else math.nan
    plate.rail_frames = float((plate.input_power >= FULL_SCALE_NATIVE).sum()) if plate.input_power.size else math.nan

    terms = product.fine_terms_all()
    ratio = fine_power_ratio(terms)
    positive = (terms[:, 1].astype(np.float64) + terms[:, 2].astype(np.float64)) > 0.0
    del terms
    plate.fine_hz = fine_hz_of_bin(np.arange(ratio.shape[1]))
    plate.heat_months, heat = monthly_fine_means(ratio, months, selected)
    plate.heat_db = _db(heat, 1.0)
    plate.populated_months = float(plate.heat_months.size)
    if plate.heat_months.size:
        plate.blank_months = float(plate.heat_months[-1] - plate.heat_months[0] + 1 - plate.heat_months.size)

    keep = np.zeros(product.n_frames, dtype=bool)
    if plate.has_point and _finite(plate.anchor_bin):
        bulk = anchor_mod.bulk_mask(int(plate.anchor_bin), pad_factor=product.fine_pad_factor,
                                    guard_fine_bins=product.fine_guard_bins,
                                    census_excluded_bins=product.fine_census_excluded_bins,
                                    designated_half_width=DESIGNATED_HALF_WIDTH, fine_bins=ratio.shape[1])
        z = z_statistic(ratio, positive, anchor_bin=int(plate.anchor_bin), bulk=bulk, rho=int(plate.rho))
        keep = z <= plate.eta
        plate.z = z[era]
        plate.kept_frames = float((keep & era).sum())
        plate.masked_fraction_era = 1.0 - plate.kept_frames / plate.era_frames if plate.era_frames else math.nan
        inside = plate.z[np.isfinite(plate.z) & (plate.z > 0)]
        if inside.size:
            centre = float(np.median(inside))
            plate.z_bulk_centre = centre
            plate.z_bulk_scale = float(null_mod.core_scale(inside, centre)[0])
    del ratio, positive

    detected = product.rejected & reference
    result = spectrum_pass(product, era, keep, detected)
    reference_power = result.all_mean[np.isfinite(result.all_mean) & (result.all_mean > 0)]
    plate.spectrum_reference = float(np.median(reference_power)) if reference_power.size else math.nan
    plate.rf_offset_hz = result.rf_offset_hz
    plate.all_db = _db(result.all_mean, plate.spectrum_reference)
    plate.keep_db = _db(result.keep_mean, plate.spectrum_reference)
    total_all = float(np.nansum(result.all_mean))
    total_removed = float(np.nansum(result.removed))
    plate.removed_fraction = total_removed / total_all if total_all > 0 else math.nan
    pilot = int(np.argmin(np.abs(result.rf_offset_hz)))
    plate.all_pilot_db = float(plate.all_db[pilot])
    plate.keep_pilot_db = float(plate.keep_db[pilot])
    plate.removed_pilot_db = float(_db(result.removed[pilot: pilot + 1], plate.spectrum_reference)[0])
    if result.keep_frames == 0:
        plate.after_mask_reason = ("no current-era frame survives the mask"
                                   if plate.has_point else "no diagnostic point to apply")

    peaks = result.peak_offsets_hz
    plate.peak_offsets_hz = peaks[np.isfinite(peaks)]
    if plate.peak_offsets_hz.size:
        plate.in_span = {k: float((np.abs(plate.peak_offsets_hz) <= span_half_width_hz(k)).mean()) for k in SPANS}


def plates(run: Run, *, products_dir: Path | str | None = None, channels: Sequence[int] | None = None) -> list[Plate]:
    """Every channel's layers, computed once per run per process (see the module docstring)."""
    key = str(Path(run.results_dir).resolve())
    cache = _CACHE.setdefault(key, {})
    out = []
    for ledger in run.channels:
        if channels is not None and ledger.channel not in channels:
            continue
        if ledger.channel not in cache:
            cache[ledger.channel] = compute_plate(run, ledger, products_dir=products_dir)
        out.append(cache[ledger.channel])
    return out


_CACHE: dict[str, dict[int, Plate]] = {}


def clear_cache() -> None:
    """Forget every computed plate (the products are re-read on the next call)."""
    _CACHE.clear()


# ------------------------------------------------------------------ the figure
HIST_FILL = dict(fill=True, facecolor=style.LIGHT_BLUE, edgecolor=style.MEASURED, lw=0.45)
TICKS = dict(labelsize=5.2, length=1.9, width=0.5, pad=1.3)
NOTE_PT = 4.9
AXIS_PT = 5.6
TITLE_PT = 6.2


def _frame(ax, *, title: str = "", subtitle: str = "", title_pad: float | None = None) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(**TICKS)
    ax.tick_params(which="minor", length=1.0, width=0.4)
    if title:
        ax.set_title(title, fontsize=TITLE_PT, color=style.INK,
                     pad=(7.5 if subtitle else 2.4) if title_pad is None else title_pad)
    if subtitle:
        ax.text(0.5, 1.012, subtitle, transform=ax.transAxes, ha="center", va="bottom",
                fontsize=NOTE_PT, color=style.MUTED)


def reserve_headroom(ax, top_data: float, note_lines: int, *, floor: float = 0.7, pad: float = 0.02) -> None:
    """Set a logarithmic y limit that leaves the note's own lines clear of the data.

    The note is written in axes coordinates from the top edge down, so the room
    it needs is a fraction of the panel's height, not a fixed number of
    decades: a 0.9-inch panel spending five decades hides a three-line note
    behind the tallest bar unless the limit is raised to make room for it.
    """
    height = ax.get_position().height * ax.figure.get_size_inches()[1]
    needed = (note_lines * NOTE_PT * 1.34 / 72.0) + pad if note_lines else pad
    share = min(MAX_NOTE_SHARE, needed / height) if height > 0 else 0.25
    data = math.log10(max(top_data, floor * 10.0) / floor)
    ax.set_ylim(floor, floor * 10.0 ** (data / (1.0 - share)))


def _note(ax, text: str, *, y: float = 0.982, colour: str = style.MUTED, x: float = 0.035, ha: str = "left") -> None:
    ax.text(x, y, text, transform=ax.transAxes, ha=ha, va="top", fontsize=NOTE_PT, color=colour, linespacing=1.3)


def _empty(ax, reason: str, *, width: int = 34) -> None:
    ax.set_axis_off()
    ax.text(0.5, 0.5, "\n".join(textwrap.wrap(reason, width)), transform=ax.transAxes, ha="center", va="center",
            fontsize=NOTE_PT + 0.3, color=style.FAILURE, linespacing=1.35)


def log_axis(ax, axis: str = "x") -> None:
    """Decade ticks, and plain labels on the 2/3/5 minors when the span is under two decades.

    Matplotlib labels every minor tick of a narrow logarithmic axis in
    scientific notation, which on a 1.3-inch panel writes one label over
    another; these panels span anything from a third of a decade to five.
    """
    target = ax.xaxis if axis == "x" else ax.yaxis
    lo, hi = (ax.get_xlim() if axis == "x" else ax.get_ylim())
    decades = math.log10(hi / lo) if lo > 0 and hi > lo else 0.0
    target.set_major_locator(LogLocator(base=10.0, numticks=8))
    target.set_minor_locator(LogLocator(base=10.0, subs=(2.0, 3.0, 5.0), numticks=24))
    plain = FuncFormatter(lambda value, _pos: f"{value:g}")
    if decades <= 2.6:
        target.set_major_formatter(plain)
        target.set_minor_formatter(plain if decades <= 1.6 else NullFormatter())
    else:
        target.set_minor_formatter(NullFormatter())


def histogram_edges(values: np.ndarray, *, log: bool, bins: int = HIST_BINS) -> np.ndarray:
    """Bin edges spanning the finite values, geometric on a logarithmic axis."""
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return np.linspace(0.0, 1.0, bins + 1)
    lo, hi = float(finite.min()), float(finite.max())
    if log:
        lo = max(lo, np.nextafter(0.0, 1.0))
        hi = max(hi, lo * (1.0 + 1e-9))
        return np.geomspace(lo, hi, bins + 1)
    if hi <= lo:
        hi = lo + 1.0
    return np.linspace(lo, hi, bins + 1)


def survival(values: np.ndarray, *, points: int = 320) -> tuple[np.ndarray, np.ndarray]:
    """``(x, N(> x))``: the tail complementary distribution as a count, thinned to ``points``."""
    finite = np.sort(values[np.isfinite(values)])
    n = finite.size
    if n == 0:
        return np.empty(0), np.empty(0)
    index = np.unique(np.linspace(0, n - 1, min(points, n)).astype(int))
    return finite[index], (n - index).astype(float)


def containment_edges(*, bins: int = HIST_BINS, low: float | None = None, high: float = WINDOW_HZ) -> np.ndarray:
    """Geometric ``|offset|`` edges that are never narrower than one stored spectrum bin.

    Peak offsets live on the ``23.84`` Hz grid of the stored spectra, so a
    geometric bin finer than that grid draws a comb of empty bins rather than a
    distribution; each candidate edge is kept only once it clears its
    predecessor by a whole bin.
    """
    lowest = PSD_BIN_HZ / 2.0 if low is None else float(low)
    edges = [lowest]
    for candidate in np.geomspace(lowest, high, bins + 1)[1:]:
        if candidate - edges[-1] >= PSD_BIN_HZ:
            edges.append(float(candidate))
    if len(edges) < 2 or edges[-1] < high:
        edges.append(float(high))
    return np.asarray(edges)


def _histogram_panel(ax, values: np.ndarray, *, log: bool, title: str, subtitle: str, xlabel: str,
                     tail: bool = False, note: Sequence[str] = ()) -> None:
    _frame(ax, title=title, subtitle=subtitle)
    edges = histogram_edges(values, log=log)
    counts, _ = np.histogram(values[np.isfinite(values)], bins=edges)
    ax.stairs(counts, edges, **HIST_FILL)
    if tail:
        x, n_above = survival(values)
        if x.size:
            ax.plot(x, n_above, color=style.PENDING, ls=(0, (2.4, 1.5)), lw=0.7, zorder=5)
    if log:
        ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(float(edges[0]), float(edges[-1]))
    top = float(counts.max()) if counts.size else 1.0
    if tail:
        top = max(top, float(np.isfinite(values).sum()))          # the survival curve starts at N
    reserve_headroom(ax, top, len(note))
    ax.set_xlabel(xlabel, fontsize=AXIS_PT, labelpad=1.4)
    ax.grid(True, axis="y", color=style.GRID, lw=0.3)
    ax.set_axisbelow(True)
    if log:
        log_axis(ax)
    if note:
        _note(ax, "\n".join(note))


def _bulk_overlay(ax, centre: float, scale: float) -> None:
    """The fitted null bulk: its median, and the band one left-side scale wide about it."""
    if not _finite(centre):
        return
    if _finite(scale) and scale > 0:
        ax.axvspan(centre - scale, centre + scale, facecolor=style.LIGHT_ORANGE, edgecolor="none", zorder=1)
    ax.axvline(centre, color=style.MODEL, lw=0.8, zorder=6)


def panel_coarse(ax, plate: Plate) -> None:
    """(a) the current era's coarse ``F/mu_0`` histogram, its tail, and the priced null bulk."""
    if not plate.coarse.size:
        _frame(ax, title=r"(a) coarse $F/\mu_0$")
        _empty(ax, plate.missing_reason or "no current-era frame")
        return
    lines = [rf"$N = {fmt_int(plate.coarse.size)}$"]
    if _finite(plate.bulk_centre):
        lines.append(rf"bulk ${fmt(plate.bulk_centre, 4, sig=True)} \pm {fmt(plate.bulk_scale, 3, sig=True)}$")
    if _finite(plate.flag_rate):
        lines.append(rf"flag rate ${fmt(plate.flag_rate, 3)}$")
    _histogram_panel(ax, plate.coarse, log=True, title=r"(a) coarse $F/\mu_0$",
                     subtitle="current era, log counts", xlabel=r"$F/\mu_0$", tail=True, note=lines)
    _bulk_overlay(ax, plate.bulk_centre, plate.bulk_scale)
    ax.axvline(1.0, color=style.MUTED, ls=(0, (1, 1.4)), lw=0.7, zorder=4)
    ax.set_ylabel("frames", fontsize=AXIS_PT, labelpad=1.6)


def panel_level(ax, plate: Plate) -> None:
    """(b) the same statistic in the normalized-decibel coordinate."""
    if not plate.level_db.size:
        _frame(ax, title="(b) normalized level")
        _empty(ax, plate.missing_reason or "no current-era frame")
        return
    note = [rf"era median ${fmt(plate.level_median_db, 2)}$ dB"] if _finite(plate.level_median_db) else []
    _histogram_panel(ax, plate.level_db, log=False, title="(b) normalized level",
                     subtitle=r"$10\log_{10}(F/\mu_0)$", xlabel="level [dB]", note=note)
    ax.axvline(0.0, color=style.MUTED, ls=(0, (1, 1.4)), lw=0.7, zorder=4)
    if _finite(plate.level_median_db):
        ax.axvline(plate.level_median_db, color=style.MODEL, lw=0.8, zorder=5)


def panel_input(ax, plate: Plate) -> None:
    """(c) the decoded native complex-int4 mean input power, and the full-scale rail."""
    if not plate.input_power.size:
        _frame(ax, title="(c) input power")
        _empty(ax, plate.missing_reason or "no current-era frame")
        return
    _histogram_panel(ax, plate.input_power, log=True, title="(c) input power",
                     subtitle=r"native complex-\texttt{int4}" if matplotlib.rcParams["text.usetex"]
                     else "native complex-int4", xlabel="mean power [native units]",
                     note=[rf"median ${fmt(plate.input_median, 2)}$",
                           rf"rail ${fmt(FULL_SCALE_NATIVE, 0)}$: ${fmt_int(plate.rail_frames)}$ frames"])
    ax.axvline(FULL_SCALE_NATIVE, color=style.FAILURE, ls=(0, (2.4, 1.5)), lw=0.7, zorder=5)


def panel_fine(ax, plate: Plate) -> None:
    """(d) the fine designated-window statistic at the diagnostic rank, with ``eta`` marked."""
    title = r"(d) fine $Z(\rho)$"
    if not plate.z.size:
        _frame(ax, title=title)
        _empty(ax, plate.missing_reason or plate.no_point_reason or "no diagnostic point")
        return
    lines = [rf"$\eta = {fmt(plate.eta, 4, sig=True)}$",
             rf"kept ${fmt_int(plate.kept_frames)}$ of ${fmt_int(plate.era_frames)}$"]
    if _finite(plate.masked_fraction_era):
        lines.append(rf"masked ${fmt(plate.masked_fraction_era, 4)}$")
    _histogram_panel(ax, plate.z, log=True, title=title,
                     subtitle=rf"$\rho = {fmt_int(plate.rho)}$, keep $Z \leq \eta$", xlabel=r"$Z(\rho)$",
                     tail=True, note=lines)
    _bulk_overlay(ax, plate.z_bulk_centre, plate.z_bulk_scale)
    if _finite(plate.eta):
        ax.axvline(plate.eta, color=style.FAILURE, lw=0.9, zorder=7)


def panel_spectra(ax, plate: Plate) -> None:
    """The middle panel: the all-frame mean and the retained conditional mean, removed contribution tabulated."""
    _frame(ax, title="Current-era mean spectra before and after the diagnostic mask")
    if not plate.rf_offset_hz.size:
        _empty(ax, plate.missing_reason or "no per-frame spectra")
        return
    khz = plate.rf_offset_hz / 1000.0
    ax.axvline(0.0, color=style.MODEL, ls=(0, (3.5, 2.2)), lw=0.8, zorder=4)
    ax.plot(khz, plate.all_db, color=style.INK, lw=0.55, zorder=5, label=r"$\bar P_{\rm all}$ (all era frames)")
    if plate.has_keep:
        ax.plot(khz, plate.keep_db, color=style.MEASURED, lw=0.55, zorder=6,
                label=r"$\bar P_{\rm keep|keep}$ (frames the point keeps)")
    ax.set_xlim(float(khz.min()), float(khz.max()))
    ax.set_xlabel("RF offset from the nominal pilot [kHz]", fontsize=AXIS_PT, labelpad=1.4)
    ax.set_ylabel("dB over the all-frame median", fontsize=AXIS_PT, labelpad=1.6)
    ax.grid(True, axis="both", color=style.GRID, lw=0.3)
    ax.set_axisbelow(True)
    low, high = ax.get_ylim()
    ax.set_ylim(low, low + (high - low) / 0.70)         # the legend and the tabulated removal live above the data
    handles, labels = ax.get_legend_handles_labels()
    handles.append(Line2D([0], [0], color=style.MODEL, ls=(0, (3.5, 2.2)), lw=0.8))
    labels.append("nominal pilot")
    ax.legend(handles, labels, loc="upper left", fontsize=NOTE_PT, handlelength=1.9, labelspacing=0.32,
              borderaxespad=0.25, frameon=False)
    lines = [r"removed $\bar P_{\rm all} - \bar P_{\rm keep,contrib}$ (common $N$):"]
    if plate.has_keep:
        lines.append(rf"${fmt(100.0 * plate.removed_fraction, 3)}\%$ of the band power, "
                     rf"${fmt(plate.removed_pilot_db, 1)}$ dB at the pilot bin")
        lines.append(rf"pilot bin: all ${fmt(plate.all_pilot_db, 1)}$ dB, kept ${fmt(plate.keep_pilot_db, 1)}$ dB")
    else:
        lines.append(f"after-mask spectrum unavailable: {plate.after_mask_reason or 'no kept frame'}")
    _note(ax, "\n".join(lines), x=0.985, ha="right")


def panel_era(ax, plate: Plate, fig) -> None:
    """The lower panel: the monthly mean fine statistic against UTC, with the era boundary marked."""
    _frame(ax, title=r"Monthly mean fine statistic $10\log_{10}T$: a detector-statistic heatmap, not a spectrogram",
           title_pad=11.0)
    if not plate.heat_months.size:
        _empty(ax, plate.missing_reason or "no month carries a health-admitted frame")
        return
    order = np.argsort(plate.fine_hz)
    fine = plate.fine_hz[order]
    first, last = int(plate.heat_months[0]), int(plate.heat_months[-1])
    grid = np.full((fine.size, last - first + 1), np.nan)
    grid[:, plate.heat_months - first] = plate.heat_db[:, order].T
    finite = grid[np.isfinite(grid)]
    lo, hi = (float(np.percentile(finite, 1)), float(np.percentile(finite, 99.5))) if finite.size else (0.0, 1.0)
    cmap = matplotlib.colormaps["viridis"].with_extremes(bad=style.PAPER)
    step = fine[1] - fine[0] if fine.size > 1 else FINE_BIN_HZ
    im = ax.imshow(np.ma.masked_invalid(grid), origin="lower", aspect="auto", cmap=cmap, vmin=lo, vmax=max(hi, lo + 1e-6),
                   extent=(first - 0.5, last + 0.5, fine[0] - step / 2, fine[-1] + step / 2), interpolation="nearest")
    if _finite(plate.predicted_anchor_hz):
        ax.axhline(plate.predicted_anchor_hz, color="white", ls=(0, (3.2, 2.0)), lw=0.8, zorder=4)
    if _finite(plate.measured_anchor_hz) and plate.era_first_month >= 0:
        ax.plot([max(first - 0.5, plate.era_first_month - 0.5), last + 0.5],
                [plate.measured_anchor_hz] * 2, color=style.PURPLE, lw=1.0, zorder=5)
    for boundary in plate.boundaries:
        if first <= boundary <= last + 1:
            ax.axvline(boundary - 0.5, color="white", ls=(0, (1, 1.6)), lw=0.55, zorder=4)
    if plate.era_first_month > first:
        ax.axvline(plate.era_first_month - 0.5, color=style.PURPLE, lw=1.0, zorder=6)
    ticks = np.unique(np.linspace(first, last, min(7, last - first + 1)).astype(int))
    ax.set_xticks(ticks)
    ax.set_xticklabels([block_mod.month_label(int(t)) for t in ticks], rotation=22, ha="right",
                       rotation_mode="anchor")
    ax.set_xlabel("UTC calendar month (gaps retained)", fontsize=AXIS_PT, labelpad=0.8)
    ax.set_ylabel("fine-envelope frequency [Hz]", fontsize=AXIS_PT, labelpad=1.6)
    ax.tick_params(**TICKS)
    bar = fig.colorbar(im, ax=ax, pad=0.008, fraction=0.021, aspect=13)
    bar.ax.tick_params(labelsize=4.8, length=1.5, width=0.4, pad=1.0)
    bar.outline.set_linewidth(0.5)
    bar.set_label(r"$10\log_{10}T$", fontsize=AXIS_PT - 0.4, labelpad=1.2)
    ax.legend(handles=[Line2D([0], [0], color=style.MUTED, ls=(0, (3.2, 2.0)), lw=0.9),
                       Line2D([0], [0], color=style.PURPLE, lw=1.0)],
              labels=["geometry-predicted anchor (drawn white on the map)",
                      "measured current-era anchor, and the era boundary"],
              loc="lower left", bbox_to_anchor=(0.0, 1.004), ncol=2, fontsize=NOTE_PT, handlelength=1.8,
              labelspacing=0.2, columnspacing=1.4, borderaxespad=0.0, frameon=False)


def panel_containment(ax, plate: Plate) -> None:
    """The offset-containment panel: per-frame raw peak offsets against the candidate spans."""
    _frame(ax, title="Offset containment", subtitle="detected frames, per-frame peak")
    if not plate.peak_offsets_hz.size:
        _empty(ax, plate.missing_reason or "no detected frame carries a spectrum")
        return
    lowest = PSD_BIN_HZ / 2.0
    magnitude = np.clip(np.abs(plate.peak_offsets_hz), lowest, WINDOW_HZ)
    edges = containment_edges()
    counts, _ = np.histogram(magnitude, bins=edges)
    ax.stairs(counts, edges, **HIST_FILL)
    for k, colour in zip(SPANS, (style.CONDITIONAL, style.MODEL, style.FAILURE)):
        ax.axvline(span_half_width_hz(k), color=colour, ls=(0, (2.6, 1.6)), lw=0.75, zorder=5,
                   label=rf"$K = {k}$: ${fmt(plate.in_span.get(k, math.nan), 3)}$")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(lowest, WINDOW_HZ)
    log_axis(ax)
    reserve_headroom(ax, float(counts.max()) if counts.size else 1.0, 4)   # the legend's title and three spans
    ax.set_xlabel("$|$peak offset$|$ from the nominal pilot [Hz]", fontsize=AXIS_PT, labelpad=1.4)
    ax.set_ylabel("frames", fontsize=AXIS_PT, labelpad=1.6)
    ax.grid(True, axis="y", color=style.GRID, lw=0.3)
    ax.set_axisbelow(True)
    ax.legend(loc="upper left", fontsize=NOTE_PT, handlelength=1.6, labelspacing=0.28, borderaxespad=0.25,
              frameon=False, title="in-span fraction", title_fontsize=NOTE_PT)
    era = plate.reference_label if plate.reference_is_current else f"previous on era {plate.reference_label}"
    _note(ax, f"{era}\nmedian $|$offset$|$ ${fmt(plate.peak_abs_median_hz, 1)}$ Hz", x=0.985, ha="right")


def panel_operating(ax, plate: Plate) -> None:
    """The operating-point panel: the rank trade curves, the tolerance, and the two marked points."""
    _frame(ax, title="Operating-point trade", subtitle=r"surviving residual against masked fraction")
    if not plate.curves.present:
        _empty(ax, plate.no_point_reason or "no calibration surface was evaluated")
        return
    ranks = sorted(plate.curves.by_rho)
    step = max(1, len(ranks) // MAX_RANK_CURVES)
    for rho in ranks[::step]:
        arc = plate.curves.by_rho[rho]
        ax.plot(arc[:, 0], arc[:, 1], color=style.CONDITIONAL, lw=0.35, alpha=0.55, zorder=2)
    if _finite(plate.rho) and int(plate.rho) in plate.curves.by_rho:
        arc = plate.curves.by_rho[int(plate.rho)]
        ax.plot(arc[:, 0], arc[:, 1], color=style.MEASURED, lw=0.9, zorder=4,
                label=rf"$\rho = {fmt_int(plate.rho)}$")
    if _finite(plate.r_tol) and plate.r_tol > 0:
        ax.axhline(plate.r_tol, color=style.FAILURE, ls=(0, (3.0, 2.0)), lw=0.85, zorder=5,
                   label=rf"$r_{{\rm tol}} = {fmt(plate.r_tol, 4)}$")
    if _finite(plate.diagnostic_r_sys):
        ax.plot([plate.diagnostic_masked_fraction], [plate.diagnostic_r_sys], marker="o", ms=3.4, ls="none",
                mfc=style.MODEL, mec=style.MODEL, zorder=7, label="diagnostic, calibration")
    if _finite(plate.evaluation_r_sys):
        ax.errorbar([plate.evaluation_masked_fraction], [plate.evaluation_r_sys],
                    xerr=[[max(0.0, plate.evaluation_masked_fraction - plate.evaluation_masked_q16)],
                          [max(0.0, plate.evaluation_masked_q84 - plate.evaluation_masked_fraction)]],
                    yerr=[[max(0.0, plate.evaluation_r_sys - plate.evaluation_r_sys_q16)],
                          [max(0.0, plate.evaluation_r_sys_q84 - plate.evaluation_r_sys)]],
                    fmt="s", ms=3.0, mfc=style.PAPER, mec=style.MEASURED, ecolor=style.MEASURED, elinewidth=0.7,
                    capsize=1.4, capthick=0.7, zorder=8, label="replay, evaluation")
    ax.set_yscale("log")
    ax.set_xlim(-0.03, 1.03)
    ax.set_xlabel("masked fraction $f$", fontsize=AXIS_PT, labelpad=1.4)
    ax.set_ylabel(r"$r_{\rm sys}$", fontsize=AXIS_PT, labelpad=1.6)
    ax.grid(True, axis="both", color=style.GRID, lw=0.3)
    ax.set_axisbelow(True)
    ax.legend(loc="center left", fontsize=NOTE_PT, handlelength=1.6, labelspacing=0.28, borderaxespad=0.25,
              frameon=False, ncol=1)


def plate_title(plate: Plate) -> str:
    """The plate's head: the channel, its era, and the point every layer is evaluated at."""
    head = rf"\textbf{{Channel {plate.channel}}} (\texttt{{freq\_id}} {plate.freq_id})" \
        if matplotlib.rcParams["text.usetex"] else f"Channel {plate.channel} (freq_id {plate.freq_id})"
    era = f"current era {plate.era_months} ({plate.era_word})" if plate.era_months else "no current era"
    return f"{head}: {era}"


def plate_subtitle(plate: Plate) -> tuple[str, str]:
    """The two head lines: the frames every layer runs on, and the point they are evaluated at."""
    first = rf"${fmt_int(plate.era_frames)}$ timed current-era frames"
    if _finite(plate.era_frames_untimed) and plate.era_frames_untimed > 0:
        first += rf"; ${fmt_int(plate.era_frames_untimed)}$ without a recorded time excluded"
    if plate.present and not plate.health_gate_agrees:
        first += rf"; frame-health gate {tex(plate.health_schema)}, not the run's"
    if plate.has_point:
        second = (rf"diagnostic point $\rho = {fmt_int(plate.rho)}$, $\eta = {fmt(plate.eta, 4, sig=True)}$: "
                  "the least-residual point of the calibration surface, a diagnostic and not an operating point")
    else:
        second = "the selector refused before evaluating a surface: no point, no after-mask spectrum, no trade curve"
    return first, second


def figure_plate(plate: Plate):
    """One channel's plate: four histograms, the spectra, the era heatmap, containment and the trade."""
    fig = plt.figure(figsize=(style.TEXT_WIDTH, 7.0))
    gs = fig.add_gridspec(4, 4, height_ratios=(1.0, 1.04, 1.34, 1.04), left=0.082, right=0.975,
                          top=0.900, bottom=0.052, wspace=0.46, hspace=0.66)
    panel_coarse(fig.add_subplot(gs[0, 0]), plate)
    panel_level(fig.add_subplot(gs[0, 1]), plate)
    panel_input(fig.add_subplot(gs[0, 2]), plate)
    panel_fine(fig.add_subplot(gs[0, 3]), plate)
    panel_spectra(fig.add_subplot(gs[1, :]), plate)
    panel_era(fig.add_subplot(gs[2, :]), plate, fig)
    panel_containment(fig.add_subplot(gs[3, 0:2]), plate)
    panel_operating(fig.add_subplot(gs[3, 2:4]), plate)
    fig.suptitle(plate_title(plate), fontsize=8.4, y=0.988)
    first, second = plate_subtitle(plate)
    fig.text(0.5, 0.960, first, ha="center", va="bottom", fontsize=5.5, color=style.MUTED)
    fig.text(0.5, 0.941, second, ha="center", va="bottom", fontsize=5.5, color=style.MUTED)
    if not plate.present:
        fig.text(0.5, 0.922, plate.missing_reason, ha="center", va="bottom", fontsize=5.5, color=style.FAILURE)
    return fig


def _save(fig, stem: Path, title: str) -> list[Path]:
    stem.parent.mkdir(parents=True, exist_ok=True)
    png = stem.with_suffix(".png")
    fig.savefig(png, format="png", dpi=200)
    with style.stable_pdf_subset_tags():
        pdf = style.save(fig, stem.with_suffix(".pdf"), title=title)
    return [pdf, png]


def render(run: Run, out_dir: Path | str, *, products_dir: Path | str | None = None,
           channels: Sequence[int] | None = None) -> list[Path]:
    """One plate per channel (PDF and PNG) under ``out_dir``; the paths in channel order."""
    out = Path(out_dir)
    paths: list[Path] = []
    for plate in plates(run, products_dir=products_dir, channels=channels):
        title = f"Channel {plate.channel} (freq_id {plate.freq_id}) archive diagnostic plate"
        paths.extend(_save(figure_plate(plate), out / FIGURE.format(channel=plate.channel), title))
    return paths


# ------------------------------------------------------------------ the fragment
def _marks(plate: Plate) -> str:
    out = []
    if not plate.present:
        out.append(tex(plate.missing_reason or "no product"))
    if plate.era_off:
        era = plate.reference_label or "unknown"
        out.append(f"current era off; containment on the previous on era {tex(era)}")
    if plate.present and not plate.has_point:
        out.append("selector refused: no surface")
    if plate.present and plate.has_point and not plate.has_keep:
        out.append("no after-mask spectrum")
    if _finite(plate.era_frames_untimed) and plate.era_frames_untimed > 0:
        out.append(rf"${fmt_int(plate.era_frames_untimed)}$ frames without a time excluded")
    if plate.present and not plate.curves.present:
        out.append("no trade curves")
    if plate.present and not plate.health_gate_agrees:
        out.append(f"frame-health gate {tex(plate.health_schema)}")
    return "; ".join(out) if out else DASH


def _math(text: str) -> str:
    return text if text == DASH else f"${text}$"


def counts(rows: Sequence[Plate]) -> dict[str, int]:
    """Plates by what they could draw: the layers present, absent, and refused."""
    return {"with_point": sum(1 for p in rows if p.has_point),
            "refused": sum(1 for p in rows if p.present and not p.has_point),
            "off_era": sum(1 for p in rows if p.era_off),
            "no_after_mask": sum(1 for p in rows if p.present and p.has_point and not p.has_keep),
            "no_product": sum(1 for p in rows if not p.present),
            "no_curves": sum(1 for p in rows if p.present and not p.curves.present),
            "other_health_gate": sum(1 for p in rows if p.present and not p.health_gate_agrees)}


def build(run: Run, *, products_dir: Path | str | None = None) -> Fragment:
    """The table behind the plates, with every value a plate prints keyed."""
    rows = plates(run, products_dir=products_dir)
    frag = Fragment(NAME, LABEL, "")
    inputs = list(run.inputs())
    for plate in rows:
        inputs.extend(plate.inputs)
    frag.inputs = inputs
    header = ["ch", "era", "frames", r"$\rho$", r"$\eta$", "kept", r"removed [\%]", "months", "anchor [Hz]", "marks"]
    body = []
    pfx = "appC.plates"
    missing, refused, off, no_keep, no_curves = [], [], [], [], []
    for plate in rows:
        ch = plate.channel
        row = {"channel": ch}

        def add(name: str, value, *, column: str, precision: int | None = None, kind: str = "float",
                status: str = "measured", renderings: Sequence[str] = (), _plate=plate, _row=row) -> None:
            frag.add(f"{pfx}.{name}.ch{_plate.channel}", value, precision=precision, kind=kind, status=status,
                     renderings=tuple(renderings), row=_row, column=column)

        if not plate.present:
            missing.append(ch)
        if plate.era_off:
            off.append(ch)
        if plate.present and not plate.has_point:
            refused.append(ch)
        if plate.present and plate.has_point and not plate.has_keep:
            no_keep.append(ch)
        if plate.present and not plate.curves.present:
            no_curves.append(ch)

        add("era", plate.era_months or None, column="era", kind="text",
            status="measured" if plate.era_months else "pending",
            renderings=(plate.era_months.replace("..", "--"),) if plate.era_months else ())
        add("era_state", plate.era_state or None, column="era", kind="text",
            status="measured" if plate.era_state else "pending",
            renderings=(plate.era_word,) if plate.era_state else ())
        if plate.present:
            add("era_frames", plate.era_frames, column="frames", kind="int")
            add("era_frames_untimed", plate.era_frames_untimed, column="marks", kind="int")
            add("bulk_centre", plate.bulk_centre, column="panel (a)", precision=4)
            add("bulk_scale", plate.bulk_scale, column="panel (a)", precision=4)
            add("flag_rate", plate.flag_rate, column="panel (a)", precision=3)
            add("level_median_db", plate.level_median_db, column="panel (b)", precision=2)
            add("input_median", plate.input_median, column="panel (c)", precision=2)
            add("input_rail_frames", plate.rail_frames, column="panel (c)", kind="int")
            add("spectrum_pilot_all_db", plate.all_pilot_db, column="middle panel", precision=1)
            add("populated_months", plate.populated_months, column="months", kind="int")
            add("blank_months", plate.blank_months, column="lower panel", kind="int")
            add("predicted_anchor_hz", plate.predicted_anchor_hz, column="lower panel", precision=1)
            add("measured_anchor_hz", plate.measured_anchor_hz, column="anchor [Hz]", precision=1)
            add("peak_frames", float(plate.peak_offsets_hz.size), column="containment panel", kind="int")
            add("peak_abs_median_hz", plate.peak_abs_median_hz, column="containment panel", precision=1)
            for k in SPANS:
                add(f"in_span_{k}", plate.in_span.get(k, math.nan), column="containment panel", precision=3)
        if plate.has_point:
            add("rho", plate.rho, column=r"$\rho$", kind="int")
            add("eta", plate.eta, column=r"$\eta$", precision=4)
        if plate.has_point and plate.present:
            add("kept_frames", plate.kept_frames, column="kept", kind="int")
            add("masked_fraction_era", plate.masked_fraction_era, column="panel (d)", precision=4)
            add("z_bulk_centre", plate.z_bulk_centre, column="panel (d)", precision=3, status="derived")
            add("z_bulk_scale", plate.z_bulk_scale, column="panel (d)", precision=3, status="derived")
        if plate.has_keep:
            add("removed_fraction", plate.removed_fraction, column=r"removed [\%]", precision=5,
                renderings=(f"{100.0 * plate.removed_fraction:.3f}%",))
            add("removed_pilot_db", plate.removed_pilot_db, column="middle panel", precision=1)
            add("spectrum_pilot_keep_db", plate.keep_pilot_db, column="middle panel", precision=1)
        if plate.curves.present:
            add("r_tol", plate.r_tol, column="operating-point panel", precision=4)
            add("diagnostic_masked_fraction", plate.diagnostic_masked_fraction, column="operating-point panel",
                precision=4)
            add("diagnostic_r_sys", plate.diagnostic_r_sys, column="operating-point panel", precision=3)
            for name, value in (("evaluation_masked_fraction", plate.evaluation_masked_fraction),
                                ("evaluation_masked_fraction_q16", plate.evaluation_masked_q16),
                                ("evaluation_masked_fraction_q84", plate.evaluation_masked_q84)):
                add(name, value, column="operating-point panel", precision=4)
            for name, value in (("evaluation_r_sys", plate.evaluation_r_sys),
                                ("evaluation_r_sys_q16", plate.evaluation_r_sys_q16),
                                ("evaluation_r_sys_q84", plate.evaluation_r_sys_q84)):
                add(name, value, column="operating-point panel", precision=3)

        body.append([
            str(ch),
            f"{tex(plate.era_months.replace('..', '--'))} {tex(plate.era_state)}".strip() if plate.era_months else DASH,
            _math(fmt_int(plate.era_frames)),
            _math(fmt_int(plate.rho)),
            _math(fmt(plate.eta, 4, sig=True)) if plate.has_point else DASH,
            _math(fmt_int(plate.kept_frames)),
            _math(fmt(100.0 * plate.removed_fraction, 3)) if plate.has_keep else DASH,
            _math(fmt_int(plate.populated_months)),
            _math(fmt(plate.measured_anchor_hz, 1)),
            _marks(plate)])
    frag.tex = booktabs(header, body, "llrrrrrrrl")

    tally = counts(rows)
    frag.add(f"{pfx}.channels", len(rows), kind="int", status="derived", column="plates")
    for name, value in tally.items():
        frag.add(f"{pfx}.count.{name}", value, kind="int", status="derived", column="plates")
    frag.add(f"{pfx}.full_scale_native", FULL_SCALE_NATIVE, precision=0, status="derived", column="panel (c)")
    frag.add(f"{pfx}.census_window_hz", WINDOW_HZ, precision=0, status="derived", column="containment panel")
    for k in SPANS:
        frag.add(f"{pfx}.span_half_width_hz.k{k}", span_half_width_hz(k), precision=1, status="derived",
                 column="containment panel")

    frag.notes.append(f"label {LABEL}: one plate per channel ({PLATE_LABEL.format(channel=0).replace('0', 'NN')}), "
                      "each five layers on the channel's current era; they replace the superseded health-filtered "
                      "plates of figs/archive_health_v1")
    frag.notes.append("every layer runs on the run's own era mask --- health-admitted current-era frames that carry a "
                      "recorded time --- so the frame count is the ledger's era frames less the frames without a time, "
                      "which the plate prints beside it")
    frag.notes.append("no marked point is a selection: the selector returned no operating point on any channel, so the "
                      "diagnostic point drawn on panel (d) and on the trade panel is the least-residual point of the "
                      "evaluated calibration surface")
    frag.notes.append("panel (a) overlays the null the threshold was priced against (null.coarse_centre and "
                      "null.coarse_core_sigma, read on the calibration block of the same era) on a histogram of the "
                      "whole era; the two populations differ by the evaluation block")
    frag.notes.append("panel (d) has no priced null in Z units --- the ledger's fine null (fine_centre, "
                      "fine_core_width_factor) is the bulk-bin distribution of T, not of Z --- so the bulk drawn there "
                      "is fitted on the panel's own population by the run's recipe (median, left-side core scale) and "
                      "is keyed z_bulk_centre / z_bulk_scale")
    frag.notes.append("the middle panel draws P_all and P_keep|keep and tabulates the removed contribution "
                      "P_all - P_keep,contrib, formed in linear power on the common denominator N: it is not the "
                      "difference of the two drawn curves, whose denominators differ")
    frag.notes.append("the lower panel is a detector-statistic heatmap over every health-admitted frame of the "
                      "channel, not only the era: the products retain one feed-summed spectrum per frame and nothing "
                      "within a frame, so no sub-frame spectrogram exists and a blank month is an unobserved month")
    if off:
        frag.notes.append(f"channels {_list(off)}: the current era is a transmitter-off era, so the containment panel "
                          "reads the previous on era as the run does; the histograms and the spectra stay on the "
                          "current era and measure the off state")
    if refused:
        frag.notes.append(f"channels {_list(refused)}: the selector refused before a surface was evaluated (frames "
                          "without a shelf estimate leave no floor), so panel (d), the after-mask spectrum and the "
                          "trade panel are empty and their cells are dashed")
    if no_keep:
        frag.notes.append(f"channels {_list(no_keep)}: the diagnostic point keeps no current-era frame, so the "
                          "after-mask spectrum is unavailable rather than a zero-power measurement")
    if no_curves:
        frag.notes.append(f"channels {_list(no_curves)}: {POINTS_CSV} carries no candidate point, so the trade panel "
                          "is empty")
    if missing:
        frag.notes.append(f"channels {_list(missing)}: the product could not be opened "
                          f"({'; '.join(sorted({p.missing_reason for p in rows if not p.present}))}), so the plate "
                          "carries only its ledger head and the row is dashed")
    ungated = [p.channel for p in rows if p.present and not p.health_gate_agrees]
    if ungated:
        frag.notes.append(f"channels {_list(ungated)}: this process could not apply the run's frame-health gate "
                          f"({HEALTH_GATE_SCHEMA}, which needs pilot_proxy) and read valid frames alone, so the frame "
                          "counts are the run's plus whatever the gate would have removed; the plate says so in its head")
    frag.notes.append("the plates print no false-alarm rate, no chain gain and no residual ratio R: those are the "
                      "ledgers' columns, and the trade panel marks r_sys against r_tol rather than their ratio")
    return frag
